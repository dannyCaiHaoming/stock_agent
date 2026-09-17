"""Yahoo SDK 的串行只读请求边界；不开放任意 URL、登录或自动同意条款。"""
from datetime import datetime, UTC
from email.utils import parsedate_to_datetime
import math
import re
import time
from urllib.parse import urlsplit, parse_qs

from product.mcp.live.contracts import validate_contract, external_path
from product.mcp.provenance import content_hash, iso_utc

TRANSPORT_VERSION = "yahoo-readonly-transport/1.2.0"
MAX_BYTES = 32 * 1024 * 1024


class YahooTransportError(ValueError):
    pass


def bounded_send(send, method, url, **kwargs):
    """curl_cffi 的读取回调在超限块到达时中止，不先下载整个正文。"""
    # curl_cffi 将普通短返回值改回块长度，必须使用其专用中止值。
    from curl_cffi.curl import CURL_WRITEFUNC_ERROR
    chunks, total, exceeded = [], 0, False
    def receive(chunk):
        nonlocal total, exceeded
        if total + len(chunk) > MAX_BYTES:
            exceeded = True
            return CURL_WRITEFUNC_ERROR
        chunks.append(chunk)
        total += len(chunk)
        return len(chunk)
    kwargs.update(content_callback=receive, stream=False)
    try:
        response = send(method, url, **kwargs)
    except Exception:
        if exceeded:
            raise YahooTransportError("YAHOO_RESPONSE_TOO_LARGE") from None
        raise
    if exceeded:
        raise YahooTransportError("YAHOO_RESPONSE_TOO_LARGE")
    response.content = b"".join(chunks)
    return response


