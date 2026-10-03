"""Local, allowlisted adapter for verified Tiger multi-section CSV statements.

Only the child DATA rows of a reconciled trade group are individual fills.
Identifying sections, descriptions, parent summaries and TOTAL rows never
leave this parser. No source row is used as a diagnostic message.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError, canonical_hash, decimal_string, decimal_value
from .normalization import MAX_BYTES, MAX_ROWS, _instrument, _number, _read_source, _source_time, _validate_references

_TRADE_PREFIX = ("交易明细", "", "", "")
_BASE_COLUMNS = ("代码", "市场", "交易所", "交易类型", "数量", "交易价格", "成交额")
# Repeated labels are distinct positional components in this official format.
# Neither occurrence of 交易费用 is a total-fee column.
_FEE_COLUMNS = (
    "交易费用", "其他代收", "结算费", "证监会费", "期权监管费", "印花税", "交易征费", "清算费",
    "交易活动费", "交易所费用", "期货监管费", "佣金", "平台费", "期权交收费", "申购费用",
    "赎回费用", "转换费用", "菲律宾股票交易税", "税收服务费", "会计及财汇局交易征费",
    "交易系统使用费", "交易费用", "佣金费用", "经手费", "证管费", "过户费(中国结算)",
    "过户费(香港结算)", "借券印花税", "综合审计追踪费", "处理费", "清结算指令费",
    "DVP指令附加费", "IPO-中签交易费", "IPO-中签手续费", "IPO账户结算费", "IPO-手续费",
)
_TAIL_COLUMNS = ("消费税", "已实现的损益", "说明", "成交时间", "交收日期", "币种")
_OPTION_HEADER = _TRADE_PREFIX + _BASE_COLUMNS + _FEE_COLUMNS + _TAIL_COLUMNS
_STOCK_HEADER = _TRADE_PREFIX + _BASE_COLUMNS + ("成交应计利息",) + _FEE_COLUMNS + _TAIL_COLUMNS
_PRODUCT_HEADER = ("金融产品信息", "", "", "", "代码", "发行人", "描述", "倍数", "期限", "行权价", "类型")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.^:/_-]{0,29}")
_DISPLAY_CODE = re.compile(r"([^()]*)\(([^()]+)\)")
_OPTION_CODE = re.compile(r"([A-Z0-9][A-Z0-9.^:/_-]{0,29}) (\d{8}) (CALL|PUT) (\d+(?:\.\d+)?)")
_TIME = re.compile(r"(\d{4}-\d{2}-\d{2}(?: |\r?\n)\d{2}:\d{2}:\d{2}), ([A-Za-z0-9_+./-]+)")
_NON_REQUESTED = frozenset({"FUND", "基金", "外汇", "外匯", "FOREX", "FX"})
# One displayed minor unit, covering the observed official rounding. No
# unverified monetary precision is guessed for other source currencies.
_AMOUNT_TOLERANCE = {"USD": Decimal("0.01"), "HKD": Decimal("0.01")}


def _rows(decoded: str):
    """Yield the original physical start row, including discarded sections."""
    reader = csv.reader(io.StringIO(decoded, newline=""), delimiter=",", strict=True)
    previous_end = 0
    try:
        for count, cells in enumerate(reader, start=1):
            if count > MAX_ROWS:
                raise JournalError("CSV_LIMIT", "来源行数超过单批预算。")
            start = previous_end + 1
            previous_end = reader.line_num
            yield start, cells
    except csv.Error:
        raise JournalError("UNKNOWN_STATEMENT_FORMAT", "官方账单 CSV 结构无效。") from None


def is_statement(data: bytes) -> bool:
    """Identify UTF-8 statements by a full, verified trade-section header."""
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        return False
    try:
        decoded = data.decode("utf-8-sig")
        return any(tuple(cells) in (_STOCK_HEADER, _OPTION_HEADER) for _, cells in _rows(decoded))
    except (UnicodeDecodeError, JournalError):
        return False


def parse_statement(path: str | Path, account_ref: str, source_id: str, as_of: str, retrieved_at: str) -> list[dict]:
    """Parse only this verified statement contract; retain no raw identity."""
    _validate_references(account_ref, source_id, as_of, retrieved_at)
    data, decoded, content_hash = _read_source(path)
    if not is_statement(data):
        raise JournalError("UNKNOWN_STATEMENT_FORMAT", "官方多区段账单格式未验证。")
    return _parse_statement(decoded, content_hash=content_hash, account_ref=account_ref,
                            source_id=source_id, as_of=as_of, retrieved_at=retrieved_at)


def _asset_type(raw: str) -> str | None:
    if raw == "期权":
        return "OPTION"
    if raw == "股票":
        return "STOCK"
    # Asset section labels are exact enumerations, not substring guesses.
    if raw == "ETF":
        return "ETF"
    if raw.upper() in _NON_REQUESTED:
        return None
    raise JournalError("UNKNOWN_STATEMENT_ASSET", "账单交易资产类别未验证。")


def _display_symbol(raw: str, asset: str) -> dict:
    match = _DISPLAY_CODE.fullmatch(raw.strip())
    if not match:
        raise JournalError("INVALID_SYMBOL", "账单展示代码格式未验证。")
    display_name, code = (value.strip() for value in match.groups())
    if asset != "OPTION":
        if not _SYMBOL.fullmatch(code):
            raise JournalError("INVALID_SYMBOL", "账单证券代码格式未验证。")
        # An explicit ETF name in the stock source section is a source
        # self-label, including leveraged/inverse ETFs; no ticker list is used.
        if (asset == "STOCK" and re.search(r"(?<![A-Za-z])ETF(?![A-Za-z])", display_name, re.IGNORECASE)
                and not re.search(r"(?:(?:非|不是|不属于)\s*|NOT(?:\s+AN?)?\s+)ETF", display_name, re.IGNORECASE)):
            asset = "ETF"
        return {"symbol": code, "asset_type": asset}
    option = _OPTION_CODE.fullmatch(code)
    if not option:
        raise JournalError("INVALID_OPTION_IDENTITY", "账单期权合约格式未验证。")
    underlying, compact_expiry, right, raw_strike = option.groups()
    try:
        expiry = datetime.strptime(compact_expiry, "%Y%m%d").date().isoformat()
    except ValueError:
        raise JournalError("INVALID_OPTION_EXPIRY", "账单期权到期日无效。") from None
    strike = _required_number(raw_strike, "strike")
    if strike <= 0:
        raise JournalError("INVALID_OPTION_IDENTITY", "账单期权行权价必须大于零。")
    strike_text = decimal_string(strike)
    return {"symbol": f"{underlying}_{compact_expiry}_{right}_{strike_text}", "asset_type": "OPTION",
            "underlying": underlying, "expiry": expiry, "right": right, "strike": strike_text,
            "adjustment_status": "UNKNOWN"}


def _required_number(raw: str, field: str) -> Decimal:
    value = _number(raw, field)
    if value is None:
        raise JournalError("INCOMPLETE_STATEMENT_DETAIL", "账单交易明细缺少必要数值。")
    return decimal_value(value, field=field)


def _source_timestamp(raw: str) -> tuple[str, str]:
    match = _TIME.fullmatch(raw.strip())
    if not match:
        raise JournalError("UNKNOWN_TIME_FORMAT", "账单成交时间必须明确包含秒与来源时区。")
    local, source_zone = match.groups()
    # The official quoted cell may put time on the next display line.
    local = local.replace("\r\n", " ").replace("\n", " ")
    zone = {"US/Eastern": "America/New_York", "GMT+8": "Etc/GMT-8"}.get(source_zone, source_zone)
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise JournalError("INVALID_TIMEZONE", "账单逐行来源时区无效。") from None
    try:
        occurred, precision = _source_time(local, zone)
    except JournalError as exc:
        raise JournalError(exc.code, "账单逐行成交时间无效或处于夏令时歧义区间。") from None
    if precision != "SECOND":
        raise JournalError("UNKNOWN_TIME_FORMAT", "账单逐笔成交时间精度未验证。")
    return occurred, zone


def _product_key(underlying: str, expiry: str, strike: str, right: str) -> tuple[str, str, str, str]:
    return underlying, expiry, strike, right


def _product(cells: list[str], header: tuple[str, ...] | None) -> tuple[tuple[str, str, str, str], str | None]:
    if header != _PRODUCT_HEADER or len(cells) != len(_PRODUCT_HEADER):
        raise JournalError("UNKNOWN_STATEMENT_FORMAT", "期权金融产品信息列结构未验证。")
    code = cells[4].strip()
    if not _SYMBOL.fullmatch(code):
        code = _display_symbol(code, "STOCK")["symbol"]
    raw_expiry = cells[8].strip()
    try:
        if re.fullmatch(r"\d{8}", raw_expiry):
            expiry = datetime.strptime(raw_expiry, "%Y%m%d").date().isoformat()
        elif re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2}", raw_expiry):
            expiry = date.fromisoformat(raw_expiry.replace("/", "-")).isoformat()
        else:
            raise ValueError
    except ValueError:
        raise JournalError("INVALID_OPTION_EXPIRY", "期权金融产品信息到期日无效。") from None
    strike = decimal_string(_required_number(cells[9], "strike"))
    right = {"C": "CALL", "CALL": "CALL", "P": "PUT", "PUT": "PUT", "认购": "CALL", "认沽": "PUT"}.get(cells[10].strip().upper())
    if not right or decimal_value(strike) <= 0:
        raise JournalError("INVALID_OPTION_IDENTITY", "期权金融产品身份字段未验证。")
    multiplier = _number(cells[7], "multiplier")
    if multiplier is not None and decimal_value(multiplier) <= 0:
        raise JournalError("INVALID_MULTIPLIER", "期权金融产品乘数必须大于零。")
    return _product_key(code, expiry, strike, right), multiplier


def _detail(cells: list[str], row: int, header: tuple[str, ...], asset: str) -> dict:
    expected = _OPTION_HEADER if asset == "OPTION" else _STOCK_HEADER
    if header != expected or len(cells) != len(header):
        raise JournalError("UNKNOWN_STATEMENT_FORMAT", "交易明细列结构与资产类别不一致。")
    # Ordinary columns are unique; fee columns deliberately retain positions.
    fields = {name: cells[index].strip() for index, name in enumerate(header) if index >= 4 and name not in _FEE_COLUMNS}
    fee_start = 4 + len(_BASE_COLUMNS) + (0 if asset == "OPTION" else 1)
    fee_values = [_required_number(cells[index], "fee_component") for index in range(fee_start, fee_start + len(_FEE_COLUMNS))]
    tax = _number(fields["消费税"], "tax")
    fee_values.append(decimal_value(tax) if tax is not None else None)
    if any(value is not None and value > 0 for value in fee_values):
        raise JournalError("UNKNOWN_STATEMENT_FEE_SIGN", "账单费用现金符号与已验证格式不一致。")
    quantity = _required_number(fields["数量"], "quantity")
    price = _required_number(fields["交易价格"], "price")
    amount = _required_number(fields["成交额"], "amount")
    if quantity == 0 or price < 0:
        raise JournalError("INCOMPLETE_EXECUTION", "账单成交数量或价格无效。")
    return {"row": row, "asset": asset, "fields": fields, "quantity": quantity, "price": price,
            "amount": amount, "fee_values": fee_values,
            "interest": _required_number(fields["成交应计利息"], "accrued_interest") if asset != "OPTION" else None}


def _validate_group(parent: dict, children: list[dict]) -> None:
    if not children:
        raise JournalError("STATEMENT_DETAIL_REQUIRED", "账单父汇总缺少逐笔成交子行。")
    if any((item["quantity"] > 0) != (parent["quantity"] > 0) for item in children):
        raise JournalError("STATEMENT_DIRECTION_CONFLICT", "账单父子成交方向冲突。")
    for field in ("quantity", "amount"):
        if sum((item[field] for item in children), Decimal(0)) != parent[field]:
            raise JournalError("STATEMENT_RECONCILIATION_FAILED", "账单父子数量或成交额勾稽失败。")
    for index, value in enumerate(parent["fee_values"]):
        components = [item["fee_values"][index] for item in children]
        # Blank consumption tax is unknown, never zero. Its unknownness must
        # agree throughout the group; a partial tax subtotal cannot reconcile.
        if value is None:
            reconciled = all(component is None for component in components)
        else:
            reconciled = all(component is not None for component in components) and sum(components, Decimal(0)) == value
        if not reconciled:
            raise JournalError("STATEMENT_RECONCILIATION_FAILED", "账单父子费用或消费税缺值模式勾稽失败。")
    if parent["interest"] is not None and sum((item["interest"] for item in children), Decimal(0)) != parent["interest"]:
        raise JournalError("STATEMENT_RECONCILIATION_FAILED", "账单父子成交应计利息勾稽失败。")


def _validate_price_amount(item: dict, instrument: dict) -> None:
    if item["amount"] != 0 and (item["amount"] > 0) != (item["quantity"] > 0):
        raise JournalError("STATEMENT_PRICE_AMOUNT_CONFLICT", "逐笔成交额符号与来源数量方向冲突。")
    multiplier = instrument["multiplier"]
    if multiplier is None:
        return  # An unknown option multiplier remains unknown; never use 100.
    tolerance = _AMOUNT_TOLERANCE.get(instrument["currency"])
    if tolerance is None:
        raise JournalError("STATEMENT_AMOUNT_PRECISION_UNKNOWN", "该来源币种的成交额舍入精度未验证。")
    # 成交额 is signed gross notional in this source, not signed cash flow.
    expected = item["quantity"] * item["price"] * decimal_value(multiplier, field="multiplier")
    if abs(item["amount"] - expected) > tolerance:
        raise JournalError("STATEMENT_PRICE_AMOUNT_CONFLICT", "逐笔成交价格、数量、乘数与来源成交额冲突。")


def _parse_statement(decoded: str, *, content_hash: str, account_ref: str, source_id: str,
                     as_of: str, retrieved_at: str) -> list[dict]:
    groups = []
    multipliers = {}
    trade_header = product_header = None
    parent = None
    children = []

    def finish_group():
        nonlocal parent, children
        if parent is not None:
            _validate_group(parent, children)
            groups.append((parent, children))
        parent, children = None, []

    for row_number, cells in _rows(decoded):
        if not cells or not any(item.strip() for item in cells):
            continue
        section = cells[0]
        if section != "交易明细":
            finish_group()
            if section == "金融产品信息":
                if tuple(cells[:4]) == _PRODUCT_HEADER[:4]:
                    product_header = tuple(cells)
                elif len(cells) >= 4 and cells[1] == "期权" and cells[3] == "DATA":
                    key, multiplier = _product(cells, product_header)
                    if key in multipliers and multipliers[key] != multiplier:
                        raise JournalError("OPTION_MULTIPLIER_CONFLICT", "相同期权身份存在冲突的来源乘数。")
                    multipliers[key] = multiplier
            continue
        if tuple(cells[:4]) == _TRADE_PREFIX:
            finish_group()
            trade_header = tuple(cells)
            continue
        if len(cells) < 4 or cells[2] != "":
            raise JournalError("UNKNOWN_STATEMENT_FORMAT", "交易明细区段行结构未验证。")
        if cells[3] == "TOTAL":
            finish_group()
            continue
        asset = _asset_type(cells[1])
        if asset is None:
            finish_group()
            continue
        if cells[3] != "DATA" or trade_header is None:
            raise JournalError("UNKNOWN_STATEMENT_FORMAT", "交易明细行角色或表头未验证。")
        item = _detail(cells, row_number, trade_header, asset)
        if item["fields"]["代码"]:
            finish_group()
            parent = item
        else:
            if parent is None:
                raise JournalError("STATEMENT_ORPHAN_DETAIL", "账单逐笔成交子行缺少父证券汇总。")
            if asset != parent["asset"]:
                raise JournalError("STATEMENT_IDENTITY_CONFLICT", "账单父子资产身份冲突。")
            children.append(item)
    finish_group()

    records = []
    for parent, children in groups:
        fields = parent["fields"]
        identity_fields = _display_symbol(fields["代码"], parent["asset"])
        if parent["asset"] == "OPTION":
            key = _product_key(*(identity_fields[name] for name in ("underlying", "expiry", "strike", "right")))
            identity_fields["multiplier"] = multipliers.get(key)
        parent_instrument = _instrument({**identity_fields, "market": fields["市场"], "currency": fields["币种"]}, None)
        if not parent_instrument["market"] or not parent_instrument["currency"]:
            raise JournalError("INCOMPLETE_EXECUTION", "账单父证券缺少可核验的市场或币种。")
        for item in children:
            detail_fields = item["fields"]
            row_instrument = _instrument({**identity_fields, "market": detail_fields["市场"] or fields["市场"],
                                          "currency": detail_fields["币种"] or fields["币种"]}, None)
            if row_instrument["key"] != parent_instrument["key"]:
                raise JournalError("STATEMENT_IDENTITY_CONFLICT", "账单父子市场或币种冲突。")
            _validate_price_amount(item, row_instrument)
            trade_type = detail_fields["交易类型"] or fields["交易类型"]
            if detail_fields["交易类型"] and fields["交易类型"] != trade_type:
                raise JournalError("POSITION_EFFECT_CONFLICT", "账单父子开平仓字段冲突。")
            effect = {"开仓": "OPEN", "平仓": "CLOSE", "开仓做空": "OPEN"}.get(trade_type)
            if effect is None:
                raise JournalError("UNKNOWN_STATEMENT_TRADE_TYPE", "账单交易类型未验证。")
            side = "BUY" if item["quantity"] > 0 else "SELL"
            if trade_type == "开仓做空" and side != "SELL":
                raise JournalError("POSITION_EFFECT_CONFLICT", "账单开仓做空与成交方向冲突。")
            occurred, source_zone = _source_timestamp(detail_fields["成交时间"])
            source_identity = {"account_ref": account_ref, "source_hash": content_hash,
                               "row": item["row"], "activity_type": "FILL"}
            records.append({
                "record_id": "record-" + canonical_hash(source_identity), "source_record_id": None,
                "activity_type": "FILL", "account_ref": account_ref, "instrument": row_instrument,
                "side": side, "quantity": decimal_string(abs(item["quantity"])), "price": decimal_string(item["price"]),
                "amount": decimal_string(item["amount"]),
                "fees": (None if any(value is None for value in item["fee_values"])
                         else decimal_string(-sum(item["fee_values"], Decimal(0)))),
                "fees_complete": False, "currency": row_instrument["currency"], "position_effect": effect,
                "occurred_at": occurred, "time_precision": "SECOND", "source_timezone": source_zone,
                "source_id": source_id, "as_of": as_of, "retrieved_at": retrieved_at, "source_hash": content_hash,
                "source_location": {"row": item["row"], "parent_row": parent["row"], "section": "交易明细"},
                "order_id": None, "status": None, "related_source_record_id": None, "identity_status": "FILE_ROW_ONLY",
            })
    if not records:
        raise JournalError("EMPTY_EXPORT_UNPROVEN", "账单没有可核验的请求资产逐笔成交。")
    return records
