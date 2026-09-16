"""NASDAQ 目录：有界只读页面、追加缓存和诚实的覆盖状态；不筛选投资机会。"""
from datetime import datetime, UTC
import json
import re
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, Request, build_opener

from product.mcp.live.contracts import validate_contract
from product.mcp.live.tls import CERTIFI_VERSION, verified_https_context
from product.mcp.live.sec_client import Response, _NoRedirect
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp

ENDPOINT = "https://api.nasdaq.com/api/screener/stocks"
ADAPTER_VERSION = "nasdaq-universe/1.0.0"
CLIENT_VERSION = "nasdaq-readonly/1.0.0"
TRANSPORT_VERSION = "nasdaq-https/1.0.0"
MAX_BYTES = 4 * 1024 * 1024


class NasdaqTransportError(TimeoutError):
    """只保留白名单错误分类；不暴露 URL、代理、请求头或异常正文。"""
    def __init__(self, error):
        cause = error.reason if isinstance(error, URLError) else error
        if isinstance(cause, ssl.SSLCertVerificationError):
            category = "TLS_CERTIFICATE_VERIFY_FAILED"
        elif isinstance(cause, ssl.SSLError):
            category = "TLS_ERROR"
        elif isinstance(cause, socket.gaierror):
            category = "DNS_ERROR"
        elif isinstance(cause, ConnectionRefusedError):
            category = "CONNECTION_REFUSED"
        elif isinstance(cause, TimeoutError):
            category = "TIMEOUT"
        elif isinstance(cause, ConnectionError):
            category = "CONNECTION_ERROR"
        else:
            category = "NETWORK_ERROR"
        self.details = {"category": category, "transport_version": TRANSPORT_VERSION}
        for key in ("errno", "verify_code"):
            value = getattr(cause, key, None)
            if type(value) is int:
                self.details[key] = value
        super().__init__("NASDAQ_TRANSPORT_FAILURE")


def read_bounded(stream, *, deadline, monotonic=time.monotonic):
    chunks, remaining = [], MAX_BYTES + 1
    while remaining:
        if monotonic() >= deadline:
            raise TimeoutError("NASDAQ_READ_TIMEOUT")
        chunk = stream.read(min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > MAX_BYTES:
        raise ValueError("NASDAQ_RESPONSE_TOO_LARGE")
    return raw


def http_get(url, *, params):
    if (
        url != ENDPOINT
        or set(params) not in ({"limit", "offset"}, {"limit", "offset", "download"})
        or type(params.get("limit")) is not int or type(params.get("offset")) is not int
        or not 1 <= params["limit"] <= (8000 if params.get("download") is True else 200)
        or params["offset"] < 0
        or ("download" in params and params["download"] is not True)
    ):
        raise ValueError("NASDAQ_REQUEST_SCOPE_INVALID")
    deadline = time.monotonic() + 20
    request = Request(url + "?" + urlencode(params), headers={
        "Accept": "application/json", "Accept-Encoding": "identity",
        "User-Agent": "stock-agent-readonly/1.0"}, method="GET")
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=verified_https_context())).open(request, timeout=20) as response:
            return Response(response.status, read_bounded(response, deadline=deadline))
    except HTTPError as exc:
        exc.close()
        return Response(exc.code, b"")
    except (URLError, OSError) as exc:
        raise NasdaqTransportError(exc) from exc


