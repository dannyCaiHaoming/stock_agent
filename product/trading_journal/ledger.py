"""A private SQLite ledger with append-only revisions and immutable snapshots."""

from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from .common import JournalError, canonical_hash, canonical_json, decimal_string, decimal_value, iso_datetime, utc_now
from .normalization import ACTIVITY_TYPES
from .windows import record_in_window, window_membership

_PROVENANCE = frozenset({"source_id", "as_of", "retrieved_at", "source_hash", "source_location", "record_hash", "revision", "duplicate_candidate", "identity_status"})
_RECORD_FIELDS = frozenset({"record_id", "source_record_id", "activity_type", "account_ref", "instrument", "side", "quantity", "price", "fees", "amount", "fees_complete", "currency", "position_effect", "occurred_at", "time_precision", "source_timezone", "source_id", "as_of", "retrieved_at", "source_hash", "source_location", "order_id", "status", "related_source_record_id", "identity_status", "record_hash", "revision", "duplicate_candidate"})
_INSTRUMENT_FIELDS = frozenset({"key", "symbol", "asset_type", "market", "currency", "exchange_timezone", "underlying", "expiry", "strike", "right", "multiplier", "adjustment_status", "security_id", "unknown_fields"})


def _semantic_hash(record: dict) -> str:
    return canonical_hash({key: value for key, value in record.items() if key not in _PROVENANCE})


def _economic_hash(record: dict) -> str:
    value = {key: record.get(key) for key in ("account_ref", "activity_type", "side", "quantity", "price", "currency", "occurred_at", "time_precision", "position_effect")}
    if record.get("activity_type") != "FILL":
        value["amount"] = record.get("amount")
    for field in ("quantity", "price", "amount"):
        if field in value:
            value[field] = decimal_string(decimal_value(value[field], nullable=True))
    value["instrument_key"] = record.get("instrument", {}).get("key")
    return canonical_hash(value)


def _validate_record(record: dict) -> None:
    if not isinstance(record, dict) or set(record) - _RECORD_FIELDS:
        raise JournalError("RECORD_FIELDS_NOT_ALLOWED", "记录包含不允许传入私人账本的字段。")
    instrument = record.get("instrument")
    if not isinstance(instrument, dict) or set(instrument) - _INSTRUMENT_FIELDS:
        raise JournalError("INSTRUMENT_FIELDS_NOT_ALLOWED", "证券身份包含未允许字段。")
    for field in ("record_id", "account_ref", "source_id"):
        value = record.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{3,160}", value):
            raise JournalError("INVALID_RECORD_IDENTITY", "记录必须包含非私人路径的稳定引用。")
    if re.fullmatch(r"\d+", record["account_ref"]):
        raise JournalError("OPAQUE_ACCOUNT_REF_REQUIRED", "账户必须使用随机本地引用。")
    iso_datetime(record.get("as_of"))
    iso_datetime(record.get("retrieved_at"))
    if record.get("activity_type") not in ACTIVITY_TYPES:
        raise JournalError("UNKNOWN_ACTIVITY_TYPE", "记录经济活动类型未验证。")
    if record.get("time_precision") not in {"SECOND", "MINUTE", "DATE"}:
        raise JournalError("INVALID_TIME_PRECISION", "记录时间精度未声明。")
    occurred = record.get("occurred_at")
    if record["time_precision"] == "DATE":
        try:
            date.fromisoformat(occurred)
        except (ValueError, TypeError) as exc:
            raise JournalError("INVALID_TIME", "日期精度记录必须保留来源日期。") from exc
    else:
        iso_datetime(occurred)
    if record.get("activity_type") == "FILL":
        if record.get("side") not in {"BUY", "SELL"}:
            raise JournalError("INVALID_SIDE", "逐笔成交需要来源买卖方向。")
        if decimal_value(record.get("quantity"), field="quantity") <= 0 or decimal_value(record.get("price"), field="price") < 0:
            raise JournalError("INVALID_EXECUTION_NUMBER", "逐笔数量或价格无效。")
    decimal_value(record.get("fees"), field="fees", nullable=True)
    decimal_value(record.get("amount"), field="amount", nullable=True)
    if not instrument.get("key"):
        raise JournalError("INSTRUMENT_KEY_REQUIRED", "证券稳定分组身份不能为空。")
    if record.get("currency") != instrument.get("currency"):
        raise JournalError("CURRENCY_CONFLICT", "成交与证券币种冲突。")


