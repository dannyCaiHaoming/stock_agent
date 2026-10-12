"""Repository-external append-only SQLite ledger for private broker facts."""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping, Sequence
from uuid import uuid4

from product.runtime.hashing import canonical_hash


LEDGER_SCHEMA_VERSION = 1
LEDGER_APPLICATION_ID = 0x53414754  # SAGT
LEDGER_FILENAME = "private-broker-ledger.sqlite3"
ACTIVITY_TYPES = frozenset({
    "ACCOUNT_SNAPSHOT", "POSITION", "ORDER", "EXECUTION", "CHARGE",
    "DIVIDEND", "TAX", "CORPORATE_ACTION", "CASH_ACTIVITY",
    "FUNDING_ACTIVITY", "FOREX_ACTIVITY",
})
SENSITIVE_KEYS = frozenset({
    "account", "account_id", "account_number", "token", "private_key",
    "secret_key", "authorization", "password", "credential", "credentials",
})


class PrivateBrokerLedgerError(ValueError):
    """Stable private ledger error."""


@dataclass(frozen=True)
class AppendResult:
    status: str
    logical_key: str
    revision: int
    content_hash: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in SENSITIVE_KEYS or _contains_sensitive_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _content_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    ignored = {"retrieved_at", "batch_id", "record_id", "revision", "content_hash", "last_seen_at"}
    return {str(key): value for key, value in record.items() if key not in ignored}


def _require_text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise PrivateBrokerLedgerError(f"BROKER_LEDGER_{key.upper()}_REQUIRED")
    return value


def resolve_ledger_root(repository_root: Path, ledger_root: Path, *, create: bool) -> Path:
    repository = Path(repository_root).resolve()
    raw = Path(ledger_root).expanduser()
    if not raw.is_absolute():
        raise PrivateBrokerLedgerError("BROKER_LEDGER_ABSOLUTE_PATH_REQUIRED")
    if raw.exists() and raw.is_symlink():
        raise PrivateBrokerLedgerError("BROKER_LEDGER_SYMLINK_REJECTED")
    root = raw.resolve()
    if root == repository or repository in root.parents:
        raise PrivateBrokerLedgerError("BROKER_LEDGER_MUST_BE_EXTERNAL")
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not root.is_dir():
        raise PrivateBrokerLedgerError("BROKER_LEDGER_ROOT_NOT_DIRECTORY")
    if os.name != "nt" and root.stat().st_mode & 0o077:
        raise PrivateBrokerLedgerError("BROKER_LEDGER_ROOT_PERMISSIONS_TOO_OPEN")
    if not os.access(root, os.R_OK | os.X_OK | (os.W_OK if create else os.R_OK)):
        raise PrivateBrokerLedgerError("BROKER_LEDGER_ROOT_PERMISSION_DENIED")
    database = root / LEDGER_FILENAME
    if database.exists() and database.is_symlink():
        raise PrivateBrokerLedgerError("BROKER_LEDGER_DATABASE_SYMLINK_REJECTED")
    return root