def parse_page(raw, *, limit, download=False):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("NASDAQ_RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(raw)
        data = payload["data"]
        if payload["status"]["rCode"] != 200:
            raise ValueError("NASDAQ_API_REJECTED")
        # NASDAQ 的普通分页响应把 rows 放在 data.table 下；download 响应
        # 则把 rows/headers 直接放在 data 下，并省略 totalrecords。两种都
        # 是该只读端点的实际公开形状，但不能在普通分页路径相互替代。
        if download and isinstance(data.get("rows"), list):
            rows = data["rows"]
            total = data.get("totalrecords", len(rows))
            source_asof = data.get("asOf", data.get("asof"))
        else:
            total, rows = data["totalrecords"], data["table"]["rows"]
            source_asof = data.get("asof", data.get("asOf"))
        if isinstance(total, str) and total.isdecimal():
            total = int(total)
        if type(total) is not int or total < 0 or not isinstance(rows, list) or len(rows) > limit:
            raise ValueError("NASDAQ_PAGE_SHAPE_INVALID")
        normalized = []
        for row in rows:
            raw_symbol, name = row["symbol"], row["name"]
            # download 当前会对少量短代码右侧补 ASCII 空格。只移除这种
            # 展示填充；制表符、换行等控制字符仍拒绝，归一后重复仍由
            # universe 完整性校验 fail-closed。
            symbol = raw_symbol.strip(" ") if isinstance(raw_symbol, str) else raw_symbol
            if (not isinstance(symbol, str) or not symbol
                    or len(symbol) > 32 or any(ord(c) < 32 for c in symbol)
                    or not isinstance(name, str) or not name.strip()):
                raise ValueError("NASDAQ_ROW_INVALID")
            # 不把名称、域名或符号标点解释成证券类型/交易所证明。
            normalized_row = {"symbol": symbol, "name": name, "identity_status": "UNVERIFIED"}
            if download:
                market_cap = row.get("marketCap")
                if isinstance(market_cap, str):
                    market_cap = market_cap.replace(",", "").strip() or None
                if market_cap is not None and (
                    not isinstance(market_cap, str)
                    or not market_cap.replace(".", "", 1).isdigit()
                ):
                    raise ValueError("NASDAQ_MARKET_CAP_INVALID")
                ipo_year = row.get("ipoyear")
                ipo_year = int(ipo_year) if isinstance(ipo_year, str) and ipo_year.isdecimal() else None
                normalized_row.update(
                    market_cap=market_cap,
                    country=row.get("country") or None,
                    ipo_year=ipo_year,
                    sector=row.get("sector") or None,
                    industry=row.get("industry") or None,
                )
            normalized.append(normalized_row)
        if source_asof is not None and not isinstance(source_asof, str):
            raise ValueError("NASDAQ_SOURCE_TIME_INVALID")
        return {"totalrecords": total, "rows": normalized, "source_asof": source_asof}
    except (KeyError, TypeError, AttributeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("NASDAQ_PAYLOAD_INVALID") from exc


def validate_universe(snapshot, cache=None):
    """重验完整度及原始页绑定；传入缓存时同时重新解析底层字节。"""
    if snapshot["snapshot_hash"] != content_hash({k: v for k, v in snapshot.items() if k != "snapshot_hash"}):
        raise ValueError("NASDAQ_SNAPSHOT_HASH_MISMATCH")
    rows, pages = snapshot["rows"], snapshot["pages"]
    if snapshot["row_count"] != len(rows) or len({r["symbol"] for r in rows}) != len(rows):
        raise ValueError("NASDAQ_ROW_COUNT_INVALID")
    if not parse_timestamp(snapshot["request_started_at"]) <= parse_timestamp(snapshot["as_of"]) <= parse_timestamp(snapshot["retrieved_at"]):
        raise ValueError("NASDAQ_SNAPSHOT_TIME_INVALID")
    expected_offset, known = 0, {}
    for page in pages:
        record = page["record"]
        if (record.get("record_hash") != content_hash({k: v for k, v in record.items() if k != "record_hash"})
                or record.get("key_hash") != content_hash(record.get("key"))):
            raise ValueError("NASDAQ_PAGE_RECORD_HASH_INVALID")
        key = {"provider": "nasdaq", "data_role": "universe", "client_version": CLIENT_VERSION,
               "adapter_version": ADAPTER_VERSION, "endpoint": ENDPOINT,
               "query": {"limit": page["limit"], "offset": page["offset"], **({"download": True} if page.get("download") else {})}}
        if (record["key"] != key or page["offset"] != expected_offset
                or page["row_count"] > page["limit"]
                or parse_timestamp(record["retrieved_at"]) > parse_timestamp(snapshot["retrieved_at"])):
            raise ValueError("NASDAQ_PAGE_LINEAGE_INVALID")
        expected_offset += page["row_count"]
        known[record["raw_content_hash"]] = record["retrieved_at"]
        if cache is not None:
            parsed = parse_page(cache.read(record), limit=page["limit"], download=page.get("download", False))
            if (parsed["totalrecords"] != page["totalrecords"] or parsed["source_asof"] != page["source_asof"]
                    or len(parsed["rows"]) != page["row_count"]):
                raise ValueError("NASDAQ_PAGE_CONTENT_MISMATCH")
            originals = {r["symbol"]: r for r in parsed["rows"]}
            for row in (r for r in rows if r["raw_content_hash"] == record["raw_content_hash"]):
                if row["symbol"] not in originals or any(
                    row[k] != originals[row["symbol"]][k]
                    for k in originals[row["symbol"]]
                    if k not in {"symbol"}
                ):
                    raise ValueError("NASDAQ_ROW_CONTENT_MISMATCH")
    for row in rows:
        if row["as_of"] != row["retrieved_at"] or known.get(row["raw_content_hash"]) != row["retrieved_at"]:
            raise ValueError("NASDAQ_ROW_LINEAGE_INVALID")
    if snapshot["completeness"] == "COMPLETE":
        if (snapshot["gaps"] or not pages or expected_offset != len(rows)
                or snapshot["totalrecords"] != len(rows)
                or any(p["totalrecords"] != snapshot["totalrecords"] for p in pages)):
            raise ValueError("NASDAQ_COMPLETENESS_INVALID")


class NasdaqClient:
    """只由采集层显式创建；不导入行情 SDK，不发起隐式请求。"""
    def __init__(self, access, cache, *, transport=http_get, now=lambda: datetime.now(UTC),
                 monotonic=time.monotonic, sleep=time.sleep):
        validate_contract("source-access", access)
        if (access["schema_version"] not in ("live-source-access/3.0.0", "live-source-access/4.0.0")
                or access["provider"] != "nasdaq" or access["data_role"] != "universe"
                or access["client_version"] != CLIENT_VERSION or access["adapter_version"] != ADAPTER_VERSION
                or access["domains"] != ["api.nasdaq.com"]):
            raise ValueError("NASDAQ_ACCESS_CONTRACT_MISMATCH")
        from product.mcp.live.contracts import require_source_admission
        require_source_admission(access, at=now())
        if parse_timestamp(access["checked_at"]) > now():
            raise ValueError("LIVE_ACCESS_CHECKED_IN_FUTURE")
        self.cache, self.transport, self.now = cache, transport, now
        self.monotonic, self.sleep = monotonic, sleep
        self.budget, self.requests, self.events = access["request_budget"], 0, []
        self.failure_code, self.last_request = None, None

    def _page(self, params, *, max_age_seconds):
        key = {"provider": "nasdaq", "data_role": "universe", "client_version": CLIENT_VERSION,
               "adapter_version": ADAPTER_VERSION, "endpoint": ENDPOINT, "query": params}
        cached = self.cache.lookup(key)
        if cached:
            age = (self.now() - parse_timestamp(cached["retrieved_at"])).total_seconds()
            if age < 0:
                raise ValueError("NASDAQ_CACHE_FROM_FUTURE")
            if age <= max_age_seconds:
                parsed = parse_page(
                    self.cache.read(cached),
                    limit=params["limit"],
                    download=params.get("download", False),
                )
                self.events.append({"status": "cache_hit", "record_hash": cached["record_hash"],
                                    "completed_at": iso_utc(self.now())})
                return cached, parsed
        if self.requests >= self.budget:
            raise ValueError("NASDAQ_REQUEST_BUDGET_EXHAUSTED")
        if self.last_request is not None:
            self.sleep(max(0, 1 - (self.monotonic() - self.last_request)))
        self.last_request = self.monotonic()
        self.requests += 1
        event = {"provider": "nasdaq", "query": dict(params), "request_number": self.requests,
                 "started_at": iso_utc(self.now())}
        self.events.append(event)
        try:
            response = self.transport(ENDPOINT, params=dict(params))
        except TimeoutError as exc:
            event.update(completed_at=iso_utc(self.now()), failure_code="NASDAQ_TRANSPORT_FAILURE")
            event["transport_error"] = (exc.details if isinstance(exc, NasdaqTransportError)
                                        else NasdaqTransportError(exc).details)
            raise ValueError("NASDAQ_TRANSPORT_FAILURE") from None
        event.update(completed_at=iso_utc(self.now()), http_status=response.status)
        if response.status != 200:
            event["failure_code"] = f"NASDAQ_HTTP_{response.status}"
            raise ValueError(event["failure_code"])
        # 原文留存用于错误诊断；非法页面不会成为合格目录。
        if not isinstance(response.body, bytes) or len(response.body) > MAX_BYTES:
            raise ValueError("NASDAQ_RESPONSE_TOO_LARGE")
        record = self.cache.store(key, response.body, retrieved_at=event["completed_at"])
        event.update(record_hash=record["record_hash"], raw_content_hash=record["raw_content_hash"],
                     byte_count=len(response.body))
        return record, parse_page(
            response.body,
            limit=params["limit"],
            download=params.get("download", False),
        )

    def collect(self, *, page_size=200, max_pages=1, max_rows=200, max_age_seconds=86400):
        limits = ((page_size, 1, 200), (max_pages, 1, 100), (max_rows, 1, 20000),
                  (max_age_seconds, 0, 86400))
        if any(type(v) is not int or not lo <= v <= hi for v, lo, hi in limits):
            raise ValueError("NASDAQ_SCOPE_INVALID")
        if self.failure_code:
            raise ValueError(self.failure_code)
        started = iso_utc(self.now())
        pages, rows, gaps, seen, total, offset = [], [], [], set(), None, 0
        try:
            for _ in range(max_pages):
                limit = min(page_size, max_rows - offset)
                if limit <= 0:
                    gaps.append("ROW_BUDGET_EXHAUSTED")
                    break
                record, page = self._page({"limit": limit, "offset": offset}, max_age_seconds=max_age_seconds)
                pages.append({"record": record, "offset": offset, "limit": limit,
                              "row_count": len(page["rows"]), "totalrecords": page["totalrecords"],
                              "source_asof": page["source_asof"]})
                if total is None:
                    total = page["totalrecords"]
                elif total != page["totalrecords"]:
                    gaps.append("TOTAL_CHANGED")
                    break
                for row in page["rows"]:
                    if row["symbol"] in seen:
                        gaps.append("DUPLICATE_SYMBOL")
                        continue
                    seen.add(row["symbol"])
                    rows.append(dict(row, source_id="nasdaq-screener", as_of=record["retrieved_at"],
                                     retrieved_at=record["retrieved_at"], raw_content_hash=record["raw_content_hash"]))
                offset += len(page["rows"])
                if gaps or offset >= total:
                    if offset > total:
                        gaps.append("COUNT_EXCEEDS_TOTAL")
                    break
                if len(page["rows"]) < limit:
                    gaps.append("SHORT_OR_EMPTY_PAGE")
                    break
            else:
                if total is None or offset < total:
                    gaps.append("PAGE_BUDGET_EXHAUSTED")
        except ValueError as exc:
            code = str(exc)
            self.failure_code = code if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", code) else "NASDAQ_COLLECTION_INVALID"
            gaps.append(self.failure_code)
        complete = total is not None and len(rows) == total and not gaps
        snapshot = {"schema_version": "live-universe/1.0.0", "provider": "nasdaq",
                    "source_id": "nasdaq-screener", "source_locator": ENDPOINT,
                    "adapter_version": ADAPTER_VERSION, "client_version": CLIENT_VERSION,
                    "request_started_at": started, "as_of": iso_utc(self.now()),
                    "retrieved_at": iso_utc(self.now()), "as_of_policy": "observed_membership_only",
                    "membership_effective_at": None, "pages": pages, "rows": rows,
                    "row_count": len(rows), "totalrecords": total,
                    "completeness": "COMPLETE" if complete else "PARTIAL",
                    "gaps": sorted(set(gaps)), "events": list(self.events)}
        snapshot["snapshot_hash"] = content_hash(snapshot)
        validate_contract("universe", snapshot)
        validate_universe(snapshot, self.cache)
        # 同时持久化完整/不完整目录；不得由调用者把 PARTIAL 偷换成 COMPLETE。
        self.cache.store({"provider": "nasdaq", "kind": "universe-snapshot",
                          "snapshot_hash": snapshot["snapshot_hash"]},
                         json.dumps(snapshot, sort_keys=True, allow_nan=False).encode(),
                         retrieved_at=snapshot["retrieved_at"])
        return snapshot

    def collect_download(self, *, max_rows=8000, max_age_seconds=86400):
        """使用 NASDAQ 官方 download 形状一次取得研究候选目录。"""
        if type(max_rows) is not int or not 1 <= max_rows <= 8000:
            raise ValueError("NASDAQ_SCOPE_INVALID")
        started = iso_utc(self.now())
        gaps = []
        try:
            record, page = self._page(
                {"limit": max_rows, "offset": 0, "download": True},
                max_age_seconds=max_age_seconds,
            )
            rows = [dict(
                row, source_id="nasdaq-screener", as_of=record["retrieved_at"],
                retrieved_at=record["retrieved_at"], raw_content_hash=record["raw_content_hash"],
            ) for row in page["rows"]]
            if len(rows) != page["totalrecords"]:
                gaps.append("DOWNLOAD_COUNT_MISMATCH")
            pages = [{
                "record": record, "offset": 0, "limit": max_rows,
                "row_count": len(rows), "totalrecords": page["totalrecords"],
                "source_asof": page["source_asof"], "download": True,
            }]
            total = page["totalrecords"]
        except ValueError as exc:
            code = str(exc)
            self.failure_code = code if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", code) else "NASDAQ_COLLECTION_INVALID"
            gaps.append(self.failure_code)
            record, rows, pages, total = None, [], [], None
        snapshot = {
            "schema_version": "live-universe/1.0.0", "provider": "nasdaq",
            "source_id": "nasdaq-screener", "source_locator": ENDPOINT,
            "adapter_version": ADAPTER_VERSION, "client_version": CLIENT_VERSION,
            "request_started_at": started, "as_of": iso_utc(self.now()),
            "retrieved_at": iso_utc(self.now()), "as_of_policy": "observed_membership_only",
            "membership_effective_at": None, "pages": pages, "rows": rows,
            "row_count": len(rows), "totalrecords": total,
            "completeness": "COMPLETE" if total is not None and len(rows) == total and not gaps else "PARTIAL",
            "gaps": sorted(set(gaps)), "events": list(self.events),
        }
        snapshot["snapshot_hash"] = content_hash(snapshot)
        validate_contract("universe", snapshot)
        validate_universe(snapshot, self.cache)
        return snapshot
