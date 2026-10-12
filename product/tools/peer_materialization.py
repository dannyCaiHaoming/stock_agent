"""已有同行物化的数据业务层；不启动模型、不声明Agent执行成功。"""
from __future__ import annotations
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from product.mcp.live.peer_candidates import validate_peer_candidate_pool
from product.mcp.provenance import parse_timestamp, content_hash
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash

class PeerMaterializationError(ValueError):
    pass

ResearchMaterialsStageError = PeerMaterializationError

def _read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PeerMaterializationError("PEER_MATERIALIZATION_OBJECT_REQUIRED")
    return value

def _write_object(path, value):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise PeerMaterializationError("PEER_MATERIALIZATION_OUTPUT_EXISTS")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+"\n",encoding="utf-8")

def _read_object_list(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_SOURCE_ACCESS_INVALID") from exc
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_SOURCE_ACCESS_INVALID")
    return [dict(item) for item in value]

def _verify_merged_peer_gate_time(
    base_gate: Mapping[str, Any], peer_gate: Mapping[str, Any],
    allowed: list[Mapping[str, Any]], excluded: list[Mapping[str, Any]],
    *, observed_at: str, calendar=None,
) -> str:
    """Fail closed at the final cutoff after both independently gated captures."""
    base_cutoff = parse_timestamp(base_gate["decision_cutoff"])
    peer_cutoff = parse_timestamp(peer_gate["decision_cutoff"])
    final_cutoff = max(base_cutoff, peer_cutoff)
    if final_cutoff > parse_timestamp(observed_at):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_CUTOFF_IN_FUTURE")
    if (base_gate.get("calendar_lock") and peer_gate.get("calendar_lock")
            and base_gate["calendar_lock"] != peer_gate["calendar_lock"]):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_CALENDAR_MISMATCH")
    allowed_ids = [fact.get("evidence_id") for fact in allowed]
    excluded_ids = [fact.get("evidence_id") for fact in excluded]
    if (len(allowed_ids) != len(set(allowed_ids))
            or set(allowed_ids) & set(excluded_ids)):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_EVIDENCE_DUPLICATE")
    for fact in allowed:
        if not all(isinstance(fact.get(field), str) for field in (
            "source_id", "as_of", "retrieved_at"
        )):
            raise ResearchMaterialsStageError("PEER_MATERIALIZATION_PROVENANCE_INVALID")
        time_fields = ["as_of", "retrieved_at"]
        if "published_at" in fact:
            time_fields.append("published_at")
        if any(parse_timestamp(fact[field]) > final_cutoff for field in time_fields):
            raise ResearchMaterialsStageError("PEER_MATERIALIZATION_FINAL_PIT_LEAKAGE")
        if fact.get("freshness_status") == "FRESH" and fact.get("source_type") != "derived":
            if fact.get("kind") == "price":
                if calendar is not None:
                    sessions = sorted(parse_timestamp(item)
                                      for item in calendar.completed_sessions(final_cutoff))
                    if parse_timestamp(fact["as_of"]) not in sessions[-2:]:
                        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_FINAL_PRICE_STALE")
            else:
                form = (fact.get("metadata") or {}).get("form", "")
                threshold = 800 if fact.get("usage") == "comparison" else (
                    450 if form in {"10-K", "10-K/A"}
                    else 200 if form in {"10-Q", "10-Q/A"}
                    else 90 if form in {"8-K", "8-K/A"}
                    else 90 if fact.get("kind") == "ownership" and form in {
                        "3", "3/A", "4", "4/A", "5", "5/A"
                    } else None
                )
                if threshold is not None and (
                    final_cutoff - parse_timestamp(fact["as_of"]) > timedelta(days=threshold)
                ):
                    raise ResearchMaterialsStageError("PEER_MATERIALIZATION_FINAL_FACT_STALE")
    return final_cutoff.isoformat().replace("+00:00", "Z")

def materialize_selected_peers(
    materials_run: Path, *, source_access_path: Path, cache_root: Path,
    sec_user_agent: str, output_dir: Path,
    collector=None, peer_supplement_collector=None, memory_root: Path | None = None,
    now=lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """用现有只读采集器核实并冻结 LLM 选择的有限同行资料。"""

    from product.mcp.live.contracts import validate_contract
    from product.mcp.provenance import content_hash, iso_utc
    from product.runtime.evidence_gate import run_live_evidence_gate
    from product.mcp.live.market import load_locked_calendar
    from product.runtime.research_memory import ResearchMemory, resolve_memory_root

    materials_run = Path(materials_run).resolve()
    output_dir = Path(output_dir).resolve()
    cache_root = Path(cache_root).resolve()
    memory = (
        ResearchMemory(resolve_memory_root(Path(__file__).resolve().parents[2], memory_root))
        if memory_root is not None else None
    )
    if output_dir.exists():
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_OUTPUT_EXISTS")
    manifest = _read_object(materials_run / "research/material-preparation-manifest.json")
    if manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash"):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_MANIFEST_INVALID")
    pool = _read_object(materials_run / "research/peer-candidate-pool.json")
    validate_peer_candidate_pool(pool)
    candidates = {
        item["candidate_id"]: item
        for group in pool["groups"] for item in group["candidates"]
    }
    selected_candidates = []
    for output in manifest["outputs"]:
        if output["preparation_kind"] != "PEER_SELECTION":
            continue
        for selection in output["selections"]:
            candidate = candidates.get(selection["candidate_id"])
            if candidate is None:
                raise ResearchMaterialsStageError("PEER_MATERIALIZATION_CANDIDATE_UNKNOWN")
            selected_candidates.append({
                "holding_security_id": output["security_id"],
                "candidate_id": candidate["candidate_id"], "symbol": candidate["symbol"],
                "name": candidate["name"], "country": candidate.get("country"),
                "rationale": selection["rationale"],
                "materialized_security_id": f"US:COMMON_STOCK:{candidate['symbol']}",
            })
    access_records = _read_object_list(Path(source_access_path).resolve())
    approved_limits = [
        record.get("operator_approval", {}).get("record", {}).get("scope", {}).get("max_positions")
        for record in access_records
    ]
    approved_limits = [
        item for item in approved_limits
        if isinstance(item, int) and not isinstance(item, bool) and item > 0
    ]
    max_positions = min(approved_limits) if approved_limits else len(selected_candidates)
    unsupported = [
        {**item, "skip_reason": "SEC_IDENTITY_SCOPE_UNSUPPORTED"}
        for item in selected_candidates
        if item.get("country") not in {"United States", "US", "USA"}
    ]
    eligible_candidates = [
        item for item in selected_candidates
        if item.get("country") in {"United States", "US", "USA"}
    ]
    by_holding: dict[str, list[dict[str, Any]]] = {}
    holding_order: list[str] = []
    for item in eligible_candidates:
        holding = item["holding_security_id"]
        if holding not in by_holding:
            by_holding[holding] = []
            holding_order.append(holding)
        by_holding[holding].append(item)
    selected = []
    ordinal = 0
    while len(selected) < max_positions:
        added = False
        for holding in holding_order:
            values = by_holding[holding]
            if ordinal < len(values) and len(selected) < max_positions:
                selected.append(values[ordinal])
                added = True
        if not added:
            break
        ordinal += 1
    selected_keys = {
        (item["holding_security_id"], item["candidate_id"]) for item in selected
    }
    skipped = [
        {**item, "skip_reason": "SOURCE_ACCESS_POSITION_LIMIT"}
        for item in eligible_candidates
        if (item["holding_security_id"], item["candidate_id"]) not in selected_keys
    ] + unsupported
    unique = {item["materialized_security_id"]: item for item in selected}
    if not unique:
        result = {
            "schema_version": "peer-materialization/1.0.0", "status": "SOURCE_LIMITED",
            "materials_run_id": manifest["run_id"], "selected": [],
            "gaps": [{"reason_code": "NO_PEER_SELECTED", "impact": "正式同行比较没有已核实同行资料。"}],
        }
        result["materialization_hash"] = legacy_envelope_hash(result, hash_field="materialization_hash")
        output_dir.mkdir(parents=True)
        _write_object(output_dir / "peer-materialization-manifest.json", result)
        return result
    base_gate = _read_object(materials_run / "evidence/gate.json")
    base_content_hash = canonical_hash({
        key: value for key, value in base_gate.items() if key not in {"run_id", "bundle_hash"}
    })
    base_allowed = list(base_gate.get("allowed_evidence", []))
    existing = set(base_gate.get("input_evidence_ids", base_gate.get("allowed_evidence_ids", [])))
    existing_security_ids = {
        item.get("security_id") for item in base_allowed
        if isinstance(item.get("security_id"), str)
    }
    reused_security_ids = set(unique) & existing_security_ids
    collect_unique = {
        security_id: item for security_id, item in unique.items()
        if security_id not in reused_security_ids
    }
    selected = [{
        **item,
        "materialization_source": (
            "REUSED_FROZEN_GATE"
            if item["materialized_security_id"] in reused_security_ids
            else "COLLECTED_CURRENT_RUN"
        ),
    } for item in selected]
    timestamp = iso_utc(now())
    output_dir.mkdir(parents=True)
    portfolio = None
    snapshot = {"snapshot_hash": None, "gaps": []}
    peer_gate = {
        "bundle_hash": None,
        "decision_cutoff": base_gate["decision_cutoff"],
        "input_evidence_ids": [], "allowed_evidence": [],
        "excluded": [],
    }
    if collect_unique:
        portfolio = {
            "schema_version": "live-portfolio/2.0.0", "purpose": "COMMON_STOCK_DATA_COLLECTION",
            "base_currency": "USD", "source_id": f"peer-selection:{manifest['run_id']}",
            "as_of": timestamp, "retrieved_at": timestamp,
            "positions": [
                {"security_id": security_id, "ticker": item["symbol"], "exchange": None, "share_class": None}
                for security_id, item in sorted(collect_unique.items())
            ],
        }
        validate_contract("portfolio", portfolio)
        portfolio_path = output_dir / "peer-collection-input.json"
        _write_object(portfolio_path, portfolio)
        supplement_results = {}
        reused_bundle = None
        source_access = None
        if collector is None or peer_supplement_collector is not None:
            from product.mcp.live.collection import validate_live_collection_configuration
            from product.mcp.live.research_supplement_collection import (
                capture_external_research_results, capture_public_company_news_result,
            )
            source_access = validate_live_collection_configuration(
                Path(source_access_path).resolve(), at=now(),
            )
            if memory is not None and collector is None:
                from product.tools.data_materialization import _snapshot_bundle_cache_valid
                plans = [memory.plan(security_id, "live", "live_snapshot", planning_as_of=timestamp)
                         for security_id in collect_unique]
                if all(plan["mode"] == "SKIP_FRESH" for plan in plans):
                    first = memory.checkpoint(next(iter(collect_unique)), "live", "live_snapshot")
                    try:
                        candidate = memory.load_snapshot_bundle(first)
                        prior_ids = {item["security_id"] for item in candidate["portfolio"]["positions"]}
                        if (prior_ids == set(collect_unique)
                            and candidate.get("cache_root") == str(cache_root)
                            and candidate.get("source_item", {}).get("access_hash") == content_hash(source_access)
                            and isinstance(candidate.get("source_item", {}).get("supplement_results"), dict)
                            and _snapshot_bundle_cache_valid(candidate, cache_root=cache_root)
                            and all(memory.checkpoint(security_id, "live", "live_snapshot")
                                    .get("state", {}).get("snapshot_hash") == candidate["snapshot"]["snapshot_hash"]
                                    for security_id in collect_unique)):
                            reused_bundle = candidate
                    except (OSError, ValueError, KeyError, TypeError, AttributeError):
                        reused_bundle = None
            if reused_bundle is not None:
                supplement_results = reused_bundle["source_item"]["supplement_results"]
            else:
                supplement_results = (peer_supplement_collector or capture_external_research_results)(
                    portfolio["positions"], access=source_access, cache_root=cache_root,
                    state_root=output_dir / "peer-source-state", peer_scope=True,
                    now=lambda: iso_utc(now()),
                )
                for security_id, item in collect_unique.items():
                    supplement_results.setdefault(security_id, []).append(
                        capture_public_company_news_result(
                            security_id=security_id, ticker=item["symbol"],
                            issuer_name=item["name"], cache_root=cache_root,
                            decision_cutoff=base_gate["decision_cutoff"], now=now,
                        )
                    )
        collection_dir = output_dir / "source-snapshot"
        if reused_bundle is None:
            default_collector = collector is None
            collector = collector or __import__(
                "product.mcp.live.collection", fromlist=["collect_live_snapshot"]
            ).collect_live_snapshot
            collected = collector(
                portfolio_path, access_path=source_access_path, output_dir=collection_dir,
                cache_root=cache_root, sec_user_agent=sec_user_agent,
                **({"peer_scope": True} if default_collector else {}),
            )
            snapshot = _read_object(Path(collected["snapshot_path"]))
            calendar_record = _read_object(Path(collected["calendar_lock"]))
        else:
            from product.tools.snapshot import freeze_snapshot
            previous = reused_bundle["snapshot"]
            snapshot = freeze_snapshot(
                snapshot_id=f"peer-snapshot:{manifest['run_id']}",
                portfolio=portfolio, request_started_at=previous["request_started_at"],
                decision_cutoff=iso_utc(now()), facts=previous["facts"],
                source_access=previous["source_access"], raw_records=previous["raw_records"],
                collection_events=previous["collection_events"], gaps=previous["gaps"],
                identity=previous.get("identity"), universe=previous.get("universe"),
                source_selections=previous.get("source_selections"),
            )
            calendar_record = reused_bundle["calendar"]
            collection_dir.mkdir()
            _write_object(collection_dir / "snapshot.json", snapshot)
            _write_object(collection_dir / "calendar.json", calendar_record)
        peer_gate = run_live_evidence_gate(
            snapshot, run_id=manifest["run_id"], calendar=load_locked_calendar(calendar_record)
        ).artifact
        if supplement_results:
            from product.mcp.live.research_supplement_collection import build_research_supplements
            from product.tools.data_materialization import merge_research_supplement_evidence
            supplement_dir = output_dir / "peer-supplements"
            supplement_dir.mkdir()
            packages = build_research_supplements(
                portfolio["positions"], gate=peer_gate,
                external_results=supplement_results, run_id=manifest["run_id"],
            )
            prepared = {
                "gate": peer_gate,
                "preparation": {"common_cutoff": peer_gate["decision_cutoff"]},
            }
            for package in packages:
                security_id = package["security_id"]
                prepared = merge_research_supplement_evidence(
                    prepared, background=package["background"],
                    batch=package["batch"], package=package["package"],
                    allowed_security_ids={security_id},
                )
                _write_object(supplement_dir / f"{package['ticker']}-background.json", package["background"])
                _write_object(supplement_dir / f"{package['ticker']}-batch.json", package["batch"])
                _write_object(supplement_dir / f"{package['ticker']}-package.json", package["package"])
            peer_gate = prepared["gate"]
        if memory is not None:
            from product.runtime.research_memory import VIEW_CONTEXT_FIELDS, infer_dataset, infer_provider
            source_item = {
                "access_hash": content_hash(source_access),
                "supplement_results": supplement_results,
            }
            for security_id in collect_unique:
                if reused_bundle is None:
                    with memory.dataset_lock(security_id, "live", "live_snapshot"):
                        plan = memory.plan(
                            security_id, "live", "live_snapshot",
                            planning_as_of=iso_utc(now()),
                        )
                        stored = memory.store_snapshot_bundle(
                            security_id=security_id, portfolio=portfolio,
                            snapshot=snapshot, calendar=calendar_record,
                            source_item=source_item, cache_root=cache_root,
                        )
                        memory.ingest_dataset(
                            plan=plan, facts=[],
                            status=("FETCHED_BOOTSTRAP" if plan["mode"] == "BOOTSTRAP"
                                    else "FETCHED_INCREMENTAL"),
                            completed_at=snapshot["decision_cutoff"],
                            details={"request_count": len(snapshot.get("collection_events", [])),
                                     "source_result": "PEER_SNAPSHOT_FROZEN"},
                            state={"object_ref": stored["object_ref"],
                                   "object_hash": stored["object_hash"],
                                   "snapshot_hash": snapshot["snapshot_hash"]},
                        )
                facts = [fact for fact in peer_gate["allowed_evidence"]
                         if fact.get("security_id") == security_id]
                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for fact in facts:
                    # Gate 时效标签属于冻结视图，不是来源事实版本；视图仍保留原 fact。
                    source_fact = {key: value for key, value in fact.items()
                                   if key not in VIEW_CONTEXT_FIELDS}
                    grouped.setdefault((infer_provider(fact), infer_dataset(fact)), []).append(source_fact)
                for (provider, dataset), dataset_facts in sorted(grouped.items()):
                    with memory.dataset_lock(security_id, provider, dataset):
                        plan = memory.plan(
                            security_id, provider, dataset,
                            planning_as_of=iso_utc(now()),
                        )
                        new_versions = memory.new_version_count(dataset_facts)
                        if plan["mode"] == "SKIP_FRESH" and not new_versions:
                            continue
                        memory.ingest_dataset(
                            plan=plan, facts=dataset_facts,
                            status=("FETCHED_BOOTSTRAP" if plan["mode"] == "BOOTSTRAP"
                                    else "FETCHED_INCREMENTAL" if new_versions
                                    else "CHECKED_NO_CHANGE"),
                            completed_at=snapshot["decision_cutoff"],
                            watermark=max((fact["as_of"] for fact in dataset_facts),
                                          key=parse_timestamp),
                            details={"request_count": 0,
                                     "source_result": "PEER_GATE_VERSIONED"},
                        )
                view = memory.save_view(
                    run_id=manifest["run_id"], security_id=security_id,
                    decision_cutoff=peer_gate["decision_cutoff"], facts=facts,
                    gaps=snapshot.get("gaps", []), conflicts=[],
                )
                view_dir = output_dir / "peer-views"
                view_dir.mkdir(exist_ok=True)
                _write_object(view_dir / f"{collect_unique[security_id]['symbol']}.json", view)
            if reused_bundle is not None:
                selected = [
                    {**item, "materialization_source": "REUSED_RESEARCH_MEMORY"}
                    if item["materialized_security_id"] in collect_unique else item
                    for item in selected
                ]
    peer_facts = [
        item for item in peer_gate["allowed_evidence"]
        if item.get("security_id") in set(collect_unique)
    ]
    if any(item["evidence_id"] in existing for item in peer_facts):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_EVIDENCE_DUPLICATE")
    reused_facts = [
        item for item in base_allowed
        if item.get("security_id") in reused_security_ids
    ]
    allowed = [*base_gate.get("allowed_evidence", []), *peer_facts]
    excluded = [*base_gate.get("excluded", []), *peer_gate.get("excluded", [])]
    final_cutoff = _verify_merged_peer_gate_time(
        base_gate, peer_gate, allowed, excluded, observed_at=iso_utc(now()),
        calendar=(load_locked_calendar(calendar_record) if collect_unique else None),
    )
    merged_gate = {
        **base_gate,
        "decision_cutoff": final_cutoff,
        "peer_gate_hash": peer_gate["bundle_hash"],
        "base_gate_content_hash": base_content_hash,
        "input_evidence_ids": sorted(existing | set(peer_gate.get("input_evidence_ids", []))),
        "allowed_evidence": sorted(allowed, key=lambda item: item["evidence_id"]),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in allowed),
        "excluded": sorted(excluded, key=lambda item: item["evidence_id"]),
        "excluded_evidence_ids": sorted(item["evidence_id"] for item in excluded),
    }
    merged_gate["bundle_hash"] = legacy_envelope_hash(merged_gate, hash_field="bundle_hash")
    _write_object(output_dir / "gate.json", merged_gate)
    final_view = {
        "schema_version": "peer-final-evidence-view/1.0.0",
        "run_id": manifest["run_id"], "decision_cutoff": final_cutoff,
        "gate_hash": merged_gate["bundle_hash"],
        "allowed_evidence_ids": merged_gate["allowed_evidence_ids"],
        "excluded_evidence_ids": merged_gate["excluded_evidence_ids"],
        "selected_peer_security_ids": sorted(unique),
    }
    final_view["view_hash"] = legacy_envelope_hash(final_view, hash_field="view_hash")
    _write_object(output_dir / "final-view.json", final_view)
    result = {
        "schema_version": "peer-materialization/1.0.0", "status": "FROZEN",
        "materials_run_id": manifest["run_id"], "selected": selected,
        "portfolio_hash": content_hash(portfolio) if portfolio is not None else None,
        "snapshot_hash": snapshot["snapshot_hash"],
        "peer_gate_hash": peer_gate["bundle_hash"], "merged_gate_hash": merged_gate["bundle_hash"],
        "final_view_hash": final_view["view_hash"],
        "base_gate_content_hash": base_content_hash,
        "evidence_ids": sorted(item["evidence_id"] for item in [*reused_facts, *peer_facts]),
        "skipped": [{
            "holding_security_id": item["holding_security_id"],
            "candidate_id": item["candidate_id"],
            "symbol": item["symbol"],
            "reason_code": item["skip_reason"],
        } for item in skipped],
        "gaps": [
            *list(snapshot.get("gaps", [])),
            *([{
                "reason_code": "PEER_MATERIALIZATION_BOUNDED",
                "impact": (
                    f"本批访问批准最多覆盖 {max_positions} 个证券；其余 "
                    f"{len(skipped)} 个已选候选因访问上限或当前 SEC 身份范围未物化，"
                    "也未进入正式比较 Evidence。"
                ),
            }] if skipped else []),
        ],
    }
    result["materialization_hash"] = legacy_envelope_hash(result, hash_field="materialization_hash")
    _write_object(output_dir / "peer-materialization-manifest.json", result)
    return result
