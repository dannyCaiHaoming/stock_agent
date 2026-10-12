"""同行及既有采集共用的纯数据校验/合并，不导入研究Stage或模型控制。"""
from __future__ import annotations
import copy
from pathlib import Path
from typing import Any, Mapping

from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash

class CommonStockDataError(ValueError):
    pass


def _validate_snapshot_cache(
    snapshot: Mapping[str, Any], *, cache_root: Path,
) -> None:
    """Prove that every frozen raw reference still resolves to verified bytes."""

    if snapshot.get("schema_version") not in {
        "live-snapshot/3.0.0", "live-snapshot/4.0.0", "live-research-snapshot/1.0.0",
    }:
        # Legacy/synthetic test snapshots predate the raw-evidence contract.
        # Production routed snapshots always use one of the versions above.
        return

    from product.mcp.live.cache import SnapshotCache
    from product.tools.raw_records import validate_raw_records

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


def merge_research_supplement_evidence(
    prepared: Mapping[str, Any], *, background: Mapping[str, Any],
    package: Mapping[str, Any] | None = None, batch: Mapping[str, Any] | None = None,
    allowed_security_ids: set[str], artifact_refs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """把三源研究 sidecar 合入同一 Gate，不改变基础四源快照契约。"""

    from product.mcp.live.research_supplement import (
        SHARED_MARKET_DATASETS,
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
        if fact["security_id"] not in (
            {background["security_id"], "US:MARKET"}
            if fact.get("dataset") in SHARED_MARKET_DATASETS
            else {background["security_id"]}
        ):
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