class RequestBoundary:
    """即使 SDK 捕获错误后再试，第一次硬失败仍锁住本次采集。"""
    def __init__(self, access, *, tickers, now=lambda: datetime.now(UTC), sleep=time.sleep, cache=None):
        validate_contract("source-access", access)
        from product.mcp.live.contracts import require_source_admission
        try:
            require_source_admission(access, at=now())
        except ValueError as exc:
            raise YahooTransportError(str(exc)) from exc
        if access["provider"] != "yahoo":
            raise YahooTransportError("YAHOO_SOURCE_NOT_AUTHORIZED")
        if not tickers or any(not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", ticker) for ticker in tickers):
            raise YahooTransportError("YAHOO_SYMBOL_INVALID")
        self.access_hash = content_hash(access)
        self.domains, self.tickers = set(access["domains"]), set(tickers)
        self.budget, self.requests = access["request_budget"], 0
        self.events, self.failure_code = [], None
        self.now, self.sleep = now, sleep
        self.cache, self.chart_records, self.option_records, self.research_records = cache, [], [], []

    def fail(self, code):
        self.failure_code = self.failure_code or code
        raise YahooTransportError(self.failure_code)

    def assert_healthy(self):
        if self.failure_code:
            raise YahooTransportError(self.failure_code)

    def request(self, send, method, url, **kwargs):
        self.assert_healthy()
        parsed = urlsplit(url)
        if (method.upper() != "GET" or parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.fragment or parsed.hostname not in self.domains):
            self.fail("YAHOO_ENDPOINT_NOT_AUTHORIZED")
        host, path = parsed.hostname, parsed.path
        bootstrap = host == "fc.yahoo.com" and path in ("", "/")
        chart = re.fullmatch(r"/v8/finance/chart/([A-Z][A-Z0-9.-]{0,14})", path)
        options = re.fullmatch(r"/v7/finance/options/([A-Z][A-Z0-9.-]{0,14})", path)
        quote_summary = re.fullmatch(r"/v10/finance/quoteSummary/([A-Z][A-Z0-9.-]{0,14})", path)
        query_host = host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
        if not (
            bootstrap or query_host and (
                path == "/v1/test/getcrumb"
                or chart and chart[1] in self.tickers
                or options and options[1] in self.tickers
                or quote_summary and quote_summary[1] in self.tickers
            )
        ):
            self.fail("YAHOO_ENDPOINT_NOT_AUTHORIZED")
        params = kwargs.get("params") or {}
        allowed_keys = {"period1", "period2", "range", "interval", "includePrePost", "events", "crumb", "includeAdjustedClose", "date", "modules"}
        if not isinstance(params, dict) or (set(params) | set(parse_qs(parsed.query))) - allowed_keys:
            self.fail("YAHOO_QUERY_FIELDS_NOT_AUTHORIZED")
        query = parse_qs(parsed.query)
        if any(len(v) != 1 for v in query.values()) or set(query) & set(params):
            self.fail("YAHOO_QUERY_FIELDS_AMBIGUOUS")
        effective = {**{key: value[0] for key, value in query.items()}, **params}
        if chart:
            if set(effective) - {
                "period1", "period2", "range", "interval", "includePrePost",
                "events", "crumb", "includeAdjustedClose",
            }:
                self.fail("YAHOO_QUERY_FIELDS_NOT_AUTHORIZED")
            if (effective.get("interval", "1d") != "1d"
                    or str(effective.get("includePrePost", False)).lower() not in ("false", "0")
                    or effective.get("range", "1d") not in ("1d", "5d", "1mo", "3mo", "6mo", "1y")):
                self.fail("YAHOO_QUERY_RANGE_INVALID")
            if "period1" in effective or "period2" in effective:
                try:
                    first, last = effective["period1"], effective["period2"]
                    if any(isinstance(v, bool) or re.fullmatch(r"[0-9]+", str(v)) is None for v in (first, last)):
                        raise ValueError
                    if not 0 < int(last) - int(first) <= 366 * 86400 or "range" in effective:
                        raise ValueError
                except (KeyError, ValueError, TypeError):
                    self.fail("YAHOO_QUERY_RANGE_INVALID")
        if options and set(effective) - {"date", "crumb"}:
            self.fail("YAHOO_OPTIONS_QUERY_INVALID")
        if options and "date" in effective and (
            isinstance(effective["date"], bool)
            or re.fullmatch(r"[0-9]{9,12}", str(effective["date"])) is None
        ):
            self.fail("YAHOO_OPTIONS_QUERY_INVALID")
        if quote_summary:
            allowed_modules = {
                "assetProfile", "price", "calendarEvents", "earningsTrend",
                "recommendationTrend", "defaultKeyStatistics", "summaryDetail",
            }
            modules = str(effective.get("modules", "")).split(",")
            if (
                set(effective) - {"modules", "crumb"} or not modules
                or any(module not in allowed_modules for module in modules)
                or len(modules) != len(set(modules))
            ):
                self.fail("YAHOO_RESEARCH_MODULES_INVALID")
        if any(kwargs.get(key) is not None for key in ("data", "json", "files", "auth")):
            self.fail("YAHOO_REQUEST_BODY_FORBIDDEN")
        # SDK 要求跟随重定向时仍关闭；新的 consent 域名/POST 不会自动放行。
        kwargs.update(allow_redirects=False, timeout=20)
        for attempt in range(3):
            if self.requests >= self.budget:
                self.fail("YAHOO_REQUEST_BUDGET_EXHAUSTED")
            self.requests += 1
            started = iso_utc(self.now())
            try:
                response = send(method, url, **kwargs)
                status = response.status_code
            except YahooTransportError as exc:
                self.events.append({"transport_version": TRANSPORT_VERSION, "request_number": self.requests,
                    "endpoint": f"https://{host}{path}", "method": "GET", "attempt": attempt + 1,
                    "request_started_at": started, "completed_at": iso_utc(self.now()),
                    "http_status": None, "status": "failed", "failure_code": str(exc)})
                self.fail(str(exc))
            except Exception:
                response, status = None, 0
            event = {"transport_version": TRANSPORT_VERSION, "request_number": self.requests,
                     "endpoint": f"https://{host}{path}", "method": "GET", "attempt": attempt + 1,
                     "request_started_at": started, "completed_at": iso_utc(self.now()), "http_status": status}
            self.events.append(event)
            # Cookie bootstrap 可用 404 响应设匿名 cookie；该正文不作行情证据。
            if status == 200 or bootstrap and status == 404:
                if len(response.content) > MAX_BYTES:
                    self.fail("YAHOO_RESPONSE_TOO_LARGE")
                event["status"] = "fetched"
                if chart and self.cache is not None:
                    query = dict(parse_qs(parsed.query), **params)
                    query.pop("crumb", None)
                    record = self.cache.store({"provider": "yahoo", "endpoint": event["endpoint"],
                        "params": query, "transport_version": TRANSPORT_VERSION}, response.content,
                        retrieved_at=event["completed_at"])
                    self.chart_records.append({"ticker": chart[1], "record": record})
                    event["raw_content_hash"] = record["raw_content_hash"]
                if options and self.cache is not None:
                    query = dict(parse_qs(parsed.query), **params)
                    query.pop("crumb", None)
                    record = self.cache.store({"provider": "yahoo", "endpoint": event["endpoint"],
                        "params": query, "transport_version": TRANSPORT_VERSION, "kind": "options"},
                        response.content, retrieved_at=event["completed_at"])
                    self.option_records.append({"ticker": options[1], "record": record})
                    event["raw_content_hash"] = record["raw_content_hash"]
                if quote_summary and self.cache is not None:
                    query = dict(parse_qs(parsed.query), **params)
                    query.pop("crumb", None)
                    record = self.cache.store({"provider": "yahoo", "endpoint": event["endpoint"],
                        "params": query, "transport_version": TRANSPORT_VERSION,
                        "kind": "research-quote-summary"}, response.content,
                        retrieved_at=event["completed_at"])
                    self.research_records.append({"ticker": quote_summary[1], "record": record})
                    event["raw_content_hash"] = record["raw_content_hash"]
                return response
            event["status"] = "failed"
            code = f"YAHOO_HTTP_{status}" if status else "YAHOO_TRANSPORT_FAILURE"
            event["failure_code"] = code
            if status not in (0, 500, 502, 503, 504) or attempt == 2:
                self.fail(code)
            delay = 2 ** attempt
            retry_after = response.headers.get("Retry-After") if response is not None else None
            if retry_after is not None:
                try:
                    delay = float(retry_after)
                except (ValueError, TypeError):
                    try:
                        delay = (parsedate_to_datetime(retry_after) - self.now()).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        self.fail("YAHOO_RETRY_AFTER_INVALID")
                if not math.isfinite(delay) or not 0 <= delay <= 30:
                    self.fail("YAHOO_RETRY_AFTER_OUTSIDE_BUDGET")
            self.sleep(delay)
        raise AssertionError("unreachable")


def create_yahoo_session(access, *, tickers, state_dir, cache):
    """延迟加载可选 SDK；仅显式授权采集调用，不会在模块导入时初始化。"""
    from importlib.metadata import version
    from product.mcp.live.market import YFINANCE_VERSION, MARKET_VERSION
    boundary = RequestBoundary(access, tickers=tickers, cache=cache)
    if access["client_version"] != f"yfinance/{YFINANCE_VERSION}" or access["adapter_version"] != MARKET_VERSION:
        raise YahooTransportError("YAHOO_ACCESS_VERSION_MISMATCH")
    if version("yfinance") != YFINANCE_VERSION:
        raise YahooTransportError("YAHOO_CLIENT_VERSION_MISMATCH")
    directory = external_path(state_dir)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    from curl_cffi.requests import Session
    import yfinance as yf
    yf.set_tz_cache_location(str(directory))

    class BoundedSession(Session):
        def request(self, method, url, **kwargs):
            return boundary.request(lambda m, u, **kw: bounded_send(super(BoundedSession, self).request, m, u, **kw),
                                    method, url, **kwargs)

    # 保持所锁定 SDK 的默认匿名 HTTP backend；不配置登录、不轮换身份/代理。
    session = BoundedSession(impersonate="chrome")
    session.live_boundary = boundary
    return session


def acquire_anonymous_crumb(session) -> str:
    """建立匿名 Yahoo 会话并返回仅驻留内存的 crumb。

    crumb 不进入事件、缓存 key、文件或异常；调用方只可把它传给同一有界
    session 的已批准 GET 请求。
    """

    boundary = getattr(session, "live_boundary", None)
    if not isinstance(boundary, RequestBoundary):
        raise YahooTransportError("YAHOO_BOUNDED_SESSION_REQUIRED")
    session.get("https://fc.yahoo.com/")
    response = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb")
    try:
        crumb = response.content.decode("utf-8", "strict").strip()
    except (AttributeError, UnicodeError) as exc:
        raise YahooTransportError("YAHOO_CRUMB_INVALID") from exc
    if (
        not crumb or len(crumb) > 256 or any(ord(char) < 33 or ord(char) > 126 for char in crumb)
        or "<" in crumb or ">" in crumb
    ):
        raise YahooTransportError("YAHOO_CRUMB_INVALID")
    return crumb
