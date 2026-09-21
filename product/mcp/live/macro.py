"""官方宏观资料的有界只读采集与保守时间标准化。"""

from __future__ import annotations

import csv
from email.utils import parsedate_to_datetime
import hashlib
import html
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import validate_contract
from product.mcp.live.sec_client import Response, _NoRedirect
from product.mcp.live.tls import verified_https_context
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


POLICY_VERSION = "research-source-policy/1.1.0"
BLS_VERSION = "bls-public-v1/1.0.0"
TREASURY_VERSION = "treasury-yield-csv/1.0.0"
FED_POLICY_VERSION = "federal-reserve-monetary-rss/1.0.0"
BLS_CALENDAR_VERSION = "bls-release-calendar-ics/1.0.0"
MAX_BYTES = 2 * 1024 * 1024
SERIES = {
    "CUUR0000SA0": ("us_cpi_all_items", "index_1982_84_100"),
    "LNS14000000": ("us_unemployment_rate", "percent"),
    "CES0000000001": ("us_total_nonfarm_payrolls", "thousands_persons"),
}


def load_research_source_policy(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != POLICY_VERSION
        or value.get("purpose") != "personal-read-only-research"
        or not {"bls", "treasury", "federal_reserve", "bls_calendar"} <= set(value.get("sources", {}))
    ):
        raise ValueError("RESEARCH_SOURCE_POLICY_INVALID")
    expected = {
        "bls": (BLS_VERSION, ["api.bls.gov"], 1),
        "treasury": (TREASURY_VERSION, ["home.treasury.gov"], 1),
        "federal_reserve": (FED_POLICY_VERSION, ["www.federalreserve.gov"], 2),
        "bls_calendar": (BLS_CALENDAR_VERSION, ["www.bls.gov"], 1),
    }
    for name, (version, domains, budget) in expected.items():
        source = value["sources"][name]
        if (
            source.get("adapter_version") != version
            or source.get("authentication") != "none"
            or source.get("domains") != domains
            or source.get("request_budget") != budget
            or not source.get("limitations")
        ):
            raise ValueError(f"RESEARCH_SOURCE_POLICY_INVALID:{name}")
    if value["sources"]["bls"].get("series") != list(SERIES):
        raise ValueError("RESEARCH_SOURCE_POLICY_SERIES_INVALID")
    openalex = value.get("sources", {}).get("openalex")
    if openalex is not None and (
        openalex.get("adapter_version") != "openalex-public-research/1.0.0"
        or openalex.get("authentication") != "optional_for_search_required_for_content"
        or openalex.get("domains") != ["api.openalex.org", "content.openalex.org"]
        or openalex.get("search_endpoint") != "https://api.openalex.org/works"
        or openalex.get("content_endpoint_template") != "https://content.openalex.org/works/{work_id}.grobid-xml"
        or openalex.get("request_budget") != {
            "searches_per_security": 3,
            "candidates_per_security": 10,
            "content_attempts_per_security": 5,
        }
        or not openalex.get("limitations")
    ):
        raise ValueError("RESEARCH_SOURCE_POLICY_INVALID:openalex")
    parse_timestamp(value["checked_at"])
    return value


def _http(request: Request) -> Response:
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=verified_https_context())).open(
            request, timeout=20
        ) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("OFFICIAL_MACRO_RESPONSE_TOO_LARGE")
            return Response(response.status, body)
    except HTTPError as exc:
        exc.close()
        return Response(exc.code, b"")
    except (URLError, OSError) as exc:
        raise ValueError("OFFICIAL_MACRO_TRANSPORT_FAILURE") from exc


def _fact(
    *, semantic_field: str, value: str, unit: str, source_id: str,
    source_type: str, source_locator: str, source_version: str, as_of: str,
    retrieved_at: str, raw_content_hash: str, metadata: Mapping[str, Any],
    published_at: str | None = None,
    published_at_policy: str = "retrieval_time_conservative/no_historical_vintage",
) -> dict[str, Any]:
    fact = {
        "schema_version": "live-fact/1.0.0",
        "security_id": "US:MARKET",
        "semantic_field": semantic_field,
        "value": value,
        "unit": unit,
        "currency": None,
        "source_id": source_id,
        "source_type": source_type,
        "source_locator": source_locator,
        "source_version": source_version,
        "as_of": iso_utc(as_of),
        # 两个免费响应均缺少足以重建历史 vintage 的精确发布时间；
        # 以获取时间作为保守最早已知时间，宁可排除，不回填观察日。
        "published_at": iso_utc(published_at or retrieved_at),
        "published_at_policy": published_at_policy,
        "retrieved_at": iso_utc(retrieved_at),
        "raw_content_hash": raw_content_hash,
        "kind": "macro",
        "usage": "current",
        "metadata": dict(metadata),
        "parent_ids": [],
        "parent_hashes": [],
    }
    fact["evidence_id"] = "ev-official-macro-" + content_hash(fact)
    validate_contract("fact", fact)
    return fact


