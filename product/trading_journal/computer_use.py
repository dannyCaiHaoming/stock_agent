"""Bind a sanitized computer-use declaration to a private official export.

This validates file provenance, never whether GUI actions actually occurred.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError, canonical_json, iso_datetime, utc_now
from .normalization import MAX_BYTES, parse_csv
from .privacy import PrivacyError, write_private
from .windows import record_in_window

RECEIPT_FIELDS = frozenset({"receipt_id", "source_id", "as_of", "retrieved_at", "method",
                            "requested_window", "source_timezone", "export_view",
                            "original_source_hash", "actions"})
ACTION_TYPES = frozenset({"OPEN_APP", "NAVIGATE_ACCOUNT", "NAVIGATE_TRADE_HISTORY",
                          "SELECT_TRADE_RECORDS", "SET_DATE_RANGE", "SELECT_MARKET",
                          "SELECT_ASSET_TYPE", "OPEN_READONLY_DETAIL", "NAVIGATE_STATEMENTS",
                          "SELECT_FILL_DETAILS", "EXPORT_CSV", "SAVE_EXPORT"})
MAX_RECEIPT_BYTES = 16 * 1024


def _private_source(path: Path, storage: Path) -> Path:
    sources = storage / "sources"
    if not path.is_absolute() or path.parent != sources:
        raise JournalError("COMPUTER_USE_PRIVATE_SOURCE_REQUIRED", "来源与观察回执必须直接位于已验证的私人 sources。")
    for directory in (storage.parent, storage, sources):
        if directory.is_symlink():
            raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
        if not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) != 0o700:
            raise PrivacyError("JOURNAL_PRIVATE_DIRECTORY_PERMISSION_INVALID")
    if path.is_symlink():
        raise PrivacyError("JOURNAL_SYMLINK_FORBIDDEN")
    return path


def _read_private(path: Path, storage: Path, limit: int, *, missing_code: str) -> bytes:
    path = _private_source(path, storage)
    try:
        flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise JournalError("COMPUTER_USE_SOURCE_INVALID", "只接受无链接的普通私人来源文件。")
            if before.st_size > limit:
                raise JournalError("COMPUTER_USE_SOURCE_LIMIT", "来源或观察回执超过大小预算。")
            os.fchmod(handle.fileno(), 0o600)
            payload = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
            current = path.lstat()
            if (len(payload) > limit or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
                    or before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns):
                raise JournalError("COMPUTER_USE_SOURCE_CHANGED", "读取期间来源发生变化，请重新核验材料。")
            return payload
    except FileNotFoundError as exc:
        raise JournalError(missing_code, "缺少私人来源文件或观察回执。") from exc
    except OSError as exc:
        raise JournalError("COMPUTER_USE_SOURCE_INVALID", "无法安全读取私人来源文件。") from exc


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate key")
        value[key] = item
    return value


def validate_export(storage: Path, input_path: Path, receipt_path: Path, window: dict,
                    source_timezone: str | None = None) -> dict:
    """Validate every receipt field before reading CSV or opening a writable ledger."""
    _private_source(input_path, storage)
    raw = _read_private(receipt_path, storage, MAX_RECEIPT_BYTES,
                        missing_code="COMPUTER_USE_RECEIPT_REQUIRED")
    try:
        receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise JournalError("COMPUTER_USE_RECEIPT_INVALID", "观察回执必须为有限、无重复字段的 JSON。") from exc
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise JournalError("COMPUTER_USE_RECEIPT_FIELDS_INVALID", "观察回执只允许固定脱敏字段。")
    for field, pattern in (("receipt_id", r"computer-use-[a-f0-9]{32}"),
                           ("source_id", r"tiger-computer-use:[a-f0-9]{32}")):
        if not isinstance(receipt[field], str) or not re.fullmatch(pattern, receipt[field]):
            raise JournalError("COMPUTER_USE_RECEIPT_ID_INVALID", "观察回执必须使用随机、不含私人身份的引用。")
    if (receipt["method"] != "CODEX_COMPUTER_USE_EXPORT"
            or receipt["export_view"] not in {"trade_records", "account_statement"}):
        raise JournalError("COMPUTER_USE_RECEIPT_METHOD_INVALID", "观察回执必须声明已核验的 computer-use 正式导出视图。")
    if not isinstance(receipt["requested_window"], dict) or canonical_json(receipt["requested_window"]) != canonical_json(window):
        raise JournalError("COMPUTER_USE_WINDOW_CONFLICT", "观察回执与用户所选的完整期间不一致。")
    try:
        for field in ("as_of", "retrieved_at"):
            if not isinstance(receipt[field], str) or len(receipt[field]) > 40:
                raise ValueError("time")
        as_of, retrieved = iso_datetime(receipt["as_of"]), iso_datetime(receipt["retrieved_at"])
        if as_of != iso_datetime(window["end"]) or retrieved < as_of or retrieved > iso_datetime(utc_now()):
            raise ValueError("time")
    except (JournalError, ValueError) as exc:
        raise JournalError("COMPUTER_USE_RECEIPT_TIME_INVALID", "观察回执的截止或取得时间无效。") from exc
    zone = receipt["source_timezone"]
    try:
        if not isinstance(zone, str) or len(zone) > 80:
            raise ValueError("timezone")
        if zone == "PER_ROW":
            if receipt["export_view"] != "account_statement":
                raise ValueError("per-row timezone requires a verified statement")
        else:
            ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise JournalError("COMPUTER_USE_TIMEZONE_INVALID", "观察回执需要可靠的来源时区。") from exc
    if source_timezone is not None and source_timezone != zone:
        raise JournalError("COMPUTER_USE_TIMEZONE_CONFLICT", "导入来源时区与观察回执不一致。")
    actions = receipt["actions"]
    if (not isinstance(actions, list) or not 1 <= len(actions) <= 32
            or any(not isinstance(action, str) or action not in ACTION_TYPES for action in actions)
            or not {"EXPORT_CSV", "SAVE_EXPORT"}.issubset(actions)):
        raise JournalError("COMPUTER_USE_ACTIONS_INVALID", "观察回执只能声明有限的只读导航与正式导出动作。")
    if receipt["export_view"] == "account_statement" and not {
            "NAVIGATE_STATEMENTS", "SELECT_FILL_DETAILS"}.issubset(actions):
        raise JournalError("COMPUTER_USE_ACTIONS_INVALID", "逐笔账单需要声明已打开账单并选择逐笔成交。")
    digest = receipt["original_source_hash"]
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise JournalError("COMPUTER_USE_HASH_INVALID", "观察回执需要原始导出 SHA-256。")
    payload = _read_private(input_path, storage, MAX_BYTES, missing_code="IMPORT_SOURCE_INVALID")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise JournalError("COMPUTER_USE_HASH_CONFLICT", "导出文件与观察回执的 hash 不一致。")
    destination = storage / "sources" / (receipt["receipt_id"] + ".json")
    if destination.exists() or destination.is_symlink():
        existing = _read_private(destination, storage, MAX_RECEIPT_BYTES,
                                 missing_code="COMPUTER_USE_RECEIPT_REQUIRED")
        if existing != raw:
            raise JournalError("COMPUTER_USE_RECEIPT_ID_CONFLICT", "观察回执引用已绑定其他材料。")
    return {"receipt": receipt, "payload": payload, "receipt_path": destination,
            "receipt_bytes": raw, "receipt_hash": hashlib.sha256(raw).hexdigest(), "source_hash": digest}


def parse_export(prepared: dict, storage: Path, *, account_ref: str,
                 exchange_timezone: str | None = None, activity_type: str | None = None) -> list[dict]:
    """Parse a frozen private copy so validation and parsing share exact bytes."""
    receipt = prepared["receipt"]
    if receipt["export_view"] == "account_statement":
        from .statement import is_statement
        if not is_statement(prepared["payload"]):
            raise JournalError("COMPUTER_USE_STATEMENT_REQUIRED", "账单观察回执需要匹配正式多区段账单。")
    with tempfile.TemporaryDirectory(prefix=".computer-use-", dir=storage / "sources") as temporary:
        path = Path(temporary) / "export.csv"
        write_private(path, prepared["payload"])
        records = parse_csv(path, account_ref=account_ref, source_id=receipt["source_id"],
                            as_of=receipt["as_of"], retrieved_at=receipt["retrieved_at"],
                            source_timezone=receipt["source_timezone"],
                            exchange_timezone=exchange_timezone, activity_type=activity_type)
    if receipt["source_timezone"] == "PER_ROW":
        for record in records:
            try:
                ZoneInfo(record["source_timezone"])
            except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
                raise JournalError("COMPUTER_USE_TIMEZONE_CONFLICT", "账单逐笔记录必须声明明确来源时区。") from exc
    elif any(record["source_timezone"] != receipt["source_timezone"] for record in records):
        raise JournalError("COMPUTER_USE_TIMEZONE_CONFLICT", "导出行声明的来源时区与观察回执不一致。")
    return [record for record in records if record_in_window(record, receipt["requested_window"])]


def persist_receipt(prepared: dict) -> dict:
    receipt = prepared["receipt"]
    path = prepared["receipt_path"]
    storage = path.parent.parent
    frozen_source = path.parent / (prepared["source_hash"] + ".csv")
    receipt_exists = path.exists() or path.is_symlink()
    if receipt_exists:
        existing = _read_private(path, storage, MAX_RECEIPT_BYTES,
                                 missing_code="COMPUTER_USE_RECEIPT_REQUIRED")
        if existing != prepared["receipt_bytes"]:
            raise JournalError("COMPUTER_USE_RECEIPT_ID_CONFLICT", "观察回执引用已绑定其他材料。")
    source_exists = frozen_source.exists() or frozen_source.is_symlink()
    if source_exists:
        existing = _read_private(frozen_source, storage, MAX_BYTES, missing_code="IMPORT_SOURCE_INVALID")
        if existing != prepared["payload"]:
            raise JournalError("COMPUTER_USE_HASH_CONFLICT", "冻结来源引用已绑定其他材料。")
    # All binding and parsing checks have passed; never replace an old source.
    if not source_exists:
        write_private(frozen_source, prepared["payload"])
    if not receipt_exists:
        write_private(path, prepared["receipt_bytes"])
    return {"source_id": receipt["source_id"], "as_of": receipt["as_of"],
            "retrieved_at": receipt["retrieved_at"], "window": receipt["requested_window"],
            "source_hash": prepared["source_hash"], "receipt_id": receipt["receipt_id"],
            "receipt_hash": prepared["receipt_hash"],
            "actions": [{"action": action} for action in receipt["actions"]]}