def _normalise_coverage(coverage: dict | None, records: list[dict], requested: dict | None, mode: str) -> dict:
    supplied = deepcopy(coverage or {})
    collection_receipt = supplied.get("collection_receipt")
    if collection_receipt is not None:
        receipt_fields = {"receipt_id", "content_hash", "source_id", "as_of", "retrieved_at", "original_source_hash", "normalized_csv_hash"}
        if not isinstance(collection_receipt, dict) or set(collection_receipt) != receipt_fields:
            raise JournalError("COLLECTION_RECEIPT_FIELDS_INVALID", "采集来源回执只能包含已允许的非私人路径字段。")
        for field in ("receipt_id", "source_id"):
            if not isinstance(collection_receipt[field], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{3,160}", collection_receipt[field]):
                raise JournalError("COLLECTION_RECEIPT_ID_INVALID", "采集来源回执必须包含稳定、非私人路径引用。")
        for field in ("content_hash", "original_source_hash", "normalized_csv_hash"):
            if not isinstance(collection_receipt[field], str) or not re.fullmatch(r"[a-f0-9]{64}", collection_receipt[field]):
                raise JournalError("COLLECTION_RECEIPT_HASH_INVALID", "采集来源回执必须包含合法 SHA-256 hash。")
        iso_datetime(collection_receipt["as_of"])
        iso_datetime(collection_receipt["retrieved_at"])
        collection_receipt = {field: collection_receipt[field] for field in receipt_fields}
    observed_assets = sorted({record.get("instrument", {}).get("asset_type") or "UNKNOWN" for record in records})
    required = {"STOCK", "ETF", "OPTION"}
    actual = [record["occurred_at"] for record in records]
    gaps = list(supplied.get("gaps") or [])
    if not records:
        gaps.append({"code": "NO_ROWS_UNPROVEN", "message": "空来源不能证明完整覆盖。"})
    category_fields = {"status", "termination_proven", "reconciled", "expected_rows", "observed_rows", "source_id", "start", "end"}
    categories = {key: {field: value for field, value in item.items() if field in category_fields}
                  for key, item in (supplied.get("categories") or {}).items() if key in required and isinstance(item, dict)}
    actual_counts = {asset: sum(record.get("instrument", {}).get("asset_type") == asset for record in records) for asset in required}
    # A source is complete only with independent termination and reconciliation,
    # not because a caller passed a desired status or an empty successful query.
    complete_categories = {asset for asset, info in categories.items() if isinstance(info, dict)
                           and info.get("status") == "COMPLETE" and info.get("termination_proven") is True
                           and info.get("reconciled") is True and isinstance(info.get("expected_rows"), int)
                           and info.get("expected_rows") == info.get("observed_rows") == actual_counts.get(asset)}
    for asset in sorted(required - complete_categories):
        gaps.append({"code": "ASSET_COVERAGE_UNPROVEN", "asset_type": asset, "message": "该类别期间完整性尚未核验。"})
    segment_fields = {"start", "end", "termination_proven", "reconciled", "source_id", "row_count", "page_count"}
    segments = [{key: value for key, value in segment.items() if key in segment_fields}
                for segment in supplied.get("segments", []) if isinstance(segment, dict)]
    segment_proven = bool(segments) and all(
        isinstance(segment, dict) and segment.get("termination_proven") is True
        and segment.get("reconciled") is True for segment in segments)
    continuous = False
    if segment_proven and requested and requested.get("start") and requested.get("end"):
        try:
            intervals = sorted((iso_datetime(item["start"]), iso_datetime(item["end"])) for item in segments)
            cursor = iso_datetime(requested["start"])
            continuous = all(left <= right for left, right in intervals)
            for left, right in intervals:
                if left > cursor + timedelta(microseconds=1):
                    continuous = False
                    break
                cursor = max(cursor, right)
            continuous = continuous and cursor >= iso_datetime(requested["end"])
        except (JournalError, KeyError, TypeError):
            continuous = False
    if not continuous:
        gaps.append({"code": "SEGMENT_RANGE_UNPROVEN", "message": "查询分段尚未证明连续覆盖请求期间。"})
    window_proven = bool(requested and requested.get("start") and requested.get("end")
                         and supplied.get("requested_range_reconciled") is True and segment_proven and continuous)
    status = "SOURCE_COMPLETE_FOR_WINDOW" if records and required <= complete_categories and window_proven and not supplied.get("gaps") else "PARTIAL"
    lifetime_proof = supplied.get("lifetime_proof") or {}
    lifetime_months_proven = False
    if requested and requested.get("start") and requested.get("end"):
        from zoneinfo import ZoneInfo
        try:
            zone = ZoneInfo(requested.get("timezone") or "Asia/Shanghai")
            start_day = iso_datetime(requested["start"]).astimezone(zone).date()
            end_day = iso_datetime(requested["end"]).astimezone(zone).date()
            months = set()
            year, month = start_day.year, start_day.month
            while (year, month) <= (end_day.year, end_day.month):
                months.add(f"{year:04}-{month:02}")
                year, zero_month = divmod(year * 12 + month, 12)
                month = zero_month + 1
            monthly = lifetime_proof.get("monthly_reconciliation") or []
            reconciled_months = {
                item.get("month") for item in monthly if isinstance(item, dict)
                and item.get("statement_source_id")
                and re.fullmatch(r"[a-f0-9]{64}", item.get("statement_hash") or "")
                and isinstance(item.get("expected_rows"), int) and item.get("expected_rows") >= 0
                and item.get("observed_rows") == item.get("expected_rows")
                and item.get("quantity_reconciled") is True
                and set(item.get("reconciled_categories") or []) >= required
            }
            opened = lifetime_proof.get("official_opened_at")
            opened_day = (date.fromisoformat(opened) if isinstance(opened, str) and len(opened) == 10
                          else iso_datetime(opened).astimezone(zone).date()) if opened else None
            lifetime_months_proven = months <= reconciled_months and opened_day == start_day
        except (JournalError, ValueError, TypeError):
            lifetime_months_proven = False
    if (status == "SOURCE_COMPLETE_FOR_WINDOW" and requested.get("preset") == "lifetime"
            and requested.get("account_opened_at_known") is True
            and lifetime_proof.get("official_opening_source_id")
            and lifetime_months_proven
            and lifetime_proof.get("lifecycle_reconciled") is True):
        status = "LIFETIME_RECONCILED"
    elif requested and requested.get("preset") == "lifetime":
        gaps.append({"code": "LIFETIME_UNPROVEN", "message": "开户起点、月份或生命周期未完全勾稽。"})
    return {
        "status": status, "request": deepcopy(requested), "actual_start": min(actual) if actual else None,
        "actual_end": max(actual) if actual else None, "observed_assets": observed_assets,
        "categories": categories, "segments": segments, "gaps": gaps,
        "collection_mode": mode, "automatic_client_collection": mode == "VERIFIED_DESKTOP",
        "source_id": supplied.get("source_id") or (records[0]["source_id"] if records else "source-empty-batch"),
        "as_of": supplied.get("as_of") or (records[0]["as_of"] if records else utc_now()),
        "retrieved_at": supplied.get("retrieved_at") or (records[0]["retrieved_at"] if records else utc_now()),
        "account_opened_at_known": bool(requested and requested.get("account_opened_at_known")),
        "collection_receipt": collection_receipt,
        "lifetime_proof": ({key: value for key, value in lifetime_proof.items()
                            if key in {"official_opening_source_id", "official_opened_at", "monthly_reconciliation", "lifecycle_reconciled"}}
                           if requested and requested.get("preset") == "lifetime" else None),
    }


class Ledger:
    """root is supplied by the independently validated privacy boundary.

    No discovery from cwd, code location, plugin cache, or broker database.
    """

    def __init__(self, root: Path, *, read_only: bool = False):
        self.root = Path(root)
        self.read_only = read_only
        self._atomic_depth = 0
        if not self.root.is_absolute() or self.root.is_symlink():
            raise JournalError("PRIVATE_ROOT_REQUIRED", "账本需要已验证的绝对私人目录。")
        if not self.root.is_dir():
            if self.read_only and not self.root.exists():
                raise JournalError("JOURNAL_NOT_INITIALIZED", "尚无保存的交易账本；请先采集。")
            raise JournalError("PRIVATE_ROOT_REQUIRED", "账本需要已验证的绝对私人目录。")
        self.path = self.root / "journal.sqlite"
        if self.path.is_symlink():
            raise JournalError("PRIVATE_PATH_SYMLINK", "账本路径不能为符号链接。")
        if not self.path.exists():
            if self.read_only:
                raise JournalError("JOURNAL_NOT_INITIALIZED", "尚无保存的交易账本；请先采集。")
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        if self.path.stat().st_mode & 0o077:
            raise JournalError("PRIVATE_FILE_PERMISSION", "账本文件必须为本机私人权限。")
        if self.read_only:
            self._open_read_only()
            return
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = DELETE")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS batches (
                batch_id TEXT PRIMARY KEY, account_ref TEXT, created_at TEXT NOT NULL,
                status TEXT NOT NULL, source_hash TEXT, receipt_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT NOT NULL, revision INTEGER NOT NULL, record_hash TEXT NOT NULL,
                economic_hash TEXT NOT NULL, account_ref TEXT NOT NULL, batch_id TEXT NOT NULL,
                payload_json TEXT NOT NULL, PRIMARY KEY(record_id, revision),
                FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
            );
            CREATE INDEX IF NOT EXISTS records_account ON records(account_ref);
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY, account_ref TEXT NOT NULL, input_hash TEXT NOT NULL,
                created_at TEXT NOT NULL, payload_json TEXT NOT NULL
            );
        """)
        self._db.commit()

    def _open_read_only(self) -> None:
        # The journal writer always uses DELETE mode. Reject foreign WAL files
        # rather than let SQLite create writable shared-memory sidecars or read
        # stale data via immutable=1 while a writer is active.
        with self.path.open("rb") as handle:
            header = handle.read(20)
        if len(header) < 20:
            raise JournalError("JOURNAL_NOT_INITIALIZED", "交易账本尚未完成初始化。")
        if header[:16] == b"SQLite format 3\x00" and (header[18] == 2 or header[19] == 2):
            raise JournalError("JOURNAL_READ_ONLY_WAL_UNSUPPORTED", "该账本使用非本模块的 WAL 模式；只读查看不会创建共享内存或迁移账本。")
        try:
            self._db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA query_only = ON")
            # Reading never initializes or migrates an older/unrecognized schema.
            required_columns = {
                "batches": {"batch_id", "account_ref", "created_at", "status", "source_hash", "receipt_json"},
                "records": {"record_id", "revision", "record_hash", "economic_hash", "account_ref", "batch_id", "payload_json"},
                "snapshots": {"snapshot_id", "account_ref", "input_hash", "created_at", "payload_json"},
            }
            for table, expected in required_columns.items():
                observed = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}
                if not expected <= observed:
                    raise JournalError("JOURNAL_SCHEMA_UNSUPPORTED", "现有账本结构不匹配；只读查看不会初始化或迁移它。")
        except (sqlite3.Error, JournalError) as exc:
            if hasattr(self, "_db"):
                self._db.close()
            if isinstance(exc, JournalError):
                raise
            raise JournalError("JOURNAL_UNREADABLE", "现有账本无法只读打开；没有修改任何账本文件。") from exc

    def _require_write(self) -> None:
        if self.read_only:
            raise JournalError("JOURNAL_READ_ONLY", "只读账本不能导入、记录失败批次或创建冻结版本。")

    @contextmanager
    def _transaction(self):
        """Respect a caller's explicit transaction instead of committing it."""
        if self._atomic_depth:
            yield
        else:
            with self._db:
                yield

    @contextmanager
    def atomic_write(self, *, on_failure=None):
        """Keep records and their new snapshot in one exclusive write unit.

        Legacy individual operations retain their existing commit behavior.
        A workspace update holds this lock through admission and freeze, so a
        failed freeze cannot leave a successful partial import behind.
        """
        self._require_write()
        if self._atomic_depth:
            self._atomic_depth += 1
            try:
                yield self
            except BaseException:
                if on_failure:
                    on_failure()
                raise
            finally:
                self._atomic_depth -= 1
            return
        self._db.execute("BEGIN IMMEDIATE")
        self._atomic_depth = 1
        try:
            yield self
            self._db.commit()
        except BaseException:
            # Caller-owned new source cleanup must happen before releasing
            # this write lock, or another importer could adopt that source.
            try:
                if on_failure:
                    on_failure()
            finally:
                self._db.rollback()
            raise
        finally:
            self._atomic_depth = 0

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def record_failed_batch(self, code: str, *, account_ref: str | None = None, source_hash: str | None = None) -> dict:
        """Store a stable failure code, never the raw parse error or source row."""
        self._require_write()
        if not re.fullmatch(r"[A-Z0-9_]{1,100}", code):
            code = "BATCH_FAILED"
        receipt = {"batch_id": "batch-" + uuid4().hex, "status": "FAILED", "code": code,
                   "account_ref": account_ref, "source_hash": source_hash, "retrieved_at": utc_now()}
        with self._transaction():
            self._db.execute("INSERT INTO batches VALUES (?, ?, ?, ?, ?, ?)",
                             (receipt["batch_id"], account_ref, receipt["retrieved_at"], "FAILED", source_hash, canonical_json(receipt)))
        return receipt

    def import_records(self, records: list[dict], *, coverage: dict | None = None,
                       source_hash: str | None = None, requested_window: dict | None = None,
                       mode: str = "USER_ASSISTED") -> dict:
        self._require_write()
        if mode not in {"USER_ASSISTED", "VERIFIED_DESKTOP", "COMPUTER_USE_EXPORT", "SYNTHETIC"}:
            raise JournalError("INVALID_COLLECTION_MODE", "采集模式未验证。")
        computer_coverage = None
        if mode == "COMPUTER_USE_EXPORT":
            if not isinstance(coverage, dict) or coverage.get("collection_receipt") is None:
                raise JournalError("COMPUTER_USE_RECEIPT_REQUIRED", "computer-use 来源必须绑定已验证的私人观察回执。")
            if not isinstance(records, list):
                raise JournalError("INVALID_RECORDS", "导入必须为记录列表。")
            if not records:
                raise JournalError("NO_RECORDS_IN_WINDOW", "导出没有可准入所选窗口的交易，不能证明完整空历史。")
            for record in records:
                _validate_record(record)
            # Invalid provenance must not even append a failed batch.
            computer_coverage = _normalise_coverage(coverage, records, requested_window, mode)
            lineage = computer_coverage["collection_receipt"]
            if (not requested_window or iso_datetime(lineage["as_of"]) != iso_datetime(requested_window["end"])
                    or lineage["original_source_hash"] != source_hash
                    or lineage["normalized_csv_hash"] != source_hash
                    or any(record.get("source_hash") != source_hash
                           or record.get("source_id") != lineage["source_id"]
                           or iso_datetime(record.get("as_of")) != iso_datetime(lineage["as_of"])
                           or iso_datetime(record.get("retrieved_at")) != iso_datetime(lineage["retrieved_at"])
                           for record in records)):
                raise JournalError("COMPUTER_USE_LINEAGE_CONFLICT", "computer-use 来源与回执引用不一致。")
        try:
            if not isinstance(records, list):
                raise JournalError("INVALID_RECORDS", "导入必须为记录列表。")
            for record in records:
                _validate_record(record)
            accounts = {record["account_ref"] for record in records}
            if len(accounts) > 1:
                raise JournalError("ACCOUNT_BATCH_MIXED", "一次导入不能混合账户。")
            account_ref = next(iter(accounts), None)
            if len({record["record_id"] for record in records}) != len(records):
                raise JournalError("SOURCE_ID_COLLISION", "同一批来源活动身份重复或冲突；未覆盖任何记录。")
            verified_coverage = computer_coverage or _normalise_coverage(coverage, records, requested_window, mode)
            batch_id, created = "batch-" + uuid4().hex, utc_now()
            receipt = {"batch_id": batch_id, "status": "SAVED", "account_ref": account_ref,
                       "inserted": 0, "revised": 0, "unchanged": 0, "coverage": verified_coverage,
                       "source_hash": source_hash, "source_id": verified_coverage["source_id"],
                       "as_of": verified_coverage["as_of"], "retrieved_at": created}
            with self._transaction():
                self._db.execute("INSERT INTO batches VALUES (?, ?, ?, ?, ?, ?)", (batch_id, account_ref, created, "SAVED", source_hash, "{}"))
                for record in records:
                    previous = self._db.execute("SELECT revision, record_hash, account_ref FROM records WHERE record_id = ? ORDER BY revision DESC LIMIT 1", (record["record_id"],)).fetchone()
                    record_hash = _semantic_hash(record)
                    if previous and previous["account_ref"] != record["account_ref"]:
                        raise JournalError("RECORD_ACCOUNT_CONFLICT", "来源身份与已保存账户不一致。")
                    if previous and previous["record_hash"] == record_hash:
                        receipt["unchanged"] += 1
                        continue
                    revision = previous["revision"] + 1 if previous else 1
                    stored = deepcopy(record)
                    stored.update(revision=revision, record_hash=record_hash)
                    self._db.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?)",
                                     (stored["record_id"], revision, record_hash, _economic_hash(record), record["account_ref"], batch_id, canonical_json(stored)))
                    receipt["revised" if previous else "inserted"] += 1
                self._db.execute("UPDATE batches SET receipt_json = ? WHERE batch_id = ?", (canonical_json(receipt), batch_id))
            return receipt
        except JournalError as exc:
            self.record_failed_batch(exc.code, source_hash=source_hash)
            raise
        except sqlite3.Error as exc:
            self.record_failed_batch("SQLITE_BATCH_FAILED", source_hash=source_hash)
            raise JournalError("SQLITE_BATCH_FAILED", "账本事务失败，成功历史保持不变。") from exc

    def current_records(self, account_ref: str, *, cutoff: str | None = None) -> list[dict]:
        rows = self._db.execute("SELECT r.payload_json FROM records r JOIN (SELECT record_id, MAX(revision) revision FROM records WHERE account_ref = ? GROUP BY record_id) c ON r.record_id = c.record_id AND r.revision = c.revision ORDER BY r.record_id", (account_ref,)).fetchall()
        values = [json.loads(row["payload_json"]) for row in rows]
        if cutoff:
            # cutoff is business-time scope, not an attempt to rewrite historical
            # revisions. The exact prior revision is preserved by a snapshot.
            values = [record for record in values if record_in_window(record, {"end": cutoff})]
        groups: dict[str, list[dict]] = {}
        for record in values:
            groups.setdefault(_economic_hash(record), []).append(record)
        for candidates in groups.values():
            files = {record.get("source_hash") for record in candidates}
            ambiguous = len(candidates) > 1 and len(files) > 1 and any(not record.get("source_record_id") for record in candidates)
            for record in candidates:
                record["duplicate_candidate"] = ambiguous
        return sorted(values, key=lambda record: (record["occurred_at"], record["record_id"]))

    def revisions(self, record_id: str) -> list[dict]:
        return [json.loads(row["payload_json"]) for row in self._db.execute("SELECT payload_json FROM records WHERE record_id = ? ORDER BY revision", (record_id,))]

    def batches(self, account_ref: str | None = None) -> list[dict]:
        if account_ref:
            rows = self._db.execute("SELECT receipt_json FROM batches WHERE account_ref = ? ORDER BY rowid", (account_ref,))
        else:
            rows = self._db.execute("SELECT receipt_json FROM batches ORDER BY rowid")
        return [json.loads(row["receipt_json"]) for row in rows]

    def accounts(self) -> list[str]:
        return [row[0] for row in self._db.execute("SELECT DISTINCT account_ref FROM records ORDER BY account_ref")]

    def freeze_snapshot(self, account_ref: str, *, window: dict | None = None,
                        market: list[dict] | None = None, opening_positions: dict | None = None) -> dict:
        self._require_write()
        snapshot = self.build_snapshot(account_ref, window=window, market=market,
                                       opening_positions=opening_positions)
        with self._transaction():
            self._db.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
                             (snapshot["snapshot_id"], account_ref, snapshot["input_hash"],
                              snapshot["retrieved_at"], canonical_json(snapshot)))
        return snapshot

    def build_snapshot(self, account_ref: str, *, window: dict | None = None,
                       market: list[dict] | None = None, opening_positions: dict | None = None) -> dict:
        """Construct the same full-input view without writing a snapshot row.

        Persistent workspaces use this with a request-local read-only connection
        when newer records do not yet have a matching full-history snapshot.
        """
        from .analysis import analyze_records
        all_records = self.current_records(account_ref)
        records = [record for record in all_records if record_in_window(record, window)]
        if not all_records:
            raise JournalError("JOURNAL_EMPTY", "该账户尚无保存的交易；请先采集。")
        receipts = [receipt for receipt in self.batches(account_ref) if receipt.get("status") == "SAVED"]
        observations = [receipt["coverage"] for receipt in receipts]
        # Full-history read exposes every observation and gap, not just last batch.
        latest_observations = {}
        for item in observations:
            latest_observations[canonical_hash(item.get("request"))] = item
        active_observations = list(latest_observations.values())
        latest_business_time = max(record["occurred_at"] for record in all_records)
        proven_lifetime = any(item.get("status") == "LIFETIME_RECONCILED"
                              and record_in_window({"occurred_at": latest_business_time,
                                                    "time_precision": "DATE" if len(latest_business_time) == 10 else "SECOND"},
                                                   {"end": item["request"]["end"]}) for item in active_observations)
        coverage = {
            "status": "LIFETIME_RECONCILED" if proven_lifetime else "PARTIAL",
            "observations": observations, "gaps": [gap for item in active_observations for gap in item.get("gaps", [])],
            "requested_window": deepcopy(window), "record_count": len(records), "all_saved_record_count": len(all_records),
        }
        if window and coverage["status"] != "LIFETIME_RECONCILED":
            matching = [item for item in observations if item.get("request") == window]
            if matching and matching[-1].get("status") == "SOURCE_COMPLETE_FOR_WINDOW":
                coverage["status"] = "SOURCE_COMPLETE_FOR_WINDOW"
        created = utc_now()
        source_id = "journal-source-" + canonical_hash({"account_ref": account_ref, "records": all_records})
        coverage.update(source_id=source_id, as_of=created, retrieved_at=created)
        uncertain_boundaries = [record["record_id"] for record in records if window_membership(record, window) == "BOUNDARY_UNCERTAIN"]
        if uncertain_boundaries:
            coverage["gaps"].append({"code": "WINDOW_BOUNDARY_TIME_UNCERTAIN", "record_ids": uncertain_boundaries,
                                     "message": "日期精度成交位于日内窗口边界，仅保留为期间归属不确定的事实。"})
        analysis = analyze_records(all_records, window=window, opening_positions=opening_positions,
                                   history_complete=coverage["status"] == "LIFETIME_RECONCILED")
        related_fees = {item["fee_record_id"] for item in analysis.get("fee_record_refs", [])}
        visible_ids = {record["record_id"] for record in records}
        context_records = [record for record in all_records if record["record_id"] not in visible_ids
                           and (not window or record_in_window(record, {"end": window.get("end"), "timezone": window.get("timezone")})
                                or record["record_id"] in related_fees)]
        inputs = {"records": records, "context_records": context_records, "opening_positions": deepcopy(opening_positions or {}),
                  "coverage": coverage, "analysis": analysis, "market": deepcopy(market or [])}
        snapshot = {"kind": "TradeJournalSnapshot", "schema_version": "1.0.0", "snapshot_id": "snapshot-" + uuid4().hex,
                    "account_ref": account_ref, "source_id": source_id, "as_of": created, "retrieved_at": created,
                    **inputs, "input_hash": canonical_hash(inputs)}
        return snapshot

    def load_snapshot(self, snapshot_id: str) -> dict:
        row = self._db.execute("SELECT payload_json FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise JournalError("SNAPSHOT_NOT_FOUND", "冻结账本版本不存在。")
        result = json.loads(row["payload_json"])
        if result["input_hash"] != canonical_hash({key: result[key] for key in ("records", "context_records", "opening_positions", "coverage", "analysis", "market")}):
            raise JournalError("SNAPSHOT_HASH_MISMATCH", "冻结账本版本内容校验失败。")
        return result

    def derive_snapshot(self, snapshot_id: str, market: list[dict]) -> dict:
        """Attach newly frozen market data to the exact original ledger version.

        Reading the current ledger here would silently exchange historical
        revisions underneath an existing chart or report, so this path reads
        only the named parent snapshot and preserves all non-market inputs.
        """
        self._require_write()
        if not isinstance(market, list) or not all(isinstance(item, dict) for item in market):
            raise JournalError("INVALID_MARKET_INPUT", "冻结行情必须是资料包列表。")
        parent = self.load_snapshot(snapshot_id)
        result = deepcopy(parent)
        result.update(snapshot_id="snapshot-" + uuid4().hex, parent_snapshot_id=parent["snapshot_id"],
                      parent_input_hash=parent["input_hash"], retrieved_at=utc_now(), market=deepcopy(market))
        result["input_hash"] = canonical_hash({key: result[key] for key in ("records", "context_records", "opening_positions", "coverage", "analysis", "market")})
        with self._transaction():
            self._db.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
                             (result["snapshot_id"], result["account_ref"], result["input_hash"], result["retrieved_at"], canonical_json(result)))
        return result

    def snapshots(self, account_ref: str | None = None) -> list[dict]:
        query = "SELECT snapshot_id, account_ref, input_hash, created_at FROM snapshots"
        params = ()
        if account_ref:
            query += " WHERE account_ref = ?"
            params = (account_ref,)
        return [dict(row) for row in self._db.execute(query + " ORDER BY rowid", params)]


TradeJournalLedger = Ledger
