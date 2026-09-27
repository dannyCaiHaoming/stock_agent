"""Bounded public moomoo headline discovery; never fetches article bodies."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html import unescape
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, Request, build_opener

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.sec_client import Response, _NoRedirect
from product.mcp.live.tls import verified_https_context
from product.mcp.provenance import iso_utc, parse_timestamp


ADAPTER_VERSION = "moomoo-public-news-search/1.0.0"
POLICY_PATH = Path(__file__).with_name("research-source-policy.json")
ENDPOINT = "https://ai-news-search.moomoo.com/news_search"
MAX_BYTES = 1024 * 1024
_TAG = re.compile(r"<[^>]*>")
_TRACKING = {"futusource", "src", "utm_source", "utm_medium", "utm_campaign"}


def _http(request: Request) -> Response:
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=verified_https_context())).open(
            request, timeout=15,
        ) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("MOOMOO_PUBLIC_NEWS_RESPONSE_TOO_LARGE")
            return Response(response.status, body)
    except HTTPError as exc:
        exc.close()
        return Response(exc.code, b"")
    except (URLError, OSError, ImportError) as exc:
        raise ValueError("MOOMOO_PUBLIC_NEWS_TRANSPORT_FAILURE") from exc


def _policy(path: Path = POLICY_PATH) -> Mapping[str, Any]:
    source = json.loads(path.read_text(encoding="utf-8")).get("sources", {}).get(
        "moomoo_public_news", {},
    )
    if source != {
        "adapter_version": ADAPTER_VERSION,
        "authentication": "none",
        "domains": ["ai-news-search.moomoo.com"],
        "endpoint": ENDPOINT,
        "request_budget": {"per_security": 2, "market": 1, "results_per_query": 10},
        "limitations": source.get("limitations"),
    } or not isinstance(source.get("limitations"), list):
        raise ValueError("MOOMOO_PUBLIC_NEWS_POLICY_INVALID")
    return source


def canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("MOOMOO_PUBLIC_NEWS_URL_INVALID")
    if len(value) > 2048:
        raise ValueError("MOOMOO_PUBLIC_NEWS_URL_INVALID")
    from urllib.parse import parse_qsl
    query = urlencode([
        (key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING and not key.lower().startswith("utm_")
    ])
    return urlunsplit(("https", parsed.hostname.lower(), parsed.path.rstrip("/") or "/", query, ""))


def clean_title(value: str) -> str:
    return " ".join(unescape(_TAG.sub("", value)).split())


def fetch_news_search(
    *, keyword: str, news_type: int, cache_root: Path,
    decision_cutoff: str | None = None,
    transport: Callable[[Request], Response] = _http,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    policy_path: Path = POLICY_PATH,
) -> dict[str, Any]:
    """One bounded request; returns only verified search metadata and exclusions."""
    source = _policy(policy_path)
    if not isinstance(keyword, str) or not 1 <= len(keyword.strip()) <= 120 \
            or news_type not in {1, 2, 3}:
        raise ValueError("MOOMOO_PUBLIC_NEWS_REQUEST_INVALID")
    size = source["request_budget"]["results_per_query"]
    endpoint = source["endpoint"] + "?" + urlencode({
        "keyword": keyword.strip(), "size": size, "news_type": news_type,
        "lang": "en", "sort_type": 2,
    })
    response = transport(Request(endpoint, headers={
        "Accept": "application/json", "User-Agent": "moomoo-news-search/0.0.2 (Skill)",
    }, method="GET"))
    retrieved_at = iso_utc(now())
    if response.status != 200:
        raise ValueError(f"MOOMOO_PUBLIC_NEWS_HTTP_{response.status}")
    if len(response.body) > MAX_BYTES:
        raise ValueError("MOOMOO_PUBLIC_NEWS_RESPONSE_TOO_LARGE")
    try:
        data = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("MOOMOO_PUBLIC_NEWS_RESPONSE_INVALID") from exc
    if not isinstance(data, dict) or data.get("code") != 0 or not isinstance(data.get("data"), list):
        raise ValueError("MOOMOO_PUBLIC_NEWS_RESPONSE_INVALID")
    record = SnapshotCache(cache_root).store({
        "provider": "moomoo_public_news", "keyword": keyword.strip(),
        "news_type": news_type, "adapter_version": ADAPTER_VERSION,
    }, response.body, retrieved_at=retrieved_at)
    cutoff = parse_timestamp(decision_cutoff) if decision_cutoff else parse_timestamp(retrieved_at)
    candidates, excluded, seen = [], [], set()
    for raw in data["data"][:size]:
        if not isinstance(raw, Mapping):
            excluded.append({"reason": "ITEM_INVALID"})
            continue
        title, link = raw.get("title"), raw.get("url")
        if not isinstance(title, str) or not isinstance(link, str):
            excluded.append({"reason": "ITEM_INVALID"})
            continue
        title = clean_title(title)
        if not title:
            excluded.append({"reason": "TITLE_EMPTY"})
            continue
        try:
            canonical = canonical_url(link)
            epoch = int(raw["publish_time"])
            if epoch > 10_000_000_000:
                epoch //= 1000
            published = datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (KeyError, TypeError, ValueError, OverflowError):
            excluded.append({"reason": "TIME_OR_URL_INVALID"})
            continue
        if published > cutoff or published > parse_timestamp(retrieved_at):
            excluded.append({"reason": "FUTURE_OR_UNAVAILABLE_AT_CUTOFF"})
            continue
        if raw.get("news_type") != news_type:
            excluded.append({"reason": "NEWS_TYPE_MISMATCH"})
            continue
        key = (canonical, title.casefold())
        if key in seen:
            excluded.append({"reason": "DUPLICATE"})
            continue
        seen.add(key)
        candidates.append({
            "news_id": str(raw.get("news_id") or hashlib.sha256(canonical.encode()).hexdigest()[:16]),
            "news_type": news_type, "title": title, "original_url": link,
            "canonical_url": canonical, "published_at": iso_utc(published),
            "source_id": "moomoo-public-news:" + str(raw.get("news_id") or hashlib.sha256(canonical.encode()).hexdigest()[:16]),
        })
    return {
        "provider": "moomoo_public_news", "keyword": keyword.strip(),
        "news_type": news_type, "retrieved_at": retrieved_at,
        "decision_cutoff": iso_utc(cutoff), "raw_content_hash": record["raw_content_hash"],
        "record_hash": record["record_hash"], "candidates": candidates,
        "excluded": excluded,
    }