def normalize_bls_response(
    raw: bytes, *, retrieved_at: str, endpoint: str,
) -> dict[str, Any]:
    raw_hash = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
        series = payload["Results"]["series"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("BLS_RESPONSE_INVALID") from exc
    if payload.get("status") != "REQUEST_SUCCEEDED" or not isinstance(series, list):
        raise ValueError("BLS_RESPONSE_REJECTED")
    evidence, gaps = [], []
    for item in series:
        series_id = item.get("seriesID")
        if series_id not in SERIES or not isinstance(item.get("data"), list):
            continue
        rows = [row for row in item["data"] if isinstance(row, dict) and row.get("period", "").startswith("M") and row.get("period") != "M13"]
        if not rows:
            gaps.append({"series_id": series_id, "reason": "BLS_SERIES_EMPTY"})
            continue
        row = max(rows, key=lambda value: (int(value["year"]), int(value["period"][1:])))
        month = int(row["period"][1:])
        try:
            number = Decimal(str(row["value"]))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("BLS_VALUE_INVALID") from exc
        if not number.is_finite() or not 1 <= month <= 12:
            raise ValueError("BLS_VALUE_INVALID")
        start = date(int(row["year"]), month, 1)
        end = (date(start.year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
        field, unit = SERIES[series_id]
        evidence.append(_fact(
            semantic_field=field, value=format(number, "f"), unit=unit,
            source_id=f"bls-series-{series_id}", source_type="bls",
            source_locator=f"{endpoint}#{series_id}", source_version=BLS_VERSION,
            as_of=f"{end.isoformat()}T00:00:00Z", retrieved_at=retrieved_at,
            raw_content_hash=raw_hash,
            metadata={
                "series_id": series_id, "year": row["year"], "period": row["period"],
                "period_name": row.get("periodName"), "footnotes": row.get("footnotes", []),
                "historical_vintage_available": False,
            },
        ))
    return {"evidence": evidence, "gaps": gaps, "raw_content_hash": raw_hash}


def normalize_treasury_csv(
    raw: bytes, *, retrieved_at: str, endpoint: str,
) -> dict[str, Any]:
    raw_hash = hashlib.sha256(raw).hexdigest()
    try:
        rows = list(csv.DictReader(StringIO(raw.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise ValueError("TREASURY_RESPONSE_INVALID") from exc
    if not rows:
        raise ValueError("TREASURY_RESPONSE_EMPTY")
    date_key = next((key for key in rows[0] if key and "date" in key.casefold()), None)
    tenor_aliases = {
        "2Y": {"2-year", "2 year", "2 yr"},
        "10Y": {"10-year", "10 year", "10 yr"},
        "30Y": {"30-year", "30 year", "30 yr"},
    }
    tenor_keys = {
        tenor: next((key for key in rows[0] if key and key.strip().casefold() in aliases), None)
        for tenor, aliases in tenor_aliases.items()
    }
    rate_key = tenor_keys["10Y"]
    if date_key is None or rate_key is None:
        raise ValueError("TREASURY_COLUMNS_MISSING")
    candidates = [row for row in rows if row.get(date_key) and row.get(rate_key)]
    if not candidates:
        raise ValueError("TREASURY_RATE_MISSING")
    def parsed_day(row: Mapping[str, str]) -> date:
        text = row[date_key].strip()
        for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, pattern).date()
            except ValueError:
                pass
        raise ValueError("TREASURY_DATE_INVALID")
    row = max(candidates, key=parsed_day)
    try:
        rate = Decimal(row[rate_key].strip())
    except InvalidOperation as exc:
        raise ValueError("TREASURY_RATE_INVALID") from exc
    if not rate.is_finite():
        raise ValueError("TREASURY_RATE_INVALID")
    fact = _fact(
        semantic_field="us_treasury_10y_yield", value=format(rate, "f"), unit="percent",
        source_id="us-treasury-daily-yield-curve", source_type="treasury",
        source_locator=endpoint, source_version=TREASURY_VERSION,
        as_of=f"{parsed_day(row).isoformat()}T00:00:00Z", retrieved_at=retrieved_at,
        raw_content_hash=raw_hash,
        metadata={"tenor": "10Y", "historical_vintage_available": False},
    )
    evidence = [fact]
    gaps = []
    rates: dict[str, Decimal] = {"10Y": rate}
    for tenor in ("2Y", "30Y"):
        key = tenor_keys[tenor]
        raw_value = row.get(key, "") if key is not None else ""
        if not raw_value:
            gaps.append({"reason": "TREASURY_TENOR_MISSING", "tenor": tenor,
                         "observation_date": parsed_day(row).isoformat()})
            continue
        try:
            value = Decimal(raw_value.strip())
        except InvalidOperation as exc:
            raise ValueError("TREASURY_RATE_INVALID") from exc
        if not value.is_finite():
            raise ValueError("TREASURY_RATE_INVALID")
        rates[tenor] = value
        evidence.append(_fact(
            semantic_field=f"us_treasury_{tenor.lower()}_yield", value=format(value, "f"),
            unit="percent", source_id="us-treasury-daily-yield-curve",
            source_type="treasury", source_locator=endpoint, source_version=TREASURY_VERSION,
            as_of=f"{parsed_day(row).isoformat()}T00:00:00Z", retrieved_at=retrieved_at,
            raw_content_hash=raw_hash,
            metadata={"tenor": tenor, "historical_vintage_available": False},
        ))
    if "2Y" in rates:
        spread = rates["10Y"] - rates["2Y"]
        evidence.append(_fact(
            semantic_field="us_treasury_10y_2y_spread", value=format(spread, "f"),
            unit="percentage_points", source_id="us-treasury-daily-yield-curve",
            source_type="treasury", source_locator=endpoint, source_version=TREASURY_VERSION,
            as_of=f"{parsed_day(row).isoformat()}T00:00:00Z", retrieved_at=retrieved_at,
            raw_content_hash=raw_hash,
            metadata={"tenors": ["10Y", "2Y"], "same_observation_date": True,
                      "derivation": "10Y_MINUS_2Y", "historical_vintage_available": False},
        ))
    return {"evidence": evidence, "gaps": gaps, "raw_content_hash": raw_hash}


def _visible_text(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8", "replace")
    except (AttributeError, UnicodeDecodeError) as exc:
        raise ValueError("FEDERAL_RESERVE_DOCUMENT_INVALID") from exc
    text = re.sub(r"(?is)<(script|style|nav|footer).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def normalize_federal_reserve_feed(
    raw: bytes, *, decision_cutoff: str,
) -> dict[str, Any]:
    """从官方货币政策 RSS 选出 cutoff 前最新正文候选。"""

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise ValueError("FEDERAL_RESERVE_FEED_INVALID") from exc
    cutoff = parse_timestamp(decision_cutoff)
    candidates = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        try:
            published_at = parsedate_to_datetime(published).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            title and link.startswith("https://www.federalreserve.gov/")
            and published_at <= cutoff
        ):
            candidates.append((published_at, title, link))
    if not candidates:
        raise ValueError("FEDERAL_RESERVE_POLICY_NOT_AVAILABLE_AT_CUTOFF")
    published_at, title, link = max(candidates, key=lambda item: item[0])
    return {
        "title": title, "source_locator": link,
        "published_at": iso_utc(published_at),
        "feed_raw_content_hash": hashlib.sha256(raw).hexdigest(),
    }


def normalize_federal_reserve_document(
    raw: bytes, *, candidate: Mapping[str, Any], retrieved_at: str,
) -> dict[str, Any]:
    text = _visible_text(raw)
    if len(text) < 120:
        raise ValueError("FEDERAL_RESERVE_DOCUMENT_EMPTY")
    raw_hash = hashlib.sha256(raw).hexdigest()
    fact = _fact(
        semantic_field="federal_reserve_monetary_policy_text",
        value=text[:12000], unit="text",
        source_id="federal-reserve-monetary-policy",
        source_type="federal_reserve",
        source_locator=str(candidate["source_locator"]),
        source_version=FED_POLICY_VERSION,
        as_of=str(candidate["published_at"]), published_at=str(candidate["published_at"]),
        published_at_policy="official_rss_pub_date",
        retrieved_at=retrieved_at, raw_content_hash=raw_hash,
        metadata={
            "title": candidate["title"], "document_kind": "OFFICIAL_POLICY_TEXT",
            "feed_raw_content_hash": candidate["feed_raw_content_hash"],
            "revision_handling": "new retrieval creates a new raw-content version",
        },
    )
    return {"evidence": [fact], "gaps": [], "raw_content_hash": raw_hash}


def _unfold_ics(raw: bytes) -> list[str]:
    try:
        lines = raw.decode("utf-8-sig").replace("\r\n", "\n").split("\n")
    except UnicodeDecodeError as exc:
        raise ValueError("BLS_CALENDAR_INVALID") from exc
    unfolded: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def normalize_bls_calendar_ics(
    raw: bytes, *, retrieved_at: str, endpoint: str, decision_cutoff: str,
) -> dict[str, Any]:
    cutoff = parse_timestamp(decision_cutoff)
    events, current = [], None
    for line in _unfold_ics(raw):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and isinstance(current, dict):
            dtstart = current.get("DTSTART")
            summary = current.get("SUMMARY")
            if dtstart and summary:
                try:
                    if dtstart.endswith("Z"):
                        scheduled = datetime.strptime(dtstart, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                    elif "T" in dtstart:
                        scheduled = datetime.strptime(dtstart, "%Y%m%dT%H%M%S").replace(
                            tzinfo=ZoneInfo("America/New_York")
                        ).astimezone(timezone.utc)
                    else:
                        scheduled = datetime.strptime(dtstart, "%Y%m%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    current = None
                    continue
                if scheduled >= cutoff - timedelta(days=7) and scheduled <= cutoff + timedelta(days=180):
                    events.append({
                        "event_id": current.get("UID") or content_hash({"summary": summary, "scheduled": iso_utc(scheduled)}),
                        "summary": summary.replace("\\,", ","),
                        "scheduled_at": iso_utc(scheduled),
                        "status": current.get("STATUS", "CONFIRMED"),
                    })
            current = None
        elif isinstance(current, dict) and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";", 1)[0]] = value.strip()
    if not events:
        raise ValueError("BLS_CALENDAR_EVENTS_EMPTY")
    raw_hash = hashlib.sha256(raw).hexdigest()
    fact = _fact(
        semantic_field="bls_announced_release_calendar",
        value=json.dumps(sorted(events, key=lambda item: item["scheduled_at"]), ensure_ascii=False),
        unit="event_list", source_id="bls-release-calendar", source_type="bls",
        source_locator=endpoint, source_version=BLS_CALENDAR_VERSION,
        as_of=retrieved_at, retrieved_at=retrieved_at, raw_content_hash=raw_hash,
        metadata={
            "event_count": len(events), "timezone_policy": "TZID America/New_York to UTC",
            "calendar_window": "cutoff_minus_7d_to_plus_180d",
            "announced_not_predicted": True,
        },
    )
    return {"evidence": [fact], "gaps": [], "raw_content_hash": raw_hash}


def collect_official_macro_snapshot(
    *, policy_path: Path, output_path: Path, cache_root: Path,
    decision_cutoff: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    transport: Callable[[Request], Response] = _http,
) -> dict[str, Any]:
    """每个官方来源最多一次请求；失败相互隔离并保留 SOURCE_LIMITED。"""

    policy = load_research_source_policy(policy_path)
    initial_time = now()
    requested_cutoff = parse_timestamp(decision_cutoff) if decision_cutoff else None
    cache = SnapshotCache(cache_root)
    evidence, excluded, gaps, events = [], [], [], []
    year = (requested_cutoff or initial_time).year
    requests = [
        (
            "bls", policy["sources"]["bls"]["endpoint"],
            Request(
                policy["sources"]["bls"]["endpoint"],
                data=json.dumps({"seriesid": list(SERIES), "startyear": str(year - 1), "endyear": str(year)}).encode(),
                headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "stock-agent-readonly/1.0"},
                method="POST",
            ),
            normalize_bls_response,
        ),
        (
            "treasury",
            policy["sources"]["treasury"]["endpoint_template"].format(year=year),
            None,
            normalize_treasury_csv,
        ),
        (
            "bls_calendar", policy["sources"]["bls_calendar"]["endpoint"],
            None,
            lambda raw, *, retrieved_at, endpoint: normalize_bls_calendar_ics(
                raw, retrieved_at=retrieved_at, endpoint=endpoint,
                decision_cutoff=iso_utc(requested_cutoff or initial_time),
            ),
        ),
    ]
    for name, endpoint, request, normalizer in requests:
        request = request or Request(endpoint, headers={"Accept": "text/csv", "User-Agent": "stock-agent-readonly/1.0"}, method="GET")
        event = {"provider": name, "request_number": 1, "started_at": iso_utc(now())}
        events.append(event)
        try:
            response = transport(request)
            event.update(http_status=response.status, completed_at=iso_utc(now()))
            if response.status != 200:
                raise ValueError(f"{name.upper()}_HTTP_{response.status}")
            record = cache.store(
                {"provider": name, "endpoint": endpoint, "adapter_version": policy["sources"][name]["adapter_version"]},
                response.body, retrieved_at=event["completed_at"],
            )
            normalized = normalizer(response.body, retrieved_at=record["retrieved_at"], endpoint=endpoint)
            event.update(status="FETCHED", record_hash=record["record_hash"])
            evidence.extend(normalized["evidence"])
            gaps.extend(dict(item, provider=name) for item in normalized["gaps"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            code = str(exc).split(":", 1)[0]
            event.update(status="FAILED", failure_code=code, completed_at=event.get("completed_at", iso_utc(now())))
            gaps.append({"provider": name, "reason": code})
    fed = policy["sources"]["federal_reserve"]
    feed_endpoint = fed["feed_endpoint"]
    feed_event = {"provider": "federal_reserve", "request_number": 1, "started_at": iso_utc(now())}
    events.append(feed_event)
    try:
        feed_response = transport(Request(
            feed_endpoint,
            headers={"Accept": "application/rss+xml, application/xml", "User-Agent": "stock-agent-readonly/1.0"},
            method="GET",
        ))
        feed_event.update(http_status=feed_response.status, completed_at=iso_utc(now()))
        if feed_response.status != 200:
            raise ValueError(f"FEDERAL_RESERVE_HTTP_{feed_response.status}")
        candidate = normalize_federal_reserve_feed(
            feed_response.body,
            decision_cutoff=iso_utc(requested_cutoff or initial_time),
        )
        feed_record = cache.store(
            {"provider": "federal_reserve", "endpoint": feed_endpoint,
             "adapter_version": FED_POLICY_VERSION, "operation": "feed"},
            feed_response.body, retrieved_at=feed_event["completed_at"],
        )
        feed_event.update(status="FETCHED", record_hash=feed_record["record_hash"])
        document_event = {
            "provider": "federal_reserve", "request_number": 2,
            "started_at": iso_utc(now()), "source_locator": candidate["source_locator"],
        }
        events.append(document_event)
        document_response = transport(Request(
            candidate["source_locator"],
            headers={"Accept": "text/html", "User-Agent": "stock-agent-readonly/1.0"},
            method="GET",
        ))
        document_event.update(http_status=document_response.status, completed_at=iso_utc(now()))
        if document_response.status != 200:
            raise ValueError(f"FEDERAL_RESERVE_DOCUMENT_HTTP_{document_response.status}")
        document_record = cache.store(
            {"provider": "federal_reserve", "endpoint": candidate["source_locator"],
             "adapter_version": FED_POLICY_VERSION, "operation": "policy_document"},
            document_response.body, retrieved_at=document_event["completed_at"],
        )
        normalized = normalize_federal_reserve_document(
            document_response.body, candidate=candidate,
            retrieved_at=document_record["retrieved_at"],
        )
        document_event.update(status="FETCHED", record_hash=document_record["record_hash"])
        evidence.extend(normalized["evidence"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        code = str(exc).split(":", 1)[0]
        active = events[-1] if events and events[-1].get("provider") == "federal_reserve" else feed_event
        active.update(status="FAILED", failure_code=code, completed_at=active.get("completed_at", iso_utc(now())))
        gaps.append({"provider": "federal_reserve", "reason": code})
    cutoff = requested_cutoff or now()
    admitted = []
    for fact in evidence:
        if max(
            parse_timestamp(fact["as_of"]), parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
        ) <= cutoff:
            admitted.append(fact)
        else:
            excluded.append({"evidence_id": fact["evidence_id"], "reason": "PIT_AFTER_DECISION_CUTOFF"})
    snapshot = {
        "schema_version": "official-macro-snapshot/1.1.0",
        "status": "FROZEN" if admitted else "SOURCE_LIMITED",
        "decision_cutoff": iso_utc(cutoff),
        "evidence": sorted(admitted, key=lambda item: item["evidence_id"]),
        "excluded": sorted(excluded, key=lambda item: item["evidence_id"]),
        "gaps": gaps,
        "events": events,
        "policy_version": POLICY_VERSION,
        "policy_hash": content_hash(policy),
    }
    snapshot["snapshot_hash"] = content_hash(snapshot)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot
