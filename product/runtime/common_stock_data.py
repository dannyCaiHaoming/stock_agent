"""将逐证券只读采集结果冻结为普通股研究 Gate。

采集器仍由现有 Provider/缓存层提供；本模块只负责批次边界、身份绑定、
共同 cutoff、PIT 过滤和单证券失败隔离，不做公司研究或投资判断。
"""

from __future__ import annotations

import copy
from contextlib import ExitStack
import json
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from product.intake.v3 import validate_handoff
from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash
from product.runtime.research_memory import fact_content_hash


DATA_PREPARATION_VERSION = "common-stock-data-preparation/1.0.0"
COLLECTION_PORTFOLIO_VERSION = "live-portfolio/2.0.0"
SOURCE_BUNDLE_VERSION = "common-stock-source-bundle/1.0.0"


class CommonStockDataError(ValueError):
    pass


_COLLECTION_FAILURE_PREFIXES = (
    "COMMON_STOCK_", "LIVE_", "RESEARCH_MEMORY_", "SEC_", "YAHOO_",
    "NASDAQ_", "EASTMONEY_", "MOOMOO_",
)


def _collection_failure_code(error: BaseException) -> str:
    code = str(error).split(":", 1)[0]
    return (
        code
        if code.startswith(_COLLECTION_FAILURE_PREFIXES)
        and re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", code)
        else "COMMON_STOCK_SECURITY_COLLECTION_FAILED"
    )


