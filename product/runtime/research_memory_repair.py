"""Research View 悬空引用的确定性预检与离线修复。

本模块不访问网络、不调用模型，也不推进 checkpoint。默认入口只读；执行
模式保留原 View，并新增一个引用已闭合的修复 View 和确定性 receipt。
"""

from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Mapping

from product.mcp.live.contracts import validate_contract
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash
from product.runtime.research_memory import (
    VIEW_VERSION,
    fact_content_hash,
    validate_research_view,
)


REPAIR_SCHEMA_VERSION = "research-view-reference-repair/1.0.0"


class ResearchMemoryRepairError(ValueError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _database(root: Path) -> Path:
    path = Path(root).expanduser().resolve() / "research-memory.sqlite3"
    if not path.is_file() or path.is_symlink():
        raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_DATABASE_UNAVAILABLE")
    return path


def _verified_snapshots(root: Path, cutoff: str, security_id: str) -> list[dict[str, Any]]:
    objects = Path(root).expanduser().resolve() / "objects"
    if not objects.is_dir() or objects.is_symlink():
        raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_OBJECTS_UNAVAILABLE")
    snapshots: list[dict[str, Any]] = []
    for path in objects.iterdir():
        if path.is_symlink() or not path.is_file() or len(path.name) != 64:
            continue
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != path.name:
                continue
            value = json.loads(raw)
            snapshot = value.get("snapshot") if isinstance(value, Mapping) else None
            if (
                not isinstance(snapshot, Mapping)
                or parse_timestamp(str(snapshot.get("decision_cutoff"))) > parse_timestamp(cutoff)
            ):
                continue
            validate_contract("snapshot", dict(snapshot))
            facts = [
                deepcopy(dict(item)) for item in snapshot.get("facts", [])
                if isinstance(item, Mapping) and item.get("security_id") == security_id
            ]
            if facts:
                snapshots.append({
                    "object_hash": path.name,
                    "freshness_policy_version": snapshot.get("freshness_policy_version"),
                    "facts": facts,
                })
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return snapshots


def inspect_view_references(root: Path, *, security_id: str | None = None) -> dict[str, Any]:
    """Return a read-only, hash-only repair plan for persisted Views."""

    root = Path(root).expanduser().resolve()
    database = _database(root)
    uri = f"file:{database}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=5.0)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        query = "SELECT view_manifest_hash,run_id,security_id,decision_cutoff,payload_json FROM research_views"
        params: tuple[Any, ...] = ()
        if security_id:
            query += " WHERE security_id=?"
            params = (security_id,)
        query += " ORDER BY decision_cutoff,view_manifest_hash"
        view_rows = connection.execute(query, params).fetchall()
        fact_rows = connection.execute(
            "SELECT version_hash,security_id,payload_json FROM fact_versions"
            + (" WHERE security_id=?" if security_id else ""), params,
        ).fetchall()
    persisted: dict[str, dict[str, Any]] = {}
    for row in fact_rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_FACT_INVALID") from exc
        version = str(row["version_hash"])
        if not isinstance(payload, Mapping) or fact_content_hash(payload) != version:
            raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_FACT_HASH_MISMATCH")
        persisted[version] = dict(payload)

    existing_view_hashes = {str(row["view_manifest_hash"]) for row in view_rows}
    plans = []
    for row in view_rows:
        try:
            original = json.loads(row["payload_json"])
            validate_research_view(original)
        except (TypeError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_VIEW_INVALID") from exc
        references = sorted(set(str(item) for item in original.get("selected_fact_versions", [])))
        existing = sorted(item for item in references if item in persisted)
        missing = sorted(set(references) - set(existing))
        mapping: dict[str, str] = {}
        ambiguous: dict[str, list[str]] = {}
        snapshots = _verified_snapshots(root, str(row["decision_cutoff"]), str(row["security_id"])) if missing else []
        candidates: dict[str, set[str]] = {item: set() for item in missing}
        for snapshot in snapshots:
            policy = snapshot.get("freshness_policy_version")
            if not isinstance(policy, str) or not policy:
                continue
            for raw_fact in snapshot["facts"]:
                persisted_hash = fact_content_hash(raw_fact)
                if persisted_hash not in persisted or persisted[persisted_hash] != raw_fact:
                    continue
                delivered = dict(raw_fact, freshness_status="FRESH", freshness_policy_version=policy)
                delivered_hash = fact_content_hash(delivered)
                if delivered_hash in candidates:
                    candidates[delivered_hash].add(persisted_hash)
        for missing_hash, values in candidates.items():
            if len(values) == 1:
                mapping[missing_hash] = next(iter(values))
            elif len(values) > 1:
                ambiguous[missing_hash] = sorted(values)
        unresolved = sorted(set(missing) - set(mapping) - set(ambiguous))
        repaired_versions = sorted(existing + list(mapping.values()))
        new_view = None
        if missing and not unresolved and not ambiguous and len(repaired_versions) == len(references):
            new_view = deepcopy(original)
            new_view["schema_version"] = VIEW_VERSION
            new_view["view_id"] = f'{original["view_id"]}:repair:references-v1'
            new_view["selected_fact_versions"] = repaired_versions
            new_view["view_manifest_hash"] = canonical_hash({
                key: value for key, value in new_view.items() if key != "view_manifest_hash"
            })
            validate_research_view(new_view)
        plans.append({
            "original_view_hash": str(row["view_manifest_hash"]),
            "security_id": str(row["security_id"]),
            "run_id": str(row["run_id"]),
            "decision_cutoff": str(row["decision_cutoff"]),
            "reference_count": len(references), "resolved_count": len(existing),
            "missing_count": len(missing), "ambiguous_count": len(ambiguous),
            "unresolved_count": len(unresolved), "mapping": mapping,
            "ambiguous": ambiguous, "unresolved": unresolved,
            "snapshot_object_hashes": sorted({item["object_hash"] for item in snapshots}),
            "repairable": new_view is not None,
            "already_repaired": bool(new_view and new_view["view_manifest_hash"] in existing_view_hashes),
            "new_view": new_view,
        })
    summary = {
        "schema_version": REPAIR_SCHEMA_VERSION,
        "security_id": security_id,
        "view_count": len(plans),
        "incomplete_view_count": sum(bool(item["missing_count"] or item["ambiguous_count"]) for item in plans),
        "repairable_view_count": sum(bool(item["repairable"]) for item in plans),
        "views": plans,
    }
    summary["plan_hash"] = canonical_hash(summary)
    return summary


def _backup(root: Path, destination: Path) -> None:
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_BACKUP_EXISTS")
    destination.mkdir(parents=True, mode=0o700)
    try:
        with closing(sqlite3.connect(_database(root))) as source, closing(sqlite3.connect(destination / "research-memory.sqlite3")) as target:
            source.backup(target)
        shutil.copytree(Path(root) / "objects", destination / "objects")
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _count_bound_versions(
    connection: sqlite3.Connection, security_id: str, versions: list[str],
) -> int:
    """Count references without depending on a large SQLite variable limit."""

    total = 0
    for start in range(0, len(versions), 500):
        chunk = versions[start:start + 500]
        placeholders = ",".join("?" for _ in chunk)
        total += int(connection.execute(
            f"SELECT COUNT(*) FROM fact_versions WHERE security_id=? AND version_hash IN ({placeholders})",
            [security_id, *chunk],
        ).fetchone()[0])
    return total


def apply_view_reference_repairs(
    root: Path, *, security_id: str, backup_root: Path,
) -> dict[str, Any]:
    """Apply a fully repairable plan after making a recoverable backup."""

    root = Path(root).expanduser().resolve()
    plan = inspect_view_references(root, security_id=security_id)
    pending = [
        item for item in plan["views"]
        if item["missing_count"] and not item.get("already_repaired")
    ]
    if not pending:
        return dict(plan, status="NO_CHANGES")
    if any(not item["repairable"] for item in pending):
        raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_EVIDENCE_INSUFFICIENT")
    _backup(root, backup_root)
    database = _database(root)
    inserted: list[str] = []
    try:
        with closing(sqlite3.connect(database, timeout=5.0)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            for item in pending:
                view = item["new_view"]
                existing = connection.execute(
                    "SELECT payload_json FROM research_views WHERE view_manifest_hash=?",
                    (view["view_manifest_hash"],),
                ).fetchone()
                if existing:
                    if json.loads(existing[0]) != view:
                        raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_VIEW_COLLISION")
                    continue
                count = _count_bound_versions(
                    connection, security_id, view["selected_fact_versions"],
                )
                if int(count) != len(view["selected_fact_versions"]):
                    raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_REFERENCES_CHANGED")
                connection.execute(
                    "INSERT INTO research_views VALUES(?,?,?,?,?)",
                    (view["view_manifest_hash"], view["run_id"], view["security_id"], view["decision_cutoff"], _canonical_json(view)),
                )
                inserted.append(view["view_manifest_hash"])
            connection.commit()
        receipt = {
            "schema_version": REPAIR_SCHEMA_VERSION,
            "security_id": security_id,
            "plan_hash": plan["plan_hash"],
            "repairs": [{
                "original_view_hash": item["original_view_hash"],
                "repaired_view_hash": item["new_view"]["view_manifest_hash"],
                "mapping": item["mapping"],
            } for item in pending],
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        receipts = root / "repairs"
        receipts.mkdir(mode=0o700, exist_ok=True)
        destination = receipts / f'{receipt["receipt_hash"]}.json'
        raw = (_canonical_json(receipt) + "\n").encode("utf-8")
        if destination.exists() and destination.read_bytes() != raw:
            raise ResearchMemoryRepairError("RESEARCH_MEMORY_REPAIR_RECEIPT_COLLISION")
        if not destination.exists():
            descriptor, name = tempfile.mkstemp(prefix=".repair-", dir=receipts)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        return dict(plan, status="REPAIRED", receipt_hash=receipt["receipt_hash"], inserted_view_hashes=inserted)
    except Exception:
        if inserted:
            with closing(sqlite3.connect(database, timeout=5.0)) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.executemany(
                    "DELETE FROM research_views WHERE view_manifest_hash=?",
                    [(item,) for item in inserted],
                )
                connection.commit()
        raise
