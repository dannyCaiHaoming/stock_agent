"""有限财务比较：只计算，不给投资评分、Thesis 或动作。"""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp

CALCULATION_VERSION = "sec-comparison/1.2.0"


def _same_filing_week_comparison(current, prior):
    """Only explicit comparative periods in one filing, not date tolerance alone."""
    if (current["context_type"] != "duration" or not current.get("accession")
            or current.get("accession") != prior.get("accession")
            or current.get("form") != prior.get("form")
            or current.get("form") not in {"10-K", "10-Q"}):
        return False
    starts = [date.fromisoformat(p["period_start"]) for p in (current, prior)]
    ends = [date.fromisoformat(p["period_end"]) for p in (current, prior)]
    lengths = [(end - start).days + 1 for start, end in zip(starts, ends)]
    buckets = ((364, 371),) if current["form"] == "10-K" else ((91, 98), (182, 189), (273, 280))
    return (all((new - old).days in {364, 371} for new, old in (starts, ends))
            and any(all(length in bucket for length in lengths) for bucket in buckets)
            and ends[1] < starts[0])


def compare_year_over_year(current_id: str, prior_id: str, evidence: dict[str, dict]) -> dict:
    if current_id == prior_id or current_id not in evidence or prior_id not in evidence:
        raise ValueError("FINANCIAL_PARENT_INVALID")
    current, prior = evidence[current_id], evidence[prior_id]
    for identifier, parent in ((current_id, current), (prior_id, prior)):
        if parent["evidence_id"] != identifier:
            raise ValueError("FINANCIAL_PARENT_ID_MISMATCH")
        for field in ("source_id", "source_locator", "as_of", "published_at", "retrieved_at"):
            if not parent.get(field):
                raise ValueError("FINANCIAL_PROVENANCE_MISSING")
    for key in ("security_id", "cik", "taxonomy", "tag", "unit", "context_type"):
        if not current.get(key) or current[key] != prior.get(key):
            raise ValueError("FINANCIAL_CONTEXT_MISMATCH")
    if current["context_type"] not in ("instant", "duration"):
        raise ValueError("FINANCIAL_CONTEXT_UNSUPPORTED")
    # Calendar anniversaries retain v1 semantics. Fiscal-week comparisons require
    # the same disclosed filing and explicit nonoverlapping period lengths.
    boundaries = ("period_end", "period_start") if current["context_type"] == "duration" else ("period_end",)
    calendar_anniversary = True
    for key in boundaries:
        newer, older = date.fromisoformat(current[key]), date.fromisoformat(prior[key])
        if (newer.year - older.year, newer.month, newer.day) != (1, older.month, older.day):
            calendar_anniversary = False
    if not calendar_anniversary and not _same_filing_week_comparison(current, prior):
        raise ValueError("FINANCIAL_PERIOD_NOT_COMPARABLE")
    if current["context_type"] == "duration":
        if any(date.fromisoformat(p["period_start"]) > date.fromisoformat(p["period_end"]) for p in (current, prior)):
            raise ValueError("FINANCIAL_PERIOD_INVALID")
        if date.fromisoformat(prior["period_end"]) >= date.fromisoformat(current["period_start"]):
            raise ValueError("FINANCIAL_PERIOD_OVERLAP")
    elif any(p.get("period_start") is not None for p in (current, prior)):
        raise ValueError("FINANCIAL_INSTANT_WITH_START")
    try:
        a, b = (Decimal(str(p["value"])) for p in (current, prior))
    except InvalidOperation as exc:
        raise ValueError("FINANCIAL_VALUE_INVALID") from exc
    if not a.is_finite() or not b.is_finite():
        raise ValueError("FINANCIAL_VALUE_NON_FINITE")
    with localcontext() as context:
        context.prec = 34
        delta = a - b
        percent = delta / b * 100 if b > 0 else None
    parents = [current, prior]
    result = {
        "source_id": "derived-sec-comparison", "source_locator": "parent_evidence",
        "security_id": current["security_id"], "semantic_field": "year_over_year_comparison",
        "parent_ids": [current_id, prior_id], "parent_hashes": [content_hash(p) for p in parents],
        "tag": current["tag"], "unit": current["unit"],
        "value": {"absolute_change": format(delta, "f"),
                  "percent_change": format(percent, "f") if percent is not None else None},
        "percentage_unavailable_reason": "NON_POSITIVE_BASE" if percent is None else None,
        "formula": {"absolute_change": "current-prior", "percent_change": "(current-prior)/prior*100; prior>0"},
        "comparison_policy": "same-context/nonoverlapping-calendar-anniversary/1.0.0",
        "comparability_scope": "MATCHED_METRIC_UNIT_AND_PERIOD_STRUCTURE_ONLY",
        "accounting_basis_status": "UNVERIFIED",
        "share_denominator_status": "UNVERIFIED" if current["unit"] == "USD/shares" else "NOT_APPLICABLE",
        "trend_interpretation_status": "REQUIRES_EVIDENCE_REVIEW",
        "comparison_limitation": (
            "Date alignment, metric and unit support the arithmetic change only; "
            "accounting basis, reporting entity and economic comparability remain unverified."
        ),
        "calculation_version": CALCULATION_VERSION, "decimal_precision": 34,
        "periods": [{key: p.get(key) for key in ("period_start", "period_end")} for p in parents],
    }
    for key in ("as_of", "published_at", "retrieved_at"):
        result[key] = iso_utc(max(parse_timestamp(p[key]) for p in parents))
    if not calendar_anniversary:
        result["comparison_policy"] = "same-filing/nonoverlapping-fiscal-weeks/1.0.0"
        result["period_day_counts"] = [(date.fromisoformat(p["period_end"]) - date.fromisoformat(p["period_start"])).days + 1 for p in parents]
        result["period_length_adjusted"] = False
        result["comparison_limitation"] = (
            "Same filing and matched fiscal-week duration support the arithmetic change only; "
            "disclose day counts, do not imply calendar-quarter equivalence, and verify accounting "
            "basis, reporting entity and per-share denominator before interpreting a trend."
        )
    result["evidence_id"] = "ev-sec-derived-" + content_hash(result)
    return result
