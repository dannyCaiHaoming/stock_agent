"""非实时行情标准化。SDK 延迟导入；默认不发起任何请求。"""
from datetime import date
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
import hashlib
import json

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp

MARKET_VERSION = "yahoo-eod-adapter/0.2.0"
RESEARCH_SERIES_VERSION = "yahoo-research-series/1.0.0"
YFINANCE_VERSION = "1.7.0"
CALENDAR_VERSION = "4.13.2"


class ExchangeCalendar:
    """只读本地交易日历，不以工作日猜测假日、DST 或提前收盘。"""
    def __init__(self, *, start: str, end: str):
        if version("exchange-calendars") != CALENDAR_VERSION:
            raise ValueError("LIVE_CALENDAR_VERSION_MISMATCH")
        import exchange_calendars as xcals
        self._calendar = xcals.get_calendar("XNYS", start=start, end=end)
        self.version = f"exchange-calendars/{CALENDAR_VERSION}/XNYS"
        self.start, self.end = start, end
        schedule = self._calendar.schedule
        self._closes = {str(index.date()): iso_utc(row["close"].to_pydatetime()) for index, row in schedule.iterrows()}
        self.content_hash = content_hash({"version": self.version, "start": start, "end": end, "closes": self._closes})

    def session_close(self, day: str) -> str | None:
        if not self.start <= day <= self.end:
            raise ValueError("LIVE_CALENDAR_RANGE_MISSING")
        return self._closes.get(day)

    def completed_sessions(self, cutoff):
        if not self.start <= cutoff.date().isoformat() <= self.end:
            raise ValueError("LIVE_CALENDAR_RANGE_MISSING")
        return [close for close in self._closes.values() if parse_timestamp(close) <= cutoff]

    def lock_record(self) -> dict:
        return {"version": self.version, "start": self.start, "end": self.end, "content_hash": self.content_hash}


def load_locked_calendar(record: dict) -> ExchangeCalendar:
    if set(record) != {"version", "start", "end", "content_hash"}:
        raise ValueError("LIVE_CALENDAR_LOCK_INVALID")
    calendar = ExchangeCalendar(start=record["start"], end=record["end"])
    if calendar.lock_record() != record:
        raise ValueError("LIVE_CALENDAR_LOCK_DRIFT")
    return calendar


def normalize_daily_rows(rows: list[dict], *, security_id: str, ticker: str,
                         retrieved_at: str, calendar, raw_content_hash: str, currency: str) -> dict:
    if currency != "USD":
        raise ValueError("YAHOO_CURRENCY_UNSUPPORTED")
    retrieved = parse_timestamp(retrieved_at)
    evidence, gaps, seen = [], [], set()
    for row in rows:
        day = row["date"]
        if day in seen:
            raise ValueError("YAHOO_DUPLICATE_SESSION")
        seen.add(day)
        close_at = calendar.session_close(day)
        if close_at is None or parse_timestamp(close_at) > retrieved:
            gaps.append({"date": day, "reason": "NOT_COMPLETED_REGULAR_SESSION"})
            continue
        try:
            close = Decimal(str(row["close"]))
        except InvalidOperation as exc:
            raise ValueError("YAHOO_CLOSE_INVALID") from exc
        if not close.is_finite() or close <= 0:
            raise ValueError("YAHOO_CLOSE_INVALID")
        fact = {"schema_version": "live-fact/1.0.0", "security_id": security_id,
                "semantic_field": "close_price", "value": format(close, "f"), "unit": "USD", "currency": "USD",
                "source_id": "yahoo-daily", "source_type": "yahoo",
                "source_locator": f"https://finance.yahoo.com/quote/{ticker}/history/",
                "source_version": f"yfinance/{YFINANCE_VERSION}/{MARKET_VERSION}",
                "as_of": close_at, "published_at": close_at,
                "published_at_policy": "completed_session_end/provider_eod_not_real_time",
                "retrieved_at": iso_utc(retrieved), "raw_content_hash": raw_content_hash,
                "kind": "price", "usage": "current", "parent_ids": [], "parent_hashes": [],
                "metadata": {"provider_symbol": ticker, "trading_date": day,
                             "exchange_timezone": "America/New_York", "price_basis": "provider_close",
                             "adjustment_semantics": "provider_close_not_guaranteed_historical_unadjusted",
                             "adjusted_close": row.get("adjusted_close"), "dividends": row.get("dividends"),
                             "stock_splits": row.get("stock_splits"), "historical_return_eligible": False,
                             "calendar_version": calendar.version, "calendar_hash": calendar.content_hash}}
        fact["evidence_id"] = "ev-yahoo-" + content_hash(fact)
        from product.mcp.live.contracts import validate_contract
        validate_contract("fact", fact)
        evidence.append(fact)
    return {"evidence": evidence, "gaps": gaps, "adapter_version": MARKET_VERSION}


