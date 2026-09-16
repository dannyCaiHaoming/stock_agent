"""受限 SEC GET 采集器；研究 Agent 不获得此客户端。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from email.utils import parsedate_to_datetime
import math
import re
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.tls import verified_https_context
from product.mcp.live.sec import (
    ADAPTER_VERSION,
    PRIMARY_DOCUMENT_PATH_PATTERN,
    normalize_cik,
    parse_submissions,
    parse_companyfacts,
    parse_submission_page,
    _decode,
)
from product.mcp.provenance import iso_utc, parse_timestamp

CLIENT_VERSION = "sec-readonly/0.3.1"
TRANSPORT_VERSION = "sec-https/1.0.0"
OWNERSHIP_DOCUMENT_RESOLUTION_VERSION = "sec-ownership-document-resolution/1.0.0"
MAX_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    retry_after: str | None = None


class FetchError(ValueError):
    pass


class SecTransportError(TimeoutError):
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
        else:
            category = "NETWORK_ERROR"
        self.details = {"category": category, "transport_version": TRANSPORT_VERSION}
        for key in ("errno", "verify_code"):
            value = getattr(cause, key, None)
            if type(value) is int:
                self.details[key] = value
        super().__init__("SEC_TRANSPORT_FAILURE")


def validate_sec_url(url: str) -> str:
    patterns = (
        r"https://data\.sec\.gov/submissions/CIK[0-9]{10}(?:-submissions-[0-9]{3})?\.json",
        r"https://data\.sec\.gov/api/xbrl/companyfacts/CIK[0-9]{10}\.json",
        r"https://www\.sec\.gov/files/company_tickers_exchange\.json",
        rf"https://www\.sec\.gov/Archives/edgar/data/[0-9]+/[0-9]{{18}}/{PRIMARY_DOCUMENT_PATH_PATTERN}",
    )
    if not isinstance(url, str) or not any(re.fullmatch(pattern, url) for pattern in patterns):
        raise FetchError("SEC_ENDPOINT_REJECTED")
    return url


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_get(url: str, user_agent: str) -> Response:
    validate_sec_url(url)
    request = Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"}, method="GET")
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=verified_https_context())).open(request, timeout=20) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise FetchError("SEC_RESPONSE_TOO_LARGE")
            return Response(response.status, raw, response.headers.get("Retry-After"))
    except HTTPError as exc:
        # 不持久化错误正文、认证头或可能包含联系身份的异常文本。
        retry_after = exc.headers.get("Retry-After")
        exc.close()
        return Response(exc.code, b"", retry_after)
    except (URLError, OSError) as exc:
        raise SecTransportError(exc) from exc


class SecClient:
    """串行单客户端最多 2 请求/秒；不宣称控制其他进程的总请求量。"""
    def __init__(self, cache: SnapshotCache, *, user_agent: str, request_budget: int = 20,
                 transport=http_get, now=lambda: datetime.now(UTC), monotonic=time.monotonic,
                 sleep=time.sleep, source_access=None):
        # 旧离线调用保持原契约；当前 collection 必须传入 v4 双状态配置。
        if source_access is not None:
            from product.mcp.live.contracts import require_source_admission
            require_source_admission(source_access, at=now())
            if source_access["provider"] != "sec" or source_access["schema_version"] != "live-source-access/4.0.0":
                raise FetchError("SEC_ACCESS_CONTRACT_MISMATCH")
            if request_budget != source_access["request_budget"]:
                raise FetchError("SEC_ACCESS_BUDGET_MISMATCH")
        self.source_access, self.failure_code = source_access, None
        if not isinstance(user_agent, str) or "@" not in user_agent or any(ord(c) < 32 for c in user_agent):
            raise FetchError("SEC_CONTACT_REQUIRED")
        if type(request_budget) is not int or request_budget < 1:
            raise FetchError("SEC_BUDGET_INVALID")
        self.cache, self._user_agent = cache, user_agent
        self.transport, self.now, self.monotonic, self.sleep = transport, now, monotonic, sleep
        self.budget, self.requests, self.events = request_budget, 0, []
        self._last_request = None

    def fetch(self, url: str, *, max_age_seconds: float, refresh: bool = False) -> dict:
        if self.failure_code:
            raise FetchError(self.failure_code)
        if self.source_access is not None:
            from product.mcp.live.contracts import require_source_admission
            require_source_admission(self.source_access, at=self.now())
        validate_sec_url(url)
        if not math.isfinite(max_age_seconds) or max_age_seconds < 0:
            raise FetchError("SEC_CACHE_AGE_INVALID")
        key = {"provider": "sec", "url": url, "adapter_version": ADAPTER_VERSION,
               "client_version": CLIENT_VERSION}
        cached = self.cache.lookup(key)
        if cached and not refresh:
            age = (self.now() - parse_timestamp(cached["retrieved_at"])).total_seconds()
            if 0 <= age <= max_age_seconds:
                self.events.append({"status": "cache_hit", "record_hash": cached["record_hash"],
                                    "cache_read_at": iso_utc(self.now())})
                return cached
        for attempt in range(3):
            if self.requests >= self.budget:
                self.events.append({"status": "failed", "failure_code": "SEC_BUDGET_EXHAUSTED"})
                raise FetchError("SEC_BUDGET_EXHAUSTED")
            if self._last_request is not None:
                self.sleep(max(0, 0.5 - (self.monotonic() - self._last_request)))
            self._last_request = self.monotonic()
            self.requests += 1
            started = iso_utc(self.now())
            transport_error = None
            try:
                response = self.transport(url, self._user_agent)
            except TimeoutError as exc:
                transport_error = (exc.details if isinstance(exc, SecTransportError)
                                   else SecTransportError(exc).details)
                response = Response(0, b"")
            event = {"url": url, "attempt": attempt + 1, "request_number": self.requests,
                     "request_started_at": started, "completed_at": iso_utc(self.now()),
                     "http_status": response.status}
            self.events.append(event)
            if transport_error is not None:
                event["transport_error"] = transport_error
                if transport_error["category"] in ("TLS_CERTIFICATE_VERIFY_FAILED", "TLS_ERROR"):
                    self.failure_code = "SEC_" + transport_error["category"]
                    event.update(status="failed", failure_code=self.failure_code)
                    raise FetchError(self.failure_code)
            if response.status == 200:
                if not isinstance(response.body, bytes) or len(response.body) > MAX_BYTES:
                    raise FetchError("SEC_RESPONSE_INVALID")
                record = self.cache.store(key, response.body, retrieved_at=event["completed_at"])
                event.update(status="fetched", record_hash=record["record_hash"])
                return record
            event.update(status="failed", failure_code=f"SEC_HTTP_{response.status}" if response.status else "SEC_TIMEOUT")
            if self.source_access is not None and response.status in (401, 403, 429):
                self.failure_code = event["failure_code"]
                raise FetchError(self.failure_code)
            if response.status not in (0, 429, 500, 502, 503, 504) or attempt == 2:
                raise FetchError(event["failure_code"])
            delay = 2 ** attempt
            if response.retry_after is not None:
                try:
                    delay = float(response.retry_after)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(response.retry_after) - self.now()).total_seconds()
                    except (ValueError, TypeError, OverflowError) as exc:
                        raise FetchError("SEC_RETRY_AFTER_INVALID") from exc
                if not math.isfinite(delay) or delay > 30 or delay < 0:
                    raise FetchError("SEC_RETRY_AFTER_OUTSIDE_BUDGET")
            self.sleep(delay)
        raise AssertionError("unreachable")

    def submissions(self, cik: str, **policy) -> dict:
        return self.fetch(f"https://data.sec.gov/submissions/CIK{normalize_cik(cik)}.json", **policy)

    def companyfacts(self, cik: str, **policy) -> dict:
        return self.fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json", **policy)

    def read_ticker_map(self, **policy) -> dict:
        from product.mcp.live.identity import parse_sec_ticker_map
        record = self.fetch("https://www.sec.gov/files/company_tickers_exchange.json", **policy)
        return {"mapping": parse_sec_ticker_map(self.cache.read(record), retrieved_at=record["retrieved_at"]),
                "record": record}

    def read_company(self, cik: str, *, security_id: str, max_history_pages: int = 0, **policy) -> dict:
        """最近 submissions 与财务事实接缝；未取得历史分页的事实明确隔离。"""
        submissions = self.submissions(cik, **policy)
        filings = parse_submissions(self.cache.read(submissions), cik=cik,
                                    retrieved_at=submissions["retrieved_at"])
        history = self.read_history(submissions, cik=cik, max_pages=max_history_pages, **policy)
        if any(row["accession"] in filings for row in history["excluded"]):
            raise FetchError("SEC_ACCESSION_CONFLICT")
        for accession, filing in history["filings"].items():
            if accession in filings:
                keys = ("cik", "form", "report_date", "published_at", "document_url")
                if any(filings[accession][key] != filing[key] for key in keys):
                    raise FetchError("SEC_ACCESSION_CONFLICT")
            else:
                filings[accession] = filing
        financials = self.companyfacts(cik, **policy)
        facts = parse_companyfacts(self.cache.read(financials), cik=cik, security_id=security_id,
                                   retrieved_at=financials["retrieved_at"], filings=filings)
        return {"filings": filings, **facts,
                "coverage": "RECENT_SUBMISSIONS_ONLY" if not max_history_pages else
                            ("PARTIAL_LISTED_HISTORY" if history["truncated"] or history["excluded"] else "ALL_LISTED_HISTORY"),
                "history": history,
                "submissions_record": submissions, "companyfacts_record": financials}

    def read_history(self, submissions: dict, *, cik: str, max_pages: int, **policy) -> dict:
        cik = normalize_cik(cik)
        if type(max_pages) is not int or max_pages < 0:
            raise FetchError("SEC_PAGE_BUDGET_INVALID")
        body = _decode(self.cache.read(submissions))
        if normalize_cik(body["cik"]) != cik:
            raise FetchError("SEC_CIK_MISMATCH")
        names = []
        for item in body["filings"].get("files", []):
            name = item["name"]
            if not isinstance(name, str) or not re.fullmatch(rf"CIK{cik}-submissions-[0-9]{{3}}\.json", name):
                raise FetchError("SEC_PAGE_NAME_INVALID")
            if name not in names:
                names.append(name)
        filings, records, excluded = {}, [], []
        isolated_accessions = set()
        for name in names[:max_pages]:
            record = self.fetch(f"https://data.sec.gov/submissions/{name}", **policy)
            page_excluded = []
            parsed = parse_submission_page(self.cache.read(record), cik=cik, name=name,
                                            retrieved_at=record["retrieved_at"], excluded=page_excluded)
            page_isolated = {row["accession"] for row in page_excluded}
            if page_isolated & (set(filings) | isolated_accessions) or set(parsed) & isolated_accessions:
                raise FetchError("SEC_ACCESSION_CONFLICT")
            isolated_accessions.update(page_isolated)
            excluded.extend(page_excluded)
            for accession, filing in parsed.items():
                if accession in filings:
                    keys = ("form", "report_date", "published_at", "document_url")
                    if any(filings[accession][key] != filing[key] for key in keys):
                        raise FetchError("SEC_ACCESSION_CONFLICT")
                else:
                    filings[accession] = filing
            records.append(record)
        return {"filings": filings, "records": records, "excluded": excluded, "omitted_pages": names[max_pages:],
                "truncated": len(names) > max_pages, "listed_pages": len(names)}

    def read_document(self, filing: dict, **policy) -> dict:
        """保存限定披露原文字节及来源，不将文本视为指令或自动启动研究。"""
        if filing["form"] not in ("10-K", "10-Q", "8-K", "10-K/A", "10-Q/A", "8-K/A"):
            raise FetchError("SEC_FORM_UNSUPPORTED")
        cik = normalize_cik(filing["cik"])
        accession = filing["accession"]
        if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            raise FetchError("SEC_ACCESSION_INVALID")
        url = validate_sec_url(filing["document_url"])
        prefix = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        if not url.startswith(prefix):
            raise FetchError("SEC_DOCUMENT_BINDING_MISMATCH")
        record = self.fetch(url, **policy)
        published = iso_utc(filing["published_at"])
        if parse_timestamp(published) > parse_timestamp(record["retrieved_at"]):
            raise FetchError("SEC_ACCEPTED_AFTER_RETRIEVAL")
        return {"source_id": f"sec-filing-{cik}-{accession}", "source_locator": url,
                "cik": cik, "accession": accession, "form": filing["form"],
                "as_of": published, "published_at": published,
                "published_at_policy": filing["published_at_policy"],
                "retrieved_at": record["retrieved_at"],
                "raw_content_hash": record["raw_content_hash"], "cache_record": record,
                "adapter_version": ADAPTER_VERSION}

    def read_ownership_document(self, filing: dict, **policy) -> dict:
        """读取 Forms 3/4/5 原始 XML；SEC xsl 路径仅是展示层。"""
        if filing["form"] not in {"3", "3/A", "4", "4/A", "5", "5/A"}:
            raise FetchError("SEC_OWNERSHIP_FORM_UNSUPPORTED")
        cik = normalize_cik(filing["cik"])
        accession = filing["accession"]
        if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            raise FetchError("SEC_ACCESSION_INVALID")
        submitted_url = validate_sec_url(filing["document_url"])
        prefix = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        if not submitted_url.startswith(prefix):
            raise FetchError("SEC_DOCUMENT_BINDING_MISMATCH")
        relative = submitted_url[len(prefix):]
        if "/" in relative:
            display_directory, filename = relative.split("/", 1)
            if not re.fullmatch(r"xsl[A-Za-z0-9_-]+", display_directory):
                raise FetchError("SEC_ENDPOINT_REJECTED")
            raw_url = validate_sec_url(prefix + filename)
        else:
            raw_url = submitted_url
        record = self.fetch(raw_url, **policy)
        published = iso_utc(filing["published_at"])
        if parse_timestamp(published) > parse_timestamp(record["retrieved_at"]):
            raise FetchError("SEC_ACCEPTED_AFTER_RETRIEVAL")
        resolved_filing = dict(filing, document_url=raw_url)
        resolved_filing["submission_document_url"] = submitted_url
        resolved_filing["document_resolution_version"] = OWNERSHIP_DOCUMENT_RESOLUTION_VERSION
        return {
            "record": record,
            "filing": resolved_filing,
            "submission_document_url": submitted_url,
            "raw_document_url": raw_url,
            "resolution_version": OWNERSHIP_DOCUMENT_RESOLUTION_VERSION,
        }

    def fetch_many(self, urls: list[str], **policy) -> dict:
        # 先验证整个集合，防止传入无关持仓信息；同一集合内刷新也去重。
        unique = dict.fromkeys(validate_sec_url(url) for url in urls)
        results, failures = {}, {}
        for url in unique:
            try:
                results[url] = self.fetch(url, **policy)
            except FetchError as exc:
                failures[url] = str(exc)
        return {"results": results, "failures": failures, "actual_requests": self.requests}

    def read_earnings_attachments(
        self, filing: dict, *, attachment_limit: int = 3, **policy,
    ) -> dict:
        # 局部导入避免模块导入时初始化采集或循环依赖。
        from product.mcp.live.attachments import earnings_attachments

        if filing["form"] not in ("8-K", "8-K/A"):
            raise FetchError("SEC_ATTACHMENT_FORM_UNSUPPORTED")
        prefix = filing["document_url"].rsplit("/", 1)[0]
        index = self.read_document(dict(filing, document_url=f"{prefix}/{filing['accession']}-index.html"), **policy)
        selection = earnings_attachments(
            self.cache.read(index["cache_record"]), index, limit=attachment_limit,
        )
        documents = []
        for item in selection["selected"]:
            document = self.read_document(dict(filing, document_url=item["document_url"]), **policy)
            document["attachment_selection"] = item
            documents.append(document)
        return {"index": index, "selection": selection, "documents": documents}

    def read_selected_disclosures(
        self, filings: dict, *, selection_as_of: str, event_limit: int = 3,
        attachment_limit: int = 3, **policy,
    ) -> dict:
        from product.mcp.live.filing_selection import select_filings
        from product.mcp.live.disclosure import extract_sections

        selection = select_filings(
            filings, selection_as_of=selection_as_of, event_limit=event_limit,
        )
        documents = []
        for filing in selection["selected"]:
            document = self.read_document(filing, **policy)
            entry = {"document": document}
            if filing["form"].startswith(("10-K", "10-Q")):
                entry["sections"] = extract_sections(self.cache.read(document["cache_record"]), document)
            elif filing["form"] == "8-K":
                entry["attachments"] = self.read_earnings_attachments(
                    filing, attachment_limit=attachment_limit, **policy,
                )
            documents.append(entry)
        return {"selection": selection, "documents": documents}
