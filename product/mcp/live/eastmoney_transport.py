"""东方财富日线的逐调用请求接缝；无默认网络传输或隐式 SDK 加载。

这里只接收采集层传入的 transport，不负责来源准入或证券身份映射。
完整采集入口接通前不能用于正式采集；provider_symbol 必须另经身份验证。
"""
from datetime import date, datetime, UTC
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from importlib.metadata import version
import inspect
import json
import re
import time
from types import FunctionType, SimpleNamespace

from product.mcp.provenance import iso_utc

ADAPTER_VERSION = "eastmoney-bounded-transport/1.0.0"
AKSHARE_VERSION = "1.18.94"
HTTPS_VERSION = "eastmoney-https/1.0.0"
FUNCTION_HASH = "e539a1b0b85c31fa6dd6d84ea0b19241a805abb62138e7da4844f50509f9ba46"
ENDPOINT = "https://63.push2his.eastmoney.com/api/qt/stock/kline/get"
MAX_BYTES = 2 * 1024 * 1024
FIELDS1 = "f1,f2,f3,f4,f5,f6"
FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"


def read_bounded(stream, *, deadline=None, monotonic=time.monotonic):
    """由传输层在读取时调用，不能先下载整个正文再限长。"""
    chunks, remaining = [], MAX_BYTES + 1
    while remaining:
        if deadline is not None and monotonic() >= deadline:
            raise TimeoutError("EASTMONEY_READ_TIMEOUT")
        chunk = stream.read(min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > MAX_BYTES:
        raise ValueError("EASTMONEY_RESPONSE_TOO_LARGE")
    return raw


def http_get(url, *, params, timeout):
    """独立 opener、不跟随重定向、不持久化 cookies，仅访问已锁定端点。"""
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import HTTPSHandler, Request, build_opener
    from product.mcp.live.tls import verified_https_context
    from product.mcp.live.sec_client import Response, _NoRedirect
    if url != ENDPOINT or timeout != 15:
        raise ValueError("EASTMONEY_ENDPOINT_REJECTED")
    deadline = time.monotonic() + 20
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=verified_https_context())).open(Request(url + "?" + urlencode(params),
                headers={"Accept-Encoding": "identity"}, method="GET"), timeout=timeout) as reply:
            return Response(reply.status, read_bounded(reply, deadline=deadline))
    except HTTPError as exc:
        exc.close()
        return Response(exc.code, b"")
    except (URLError, TimeoutError) as exc:
        raise TimeoutError("EASTMONEY_TRANSPORT_FAILURE") from exc