def normalize_research_daily_rows(
    rows: list[dict], *, security_id: str, ticker: str, retrieved_at: str,
    calendar, raw_content_hash: str, currency: str,
) -> dict:
    """把同一份 Yahoo 原始日线扩展为研究序列，不改变现有估值行情输出。

    字段缺失会形成显式 gap；公司行动只在非零时生成事实。历史收益优先
    使用 adjusted close，原始 close 仅用于价格结构与当日区间。
    """

    if currency != "USD":
        raise ValueError("YAHOO_CURRENCY_UNSUPPORTED")
    retrieved = parse_timestamp(retrieved_at)
    evidence: list[dict] = []
    gaps: list[dict] = []
    seen: set[str] = set()
    price_fields = (
        ("open", "open_price", "provider_open", "USD"),
        ("high", "high_price", "provider_high", "USD"),
        ("low", "low_price", "provider_low", "USD"),
        ("close", "historical_close_price", "provider_close", "USD"),
        ("adjusted_close", "adjusted_close_price", "provider_adjusted_close", "USD"),
        ("volume", "share_volume", "provider_volume", "shares"),
    )
    for row in rows:
        day = row.get("date")
        if not isinstance(day, str) or day in seen:
            raise ValueError("YAHOO_RESEARCH_SESSION_INVALID")
        seen.add(day)
        close_at = calendar.session_close(day)
        if close_at is None or parse_timestamp(close_at) > retrieved:
            gaps.append({"date": day, "reason": "NOT_COMPLETED_REGULAR_SESSION"})
            continue
        comparable: dict[str, Decimal] = {}
        for key in ("open", "high", "low", "close"):
            if row.get(key) is not None:
                try:
                    comparable[key] = Decimal(str(row[key]))
                except (InvalidOperation, TypeError) as exc:
                    raise ValueError(f"YAHOO_RESEARCH_FIELD_INVALID:{key}") from exc
        if set(comparable) == {"open", "high", "low", "close"} and (
            comparable["high"] < max(comparable["open"], comparable["close"], comparable["low"])
            or comparable["low"] > min(comparable["open"], comparable["close"], comparable["high"])
        ):
            raise ValueError("YAHOO_RESEARCH_OHLC_INCONSISTENT")
        present = 0
        for source_key, semantic_field, price_basis, unit in price_fields:
            raw_value = row.get(source_key)
            if raw_value is None:
                gaps.append({"date": day, "reason": "YAHOO_RESEARCH_FIELD_MISSING", "field": source_key})
                continue
            try:
                number = Decimal(str(raw_value))
            except (InvalidOperation, TypeError) as exc:
                raise ValueError(f"YAHOO_RESEARCH_FIELD_INVALID:{source_key}") from exc
            if not number.is_finite() or number < 0 or (source_key != "volume" and number == 0):
                raise ValueError(f"YAHOO_RESEARCH_FIELD_INVALID:{source_key}")
            fact = {
                "schema_version": "live-fact/1.0.0",
                "security_id": security_id,
                "semantic_field": semantic_field,
                "value": format(number, "f"),
                "unit": unit,
                "currency": "USD" if unit == "USD" else None,
                "source_id": "yahoo-daily",
                "source_type": "yahoo",
                "source_locator": f"https://finance.yahoo.com/quote/{ticker}/history/",
                "source_version": f"yfinance/{YFINANCE_VERSION}/{MARKET_VERSION}/{RESEARCH_SERIES_VERSION}",
                "as_of": close_at,
                "published_at": close_at,
                "published_at_policy": "completed_session_end/provider_eod_not_real_time",
                "retrieved_at": iso_utc(retrieved),
                "raw_content_hash": raw_content_hash,
                "kind": "price",
                "usage": "comparison",
                "parent_ids": [],
                "parent_hashes": [],
                "metadata": {
                    "provider_symbol": ticker,
                    "trading_date": day,
                    "exchange_timezone": "America/New_York",
                    "price_basis": price_basis,
                    "adjustment_semantics": (
                        "provider_adjusted_close_for_historical_return"
                        if source_key == "adjusted_close"
                        else "provider_raw_daily_field"
                    ),
                    "historical_return_eligible": source_key == "adjusted_close",
                    "calendar_version": calendar.version,
                    "calendar_hash": calendar.content_hash,
                },
            }
            fact["evidence_id"] = "ev-yahoo-research-" + content_hash(fact)
            from product.mcp.live.contracts import validate_contract
            validate_contract("fact", fact)
            evidence.append(fact)
            present += 1
        for source_key, semantic_field, unit in (
            ("dividends", "cash_dividend", "USD_per_share"),
            ("stock_splits", "stock_split_ratio", "ratio"),
        ):
            raw_value = row.get(source_key)
            if raw_value in (None, 0, 0.0, "0", "0.0"):
                continue
            try:
                number = Decimal(str(raw_value))
            except (InvalidOperation, TypeError) as exc:
                raise ValueError(f"YAHOO_RESEARCH_FIELD_INVALID:{source_key}") from exc
            if not number.is_finite() or number <= 0:
                raise ValueError(f"YAHOO_RESEARCH_FIELD_INVALID:{source_key}")
            fact = {
                "schema_version": "live-fact/1.0.0",
                "security_id": security_id,
                "semantic_field": semantic_field,
                "value": format(number, "f"),
                "unit": unit,
                "currency": "USD" if source_key == "dividends" else None,
                "source_id": "yahoo-daily",
                "source_type": "yahoo",
                "source_locator": f"https://finance.yahoo.com/quote/{ticker}/history/",
                "source_version": f"yfinance/{YFINANCE_VERSION}/{MARKET_VERSION}/{RESEARCH_SERIES_VERSION}",
                "as_of": close_at,
                "published_at": close_at,
                "published_at_policy": "completed_session_end/provider_eod_not_real_time",
                "retrieved_at": iso_utc(retrieved),
                "raw_content_hash": raw_content_hash,
                "kind": "disclosure",
                "usage": "comparison",
                "parent_ids": [],
                "parent_hashes": [],
                "metadata": {
                    "provider_symbol": ticker,
                    "trading_date": day,
                    "exchange_timezone": "America/New_York",
                    "action_type": source_key,
                    "calendar_version": calendar.version,
                    "calendar_hash": calendar.content_hash,
                },
            }
            fact["evidence_id"] = "ev-yahoo-action-" + content_hash(fact)
            from product.mcp.live.contracts import validate_contract
            validate_contract("fact", fact)
            evidence.append(fact)
        if present == 0:
            gaps.append({"date": day, "reason": "YAHOO_RESEARCH_ROW_EMPTY"})
    return {
        "evidence": evidence,
        "gaps": gaps,
        "adapter_version": RESEARCH_SERIES_VERSION,
    }


