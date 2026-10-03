"""Allowlisted CSV fields, never a passthrough of account names or raw rows.

An explicit export view may supply activity_type. Otherwise the header must
identify actual fills, orders, or an activity column; a FILLED order status is
not sufficient evidence of individual executions.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError, canonical_hash, decimal_string, decimal_value, iso_datetime

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 200_000
ACTIVITY_TYPES = frozenset({"FILL", "ORDER", "FEE", "EXERCISE", "ASSIGNMENT", "EXPIRY", "TRANSFER", "CORPORATE_ACTION", "CASH", "DIVIDEND", "TAX"})

_ALIASES = {
    "symbol": ("Symbol", "Ticker", "Stock Code", "Security Code", "Contract", "Contract Code", "代码", "股票代码", "证券代码", "合约代码", "合約代碼"),
    "asset_type": ("Asset Type", "Security Type", "Product Type", "资产类型", "證券類型", "证券类型", "产品类型"),
    "market": ("Market", "Trading Market", "市场", "交易市场", "市場"),
    "currency": ("Currency", "Settlement Currency", "币种", "货币", "結算貨幣", "幣種"),
    "side": ("Side", "Action", "Buy/Sell", "Buy Sell", "Direction", "买卖方向", "买卖", "方向", "交易方向", "買賣方向"),
    "quantity": ("Quantity", "Qty", "Shares", "Contracts", "Trade Quantity", "Filled Quantity", "Filled Qty", "成交数量", "成交量", "數量", "数量"),
    "price": ("Price", "Trade Price", "Execution Price", "Fill Price", "成交价格", "成交价", "成交價格", "价格"),
    "amount": ("Amount", "Cash Amount", "Net Amount", "金额", "变动金额", "资金金额", "現金金額", "现金金额"),
    "order_price": ("Average Price", "Avg Price", "Order Price", "平均成交价", "平均成交价格", "委托价格", "委託價格"),
    "occurred_at": ("Trade Time", "Execution Time", "Fill Time", "Trade DateTime", "成交时间", "成交日期时间", "成交時間"),
    "date": ("Trade Date", "Execution Date", "Date", "成交日期", "交易日期", "日期"),
    "time": ("Time", "时间", "時間"),
    "order_time": ("Order Time", "Update Time", "Updated At", "Last Update Time", "委托时间", "订单更新时间", "更新时间", "委託時間"),
    "activity_type": ("Activity Type", "Transaction Type", "Event Type", "Record Type", "活动类型", "交易类型", "事件类型", "记录类型"),
    "source_record_id": ("Execution ID", "Fill ID", "Trade ID", "Transaction ID", "成交编号", "成交編號", "成交ID", "交易流水号"),
    "order_id": ("Order ID", "Order No", "订单编号", "订单号", "委托编号", "訂單編號"),
    "fees": ("Total Fees", "Total Fee", "总费用", "總費用"),
    "ambiguous_fee": ("Fees", "Fee", "Transaction Fees", "费用", "交易费用", "費用", "交易費用"),
    "commission": ("Commission", "佣金", "傭金"),
    "platform_fee": ("Platform Fee", "Platform Fees", "平台费", "平台使用费"),
    "tax": ("Tax", "Stamp Duty", "税费", "印花税", "印花稅"),
    "other_fee": ("Other Fees", "Other Fee", "其他费用", "其他費用"),
    "underlying": ("Underlying", "Underlying Symbol", "标的", "标的代码", "正股代码", "標的"),
    "expiry": ("Expiry", "Expiration", "Expiry Date", "Expiration Date", "到期日", "到期日期"),
    "strike": ("Strike", "Strike Price", "行权价", "行权价格", "行使價"),
    "right": ("Put/Call", "Call/Put", "Option Type", "Right", "期权类型", "認購認沽", "认购认沽"),
    "multiplier": ("Multiplier", "Contract Multiplier", "合约乘数", "合約乘數", "乘数"),
    "adjustment_status": ("Adjustment Status", "Adjusted Contract", "合约调整状态", "调整状态"),
    "position_effect": ("Position Effect", "Open/Close", "Opening/Closing", "开平仓", "開平倉"),
    "source_timezone": ("Timezone", "Time Zone", "Source Timezone", "时区", "来源时区"),
    "exchange_timezone": ("Exchange Timezone", "交易所时区"),
    "security_id": ("ISIN", "Security ID", "Instrument ID", "证券ID", "证券识别码"),
    "status": ("Status", "Order Status", "状态", "订单状态"),
    "related_record_id": ("Related Execution ID", "Related Trade ID", "关联成交编号"),
}


def _heading(value: str) -> str:
    return re.sub(r"[\s_\-()/：:]+", "", value).lower()


_HEADER_MAP = {_heading(alias): field for field, aliases in _ALIASES.items() for alias in aliases}
_MARKETS = {
    "US": "US", "USA": "US", "美股": "US", "美国": "US", "NASDAQ": "US", "NYSE": "US", "AMEX": "US",
    "HK": "HK", "HKEX": "HK", "香港": "HK", "港股": "HK",
    "SG": "SG", "SGX": "SG", "新加坡": "SG", "AU": "AU", "ASX": "AU", "澳大利亚": "AU",
    "CN": "CN", "SSE": "CN", "SZSE": "CN", "中国": "CN", "A股": "CN",
}
_ZONES = {"US": "America/New_York", "HK": "Asia/Hong_Kong", "SG": "Asia/Singapore", "AU": "Australia/Sydney", "CN": "Asia/Shanghai"}
_ASSETS = {"STOCK": "STOCK", "STK": "STOCK", "EQUITY": "STOCK", "COMMON STOCK": "STOCK", "股票": "STOCK", "ETF": "ETF", "交易所交易基金": "ETF", "OPTION": "OPTION", "OPT": "OPTION", "LISTED OPTION": "OPTION", "期权": "OPTION", "期權": "OPTION"}
_ACTIVITIES = {
    "FILL": "FILL", "EXECUTION": "FILL", "TRADE": "FILL", "成交": "FILL", "交易": "FILL",
    "ORDER": "ORDER", "订单": "ORDER", "委托": "ORDER", "FEE": "FEE", "费用": "FEE", "COMMISSION": "FEE",
    "EXERCISE": "EXERCISE", "行权": "EXERCISE", "行使": "EXERCISE", "ASSIGNMENT": "ASSIGNMENT", "指派": "ASSIGNMENT", "被行权": "ASSIGNMENT",
    "EXPIRY": "EXPIRY", "EXPIRATION": "EXPIRY", "到期": "EXPIRY", "TRANSFER": "TRANSFER", "转仓": "TRANSFER", "转入": "TRANSFER", "转出": "TRANSFER",
    "CORPORATE_ACTION": "CORPORATE_ACTION", "公司行动": "CORPORATE_ACTION", "CASH": "CASH", "资金": "CASH", "DIVIDEND": "DIVIDEND", "股息": "DIVIDEND", "TAX": "TAX", "税": "TAX",
}
_SIDES = {"BUY": ("BUY", None), "B": ("BUY", None), "买": ("BUY", None), "买入": ("BUY", None), "買入": ("BUY", None), "SELL": ("SELL", None), "S": ("SELL", None), "卖": ("SELL", None), "卖出": ("SELL", None), "賣出": ("SELL", None), "BTO": ("BUY", "OPEN"), "BUY TO OPEN": ("BUY", "OPEN"), "BTC": ("BUY", "CLOSE"), "BUY TO CLOSE": ("BUY", "CLOSE"), "STO": ("SELL", "OPEN"), "SELL TO OPEN": ("SELL", "OPEN"), "STC": ("SELL", "CLOSE"), "SELL TO CLOSE": ("SELL", "CLOSE")}
_OCC = re.compile(r"^([A-Z0-9.]{1,8})\s*(\d{6})([CP])(\d{8})$")


def _number(raw: str | None, field: str) -> str | None:
    if raw is None or raw.strip() in {"", "--", "N/A", "-", "未知"}:
        return None
    value = raw.strip().replace(",", "")
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    return decimal_string(decimal_value(value, field=field))


def _source_time(raw: str, timezone_name: str | None) -> tuple[str, str]:
    raw = raw.strip().replace("/", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return date.fromisoformat(raw).isoformat(), "DATE"
        except ValueError as exc:
            raise JournalError("INVALID_TIME", "来源日期无效。") from exc
    # Avoid locale-dependent day/month guesses and order update substitutions.
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JournalError("UNKNOWN_TIME_FORMAT", "来源业务时间格式未验证；需提供 ISO 日期/时刻。") from exc
    precision = "SECOND" if re.search(r"\d{2}:\d{2}:\d{2}", raw) else "MINUTE"
    if parsed.tzinfo is None:
        if not timezone_name:
            raise JournalError("TIMEZONE_REQUIRED", "无时区的逐笔时间需要来源或交易所时区。")
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise JournalError("INVALID_TIMEZONE", "来源时区无效。") from exc
        candidates = [parsed.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
        valid = [item for item in candidates if item.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == parsed]
        offsets = {item.utcoffset() for item in valid}
        if not valid or len(offsets) > 1:
            raise JournalError("AMBIGUOUS_LOCAL_TIME", "来源时间处于夏令时缺失或歧义区间，需要明确 UTC offset。")
        parsed = valid[0]
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), precision


def _instrument(row: dict, default_zone: str | None) -> dict:
    symbol = (row.get("symbol") or "").strip().upper() or None
    if symbol and not (re.fullmatch(r"[A-Z0-9][A-Z0-9.^:/_-]{0,79}", symbol) or _OCC.fullmatch(symbol)):
        raise JournalError("INVALID_SYMBOL", "证券代码格式无效。")
    market_raw = (row.get("market") or "").strip().upper()
    market = _MARKETS.get(market_raw) or (market_raw if re.fullmatch(r"[A-Z]{2,8}", market_raw) else None)
    currency = (row.get("currency") or "").strip().upper() or None
    if currency and not re.fullmatch(r"[A-Z]{3}", currency):
        raise JournalError("INVALID_CURRENCY", "币种必须是来源中的三位货币代码。")
    asset = _ASSETS.get((row.get("asset_type") or "").strip().upper())
    underlying = (row.get("underlying") or "").strip().upper() or None
    if underlying and not re.fullmatch(r"[A-Z0-9][A-Z0-9.^:/_-]{0,29}", underlying):
        raise JournalError("INVALID_UNDERLYING", "期权标的代码格式无效。")
    expiry = (row.get("expiry") or "").strip().replace("/", "-") or None
    if expiry:
        try:
            expiry = date.fromisoformat(expiry).isoformat()
        except ValueError as exc:
            raise JournalError("INVALID_OPTION_EXPIRY", "期权到期日格式无效。") from exc
    strike = _number(row.get("strike"), "strike")
    right_raw = (row.get("right") or "").strip().upper()
    right = {"C": "CALL", "CALL": "CALL", "认购": "CALL", "認購": "CALL", "P": "PUT", "PUT": "PUT", "认沽": "PUT", "認沽": "PUT"}.get(right_raw)
    match = _OCC.fullmatch(symbol or "")
    if match:
        occ_underlying, occ_date, occ_right, occ_strike = match.groups()
        try:
            occ_expiry = datetime.strptime(occ_date, "%y%m%d").date().isoformat()
        except ValueError as exc:
            raise JournalError("INVALID_OPTION_EXPIRY", "OCC 合约日期无效。") from exc
        occ_values = {"underlying": occ_underlying, "expiry": occ_expiry, "right": "CALL" if occ_right == "C" else "PUT", "strike": decimal_string(decimal_value(occ_strike) / 1000)}
        supplied = {"underlying": underlying, "expiry": expiry, "right": right, "strike": strike}
        if any(value is not None and value != occ_values[name] for name, value in supplied.items()):
            raise JournalError("OPTION_IDENTITY_CONFLICT", "合约代码与来源期权字段冲突。")
        underlying, expiry, right, strike = (occ_values[name] for name in ("underlying", "expiry", "right", "strike"))
        if asset not in (None, "OPTION"):
            raise JournalError("OPTION_IDENTITY_CONFLICT", "合约代码与资产类别冲突。")
        asset = "OPTION"
    elif underlying or expiry or strike or right:
        if asset not in (None, "OPTION"):
            raise JournalError("OPTION_IDENTITY_CONFLICT", "期权字段与资产类别冲突。")
        asset = "OPTION"
    multiplier = _number(row.get("multiplier"), "multiplier")
    if multiplier is not None and decimal_value(multiplier) <= 0:
        raise JournalError("INVALID_MULTIPLIER", "合约乘数必须大于零。")
    if asset in {"STOCK", "ETF"}:
        multiplier = "1"
    adjustment = (row.get("adjustment_status") or "").strip().upper() or "UNKNOWN"
    # Only an explicit source field establishes that an option is standard.
    if adjustment not in {"STANDARD", "ADJUSTED", "UNKNOWN", "标准", "已调整"}:
        adjustment = "UNKNOWN"
    adjustment = {"标准": "STANDARD", "已调整": "ADJUSTED"}.get(adjustment, adjustment)
    exchange_zone = row.get("exchange_timezone") or default_zone or _ZONES.get(market)
    if exchange_zone:
        try:
            ZoneInfo(exchange_zone)
        except ZoneInfoNotFoundError as exc:
            raise JournalError("INVALID_TIMEZONE", "来源交易所时区无效。") from exc
    security_id = (row.get("security_id") or "").strip() or None
    if security_id and not re.fullmatch(r"[A-Za-z0-9._:-]{1,80}", security_id):
        raise JournalError("INVALID_SECURITY_ID", "来源证券稳定身份格式无效。")
    identity = {"market": market, "currency": currency, "security_id": security_id, "symbol": symbol, "asset_type": asset,
                "underlying": underlying, "expiry": expiry, "strike": strike, "right": right,
                "multiplier": multiplier if asset == "OPTION" else "1", "adjustment_status": adjustment if asset == "OPTION" else None}
    missing = [name for name in ("symbol", "market", "currency", "asset_type") if identity[name] is None]
    if asset == "OPTION":
        missing.extend(name for name in ("underlying", "expiry", "strike", "right", "multiplier") if identity[name] is None)
        if adjustment == "UNKNOWN":
            missing.append("adjustment_status")
    return {"key": "instrument-" + canonical_hash(identity), **identity, "exchange_timezone": exchange_zone, "unknown_fields": missing}


def _validate_references(account_ref: str, source_id: str, as_of: str, retrieved_at: str) -> None:
    iso_datetime(as_of)
    iso_datetime(retrieved_at)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{7,100}", account_ref):
        raise JournalError("OPAQUE_ACCOUNT_REF_REQUIRED", "账户必须使用随机本地引用。")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{3,150}", source_id):
        raise JournalError("OPAQUE_SOURCE_REF_REQUIRED", "来源必须使用非私人路径的引用。")


def _read_source(path: str | Path) -> tuple[bytes, str, str]:
    source_path = Path(path)
    if source_path.is_symlink():
        raise JournalError("SOURCE_SYMLINK", "原始文件不能是符号链接。")
    try:
        source_size = source_path.stat().st_size
        if source_size > MAX_BYTES:
            raise JournalError("CSV_LIMIT", "来源文件超过单批大小预算，请分段导出。")
        data = source_path.read_bytes()
    except OSError:
        raise JournalError("SOURCE_UNAVAILABLE", "无法读取已绑定的本地来源文件。") from None
    if len(data) > MAX_BYTES:
        raise JournalError("CSV_LIMIT", "来源文件超过单批大小预算，请分段导出。")
    content_hash = hashlib.sha256(data).hexdigest()
    encodings = ("utf-16",) if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "gb18030")
    decoded = None
    for encoding in encodings:
        try:
            decoded = data.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    if decoded is None:
        raise JournalError("CSV_ENCODING", "来源编码未支持。")
    return data, decoded, content_hash


def parse_csv(path: str | Path, *, account_ref: str, source_id: str, as_of: str,
              retrieved_at: str, exchange_timezone: str | None = None,
              source_timezone: str | None = None, activity_type: str | None = None) -> list[dict]:
    """Parse recognized official-export columns; fail the batch on unsafe guesses.

    Reading and raw file retention are the restricted local caller's job. Only
    the resulting allowlisted dictionaries may reach chart or LLM interfaces.
    """
    _validate_references(account_ref, source_id, as_of, retrieved_at)
    if activity_type is not None and activity_type not in ACTIVITY_TYPES:
        raise JournalError("UNKNOWN_ACTIVITY_TYPE", "导出类别未验证。")
    data, decoded, content_hash = _read_source(path)
    # A statement has its own verified section/parent/child contract. The
    # detector matches full official headers, never identifying preamble text.
    from .statement import _parse_statement, is_statement

    if is_statement(data):
        if activity_type not in (None, "FILL"):
            raise JournalError("ACTIVITY_TYPE_CONFLICT", "账单逐笔成交与声明的导出类别冲突。")
        records = _parse_statement(decoded, content_hash=content_hash, account_ref=account_ref,
                                   source_id=source_id, as_of=as_of, retrieved_at=retrieved_at)
        if source_timezone not in (None, "PER_ROW") and any(item["source_timezone"] != source_timezone for item in records):
            raise JournalError("SOURCE_TIMEZONE_CONFLICT", "账单逐行时区与声明时区冲突。")
        return records
    if source_timezone == "PER_ROW":
        raise JournalError("INVALID_TIMEZONE", "逐行时区模式仅适用于已验证的官方账单。")
    # Official reports can contain a few identifying preamble lines. They are
    # discarded in this local process; never return them in diagnostics.
    lines = decoded.splitlines()
    header_index = None
    delimiter = ","
    headings = None
    for index, line in enumerate(lines[:20]):
        for candidate in (",", "\t", ";"):
            raw_headers = next(csv.reader([line], delimiter=candidate))
            mapped = [_HEADER_MAP.get(_heading(item.lstrip("\ufeff"))) for item in raw_headers]
            fields = {item for item in mapped if item}
            if {"symbol", "side", "quantity"}.issubset(fields) or {"activity_type", "date"}.issubset(fields) or {"activity_type", "occurred_at"}.issubset(fields):
                header_index, delimiter, headings = index, candidate, mapped
                break
        if header_index is not None:
            break
    if header_index is None or headings is None:
        raise JournalError("UNKNOWN_CSV_FORMAT", "来源列结构未验证；不从未知表格猜测逐笔成交。")
    known = [item for item in headings if item]
    if len(known) != len(set(known)):
        raise JournalError("AMBIGUOUS_CSV_COLUMNS", "存在重复语义字段，需明确来源列。")
    fields = set(known)
    inferred_kind = activity_type
    if inferred_kind is None and "activity_type" not in fields:
        if "occurred_at" in fields or ("date" in fields and "price" in fields and "order_price" not in fields and "order_time" not in fields):
            inferred_kind = "FILL"
        elif "order_time" in fields or "order_price" in fields:
            inferred_kind = "ORDER"
        else:
            raise JournalError("EXECUTION_PROVENANCE_REQUIRED", "表格无法区分逐笔成交与委托；需要已验证导出类别。")
    records = []
    reader = csv.reader(io.StringIO("\n".join(lines[header_index + 1:])), delimiter=delimiter)
    for offset, cells in enumerate(reader, start=header_index + 2):
        if not cells or not any(item.strip() for item in cells):
            continue
        if len(records) >= MAX_ROWS:
            raise JournalError("CSV_LIMIT", "来源行数超过单批预算。")
        if len(cells) != len(headings):
            raise JournalError("CSV_ROW_WIDTH", "来源行列数与已验证表头不一致。")
        row = {name: value.strip() for name, value in zip(headings, cells) if name}
        kind = _ACTIVITIES.get((row.get("activity_type") or "").strip().upper()) if "activity_type" in fields else inferred_kind
        if kind not in ACTIVITY_TYPES:
            raise JournalError("UNKNOWN_ACTIVITY_TYPE", "存在未验证经济活动类别；整批未写入。")
        if activity_type is not None and kind != activity_type:
            raise JournalError("ACTIVITY_TYPE_CONFLICT", "来源活动类别与已验证导出视图冲突。")
        instrument = _instrument(row, exchange_timezone)
        raw_time = row.get("occurred_at")
        if not raw_time and row.get("date"):
            raw_time = row["date"] + (" " + row["time"] if row.get("time") else "")
        if not raw_time and kind == "ORDER":
            raw_time = row.get("order_time")
        if not raw_time:
            raise JournalError("BUSINESS_TIME_REQUIRED", "缺少该经济活动的业务时间；不使用订单更新时间代替成交。")
        verified_source_zone = row.get("source_timezone") or source_timezone or exchange_timezone or row.get("exchange_timezone")
        if verified_source_zone:
            try:
                ZoneInfo(verified_source_zone)
            except ZoneInfoNotFoundError as exc:
                raise JournalError("INVALID_TIMEZONE", "来源显示时区无效。") from exc
        # Broker export display timezone can differ from exchange timezone.
        # Market identity alone cannot establish a naive timestamp's offset.
        occurred, precision = _source_time(raw_time, verified_source_zone)
        side, side_effect = _SIDES.get((row.get("side") or "").strip().upper(), (None, None))
        effect_raw = (row.get("position_effect") or "").strip().upper()
        effect = {"OPEN": "OPEN", "OPENING": "OPEN", "开仓": "OPEN", "CLOSE": "CLOSE", "CLOSING": "CLOSE", "平仓": "CLOSE"}.get(effect_raw) or side_effect
        if side_effect and effect and effect != side_effect:
            raise JournalError("POSITION_EFFECT_CONFLICT", "买卖动作与来源开平仓字段冲突。")
        quantity = _number(row.get("quantity"), "quantity")
        price = _number(row.get("price"), "price")
        if kind == "ORDER" and price is None:
            price = _number(row.get("order_price"), "order_price")
        if kind == "FILL":
            if not side or quantity is None or decimal_value(quantity) <= 0 or price is None or decimal_value(price) < 0 or not instrument["symbol"]:
                raise JournalError("INCOMPLETE_EXECUTION", "逐笔成交缺少有效证券、方向、数量或价格。")
            if "price" not in fields:
                raise JournalError("EXECUTION_PRICE_REQUIRED", "逐笔成交不能使用订单均价。")
        total_fee = _number(row.get("fees"), "fees")
        ambiguous_fee = _number(row.get("ambiguous_fee"), "ambiguous_fee")
        fee_components = [_number(row.get(name), name) for name in ("commission", "platform_fee", "tax", "other_fee") if name in fields]
        fees_complete = total_fee is not None
        # A generic "Fees/费用" field may already aggregate commission and
        # platform charges. Neither using it as a complete total nor adding
        # it to separately shown components is supported by the label alone.
        if total_fee is None and ambiguous_fee is None and fee_components:
            total_fee = decimal_string(sum((decimal_value(value) for value in fee_components if value is not None), decimal_value("0")))
        # Component columns alone do not establish that every charge was included.
        source_record_id = (row.get("source_record_id") or "").strip() or (row.get("order_id") if kind == "ORDER" else None)
        if source_record_id and not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", source_record_id):
            raise JournalError("INVALID_SOURCE_RECORD_ID", "来源活动身份格式未验证。")
        identity = {"account_ref": account_ref, "activity_type": kind, "source_record_id": source_record_id} if source_record_id else {"account_ref": account_ref, "source_hash": content_hash, "row": offset, "activity_type": kind}
        record = {
            "record_id": "record-" + canonical_hash(identity), "source_record_id": source_record_id,
            "activity_type": kind, "account_ref": account_ref, "instrument": instrument,
            "side": side, "quantity": quantity, "price": price, "fees": total_fee, "amount": _number(row.get("amount"), "amount"),
            "fees_complete": fees_complete, "currency": instrument["currency"], "position_effect": effect,
            "occurred_at": occurred, "time_precision": precision, "source_timezone": verified_source_zone,
            "source_id": source_id, "as_of": as_of, "retrieved_at": retrieved_at,
            "source_hash": content_hash, "source_location": {"row": offset},
            "order_id": (row.get("order_id") or None) if re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", row.get("order_id") or "") else None,
            "status": ({"FILLED": "FILLED", "CANCELLED": "CANCELLED", "CANCELED": "CANCELLED", "PARTIALLY FILLED": "PARTIALLY_FILLED", "SUBMITTED": "SUBMITTED", "REJECTED": "REJECTED", "已成交": "FILLED", "已撤销": "CANCELLED", "部分成交": "PARTIALLY_FILLED"}.get((row.get("status") or "").strip().upper(), "UNKNOWN") if kind == "ORDER" else None),
            "related_source_record_id": (row.get("related_record_id") or None) if re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", row.get("related_record_id") or "") else None,
            "identity_status": "SOURCE_STABLE_ID" if source_record_id else "FILE_ROW_ONLY",
        }
        records.append(record)
    if not records:
        raise JournalError("EMPTY_EXPORT_UNPROVEN", "导出没有可核验活动；空列表不能证明期间完整。")
    return records
