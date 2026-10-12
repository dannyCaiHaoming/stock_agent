"""沿用既有Company资料范围；不作投资判断。"""
import copy
from typing import Any, Mapping, Sequence
from product.mcp.provenance import parse_timestamp

COMPANY_RESEARCH_EXCLUDED_SEMANTIC_FIELDS = frozenset({
    "adjusted_close_price",
    "historical_close_price",
    "open_price",
    "high_price",
    "low_price",
    "share_volume",
})

COMPANY_RESEARCH_EXCLUDED_DATASETS = frozenset({
    "share_short_context",
    "institutional_ownership",
    "insider_transactions",
    "analyst_expectations",
    "research_discovery",
    "options_snapshot",
    "vendor_money_flow",
    "options_underlying_context",
    "option_market_statistics",
    "market_breadth",
    "macro_history",
    "economic_calendar",
    "fedwatch_expectations",
    "dot_plot",
})

def is_company_research_evidence(fact: Mapping[str, Any]) -> bool:
    return (
        fact.get("semantic_field") not in COMPANY_RESEARCH_EXCLUDED_SEMANTIC_FIELDS
        and fact.get("dataset") not in COMPANY_RESEARCH_EXCLUDED_DATASETS
    )


RESEARCH_CAPABILITIES = (
    "TECHNICAL_STRUCTURE", "FUNDAMENTAL_EVENT", "RESEARCH_REPORT", "INDUSTRY_COMPARISON",
    "MACRO_CONTEXT", "MARKET_STATE", "OWNERSHIP_DISCLOSURE", "OPTIONS_FLOW",
)

CAPABILITY_BINDINGS = {
    "TECHNICAL_STRUCTURE": ("runtime_market_catalyst", "technical-structure", "PER_SECURITY"),
    "FUNDAMENTAL_EVENT": ("runtime_company_analyst", "company-research", "PER_SECURITY"),
    "RESEARCH_REPORT": ("runtime_company_analyst", "research-report-analysis", "PER_SECURITY"),
    "INDUSTRY_COMPARISON": ("runtime_market_catalyst", "industry-comparison", "PER_SECURITY"),
    "MACRO_CONTEXT": ("runtime_market_catalyst", "macro-market-analysis", "SHARED_MARKET"),
    "MARKET_STATE": ("runtime_market_catalyst", "macro-market-analysis", "SHARED_MARKET"),
    "OWNERSHIP_DISCLOSURE": ("runtime_market_catalyst", "ownership-disclosure", "PER_SECURITY"),
    "OPTIONS_FLOW": ("runtime_market_catalyst", "options-market-structure", "PER_SECURITY"),
}

def capability_tools(capability: str) -> list[str]:
    if capability not in CAPABILITY_BINDINGS:
        raise ValueError(f"RESEARCH_CAPABILITY_UNMAPPED:{capability}")
    return (["fixture_evidence.query", "fixture_math.calculate"]
            if capability in {"OWNERSHIP_DISCLOSURE", "FUNDAMENTAL_EVENT"}
            else ["fixture_evidence.query"])

DATASET_CAPABILITY_ROUTES = {
    "FUNDAMENTAL_EVENT": {
        "identity_profile", "business_segments", "management_governance",
        "financial_history", "capital_allocation", "earnings_guidance", "event_context",
    },
    "RESEARCH_REPORT": {"analyst_expectations", "research_discovery"},
    "OWNERSHIP_DISCLOSURE": {
        "institutional_ownership", "insider_transactions", "share_short_context",
    },
    "MACRO_CONTEXT": {"macro_history", "economic_calendar", "dot_plot"},
    "MARKET_STATE": {
        "market_breadth", "option_market_statistics", "fedwatch_expectations",
    },
    "OPTIONS_FLOW": {
        "options_snapshot", "options_underlying_context", "vendor_money_flow",
    },
}

