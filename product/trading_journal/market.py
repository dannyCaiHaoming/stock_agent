"""独立日线只读获取；无账户字段、认证材料、Runtime 或模型依赖。

默认匿名 Yahoo 图表 GET 的历史价格口径未获证明，不能与券商原价混画。
可靠适配器可交付 UNADJUSTED 或可靠逐日展示因子；未知口径保留时间线。
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError, canonical_hash, utc_now

ADAPTER_VERSION = "journal-daily-market/1.0.0"
MAX_BYTES = 16 * 1024 * 1024
MAX_SEGMENT_DAYS = 366
_MAC_SYSTEM_CA = "/etc/ssl/cert.pem"


def _day(value: str | date) -> date:
    try:
        return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        raise JournalError("MARKET_DATE_INVALID", "行情日期无效") from None


def _number(value, *, positive=False) -> str:
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or positive and number <= 0:
            raise ValueError
        return format(number, "f")
    except (ValueError, TypeError, InvalidOperation):
        raise JournalError("MARKET_NUMBER_INVALID", "行情数值无效") from None


def _identity(instrument: dict) -> dict:
    symbol = instrument.get("underlying") if instrument.get("asset_type") == "OPTION" else instrument.get("symbol")
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9.^-]{0,24}", symbol):
        raise JournalError("MARKET_SYMBOL_UNSUPPORTED", "标的代码缺失或未受支持")
    market = str(instrument.get("market") or "UNKNOWN").upper()
    symbol = symbol.upper()
    if market in {"HK", "HONG_KONG", "HKEX"} and symbol.isdigit():
        code = int(symbol)
        if not 1 <= code <= 99999:
            raise JournalError("MARKET_SYMBOL_UNSUPPORTED", "港股数字代码不在支持范围")
        symbol = str(code).zfill(4) + ".HK"
    if market in {"CN", "CHINA", "A_SHARE", "SSE", "SZSE"} and not symbol.endswith((".SS", ".SZ")):
        raise JournalError("MARKET_SYMBOL_MAPPING_UNKNOWN", "A股代码需要明确 .SS 或 .SZ 身份，不猜交易所")
    return {"symbol": symbol, "underlying": instrument.get("underlying"),
            "instrument_key": instrument.get("key"), "market": market,
            "currency": instrument.get("currency"), "exchange_timezone": instrument.get("exchange_timezone")}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise JournalError("MARKET_REDIRECT_REJECTED", "行情请求发生重定向，已停止")


def _ca_path_available(path: str | None, *, directory: bool = False) -> bool:
    if not path:
        return False
    try:
        mode = Path(path).stat().st_mode
    except FileNotFoundError:
        return False
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        return False
    if not os.access(path, os.R_OK | (os.X_OK if directory else 0)):
        raise PermissionError("Certificate path is not readable")
    return True


def _https_context() -> ssl.SSLContext:
    """仅缺少 Python 默认 CA 的 Mac 使用系统 CA，不覆盖用户证书配置。"""
    if sys.platform == "darwin" and not any(key in os.environ for key in ("SSL_CERT_FILE", "SSL_CERT_DIR")):
        paths = ssl.get_default_verify_paths()
        cafile_available = _ca_path_available(paths.cafile or paths.openssl_cafile)
        capath_available = _ca_path_available(paths.capath or paths.openssl_capath, directory=True)
        if not cafile_available and not capath_available:
            if not _ca_path_available(_MAC_SYSTEM_CA):
                raise FileNotFoundError("System certificate bundle is unavailable")
            return ssl.create_default_context(cafile=_MAC_SYSTEM_CA)
    return ssl.create_default_context()


def yahoo_get(query: dict) -> dict:
    """固定匿名端点，一次 GET、无 Cookie/认证/重试，不接受任意 URL。"""
    if set(query) != {"symbol", "start", "end"} or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^-]{0,24}", query["symbol"]):
        raise JournalError("MARKET_QUERY_REJECTED", "行情查询字段不在白名单")
    start, end = _day(query["start"]), _day(query["end"])
    if not 0 <= (end - start).days < MAX_SEGMENT_DAYS:
        raise JournalError("MARKET_RANGE_REJECTED", "单次行情日期范围超限")
    period1 = int(datetime.combine(start, datetime.min.time(), UTC).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), UTC).timestamp())
    params = urlencode({"period1": period1, "period2": period2, "interval": "1d",
                        "events": "div,splits", "includePrePost": "false", "includeAdjustedClose": "true"})
    # ^、数字及点只用于已验证的证券代码，不能改变 host/path/query。
    symbol = query["symbol"].replace("^", "%5E")
    request = Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}",
                      headers={"Accept": "application/json", "User-Agent": "TradeJournal/1.0"}, method="GET")
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=_https_context())).open(request, timeout=20) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise JournalError("MARKET_RESPONSE_TOO_LARGE", "行情响应超限")
    except (HTTPError, URLError, OSError):
        raise JournalError("MARKET_TRANSPORT_FAILED", "公开行情读取失败；成交账本不受影响") from None
    try:
        payload = json.loads(raw)
        result = payload["chart"]["result"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        raise JournalError("MARKET_FORMAT_UNKNOWN", "行情响应格式无法核验") from None
    return {"provider_result": result, "raw_content_hash": hashlib.sha256(raw).hexdigest()}


def _normalize_provider(response: dict, identity: dict, retrieved_at: str) -> dict:
    """仅标准化公开行情，不将 provider OHLC 的复权声明升级为已验证原价。"""
    result = response["provider_result"]
    meta = result.get("meta") or {}
    timezone = meta.get("exchangeTimezoneName") or identity.get("exchange_timezone")
    try:
        zone = ZoneInfo(timezone)
    except (TypeError, ZoneInfoNotFoundError):
        raise JournalError("MARKET_TIMEZONE_UNKNOWN", "行情缺少可靠交易所时区") from None
    currency = meta.get("currency")
    if meta.get("symbol") and str(meta["symbol"]).upper() != identity["symbol"]:
        raise JournalError("MARKET_SYMBOL_MISMATCH", "行情标的身份与查询不一致")
    if identity.get("exchange_timezone") and timezone != identity["exchange_timezone"]:
        raise JournalError("MARKET_TIMEZONE_MISMATCH", "行情时区与证券身份不一致")
    if identity.get("currency") and currency and currency != identity["currency"]:
        raise JournalError("MARKET_CURRENCY_MISMATCH", "行情与证券币种不一致")
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    candles, gaps, events = [], [], []
    for index, stamp in enumerate(result.get("timestamp") or []):
        timestamp = datetime.fromtimestamp(stamp, UTC)
        day = timestamp.astimezone(zone).date().isoformat()
        values = {}
        try:
            for key in ("open", "high", "low", "close", "volume"):
                values[key] = _number(quote[key][index], positive=key != "volume")
            if Decimal(values["high"]) < max(Decimal(values[key]) for key in ("open", "low", "close")) or Decimal(values["low"]) > min(Decimal(values[key]) for key in ("open", "high", "close")):
                raise ValueError
        except (JournalError, KeyError, IndexError, TypeError, ValueError):
            gaps.append({"date": day, "reason": "OHLCV_MISSING_OR_INVALID"})
            continue
        candles.append({"date": day, **values, "provider_timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                        "available_at": None, "session": "REGULAR_DAILY_PROVIDER",
                        "source_id": "yahoo-public-chart", "as_of": day, "retrieved_at": retrieved_at})
    for source_kind, kind in (("splits", "SPLIT"), ("dividends", "DIVIDEND")):
        for item in (result.get("events", {}).get(source_kind) or {}).values():
            day = datetime.fromtimestamp(item["date"], UTC).astimezone(zone).date().isoformat()
            event = {"date": day, "event_type": kind, "source_id": "yahoo-public-chart", "as_of": day, "retrieved_at": retrieved_at}
            if kind == "SPLIT":
                event["numerator"], event["denominator"] = _number(item.get("numerator"), positive=True), _number(item.get("denominator"), positive=True)
            else:
                event["amount"] = _number(item.get("amount"))
            events.append(event)
    return {"candles": candles, "events": events, "gaps": gaps,
            "symbol": identity["symbol"], "exchange_timezone": timezone, "currency": currency or identity.get("currency"),
            "price_basis": "PROVIDER_UNVERIFIED", "adjustment_factors": [],
            "price_basis_evidence": None, "source_id": "yahoo-public-chart",
            "raw_content_hash": response.get("raw_content_hash") or canonical_hash(result),
            "session_calendar": None}


def fetch_market(instrument: dict, start: str, end: str, *, transport=None, now=None,
                 request_budget: int = 24, context_sessions: int = 60) -> dict:
    """冻结日线；自定义 transport(query) 只得到证券代码和日期。

    start/end 均为包含的交易日期。请求额外约60交易日上下文（120日历日）；
    实际交易日数不足时披露，不以工作日伪造交易日历。历史分段失败保留 gap。
    返回包不包含 instrument 以外的私人成交/账户字段，保存由调用者负责。
    """
    first, last = _day(start), _day(end)
    if first > last or (last - first).days > 36525 or not isinstance(request_budget, int) or isinstance(request_budget, bool) or not 1 <= request_budget <= 120 or not 0 <= context_sessions <= 120:
        raise JournalError("MARKET_RANGE_REJECTED", "行情查询日期或请求预算无效")
    retrieved_at = now or utc_now()
    if isinstance(retrieved_at, datetime):
        retrieved_at = retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    identity = _identity(instrument)
    package = {"kind": "TradeJournalMarket", "schema_version": "1.0.0", **identity,
               "adapter_version": ADAPTER_VERSION, "interval": "1d", "source_id": "journal-market",
               "as_of": last.isoformat(), "retrieved_at": retrieved_at,
               "requested_range": {"start": first.isoformat(), "end": last.isoformat()},
               "context_sessions_requested": context_sessions, "candles": [], "events": [], "gaps": [],
               "segments": [], "price_basis": "UNKNOWN", "adjustment_factors": [], "price_basis_evidence": None,
               "session": "REGULAR_DAILY", "session_calendar": None}
    send, cursor, count = transport or yahoo_get, first - timedelta(days=context_sessions * 2), 0
    bases, zones, seen, event_seen, factors = set(), set(), {}, {}, {}
    while cursor <= last:
        segment_end = min(last, cursor + timedelta(days=MAX_SEGMENT_DAYS - 1))
        if count >= request_budget:
            package["gaps"].append({"start": cursor.isoformat(), "end": last.isoformat(), "reason": "MARKET_REQUEST_BUDGET_EXHAUSTED"})
            break
        count += 1
        query = {"symbol": identity["symbol"], "start": cursor.isoformat(), "end": segment_end.isoformat()}
        segment = {"query": query, "request_number": count}
        try:
            response = send(dict(query))
            normalized = _normalize_provider(response, identity, retrieved_at) if "provider_result" in response else response
            if not isinstance(normalized, dict) or not isinstance(normalized.get("candles"), list):
                raise JournalError("MARKET_FORMAT_UNKNOWN", "行情响应不是可核验日线包")
            basis = normalized.get("price_basis", "UNKNOWN")
            proof = normalized.get("price_basis_evidence")
            if basis in {"UNADJUSTED", "ADJUSTED_WITH_FACTORS"} and not (isinstance(proof, dict) and all(proof.get(key) for key in ("source_id", "as_of", "retrieved_at"))):
                basis = "PROVIDER_UNVERIFIED"
            timezone = normalized.get("exchange_timezone") or identity.get("exchange_timezone")
            ZoneInfo(timezone)
            if identity.get("exchange_timezone") and timezone != identity["exchange_timezone"]:
                raise JournalError("MARKET_TIMEZONE_MISMATCH", "行情时区不匹配")
            if normalized.get("symbol") and str(normalized["symbol"]).upper() != identity["symbol"]:
                raise JournalError("MARKET_SYMBOL_MISMATCH", "行情标的身份不匹配")
            if identity.get("currency") and normalized.get("currency") and normalized["currency"] != identity["currency"]:
                raise JournalError("MARKET_CURRENCY_MISMATCH", "行情币种不匹配")
            local_candles = []
            for row in normalized["candles"]:
                day = _day(row["date"]).isoformat()
                if not cursor.isoformat() <= day <= segment_end.isoformat():
                    continue
                values = {key: _number(row.get(key), positive=key != "volume") for key in ("open", "high", "low", "close", "volume")}
                if Decimal(values["high"]) < max(Decimal(values[key]) for key in ("open", "low", "close")) or Decimal(values["low"]) > min(Decimal(values[key]) for key in ("open", "high", "close")):
                    raise JournalError("MARKET_OHLC_INVALID", "行情开高低收关系错误")
                source = row.get("source_id") or normalized.get("source_id") or "journal-market"
                candle = {"date": day, **values, "source_id": source, "as_of": row.get("as_of") or day,
                          "retrieved_at": row.get("retrieved_at") or retrieved_at,
                          "available_at": row.get("available_at"), "session": row.get("session", "REGULAR_DAILY_PROVIDER")}
                if day in seen and seen[day] != candle:
                    raise JournalError("MARKET_DUPLICATE_SESSION_CONFLICT", "重复行情日期内容不同")
                local_candles.append(candle)
            local_events, local_factors = {}, {}
            for event in normalized.get("events", []):
                if cursor.isoformat() <= str(event.get("date", "")) <= segment_end.isoformat():
                    local_events[canonical_hash(event)] = {**event, "source_id": event.get("source_id") or normalized.get("source_id") or "journal-market", "as_of": event.get("as_of") or event.get("date"), "retrieved_at": event.get("retrieved_at") or retrieved_at}
            for factor in normalized.get("adjustment_factors", []):
                day, value = _day(factor["date"]).isoformat(), _number(factor["factor"], positive=True)
                if cursor.isoformat() <= day <= segment_end.isoformat():
                    local_factors[day] = {"date": day, "factor": value}
            # 整段校验完成才合并，失败段不留下价格、公司行动或因子。
            seen.update({row["date"]: row for row in local_candles})
            event_seen.update(local_events)
            factors.update(local_factors)
            bases.add(basis)
            zones.add(timezone)
            package["gaps"].extend(normalized.get("gaps", []))
            if proof:
                package["price_basis_evidence"] = proof
            if normalized.get("session_calendar"):
                package["session_calendar"] = normalized["session_calendar"]
            segment.update(status="FETCHED", source_id=normalized.get("source_id", "journal-market"), raw_content_hash=normalized.get("raw_content_hash") or canonical_hash(normalized), as_of=segment_end.isoformat(), retrieved_at=retrieved_at, count=len(local_candles))
        except Exception as exc:
            # 外部错误正文可能携带任意数据，不直接进入日志或图表。
            code = getattr(exc, "code", None) or "MARKET_SEGMENT_FAILED"
            segment.update(status="FAILED", reason=code)
            package["gaps"].append({"start": cursor.isoformat(), "end": segment_end.isoformat(), "reason": code})
        package["segments"].append(segment)
        cursor = segment_end + timedelta(days=1)
    package["candles"] = sorted(seen.values(), key=lambda item: item["date"])
    package["events"] = sorted(event_seen.values(), key=lambda item: item.get("date", ""))
    package["adjustment_factors"] = sorted(factors.values(), key=lambda item: item["date"])
    package["price_basis"] = next(iter(bases)) if len(bases) == 1 else "UNKNOWN"
    if len(zones) == 1:
        package["exchange_timezone"] = next(iter(zones))
    elif len(zones) > 1:
        package["gaps"].append({"reason": "MARKET_TIMEZONE_CONFLICT"})
        package["price_basis"] = "UNKNOWN"
    if package["price_basis"] not in {"UNADJUSTED", "ADJUSTED_WITH_FACTORS"}:
        package["gaps"].append({"reason": "PRICE_BASIS_UNVERIFIED", "detail": "行情历史复权口径未证实；成交仅作时间注释，原价保留明细"})
    if not package["session_calendar"]:
        package["gaps"].append({"reason": "SESSION_CALENDAR_UNAVAILABLE", "detail": "未取得历史交易日历，不能用工作日判断缺K线或精确常规时段"})
    else:
        calendar = package["session_calendar"]
        sessions = calendar.get("sessions", []) if isinstance(calendar, dict) else calendar
        for session in sessions:
            day = session.get("date")
            if first.isoformat() <= str(day) <= last.isoformat() and day not in seen:
                package["gaps"].append({"date": day, "reason": "KNOWN_SESSION_BAR_MISSING"})
    if any(row.get("available_at") is None for row in package["candles"]):
        package["gaps"].append({"reason": "DAILY_BAR_AVAILABILITY_UNKNOWN", "detail": "历史日K完整可用时刻未获核验，不能用于证明交易当时已知的完整OHLCV"})
    actual_context = sum(row["date"] < first.isoformat() for row in package["candles"])
    package["context_sessions_available"] = actual_context
    if actual_context < context_sessions:
        package["gaps"].append({"reason": "CONTEXT_SHORT", "requested": context_sessions, "available": actual_context})
    if not package["candles"]:
        package["gaps"].append({"reason": "NO_RELIABLE_OHLCV"})
    package["content_hash"] = canonical_hash(package)
    return package
