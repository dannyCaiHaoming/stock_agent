"""把冻结行情与 SEC 事实装配为可验证的公司估值研究输入。"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from product.mcp.provenance import iso_utc, parse_timestamp


class CompanyValuationReportError(ValueError):
    pass


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CompanyValuationReportError(f"COMPANY_VALUATION_NUMBER_INVALID:{name}") from exc
    if not result.is_finite():
        raise CompanyValuationReportError(f"COMPANY_VALUATION_NUMBER_INVALID:{name}")
    return result


def normalized_daily_rows(
    facts: Sequence[Mapping[str, Any]], *, security_id: str,
) -> list[dict[str, Any]]:
    """把冻结 Yahoo 字段事实重组为一日一行；不以 Adj Close 替代 PE 价格。"""

    fields = {
        "open_price": "open", "high_price": "high", "low_price": "low",
        "historical_close_price": "close", "adjusted_close_price": "adjusted_close",
        "share_volume": "volume",
    }
    rows: dict[str, dict[str, Any]] = {}
    refs: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        if fact.get("security_id") != security_id or fact.get("semantic_field") not in fields:
            continue
        if not all(fact.get(key) for key in ("source_id", "as_of", "retrieved_at", "evidence_id")):
            raise CompanyValuationReportError("COMPANY_VALUATION_MARKET_PROVENANCE_MISSING")
        day = str((fact.get("metadata") or {}).get("trading_date") or str(fact["as_of"])[:10])
        row = rows.setdefault(day, {"date": day})
        output_field = fields[str(fact["semantic_field"])]
        value = format(_decimal(fact.get("value"), output_field), "f")
        if output_field in row and row[output_field] != value:
            raise CompanyValuationReportError("COMPANY_VALUATION_MARKET_FIELD_CONFLICT")
        row[output_field] = value
        refs[day].add(str(fact["evidence_id"]))
    result = []
    for day in sorted(rows):
        row = rows[day]
        if not all(field in row for field in ("open", "high", "low", "close", "volume")):
            continue
        row["evidence_refs"] = sorted(refs[day])
        result.append(row)
    return result


def valuation_price_rows(
    daily_rows: Sequence[Mapping[str, Any]], *, security_id: str,
    segment_id: str = "continuing-entity",
) -> list[dict[str, Any]]:
    return [{
        "date": str(row["date"]), "close": str(row["close"]),
        "evidence_refs": sorted(set(row.get("evidence_refs", []))),
        "price_basis": "CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
        "dividend_adjusted": False, "currency": "USD",
        "security_id": security_id, "segment_id": segment_id,
    } for row in daily_rows]


def _quarter_candidates(
    facts: Sequence[Mapping[str, Any]], *, security_id: str, decision_cutoff: str,
) -> list[dict[str, Any]]:
    cutoff = parse_timestamp(decision_cutoff)
    candidates = []
    for fact in facts:
        if fact.get("security_id") != security_id or fact.get("semantic_field") != "us-gaap.EarningsPerShareDiluted":
            continue
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        start, end = metadata.get("period_start"), metadata.get("period_end")
        published, retrieved = fact.get("published_at"), fact.get("retrieved_at")
        if not all((start, end, published, retrieved, fact.get("evidence_id"))):
            continue
        days = (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1
        if not 70 <= days <= 110 or str(metadata.get("unit") or fact.get("unit")) not in {"USD/shares", "USD / shares"}:
            continue
        if parse_timestamp(str(published)) > cutoff or parse_timestamp(str(retrieved)) > cutoff:
            continue
        candidates.append({
            "period_start": str(start), "period_end": str(end),
            "published_at": iso_utc(str(published)), "retrieved_at": iso_utc(str(retrieved)),
            "value": format(_decimal(fact.get("value"), "diluted_eps"), "f"),
            "evidence_id": str(fact["evidence_id"]),
        })
    return candidates


def build_pit_ttm_eps_versions(
    facts: Sequence[Mapping[str, Any]], *, security_id: str, decision_cutoff: str,
    segment_id: str = "continuing-entity",
) -> list[dict[str, Any]]:
    """按每次公开时点选四个最近独立季度，形成带限制的 TTM diluted EPS。

    EPS 不从累计期间相减；仅对 SEC 已单独披露的季度每股数求和。因季度
    加权平均股数可能变化，输出明确保留近似限制。
    """

    candidates = _quarter_candidates(
        facts, security_id=security_id, decision_cutoff=decision_cutoff,
    )
    publications = sorted({item["published_at"] for item in candidates})
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for published in publications:
        available = [item for item in candidates if item["published_at"] <= published]
        by_period: dict[tuple[str, str], dict[str, Any]] = {}
        for item in available:
            key = (item["period_start"], item["period_end"])
            previous = by_period.get(key)
            if previous is None or (item["published_at"], item["evidence_id"]) > (previous["published_at"], previous["evidence_id"]):
                by_period[key] = item
        quarters = sorted(by_period.values(), key=lambda item: item["period_end"])[-4:]
        if len(quarters) != 4:
            continue
        ends = [date.fromisoformat(item["period_end"]) for item in quarters]
        if any(not 70 <= (ends[index] - ends[index - 1]).days <= 110 for index in range(1, 4)):
            continue
        value = sum((_decimal(item["value"], "quarter_eps") for item in quarters), Decimal(0))
        fingerprint = (published, quarters[-1]["period_end"], format(value, "f"))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        output.append({
            "published_at": published,
            "retrieved_at": max(item["retrieved_at"] for item in quarters),
            "financial_period": quarters[-1]["period_end"],
            "period_start": quarters[0]["period_start"],
            "value": format(value, "f"), "currency": "USD",
            "share_basis": "SPLIT_ADJUSTED", "security_id": security_id,
            "segment_id": segment_id,
            "evidence_refs": sorted(item["evidence_id"] for item in quarters),
            "formula": "sum of four independently disclosed quarterly diluted EPS values",
            "limitation": "季度 diluted EPS 的加权平均股数可能不同；未从累计 EPS 相减",
        })
    return output


def select_latest_fact(
    facts: Sequence[Mapping[str, Any]], *, security_id: str, semantic_field: str,
    decision_cutoff: str, duration_days: tuple[int, int] | None = None,
) -> dict[str, Any] | None:
    """选择 cutoff 前最新公开版本；期间筛选显式且不按 retrieved_at 覆盖。"""

    cutoff = parse_timestamp(decision_cutoff)
    selected = []
    for fact in facts:
        if fact.get("security_id") != security_id or fact.get("semantic_field") != semantic_field:
            continue
        published, retrieved = fact.get("published_at"), fact.get("retrieved_at")
        if not published or not retrieved or parse_timestamp(str(published)) > cutoff or parse_timestamp(str(retrieved)) > cutoff:
            continue
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        if duration_days is not None:
            start, end = metadata.get("period_start"), metadata.get("period_end")
            if not start or not end:
                continue
            days = (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1
            if not duration_days[0] <= days <= duration_days[1]:
                continue
        selected.append(fact)
    if not selected:
        return None
    return deepcopy(max(selected, key=lambda item: (
        str((item.get("metadata") or {}).get("period_end") or item.get("as_of") or ""),
        str(item.get("published_at")), str(item.get("evidence_id")),
    )))
