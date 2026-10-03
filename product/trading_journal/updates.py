"""Bounded deterministic updates for the local journal workspace.

Every operation opens its own SQLite connection. No broker, model, arbitrary
file path or URL is reachable from this interface.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import hashlib
import os
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError, canonical_hash, decimal_value, iso_datetime, utc_now
from .ledger import Ledger, _validate_record
from .market import fetch_market
from .normalization import MAX_BYTES, parse_csv
from .privacy import assert_real_write_ready, private_root, write_private
from .windows import record_in_window, resolve_window

MAX_MARKET_SYMBOLS = 128
MAX_MARKET_REQUESTS = 120
MAX_REQUESTS_PER_SYMBOL = 24


def _symbol_key(value: dict) -> tuple:
    symbol = value.get("underlying") if value.get("asset_type") == "OPTION" else value.get("symbol")
    market = str(value.get("market") or "UNKNOWN").upper()
    symbol = str(symbol or "").upper()
    if market in {"HK", "HONG_KONG", "HKEX"} and symbol.isdigit():
        symbol = str(int(symbol)).zfill(4) + ".HK"
    return market, value.get("currency"), symbol


def _records_key(records: list[dict]) -> str:
    # Snapshot records already carry revision identity; ignore the read-time
    # duplicate hint because it can change after another source is appended.
    return canonical_hash([{key: item for key, item in record.items() if key != "duplicate_candidate"}
                           for record in sorted(records, key=lambda item: item["record_id"])])


def _exchange_day(record: dict) -> date:
    if record.get("time_precision") == "DATE" or len(record["occurred_at"]) == 10:
        return date.fromisoformat(record["occurred_at"])
    zone = record.get("instrument", {}).get("exchange_timezone") or record.get("source_timezone") or "UTC"
    return iso_datetime(record["occurred_at"]).astimezone(ZoneInfo(zone)).date()


def _canonical_day(value: str) -> date:
    try:
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise JournalError("JOURNAL_DATE_INVALID", "请选择完整的开始和截止日期。") from None


def _check_market(package: dict, identity: dict, today: date, now: str) -> dict:
    if not isinstance(package, dict) or not isinstance(package.get("candles"), list):
        raise JournalError("MARKET_FORMAT_UNKNOWN", "新行情无法校验，原行情保留。")
    if _symbol_key(package) != _symbol_key(identity):
        raise JournalError("MARKET_IDENTITY_CONFLICT", "新行情证券身份不一致，原行情保留。")
    for field in ("source_id", "as_of", "retrieved_at"):
        if not isinstance(package.get(field), str) or not package[field]:
            raise JournalError("MARKET_PROVENANCE_MISSING", "新行情缺少来源时间，原行情保留。")
    iso_datetime(package["retrieved_at"])
    if package.get("price_basis") in {"UNADJUSTED", "ADJUSTED_WITH_FACTORS"}:
        proof = package.get("price_basis_evidence")
        if not isinstance(proof, dict) or not all(proof.get(field) for field in ("source_id", "as_of", "retrieved_at")):
            raise JournalError("MARKET_BASIS_UNPROVEN", "新行情缺少价格口径证据，原行情保留。")
        iso_datetime(proof["retrieved_at"])
    zone = package.get("exchange_timezone")
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, TypeError):
        raise JournalError("MARKET_TIMEZONE_UNKNOWN", "新行情时区未验证，原行情保留。") from None
    if identity.get("exchange_timezone") and zone != identity["exchange_timezone"]:
        raise JournalError("MARKET_TIMEZONE_MISMATCH", "新行情时区不一致，原行情保留。")
    if package.get("content_hash") and package["content_hash"] != canonical_hash({
            key: item for key, item in package.items() if key != "content_hash"}):
        raise JournalError("MARKET_HASH_MISMATCH", "新行情内容校验失败，原行情保留。")
    result, seen = deepcopy(package), set()
    for row in result["candles"]:
        day = _canonical_day(row.get("date"))
        if day > today or day in seen:
            raise JournalError("MARKET_DATE_INVALID", "新行情日期重复或超出今天，原行情保留。")
        seen.add(day)
        for field in ("source_id", "as_of", "retrieved_at"):
            if not row.get(field):
                raise JournalError("MARKET_PROVENANCE_MISSING", "新蜡烛缺少来源时间，原行情保留。")
        values = {field: decimal_value(row.get(field)) for field in ("open", "high", "low", "close", "volume")}
        if (any(values[field] <= 0 for field in ("open", "high", "low", "close")) or values["volume"] < 0
                or values["high"] < max(values[field] for field in ("open", "low", "close"))
                or values["low"] > min(values[field] for field in ("open", "high", "close"))):
            raise JournalError("MARKET_OHLC_INVALID", "新蜡烛价格关系错误，原行情保留。")
        available = row.get("available_at")
        if available and iso_datetime(available) > iso_datetime(now):
            # A still-forming daily bar cannot be asserted as a known close.
            row["available_at"] = None
    result.pop("content_hash", None)
    result["content_hash"] = canonical_hash(result)
    return result


def _merge_market(old: dict | None, new: dict) -> dict:
    if not old:
        return deepcopy(new)
    old_basis, new_basis = old.get("price_basis"), new.get("price_basis")
    if old.get("candles") and (old_basis != new_basis or old.get("exchange_timezone") != new.get("exchange_timezone")):
        raise JournalError("MARKET_BASIS_CONFLICT", "新旧行情口径不同，保留旧有效行情。")
    if old_basis == "ADJUSTED_WITH_FACTORS" and old.get("candles"):
        old_factors = {item["date"]: item["factor"] for item in old.get("adjustment_factors", [])}
        new_factors = {item["date"]: item["factor"] for item in new.get("adjustment_factors", [])}
        if any(day in new_factors and new_factors[day] != factor for day, factor in old_factors.items()):
            raise JournalError("MARKET_BASIS_CONFLICT", "复权因子发生冲突，保留旧有效行情。")
    result = deepcopy(new)
    for field, key in (("candles", "date"), ("adjustment_factors", "date")):
        rows = {item[key]: deepcopy(item) for item in old.get(field, [])}
        rows.update({item[key]: deepcopy(item) for item in new.get(field, [])})
        result[field] = [rows[day] for day in sorted(rows)]
    for field in ("events", "gaps"):
        rows = {canonical_hash(item): deepcopy(item) for item in old.get(field, []) + new.get(field, [])}
        result[field] = list(rows.values())
    if not new.get("session_calendar"):
        result["session_calendar"] = deepcopy(old.get("session_calendar"))
    elif old.get("session_calendar"):
        old_calendar, new_calendar = old["session_calendar"], new["session_calendar"]
        if isinstance(old_calendar, dict) and isinstance(new_calendar, dict):
            sessions = {row["date"]: row for row in old_calendar.get("sessions", [])}
            sessions.update({row["date"]: row for row in new_calendar.get("sessions", [])})
            result["session_calendar"]["sessions"] = [sessions[day] for day in sorted(sessions)]
    result["source_id"] = "journal-market-merge"
    result["source_packages"] = [{field: item.get(field) for field in ("source_id", "as_of", "retrieved_at", "content_hash")}
                                 for item in (old, new)]
    result.pop("content_hash", None)
    result["content_hash"] = canonical_hash(result)
    return result


class JournalUpdates:
    def __init__(self, repo: Path | str, account_ref: str, *, real: bool = True, market_fetch=None):
        if not isinstance(account_ref, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{7,100}", account_ref):
            raise JournalError("OPAQUE_ACCOUNT_REF_REQUIRED", "请选择已有本地账户引用。")
        self.repo = Path(repo)
        self.root = private_root(self.repo, real=False)
        self.account_ref, self.real = account_ref, real
        self.market_fetch = market_fetch or fetch_market

    def _write_guard(self) -> None:
        if self.real:
            assert_real_write_ready(self.repo)

    def _read(self, ledger: Ledger) -> tuple[dict, bool]:
        records = ledger.current_records(self.account_ref)
        if not records:
            raise JournalError("JOURNAL_EMPTY", "该账户尚无保存的交易。")
        markets, matching, opening = {}, None, {}
        current_key = _records_key(records)
        for item in ledger.snapshots(self.account_ref):
            snapshot = ledger.load_snapshot(item["snapshot_id"])
            if snapshot.get("account_ref") != self.account_ref:
                raise JournalError("SNAPSHOT_ACCOUNT_CONFLICT", "保存版本的账户绑定不一致。")
            if not snapshot.get("coverage", {}).get("requested_window") and not snapshot.get("context_records"):
                opening = snapshot.get("opening_positions", {})
            for package in snapshot.get("market", []):
                markets[_symbol_key(package)] = deepcopy(package)
            if (not snapshot.get("coverage", {}).get("requested_window")
                    and not snapshot.get("context_records") and _records_key(snapshot["records"]) == current_key):
                matching = snapshot
        frozen_market = list(markets.values())
        if matching and canonical_hash(matching.get("market", [])) == canonical_hash(frozen_market):
            return deepcopy(matching), True
        result = ledger.build_snapshot(self.account_ref, market=frozen_market, opening_positions=opening)
        result["snapshot_id"] = "snapshot-memory-" + canonical_hash({
            "records": current_key, "market": frozen_market, "opening_positions": opening})
        return result, False

    def read_timeline(self) -> dict:
        with Ledger(self.root, read_only=True) as ledger:
            return self._read(ledger)[0]

    load_timeline = read_timeline

    def refresh(self) -> dict:
        """Reload all saved facts. A refresh by itself never writes or fetches."""
        snapshot = self.read_timeline()
        return self._result("REFRESHED", snapshot)

    def _result(self, status: str, snapshot: dict, **extra) -> dict:
        now = utc_now()
        return {"status": status, "snapshot": snapshot, "snapshot_id": snapshot["snapshot_id"],
                "record_count": len(snapshot["records"]), "source_id": "journal-workspace-update",
                "as_of": snapshot["as_of"], "retrieved_at": now, **extra}

    def _csv_admission(self, ledger: Ledger, records: list[dict], digest: str, window: dict) -> dict | None:
        receipts = [item for item in ledger.batches(self.account_ref) if item.get("status") == "SAVED"]
        repeated = next((item for item in receipts if item.get("source_hash") == digest), None)
        if repeated:
            return repeated
        if all(record.get("source_record_id") for record in records):
            return None
        old_records = ledger.current_records(self.account_ref)
        first, last = iso_datetime(window["start"]), iso_datetime(window["end"])
        zone = ZoneInfo(window["timezone"])
        overlap = False
        for record in old_records:
            # A display day is not an execution identity: compare precise
            # timestamps in the explicitly selected date-range timezone.
            overlap = overlap or record_in_window(record, window)
            if record.get("time_precision") == "DATE" and record.get("source_timezone") != window["timezone"]:
                source_day = date.fromisoformat(record["occurred_at"])
                overlap = overlap or (first.astimezone(zone).date() - timedelta(days=1)
                                      <= source_day <= last.astimezone(zone).date() + timedelta(days=1))
        for receipt in receipts:
            request = receipt.get("coverage", {}).get("request") or {}
            old_first = iso_datetime(request["start"]) if request.get("start") else None
            old_last = iso_datetime(request["end"]) if request.get("end") else None
            if old_first or old_last:
                # An unknown account-opening bound is an open interval, not
                # permission to append another unidentified overlapping batch.
                overlap = overlap or ((old_first is None or old_first <= last)
                                      and (old_last is None or first <= old_last))
        if overlap:
            raise JournalError("CSV_OVERLAP_UNPROVEN", "该文件没有稳定成交编号且与已保存期间重叠；请导出不重叠日期，或使用包含稳定成交编号的官方文件。")
        return None

    def _unchanged_csv(self, ledger: Ledger, records: list[dict], repeated: dict, now: str) -> dict:
        parent = self._read(ledger)[0]
        return self._result("UNCHANGED", parent, receipt={
            "status": "UNCHANGED", "inserted": 0, "revised": 0, "unchanged": len(records),
            "source_id": repeated.get("source_id"), "as_of": repeated.get("as_of"), "retrieved_at": now})

    def update_market(self, *, snapshot_id: str | None = None) -> dict:
        # Read with this thread's own connection, then release it before I/O.
        with Ledger(self.root, read_only=True) as ledger:
            parent, persistent = self._read(ledger)
            if snapshot_id:
                try:
                    requested = ledger.load_snapshot(snapshot_id)
                except JournalError as exc:
                    if exc.code != "SNAPSHOT_NOT_FOUND" or snapshot_id != parent["snapshot_id"]:
                        raise
                else:
                    if (requested.get("account_ref") != self.account_ref
                            or _records_key(requested["records"]) != _records_key(parent["records"])
                            or requested["snapshot_id"] != parent["snapshot_id"]):
                        raise JournalError("TIMELINE_VERSION_CHANGED", "交易资料已变化，请先刷新时间线。")
                    parent, persistent = requested, True
        now = utc_now()
        today = iso_datetime(now).date()
        first = min(_exchange_day(record) for record in parent["records"])
        if first > today or (today - first).days > 36525:
            raise JournalError("MARKET_RANGE_REJECTED", "保存交易的行情日期超出允许范围。")
        identities = {}
        for record in parent["records"]:
            instrument = record.get("instrument", {})
            if instrument.get("asset_type") not in {"STOCK", "ETF", "OPTION"}:
                continue
            public = {field: instrument.get(field) for field in ("key", "symbol", "asset_type", "underlying", "market", "currency", "exchange_timezone")}
            identities.setdefault(_symbol_key(public), public)
        if not identities or len(identities) > MAX_MARKET_SYMBOLS:
            raise JournalError("MARKET_SYMBOL_LIMIT", "本次行情证券数量超限，请使用现有Skill分段更新。")
        markets = {_symbol_key(item): deepcopy(item) for item in parent.get("market", [])}
        updated, failed, retained, budget = [], [], [], MAX_MARKET_REQUESTS
        # Verify installation before any externally visible data operation.
        self._write_guard()
        for key, identity in identities.items():
            old = markets.get(key)
            try:
                if budget <= 0:
                    raise JournalError("MARKET_REQUEST_BUDGET_EXHAUSTED", "本次公开行情请求达到上限。")
                package = self.market_fetch(identity, first.isoformat(), today.isoformat(),
                                            now=now, request_budget=min(budget, MAX_REQUESTS_PER_SYMBOL))
                used = max(1, len(package.get("segments", []))) if isinstance(package, dict) else 1
                budget -= min(budget, used)
                package = _check_market(package, identity, today, now)
                if not package["candles"]:
                    raise JournalError("NO_RELIABLE_OHLCV", "本次未取得有效蜡烛，原行情保留。")
                markets[key] = _merge_market(old, package)
                updated.append(key[2])
                if any(item.get("status") == "FAILED" for item in package.get("segments", [])):
                    failed.append({"symbol": key[2], "code": "MARKET_PARTIAL"})
                    if old:
                        retained.append(key[2])
            except Exception as exc:
                code = getattr(exc, "code", None) or "MARKET_UPDATE_FAILED"
                if not re.fullmatch(r"[A-Z0-9_]{1,100}", str(code)):
                    code = "MARKET_UPDATE_FAILED"
                failed.append({"symbol": key[2], "code": code})
                if old:
                    retained.append(key[2])
        if not updated:
            return self._result("UNCHANGED", parent, updated_symbols=[], failed_symbols=failed,
                                retained_symbols=retained)
        self._write_guard()
        with Ledger(self.root) as ledger:
            with ledger.atomic_write():
                # Another import between the read and this write must not make
                # the latest timeline silently lose records.
                if _records_key(ledger.current_records(self.account_ref)) != _records_key(parent["records"]):
                    raise JournalError("TIMELINE_VERSION_CHANGED", "交易资料已变化，请先刷新时间线。")
                if not persistent:
                    parent = ledger.freeze_snapshot(self.account_ref, market=parent.get("market", []),
                                                    opening_positions=parent.get("opening_positions", {}))
                snapshot = ledger.derive_snapshot(parent["snapshot_id"], list(markets.values()))
        return self._result("PARTIAL" if failed else "UPDATED", snapshot, updated_symbols=updated,
                            failed_symbols=failed, retained_symbols=retained)

    def import_csv(self, raw: bytes, *, start: str, end: str, timezone: str | None = None,
                   range_timezone: str | None = None,
                   source_timezone: str = "Asia/Hong_Kong", exchange_timezone: str | None = None,
                   activity_type: str = "FILL") -> dict:
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
            raise JournalError("CSV_LIMIT", "请选择大小在允许范围内的官方CSV文件。")
        first, last = _canonical_day(start), _canonical_day(end)
        if first > last:
            raise JournalError("INVALID_WINDOW", "开始日期晚于截止日期。")
        if range_timezone and timezone and range_timezone != timezone:
            raise JournalError("IMPORT_RANGE_TIMEZONE_CONFLICT", "导入日期范围的时区选择冲突。")
        selected_timezone = range_timezone or timezone
        if not selected_timezone:
            if source_timezone == "PER_ROW":
                raise JournalError("IMPORT_RANGE_TIMEZONE_REQUIRED", "逐行时区账单还需明确选择起止日期所属时区。")
            selected_timezone = source_timezone
        now = utc_now()
        try:
            zone = ZoneInfo(selected_timezone)
            if last > iso_datetime(now).astimezone(zone).date():
                raise JournalError("FUTURE_IMPORT_WINDOW", "截止日期不能晚于今天。")
        except (ZoneInfoNotFoundError, TypeError):
            raise JournalError("INVALID_TIMEZONE", "导入时区无效。") from None
        window = resolve_window("custom", start=start, end=end, timezone_name=selected_timezone, now=now)
        digest = hashlib.sha256(raw).hexdigest()
        # Temporary parsing is never retained as an official source. In
        # particular, an overlapping FILE_ROW_ONLY export leaves zero writes.
        with tempfile.TemporaryDirectory(prefix="journal-csv-") as temporary:
            source = Path(temporary) / "upload.csv"
            fd = os.open(source, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            records = parse_csv(source, account_ref=self.account_ref, source_id="tiger-source:" + digest,
                                as_of=window["end"], retrieved_at=now, source_timezone=source_timezone,
                                exchange_timezone=exchange_timezone, activity_type=activity_type)
        if not records or any(not record_in_window(record, window) for record in records):
            raise JournalError("CSV_OUTSIDE_DECLARED_WINDOW", "文件包含所选日期外的记录，请核对官方导出完整起止日期。")
        for record in records:
            _validate_record(record)
        if len({record["record_id"] for record in records}) != len(records):
            raise JournalError("SOURCE_ID_COLLISION", "官方文件包含冲突的成交编号，未保存。")
        with Ledger(self.root, read_only=True) as ledger:
            old_records = ledger.current_records(self.account_ref)
            preflight_records_key = _records_key(old_records)
            parent = self._read(ledger)[0] if old_records else None
            repeated = self._csv_admission(ledger, records, digest, window)
            if repeated:
                return self._unchanged_csv(ledger, records, repeated, now)
        self._write_guard()
        destination = self.root / "sources" / (digest + ".csv")
        created_source = False

        def remove_new_source():
            if created_source:
                destination.unlink(missing_ok=True)

        with Ledger(self.root) as ledger:
            with ledger.atomic_write(on_failure=remove_new_source):
                # The exclusive transaction spans admission, import and
                # snapshot freeze; helper calls cannot commit it early.
                if _records_key(ledger.current_records(self.account_ref)) != preflight_records_key:
                    raise JournalError("TIMELINE_VERSION_CHANGED", "其他入口已更新交易，请刷新后重试导入。")
                repeated = self._csv_admission(ledger, records, digest, window)
                if repeated:
                    return self._unchanged_csv(ledger, records, repeated, now)
                if destination.exists():
                    if destination.is_symlink() or destination.stat().st_mode & 0o077 or hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                        raise JournalError("CSV_SOURCE_CONFLICT", "已保存来源文件无法核验，未导入。")
                else:
                    try:
                        write_private(destination, raw)
                    except FileExistsError:
                        raise JournalError("CSV_SOURCE_CONFLICT", "其他入口已保存该来源，请刷新后重试。") from None
                    except BaseException:
                        # write_private may have created a partial file
                        # before a disk write failed; it is ours to remove.
                        created_source = destination.exists()
                        raise
                    created_source = True
                receipt = ledger.import_records(records, source_hash=digest, requested_window=window,
                                                coverage={"source_id": "tiger-source:" + digest,
                                                          "as_of": window["end"], "retrieved_at": now},
                                                mode="USER_ASSISTED")
                snapshot = ledger.freeze_snapshot(self.account_ref, market=parent.get("market", []) if parent else [],
                                                  opening_positions=parent.get("opening_positions", {}) if parent else {})
        return self._result("SAVED", snapshot, receipt=receipt)
