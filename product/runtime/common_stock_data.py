"""将逐证券只读采集结果冻结为普通股研究 Gate。

采集器仍由现有 Provider/缓存层提供；本模块只负责批次边界、身份绑定、
共同 cutoff、PIT 过滤和单证券失败隔离，不做公司研究或投资判断。
"""

from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from product.intake.v3 import validate_handoff
from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash


DATA_PREPARATION_VERSION = "common-stock-data-preparation/1.0.0"
COLLECTION_PORTFOLIO_VERSION = "live-portfolio/2.0.0"
SOURCE_BUNDLE_VERSION = "common-stock-source-bundle/1.0.0"


class CommonStockDataError(ValueError):
    pass


def _hash_without(value: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: item for key, item in value.items() if key != field})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_common_stock_collection_portfolio(
    handoff: Mapping[str, Any],
) -> dict[str, Any]:
    """将确认 Handoff 最小化为只供现有数据适配器使用的证券集合。"""

    validate_handoff(handoff)
    positions = []
    for item in handoff["portfolio"]["positions"]:
        if item["asset_type"] != "COMMON_STOCK":
            continue
        positions.append({
            "security_id": item["security_id"],
            "ticker": item["display_symbol"].upper(),
            "exchange": None,
            "share_class": None,
        })
    if not positions:
        raise CommonStockDataError("COMMON_STOCK_COLLECTION_EMPTY")
    return {
        "schema_version": COLLECTION_PORTFOLIO_VERSION,
        "purpose": "COMMON_STOCK_DATA_COLLECTION",
        "base_currency": handoff["portfolio"]["base_currency"],
        "source_id": f"portfolio-handoff:{handoff['handoff_id']}",
        "as_of": handoff["account_snapshot"]["as_of"],
        "retrieved_at": handoff["confirmation"]["confirmed_at"],
        "positions": positions,
    }


def _security_live_result(
    position: Mapping[str, Any], *, live_portfolio: Mapping[str, Any],
    snapshot: Mapping[str, Any], calendar: Any, run_id: str,
) -> dict[str, Any]:
    """把一个已冻结的单证券快照转为 provider-neutral 采集结果。"""

    from product.mcp.live.contracts import validate_contract
    from product.mcp.live.identity import verify_frozen_identity
    from product.mcp.provenance import content_hash
    from product.runtime.evidence_gate import run_live_evidence_gate

    validate_contract("portfolio", dict(live_portfolio))
    validate_contract("snapshot", dict(snapshot))
    if snapshot.get("portfolio_hash") != content_hash(live_portfolio):
        raise CommonStockDataError("COMMON_STOCK_LIVE_PORTFOLIO_BINDING_INVALID")
    if {item["security_id"] for item in live_portfolio["positions"]} != {position["security_id"]}:
        raise CommonStockDataError("COMMON_STOCK_LIVE_SECURITY_SET_MISMATCH")
    verify_frozen_identity(
        dict(live_portfolio), snapshot.get("identity"), cutoff=snapshot["decision_cutoff"]
    )
    live_gate = run_live_evidence_gate(snapshot, run_id=run_id, calendar=calendar).artifact
    accepted = [
        copy.deepcopy(fact) for fact in live_gate["allowed_evidence"]
        if fact.get("security_id") == position["security_id"]
    ]
    accepted_ids = {fact["evidence_id"] for fact in accepted}
    research_fields = {
        "open_price", "high_price", "low_price", "historical_close_price",
        "adjusted_close_price", "share_volume", "cash_dividend", "stock_split_ratio",
    }
    cutoff = parse_timestamp(snapshot["decision_cutoff"])
    for fact in snapshot.get("facts", []):
        if (
            fact.get("security_id") != position["security_id"]
            or fact.get("semantic_field") not in research_fields
            or fact.get("evidence_id") in accepted_ids
        ):
            continue
        timestamps = [fact.get("as_of"), fact.get("published_at"), fact.get("retrieved_at")]
        if any(not isinstance(item, str) or parse_timestamp(item) > cutoff for item in timestamps):
            continue
        accepted.append(copy.deepcopy(fact))
        accepted_ids.add(fact["evidence_id"])
    return {
        "security_id": position["security_id"],
        "identity_status": "VERIFIED",
        "decision_cutoff": snapshot["decision_cutoff"],
        "facts": sorted(accepted, key=lambda fact: fact["evidence_id"]),
        "data_gaps": [
            item for item in snapshot.get("gaps", [])
            if position["security_id"] in str(item)
        ],
        "input_evidence_ids": list(live_gate["input_evidence_ids"]),
        "excluded": copy.deepcopy(live_gate["excluded"]),
        "conflicts": copy.deepcopy(live_gate["conflicts"]),
    }


def _safe_security_component(security_id: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "-", security_id).strip("-.") or "security"
    return f"{label[:48]}-{canonical_hash(security_id)[:10]}"


