"""OpenAlex 公开研究检索与正文获取；候选线索和已核实正文严格分离。"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPSHandler, Request, build_opener
from xml.etree import ElementTree

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.sec_client import Response, _NoRedirect
from product.mcp.live.tls import verified_https_context
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


ADAPTER_VERSION = "openalex-public-research/1.0.0"
SEARCH_ENDPOINT = "https://api.openalex.org/works"
CONTENT_HOST = "content.openalex.org"
MAX_SEARCH_BYTES = 2 * 1024 * 1024
MAX_CONTENT_BYTES = 12 * 1024 * 1024


def _http(request: Request, *, max_bytes: int) -> Response:
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=verified_https_context())).open(
            request, timeout=25
        ) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("PUBLIC_RESEARCH_RESPONSE_TOO_LARGE")
            return Response(response.status, body)
    except HTTPError as exc:
        exc.close()
        return Response(exc.code, b"")
    except (URLError, OSError) as exc:
        raise ValueError("PUBLIC_RESEARCH_TRANSPORT_FAILURE") from exc


def _work_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("PUBLIC_RESEARCH_WORK_ID_INVALID")
    identifier = value.rsplit("/", 1)[-1]
    if re.fullmatch(r"W[0-9]+", identifier) is None:
        raise ValueError("PUBLIC_RESEARCH_WORK_ID_INVALID")
    return identifier


def normalize_search_results(
    raw: bytes, *, query: str, security_id: str, retrieved_at: str,
    decision_cutoff: str, max_candidates: int,
) -> dict[str, Any]:
    """搜索结果只生成 LEAD_ONLY 候选，不升级为研究事实。"""

    try:
        payload = json.loads(raw)
        results = payload["results"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("PUBLIC_RESEARCH_SEARCH_RESPONSE_INVALID") from exc
    if not isinstance(results, list) or len(results) > max_candidates:
        raise ValueError("PUBLIC_RESEARCH_SEARCH_RESPONSE_INVALID")
    cutoff = parse_timestamp(decision_cutoff)
    raw_hash = hashlib.sha256(raw).hexdigest()
    candidates, excluded = [], []
    for work in results:
        identifier = _work_id(work.get("id"))
        title = work.get("title")
        publication_date = work.get("publication_date")
        if not isinstance(title, str) or not title.strip() or not isinstance(publication_date, str):
            continue
        try:
            published_text = f"{publication_date}T00:00:00Z"
            published_at = parse_timestamp(published_text)
        except ValueError:
            continue
        authors = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author") if isinstance(authorship, Mapping) else None
            name = author.get("display_name") if isinstance(author, Mapping) else None
            if isinstance(name, str) and name.strip():
                authors.append(name.strip())
        location = work.get("primary_location") if isinstance(work.get("primary_location"), Mapping) else {}
        source = location.get("source") if isinstance(location.get("source"), Mapping) else {}
        content_urls = work.get("content_urls") if isinstance(work.get("content_urls"), Mapping) else {}
        candidate = {
            "candidate_id": "research-lead-" + content_hash({
                "security_id": security_id, "work_id": identifier, "query": query,
            })[:24],
            "security_id": security_id,
            "query": query,
            "work_id": identifier,
            "title": title.strip(),
            "authors": authors,
            "institution": source.get("display_name") if isinstance(source.get("display_name"), str) else None,
            "material_type": "SEARCH_LEAD",
            "publication_date": publication_date,
            "published_at": iso_utc(published_text),
            "retrieved_at": iso_utc(retrieved_at),
            "source_id": f"openalex-work-{identifier}",
            "source_url": f"https://openalex.org/{identifier}",
            "doi": work.get("doi") if isinstance(work.get("doi"), str) else None,
            "content_url": content_urls.get("grobid_xml") if isinstance(content_urls.get("grobid_xml"), str) else None,
            "verification_status": "LEAD_ONLY",
            "raw_content_hash": raw_hash,
        }
        if published_at > cutoff:
            excluded.append(dict(candidate, exclusion_reason="FUTURE_PUBLICATION"))
        else:
            candidates.append(candidate)
    return {"candidates": candidates, "excluded": excluded, "raw_content_hash": raw_hash}


def normalize_grobid_xml(
    raw: bytes, *, candidate: Mapping[str, Any], retrieved_at: str,
) -> dict[str, Any]:
    """解析可定位章节文本；不对正文中的指令或观点作事实升级。"""

    if raw.startswith(b"\x1f\x8b"):
        try:
            raw = gzip.decompress(raw)
        except OSError as exc:
            raise ValueError("PUBLIC_RESEARCH_CONTENT_GZIP_INVALID") from exc
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise ValueError("PUBLIC_RESEARCH_CONTENT_XML_INVALID") from exc
    sections = []
    for division in root.findall(".//{*}div"):
        heading = " ".join("".join(division.find("{*}head").itertext()).split()) if division.find("{*}head") is not None else None
        paragraphs = [" ".join("".join(item.itertext()).split()) for item in division.findall(".//{*}p")]
        text = "\n".join(item for item in paragraphs if item)
        if text:
            sections.append({"section": heading or f"section-{len(sections) + 1}", "text": text})
    if not sections:
        raise ValueError("PUBLIC_RESEARCH_CONTENT_EMPTY")
    body_hash = hashlib.sha256(raw).hexdigest()
    return {
        "schema_version": "verified-research-document/1.0.0",
        "document_id": "research-document-" + content_hash({
            "candidate_id": candidate["candidate_id"], "body_hash": body_hash,
        })[:24],
        "candidate_id": candidate["candidate_id"],
        "security_id": candidate["security_id"],
        "source_id": candidate["source_id"],
        "title": candidate["title"], "authors": list(candidate.get("authors", [])),
        "institution": candidate.get("institution"), "material_type": "INDEPENDENT_RESEARCH",
        "source_url": candidate["source_url"], "original_source_url": candidate.get("doi"),
        "published_at": candidate["published_at"], "as_of": candidate["published_at"],
        "retrieved_at": iso_utc(retrieved_at), "body_hash": body_hash,
        "locations": [item["section"] for item in sections],
        "parse_scope": "GROBID_XML_SECTIONS",
        "duplicate_of": None, "revision_of": None,
        "interest_disclosure": "UNKNOWN", "verification_status": "BODY_VERIFIED",
        "sections": sections,
        "untrusted_content": True,
    }


class OpenAlexResearchClient:
    """有界客户端；API key 只从调用方传入内存，不进入策略或运行仓库。"""

    def __init__(
        self, policy: Mapping[str, Any], cache: SnapshotCache, *, api_key: str | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        transport: Callable[..., Response] = _http,
    ):
        if (
            policy.get("adapter_version") != ADAPTER_VERSION
            or policy.get("domains") != ["api.openalex.org", "content.openalex.org"]
            or policy.get("search_endpoint") != SEARCH_ENDPOINT
        ):
            raise ValueError("PUBLIC_RESEARCH_POLICY_INVALID")
        self.policy, self.cache, self.api_key = dict(policy), cache, api_key
        self.now, self.transport = now, transport
        self.search_count = 0
        self.content_count = 0
        self.events: list[dict[str, Any]] = []

    def search(self, *, query: str, security_id: str, decision_cutoff: str) -> dict[str, Any]:
        budget = self.policy["request_budget"]
        if self.search_count >= budget["searches_per_security"]:
            raise ValueError("PUBLIC_RESEARCH_SEARCH_BUDGET_EXHAUSTED")
        if not isinstance(query, str) or not query.strip() or len(query) > 240:
            raise ValueError("PUBLIC_RESEARCH_QUERY_INVALID")
        self.search_count += 1
        params = {
            "search": query.strip(),
            "filter": f"from_publication_date:2020-01-01,to_publication_date:{parse_timestamp(decision_cutoff).date().isoformat()}",
            "sort": "relevance_score:desc",
            "per_page": budget["candidates_per_security"],
            "select": "id,title,publication_date,authorships,primary_location,doi,content_urls",
        }
        if self.api_key:
            params["api_key"] = self.api_key
        request = Request(SEARCH_ENDPOINT + "?" + urlencode(params), headers={"Accept": "application/json", "User-Agent": "stock-agent-readonly/1.0"}, method="GET")
        response = self.transport(request, max_bytes=MAX_SEARCH_BYTES)
        event = {"producer": ADAPTER_VERSION, "operation": "search", "request_number": self.search_count,
                 "query_hash": content_hash({"query": query.strip()}), "http_status": response.status,
                 "completed_at": iso_utc(self.now())}
        self.events.append(event)
        if response.status != 200:
            raise ValueError(f"PUBLIC_RESEARCH_SEARCH_HTTP_{response.status}")
        return normalize_search_results(
            response.body, query=query.strip(), security_id=security_id,
            retrieved_at=event["completed_at"], decision_cutoff=decision_cutoff,
            max_candidates=budget["candidates_per_security"],
        )

    def fetch(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        budget = self.policy["request_budget"]
        if not self.api_key:
            raise ValueError("PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED")
        if self.content_count >= budget["content_attempts_per_security"]:
            raise ValueError("PUBLIC_RESEARCH_CONTENT_BUDGET_EXHAUSTED")
        work_id = _work_id(candidate.get("work_id"))
        content_url = candidate.get("content_url")
        if not isinstance(content_url, str):
            raise ValueError("PUBLIC_RESEARCH_CONTENT_NOT_AVAILABLE")
        parsed = urlparse(content_url)
        if parsed.scheme != "https" or parsed.hostname != CONTENT_HOST or parsed.path != f"/works/{work_id}.grobid-xml":
            raise ValueError("PUBLIC_RESEARCH_CONTENT_SCOPE_INVALID")
        self.content_count += 1
        request = Request(
            content_url + "?" + urlencode({"api_key": self.api_key}),
            headers={"Accept": "application/xml", "User-Agent": "stock-agent-readonly/1.0"},
            method="GET",
        )
        response = self.transport(request, max_bytes=MAX_CONTENT_BYTES)
        completed = iso_utc(self.now())
        self.events.append({"producer": ADAPTER_VERSION, "operation": "fetch_content",
                            "request_number": self.content_count, "work_id": work_id,
                            "http_status": response.status, "completed_at": completed})
        if response.status != 200:
            raise ValueError(f"PUBLIC_RESEARCH_CONTENT_HTTP_{response.status}")
        document = normalize_grobid_xml(response.body, candidate=candidate, retrieved_at=completed)
        # 缓存键不含 key；凭证不写入缓存记录或事件。
        record = self.cache.store(
            {"provider": "openalex", "operation": "content", "work_id": work_id,
             "adapter_version": ADAPTER_VERSION},
            response.body, retrieved_at=completed,
        )
        document["record_hash"] = record["record_hash"]
        return document