class PrivateBrokerLedger:
    def __init__(self, root: Path, *, repository_root: Path, create: bool = False, timeout: float = 0.2):
        self.root = resolve_ledger_root(repository_root, root, create=create)
        self.database = self.root / LEDGER_FILENAME
        self.timeout = timeout
        if create:
            self._initialize()
        elif not self.database.is_file():
            raise PrivateBrokerLedgerError("BROKER_LEDGER_DATABASE_MISSING")
        self._validate_version(read_only=not create)

    @contextmanager
    def _write_connection(self) -> Iterator[sqlite3.Connection]:
        try:
            with closing(sqlite3.connect(self.database, timeout=self.timeout)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("PRAGMA busy_timeout = 100")
                yield connection
                connection.commit()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).casefold() or "busy" in str(exc).casefold():
                raise PrivateBrokerLedgerError("BROKER_LEDGER_BUSY") from exc
            raise PrivateBrokerLedgerError("BROKER_LEDGER_WRITE_FAILED") from exc
        except sqlite3.Error as exc:
            raise PrivateBrokerLedgerError("BROKER_LEDGER_WRITE_FAILED") from exc

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        uri = f"file:{self.database}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=self.timeout)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA query_only = ON")
                connection.execute("PRAGMA busy_timeout = 100")
                yield connection
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).casefold() or "busy" in str(exc).casefold():
                raise PrivateBrokerLedgerError("BROKER_LEDGER_BUSY") from exc
            raise PrivateBrokerLedgerError("BROKER_LEDGER_READ_FAILED") from exc
        except sqlite3.Error as exc:
            raise PrivateBrokerLedgerError("BROKER_LEDGER_READ_FAILED") from exc

    def _initialize(self) -> None:
        created = not self.database.exists()
        with self._write_connection() as connection:
            connection.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS activity_revisions (
                    record_id TEXT NOT NULL,
                    logical_key TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    activity_type TEXT NOT NULL,
                    account_ref TEXT NOT NULL,
                    provider_id TEXT,
                    key_reliability TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    raw_time TEXT,
                    raw_timezone TEXT,
                    occurred_at_utc TEXT,
                    market_date TEXT,
                    instrument_key TEXT,
                    display_symbol TEXT,
                    market TEXT,
                    currency TEXT,
                    asset_type TEXT,
                    direction TEXT,
                    status TEXT,
                    quantity REAL,
                    price REAL,
                    amount REAL,
                    order_id TEXT,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    PRIMARY KEY (logical_key, revision),
                    UNIQUE (logical_key, content_hash)
                );
                CREATE INDEX IF NOT EXISTS activity_current_idx
                    ON activity_revisions(account_ref, activity_type, retrieved_at, logical_key, revision);
                CREATE INDEX IF NOT EXISTS activity_filter_idx
                    ON activity_revisions(account_ref, market_date, display_symbol, market, currency, direction, status);

                CREATE TABLE IF NOT EXISTS asset_points (
                    point_id TEXT NOT NULL,
                    logical_key TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    account_ref TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    business_date TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    asset_value REAL,
                    cash_balance REAL,
                    net_external_flow REAL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    PRIMARY KEY (logical_key, revision),
                    UNIQUE (logical_key, content_hash)
                );
                CREATE INDEX IF NOT EXISTS asset_point_current_idx
                    ON asset_points(account_ref, business_date, retrieved_at, logical_key, revision);

                CREATE TABLE IF NOT EXISTS sync_windows (
                    sync_window_id TEXT PRIMARY KEY,
                    account_ref TEXT NOT NULL,
                    category TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    status TEXT NOT NULL,
                    history_start TEXT NOT NULL,
                    history_start_accuracy TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    record_count INTEGER NOT NULL,
                    duplicate_count INTEGER NOT NULL,
                    revision_count INTEGER NOT NULL,
                    gap_code TEXT,
                    retrieved_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sync_window_lookup_idx
                    ON sync_windows(account_ref, category, window_end, retrieved_at);

                CREATE TABLE IF NOT EXISTS analysis_packages (
                    analysis_id TEXT PRIMARY KEY,
                    account_ref TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    formula_version TEXT NOT NULL,
                    ledger_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE
                );
                CREATE INDEX IF NOT EXISTS analysis_lookup_idx
                    ON analysis_packages(account_ref, as_of, retrieved_at);
            """)
            connection.execute(f"PRAGMA application_id = {LEDGER_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION}")
        if created and os.name != "nt":
            os.chmod(self.database, 0o600)

    def _validate_version(self, *, read_only: bool) -> None:
        context = self.read_connection() if read_only else self._write_connection()
        with context as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            if version != LEDGER_SCHEMA_VERSION or application_id != LEDGER_APPLICATION_ID:
                raise PrivateBrokerLedgerError("BROKER_LEDGER_VERSION_UNSUPPORTED")

    def diagnostic(self) -> dict[str, Any]:
        with self.read_connection() as connection:
            tables = sorted(row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ))
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }
        return {
            "status": "READY",
            "schema_version": LEDGER_SCHEMA_VERSION,
            "tables": tables,
            "counts": counts,
        }

    def get_or_create_account_ref(self) -> str:
        """Return the ledger-local opaque account reference without persisting an account id."""
        metadata_id = "metadata:account_ref"
        with self._write_connection() as connection:
            existing = connection.execute(
                "SELECT account_ref FROM sync_windows WHERE sync_window_id=?",
                (metadata_id,),
            ).fetchone()
            if existing is not None:
                return str(existing["account_ref"])
            account_ref = f"tiger-account:****:{uuid4().hex}"
            created_at = utc_now()
            payload = {
                "kind": "OPAQUE_ACCOUNT_REFERENCE",
                "account_ref": account_ref,
                "created_at": created_at,
            }
            connection.execute(
                """INSERT INTO sync_windows(
                    sync_window_id,account_ref,category,window_start,window_end,status,
                    history_start,history_start_accuracy,page_count,record_count,
                    duplicate_count,revision_count,gap_code,retrieved_at,payload_json,content_hash
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    metadata_id, account_ref, "LEDGER_METADATA", created_at, created_at,
                    "METADATA", created_at, "EXACT", 0, 0, 0, 0, None, created_at,
                    _canonical_json(payload), canonical_hash(payload),
                ),
            )
            return account_ref

    def account_ref(self) -> str:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT account_ref FROM sync_windows WHERE sync_window_id='metadata:account_ref'",
            ).fetchone()
        if row is None:
            raise PrivateBrokerLedgerError("BROKER_LEDGER_ACCOUNT_REF_MISSING")
        return str(row["account_ref"])

    def append_activity(self, record: Mapping[str, Any]) -> AppendResult:
        activity_type = _require_text(record, "activity_type")
        if activity_type not in ACTIVITY_TYPES:
            raise PrivateBrokerLedgerError("BROKER_LEDGER_ACTIVITY_TYPE_INVALID")
        account_ref = _require_text(record, "account_ref")
        source_id = _require_text(record, "source_id")
        as_of = _require_text(record, "as_of")
        retrieved_at = _require_text(record, "retrieved_at")
        batch_id = _require_text(record, "batch_id")
        if _contains_sensitive_key(record):
            raise PrivateBrokerLedgerError("BROKER_LEDGER_SENSITIVE_FIELD_REJECTED")
        provider_id = record.get("provider_id")
        if provider_id is not None and (not isinstance(provider_id, str) or not provider_id):
            raise PrivateBrokerLedgerError("BROKER_LEDGER_PROVIDER_ID_INVALID")
        logical_basis = {
            key: record.get(key)
            for key in (
                "activity_type", "account_ref", "instrument_key", "as_of", "direction",
                "quantity", "price", "amount", "order_id",
            )
        }
        logical_key = canonical_hash({
            "account_ref": account_ref,
            "activity_type": activity_type,
            "provider_id": provider_id,
        } if provider_id else logical_basis)
        key_reliability = "PROVIDER_ID" if provider_id else "DERIVED"
        content = _content_payload(record)
        content_hash = canonical_hash(content)
        payload_json = _canonical_json(dict(record))
        with self._write_connection() as connection:
            existing = connection.execute(
                "SELECT revision FROM activity_revisions WHERE logical_key=? AND content_hash=?",
                (logical_key, content_hash),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    "UPDATE activity_revisions SET last_seen_at=? WHERE logical_key=? AND revision=?",
                    (retrieved_at, logical_key, int(existing["revision"])),
                )
                return AppendResult("OBSERVED", logical_key, int(existing["revision"]), content_hash)
            previous = connection.execute(
                "SELECT MAX(revision) AS revision FROM activity_revisions WHERE logical_key=?",
                (logical_key,),
            ).fetchone()
            revision = int(previous["revision"] or 0) + 1
            status = "INSERTED" if revision == 1 else "REVISED"
            values = (
                f"activity:{uuid4().hex}", logical_key, revision, activity_type, account_ref,
                provider_id, key_reliability, source_id, as_of, retrieved_at,
                record.get("raw_time"), record.get("raw_timezone"), record.get("occurred_at_utc"),
                record.get("market_date"), record.get("instrument_key"), record.get("display_symbol"),
                record.get("market"), record.get("currency"), record.get("asset_type"),
                record.get("direction"), record.get("status"), record.get("quantity"),
                record.get("price"), record.get("amount"), record.get("order_id"),
                payload_json, content_hash, retrieved_at, retrieved_at, batch_id,
            )
            connection.execute(
                """INSERT INTO activity_revisions(
                    record_id,logical_key,revision,activity_type,account_ref,provider_id,
                    key_reliability,source_id,as_of,retrieved_at,raw_time,raw_timezone,
                    occurred_at_utc,market_date,instrument_key,display_symbol,market,currency,
                    asset_type,direction,status,quantity,price,amount,order_id,payload_json,
                    content_hash,first_seen_at,last_seen_at,batch_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                values,
            )
            return AppendResult(status, logical_key, revision, content_hash)

    def append_asset_point(self, record: Mapping[str, Any]) -> AppendResult:
        for key in ("account_ref", "source_id", "as_of", "retrieved_at", "business_date", "currency", "batch_id"):
            _require_text(record, key)
        if _contains_sensitive_key(record):
            raise PrivateBrokerLedgerError("BROKER_LEDGER_SENSITIVE_FIELD_REJECTED")
        logical_key = canonical_hash({
            "account_ref": record["account_ref"],
            "business_date": record["business_date"],
            "currency": record["currency"],
        })
        content_hash = canonical_hash(_content_payload(record))
        payload_json = _canonical_json(dict(record))
        with self._write_connection() as connection:
            existing = connection.execute(
                "SELECT revision FROM asset_points WHERE logical_key=? AND content_hash=?",
                (logical_key, content_hash),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    "UPDATE asset_points SET last_seen_at=? WHERE logical_key=? AND revision=?",
                    (record["retrieved_at"], logical_key, int(existing["revision"])),
                )
                return AppendResult("OBSERVED", logical_key, int(existing["revision"]), content_hash)
            previous = connection.execute(
                "SELECT MAX(revision) AS revision FROM asset_points WHERE logical_key=?", (logical_key,),
            ).fetchone()
            revision = int(previous["revision"] or 0) + 1
            status = "INSERTED" if revision == 1 else "REVISED"
            connection.execute(
                """INSERT INTO asset_points(
                    point_id,logical_key,revision,account_ref,source_id,as_of,retrieved_at,
                    business_date,currency,asset_value,cash_balance,net_external_flow,
                    payload_json,content_hash,first_seen_at,last_seen_at,batch_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"asset:{uuid4().hex}", logical_key, revision, record["account_ref"],
                    record["source_id"], record["as_of"], record["retrieved_at"],
                    record["business_date"], record["currency"], record.get("asset_value"),
                    record.get("cash_balance"), record.get("net_external_flow"), payload_json,
                    content_hash, record["retrieved_at"], record["retrieved_at"], record["batch_id"],
                ),
            )
            return AppendResult(status, logical_key, revision, content_hash)

    def record_sync_window(self, value: Mapping[str, Any]) -> str:
        if _contains_sensitive_key(value):
            raise PrivateBrokerLedgerError("BROKER_LEDGER_SENSITIVE_FIELD_REJECTED")
        required = (
            "account_ref", "category", "window_start", "window_end", "status",
            "history_start", "history_start_accuracy", "retrieved_at",
        )
        for key in required:
            _require_text(value, key)
        payload_json = _canonical_json(dict(value))
        content_hash = canonical_hash(dict(value))
        sync_window_id = str(value.get("sync_window_id") or f"sync-window:{uuid4().hex}")
        with self._write_connection() as connection:
            connection.execute(
                """INSERT INTO sync_windows(
                    sync_window_id,account_ref,category,window_start,window_end,status,
                    history_start,history_start_accuracy,page_count,record_count,
                    duplicate_count,revision_count,gap_code,retrieved_at,payload_json,content_hash
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sync_window_id, value["account_ref"], value["category"],
                    value["window_start"], value["window_end"], value["status"],
                    value["history_start"], value["history_start_accuracy"],
                    int(value.get("page_count", 0)), int(value.get("record_count", 0)),
                    int(value.get("duplicate_count", 0)), int(value.get("revision_count", 0)),
                    value.get("gap_code"), value["retrieved_at"], payload_json, content_hash,
                ),
            )
        return sync_window_id

    def latest_complete_window_end(self, *, account_ref: str, category: str) -> str | None:
        with self.read_connection() as connection:
            rows = connection.execute(
                """SELECT window_start,window_end,status,retrieved_at,rowid FROM sync_windows
                   WHERE account_ref=? AND category=?
                   ORDER BY window_start,window_end,retrieved_at DESC,rowid DESC""",
                (account_ref, category),
            ).fetchall()
        latest_by_window: dict[tuple[str, str], sqlite3.Row] = {}
        for row in rows:
            latest_by_window.setdefault((str(row["window_start"]), str(row["window_end"])), row)
        ordered = sorted(latest_by_window.values(), key=lambda item: (item["window_start"], item["window_end"]))
        last_complete: str | None = None
        for row in ordered:
            if row["status"] != "COMPLETE":
                break
            last_complete = str(row["window_end"])
        return last_complete

    def read_sync_windows(self, *, account_ref: str, cutoff: str) -> list[dict[str, Any]]:
        with self.read_connection() as connection:
            rows = connection.execute(
                """SELECT payload_json FROM sync_windows
                   WHERE account_ref=? AND retrieved_at<=? AND category<>'LEDGER_METADATA'
                   ORDER BY window_start, category, retrieved_at, rowid""",
                (account_ref, cutoff),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def save_analysis(self, analysis: Mapping[str, Any]) -> None:
        if _contains_sensitive_key(analysis):
            raise PrivateBrokerLedgerError("BROKER_LEDGER_SENSITIVE_FIELD_REJECTED")
        payload_json = _canonical_json(dict(analysis))
        with self._write_connection() as connection:
            connection.execute(
                """INSERT INTO analysis_packages(
                    analysis_id,account_ref,source_id,as_of,retrieved_at,formula_version,
                    ledger_hash,payload_json,content_hash
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    analysis["analysis_id"], analysis["account_ref"], analysis["source_id"],
                    analysis["as_of"], analysis["retrieved_at"], analysis["formula_version"],
                    analysis["ledger_hash"], payload_json, analysis["content_hash"],
                ),
            )

    @staticmethod
    def _current_rows(connection: sqlite3.Connection, table: str, account_ref: str, cutoff: str) -> list[sqlite3.Row]:
        key = "logical_key"
        return connection.execute(
            f"""SELECT current.* FROM {table} AS current
                JOIN (
                    SELECT {key}, MAX(revision) AS revision FROM {table}
                    WHERE account_ref=? AND retrieved_at<=? GROUP BY {key}
                ) latest ON latest.{key}=current.{key} AND latest.revision=current.revision
                ORDER BY current.as_of, current.{key}""",
            (account_ref, cutoff),
        ).fetchall()

    def read_current_activities(self, *, account_ref: str, cutoff: str) -> list[dict[str, Any]]:
        with self.read_connection() as connection:
            rows = self._current_rows(connection, "activity_revisions", account_ref, cutoff)
        result = []
        for row in rows:
            value = json.loads(row["payload_json"])
            value["_ledger"] = {
                "logical_key": row["logical_key"], "revision": row["revision"],
                "content_hash": row["content_hash"], "record_id": row["record_id"],
            }
            result.append(value)
        return result

    def read_current_asset_points(self, *, account_ref: str, cutoff: str) -> list[dict[str, Any]]:
        with self.read_connection() as connection:
            rows = self._current_rows(connection, "asset_points", account_ref, cutoff)
        result = []
        for row in rows:
            value = json.loads(row["payload_json"])
            value["_ledger"] = {
                "logical_key": row["logical_key"], "revision": row["revision"],
                "content_hash": row["content_hash"], "record_id": row["point_id"],
            }
            result.append(value)
        return result

    def latest_analysis(self, *, account_ref: str) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM analysis_packages WHERE account_ref=? ORDER BY retrieved_at DESC, analysis_id DESC LIMIT 1",
                (account_ref,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def analysis(self, *, account_ref: str, analysis_id: str) -> dict[str, Any] | None:
        with self.read_connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM analysis_packages WHERE account_ref=? AND analysis_id=?",
                (account_ref, analysis_id),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_analyses(self, *, account_ref: str) -> list[dict[str, Any]]:
        with self.read_connection() as connection:
            rows = connection.execute(
                """SELECT analysis_id,as_of,retrieved_at,formula_version,ledger_hash,content_hash
                   FROM analysis_packages WHERE account_ref=?
                   ORDER BY as_of DESC,retrieved_at DESC,analysis_id DESC""",
                (account_ref,),
            ).fetchall()
        return [dict(row) for row in rows]

    def ledger_hash(self, *, account_ref: str, cutoff: str) -> str:
        with self.read_connection() as connection:
            activities = self._current_rows(connection, "activity_revisions", account_ref, cutoff)
            assets = self._current_rows(connection, "asset_points", account_ref, cutoff)
            windows = connection.execute(
                "SELECT sync_window_id,content_hash FROM sync_windows WHERE account_ref=? AND retrieved_at<=? ORDER BY sync_window_id",
                (account_ref, cutoff),
            ).fetchall()
        return canonical_hash({
            "account_ref": account_ref,
            "cutoff": cutoff,
            "activities": [(row["logical_key"], row["revision"], row["content_hash"]) for row in activities],
            "asset_points": [(row["logical_key"], row["revision"], row["content_hash"]) for row in assets],
            "sync_windows": [(row["sync_window_id"], row["content_hash"]) for row in windows],
        })