def validate_common_stock_source_bundle(
    handoff: Mapping[str, Any], *, gate: Mapping[str, Any],
    preparation: Mapping[str, Any], source_bundle_path: Path,
) -> None:
    """从底层快照重算当前数据包绑定；任一漂移在 Agent 前失败。"""

    from product.mcp.live.contracts import external_path, validate_contract
    from product.mcp.live.market import load_locked_calendar
    from product.mcp.provenance import content_hash

    validate_handoff(handoff)
    if gate.get("bundle_hash") != canonical_hash({
        key: value for key, value in gate.items() if key != "bundle_hash"
    }):
        raise CommonStockDataError("COMMON_STOCK_GATE_HASH_MISMATCH")
    if preparation.get("preparation_hash") != canonical_hash({
        key: value for key, value in preparation.items() if key != "preparation_hash"
    }):
        raise CommonStockDataError("COMMON_STOCK_PREPARATION_HASH_MISMATCH")
    bundle_path = external_path(source_bundle_path)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle.get("schema_version") != SOURCE_BUNDLE_VERSION:
        raise CommonStockDataError("COMMON_STOCK_SOURCE_BUNDLE_VERSION_INVALID")
    if bundle.get("bundle_hash") != canonical_hash({
        key: value for key, value in bundle.items() if key != "bundle_hash"
    }):
        raise CommonStockDataError("COMMON_STOCK_SOURCE_BUNDLE_HASH_MISMATCH")
    expected_bindings = {
        "run_id": gate.get("run_id"),
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
    }
    if any(bundle.get(key) != value for key, value in expected_bindings.items()):
        raise CommonStockDataError("COMMON_STOCK_SOURCE_BUNDLE_BINDING_INVALID")
    if (
        gate.get("run_id") != preparation.get("run_id")
        or preparation.get("handoff_id") != handoff["handoff_id"]
        or preparation.get("handoff_hash") != handoff["handoff_hash"]
        or preparation.get("portfolio_hash") != handoff["portfolio_hash"]
        or gate.get("decision_cutoff") != preparation.get("common_cutoff")
    ):
        raise CommonStockDataError("COMMON_STOCK_DATA_PACKAGE_BINDING_INVALID")
    source_access = bundle.get("source_access")
    if not isinstance(source_access, list) or canonical_hash(source_access) != bundle.get("source_access_hash"):
        raise CommonStockDataError("COMMON_STOCK_SOURCE_ACCESS_BINDING_INVALID")
    for access in source_access:
        validate_contract("source-access", access)
    if (
        gate.get("source_mode") != "live-read-only"
        or gate.get("source_bundle_id") != bundle.get("bundle_id")
        or gate.get("source_bundle_hash") != bundle.get("bundle_hash")
        or preparation.get("source_bundle_id") != bundle.get("bundle_id")
        or preparation.get("source_bundle_hash") != bundle.get("bundle_hash")
    ):
        raise CommonStockDataError("COMMON_STOCK_SOURCE_BUNDLE_REFERENCE_INVALID")
    root = bundle_path.parent.resolve()
    collection_input_path = (root / "collection-input.json").resolve()
    if not collection_input_path.is_relative_to(root):
        raise CommonStockDataError("COMMON_STOCK_SOURCE_PATH_ESCAPE")
    collection_input = json.loads(collection_input_path.read_text(encoding="utf-8"))
    validate_contract("portfolio", collection_input)
    if (
        canonical_hash(collection_input) != bundle.get("collection_input_hash")
        or preparation.get("collection_input_hash") != bundle.get("collection_input_hash")
    ):
        raise CommonStockDataError("COMMON_STOCK_COLLECTION_INPUT_HASH_MISMATCH")
    expected_ids = {
        item["security_id"] for item in handoff["portfolio"]["positions"]
        if item["asset_type"] == "COMMON_STOCK"
    }
    if {item["security_id"] for item in collection_input["positions"]} != expected_ids:
        raise CommonStockDataError("COMMON_STOCK_COLLECTION_INPUT_COVERAGE_INVALID")
    items = bundle.get("items")
    if (
        not isinstance(items, list) or len(items) != len(expected_ids)
        or {item.get("security_id") for item in items} != expected_ids
    ):
        raise CommonStockDataError("COMMON_STOCK_SOURCE_BUNDLE_COVERAGE_INVALID")
    preparation_rows = {
        item.get("security_id"): item for item in preparation.get("items", [])
        if isinstance(item, Mapping)
    }
    if set(preparation_rows) != expected_ids:
        raise CommonStockDataError("COMMON_STOCK_PREPARATION_COVERAGE_INVALID")
    facts_by_id: dict[str, Mapping[str, Any]] = {}
    input_ids: set[str] = set()
    excluded_by_id: dict[str, Mapping[str, Any]] = {}
    expected_conflicts: list[Mapping[str, Any]] = []
    replay_results: dict[str, Mapping[str, Any]] = {}
    replay_failures: dict[str, str] = {}

    def read_ref(item: Mapping[str, Any], field: str) -> tuple[Path, dict[str, Any]]:
        ref = item.get(field)
        if not isinstance(ref, str):
            raise CommonStockDataError("COMMON_STOCK_SOURCE_REFERENCE_MISSING")
        path = (root / ref).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise CommonStockDataError("COMMON_STOCK_SOURCE_PATH_INVALID")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise CommonStockDataError("COMMON_STOCK_SOURCE_ARTIFACT_INVALID")
        return path, dict(value)

    for item in items:
        security_id = item["security_id"]
        row = preparation_rows[security_id]
        _, scoped_input = read_ref(item, "collection_input_ref")
        validate_contract("portfolio", scoped_input)
        if (
            canonical_hash(scoped_input) != item.get("collection_input_hash")
            or {value["security_id"] for value in scoped_input["positions"]} != {security_id}
        ):
            raise CommonStockDataError("COMMON_STOCK_SCOPED_INPUT_HASH_MISMATCH")
        if item.get("status") == "FAILED":
            failure_code = item.get("failure_code")
            if (
                row.get("status") != "FAILED"
                or not isinstance(failure_code, str)
                or not failure_code
                or row.get("failure_code") != failure_code
                or row.get("identity_status") != "UNVERIFIED"
                or row.get("decision_cutoff") is not None
                or row.get("evidence_ids") != []
                or row.get("data_gaps") != []
            ):
                raise CommonStockDataError("COMMON_STOCK_SOURCE_FAILURE_BINDING_INVALID")
            if any(item.get(field) is not None for field in (
                "portfolio_ref", "portfolio_hash", "snapshot_ref", "snapshot_id",
                "snapshot_hash", "calendar_ref", "calendar_hash", "source_selection",
                "source_selection_hash",
            )):
                raise CommonStockDataError("COMMON_STOCK_SOURCE_FAILURE_ARTIFACT_INVALID")
            error_ref = item.get("collection_error_ref")
            error_hash = item.get("collection_error_hash")
            if (error_ref is None) != (error_hash is None):
                raise CommonStockDataError("COMMON_STOCK_COLLECTION_ERROR_BINDING_INVALID")
            if error_ref is not None:
                _, error_record = read_ref(item, "collection_error_ref")
                if content_hash(error_record) != error_hash:
                    raise CommonStockDataError("COMMON_STOCK_COLLECTION_ERROR_HASH_MISMATCH")
                if error_record.get("failure_code") != failure_code:
                    raise CommonStockDataError("COMMON_STOCK_COLLECTION_ERROR_BINDING_INVALID")
            replay_failures[security_id] = failure_code
            continue
        if item.get("status") != "FROZEN":
            raise CommonStockDataError("COMMON_STOCK_SOURCE_ITEM_STATUS_INVALID")

        _, scoped_portfolio = read_ref(item, "portfolio_ref")
        _, snapshot = read_ref(item, "snapshot_ref")
        _, calendar_record = read_ref(item, "calendar_ref")
        if scoped_input != scoped_portfolio or canonical_hash(scoped_input) != item.get("collection_input_hash"):
            raise CommonStockDataError("COMMON_STOCK_SCOPED_INPUT_HASH_MISMATCH")
        validate_contract("portfolio", scoped_portfolio)
        validate_contract("snapshot", snapshot)
        if (
            canonical_hash(scoped_portfolio) != item.get("portfolio_hash")
            or snapshot.get("snapshot_id") != item.get("snapshot_id")
            or snapshot.get("snapshot_hash") != item.get("snapshot_hash")
            or canonical_hash(calendar_record) != item.get("calendar_hash")
        ):
            raise CommonStockDataError("COMMON_STOCK_SOURCE_ARTIFACT_HASH_MISMATCH")
        selection = next(
            (value for value in snapshot["source_selections"] if value["security_id"] == security_id),
            None,
        )
        if (
            selection is None or selection != item.get("source_selection")
            or selection.get("selection_hash") != item.get("source_selection_hash")
            or canonical_hash(snapshot["source_access"]) != bundle.get("source_access_hash")
        ):
            raise CommonStockDataError("COMMON_STOCK_SOURCE_SELECTION_BINDING_INVALID")
        position = next(
            value for value in handoff["portfolio"]["positions"]
            if value["security_id"] == security_id
        )
        result = _security_live_result(
            position, live_portfolio=scoped_portfolio, snapshot=snapshot,
            calendar=load_locked_calendar(calendar_record), run_id=str(gate.get("run_id")),
        )
        replay_results[security_id] = result
        for fact in result["facts"]:
            previous = facts_by_id.setdefault(fact["evidence_id"], fact)
            if previous != fact:
                raise CommonStockDataError("COMMON_STOCK_SOURCE_EVIDENCE_CONFLICT")
        input_ids.update(result["input_evidence_ids"])
        expected_conflicts.extend(copy.deepcopy(result["conflicts"]))
        for excluded in result["excluded"]:
            excluded_by_id[excluded["evidence_id"]] = excluded
        expected_evidence_ids = sorted(fact["evidence_id"] for fact in result["facts"])
        expected_status = "READY" if expected_evidence_ids else "INSUFFICIENT_EVIDENCE"
        if (
            row.get("status") != expected_status
            or row.get("identity_status") != "VERIFIED"
            or row.get("decision_cutoff") != result["decision_cutoff"]
            or row.get("evidence_ids") != expected_evidence_ids
            or row.get("failure_code") is not None
            or row.get("data_gaps") != result["data_gaps"]
        ):
            raise CommonStockDataError("COMMON_STOCK_PREPARATION_EVIDENCE_MISMATCH")
    expected_allowed = [facts_by_id[key] for key in sorted(facts_by_id)]
    allowed_ids = [fact["evidence_id"] for fact in expected_allowed]
    expected_excluded = [
        excluded_by_id[key] for key in sorted(excluded_by_id)
        if key not in set(allowed_ids)
    ]

    def replay_collect(position: Mapping[str, Any]) -> Mapping[str, Any]:
        security_id = position["security_id"]
        if security_id in replay_failures:
            raise CommonStockDataError(replay_failures[security_id])
        return replay_results[security_id]

    expected = assemble_common_stock_evidence(
        handoff, run_id=str(gate["run_id"]), collect_security=replay_collect,
    )
    completed_at = preparation.get("completed_at")
    if not isinstance(completed_at, str):
        raise CommonStockDataError("COMMON_STOCK_PREPARATION_COMPLETION_INVALID")
    parse_timestamp(completed_at)
    expected["preparation"]["completed_at"] = completed_at
    if bundle.get("decision_cutoff") != expected["preparation"]["common_cutoff"]:
        raise CommonStockDataError("COMMON_STOCK_SOURCE_BUNDLE_CUTOFF_INVALID")
    expected_gate = expected["gate"]
    expected_gate.update({
        "source_mode": "live-read-only",
        "source_bundle_id": bundle["bundle_id"],
        "source_bundle_hash": bundle["bundle_hash"],
        "input_evidence_ids": sorted(input_ids),
        "excluded_evidence_ids": [item["evidence_id"] for item in expected_excluded],
        "excluded": expected_excluded,
        "conflicts": expected_conflicts,
    })
    expected_gate["bundle_hash"] = _hash_without(expected_gate, "bundle_hash")
    expected_preparation = expected["preparation"]
    expected_preparation.update({
        "source_mode": "live-read-only",
        "source_bundle_id": bundle["bundle_id"],
        "source_bundle_hash": bundle["bundle_hash"],
        "source_bundle_ref": "source-bundle.json",
    })
    expected_preparation["preparation_hash"] = _hash_without(
        expected_preparation, "preparation_hash"
    )

    def read_snapshot(name: str) -> dict[str, Any]:
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENTAL_ARTIFACT_MISSING")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, Mapping):
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENTAL_ARTIFACT_INVALID")
        value = dict(value)
        if value.get("snapshot_hash") != _hash_without(value, "snapshot_hash"):
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENTAL_ARTIFACT_HASH_MISMATCH")
        return value

    if "benchmark" in preparation:
        expected = merge_benchmark_research_evidence(
            expected, benchmark=read_snapshot("benchmark-snapshot.json")
        )
    if "official_macro" in preparation:
        expected = merge_macro_research_evidence(
            expected, macro=read_snapshot("official-macro-snapshot.json")
        )
    if "options" in preparation:
        expected = merge_option_research_evidence(
            expected, options=read_snapshot("portfolio-option-snapshot.json")
        )

    peer_path = root / "peer-candidate-pool.json"
    if peer_path.is_file():
        peer_pool = json.loads(peer_path.read_text(encoding="utf-8"))
        if (
            not isinstance(peer_pool, Mapping)
            or peer_pool.get("pool_hash") != _hash_without(peer_pool, "pool_hash")
        ):
            raise CommonStockDataError("COMMON_STOCK_PEER_POOL_HASH_MISMATCH")
        peer_record = {
            "status": "CANDIDATES_FROZEN",
            "artifact_ref": "peer-candidate-pool.json",
            "pool_hash": peer_pool["pool_hash"],
            "selection_authority": "LLM_REQUIRED",
        }
    else:
        peer_record = {
            "status": "SOURCE_LIMITED",
            "reason": "SNAPSHOT_UNIVERSE_MISSING",
            "selection_authority": "LLM_REQUIRED",
        }
    expected["preparation"].update({
        "collection_input_schema": COLLECTION_PORTFOLIO_VERSION,
        "collection_input_hash": bundle["collection_input_hash"],
        "collection_input_ref": "collection-input.json",
        "source_bundle_ref": "source-bundle.json",
        "authoritative_portfolio_source": "portfolio-handoff-v3",
        "collection_only_fields_not_for_research": [],
        "peer_candidate_pool": peer_record,
    })
    expected["preparation"]["preparation_hash"] = _hash_without(
        expected["preparation"], "preparation_hash"
    )
    if gate != expected["gate"]:
        raise CommonStockDataError("COMMON_STOCK_GATE_RECONSTRUCTION_MISMATCH")
    if preparation != expected["preparation"]:
        raise CommonStockDataError("COMMON_STOCK_PREPARATION_RECONSTRUCTION_MISMATCH")


def collect_common_stock_data_from_handoff(
    handoff_path: Path, *, access_path: Path, output_dir: Path, cache_root: Path,
    sec_user_agent: str, run_id: str, benchmark_id: str | None = None,
    benchmark_ticker: str | None = None,
) -> dict[str, Any]:
    """通过现有只读适配器自动生成 Gate；不启动模型或完整组合估值。"""

    from product.mcp.live.collection import (
        collect_live_snapshot,
        validate_live_collection_configuration,
    )
    from product.mcp.live.contracts import external_path, validate_contract
    from product.mcp.live.market import load_locked_calendar
    from product.mcp.provenance import content_hash

    handoff_file = external_path(handoff_path)
    handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
    collection_portfolio = build_common_stock_collection_portfolio(handoff)
    validate_contract("portfolio", collection_portfolio)
    access_file = external_path(access_path)
    validation_time = datetime.now(timezone.utc)
    access = validate_live_collection_configuration(access_file, at=validation_time)
    destination = external_path(output_dir)
    if destination.exists():
        raise CommonStockDataError("COMMON_STOCK_DATA_OUTPUT_EXISTS")
    destination.mkdir(parents=True, mode=0o700)
    collection_input_path = destination / "collection-input.json"
    collection_input_path.write_text(
        json.dumps(collection_portfolio, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    collected_results: dict[str, Mapping[str, Any]] = {}
    source_items: list[dict[str, Any]] = []
    successful_snapshots: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    source_root = destination / "source-snapshots"
    source_root.mkdir(mode=0o700)
    for ordinal, position in enumerate(collection_portfolio["positions"], start=1):
        security_id = position["security_id"]
        item_root = source_root / f"{ordinal:04d}-{_safe_security_component(security_id)}"
        item_root.mkdir(mode=0o700)
        scoped_portfolio = dict(collection_portfolio, positions=[copy.deepcopy(position)])
        scoped_input = item_root / "collection-input.json"
        scoped_input.write_text(
            json.dumps(scoped_portfolio, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        snapshot_dir = item_root / "snapshot"
        try:
            collected = collect_live_snapshot(
                scoped_input, access_path=access_file, output_dir=snapshot_dir,
                cache_root=cache_root, sec_user_agent=sec_user_agent,
            )
            live_portfolio = json.loads(Path(collected["portfolio_path"]).read_text(encoding="utf-8"))
            snapshot = json.loads(Path(collected["snapshot_path"]).read_text(encoding="utf-8"))
            calendar_record = json.loads(Path(collected["calendar_lock"]).read_text(encoding="utf-8"))
            calendar = load_locked_calendar(calendar_record)
            position_result = _security_live_result(
                position, live_portfolio=live_portfolio, snapshot=snapshot,
                calendar=calendar, run_id=run_id,
            )
            collected_results[security_id] = position_result
            successful_snapshots.append((live_portfolio, snapshot, calendar_record))
            selection = next(
                item for item in snapshot["source_selections"]
                if item["security_id"] == security_id
            )
            source_items.append({
                "security_id": security_id,
                "status": "FROZEN",
                "collection_input_ref": str(scoped_input.relative_to(destination)),
                "collection_input_hash": canonical_hash(scoped_portfolio),
                "portfolio_ref": str(Path(collected["portfolio_path"]).relative_to(destination)),
                "portfolio_hash": canonical_hash(live_portfolio),
                "snapshot_ref": str(Path(collected["snapshot_path"]).relative_to(destination)),
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_hash": snapshot["snapshot_hash"],
                "calendar_ref": str(Path(collected["calendar_lock"]).relative_to(destination)),
                "calendar_hash": canonical_hash(calendar_record),
                "source_selection": copy.deepcopy(selection),
                "source_selection_hash": selection["selection_hash"],
                "failure_code": None,
            })
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            code = str(exc).split(":", 1)[0]
            error_path = snapshot_dir / "collection-error.json"
            error_ref = str(error_path.relative_to(destination)) if error_path.is_file() else None
            source_items.append({
                "security_id": security_id,
                "status": "FAILED",
                "collection_input_ref": str(scoped_input.relative_to(destination)),
                "collection_input_hash": canonical_hash(scoped_portfolio),
                "portfolio_ref": None,
                "portfolio_hash": None,
                "snapshot_ref": None,
                "snapshot_id": None,
                "snapshot_hash": None,
                "calendar_ref": None,
                "calendar_hash": None,
                "source_selection": None,
                "source_selection_hash": None,
                "failure_code": code if code.startswith("LIVE_") else "COMMON_STOCK_SECURITY_COLLECTION_FAILED",
                "collection_error_ref": error_ref,
                "collection_error_hash": content_hash(json.loads(error_path.read_text(encoding="utf-8"))) if error_ref else None,
            })

    def collected_security(position: Mapping[str, Any]) -> Mapping[str, Any]:
        result = collected_results.get(position["security_id"])
        if result is None:
            failed = next(item for item in source_items if item["security_id"] == position["security_id"])
            raise CommonStockDataError(str(failed["failure_code"]))
        return result

    prepared = assemble_common_stock_evidence(
        handoff, run_id=run_id, collect_security=collected_security,
    )
    source_bundle = {
        "schema_version": SOURCE_BUNDLE_VERSION,
        "bundle_id": f"common-stock-source:{run_id}",
        "run_id": run_id,
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "collection_input_hash": canonical_hash(collection_portfolio),
        "source_access": copy.deepcopy(access),
        "source_access_hash": canonical_hash(access),
        "decision_cutoff": prepared["preparation"]["common_cutoff"],
        "items": source_items,
    }
    source_bundle["bundle_hash"] = canonical_hash(source_bundle)
    source_bundle_path = destination / "source-bundle.json"
    source_bundle_path.write_text(
        json.dumps(source_bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    gate = prepared["gate"]
    all_input_ids = {
        evidence_id for result in collected_results.values()
        for evidence_id in result["input_evidence_ids"]
    }
    accepted_ids = set(gate["allowed_evidence_ids"])
    excluded_by_id = {
        item["evidence_id"]: copy.deepcopy(item)
        for result in collected_results.values() for item in result["excluded"]
        if item["evidence_id"] not in accepted_ids
    }
    gate.update({
        "source_mode": "live-read-only",
        "source_bundle_id": source_bundle["bundle_id"],
        "source_bundle_hash": source_bundle["bundle_hash"],
        "input_evidence_ids": sorted(all_input_ids),
        "excluded_evidence_ids": sorted(excluded_by_id),
        "excluded": [excluded_by_id[key] for key in sorted(excluded_by_id)],
        "conflicts": [
            copy.deepcopy(item) for result in collected_results.values()
            for item in result["conflicts"]
        ],
    })
    gate["bundle_hash"] = canonical_hash({
        key: value for key, value in gate.items() if key != "bundle_hash"
    })
    prepared["preparation"].update({
        "source_mode": "live-read-only",
        "source_bundle_id": source_bundle["bundle_id"],
        "source_bundle_hash": source_bundle["bundle_hash"],
        "source_bundle_ref": "source-bundle.json",
    })
    peer_candidate_path = None
    peer_candidate_pool = None
    representative_snapshot = successful_snapshots[0][1] if successful_snapshots else None
    calendar_record = successful_snapshots[0][2] if successful_snapshots else None
    if representative_snapshot is not None and isinstance(representative_snapshot.get("universe"), Mapping):
        from product.mcp.live.peer_candidates import build_peer_candidate_pool
        peer_candidate_pool = build_peer_candidate_pool(
            [
                {"security_id": item["security_id"], "ticker": item["ticker"]}
                for item in collection_portfolio["positions"]
            ],
            universe=representative_snapshot["universe"],
        )
        peer_candidate_path = destination / "peer-candidate-pool.json"
        peer_candidate_path.write_text(
            json.dumps(peer_candidate_pool, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if (benchmark_id is None) != (benchmark_ticker is None):
        raise CommonStockDataError("COMMON_STOCK_BENCHMARK_BINDING_INCOMPLETE")
    if benchmark_id is not None and benchmark_ticker is not None and calendar_record is not None:
        try:
            benchmark = collect_benchmark_research_series(
                access_path=access_path,
                output_path=destination / "benchmark-snapshot.json",
                state_dir=destination / "benchmark-yahoo-state",
                cache_root=cache_root,
                calendar=load_locked_calendar(calendar_record),
                benchmark_id=benchmark_id,
                benchmark_ticker=benchmark_ticker,
            )
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            code = str(exc).split(":", 1)[0]
            benchmark = {
                "schema_version": "benchmark-research-snapshot/1.0.0",
                "status": "SOURCE_LIMITED",
                "benchmark_id": benchmark_id,
                "benchmark_ticker": benchmark_ticker,
                "evidence": [],
                "gaps": [{
                    "reason": code,
                    "impact": "技术研究不能计算相对广泛市场基准表现。",
                }],
                "retrieved_at": _utc_now(),
            }
            benchmark["snapshot_hash"] = canonical_hash(benchmark)
            (destination / "benchmark-snapshot.json").write_text(
                json.dumps(benchmark, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        prepared = merge_benchmark_research_evidence(
            prepared,
            benchmark=benchmark,
        )
        from product.mcp.live.macro import collect_official_macro_snapshot
        macro = collect_official_macro_snapshot(
            policy_path=Path(__file__).resolve().parents[1] / "mcp/live/research-source-policy.json",
            output_path=destination / "official-macro-snapshot.json",
            cache_root=cache_root,
        )
        prepared = merge_macro_research_evidence(prepared, macro=macro)
        from product.mcp.live.options import collect_portfolio_option_snapshots
        option_securities = [
            {"security_id": item["security_id"], "ticker": item["display_symbol"].upper()}
            for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "COMMON_STOCK"
        ]
        try:
            options = collect_portfolio_option_snapshots(
                securities=option_securities, access_path=access_path,
                output_path=destination / "portfolio-option-snapshot.json",
                state_root=destination / "option-yahoo-state", cache_root=cache_root,
            )
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            code = str(exc).split(":", 1)[0]
            options = {
                "schema_version": "portfolio-option-snapshot/1.0.0",
                "status": "SOURCE_LIMITED", "decision_cutoff": _utc_now(),
                "security_ids": sorted(item["security_id"] for item in option_securities),
                "evidence": [], "excluded_evidence_ids": [],
                "gaps": [{"reason": "OPTIONS_SOURCE_LIMITED", "failure_code": code}],
                "events": [], "records": [], "adapter_version": "yahoo-option-snapshot/1.0.0",
            }
            options["snapshot_hash"] = canonical_hash(options)
            (destination / "portfolio-option-snapshot.json").write_text(
                json.dumps(options, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        prepared = merge_option_research_evidence(prepared, options=options)
    prepared["preparation"].update({
        "collection_input_schema": COLLECTION_PORTFOLIO_VERSION,
        "collection_input_hash": canonical_hash(collection_portfolio),
        "collection_input_ref": "collection-input.json",
        "source_bundle_ref": "source-bundle.json",
        "authoritative_portfolio_source": "portfolio-handoff-v3",
        "collection_only_fields_not_for_research": [],
        "peer_candidate_pool": (
            {
                "status": "CANDIDATES_FROZEN",
                "artifact_ref": "peer-candidate-pool.json",
                "pool_hash": peer_candidate_pool["pool_hash"],
                "selection_authority": "LLM_REQUIRED",
            }
            if peer_candidate_pool is not None
            else {
                "status": "SOURCE_LIMITED",
                "reason": "SNAPSHOT_UNIVERSE_MISSING",
                "selection_authority": "LLM_REQUIRED",
            }
        ),
    })
    prepared["preparation"]["preparation_hash"] = canonical_hash({
        key: value for key, value in prepared["preparation"].items()
        if key != "preparation_hash"
    })
    for name, value in (
        ("gate.json", prepared["gate"]),
        ("data-preparation.json", prepared["preparation"]),
    ):
        (destination / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    result = {
        "status": "FROZEN", "run_id": run_id,
        "gate": str(destination / "gate.json"),
        "data_preparation": str(destination / "data-preparation.json"),
        "source_bundle": str(source_bundle_path),
        **({
            "benchmark_snapshot": str(destination / "benchmark-snapshot.json"),
            "official_macro_snapshot": str(destination / "official-macro-snapshot.json"),
            "portfolio_option_snapshot": str(destination / "portfolio-option-snapshot.json"),
        } if benchmark_id and calendar_record is not None else {}),
    }
    if peer_candidate_path is not None:
        result["peer_candidate_pool"] = str(peer_candidate_path)
    return result


def collect_benchmark_research_series(
    *, access_path: Path, output_path: Path, state_dir: Path, cache_root: Path,
    calendar: Any, benchmark_id: str, benchmark_ticker: str,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    session_factory: Callable[..., Any] | None = None,
    market_collector: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """只采集广泛市场基准日线；不把 ETF 送入公司 SEC 采集。"""

    import json
    from product.mcp.live.cache import SnapshotCache
    from product.mcp.live.contracts import external_path, validate_contract, require_source_admission
    from product.mcp.live.market import collect_daily, normalize_cached_research_series

    if not benchmark_id or not benchmark_ticker:
        raise CommonStockDataError("COMMON_STOCK_BENCHMARK_IDENTITY_INVALID")
    access = json.loads(external_path(access_path).read_text(encoding="utf-8"))
    if not isinstance(access, list):
        raise CommonStockDataError("COMMON_STOCK_BENCHMARK_ACCESS_INVALID")
    matches = [item for item in access if item.get("provider") == "yahoo"]
    if len(matches) != 1:
        raise CommonStockDataError("COMMON_STOCK_BENCHMARK_YAHOO_POLICY_MISSING")
    policy = matches[0]
    validate_contract("source-access", policy)
    require_source_admission(policy, at=now())
    cache = SnapshotCache(cache_root)
    if session_factory is None:
        from product.mcp.live.yahoo_transport import create_yahoo_session
        session_factory = create_yahoo_session
    session = session_factory(
        policy,
        tickers=[benchmark_ticker],
        state_dir=state_dir,
        cache=cache,
    )
    market_collector = market_collector or collect_daily
    started = now()
    try:
        result = market_collector(
            [{"security_id": benchmark_id, "ticker": benchmark_ticker, "currency": "USD"}],
            start=(started.date() - timedelta(days=365)).isoformat(),
            end=(started.date() + timedelta(days=1)).isoformat(),
            source_access=policy,
            cache=cache,
            calendar=calendar,
            retrieved_at=now,
            max_age_seconds=86400,
            session=session,
        )
        evidence: list[dict[str, Any]] = []
        records = []
        for record in result.get("records", {}).values():
            normalized = normalize_cached_research_series(
                record,
                cache.read(record),
                security_id=benchmark_id,
                ticker=benchmark_ticker,
                currency="USD",
                calendar=calendar,
            )
            evidence.extend(normalized["evidence"])
            records.append({
                "record_hash": record["record_hash"],
                "raw_content_hash": record["raw_content_hash"],
                "retrieved_at": record["retrieved_at"],
            })
        snapshot = {
            "schema_version": "benchmark-research-snapshot/1.0.0",
            "status": "FROZEN" if evidence else "SOURCE_LIMITED",
            "benchmark_id": benchmark_id,
            "benchmark_ticker": benchmark_ticker,
            "evidence": sorted(evidence, key=lambda item: item["evidence_id"]),
            "gaps": list(result.get("gaps", [])),
            "records": sorted(records, key=lambda item: item["record_hash"]),
            "retrieved_at": iso_utc(now()),
        }
        snapshot["snapshot_hash"] = canonical_hash(snapshot)
        Path(output_path).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return snapshot
    finally:
        session.close()


def merge_benchmark_research_evidence(
    prepared: Mapping[str, Any], *, benchmark: Mapping[str, Any],
) -> dict[str, Any]:
    """把独立冻结的基准 Evidence 合入同一 Gate，保持 PIT 与引用闭合。"""

    result = copy.deepcopy(dict(prepared))
    gate = result.get("gate")
    preparation = result.get("preparation")
    if not isinstance(gate, dict) or not isinstance(preparation, dict):
        raise CommonStockDataError("COMMON_STOCK_BENCHMARK_PREPARATION_INVALID")
    benchmark_id = benchmark.get("benchmark_id")
    facts = benchmark.get("evidence")
    if not isinstance(benchmark_id, str) or not isinstance(facts, list):
        raise CommonStockDataError("COMMON_STOCK_BENCHMARK_SNAPSHOT_INVALID")
    existing_ids = set(gate.get("input_evidence_ids", []))
    cutoff = parse_timestamp(gate["decision_cutoff"])
    for fact in facts:
        if not isinstance(fact, Mapping) or fact.get("security_id") != benchmark_id:
            raise CommonStockDataError("COMMON_STOCK_BENCHMARK_FACT_SCOPE_INVALID")
        for key in ("evidence_id", "source_id", "as_of", "retrieved_at"):
            if not isinstance(fact.get(key), str) or not fact[key]:
                raise CommonStockDataError(f"COMMON_STOCK_BENCHMARK_PROVENANCE_MISSING:{key}")
        evidence_id = fact["evidence_id"]
        if evidence_id in existing_ids:
            raise CommonStockDataError("COMMON_STOCK_BENCHMARK_EVIDENCE_DUPLICATE")
        existing_ids.add(evidence_id)
        cutoff = max(cutoff, parse_timestamp(fact["retrieved_at"]))
    allowed = list(gate.get("allowed_evidence", []))
    excluded = list(gate.get("excluded", []))
    for original in facts:
        fact = copy.deepcopy(dict(original))
        published = fact.get("published_at")
        timestamps = [parse_timestamp(fact["as_of"]), parse_timestamp(fact["retrieved_at"])]
        if isinstance(published, str):
            timestamps.append(parse_timestamp(published))
        if any(item > cutoff for item in timestamps):
            excluded.append({
                "evidence_id": fact["evidence_id"],
                "reason_codes": ["FUTURE_BENCHMARK_INFORMATION"],
                "as_of": fact["as_of"],
                "retrieved_at": fact["retrieved_at"],
                **({"published_at": published} if isinstance(published, str) else {}),
            })
        else:
            allowed.append(fact)
    gate.update({
        "decision_cutoff": cutoff.isoformat().replace("+00:00", "Z"),
        "input_evidence_ids": sorted(existing_ids),
        "allowed_evidence": sorted(allowed, key=lambda item: item["evidence_id"]),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in allowed),
        "excluded": sorted(excluded, key=lambda item: item["evidence_id"]),
        "excluded_evidence_ids": sorted(item["evidence_id"] for item in excluded),
    })
    gate["bundle_hash"] = canonical_hash({
        key: value for key, value in gate.items() if key != "bundle_hash"
    })
    preparation.update({
        "common_cutoff": gate["decision_cutoff"],
        "benchmark": {
            "benchmark_id": benchmark_id,
            "status": benchmark.get("status"),
            "snapshot_hash": benchmark.get("snapshot_hash"),
            "evidence_ids": sorted(item["evidence_id"] for item in facts),
            "gaps": copy.deepcopy(list(benchmark.get("gaps", []))),
        },
    })
    preparation["preparation_hash"] = canonical_hash({
        key: value for key, value in preparation.items() if key != "preparation_hash"
    })
    return result


def merge_macro_research_evidence(
    prepared: Mapping[str, Any], *, macro: Mapping[str, Any],
) -> dict[str, Any]:
    """把已由官方采集器执行 PIT 的共享宏观事实合入同一研究 Gate。"""

    result = copy.deepcopy(dict(prepared))
    gate = result.get("gate")
    preparation = result.get("preparation")
    if not isinstance(gate, dict) or not isinstance(preparation, dict):
        raise CommonStockDataError("COMMON_STOCK_MACRO_PREPARATION_INVALID")
    facts = macro.get("evidence")
    snapshot_cutoff = macro.get("decision_cutoff")
    if not isinstance(facts, list) or not isinstance(snapshot_cutoff, str):
        raise CommonStockDataError("COMMON_STOCK_MACRO_SNAPSHOT_INVALID")
    cutoff = max(parse_timestamp(gate["decision_cutoff"]), parse_timestamp(snapshot_cutoff))
    existing_ids = set(gate.get("input_evidence_ids", []))
    allowed = list(gate.get("allowed_evidence", []))
    for fact in facts:
        if not isinstance(fact, Mapping) or fact.get("security_id") != "US:MARKET":
            raise CommonStockDataError("COMMON_STOCK_MACRO_FACT_SCOPE_INVALID")
        for key in ("evidence_id", "source_id", "as_of", "published_at", "retrieved_at"):
            if not isinstance(fact.get(key), str) or not fact[key]:
                raise CommonStockDataError(f"COMMON_STOCK_MACRO_PROVENANCE_MISSING:{key}")
        if max(
            parse_timestamp(fact["as_of"]), parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
        ) > parse_timestamp(snapshot_cutoff):
            raise CommonStockDataError("COMMON_STOCK_MACRO_PIT_INVALID")
        if fact["evidence_id"] in existing_ids:
            raise CommonStockDataError("COMMON_STOCK_MACRO_EVIDENCE_DUPLICATE")
        existing_ids.add(fact["evidence_id"])
        allowed.append(copy.deepcopy(dict(fact)))
    gate.update({
        "decision_cutoff": iso_utc(cutoff),
        "input_evidence_ids": sorted(existing_ids),
        "allowed_evidence": sorted(allowed, key=lambda item: item["evidence_id"]),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in allowed),
    })
    gate["bundle_hash"] = canonical_hash({
        key: value for key, value in gate.items() if key != "bundle_hash"
    })
    preparation.update({
        "common_cutoff": gate["decision_cutoff"],
        "official_macro": {
            "status": macro.get("status"),
            "snapshot_hash": macro.get("snapshot_hash"),
            "policy_hash": macro.get("policy_hash"),
            "evidence_ids": sorted(item["evidence_id"] for item in facts),
            "excluded": copy.deepcopy(list(macro.get("excluded", []))),
            "gaps": copy.deepcopy(list(macro.get("gaps", []))),
        },
    })
    preparation["preparation_hash"] = canonical_hash({
        key: value for key, value in preparation.items() if key != "preparation_hash"
    })
    return result


def merge_option_research_evidence(
    prepared: Mapping[str, Any], *, options: Mapping[str, Any],
) -> dict[str, Any]:
    """合入普通股相关期权快照；只接受采集器已完成 PIT 的证券事实。"""

    result = copy.deepcopy(dict(prepared))
    gate = result.get("gate")
    preparation = result.get("preparation")
    if not isinstance(gate, dict) or not isinstance(preparation, dict):
        raise CommonStockDataError("COMMON_STOCK_OPTIONS_PREPARATION_INVALID")
    facts = options.get("evidence")
    security_ids = set(options.get("security_ids", []))
    snapshot_cutoff = options.get("decision_cutoff")
    if not isinstance(facts, list) or not isinstance(snapshot_cutoff, str):
        raise CommonStockDataError("COMMON_STOCK_OPTIONS_SNAPSHOT_INVALID")
    cutoff = max(parse_timestamp(gate["decision_cutoff"]), parse_timestamp(snapshot_cutoff))
    existing_ids = set(gate.get("input_evidence_ids", []))
    allowed = list(gate.get("allowed_evidence", []))
    for fact in facts:
        if not isinstance(fact, Mapping) or fact.get("security_id") not in security_ids:
            raise CommonStockDataError("COMMON_STOCK_OPTIONS_FACT_SCOPE_INVALID")
        if fact.get("source_type") != "options" or fact.get("kind") != "market_structure":
            raise CommonStockDataError("COMMON_STOCK_OPTIONS_FACT_TYPE_INVALID")
        if max(
            parse_timestamp(fact["as_of"]), parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
        ) > parse_timestamp(snapshot_cutoff):
            raise CommonStockDataError("COMMON_STOCK_OPTIONS_PIT_INVALID")
        if fact["evidence_id"] in existing_ids:
            raise CommonStockDataError("COMMON_STOCK_OPTIONS_EVIDENCE_DUPLICATE")
        existing_ids.add(fact["evidence_id"])
        allowed.append(copy.deepcopy(dict(fact)))
    gate.update({
        "decision_cutoff": iso_utc(cutoff),
        "input_evidence_ids": sorted(existing_ids),
        "allowed_evidence": sorted(allowed, key=lambda item: item["evidence_id"]),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in allowed),
    })
    gate["bundle_hash"] = canonical_hash({
        key: value for key, value in gate.items() if key != "bundle_hash"
    })
    preparation.update({
        "common_cutoff": gate["decision_cutoff"],
        "options": {
            "status": options.get("status"),
            "snapshot_hash": options.get("snapshot_hash"),
            "adapter_version": options.get("adapter_version"),
            "evidence_ids": sorted(item["evidence_id"] for item in facts),
            "excluded_evidence_ids": copy.deepcopy(list(options.get("excluded_evidence_ids", []))),
            "gaps": copy.deepcopy(list(options.get("gaps", []))),
        },
    })
    preparation["preparation_hash"] = canonical_hash({
        key: value for key, value in preparation.items() if key != "preparation_hash"
    })
    return result


def assemble_common_stock_evidence(
    handoff: Mapping[str, Any], *, run_id: str,
    collect_security: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    validate_shared_configuration: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """按证券调用既有数据层并冻结共同 Gate；单项失败不删除持仓。"""

    validate_handoff(handoff)
    if validate_shared_configuration is not None:
        try:
            validate_shared_configuration()
        except Exception as exc:
            raise CommonStockDataError("COMMON_STOCK_SHARED_CONFIGURATION_INVALID") from exc
    positions = [item for item in handoff["portfolio"]["positions"] if item["asset_type"] == "COMMON_STOCK"]
    rows: list[dict[str, Any]] = []
    successful: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for position in positions:
        row = {
            "security_id": position["security_id"], "status": "FAILED",
            "identity_status": "UNVERIFIED", "decision_cutoff": None,
            "evidence_ids": [], "failure_code": None, "data_gaps": [],
        }
        try:
            result = collect_security(copy.deepcopy(position))
            if not isinstance(result, Mapping):
                raise CommonStockDataError("COMMON_STOCK_COLLECTION_RESULT_INVALID")
            if result.get("security_id") != position["security_id"]:
                raise CommonStockDataError("COMMON_STOCK_COLLECTION_SECURITY_MISMATCH")
            if result.get("identity_status") != "VERIFIED":
                raise CommonStockDataError("COMMON_STOCK_SECURITY_IDENTITY_UNVERIFIED")
            cutoff = result.get("decision_cutoff")
            facts = result.get("facts")
            if not isinstance(cutoff, str) or not isinstance(facts, list):
                raise CommonStockDataError("COMMON_STOCK_COLLECTION_PAYLOAD_INVALID")
            parse_timestamp(cutoff)
            for fact in facts:
                if not isinstance(fact, Mapping) or fact.get("security_id") not in {
                    position["security_id"], "MARKET", "US:MARKET"
                }:
                    raise CommonStockDataError("COMMON_STOCK_COLLECTION_FACT_SCOPE_INVALID")
                for key in ("evidence_id", "source_id", "as_of", "retrieved_at"):
                    if not isinstance(fact.get(key), str) or not fact[key]:
                        raise CommonStockDataError(f"COMMON_STOCK_COLLECTION_PROVENANCE_MISSING:{key}")
                parse_timestamp(fact["as_of"])
                parse_timestamp(fact["retrieved_at"])
                if fact.get("published_at") is not None:
                    parse_timestamp(fact["published_at"])
            row.update({
                "status": "READY" if facts else "INSUFFICIENT_EVIDENCE",
                "identity_status": "VERIFIED", "decision_cutoff": cutoff,
                "evidence_ids": [fact["evidence_id"] for fact in facts],
                "data_gaps": list(result.get("data_gaps", [])),
            })
            successful.append((position, result))
        except Exception as exc:
            code = str(exc).split(":", 1)[0]
            row["failure_code"] = (
                code if code.startswith(("COMMON_STOCK_", "LIVE_"))
                else "COMMON_STOCK_SECURITY_COLLECTION_FAILED"
            )
        rows.append(row)
    cutoffs = [parse_timestamp(result["decision_cutoff"]) for _, result in successful]
    common_cutoff = max(cutoffs).isoformat().replace("+00:00", "Z") if cutoffs else handoff["confirmation"]["confirmed_at"]
    cutoff_time = parse_timestamp(common_cutoff)
    allowed, excluded = [], []
    identifiers = set()
    allowed_by_security: dict[str, list[str]] = {}
    for position, result in successful:
        security_cutoff = parse_timestamp(result["decision_cutoff"])
        for original in result["facts"]:
            fact = copy.deepcopy(dict(original))
            evidence_id = fact["evidence_id"]
            if evidence_id in identifiers:
                raise CommonStockDataError("COMMON_STOCK_EVIDENCE_ID_DUPLICATE")
            identifiers.add(evidence_id)
            reasons = []
            # 批次使用共同 cutoff，但某只证券不得借共同 cutoff 接纳其自身采集完成后才出现的事实。
            if parse_timestamp(fact["as_of"]) > security_cutoff:
                reasons.append("FUTURE_AS_OF")
            if parse_timestamp(fact["retrieved_at"]) > security_cutoff:
                reasons.append("FUTURE_RETRIEVAL")
            if fact.get("published_at") is not None and parse_timestamp(fact["published_at"]) > security_cutoff:
                reasons.append("FUTURE_PUBLICATION")
            if reasons:
                excluded.append({
                    "evidence_id": evidence_id, "reason_codes": reasons,
                    "as_of": fact["as_of"], "retrieved_at": fact["retrieved_at"],
                    **({"published_at": fact["published_at"]} if fact.get("published_at") else {}),
                })
            else:
                allowed.append(fact)
                allowed_by_security.setdefault(position["security_id"], []).append(evidence_id)
    for row in rows:
        if row["status"] in {"READY", "INSUFFICIENT_EVIDENCE"}:
            row["evidence_ids"] = sorted(allowed_by_security.get(row["security_id"], []))
            row["status"] = "READY" if row["evidence_ids"] else "INSUFFICIENT_EVIDENCE"
    allowed.sort(key=lambda item: item["evidence_id"])
    excluded.sort(key=lambda item: item["evidence_id"])
    gate = {
        "schema_version": "common-stock-research-evidence-gate/1.0.0",
        "run_id": run_id, "source_mode": "provider-neutral-read-only",
        "decision_cutoff": common_cutoff,
        "input_evidence_ids": sorted(identifiers),
        "allowed_evidence_ids": [item["evidence_id"] for item in allowed],
        "excluded_evidence_ids": [item["evidence_id"] for item in excluded],
        "allowed_evidence": allowed, "excluded": excluded, "conflicts": [],
    }
    gate["bundle_hash"] = canonical_hash(gate)
    preparation = {
        "schema_version": DATA_PREPARATION_VERSION, "run_id": run_id,
        "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "account_source_as_of": handoff["account_snapshot"]["as_of"],
        "common_cutoff": common_cutoff, "items": rows,
        "provider_requests_completed_before_freeze": True,
        "model_calls": 0, "completed_at": _utc_now(),
    }
    preparation["preparation_hash"] = canonical_hash(preparation)
    return {"gate": gate, "preparation": preparation}


def assemble_common_stock_evidence_from_live_snapshot(
    handoff: Mapping[str, Any], *, live_portfolio: Mapping[str, Any],
    snapshot: Mapping[str, Any], calendar: Any, run_id: str,
) -> dict[str, Any]:
    """复用既有 live 适配器冻结物，不运行完整组合估值。"""

    from product.mcp.live.contracts import validate_contract
    from product.mcp.live.identity import verify_frozen_identity
    from product.mcp.provenance import content_hash
    from product.runtime.evidence_gate import run_live_evidence_gate

    validate_handoff(handoff)
    validate_contract("portfolio", dict(live_portfolio))
    validate_contract("snapshot", dict(snapshot))
    if snapshot.get("portfolio_hash") != content_hash(live_portfolio):
        raise CommonStockDataError("COMMON_STOCK_LIVE_PORTFOLIO_BINDING_INVALID")
    verify_frozen_identity(
        dict(live_portfolio), snapshot.get("identity"), cutoff=snapshot["decision_cutoff"]
    )
    common_ids = {
        item["security_id"] for item in handoff["portfolio"]["positions"]
        if item["asset_type"] == "COMMON_STOCK"
    }
    live_ids = {item["security_id"] for item in live_portfolio["positions"]}
    if common_ids != live_ids:
        raise CommonStockDataError("COMMON_STOCK_LIVE_SECURITY_SET_MISMATCH")
    live_gate = run_live_evidence_gate(snapshot, run_id=run_id, calendar=calendar).artifact
    allowed_by_security: dict[str, list[dict[str, Any]]] = {
        identifier: [] for identifier in common_ids
    }
    for fact in live_gate["allowed_evidence"]:
        security_id = fact.get("security_id")
        if security_id in allowed_by_security:
            allowed_by_security[security_id].append(copy.deepcopy(fact))
    # 多维研究所需的历史序列不受“最近两个交易日的估值价格”新鲜度规则约束，
    # 但仍必须来自冻结 snapshot，并在这里逐项执行 PIT。旧 close_price 风控口径不变。
    research_fields = {
        "open_price", "high_price", "low_price", "historical_close_price",
        "adjusted_close_price", "share_volume", "cash_dividend", "stock_split_ratio",
    }
    cutoff = parse_timestamp(snapshot["decision_cutoff"])
    live_allowed_ids = set(live_gate["allowed_evidence_ids"])
    for fact in snapshot.get("facts", []):
        if fact.get("semantic_field") not in research_fields:
            continue
        security_id = fact.get("security_id")
        if security_id not in allowed_by_security or fact.get("evidence_id") in live_allowed_ids:
            continue
        timestamps = [fact.get("as_of"), fact.get("published_at"), fact.get("retrieved_at")]
        if any(not isinstance(item, str) or parse_timestamp(item) > cutoff for item in timestamps):
            continue
        allowed_by_security[security_id].append(copy.deepcopy(fact))

    def collect(position: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "security_id": position["security_id"],
            "identity_status": "VERIFIED",
            "decision_cutoff": snapshot["decision_cutoff"],
            "facts": allowed_by_security[position["security_id"]],
            "data_gaps": [
                item for item in snapshot.get("gaps", [])
                if position["security_id"] in str(item)
            ],
        }

    result = assemble_common_stock_evidence(
        handoff, run_id=run_id, collect_security=collect
    )
    gate = result["gate"]
    accepted_ids = set(gate["allowed_evidence_ids"])
    remaining_excluded = [
        item for item in live_gate["excluded"]
        if item["evidence_id"] not in accepted_ids
    ]
    gate.update({
        "source_mode": "live-read-only",
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_snapshot_hash": snapshot["snapshot_hash"],
        "input_evidence_ids": list(live_gate["input_evidence_ids"]),
        "excluded_evidence_ids": sorted(item["evidence_id"] for item in remaining_excluded),
        "excluded": copy.deepcopy(remaining_excluded),
        "conflicts": copy.deepcopy(live_gate["conflicts"]),
    })
    gate["bundle_hash"] = canonical_hash({
        key: value for key, value in gate.items() if key != "bundle_hash"
    })
    preparation = result["preparation"]
    preparation.update({
        "source_mode": "live-read-only",
        "source_snapshot_id": snapshot["snapshot_id"],
        "source_snapshot_hash": snapshot["snapshot_hash"],
        "calendar_version": calendar.version,
        "calendar_hash": calendar.content_hash,
    })
    preparation["preparation_hash"] = canonical_hash({
        key: value for key, value in preparation.items() if key != "preparation_hash"
    })
    return {"gate": gate, "preparation": preparation}
