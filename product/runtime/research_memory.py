"""跨运行的普通股研究资料与报告持久化。

本模块只做确定性规划、版本化、查询和保存；不形成研究判断，也不
启动模型。SQLite 保存可查询索引，较大的原始对象与报告包使用仓库外
内容寻址对象目录。
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash


MEMORY_SCHEMA_VERSION = 2
PLAN_VERSION = "company-research-incremental-plan/1.0.0"
VIEW_VERSION = "company-research-view/1.0.0"
REPORT_REFERENCE_VERSION = "company-research-report-reference/1.0.0"
POLICY_VERSION = "company-research-dataset-policy/1.0.0"
ATTEMPT_STATUSES = frozenset({
    "SKIPPED_FRESH", "CACHE_HIT", "CHECKED_NO_CHANGE",
    "FETCHED_INCREMENTAL", "FETCHED_BOOTSTRAP", "SOURCE_LIMITED",
    "FAILED_VALIDATION", "FAILED_PERSISTENCE", "LOCK_TIMEOUT",
})
SUCCESSFUL_INGEST_STATUSES = frozenset({
    "CHECKED_NO_CHANGE", "FETCHED_INCREMENTAL", "FETCHED_BOOTSTRAP",
})

DATASET_POLICIES: dict[str, dict[str, Any]] = {
    "live_snapshot": {
        "freshness_seconds": 86400, "request_budget": 1,
        "bootstrap_days": 365, "overlap_sessions": 5,
    },
    "yahoo_daily": {
        "freshness_seconds": 86400, "request_budget": 1,
        "repair_budget": 1, "bootstrap_days": 365, "overlap_sessions": 5,
    },
    "sec_identity": {"freshness_seconds": 86400, "request_budget": 1},
    "sec_companyfacts": {
        "freshness_seconds": 86400, "request_budget": 2,
        "history_pages": 1, "annual_periods": 7, "quarter_periods": 24,
    },
    "sec_documents": {
        "freshness_seconds": 86400, "request_budget": 3,
        "history_pages": 1,
    },
    "current_snapshot": {"freshness_seconds": 86400, "request_budget": 1},
    "company_profile": {"freshness_seconds": 7 * 86400, "request_budget": 1},
}


class ResearchMemoryError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def resolve_memory_root(
    repository_root: Path, explicit: Path | None = None,
    *, environment: Mapping[str, str] | None = None, create: bool = True,
) -> Path:
    """Resolve and validate the stable external memory root.

    Explicit CLI configuration wins over ``RESEARCH_MEMORY_ROOT``.  The path
    must not be inside the source repository and may not be a symlink.
    """

    env = os.environ if environment is None else environment
    candidate = explicit
    if candidate is None:
        configured = env.get("RESEARCH_MEMORY_ROOT")
        candidate = Path(configured) if configured else None
    if candidate is None:
        raise ResearchMemoryError("RESEARCH_MEMORY_ROOT_REQUIRED")
    repository = Path(repository_root).resolve()
    raw = Path(candidate).expanduser()
    if raw.exists() and raw.is_symlink():
        raise ResearchMemoryError("RESEARCH_MEMORY_ROOT_SYMLINK_REJECTED")
    root = raw.resolve()
    if root == repository or repository in root.parents:
        raise ResearchMemoryError("RESEARCH_MEMORY_MUST_BE_EXTERNAL")
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not root.is_dir():
        raise ResearchMemoryError("RESEARCH_MEMORY_ROOT_NOT_DIRECTORY")
    if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
        raise ResearchMemoryError("RESEARCH_MEMORY_ROOT_PERMISSION_DENIED")
    for name in ("objects", "locks", "raw-cache"):
        path = root / name
        if path.exists() and path.is_symlink():
            raise ResearchMemoryError("RESEARCH_MEMORY_PATH_SYMLINK_REJECTED")
        if create:
            path.mkdir(exist_ok=True, mode=0o700)
    return root


def _strip_for_logical_key(value: Any) -> Any:
    volatile = {
        "evidence_id", "value", "retrieved_at", "raw_content_hash",
        "record_hash", "snapshot_hash", "row_locator", "source_locator",
        "publication_retrieved_at", "checked_at", "request_started_at",
        "calendar_hash",
    }
    if isinstance(value, Mapping):
        return {
            str(key): _strip_for_logical_key(child)
            for key, child in value.items() if key not in volatile
        }
    if isinstance(value, list):
        return [_strip_for_logical_key(item) for item in value]
    return value


def _strip_for_content_version(value: Any) -> Any:
    observations = {
        "evidence_id", "retrieved_at", "raw_content_hash", "record_hash",
        "snapshot_hash", "row_locator", "source_locator",
        "publication_retrieved_at", "checked_at", "request_started_at",
        "calendar_hash",
    }
    if isinstance(value, Mapping):
        return {
            str(key): _strip_for_content_version(child)
            for key, child in value.items() if key not in observations
        }
    if isinstance(value, list):
        return [_strip_for_content_version(item) for item in value]
    return value


def logical_fact_key(fact: Mapping[str, Any]) -> str:
    for field in ("security_id", "source_id", "as_of", "published_at", "retrieved_at"):
        if not isinstance(fact.get(field), str) or not fact[field]:
            raise ResearchMemoryError(f"RESEARCH_MEMORY_FACT_{field.upper()}_REQUIRED")
    # published_at belongs to a content version, not the logical identity.
    value = _strip_for_logical_key(dict(fact))
    value.pop("published_at", None)
    return canonical_hash(value)


def fact_content_hash(fact: Mapping[str, Any]) -> str:
    logical_fact_key(fact)
    return canonical_hash(_strip_for_content_version(dict(fact)))


def infer_dataset(fact: Mapping[str, Any]) -> str:
    source_id = str(fact.get("source_id", "")).lower()
    semantic = str(fact.get("semantic_field", "")).lower()
    if source_id.startswith("sec-companyfacts"):
        return "sec_companyfacts"
    if source_id.startswith("sec-"):
        return "sec_documents"
    if source_id.startswith("yahoo") and semantic in {
        "adjusted_close_price", "historical_close_price", "open_price",
        "high_price", "low_price", "share_volume", "cash_dividend",
        "stock_split_ratio",
    }:
        return "yahoo_daily"
    if source_id.startswith("yahoo"):
        return "current_snapshot"
    if semantic in {"company_name", "company_description", "employee_count"}:
        return "company_profile"
    return "current_snapshot"


def infer_provider(fact: Mapping[str, Any]) -> str:
    dataset = infer_dataset(fact)
    if dataset.startswith("sec_"):
        return "sec"
    if dataset == "yahoo_daily":
        return "yahoo"
    if dataset == "current_snapshot":
        return "market"
    if dataset == "company_profile":
        return "public"
    return str(fact.get("source_id", "")).split("-", 1)[0].lower()


def report_entry_id(reuse_key: str, report_hash: str) -> str:
    return canonical_hash({"reuse_key": reuse_key, "report_hash": report_hash})


def validate_incremental_plan(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "security_id", "provider", "dataset", "scope",
        "planning_as_of", "mode", "request_range", "policy", "reason",
        "checkpoint_revision", "plan_hash",
    }
    if set(value) != required or value.get("schema_version") != PLAN_VERSION:
        raise ResearchMemoryError("RESEARCH_MEMORY_PLAN_SCHEMA_INVALID")
    if value.get("mode") not in {"BOOTSTRAP", "REFRESH", "DELTA", "SKIP_FRESH"}:
        raise ResearchMemoryError("RESEARCH_MEMORY_PLAN_MODE_INVALID")
    if value.get("plan_hash") != canonical_hash({k: v for k, v in value.items() if k != "plan_hash"}):
        raise ResearchMemoryError("RESEARCH_MEMORY_PLAN_HASH_INVALID")
    parse_timestamp(str(value["planning_as_of"]))


def validate_research_view(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "view_id", "run_id", "security_id", "decision_cutoff",
        "selected_fact_versions", "checkpoint_revisions", "coverage", "gaps",
        "conflicts", "policy_version", "view_manifest_hash",
    }
    if set(value) != required or value.get("schema_version") != VIEW_VERSION:
        raise ResearchMemoryError("RESEARCH_MEMORY_VIEW_SCHEMA_INVALID")
    parse_timestamp(str(value["decision_cutoff"]))
    if value.get("view_manifest_hash") != canonical_hash({k: v for k, v in value.items() if k != "view_manifest_hash"}):
        raise ResearchMemoryError("RESEARCH_MEMORY_VIEW_HASH_INVALID")


def validate_report_reference(value: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "security_id", "reuse_key", "research_input_fingerprint",
        "report_hash", "package_hash", "original_run_id", "original_invocation_id",
        "original_report_cutoff", "checked_at", "research_status", "package_ref",
        "reference_hash",
    }
    if set(value) != required or value.get("schema_version") != REPORT_REFERENCE_VERSION:
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_REFERENCE_SCHEMA_INVALID")
    for field in ("original_report_cutoff", "checked_at"):
        parse_timestamp(str(value[field]))
    if value.get("reference_hash") != canonical_hash({k: v for k, v in value.items() if k != "reference_hash"}):
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_REFERENCE_HASH_INVALID")


class ResearchMemory:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.database_path = self.root / "research-memory.sqlite3"
        self.objects_root = self.root / "objects"
        self.locks_root = self.root / "locks"
        self.objects_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.locks_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def session(self):
        """A committing/rolling-back SQLite context that also closes."""
        with closing(self.connect()) as connection:
            with connection:
                yield connection

    def _migrate(self) -> None:
        connection = self.connect()
        try:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > MEMORY_SCHEMA_VERSION:
                raise ResearchMemoryError("RESEARCH_MEMORY_SCHEMA_NEWER_THAN_RUNTIME")
            if current == 0:
                connection.executescript("""
                    BEGIN;
                    CREATE TABLE fact_versions (
                        version_hash TEXT PRIMARY KEY,
                        logical_key TEXT NOT NULL,
                        security_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        dataset TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        evidence_id TEXT NOT NULL UNIQUE,
                        as_of TEXT NOT NULL,
                        published_at TEXT NOT NULL,
                        first_retrieved_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX fact_lookup ON fact_versions(security_id, dataset, logical_key, published_at);
                    CREATE TABLE observations (
                        observation_hash TEXT PRIMARY KEY,
                        version_hash TEXT NOT NULL REFERENCES fact_versions(version_hash),
                        retrieved_at TEXT NOT NULL,
                        raw_content_hash TEXT,
                        source_locator TEXT,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE dataset_state (
                        security_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        dataset TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        policy_version TEXT NOT NULL,
                        revision INTEGER NOT NULL,
                        last_success_at TEXT,
                        freshness_until TEXT,
                        watermark TEXT,
                        coverage_json TEXT NOT NULL,
                        pending_json TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        PRIMARY KEY(security_id, provider, dataset, scope)
                    );
                    CREATE TABLE attempts (
                        attempt_id TEXT PRIMARY KEY,
                        security_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        dataset TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        plan_hash TEXT,
                        status TEXT NOT NULL,
                        started_at TEXT NOT NULL,
                        completed_at TEXT NOT NULL,
                        details_json TEXT NOT NULL
                    );
                    CREATE INDEX attempt_lookup ON attempts(security_id, dataset, completed_at);
                    CREATE TABLE research_views (
                        view_manifest_hash TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        security_id TEXT NOT NULL,
                        decision_cutoff TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE reports (
                        entry_id TEXT PRIMARY KEY,
                        reuse_key TEXT NOT NULL,
                        security_id TEXT NOT NULL,
                        research_input_fingerprint TEXT NOT NULL,
                        report_hash TEXT NOT NULL,
                        package_hash TEXT NOT NULL,
                        package_ref TEXT NOT NULL,
                        original_run_id TEXT NOT NULL,
                        original_invocation_id TEXT NOT NULL,
                        original_report_cutoff TEXT NOT NULL,
                        research_status TEXT NOT NULL,
                        stored_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        UNIQUE(reuse_key, report_hash)
                    );
                    CREATE INDEX report_lookup ON reports(security_id, reuse_key, stored_at);
                    CREATE TABLE reuse_events (
                        event_hash TEXT PRIMARY KEY,
                        reuse_key TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        checked_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    PRAGMA user_version = 2;
                    COMMIT;
                """)
            elif current == 1:
                connection.create_function("report_entry_id", 2, report_entry_id)
                connection.executescript("""
                    PRAGMA foreign_keys = OFF;
                    BEGIN IMMEDIATE;
                    ALTER TABLE reports RENAME TO reports_v1;
                    ALTER TABLE reuse_events RENAME TO reuse_events_v1;
                    CREATE TABLE reports (
                        entry_id TEXT PRIMARY KEY,
                        reuse_key TEXT NOT NULL,
                        security_id TEXT NOT NULL,
                        research_input_fingerprint TEXT NOT NULL,
                        report_hash TEXT NOT NULL,
                        package_hash TEXT NOT NULL,
                        package_ref TEXT NOT NULL,
                        original_run_id TEXT NOT NULL,
                        original_invocation_id TEXT NOT NULL,
                        original_report_cutoff TEXT NOT NULL,
                        research_status TEXT NOT NULL,
                        stored_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        UNIQUE(reuse_key, report_hash)
                    );
                    CREATE INDEX report_lookup ON reports(security_id, reuse_key, stored_at);
                    CREATE TABLE reuse_events (
                        event_hash TEXT PRIMARY KEY,
                        reuse_key TEXT NOT NULL,
                        run_id TEXT NOT NULL,
                        checked_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    INSERT INTO reports (
                        entry_id, reuse_key, security_id,
                        research_input_fingerprint, report_hash, package_hash,
                        package_ref, original_run_id, original_invocation_id,
                        original_report_cutoff, research_status, stored_at,
                        metadata_json
                    )
                    SELECT
                        report_entry_id(reuse_key, report_hash), reuse_key,
                        security_id, research_input_fingerprint, report_hash,
                        package_hash, package_ref, original_run_id,
                        original_invocation_id, original_report_cutoff,
                        research_status, stored_at, metadata_json
                    FROM reports_v1;
                    INSERT INTO reuse_events
                    SELECT event_hash, reuse_key, run_id, checked_at, payload_json
                    FROM reuse_events_v1;
                    DROP TABLE reuse_events_v1;
                    DROP TABLE reports_v1;
                    PRAGMA user_version = 2;
                    COMMIT;
                    PRAGMA foreign_keys = ON;
                """)
            self.lightweight_check(connection)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def lightweight_check(connection: sqlite3.Connection) -> None:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ResearchMemoryError("RESEARCH_MEMORY_QUICK_CHECK_FAILED")
        required = {"fact_versions", "observations", "dataset_state", "attempts", "research_views", "reports", "reuse_events"}
        existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= existing:
            raise ResearchMemoryError("RESEARCH_MEMORY_SCHEMA_INCOMPLETE")

    def integrity_check(self) -> None:
        with self.session() as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ResearchMemoryError("RESEARCH_MEMORY_INTEGRITY_CHECK_FAILED")

    def backup(self, destination: Path) -> Path:
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        with closing(self.connect()) as source, closing(sqlite3.connect(destination / "research-memory.sqlite3")) as target:
            source.backup(target)
        shutil.copytree(self.objects_root, destination / "objects")
        return destination

    @contextmanager
    def dataset_lock(
        self, security_id: str, provider: str, dataset: str, scope: str = "default",
        *, timeout_seconds: float = 30.0,
    ):
        identity = canonical_hash({"security_id": security_id, "provider": provider, "dataset": dataset, "scope": scope})
        path = self.locks_root / f"{identity}.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        started = time.monotonic()
        acquired = False
        try:
            while time.monotonic() - started <= timeout_seconds:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    time.sleep(min(0.05, max(timeout_seconds / 20, 0.005)))
            if not acquired:
                raise ResearchMemoryError("RESEARCH_MEMORY_DATASET_LOCK_TIMEOUT")
            yield
        finally:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def store_object(self, value: bytes | Mapping[str, Any] | Sequence[Any]) -> dict[str, str]:
        raw = value if isinstance(value, bytes) else (_canonical_json(value) + "\n").encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        path = self.objects_root / digest
        if path.exists():
            if path.is_symlink() or path.read_bytes() != raw:
                raise ResearchMemoryError("RESEARCH_MEMORY_OBJECT_COLLISION")
        else:
            descriptor, name = tempfile.mkstemp(dir=self.objects_root, prefix=".pending-")
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.read_bytes() != raw:
                        raise ResearchMemoryError("RESEARCH_MEMORY_OBJECT_COLLISION")
            finally:
                temporary.unlink(missing_ok=True)
        return {"object_hash": digest, "object_ref": f"objects/{digest}"}

    def read_object(self, reference: str, expected_hash: str) -> bytes:
        if reference != f"objects/{expected_hash}":
            raise ResearchMemoryError("RESEARCH_MEMORY_OBJECT_REFERENCE_INVALID")
        path = self.root / reference
        if path.is_symlink() or not path.is_file():
            raise ResearchMemoryError("RESEARCH_MEMORY_OBJECT_MISSING")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ResearchMemoryError("RESEARCH_MEMORY_OBJECT_HASH_MISMATCH")
        return raw

    def checkpoint(self, security_id: str, provider: str, dataset: str, scope: str = "default") -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM dataset_state WHERE security_id=? AND provider=? AND dataset=? AND scope=?",
                (security_id, provider, dataset, scope),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        for field in ("coverage_json", "pending_json", "state_json"):
            value[field.removesuffix("_json")] = json.loads(value.pop(field))
        return value

    def plan(
        self, security_id: str, provider: str, dataset: str,
        *, planning_as_of: str, scope: str = "default",
        source_limits: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = parse_timestamp(planning_as_of)
        checkpoint = self.checkpoint(security_id, provider, dataset, scope)
        policy = deepcopy(DATASET_POLICIES.get(dataset, DATASET_POLICIES["current_snapshot"]))
        for key, value in (source_limits or {}).items():
            if key in policy and isinstance(value, (int, float)):
                policy[key] = min(policy[key], value)
        if checkpoint is None:
            mode, reason = "BOOTSTRAP", "CHECKPOINT_MISSING"
            request_range = {
                "start": (now.date() - timedelta(days=int(policy.get("bootstrap_days", 0)))).isoformat()
                if policy.get("bootstrap_days") else None,
                "end": (now.date() + timedelta(days=1)).isoformat(),
            }
            revision = 0
        else:
            revision = int(checkpoint["revision"])
            fresh = checkpoint.get("freshness_until") and parse_timestamp(checkpoint["freshness_until"]) >= now
            if fresh and not checkpoint["pending"]:
                mode, reason, request_range = "SKIP_FRESH", "CHECKPOINT_FRESH", {"start": None, "end": None}
            else:
                mode = "DELTA" if checkpoint.get("watermark") else "REFRESH"
                reason = "KNOWN_GAP" if checkpoint["pending"] else "STALE_CHECKPOINT"
                overlap = int(policy.get("overlap_sessions", 0))
                start = None
                if checkpoint.get("watermark"):
                    start = (parse_timestamp(checkpoint["watermark"]).date() - timedelta(days=max(overlap * 2, overlap))).isoformat()
                pending_starts = sorted(
                    str(item["start"])
                    for item in checkpoint["pending"]
                    if isinstance(item, Mapping)
                    and isinstance(item.get("start"), str)
                )
                if pending_starts:
                    bounded = (
                        now.date() - timedelta(days=int(policy.get("bootstrap_days", 0)))
                    ).isoformat() if policy.get("bootstrap_days") else pending_starts[0]
                    pending_start = max(bounded, pending_starts[0])
                    start = min(start, pending_start) if start is not None else pending_start
                request_range = {"start": start, "end": (now.date() + timedelta(days=1)).isoformat()}
        body = {
            "schema_version": PLAN_VERSION, "security_id": security_id,
            "provider": provider, "dataset": dataset, "scope": scope,
            "planning_as_of": iso_utc(now), "mode": mode,
            "request_range": request_range,
            "policy": dict(policy, policy_version=POLICY_VERSION),
            "reason": reason, "checkpoint_revision": revision,
        }
        body["plan_hash"] = canonical_hash(body)
        validate_incremental_plan(body)
        return body

    def ingest_dataset(
        self, *, plan: Mapping[str, Any], facts: Sequence[Mapping[str, Any]],
        status: str, completed_at: str, watermark: str | None = None,
        coverage: Sequence[Mapping[str, Any]] = (), pending: Sequence[Mapping[str, Any]] = (),
        details: Mapping[str, Any] | None = None,
        state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_incremental_plan(plan)
        if status not in SUCCESSFUL_INGEST_STATUSES:
            raise ResearchMemoryError("RESEARCH_MEMORY_INGEST_STATUS_NOT_SUCCESS")
        completed = iso_utc(completed_at)
        prepared: list[tuple[dict[str, Any], str, str, str]] = []
        for raw in facts:
            fact = deepcopy(dict(raw))
            logical = logical_fact_key(fact)
            version = fact_content_hash(fact)
            dataset = infer_dataset(fact)
            provider = infer_provider(fact)
            if fact["security_id"] != plan["security_id"]:
                raise ResearchMemoryError("RESEARCH_MEMORY_FACT_SECURITY_MISMATCH")
            if dataset != plan["dataset"]:
                raise ResearchMemoryError("RESEARCH_MEMORY_FACT_DATASET_MISMATCH")
            if provider != plan["provider"]:
                raise ResearchMemoryError("RESEARCH_MEMORY_FACT_PROVIDER_MISMATCH")
            prepared.append((fact, logical, version, dataset))
        attempt_body = {
            "security_id": plan["security_id"], "provider": plan["provider"],
            "dataset": plan["dataset"], "scope": plan["scope"],
            "plan_hash": plan["plan_hash"], "status": status,
            "started_at": plan["planning_as_of"], "completed_at": completed,
            "details": dict(details or {}),
        }
        attempt_id = canonical_hash(attempt_body)
        inserted = observations = 0
        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT revision FROM dataset_state WHERE security_id=? AND provider=? AND dataset=? AND scope=?",
                (plan["security_id"], plan["provider"], plan["dataset"], plan["scope"]),
            ).fetchone()
            revision = int(current[0]) if current else 0
            if revision != int(plan["checkpoint_revision"]):
                raise ResearchMemoryError("RESEARCH_MEMORY_CHECKPOINT_REVISION_CONFLICT")
            for fact, logical, version, fact_dataset in prepared:
                provider = str(fact["source_id"]).split("-", 1)[0]
                existing = connection.execute(
                    "SELECT payload_json FROM fact_versions WHERE version_hash=?", (version,),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO fact_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (version, logical, fact["security_id"], provider, fact_dataset,
                         fact["source_id"], fact["evidence_id"], fact["as_of"],
                         fact["published_at"], fact["retrieved_at"], _canonical_json(fact)),
                    )
                    inserted += 1
                elif json.loads(existing[0]) != fact:
                    # A semantically identical version retains the first canonical
                    # payload/Evidence ID. Later retrieval details are observations.
                    pass
                observation_body = {
                    "version_hash": version, "retrieved_at": fact["retrieved_at"],
                    "raw_content_hash": fact.get("raw_content_hash"),
                    "source_locator": fact.get("source_locator"),
                }
                observation_hash = canonical_hash(observation_body)
                before = connection.total_changes
                connection.execute(
                    "INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?)",
                    (observation_hash, version, fact["retrieved_at"],
                     fact.get("raw_content_hash"), fact.get("source_locator"),
                     _canonical_json(observation_body)),
                )
                observations += connection.total_changes - before
            connection.execute(
                "INSERT OR IGNORE INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)",
                (attempt_id, plan["security_id"], plan["provider"], plan["dataset"],
                 plan["scope"], plan["plan_hash"], status, plan["planning_as_of"],
                 completed, _canonical_json(attempt_body["details"])),
            )
            freshness = iso_utc(parse_timestamp(completed) + timedelta(seconds=int(plan["policy"].get("freshness_seconds", 0))))
            new_revision = revision + 1
            checkpoint_state = (
                dict(state) if state is not None
                else {"last_plan_hash": plan["plan_hash"], "last_status": status}
            )
            connection.execute(
                "INSERT INTO dataset_state VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(security_id,provider,dataset,scope) DO UPDATE SET "
                "policy_version=excluded.policy_version, revision=excluded.revision, "
                "last_success_at=excluded.last_success_at, freshness_until=excluded.freshness_until, "
                "watermark=excluded.watermark, coverage_json=excluded.coverage_json, "
                "pending_json=excluded.pending_json, state_json=excluded.state_json",
                (plan["security_id"], plan["provider"], plan["dataset"], plan["scope"],
                 plan["policy"]["policy_version"], new_revision, completed, freshness,
                 watermark, _canonical_json(list(coverage)), _canonical_json(list(pending)),
                 _canonical_json(checkpoint_state)),
            )
        return {
            "attempt_id": attempt_id, "status": status,
            "inserted_versions": inserted, "observations": observations,
            "request_range": dict(plan["request_range"]),
            "request_count": int((details or {}).get("request_count", 0)),
            "repair_request_count": int((details or {}).get("repair_request_count", 0)),
            "pending_count": len(pending),
            "checkpoint_revision_before": revision,
            "checkpoint_revision": new_revision,
        }

    def new_version_count(self, facts: Sequence[Mapping[str, Any]]) -> int:
        hashes = sorted({fact_content_hash(item) for item in facts})
        if not hashes:
            return 0
        placeholders = ",".join("?" for _ in hashes)
        with self.session() as connection:
            existing = connection.execute(
                f"SELECT COUNT(*) FROM fact_versions WHERE version_hash IN ({placeholders})",
                hashes,
            ).fetchone()[0]
        return len(hashes) - int(existing)

    def existing_version_hashes(
        self, facts: Sequence[Mapping[str, Any]],
    ) -> set[str]:
        """Return candidate content versions already committed to Memory."""

        hashes = sorted({fact_content_hash(item) for item in facts})
        if not hashes:
            return set()
        placeholders = ",".join("?" for _ in hashes)
        with self.session() as connection:
            rows = connection.execute(
                f"SELECT version_hash FROM fact_versions WHERE version_hash IN ({placeholders})",
                hashes,
            ).fetchall()
        return {str(row[0]) for row in rows}

    def revision_count(self, facts: Sequence[Mapping[str, Any]]) -> int:
        """Count new candidate versions whose logical fact already exists."""

        candidates = {
            (logical_fact_key(item), fact_content_hash(item)) for item in facts
        }
        if not candidates:
            return 0
        revisions = 0
        with self.session() as connection:
            for logical, version in sorted(candidates):
                version_exists = connection.execute(
                    "SELECT 1 FROM fact_versions WHERE version_hash=?", (version,),
                ).fetchone()
                prior_exists = connection.execute(
                    "SELECT 1 FROM fact_versions WHERE logical_key=? AND version_hash<>? LIMIT 1",
                    (logical, version),
                ).fetchone()
                if version_exists is None and prior_exists is not None:
                    revisions += 1
        return revisions

    def record_failed_attempt(
        self, *, plan: Mapping[str, Any], status: str, completed_at: str,
        details: Mapping[str, Any] | None = None,
    ) -> str:
        validate_incremental_plan(plan)
        if status not in {"SOURCE_LIMITED", "FAILED_VALIDATION", "FAILED_PERSISTENCE", "LOCK_TIMEOUT"}:
            raise ResearchMemoryError("RESEARCH_MEMORY_FAILED_ATTEMPT_STATUS_INVALID")
        body = {
            "security_id": plan["security_id"], "provider": plan["provider"],
            "dataset": plan["dataset"], "scope": plan["scope"],
            "plan_hash": plan["plan_hash"], "status": status,
            "started_at": plan["planning_as_of"], "completed_at": iso_utc(completed_at),
            "details": dict(details or {}),
        }
        attempt_id = canonical_hash(body)
        with self.session() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)",
                (attempt_id, body["security_id"], body["provider"], body["dataset"],
                 body["scope"], body["plan_hash"], body["status"], body["started_at"],
                 body["completed_at"], _canonical_json(body["details"])),
            )
        return attempt_id

    def record_attempt_only(
        self, *, plan: Mapping[str, Any], status: str, completed_at: str,
        details: Mapping[str, Any] | None = None,
    ) -> str:
        """Record a cache/freshness outcome without advancing its checkpoint."""
        validate_incremental_plan(plan)
        if status not in {"SKIPPED_FRESH", "CACHE_HIT", "NOT_ATTEMPTED"}:
            raise ResearchMemoryError("RESEARCH_MEMORY_ATTEMPT_ONLY_STATUS_INVALID")
        body = {
            "security_id": plan["security_id"], "provider": plan["provider"],
            "dataset": plan["dataset"], "scope": plan["scope"],
            "plan_hash": plan["plan_hash"], "status": status,
            "started_at": plan["planning_as_of"],
            "completed_at": iso_utc(completed_at),
            "details": dict(details or {}),
        }
        attempt_id = canonical_hash(body)
        with self.session() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)",
                (attempt_id, body["security_id"], body["provider"], body["dataset"],
                 body["scope"], body["plan_hash"], body["status"], body["started_at"],
                 body["completed_at"], _canonical_json(body["details"])),
            )
        return attempt_id

    def current_facts(self, security_id: str, decision_cutoff: str) -> list[dict[str, Any]]:
        cutoff = parse_timestamp(decision_cutoff)
        with self.session() as connection:
            rows = connection.execute(
                "SELECT logical_key, version_hash, published_at, first_retrieved_at, payload_json FROM fact_versions "
                "WHERE security_id=? ORDER BY logical_key, published_at, version_hash",
                (security_id,),
            ).fetchall()
        selected: dict[str, tuple[datetime, datetime, str, dict[str, Any]]] = {}
        for row in rows:
            payload = json.loads(row["payload_json"])
            if max(parse_timestamp(payload["as_of"]), parse_timestamp(payload["published_at"]), parse_timestamp(payload["retrieved_at"])) > cutoff:
                continue
            rank = (
                parse_timestamp(payload["published_at"]),
                parse_timestamp(row["first_retrieved_at"]),
                row["version_hash"],
            )
            current = selected.get(row["logical_key"])
            if current is None or rank > current[:3]:
                selected[row["logical_key"]] = (rank[0], rank[1], rank[2], payload)
        return sorted((item[3] for item in selected.values()), key=lambda value: value["evidence_id"])

    def save_view(
        self, *, run_id: str, security_id: str, decision_cutoff: str,
        facts: Sequence[Mapping[str, Any]], gaps: Sequence[Any], conflicts: Sequence[Any],
    ) -> dict[str, Any]:
        with self.session() as connection:
            checkpoints = {
                row["dataset"]: row["revision"] for row in connection.execute(
                    "SELECT dataset, revision FROM dataset_state WHERE security_id=?", (security_id,),
                )
            }
        selected_versions = [fact_content_hash(item) for item in facts]
        body = {
            "schema_version": VIEW_VERSION,
            "view_id": f"research-view:{run_id}:{security_id}", "run_id": run_id,
            "security_id": security_id, "decision_cutoff": iso_utc(decision_cutoff),
            "selected_fact_versions": sorted(selected_versions),
            "checkpoint_revisions": checkpoints,
            "coverage": sorted({infer_dataset(item) for item in facts}),
            "gaps": list(gaps), "conflicts": list(conflicts),
            "policy_version": POLICY_VERSION,
        }
        body["view_manifest_hash"] = canonical_hash(body)
        validate_research_view(body)
        with self.session() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO research_views VALUES(?,?,?,?,?)",
                (body["view_manifest_hash"], run_id, security_id, body["decision_cutoff"], _canonical_json(body)),
            )
        return body

    def store_snapshot_bundle(
        self, *, security_id: str, portfolio: Mapping[str, Any], snapshot: Mapping[str, Any],
        calendar: Mapping[str, Any], source_item: Mapping[str, Any] | None = None,
        cache_root: Path | None = None,
    ) -> dict[str, Any]:
        payload = {
            "portfolio": portfolio, "snapshot": snapshot, "calendar": calendar,
            "source_item": source_item,
            "cache_root": str(Path(cache_root).resolve()) if cache_root is not None else None,
        }
        stored = self.store_object(payload)
        return dict(stored, snapshot_hash=snapshot["snapshot_hash"], decision_cutoff=snapshot["decision_cutoff"], security_id=security_id)

    def load_snapshot_bundle(self, checkpoint: Mapping[str, Any]) -> dict[str, Any]:
        state = checkpoint.get("state", {})
        raw = self.read_object(str(state.get("object_ref")), str(state.get("object_hash")))
        value = json.loads(raw)
        if not isinstance(value, dict) or not {"portfolio", "snapshot", "calendar"} <= set(value):
            raise ResearchMemoryError("RESEARCH_MEMORY_SNAPSHOT_BUNDLE_INVALID")
        return value

    def save_report_index(self, reference: Mapping[str, Any], metadata: Mapping[str, Any]) -> None:
        validate_report_reference(reference)
        entry_id = report_entry_id(
            reference["reuse_key"], reference["report_hash"],
        )
        with self.session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT metadata_json FROM reports WHERE entry_id=?", (entry_id,)
            ).fetchone()
            payload = _canonical_json(dict(metadata))
            if row is not None and row[0] != payload:
                raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_KEY_COLLISION")
            connection.execute(
                "INSERT OR IGNORE INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (entry_id, reference["reuse_key"], reference["security_id"], reference["research_input_fingerprint"],
                 reference["report_hash"], reference["package_hash"], reference["package_ref"],
                 reference["original_run_id"], reference["original_invocation_id"],
                 reference["original_report_cutoff"], reference["research_status"],
                 reference["checked_at"], payload),
            )

    def reusable_report(self, security_id: str, reuse_key: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM reports WHERE security_id=? AND reuse_key=? "
                "ORDER BY stored_at DESC, entry_id DESC LIMIT 1",
                (security_id, reuse_key),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value.pop("entry_id", None)
        value["metadata"] = json.loads(value.pop("metadata_json"))
        self.read_object(value["package_ref"], value["package_hash"])
        return value

    def load_report_package(
        self, package_ref: str, package_hash: str,
    ) -> dict[str, Any]:
        raw = self.read_object(package_ref, package_hash)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_INVALID") from exc
        if not isinstance(value, dict):
            raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_INVALID")
        required = {
            "schema_version", "security_id", "research_input_fingerprint",
            "reuse_key", "report", "markdown", "request", "evidence",
            "calculations", "attachment", "validation", "manifest",
        }
        if set(value) != required or value.get("schema_version") != "company-research-report-package/1.0.0":
            raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_INVALID")
        if value.get("reuse_key") != report_reuse_key(
            str(value.get("security_id")), str(value.get("research_input_fingerprint")),
        ):
            raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_BINDING_INVALID")
        report = value.get("report")
        manifest = value.get("manifest")
        if not isinstance(report, Mapping) or not isinstance(manifest, Mapping):
            raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_INVALID")
        if manifest.get("report_hash") != canonical_hash(report):
            raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_HASH_MISMATCH")
        expected_hashes = {
            "request_hash": canonical_hash(value["request"]),
            "evidence_hash": canonical_hash(value["evidence"]),
            "calculation_hash": canonical_hash(value["calculations"]),
            "attachment_hash": canonical_hash(value["attachment"]),
            "markdown_hash": hashlib.sha256(
                str(value["markdown"]).encode("utf-8")
            ).hexdigest(),
        }
        if any(manifest.get(field) != digest for field, digest in expected_hashes.items()):
            raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_HASH_MISMATCH")
        return value

    def make_report_reference(
        self, stored: Mapping[str, Any], *, checked_at: str,
    ) -> dict[str, Any]:
        body = {
            "schema_version": REPORT_REFERENCE_VERSION,
            "security_id": stored["security_id"],
            "reuse_key": stored["reuse_key"],
            "research_input_fingerprint": stored["research_input_fingerprint"],
            "report_hash": stored["report_hash"],
            "package_hash": stored["package_hash"],
            "original_run_id": stored["original_run_id"],
            "original_invocation_id": stored["original_invocation_id"],
            "original_report_cutoff": stored["original_report_cutoff"],
            "checked_at": iso_utc(checked_at),
            "research_status": stored["research_status"],
            "package_ref": stored["package_ref"],
        }
        body["reference_hash"] = canonical_hash(body)
        validate_report_reference(body)
        return body

    def record_reuse(self, reference: Mapping[str, Any], *, run_id: str) -> None:
        validate_report_reference(reference)
        body = {"run_id": run_id, "reference": dict(reference)}
        event_hash = canonical_hash(body)
        with self.session() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO reuse_events VALUES(?,?,?,?,?)",
                (event_hash, reference["reuse_key"], run_id, reference["checked_at"], _canonical_json(body)),
            )


def research_input_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash only the explicitly model-visible research input.

    Callers construct this closed object. Unknown top-level keys fail closed so
    a new input field cannot be silently excluded from report reuse.
    """

    allowed = {
        "security", "evidence", "gaps", "conflicts", "attachments", "calculations",
        "research_question", "holding_horizon", "user_context", "model",
        "agent_binding", "skill_bindings", "schema_hash", "prompt_policy",
        "data_policy", "risk_policy", "adapter_versions", "time_context",
    }
    if set(payload) != allowed:
        raise ResearchMemoryError("RESEARCH_INPUT_FINGERPRINT_FIELDS_INVALID")
    return canonical_hash(payload)


def report_reuse_key(security_id: str, fingerprint: str) -> str:
    return canonical_hash({"security_id": security_id, "research_input_fingerprint": fingerprint})
