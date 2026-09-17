"""三源事件/新闻/电话会定位与空头统计语义标准化。"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from product.mcp.live.research_supplement import build_supplement_fact


ADAPTER_VERSION = "research-event-context/1.0.0"
EVENT_TIERS = {"TITLE_ONLY", "SUMMARY", "TRANSCRIPT_LOCATOR", "SEC_FILING"}
SHORT_TYPES = {"SHORT_INTEREST", "SHORT_VOLUME"}


def normalize_event_rows(
    rows: Sequence[Mapping[str, Any]], *, source_family: str, security_id: str,
    ticker: str, retrieved_at: str, raw_content_hash: str, source_locator: str,
    allowed_original_hosts: Sequence[str],
) -> dict[str, Any]:
    if source_family not in {"sec", "yahoo", "moomoo_sg"}:
        raise ValueError("EVENT_SOURCE_INVALID")
    allowed_hosts = {host.lower() for host in allowed_original_hosts}
    evidence, gaps, seen = [], [], set()
    for row in rows:
        required = {"title", "published_at", "as_of", "content_tier", "event_type"}
        if not required <= set(row) or row["content_tier"] not in EVENT_TIERS:
            raise ValueError("EVENT_FIELDS_INVALID")
        original_url = row.get("original_url")
        if original_url is not None:
            parsed = urlsplit(original_url)
            if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
                gaps.append({
                    "reason": "EVENT_FOURTH_PARTY_LINK_EXCLUDED", "title": row["title"],
                    "original_url": original_url,
                })
                continue
        key = original_url or (str(row["title"]).casefold(), row["published_at"])
        if key in seen:
            gaps.append({"reason": "EVENT_DUPLICATE_EXCLUDED", "title": row["title"]})
            continue
        seen.add(key)
        value = {
            "title": row["title"], "event_type": row["event_type"],
            "summary": row.get("summary"), "content_tier": row["content_tier"],
            "original_url": original_url, "event_date": row.get("event_date"),
            "event_date_status": "ESTIMATED" if row.get("event_date_estimated") else "REPORTED",
            "transcript_status": (
                "LOCATOR_ONLY" if row["content_tier"] == "TRANSCRIPT_LOCATOR"
                else "NOT_AVAILABLE" if row["content_tier"] == "TITLE_ONLY" else "NOT_APPLICABLE"
            ),
        }
        limitations = []
        if row["content_tier"] == "TITLE_ONLY":
            limitations.append("仅标题，不形成正文事实或事件影响结论")
        if row.get("event_date_estimated"):
            limitations.append("事件日期为供应商估计，未获公司确认")
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="event_context",
            semantic_field="research_event_item", value=value,
            source_id=f"{source_family}-event:{ticker}", source_family=source_family,
            source_locator=source_locator, source_version=ADAPTER_VERSION,
            as_of=row["as_of"], published_at=row["published_at"],
            retrieved_at=retrieved_at, raw_content_hash=raw_content_hash,
            limitations=limitations,
        ))
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": gaps}


def normalize_short_rows(
    rows: Sequence[Mapping[str, Any]], *, source_family: str, security_id: str,
    ticker: str, retrieved_at: str, raw_content_hash: str, source_locator: str,
) -> dict[str, Any]:
    if source_family not in {"yahoo", "moomoo_sg"}:
        raise ValueError("SHORT_SOURCE_INVALID")
    evidence = []
    for row in rows:
        required = {"statistic_type", "value", "unit", "as_of"}
        if not required <= set(row) or row["statistic_type"] not in SHORT_TYPES:
            raise ValueError("SHORT_FIELDS_INVALID")
        value = {
            "statistic_type": row["statistic_type"], "value": row["value"],
            "unit": row["unit"], "period_start": row.get("period_start"),
            "period_end": row.get("period_end"),
            "days_to_cover": row.get("days_to_cover") if row["statistic_type"] == "SHORT_INTEREST" else None,
            "borrow_fee": None,
        }
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="share_short_context",
            semantic_field=(
                "short_interest_snapshot" if row["statistic_type"] == "SHORT_INTEREST"
                else "short_volume_snapshot"
            ),
            value=value, source_id=f"{source_family}-short:{ticker}",
            source_family=source_family, source_locator=source_locator,
            source_version=ADAPTER_VERSION, as_of=row["as_of"],
            published_at=row.get("published_at", row["as_of"]), retrieved_at=retrieved_at,
            raw_content_hash=raw_content_hash,
            limitations=[
                "short interest 与 short volume 为不同统计口径，不得互换",
                "未取得借券费率，不推算借券成本或挤空评分",
            ],
        ))
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": []}