def _hash_without(value: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: item for key, item in value.items() if key != field})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _merge_persisted_snapshot_facts(
    persisted_facts: list[dict[str, Any]], observed_facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a PIT view without widening the current market selection.

    Memory retains the first canonical payload for a content version while a
    later provider check records another observation.  Prefer the current
    observation when the same version was just seen, so its Evidence ID and raw
    hash remain bound to this run.  Historical research-series facts remain in
    the view, but current ``close_price`` facts are limited to the provider
    selection's bounded request window.
    """

    observed_by_version = {
        fact_content_hash(item): copy.deepcopy(item) for item in observed_facts
    }
    observed_current_prices = {
        version for version, item in observed_by_version.items()
        if item.get("kind") == "price"
        and item.get("semantic_field") == "close_price"
        and item.get("usage") == "current"
    }
    merged: list[dict[str, Any]] = []
    for canonical in persisted_facts:
        version = fact_content_hash(canonical)
        is_current_price = (
            canonical.get("kind") == "price"
            and canonical.get("semantic_field") == "close_price"
            and canonical.get("usage") == "current"
        )
        if is_current_price and version not in observed_current_prices:
            continue
        merged.append(observed_by_version.get(version, copy.deepcopy(canonical)))
    return sorted(merged, key=lambda item: item["evidence_id"])


def _merge_raw_records(
    current: list[dict[str, Any]], prior_bundle: Mapping[str, Any] | None,
    *, required_facts: list[dict[str, Any]], cache_root: Path,
) -> list[dict[str, Any]]:
    """Retain only prior raw metadata needed by facts restored from Memory."""

    records: dict[str, dict[str, Any]] = {}
    required_hashes = {
        item.get("raw_content_hash") for item in required_facts
        if item.get("kind") != "derived"
        and isinstance(item.get("raw_content_hash"), str)
    }
    for item in _readable_prior_raw_records(
        prior_bundle, cache_root=cache_root,
    ):
        if item.get("raw_content_hash") in required_hashes:
            records[item["record_hash"]] = copy.deepcopy(item)
    for item in current:
        record_hash = item.get("record_hash")
        if not isinstance(record_hash, str):
            raise CommonStockDataError("RESEARCH_MEMORY_RAW_RECORD_INVALID")
        existing = records.get(record_hash)
        if existing is not None and existing != item:
            raise CommonStockDataError("RESEARCH_MEMORY_RAW_RECORD_COLLISION")
        records[record_hash] = copy.deepcopy(item)
    return [records[key] for key in sorted(records)]


def _readable_prior_raw_records(
    bundle: Mapping[str, Any] | None, *, cache_root: Path,
) -> list[dict[str, Any]]:
    """Return only individually verified prior records from the same cache."""

    from product.mcp.live.cache import SnapshotCache
    from product.mcp.provenance import content_hash

    if not isinstance(bundle, Mapping) or not isinstance(bundle.get("cache_root"), str):
        return []
    try:
        if Path(bundle["cache_root"]).resolve() != cache_root.resolve():
            return []
    except OSError:
        return []
    snapshot = bundle.get("snapshot")
    if not isinstance(snapshot, Mapping):
        return []
    cache = SnapshotCache(cache_root)
    readable = []
    for raw in snapshot.get("raw_records", []):
        if not isinstance(raw, Mapping):
            continue
        record = dict(raw)
        try:
            if (
                record.get("schema_version") != "live-cache/1.0.0"
                or record.get("record_hash") != content_hash({
                    key: value for key, value in record.items()
                    if key != "record_hash"
                })
                or record.get("key_hash") != content_hash(record.get("key"))
            ):
                continue
            cache.read(record)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        readable.append(record)
    return readable


def _validate_snapshot_cache(
    snapshot: Mapping[str, Any], *, cache_root: Path,
) -> None:
    """Prove that every frozen raw reference still resolves to verified bytes."""

    if snapshot.get("schema_version") not in {
        "live-snapshot/3.0.0", "live-snapshot/4.0.0",
    }:
        # Legacy/synthetic test snapshots predate the raw-evidence contract.
        # Production routed snapshots always use one of the versions above.
        return

    from product.mcp.live.cache import SnapshotCache
    from product.runtime.live_context import validate_raw_records

    cache = SnapshotCache(cache_root)
    records_by_digest: dict[str, list[dict[str, Any]]] = {}
    for raw in snapshot.get("raw_records", []):
        if not isinstance(raw, Mapping):
            raise CommonStockDataError("RESEARCH_MEMORY_RAW_RECORD_INVALID")
        digest = raw.get("raw_content_hash")
        if isinstance(digest, str):
            records_by_digest.setdefault(digest, []).append(dict(raw))

    def read_object(digest: str) -> bytes:
        records = records_by_digest.get(digest, [])
        if not records:
            raise CommonStockDataError("RESEARCH_MEMORY_RAW_EVIDENCE_OBJECT_MISSING")
        return cache.read(records[0])

    try:
        validate_raw_records(dict(snapshot), read_object)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CommonStockDataError(
            f"RESEARCH_MEMORY_RAW_CLOSURE_INVALID:{type(exc).__name__}"
        ) from exc


def _snapshot_bundle_cache_valid(
    bundle: Mapping[str, Any] | None, *, cache_root: Path,
) -> bool:
    """Accept a persisted bundle only with the same cache identity and closure."""

    if not isinstance(bundle, Mapping):
        return False
    recorded_root = bundle.get("cache_root")
    if not isinstance(recorded_root, str):
        return False
    try:
        if Path(recorded_root).resolve() != cache_root.resolve():
            return False
        snapshot = bundle.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return False
        _validate_snapshot_cache(snapshot, cache_root=cache_root)
    except (OSError, ValueError, KeyError, TypeError, CommonStockDataError):
        return False
    return True


def _raw_closure_repair_plan(
    plan: Mapping[str, Any], *, planning_as_of: str,
    market_window: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn an existing checkpoint plan into an explicit bounded repair."""

    repaired = copy.deepcopy(dict(plan))
    repaired["mode"] = "REFRESH"
    repaired["reason"] = "RAW_CLOSURE_REPAIR"
    if market_window is not None and repaired["dataset"] in {
        "live_snapshot", "current_snapshot", "yahoo_daily",
    }:
        repaired["request_range"] = dict(market_window)
    repaired["planning_as_of"] = planning_as_of
    repaired["plan_hash"] = canonical_hash({
        key: value for key, value in repaired.items() if key != "plan_hash"
    })
    return repaired


def _preflight_repaired_raw_closure(
    *, memory: Any, security_id: str, snapshot: Mapping[str, Any],
    prior_bundle: Mapping[str, Any] | None, cache_root: Path,
) -> None:
    """Fail before checkpoint writes if a repair cannot cover retained facts."""

    from product.runtime.research_memory import fact_content_hash, logical_fact_key

    observed_facts = [
        dict(fact) for fact in snapshot.get("facts", [])
        if isinstance(fact, Mapping)
    ]
    observed_by_logical: dict[str, list[dict[str, Any]]] = {}
    for fact in observed_facts:
        observed_by_logical.setdefault(logical_fact_key(fact), []).append(fact)
    observed_versions = {fact_content_hash(fact) for fact in observed_facts}
    existing_observed_versions = memory.existing_version_hashes(observed_facts)
    current_raw_hashes = {
        item.get("raw_content_hash")
        for item in snapshot.get("raw_records", [])
        if isinstance(item, Mapping)
    }
    current_raw_hashes.update(
        record["raw_content_hash"] for record in _readable_prior_raw_records(
            prior_bundle, cache_root=cache_root,
        )
    )
    missing = []
    for fact in memory.current_facts(security_id, snapshot["decision_cutoff"]):
        if fact.get("kind") == "derived":
            continue
        if (
            fact.get("kind") == "price"
            and fact.get("semantic_field") == "close_price"
            and fact.get("usage") == "current"
        ):
            # Current prices outside this run's selected market window are
            # intentionally not retained in the next View.
            continue
        prior_version = fact_content_hash(fact)
        if prior_version in observed_versions:
            continue
        observed_same_logical = observed_by_logical.get(logical_fact_key(fact), [])
        prior_rank = (
            parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
            prior_version,
        )
        if any(
            fact_content_hash(candidate) not in existing_observed_versions
            and (
                parse_timestamp(candidate["published_at"]),
                parse_timestamp(candidate["retrieved_at"]),
                fact_content_hash(candidate),
            ) > prior_rank
            for candidate in observed_same_logical
        ):
            # A genuinely new version observed now will supersede the prior
            # selected version after commit. An already-known older version
            # does not get this exception.
            continue
        if fact.get("raw_content_hash") not in current_raw_hashes:
            missing.append(str(fact.get("evidence_id") or "UNKNOWN"))
    if missing:
        raise CommonStockDataError(
            "RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE:"
            + ",".join(sorted(missing)[:8])
        )


def _structured_snapshot_gaps(
    gaps: Any, *, security_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Decode the frozen snapshot's JSON-string gaps for incremental planning."""

    structured: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for item in gaps if isinstance(gaps, list) else []:
        candidate: Any = item
        if isinstance(item, str):
            try:
                candidate = json.loads(item)
            except json.JSONDecodeError:
                diagnostics.append("SNAPSHOT_GAP_NOT_JSON")
                continue
        if not isinstance(candidate, Mapping):
            diagnostics.append("SNAPSHOT_GAP_NOT_OBJECT")
            continue
        value = dict(candidate)
        if value.get("security_id") not in (None, security_id):
            continue
        structured.append(value)
    return structured, sorted(set(diagnostics))


def _dataset_request_evidence(
    snapshot: Mapping[str, Any], dataset: str,
) -> dict[str, Any]:
    """Map frozen provider/cache events to one logical dataset outcome."""

    events = [
        dict(item) for item in snapshot.get("collection_events", [])
        if isinstance(item, Mapping)
    ]

    def matches(event: Mapping[str, Any]) -> bool:
        locator = str(event.get("url") or event.get("endpoint") or "")
        producer = str(event.get("producer") or "")
        if dataset == "sec_companyfacts":
            return "/api/xbrl/companyfacts/" in locator
        if dataset == "sec_documents":
            return "/Archives/edgar/data/" in locator
        if dataset == "sec_identity":
            return (
                "/files/company_tickers_exchange.json" in locator
                or "/submissions/" in locator
                or producer == "sec-history-parser"
            )
        if dataset == "yahoo_daily":
            return (
                "/v8/finance/chart/" in locator
                or producer == "yahoo-daily-collector"
            )
        if dataset == "current_snapshot":
            return (
                producer == "live-market-routing"
                or "/v8/finance/chart/" in locator
                or "push2his.eastmoney.com" in locator
            )
        return False

    matched = [event for event in events if matches(event)]
    if dataset == "sec_identity" and isinstance(snapshot.get("identity"), Mapping):
        matched.append({"producer": "frozen-sec-identity", "provider": "sec"})
    actual = [
        event for event in matched
        if event.get("request_number") is not None
        and event.get("status") not in {"cache_hit", "stable_cache_hit"}
    ]
    cache_hits = [
        event for event in matched
        if event.get("status") in {"cache_hit", "stable_cache_hit"}
    ]
    logical_keys = {
        str(event.get("url") or event.get("endpoint") or event.get("producer"))
        for event in matched
    }
    metric_events = [
        event for event in matched
        if event.get("producer") == "yahoo-daily-collector"
    ]
    metric_logical = sum(
        int(event["sdk_calls"]) for event in metric_events
        if isinstance(event.get("sdk_calls"), int)
    )
    metric_http = sum(
        int(event["actual_http_requests"]) for event in metric_events
        if isinstance(event.get("actual_http_requests"), int)
    )
    providers = set()
    for event in matched:
        url = str(event.get("url", ""))
        if url.startswith(("https://data.sec.gov", "https://www.sec.gov")):
            providers.add("sec")
        elif event.get("provider"):
            providers.add(str(event["provider"]))
    if dataset == "current_snapshot":
        providers.update(
            str(selection["selected_provider"])
            for selection in snapshot.get("source_selections", [])
            if isinstance(selection, Mapping)
            and isinstance(selection.get("selected_provider"), str)
        )
    route_logical = sum(
        1 for event in matched
        if event.get("producer") == "live-market-routing"
    )
    logical_count = (
        route_logical if dataset == "current_snapshot" and route_logical
        else metric_logical or len(logical_keys)
    )
    actual_count = metric_http or len(actual)
    return {
        "attempted": bool(matched),
        "logical_request_count": logical_count,
        "actual_http_requests": actual_count,
        "cache_hit_count": len(cache_hits),
        "retry_count": max(
            0,
            actual_count - logical_count,
        ),
        "actual_providers": sorted(providers),
    }


def _yahoo_pending_from_gaps(
    gaps: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Only completed-session data gaps become retry ranges."""

    return [
        {
            "start": str(gap["date"]),
            "end": str(gap["date"]),
            "reason": str(gap.get("reason", "UNKNOWN")),
        }
        for gap in gaps
        if isinstance(gap.get("date"), str)
        and gap.get("reason") != "NOT_COMPLETED_REGULAR_SESSION"
    ]


def _failed_dataset_statuses(
    plans: Mapping[str, Mapping[str, Any]], *, snapshot_dir: Path,
    failure_code: str,
) -> dict[str, str]:
    """Map a failed production collection stage without inventing attempts.

    A source-boundary failure affects the aggregate snapshot and only the
    datasets owned by that stage. Datasets whose boundary was never reached are
    recorded as ``NOT_ATTEMPTED``. Contract/freeze failures are validation
    failures, not source limitations.
    """

    if failure_code == "RESEARCH_MEMORY_DATASET_LOCK_TIMEOUT":
        return {dataset: "LOCK_TIMEOUT" for dataset in plans}
    error_path = snapshot_dir / "collection-error.json"
    error: Mapping[str, Any] | None = None
    if error_path.is_file():
        try:
            candidate = json.loads(error_path.read_text(encoding="utf-8"))
            if isinstance(candidate, Mapping) and candidate.get("failure_code") == failure_code:
                error = candidate
        except (OSError, json.JSONDecodeError):
            error = None
    if error is None:
        return {dataset: "FAILED_VALIDATION" for dataset in plans}

    stage = str(error.get("failed_stage", ""))
    stage_datasets = {
        "NASDAQ_UNIVERSE": set(),
        "SEC_MAPPING": {"sec_identity"},
        "YAHOO_COLLECTION": {"yahoo_daily", "current_snapshot"},
        "SEC_COMPANY_COLLECTION": {"sec_companyfacts", "sec_documents"},
        "SEC_YAHOO_IDENTITY_BINDING": {"sec_identity", "current_snapshot"},
    }
    affected = set(stage_datasets.get(stage, ())) | {"live_snapshot"}
    source_boundary_failure = stage in stage_datasets and any(
        marker in failure_code
        for marker in (
            "TRANSPORT", "HTTP_", "TIMEOUT", "BUDGET_EXHAUSTED",
            "REQUEST_BUDGET_EXHAUSTED", "NO_COMPLETED_PRICE",
            "NO_FRESH_PRICE", "IDENTITY_AMBIGUOUS_OR_MISSING",
            "IDENTITY_SOURCE_MISSING",
        )
    )
    failed_status = "SOURCE_LIMITED" if source_boundary_failure else "FAILED_VALIDATION"
    return {
        dataset: failed_status if dataset in affected else "NOT_ATTEMPTED"
        for dataset in plans
    }


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
    supplemental_evidence_ids: set[str] = set()
    legacy_supplement = preparation.get("research_supplement")
    if isinstance(legacy_supplement, Mapping):
        supplemental_evidence_ids.update(legacy_supplement.get("evidence_ids", []))
    for supplement in preparation.get("research_supplements", []):
        if isinstance(supplement, Mapping):
            supplemental_evidence_ids.update(supplement.get("evidence_ids", []))
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
            or sorted(
                evidence_id for evidence_id in row.get("evidence_ids", [])
                if evidence_id not in supplemental_evidence_ids
            ) != expected_evidence_ids
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
    if "research_supplement" in preparation:
        def read_supplement(name: str) -> dict[str, Any]:
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_ARTIFACT_MISSING")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping):
                raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_ARTIFACT_INVALID")
            return dict(value)
        expected = merge_research_supplement_evidence(
            expected,
            background=read_supplement("company-background-snapshot.json"),
            package=read_supplement("research-supplement-package.json"),
            batch=read_supplement("research-capture-batch.json"),
            allowed_security_ids={
                item["security_id"] for item in handoff["portfolio"]["positions"]
            },
        )
    plural_supplements = preparation.get("research_supplements", [])
    bundle_supplements = bundle.get("research_supplements", [])
    if plural_supplements != bundle_supplements:
        raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_INDEX_MISMATCH")
    if "research_supplement" in preparation and plural_supplements:
        raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_INDEX_AMBIGUOUS")
    if not isinstance(plural_supplements, list) or len({
        item.get("security_id") for item in plural_supplements if isinstance(item, Mapping)
    }) != len(plural_supplements):
        raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_INDEX_INVALID")
    for record in plural_supplements:
        if not isinstance(record, Mapping):
            raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_INDEX_INVALID")

        def read_supplement_ref(field: str) -> dict[str, Any]:
            ref = record.get(field)
            if not isinstance(ref, str):
                raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_REFERENCE_MISSING")
            path = (root / ref).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_REFERENCE_INVALID")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping):
                raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_ARTIFACT_INVALID")
            return dict(value)

        markdown_ref = record.get("markdown_ref")
        markdown_path = (root / markdown_ref).resolve() if isinstance(markdown_ref, str) else root
        if not isinstance(markdown_ref, str) or not markdown_path.is_relative_to(root) \
                or not markdown_path.is_file():
            raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_REFERENCE_INVALID")
        background = read_supplement_ref("background_ref")
        package = read_supplement_ref("package_ref")
        batch = read_supplement_ref("batch_ref")
        if (
            record.get("security_id") != background.get("security_id")
            or record.get("snapshot_hash") != background.get("snapshot_hash")
            or record.get("package_hash") != package.get("package_hash")
            or record.get("batch_id") != batch.get("batch_id")
        ):
            raise CommonStockDataError("COMMON_STOCK_RESEARCH_SUPPLEMENT_BINDING_INVALID")
        expected = merge_research_supplement_evidence(
            expected, background=background, package=package, batch=batch,
            allowed_security_ids={
                item["security_id"] for item in handoff["portfolio"]["positions"]
            },
            artifact_refs={
                field: str(record[field]) for field in (
                    "background_ref", "package_ref", "batch_ref", "markdown_ref"
                )
            },
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
    handoff_path: Path, *, access_path: Path, output_dir: Path, cache_root: Path | None,
    sec_user_agent: str, run_id: str, benchmark_id: str | None = None,
    benchmark_ticker: str | None = None, collect_research_supplements: bool = False,
    repository_root: Path | None = None, memory_root: Path | None = None,
    collection_options: Mapping[str, Any] | None = None,
    planning_now: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """通过现有只读适配器自动生成 Gate；不启动模型或完整组合估值。"""

    from product.mcp.live.collection import (
        collect_live_snapshot,
        validate_live_collection_configuration,
    )
    from product.mcp.live.contracts import external_path, validate_contract
    from product.mcp.live.market import load_locked_calendar
    from product.mcp.provenance import content_hash
    from product.runtime.research_memory import (
        ResearchMemory, infer_dataset, resolve_memory_root,
    )
    from product.runtime.live_input import freeze_snapshot

    handoff_file = external_path(handoff_path)
    handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
    collection_portfolio = build_common_stock_collection_portfolio(handoff)
    validate_contract("portfolio", collection_portfolio)
    access_file = external_path(access_path)
    clock = planning_now or (lambda: datetime.now(timezone.utc))
    validation_time = clock()
    access = validate_live_collection_configuration(access_file, at=validation_time)
    repository = Path(repository_root or Path(__file__).resolve().parents[2]).resolve()
    resolved_memory_root = resolve_memory_root(repository, memory_root)
    memory = ResearchMemory(resolved_memory_root)
    # Automatic live collection always shares the stable raw cache with the
    # Research Memory unless a caller explicitly supplies that same location.
    cache_root = Path(cache_root or (resolved_memory_root / "raw-cache")).resolve()
    destination = external_path(output_dir)
    if destination.exists():
        raise CommonStockDataError("COMMON_STOCK_DATA_OUTPUT_EXISTS")
    destination.mkdir(parents=True, mode=0o700)
    collection_input_path = destination / "collection-input.json"
    collection_input_path.write_text(
        json.dumps(collection_portfolio, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    external_research_results: dict[str, list[dict[str, Any]]] = {}
    company_profile_plans: dict[str, dict[str, Any]] = {}
    company_profile_outcomes: dict[str, dict[str, Any]] = {}
    collected_results: dict[str, Mapping[str, Any]] = {}
    source_items: list[dict[str, Any]] = []
    memory_results: list[dict[str, Any]] = []
    successful_snapshots: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    source_root = destination / "source-snapshots"
    source_root.mkdir(mode=0o700)

    def failed_source_item(
        *, security_id: str, scoped_input: Path, scoped_portfolio: Mapping[str, Any],
        snapshot_dir: Path, failure_code: str, diagnostic: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        error_path = snapshot_dir / "collection-error.json"
        if diagnostic is not None:
            snapshot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            error_path = snapshot_dir / "persistence-error.json"
            error_path.write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        error_ref = (
            str(error_path.relative_to(destination)) if error_path.is_file() else None
        )
        error_value = (
            json.loads(error_path.read_text(encoding="utf-8")) if error_ref else None
        )
        return {
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
            "failure_code": failure_code,
            "collection_error_ref": error_ref,
            "collection_error_hash": content_hash(error_value) if error_value else None,
        }

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
        plans: dict[str, dict[str, Any]] = {}
        try:
            planning_as_of = iso_utc(clock())
            dataset_specs = (
                ("live", "live_snapshot"), ("public", "company_profile"),
                ("sec", "sec_companyfacts"), ("sec", "sec_documents"),
                ("sec", "sec_identity"), ("market", "current_snapshot"),
                ("yahoo", "yahoo_daily"),
            )
            # Acquire every affected dataset lock in a stable order, then plan
            # again under those locks. This keeps independent securities
            # concurrent while preventing duplicate refreshes for any one
            # dataset and avoiding cross-process lock-order deadlocks.
            with ExitStack() as dataset_locks:
                for provider, dataset in dataset_specs:
                    dataset_locks.enter_context(
                        memory.dataset_lock(security_id, provider, dataset)
                    )
                for provider, dataset in dataset_specs:
                    plans[dataset] = memory.plan(
                        security_id, provider, dataset, planning_as_of=planning_as_of,
                    )
                if collect_research_supplements:
                    from product.mcp.live.research_supplement_collection import (
                        capture_external_research_results,
                    )

                    profile_plan = plans["company_profile"]
                    profile_checkpoint = memory.checkpoint(
                        security_id, "public", "company_profile",
                    )
                    if profile_plan["mode"] == "SKIP_FRESH" and profile_checkpoint:
                        try:
                            state = profile_checkpoint.get("state", {})
                            raw = memory.read_object(
                                str(state.get("object_ref")),
                                str(state.get("object_hash")),
                            )
                            persisted = json.loads(raw)
                            required = {
                                "schema_version", "security_id", "ticker", "results",
                            }
                            if set(persisted) != required \
                                    or persisted["schema_version"] \
                                    != "research-supplement-external-results/1.0.0" \
                                    or persisted["security_id"] != security_id \
                                    or persisted["ticker"] != position["ticker"] \
                                    or not isinstance(persisted["results"], list) \
                                    or any(
                                        not isinstance(item, Mapping)
                                        for item in persisted["results"]
                                    ):
                                raise ValueError("RESEARCH_SUPPLEMENT_MEMORY_BINDING_INVALID")
                            external_research_results[security_id] = [
                                dict(item) for item in persisted["results"]
                            ]
                        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                            profile_plan = _raw_closure_repair_plan(
                                profile_plan, planning_as_of=planning_as_of,
                            )
                            plans["company_profile"] = profile_plan
                    if profile_plan["mode"] != "SKIP_FRESH" \
                            or security_id not in external_research_results:
                        captured = capture_external_research_results(
                            [position], access=access, cache_root=cache_root,
                            state_root=(
                                destination / "research-supplement-capture"
                                / _safe_security_component(security_id)
                            ),
                        )
                        external_research_results[security_id] = list(
                            captured.get(security_id, [])
                        )
                        completed_at = iso_utc(clock())
                        stored = memory.store_object({
                            "schema_version": "research-supplement-external-results/1.0.0",
                            "security_id": security_id,
                            "ticker": position["ticker"],
                            "results": external_research_results[security_id],
                        })
                        status = (
                            "FETCHED_BOOTSTRAP" if profile_plan["mode"] == "BOOTSTRAP"
                            else "CHECKED_NO_CHANGE" if profile_checkpoint
                            and profile_checkpoint.get("state", {}).get("object_hash")
                            == stored["object_hash"]
                            else "FETCHED_INCREMENTAL"
                        )
                        profile_outcome = memory.ingest_dataset(
                            plan=profile_plan, facts=[], status=status,
                            completed_at=completed_at, watermark=completed_at,
                            details={
                                "request_count": 1, "repair_request_count": 0,
                                "source_result": "SUPPLEMENT_BATCH_CAPTURED",
                                "supplement_object_hash": stored["object_hash"],
                            },
                            state=stored,
                        )
                    else:
                        attempt_id = memory.record_attempt_only(
                            plan=profile_plan, status="SKIPPED_FRESH",
                            completed_at=iso_utc(clock()),
                            details={
                                "request_count": 0, "repair_request_count": 0,
                                "source_result": "PERSISTED_SUPPLEMENT_REUSED",
                            },
                        )
                        profile_outcome = {
                            "attempt_id": attempt_id, "status": "SKIPPED_FRESH",
                            "inserted_versions": 0, "observations": 0,
                            "request_range": dict(profile_plan["request_range"]),
                            "request_count": 0, "repair_request_count": 0,
                            "pending_count": len(profile_checkpoint.get("pending", [])),
                            "checkpoint_revision_before": profile_plan["checkpoint_revision"],
                            "checkpoint_revision": profile_plan["checkpoint_revision"],
                        }
                    company_profile_plans[security_id] = profile_plan
                    company_profile_outcomes[security_id] = profile_outcome
                snapshot_plan = plans["live_snapshot"]
                snapshot_checkpoint = memory.checkpoint(
                    security_id, "live", "live_snapshot",
                )
                prior_bundle = None
                prior_bundle_valid = False
                if snapshot_checkpoint is not None:
                    try:
                        prior_bundle = memory.load_snapshot_bundle(snapshot_checkpoint)
                        prior_bundle_valid = _snapshot_bundle_cache_valid(
                            prior_bundle, cache_root=cache_root,
                        )
                    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                        prior_bundle = None
                        prior_bundle_valid = False
                raw_closure_repair_required = bool(
                    snapshot_checkpoint is not None and not prior_bundle_valid
                )
                if raw_closure_repair_required:
                    policy = plans["yahoo_daily"]["policy"]
                    market_window = {
                        "start": (
                            parse_timestamp(planning_as_of).date()
                            - timedelta(days=int(policy["bootstrap_days"]))
                        ).isoformat(),
                        "end": (
                            parse_timestamp(planning_as_of).date()
                            + timedelta(days=1)
                        ).isoformat(),
                    }
                    plans = {
                        dataset: (
                            plan if dataset == "company_profile"
                            else _raw_closure_repair_plan(
                                plan, planning_as_of=planning_as_of,
                                market_window=market_window,
                            )
                        )
                        for dataset, plan in plans.items()
                    }
                    snapshot_plan = plans["live_snapshot"]
                reused_bundle = None
                dataset_outcomes = {}
                if (
                    snapshot_plan["mode"] == "SKIP_FRESH"
                    and all(
                        plan["mode"] == "SKIP_FRESH"
                        for dataset, plan in plans.items()
                        if dataset != "company_profile"
                    )
                    and snapshot_checkpoint is not None
                ):
                    try:
                        if (
                            prior_bundle_valid
                            and prior_bundle is not None
                            and prior_bundle["portfolio"] == scoped_portfolio
                            and canonical_hash(prior_bundle["snapshot"]["source_access"])
                            == canonical_hash(access)
                        ):
                            reused_bundle = prior_bundle
                    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                        reused_bundle = None
                if reused_bundle is not None:
                    snapshot_dir.mkdir(mode=0o700)
                    reused_snapshot = copy.deepcopy(reused_bundle["snapshot"])
                    if reused_snapshot.get("schema_version") in {
                        "live-snapshot/1.0.0", "live-snapshot/2.0.0",
                        "live-snapshot/3.0.0", "live-snapshot/4.0.0",
                    }:
                        reused_snapshot = freeze_snapshot(
                            snapshot_id=f"live-snapshot:{run_id}:{security_id}",
                            portfolio=reused_bundle["portfolio"],
                            request_started_at=reused_snapshot["request_started_at"],
                            decision_cutoff=iso_utc(clock()),
                            facts=reused_snapshot["facts"],
                            source_access=reused_snapshot["source_access"],
                            raw_records=reused_snapshot["raw_records"],
                            collection_events=reused_snapshot["collection_events"],
                            gaps=reused_snapshot["gaps"],
                            identity=reused_snapshot.get("identity"),
                            universe=reused_snapshot.get("universe"),
                            source_selections=reused_snapshot.get("source_selections"),
                        )
                    for name, value in (
                        ("portfolio.json", reused_bundle["portfolio"]),
                        ("snapshot.json", reused_snapshot),
                        ("calendar.json", reused_bundle["calendar"]),
                    ):
                        (snapshot_dir / name).write_text(
                            json.dumps(value, ensure_ascii=False, sort_keys=True),
                            encoding="utf-8",
                        )
                    collected = {
                        "status": "FROZEN", "collection_version": "research-memory-reuse/1.0.0",
                        "snapshot_hash": reused_snapshot["snapshot_hash"],
                        "snapshot_path": str(snapshot_dir / "snapshot.json"),
                        "portfolio_path": str(snapshot_dir / "portfolio.json"),
                        "calendar_lock": str(snapshot_dir / "calendar.json"),
                        "cache_root": str(cache_root),
                    }
                    collection_mode = "CACHE_HIT"
                    completed_at = planning_as_of
                    for dataset, plan in plans.items():
                        if dataset == "company_profile" and collect_research_supplements:
                            continue
                        attempt_status = (
                            "CACHE_HIT" if dataset == "live_snapshot"
                            else "SKIPPED_FRESH" if plan["mode"] == "SKIP_FRESH"
                            else "NOT_ATTEMPTED"
                        )
                        attempt_id = memory.record_attempt_only(
                            plan=plan, status=attempt_status,
                            completed_at=completed_at,
                            details={"request_count": 0, "repair_request_count": 0},
                        )
                        dataset_outcomes[dataset] = {
                            "attempt_id": attempt_id, "status": attempt_status,
                            "inserted_versions": 0, "observations": 0,
                            "request_range": dict(plan["request_range"]),
                            "request_count": 0, "repair_request_count": 0,
                            "pending_count": len(
                                (memory.checkpoint(
                                    plan["security_id"], plan["provider"],
                                    plan["dataset"], plan["scope"],
                                ) or {}).get("pending", [])
                            ),
                            "checkpoint_revision_before": plan["checkpoint_revision"],
                            "checkpoint_revision": plan["checkpoint_revision"],
                        }
                else:
                    yahoo_range = plans["yahoo_daily"]["request_range"]
                    collected = collect_live_snapshot(
                        scoped_input, access_path=access_file, output_dir=snapshot_dir,
                        cache_root=cache_root, sec_user_agent=sec_user_agent,
                        market_start=yahoo_range.get("start"),
                        market_end=yahoo_range.get("end"),
                        **dict(collection_options or {}),
                    )
                    live_portfolio = json.loads(Path(collected["portfolio_path"]).read_text(encoding="utf-8"))
                    snapshot = json.loads(Path(collected["snapshot_path"]).read_text(encoding="utf-8"))
                    calendar_record = json.loads(Path(collected["calendar_lock"]).read_text(encoding="utf-8"))
                    grouped: dict[str, list[dict[str, Any]]] = {}
                    for fact in snapshot["facts"]:
                        grouped.setdefault(infer_dataset(fact), []).append(fact)
                    price_series_repair_pending = False
                    structured_gaps, gap_diagnostics = _structured_snapshot_gaps(
                        snapshot.get("gaps", []), security_id=security_id,
                    )
                    if (
                        raw_closure_repair_required
                        and snapshot.get("schema_version") in {
                            "live-snapshot/3.0.0", "live-snapshot/4.0.0",
                        }
                    ):
                        _preflight_repaired_raw_closure(
                            memory=memory, security_id=security_id,
                            snapshot=snapshot, prior_bundle=prior_bundle,
                            cache_root=cache_root,
                        )
                    for dataset, plan in plans.items():
                        if dataset == "live_snapshot":
                            continue
                        if dataset == "company_profile" and collect_research_supplements:
                            continue
                        facts = grouped.get(dataset, [])
                        request_evidence = _dataset_request_evidence(snapshot, dataset)
                        if not facts and not request_evidence["attempted"]:
                            attempt_id = memory.record_attempt_only(
                                plan=plan, status="NOT_ATTEMPTED",
                                completed_at=snapshot["decision_cutoff"],
                                details={
                                    **request_evidence,
                                    "source_result": "NOT_ATTEMPTED",
                                    "failure_code": (
                                        "COMPANY_PROFILE_SOURCE_NOT_IN_CORE_COLLECTION"
                                        if dataset == "company_profile"
                                        else "DATASET_NOT_ATTEMPTED"
                                    ),
                                },
                            )
                            dataset_outcomes[dataset] = {
                                "attempt_id": attempt_id,
                                "status": "NOT_ATTEMPTED",
                                "inserted_versions": 0,
                                "observations": 0,
                                "request_range": dict(plan["request_range"]),
                                "request_count": 0,
                                "repair_request_count": 0,
                                "pending_count": 0,
                                "checkpoint_revision_before": plan["checkpoint_revision"],
                                "checkpoint_revision": plan["checkpoint_revision"],
                            }
                            continue
                        new_versions = memory.new_version_count(facts)
                        revision_count = memory.revision_count(facts)
                        status = (
                            "FETCHED_BOOTSTRAP" if plan["mode"] == "BOOTSTRAP"
                            else "FETCHED_INCREMENTAL" if new_versions
                            else "CHECKED_NO_CHANGE"
                        )
                        watermark = max(
                            (fact["as_of"] for fact in facts), default=None,
                            key=parse_timestamp,
                        )
                        pending = []
                        if dataset == "yahoo_daily":
                            pending = _yahoo_pending_from_gaps(structured_gaps)
                            prior_checkpoint = memory.checkpoint(
                                security_id, plan["provider"], dataset,
                                plan["scope"],
                            )
                            revision_repair_in_progress = bool(
                                plan["reason"] == "KNOWN_GAP"
                                and prior_checkpoint
                                and any(
                                    item.get("reason") == "PRICE_BASIS_REVISION"
                                    for item in prior_checkpoint.get("pending", [])
                                    if isinstance(item, Mapping)
                                )
                            )
                            if revision_count and not revision_repair_in_progress:
                                repair_start = (
                                    parse_timestamp(planning_as_of).date()
                                    - timedelta(days=int(plan["policy"]["bootstrap_days"]))
                                ).isoformat()
                                pending.append({
                                    "start": repair_start,
                                    "end": plan["request_range"].get("end"),
                                    "reason": "PRICE_BASIS_REVISION",
                                })
                            elif revision_repair_in_progress and pending:
                                pending.append({
                                    "start": plan["request_range"].get("start"),
                                    "end": plan["request_range"].get("end"),
                                    "reason": "PRICE_BASIS_REVISION",
                                })
                            price_series_repair_pending = any(
                                item.get("reason") == "PRICE_BASIS_REVISION"
                                for item in pending
                            )
                        dataset_outcomes[dataset] = memory.ingest_dataset(
                            plan=plan, facts=facts, status=status,
                            completed_at=snapshot["decision_cutoff"], watermark=watermark,
                            coverage=([{"start": plan["request_range"].get("start"),
                                       "end": plan["request_range"].get("end")}]
                                      if plan["request_range"].get("start") else []),
                            pending=pending,
                            details={
                                **request_evidence,
                                "source_result": (
                                    "CHECKED" if request_evidence["attempted"] or facts
                                    else "EMPTY_WITHOUT_EVENT"
                                ),
                                "new_versions": new_versions,
                                "revision_count": revision_count,
                                "observed_facts": len(facts),
                                "request_count": request_evidence["logical_request_count"],
                                "repair_request_count": (
                                    min(
                                        int(plan["policy"].get("repair_budget", 0)),
                                        1 if plan["reason"] == "KNOWN_GAP" else 0,
                                    )
                                ),
                                "gap_diagnostics": gap_diagnostics,
                            },
                        )
                    persisted_facts = memory.current_facts(
                        security_id, snapshot["decision_cutoff"],
                    )
                    persisted_facts = _merge_persisted_snapshot_facts(
                        persisted_facts, snapshot["facts"],
                    )
                    merged_raw_records = _merge_raw_records(
                        snapshot["raw_records"],
                        prior_bundle, required_facts=persisted_facts,
                        cache_root=cache_root,
                    )
                    snapshot_gaps = list(snapshot["gaps"])
                    if price_series_repair_pending:
                        inconsistent_fields = {
                            "open_price", "high_price", "low_price",
                            "historical_close_price", "adjusted_close_price",
                            "share_volume", "cash_dividend",
                            "stock_split_ratio",
                        }
                        persisted_facts = [
                            fact for fact in persisted_facts
                            if fact.get("semantic_field") not in inconsistent_fields
                        ]
                        snapshot_gaps.append(json.dumps({
                            "security_id": security_id,
                            "reason": "YAHOO_PRICE_SERIES_REPAIR_PENDING",
                            "impact": (
                                "价格/公司行动重叠区出现修订；在有界 365 日"
                                "修复完成前不将该序列交给依赖其一致性的派生计算。"
                            ),
                        }, ensure_ascii=False, sort_keys=True))
                    if (
                        persisted_facts != snapshot["facts"]
                        or merged_raw_records != snapshot["raw_records"]
                        or snapshot_gaps != snapshot["gaps"]
                    ):
                        snapshot = freeze_snapshot(
                            snapshot_id=snapshot["snapshot_id"], portfolio=live_portfolio,
                            request_started_at=snapshot["request_started_at"],
                            decision_cutoff=snapshot["decision_cutoff"], facts=persisted_facts,
                            source_access=snapshot["source_access"],
                            raw_records=merged_raw_records,
                            collection_events=snapshot["collection_events"], gaps=snapshot_gaps,
                            identity=snapshot.get("identity"), universe=snapshot.get("universe"),
                            source_selections=snapshot.get("source_selections"),
                        )
                        Path(collected["snapshot_path"]).write_text(
                            json.dumps(snapshot, ensure_ascii=False, sort_keys=True), encoding="utf-8",
                        )
                    _validate_snapshot_cache(snapshot, cache_root=cache_root)
                    stored_bundle = memory.store_snapshot_bundle(
                        security_id=security_id, portfolio=live_portfolio,
                        snapshot=snapshot, calendar=calendar_record,
                        cache_root=cache_root,
                    )
                    live_status = (
                        "FETCHED_BOOTSTRAP" if snapshot_plan["mode"] == "BOOTSTRAP"
                        else "FETCHED_INCREMENTAL" if any(
                            value["inserted_versions"] for value in dataset_outcomes.values()
                        ) else "CHECKED_NO_CHANGE"
                    )
                    live_outcome = memory.ingest_dataset(
                        plan=snapshot_plan, facts=[], status=live_status,
                        completed_at=snapshot["decision_cutoff"],
                        watermark=snapshot["decision_cutoff"],
                        details={
                            "snapshot_hash": snapshot["snapshot_hash"],
                            "request_count": 1, "repair_request_count": 0,
                        },
                        state=stored_bundle,
                    )
                    collection_mode = live_status
                    memory_results.append({
                        "security_id": security_id, "mode": collection_mode,
                        "plans": plans, "dataset_outcomes": dataset_outcomes,
                        "live_outcome": live_outcome,
                    })
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
            if reused_bundle is not None:
                memory_results.append({
                    "security_id": security_id, "mode": collection_mode,
                    "plans": plans, "dataset_outcomes": dataset_outcomes,
                })
        except sqlite3.Error as exc:
            # A transient/security-local write failure is isolated.  If even a
            # fresh quick check cannot use the shared database, continuing would
            # misrepresent every later security, so stop the batch explicitly.
            try:
                with memory.session() as connection:
                    memory.lightweight_check(connection)
            except (OSError, ValueError, sqlite3.Error) as health_error:
                raise CommonStockDataError(
                    "RESEARCH_MEMORY_SHARED_FAILURE"
                ) from health_error
            completed_at = iso_utc(datetime.now(timezone.utc))
            for dataset, plan in plans.items():
                if dataset == "company_profile" and security_id in company_profile_outcomes:
                    continue
                try:
                    memory.record_failed_attempt(
                        plan=plan, status="FAILED_PERSISTENCE",
                        completed_at=completed_at,
                        details={"failure_code": "RESEARCH_MEMORY_PERSISTENCE_FAILED"},
                    )
                except (OSError, ValueError, sqlite3.Error):
                    pass
            source_items.append(failed_source_item(
                security_id=security_id, scoped_input=scoped_input,
                scoped_portfolio=scoped_portfolio, snapshot_dir=snapshot_dir,
                failure_code="RESEARCH_MEMORY_PERSISTENCE_FAILED",
                diagnostic={
                    "status": "FAILED",
                    "failure_code": "RESEARCH_MEMORY_PERSISTENCE_FAILED",
                    "failure_type": type(exc).__name__,
                    "completed_at": completed_at,
                    "llm_calls": 0,
                },
            ))
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            code = _collection_failure_code(exc)
            failure_statuses = _failed_dataset_statuses(
                plans, snapshot_dir=snapshot_dir, failure_code=code,
            )
            error_stage = None
            error_path = snapshot_dir / "collection-error.json"
            if error_path.is_file():
                try:
                    error_stage = json.loads(
                        error_path.read_text(encoding="utf-8")
                    ).get("failed_stage")
                except (OSError, AttributeError, json.JSONDecodeError):
                    error_stage = None
            for dataset, plan in plans.items():
                if dataset == "company_profile" and security_id in company_profile_outcomes:
                    continue
                try:
                    status = failure_statuses[dataset]
                    recorder = (
                        memory.record_attempt_only
                        if status == "NOT_ATTEMPTED"
                        else memory.record_failed_attempt
                    )
                    recorder(
                        plan=plan, status=status,
                        completed_at=iso_utc(datetime.now(timezone.utc)),
                        details={"failure_code": code, "failed_stage": error_stage},
                    )
                except (OSError, ValueError, sqlite3.Error):
                    pass
            source_items.append(failed_source_item(
                security_id=security_id, scoped_input=scoped_input,
                scoped_portfolio=scoped_portfolio, snapshot_dir=snapshot_dir,
                failure_code=code,
            ))

    def collected_security(position: Mapping[str, Any]) -> Mapping[str, Any]:
        result = collected_results.get(position["security_id"])
        if result is None:
            failed = next(item for item in source_items if item["security_id"] == position["security_id"])
            raise CommonStockDataError(str(failed["failure_code"]))
        return result

    prepared = assemble_common_stock_evidence(
        handoff, run_id=run_id, collect_security=collected_security,
    )
    memory_artifact_root = destination / "research-memory"
    memory_artifact_root.mkdir(mode=0o700)
    research_supplement_paths: list[str] = []
    if collect_research_supplements:
        from product.mcp.live.research_supplement import render_company_background_markdown
        from product.mcp.live.research_supplement_collection import build_research_supplements

        supplement_positions = [
            position for position in collection_portfolio["positions"]
            if position["security_id"] in collected_results
        ]
        supplements = build_research_supplements(
            supplement_positions, gate=prepared["gate"],
            external_results=external_research_results, run_id=run_id,
        )
        allowed_security_ids = {item["security_id"] for item in supplement_positions}
        supplement_root = destination / "research-supplements"
        supplement_root.mkdir(mode=0o700)
        for supplement in supplements:
            security_id = supplement["security_id"]
            item_root = supplement_root / _safe_security_component(security_id)
            item_root.mkdir(mode=0o700)
            refs = {
                "background_ref": str((item_root / "company-background-snapshot.json").relative_to(destination)),
                "package_ref": str((item_root / "research-supplement-package.json").relative_to(destination)),
                "batch_ref": str((item_root / "research-capture-batch.json").relative_to(destination)),
                "markdown_ref": str((item_root / "company-background.md").relative_to(destination)),
            }
            for field, value in (
                ("background_ref", supplement["background"]),
                ("package_ref", supplement["package"]),
                ("batch_ref", supplement["batch"]),
            ):
                (destination / refs[field]).write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            (destination / refs["markdown_ref"]).write_text(
                render_company_background_markdown(supplement["background"]),
                encoding="utf-8",
            )
            prepared = merge_research_supplement_evidence(
                prepared, background=supplement["background"],
                package=supplement["package"], batch=supplement["batch"],
                allowed_security_ids=allowed_security_ids, artifact_refs=refs,
            )
            memory_result = next(
                item for item in memory_results if item["security_id"] == security_id
            )
            memory_result["plans"]["company_profile"] = company_profile_plans[security_id]
            memory_result["dataset_outcomes"]["company_profile"] = (
                company_profile_outcomes[security_id]
            )
            research_supplement_paths.append(str(item_root))
    views = []
    for security_id, result in collected_results.items():
        view = memory.save_view(
            run_id=run_id, security_id=security_id,
            decision_cutoff=prepared["gate"]["decision_cutoff"],
            facts=result["facts"],
            gaps=result.get("data_gaps", result.get("gaps", [])),
            conflicts=result["conflicts"],
        )
        views.append(view)
        (memory_artifact_root / f"{_safe_security_component(security_id)}-view.json").write_text(
            json.dumps(view, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    memory_manifest = {
        "schema_version": "company-research-memory-run/1.0.0", "run_id": run_id,
        "memory_root": str(resolved_memory_root), "results": memory_results,
        "view_hashes": sorted(item["view_manifest_hash"] for item in views),
    }
    memory_manifest["manifest_hash"] = canonical_hash(memory_manifest)
    (memory_artifact_root / "manifest.json").write_text(
        json.dumps(memory_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
        "research_supplements": copy.deepcopy(
            prepared["preparation"].get("research_supplements", [])
        ),
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
    all_input_ids.update(gate.get("input_evidence_ids", []))
    accepted_ids = set(gate["allowed_evidence_ids"])
    excluded_by_id = {
        item["evidence_id"]: copy.deepcopy(item)
        for item in gate.get("excluded", [])
    }
    excluded_by_id.update({
        item["evidence_id"]: copy.deepcopy(item)
        for result in collected_results.values() for item in result["excluded"]
        if item["evidence_id"] not in accepted_ids
    })
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
    if research_supplement_paths:
        result["research_supplements"] = research_supplement_paths
    return result


def attach_research_supplement(
    data_dir: Path, *, background_path: Path, package_path: Path, batch_path: Path,
) -> dict[str, Any]:
    """把已冻结补充包接到既有普通股数据目录；不采集网络、不启动模型。"""
    from product.mcp.live.contracts import external_path, validate_contract
    from product.mcp.live.research_supplement import (
        render_company_background_markdown,
        validate_research_supplement_package,
    )

    root = external_path(data_dir)
    gate_path, preparation_path = root / "gate.json", root / "data-preparation.json"
    if not root.is_dir() or not gate_path.is_file() or not preparation_path.is_file():
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_DATA_PACKAGE_INVALID")
    targets = {
        "company-background-snapshot.json": external_path(background_path),
        "research-supplement-package.json": external_path(package_path),
        "research-capture-batch.json": external_path(batch_path),
    }
    if any((root / name).exists() for name in targets):
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_ALREADY_ATTACHED")
    values = {
        name: json.loads(path.read_text(encoding="utf-8")) for name, path in targets.items()
    }
    background = values["company-background-snapshot.json"]
    package = values["research-supplement-package.json"]
    batch = values["research-capture-batch.json"]
    validate_research_supplement_package(package, batch=batch, background=background)
    prepared = {
        "gate": json.loads(gate_path.read_text(encoding="utf-8")),
        "preparation": json.loads(preparation_path.read_text(encoding="utf-8")),
    }
    if "research_supplement" in prepared["preparation"]:
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_ALREADY_ATTACHED")
    collection_input_path = root / "collection-input.json"
    if not collection_input_path.is_file():
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_COLLECTION_INPUT_MISSING")
    collection_input = json.loads(collection_input_path.read_text(encoding="utf-8"))
    validate_contract("portfolio", collection_input)
    allowed_security_ids = {
        item["security_id"] for item in collection_input["positions"]
    }
    merged = merge_research_supplement_evidence(
        prepared, background=background, package=package, batch=batch,
        allowed_security_ids=allowed_security_ids,
    )
    for name, value in values.items():
        (root / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    (root / "company-background.md").write_text(
        render_company_background_markdown(background), encoding="utf-8",
    )
    gate_path.write_text(
        json.dumps(merged["gate"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    preparation_path.write_text(
        json.dumps(merged["preparation"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "ATTACHED", "data_dir": str(root),
        "background_snapshot_hash": background["snapshot_hash"],
        "package_hash": package["package_hash"],
        "gate_hash": merged["gate"]["bundle_hash"],
        "evidence_ids": package["evidence_ids"],
    }


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


def merge_research_supplement_evidence(
    prepared: Mapping[str, Any], *, background: Mapping[str, Any],
    package: Mapping[str, Any] | None = None, batch: Mapping[str, Any] | None = None,
    allowed_security_ids: set[str], artifact_refs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """把三源研究 sidecar 合入同一 Gate，不改变基础四源快照契约。"""

    from product.mcp.live.research_supplement import (
        validate_company_background_snapshot,
        validate_research_supplement_package,
    )

    result = copy.deepcopy(dict(prepared))
    gate = result.get("gate")
    preparation = result.get("preparation")
    if not isinstance(gate, dict) or not isinstance(preparation, dict):
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_PREPARATION_INVALID")
    if not allowed_security_ids or background.get("security_id") not in allowed_security_ids:
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_PORTFOLIO_SCOPE_MISMATCH")
    try:
        validate_company_background_snapshot(background)
    except (KeyError, TypeError, ValueError) as exc:
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_SNAPSHOT_INVALID") from exc
    facts = list(background["evidence"])
    if package is not None:
        if batch is None:
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_BATCH_REQUIRED")
        try:
            validate_research_supplement_package(package, batch=batch, background=background)
        except (KeyError, TypeError, ValueError) as exc:
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_PACKAGE_INVALID") from exc
        facts.extend(package["extra_evidence"])
    snapshot_cutoff = parse_timestamp(background["decision_cutoff"])
    gate_cutoff = parse_timestamp(gate["decision_cutoff"])
    if parse_timestamp(preparation["common_cutoff"]) != gate_cutoff \
            or snapshot_cutoff > gate_cutoff:
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_CUTOFF_MISMATCH")
    existing_ids = set(gate.get("input_evidence_ids", []))
    allowed = list(gate.get("allowed_evidence", []))
    excluded = list(gate.get("excluded", []))
    for original in facts:
        fact = copy.deepcopy(dict(original))
        if fact["evidence_id"] in existing_ids:
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_EVIDENCE_DUPLICATE")
        if fact["security_id"] != background["security_id"]:
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_SECURITY_MISMATCH")
        existing_ids.add(fact["evidence_id"])
        if max(
            parse_timestamp(fact["as_of"]), parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
        ) > snapshot_cutoff:
            excluded.append({
                "evidence_id": fact["evidence_id"],
                "reason_codes": ["FUTURE_RESEARCH_SUPPLEMENT_INFORMATION"],
                "as_of": fact["as_of"],
                "published_at": fact["published_at"],
                "retrieved_at": fact["retrieved_at"],
            })
        else:
            allowed.append(fact)
    excluded_ids = {item["evidence_id"] for item in excluded}
    admitted_fact_ids = {
        fact["evidence_id"] for fact in facts
        if fact["evidence_id"] not in excluded_ids
    }
    gate.update({
        "decision_cutoff": iso_utc(gate_cutoff),
        "input_evidence_ids": sorted(existing_ids),
        "allowed_evidence": sorted(allowed, key=lambda item: item["evidence_id"]),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in allowed),
        "excluded": sorted(excluded, key=lambda item: item["evidence_id"]),
        "excluded_evidence_ids": sorted(item["evidence_id"] for item in excluded),
    })
    gate["bundle_hash"] = canonical_hash({
        key: value for key, value in gate.items() if key != "bundle_hash"
    })
    record = {
        "schema_version": background["schema_version"],
        "snapshot_id": background["snapshot_id"],
        "snapshot_hash": background["snapshot_hash"],
        "package_hash": package.get("package_hash") if package is not None else None,
        "batch_id": background["batch_id"],
        "security_id": background["security_id"],
        "status": background["status"],
        "evidence_ids": sorted(item["evidence_id"] for item in facts),
        "group_statuses": {
            name: group["status"] for name, group in sorted(background["groups"].items())
        },
    }
    preparation["common_cutoff"] = gate["decision_cutoff"]
    matching_rows = [
        item for item in preparation.get("items", [])
        if item.get("security_id") == background["security_id"]
    ]
    if preparation.get("items") is not None and len(matching_rows) != 1:
        raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_PREPARATION_ITEM_MISSING")
    if matching_rows:
        matching_rows[0]["evidence_ids"] = sorted(
            set(matching_rows[0].get("evidence_ids", [])) | admitted_fact_ids
        )
        if matching_rows[0]["evidence_ids"]:
            matching_rows[0]["status"] = "READY"
    if artifact_refs is None:
        preparation["research_supplement"] = record
    else:
        required_refs = {"background_ref", "package_ref", "batch_ref", "markdown_ref"}
        if set(artifact_refs) != required_refs or any(
            not isinstance(value, str) or not value for value in artifact_refs.values()
        ):
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_REFERENCE_INVALID")
        record.update(dict(artifact_refs))
        records = list(preparation.get("research_supplements", []))
        if any(item.get("security_id") == background["security_id"] for item in records):
            raise CommonStockDataError("COMMON_STOCK_SUPPLEMENT_ALREADY_ATTACHED")
        records.append(record)
        preparation["research_supplements"] = sorted(
            records, key=lambda item: item["security_id"]
        )
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
            row["failure_code"] = _collection_failure_code(exc)
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
