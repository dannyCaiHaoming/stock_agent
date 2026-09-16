"""按披露类型与时间选取材料，不按预期投资结论筛选。"""
from datetime import date, timedelta

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp

SELECTION_VERSION = "sec-filing-selection/1.0.0"


def select_filings(
    filings: dict[str, dict], *, selection_as_of: str, event_limit: int = 3,
) -> dict:
    """采集阶段参考时点不是最终 decision_cutoff；最终 PIT 仍需独立执行。"""
    if type(event_limit) is not int or not 0 <= event_limit <= 3:
        raise ValueError("SEC_EVENT_SELECTION_BUDGET_INVALID")
    cutoff = parse_timestamp(selection_as_of)
    eligible, excluded = [], []
    ciks = set()
    for accession, filing in filings.items():
        if filing["accession"] != accession:
            raise ValueError("SEC_ACCESSION_BINDING_MISMATCH")
        ciks.add(filing["cik"])
        published = parse_timestamp(filing["published_at"])
        retrieved = parse_timestamp(filing["retrieved_at"])
        if published > cutoff or retrieved > cutoff:
            excluded.append({"accession": accession, "reason": "AFTER_SELECTION_AS_OF"})
        else:
            eligible.append(filing)
    if len(ciks) > 1:
        raise ValueError("SEC_SELECTION_MULTIPLE_ISSUERS")
    eligible.sort(key=lambda f: (parse_timestamp(f["published_at"]), f["accession"]), reverse=True)
    annuals = [f for f in eligible if f["form"] == "10-K" and f["report_date"]]
    annual = max(annuals, key=lambda f: (date.fromisoformat(f["report_date"]), parse_timestamp(f["published_at"]))) if annuals else None
    quarters = [f for f in eligible if f["form"] == "10-Q" and f["report_date"] and
                (annual is None or (date.fromisoformat(f["report_date"]) > date.fromisoformat(annual["report_date"]) and
                                    parse_timestamp(f["published_at"]) > parse_timestamp(annual["published_at"])))]
    quarter = max(quarters, key=lambda f: (date.fromisoformat(f["report_date"]), parse_timestamp(f["published_at"]))) if quarters else None
    events = [f for f in eligible if f["form"] == "8-K" and
              parse_timestamp(f["published_at"]) >= cutoff - timedelta(days=90)]
    selected = [f for f in (annual, quarter) if f is not None] + events[:event_limit]
    # 修订作为补充保留，不用 /A 文件取代完整基准披露。
    amendments = [f for f in eligible if f["form"] in ("10-K/A", "10-Q/A") and any(
        f["form"] == base["form"] + "/A" and f["report_date"] == base["report_date"]
        and parse_timestamp(f["published_at"]) >= parse_timestamp(base["published_at"])
        for base in selected)]
    selected += amendments
    return {"selected": selected, "excluded": excluded,
            "omitted_event_accessions": [f["accession"] for f in events[event_limit:]],
            "gaps": (["ANNUAL_DISCLOSURE_MISSING"] if annual is None else []) +
                    (["EVENT_AMENDMENTS_REQUIRE_REVIEW"] if any(f["form"] == "8-K/A" for f in eligible) else []),
            "selection_as_of": iso_utc(cutoff), "selection_version": SELECTION_VERSION,
            "input_hash": content_hash(filings), "coverage": "AVAILABLE_FILINGS_ONLY"}