def select_capability_facts(
    evidence: Sequence[Mapping[str, Any]], *, capability: str, security_ids: Sequence[str], benchmark_id: str | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    scoped_ids = set(security_ids)
    latest_closes: dict[str, Mapping[str, Any]] = {}
    if capability == "FUNDAMENTAL_EVENT":
        # 输入来自已过 PIT 的 Gate；只补最近历史收盘，不授予全行情/估值权限。
        for fact in evidence:
            sid = fact.get("security_id")
            if sid not in scoped_ids or fact.get("semantic_field") != "historical_close_price":
                continue
            key = lambda item: (parse_timestamp(item["as_of"]),
                                parse_timestamp(item["retrieved_at"]), item["evidence_id"])
            if sid not in latest_closes or key(fact) > key(latest_closes[sid]):
                latest_closes[sid] = fact
    close_ids = {fact["evidence_id"] for fact in latest_closes.values()}
    if benchmark_id and capability == "TECHNICAL_STRUCTURE":
        scoped_ids.add(benchmark_id)
    for fact in evidence:
        field = str(fact.get("semantic_field", ""))
        dataset = str(fact.get("dataset", ""))
        source = str(fact.get("source_type", ""))
        source_family = str(fact.get("source_family", ""))
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        form = str(metadata.get("form", ""))
        security_id = fact.get("security_id")
        matches = False
        if capability == "TECHNICAL_STRUCTURE":
            matches = security_id in scoped_ids and field in {
                "open_price", "high_price", "low_price", "historical_close_price",
                "adjusted_close_price", "share_volume", "cash_dividend", "stock_split_ratio",
            }
        elif capability == "FUNDAMENTAL_EVENT":
            # `source_type` is optional on older normalized Evidence.  Preserve
            # Preserve SEC/provider dataset routing; add only the target's
            # latest Gate-admitted historical close, not its full price series.
            source_id = str(fact.get("source_id", "")).lower()
            matches = security_id in scoped_ids and (
                source == "sec" or "sec" in source_id
                or dataset in DATASET_CAPABILITY_ROUTES[capability]
                or fact.get("evidence_id") in close_ids
            )
        elif capability == "RESEARCH_REPORT":
            matches = security_id in scoped_ids and (
                dataset in DATASET_CAPABILITY_ROUTES[capability]
                or
                source in {"public_research", "issuer_research"}
                or source_family in {"sec", "yahoo", "moomoo_sg"}
                and field in {
                    "sec_issuer_guidance_candidate_text", "yahoo_earnings_trend",
                    "yahoo_recommendation_trend", "moomoo_analyst_consensus",
                }
                or source == "sec" and field in {"earnings_release", "management_discussion"}
            )
        elif capability == "INDUSTRY_COMPARISON":
            matches = security_id in scoped_ids and (
                source in {"sec", "yahoo", "public_research"} or field.startswith("industry_")
                or source_family in {"sec", "yahoo", "moomoo_sg"} and dataset in {
                    "identity_profile", "business_segments", "analyst_expectations",
                    "research_discovery",
                }
            )
        elif capability == "MACRO_CONTEXT":
            matches = (security_id in {"MARKET", "US:MARKET"} and dataset in DATASET_CAPABILITY_ROUTES[capability]) or source in {
                "fred", "bls", "bea", "federal_reserve", "treasury"
            }
        elif capability == "MARKET_STATE":
            matches = (security_id in {"MARKET", "US:MARKET"} and dataset in DATASET_CAPABILITY_ROUTES[capability]) or source in {
                "yahoo", "market", "fred", "treasury", "eia"
            } or (
                security_id == "US:MARKET" and field == "market_news_item"
                and source == "public_research"
                and str(fact.get("source_id", "")).startswith("moomoo-public-news:")
            )
        elif capability == "OWNERSHIP_DISCLOSURE":
            matches = security_id in scoped_ids and (
                dataset in DATASET_CAPABILITY_ROUTES[capability]
                or form in {"3", "4", "5", "13F-HR", "13F-HR/A"}
                or field.startswith("ownership_")
            )
        elif capability == "OPTIONS_FLOW":
            matches = security_id in scoped_ids and (
                dataset in DATASET_CAPABILITY_ROUTES[capability]
                or source == "options" or field.startswith(("option_", "short_", "fund_flow_", "moomoo_option_"))
            )
        if matches:
            selected.append(copy.deepcopy(dict(fact)))
    return sorted(selected, key=lambda item: str(item.get("evidence_id")))