def normalize_cached_research_series(
    record: dict, raw: bytes, *, security_id: str, ticker: str, currency: str, calendar,
) -> dict:
    """从已选中的 Yahoo 日线缓存生成研究序列，拒绝来源或内容漂移。"""

    if record.get("raw_content_hash") != hashlib.sha256(raw).hexdigest():
        raise ValueError("YAHOO_RESEARCH_RAW_HASH_MISMATCH")
    key = record.get("key")
    if not isinstance(key, dict) or any(
        key.get(field) != expected
        for field, expected in (
            ("provider", "yahoo"), ("ticker", ticker), ("security_id", security_id),
            ("currency", currency), ("interval", "1d"), ("adapter_version", MARKET_VERSION),
        )
    ):
        raise ValueError("YAHOO_RESEARCH_RECORD_BINDING_INVALID")
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("YAHOO_RESEARCH_RAW_INVALID") from exc
    if not isinstance(rows, list):
        raise ValueError("YAHOO_RESEARCH_RAW_INVALID")
    return normalize_research_daily_rows(
        rows,
        security_id=security_id,
        ticker=ticker,
        currency=currency,
        retrieved_at=record["retrieved_at"],
        calendar=calendar,
        raw_content_hash=record["raw_content_hash"],
    )


def download_daily(*, tickers: list[str], start: str, end: str, source_access: dict, downloader=None, session=None):
    """明确来源准入后才能调用；上游未核实与个人批准分开验证。"""
    from product.mcp.live.contracts import validate_contract
    import re

    validate_contract("source-access", source_access)
    from product.mcp.live.contracts import require_source_admission
    require_source_admission(source_access)
    if source_access["provider"] != "yahoo":
        raise ValueError("YAHOO_SOURCE_NOT_AUTHORIZED")
    if source_access["client_version"] != f"yfinance/{YFINANCE_VERSION}" or source_access["adapter_version"] != MARKET_VERSION:
        raise ValueError("YAHOO_ACCESS_VERSION_MISMATCH")
    if not 0 < (date.fromisoformat(end) - date.fromisoformat(start)).days <= 366:
        raise ValueError("YAHOO_DATE_RANGE_INVALID")
    if not tickers or any(not isinstance(t, str) or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", t) for t in tickers):
        raise ValueError("YAHOO_SYMBOL_INVALID")
    if downloader is None:
        from product.mcp.live.yahoo_transport import RequestBoundary
        if not isinstance(getattr(session, "live_boundary", None), RequestBoundary):
            raise ValueError("YAHOO_BOUNDED_SESSION_REQUIRED")
        if session.live_boundary.access_hash != content_hash(source_access) or not set(tickers) <= session.live_boundary.tickers:
            raise ValueError("YAHOO_SESSION_SCOPE_MISMATCH")
        session.live_boundary.assert_healthy()
        if version("yfinance") != YFINANCE_VERSION:
            raise ValueError("YAHOO_CLIENT_VERSION_MISMATCH")
        import yfinance as yf
        downloader = yf.download
    extra = {"session": session} if session is not None else {}
    frame = downloader(tickers=sorted(set(tickers)), start=start, end=end, interval="1d",
                       auto_adjust=False, back_adjust=False, repair=False, actions=True,
                       threads=False, progress=False, group_by="ticker", timeout=20, **extra)
    boundary = getattr(session, "live_boundary", None)
    if boundary is not None:
        boundary.assert_healthy()
    return {"data": frame, "sdk_calls": 1, "actual_http_requests": boundary.requests if boundary else None,
            "http_observation_gap": None if boundary else "SDK_INTERNAL_REQUESTS_NOT_COUNTED", "adapter_version": MARKET_VERSION}


def collect_daily(securities: list[dict], *, start: str, end: str, source_access: dict,
                  cache, calendar, retrieved_at: str, max_age_seconds: int,
                  downloader=None, refresh: bool = False, session=None) -> dict:
    """同参数去重、只刷新缺失/过期项；实际获取时间须由调用方在请求完成后提供。

    retrieved_at 可以是无参数时钟 callable；真实采集必须使用 callable，
    固定字符串只允许注入 downloader 的确定性测试。
    """
    from product.mcp.live.contracts import validate_contract
    if downloader is None and not callable(retrieved_at):
        raise ValueError("YAHOO_REAL_FETCH_REQUIRES_COMPLETION_CLOCK")
    now = lambda: iso_utc(retrieved_at() if callable(retrieved_at) else retrieved_at)
    if type(max_age_seconds) is not int or max_age_seconds < 0:
        raise ValueError("YAHOO_CACHE_AGE_INVALID")
    validate_contract("source-access", source_access)
    targets = {}
    for security in securities:
        ticker = security["ticker"]
        identity = {k: security[k] for k in ("security_id", "ticker", "currency")}
        if ticker in targets and targets[ticker] != identity:
            raise ValueError("YAHOO_SYMBOL_IDENTITY_CONFLICT")
        if identity["currency"] != "USD":
            raise ValueError("YAHOO_CURRENCY_UNSUPPORTED")
        targets[ticker] = identity
    keys, records, missing = {}, {}, []
    for ticker, identity in targets.items():
        key = dict(identity, provider="yahoo", start=start, end=end, interval="1d",
                   auto_adjust=False, back_adjust=False, repair=False, actions=True,
                   adapter_version=MARKET_VERSION, client_version=YFINANCE_VERSION)
        keys[ticker] = key
        cached = cache.lookup(key)
        age = (parse_timestamp(now()) - parse_timestamp(cached["retrieved_at"])).total_seconds() if cached else None
        if cached and not refresh and 0 <= age <= max_age_seconds:
            records[ticker] = cached
        else:
            missing.append(ticker)
    gaps, sdk_calls, actual_http_requests = [], 0, 0
    if missing:
        response = download_daily(tickers=missing, start=start, end=end, source_access=source_access, downloader=downloader, session=session)
        sdk_calls = response["sdk_calls"]
        actual_http_requests = response["actual_http_requests"]
        frame = response["data"]
        completed = now()
        for ticker in missing:
            try:
                series = frame[ticker]  # download 使用 group_by=ticker 与默认 multi_level_index=True。
            except (KeyError, TypeError):
                gaps.append({"ticker": ticker, "reason": "YAHOO_SYMBOL_RESPONSE_MISSING"})
                continue
            rows = []
            for index, row in series.iterrows():
                close = row.get("Close")
                if close is None or bool(close != close):
                    continue
                values = {}
                for name, column in (("open", "Open"), ("high", "High"), ("low", "Low"),
                                     ("close", "Close"), ("adjusted_close", "Adj Close"),
                                     ("volume", "Volume"), ("dividends", "Dividends"),
                                     ("stock_splits", "Stock Splits")):
                    number = row.get(column)
                    values[name] = None if number is None or bool(number != number) else float(number)
                rows.append(dict(date=index.date().isoformat(), **values))
            if not rows:
                gaps.append({"ticker": ticker, "reason": "YAHOO_EMPTY_SYMBOL_RESPONSE"})
                continue
            raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            records[ticker] = cache.store(keys[ticker], raw, retrieved_at=completed)
    evidence = []
    for ticker, record in records.items():
        normalized = normalize_daily_rows(json.loads(cache.read(record)), security_id=targets[ticker]["security_id"],
                      ticker=ticker, currency=targets[ticker]["currency"], retrieved_at=record["retrieved_at"],
                      calendar=calendar, raw_content_hash=record["raw_content_hash"])
        evidence.extend(normalized["evidence"])
        gaps.extend(dict(item, ticker=ticker) for item in normalized["gaps"])
    return {"evidence": evidence, "gaps": gaps, "records": records, "sdk_calls": sdk_calls,
            "cache_hits": len(targets) - len(missing), "fetched_symbols": len(records) - (len(targets) - len(missing)),
            "actual_http_requests": actual_http_requests,
            "raw_capture_policy": "canonical_sdk_rows_not_wire_http_response",
            "http_observation_gap": "SDK_INTERNAL_REQUESTS_NOT_COUNTED" if actual_http_requests is None else None}