def validate_payload(raw, *, ticker, start, end, limit):
    if len(raw) > MAX_BYTES:
        raise ValueError("EASTMONEY_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(raw)
        data = payload["data"]
        if payload.get("rc") != 0 or data["code"] != ticker:
            raise ValueError("EASTMONEY_RESPONSE_IDENTITY_INVALID")
        rows = data["klines"]
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError("EASTMONEY_ROW_BUDGET_INVALID")
        seen = set()
        for row in rows:
            columns = row.split(",")
            if len(columns) != 11:
                raise ValueError("EASTMONEY_ROW_SHAPE_INVALID")
            day = date.fromisoformat(columns[0])
            if not start <= day <= end or day in seen:
                raise ValueError("EASTMONEY_RESPONSE_DATE_INVALID")
            seen.add(day)
            close = Decimal(columns[2])
            if not close.is_finite() or close <= 0:
                raise ValueError("EASTMONEY_CLOSE_INVALID")
        return payload
    except (KeyError, TypeError, AttributeError, InvalidOperation, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("EASTMONEY_PAYLOAD_INVALID") from exc


class DailyRequestBoundary:
    """每个实例只服务一个已验证的 symbol/日期范围，不接收持仓内容。

    transport(url, params=..., timeout=...) 返回 status/body 的 Response。
    transport 自身须禁止重定向并使用 read_bounded；此处额外验证已读正文。
    """
    def __init__(self, *, symbol, start, end, request_budget, transport,
                 now=lambda: datetime.now(UTC), monotonic=time.monotonic, sleep=time.sleep):
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{3}\.[A-Z][A-Z0-9.-]{0,14}", symbol):
            raise ValueError("EASTMONEY_SYMBOL_INVALID")
        self.start, self.end = date.fromisoformat(start), date.fromisoformat(end)
        if not 0 <= (self.end - self.start).days <= 365:
            raise ValueError("EASTMONEY_DATE_RANGE_INVALID")
        if type(request_budget) is not int or request_budget < 1:
            raise ValueError("EASTMONEY_BUDGET_INVALID")
        self.symbol, self.budget, self.transport = symbol, request_budget, transport
        self.now, self.monotonic, self.sleep = now, monotonic, sleep
        self.requests, self.events, self.failure_code = 0, [], None
        self._last_request, self.raw, self.retrieved_at = None, None, None

    def _fail(self, code):
        self.failure_code = code
        raise ValueError(code)

    def get(self, url, *, timeout, params):
        if self.failure_code:
            raise ValueError(self.failure_code)
        expected = {"secid": self.symbol, "fields1": FIELDS1, "fields2": FIELDS2,
                    "klt": "101", "fqt": "0", "end": "20500000", "lmt": "1000000"}
        if url != ENDPOINT or timeout != 15 or params != expected:
            self._fail("EASTMONEY_SDK_REQUEST_DRIFT")
        limit = (self.end - self.start).days + 1
        actual = dict(expected, beg=self.start.strftime("%Y%m%d"),
                      end=self.end.strftime("%Y%m%d"), lmt=str(limit))
        for attempt in range(3):
            if self.requests >= self.budget:
                self._fail("EASTMONEY_BUDGET_EXHAUSTED")
            if self._last_request is not None:
                self.sleep(max(0, 1 - (self.monotonic() - self._last_request)))
            self._last_request = self.monotonic()
            self.requests += 1
            event = {"provider": "eastmoney", "client": f"akshare/{AKSHARE_VERSION}",
                     "adapter_version": ADAPTER_VERSION, "url": url, "sdk_params": dict(params),
                     "actual_params": dict(actual), "attempt": attempt + 1,
                     "request_number": self.requests, "started_at": iso_utc(self.now())}
            self.events.append(event)
            try:
                response = self.transport(url, params=dict(actual), timeout=15)
            except TimeoutError:
                response = SimpleNamespace(status=0, body=b"")
            except Exception:
                event.update(completed_at=iso_utc(self.now()), failure_code="EASTMONEY_TRANSPORT_FAILURE")
                self._fail("EASTMONEY_TRANSPORT_FAILURE")
            event.update(completed_at=iso_utc(self.now()), http_status=response.status)
            if response.status in (401, 403, 429):
                self._fail(f"EASTMONEY_HTTP_{response.status}")
            if response.status in (0, 500, 502, 503, 504) and attempt < 2:
                continue
            if response.status != 200:
                self._fail(f"EASTMONEY_HTTP_{response.status}")
            try:
                payload = validate_payload(response.body, ticker=self.symbol.split(".", 1)[1],
                                           start=self.start, end=self.end, limit=limit)
            except ValueError as exc:
                self._fail(str(exc))
            self.raw, self.retrieved_at = response.body, event["completed_at"]
            event.update(raw_content_hash=sha256(self.raw).hexdigest(), byte_count=len(self.raw))
            return SimpleNamespace(json=lambda: payload)
        self._fail("EASTMONEY_RETRIES_EXHAUSTED")


def parse_with_locked_sdk(boundary):
    """复用已核对的真实 SDK 解析代码，用独立 globals 注入单次请求。

    不修改原函数、模块 requests 或安装文件；版本/源码漂移在请求前失败。
    """
    if version("akshare") != AKSHARE_VERSION:
        raise ValueError("EASTMONEY_CLIENT_VERSION_MISMATCH")
    from akshare.stock_feature.stock_hist_em import stock_us_hist
    if sha256(inspect.getsource(stock_us_hist).encode()).hexdigest() != FUNCTION_HASH:
        raise ValueError("EASTMONEY_SDK_SOURCE_DRIFT")
    globals_copy = dict(stock_us_hist.__globals__, requests=SimpleNamespace(get=boundary.get))
    scoped = FunctionType(stock_us_hist.__code__, globals_copy, stock_us_hist.__name__,
                          stock_us_hist.__defaults__, stock_us_hist.__closure__)
    return scoped(symbol=boundary.symbol, period="daily", adjust="",
                  start_date=boundary.start.strftime("%Y%m%d"), end_date=boundary.end.strftime("%Y%m%d"))


class EastmoneyClient:
    """复用追加式缓存；整个集合共享实际 HTTP 预算、频率与拒绝状态。"""
    def __init__(self, access, cache, *, transport=http_get, now=lambda: datetime.now(UTC),
                 monotonic=time.monotonic, sleep=time.sleep):
        from product.mcp.live.contracts import validate_contract
        validate_contract("source-access", access)
        from product.mcp.live.contracts import require_source_admission
        require_source_admission(access, at=now())
        if access["provider"] != "eastmoney":
            raise ValueError("EASTMONEY_SOURCE_NOT_AUTHORIZED")
        if (access["schema_version"] not in ("live-source-access/2.0.0", "live-source-access/3.0.0", "live-source-access/4.0.0")
                or access["client_version"] != f"akshare/{AKSHARE_VERSION}"
                or access["adapter_version"] != ADAPTER_VERSION
                or access["domains"] != ["63.push2his.eastmoney.com"]):
            raise ValueError("EASTMONEY_ACCESS_CONTRACT_MISMATCH")
        from product.mcp.provenance import parse_timestamp
        if parse_timestamp(access["checked_at"]) > now():
            raise ValueError("LIVE_ACCESS_CHECKED_IN_FUTURE")
        self.cache, self.transport, self.now = cache, transport, now
        self.monotonic, self.sleep, self.budget = monotonic, sleep, access["request_budget"]
        self.requests, self.events, self.failure_code, self._last_request = 0, [], None, None

    def fetch(self, *, symbol, start, end, max_age_seconds=86400, refresh=False):
        from product.mcp.provenance import parse_timestamp
        if type(max_age_seconds) is not int or max_age_seconds < 0:
            raise ValueError("EASTMONEY_CACHE_AGE_INVALID")
        if self.failure_code:
            raise ValueError(self.failure_code)
        boundary = DailyRequestBoundary(symbol=symbol, start=start, end=end,
            request_budget=self.budget, transport=self.transport, now=self.now,
            monotonic=self.monotonic, sleep=self.sleep)
        key = {"provider": "eastmoney", "client": "akshare", "client_version": AKSHARE_VERSION,
               "adapter_version": ADAPTER_VERSION, "provider_symbol": symbol, "start": start, "end": end,
               "interval": "daily", "adjust": "", "klt": "101", "fqt": "0", "endpoint": ENDPOINT}
        cached = self.cache.lookup(key)
        if cached and not refresh:
            age = (self.now() - parse_timestamp(cached["retrieved_at"])).total_seconds()
            if 0 <= age <= max_age_seconds:
                validate_payload(self.cache.read(cached), ticker=symbol.split(".", 1)[1],
                    start=boundary.start, end=boundary.end, limit=(boundary.end - boundary.start).days + 1)
                self.events.append({"status": "cache_hit", "record_hash": cached["record_hash"],
                                    "completed_at": iso_utc(self.now())})
                return cached
        boundary.requests, boundary._last_request = self.requests, self._last_request
        try:
            parse_with_locked_sdk(boundary)
            return self.cache.store(key, boundary.raw, retrieved_at=boundary.retrieved_at)
        finally:
            self.requests, self._last_request = boundary.requests, boundary._last_request
            self.events.extend(boundary.events)
            self.failure_code = boundary.failure_code
