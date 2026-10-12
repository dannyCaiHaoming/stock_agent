"""stock-data MCP server: read-only US equity data and deterministic calculations.

Run with: python -m product.mcp.server  (stdio transport)
Environment: STOCK_AGENT_DATA_DIR (default ~/StockAgentData), SEC_USER_AGENT ("app contact@email").
"""

from __future__ import annotations

from datetime import UTC, datetime

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from product.mcp import calc_tools, data_tools, decision_log

server = MCPServer(
    name="stock-data",
    instructions=(
        "Read-only US equity research data and deterministic financial calculations. "
        "Every result carries provenance (source_id, as_of, retrieved_at). Use calculation tools for "
        "all arithmetic. `as_of` limits data to what was published by that date. No trading capability."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
LOCAL_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
def ping() -> dict[str, str]:
    """Health check: confirms the stock-data server is reachable."""
    return {"status": "ok", "server": "stock-data", "time": datetime.now(UTC).isoformat()}


@server.tool(annotations=READ_ONLY)
def get_price_history(ticker: str, start: str | None = None, end: str | None = None,
                      interval: str = "1d", as_of: str | None = None) -> dict:
    """Daily/weekly/monthly OHLCV, adjusted close, dividends and splits (Yahoo).
    Defaults to the last 365 days. Dates are YYYY-MM-DD. Max 800 rows; use 1wk/1mo for long ranges."""
    return data_tools.get_price_history(ticker, start=start, end=end, interval=interval, as_of=as_of)


@server.tool(annotations=READ_ONLY)
def get_analyst_snapshot(ticker: str) -> dict:
    """Current company profile, key statistics, analyst consensus (targets, ratings), EPS/revenue
    estimates with 7-90 day estimate trend and revisions, and next earnings date (Yahoo, current-only)."""
    return data_tools.get_analyst_snapshot(ticker)


@server.tool(annotations=READ_ONLY)
def get_financial_statements(ticker: str, period: str = "annual", limit: int = 5,
                             as_of: str | None = None) -> dict:
    """Standardized income statement, cash flow and balance sheet lines from SEC XBRL (as reported).
    period: annual | quarterly (quarterly includes a TTM block and derived Q4 = FY - 9M YTD).
    Cells are strings in USD unless noted in `units`; null means not reported (not zero)."""
    return data_tools.get_financial_statements(ticker, period=period, limit=limit, as_of=as_of)


@server.tool(annotations=READ_ONLY)
def get_sec_concept(ticker: str, tag: str, taxonomy: str = "us-gaap", limit: int = 12,
                    as_of: str | None = None) -> dict:
    """All periods of one XBRL concept (e.g. tag='OperatingLeaseLiability'), latest version per period,
    with accession and publication time. Use for lines missing from get_financial_statements."""
    return data_tools.get_sec_concept(ticker, tag, taxonomy=taxonomy, limit=limit, as_of=as_of)


@server.tool(annotations=READ_ONLY)
def list_filings(ticker: str, forms: list[str] | None = None, limit: int = 20,
                 as_of: str | None = None) -> dict:
    """Recent SEC filings (accession, form, report date, acceptance time). forms e.g. ['10-K','10-Q','8-K']."""
    return data_tools.list_filings(ticker, forms=forms, limit=limit, as_of=as_of)


@server.tool(annotations=READ_ONLY)
def get_filing_text(ticker: str, accession: str | None = None, form: str = "10-K",
                    section: str = "management_discussion", offset: int = 0, max_chars: int = 12000,
                    as_of: str | None = None) -> dict:
    """Text of a 10-K/10-Q/8-K. section: business | risk_factors | management_discussion | full_text.
    Without accession, uses the latest filing of `form`. Page with offset/next_offset."""
    return data_tools.get_filing_text(ticker, accession=accession, form=form, section=section,
                                      offset=offset, max_chars=max_chars, as_of=as_of)


@server.tool(annotations=READ_ONLY)
def technical_stats(ticker: str, benchmark: str = "SPY", as_of: str | None = None) -> dict:
    """20/60/252-session total and relative return, annualized volatility, max drawdown, volume ratio,
    window high/low, and 50/200-day moving averages, versus a benchmark ETF."""
    return calc_tools.technical_stats(ticker, benchmark=benchmark, as_of=as_of)


@server.tool(annotations=READ_ONLY)
def pe_history(ticker: str, years: int = 5, as_of: str | None = None) -> dict:
    """Monthly trailing P/E from fiscal-year diluted EPS with min/median/max and current percentile."""
    return calc_tools.pe_history(ticker, years=years, as_of=as_of)


@server.tool(annotations=READ_ONLY)
def valuation_multiples(price: str, shares_outstanding: str, valuation_date: str, financial_period: str,
                        evidence_refs: list[str], ttm_eps: str | None = None, ttm_revenue: str | None = None,
                        common_equity: str | None = None, ttm_operating_cash_flow: str | None = None,
                        ttm_capex: str | None = None, debt: str | None = None, cash: str | None = None,
                        preferred_stock: str | None = None, noncontrolling_interest: str | None = None,
                        ttm_ebitda: str | None = None, forward_eps: str | None = None,
                        forward_period: str | None = None, forward_basis: str | None = None) -> dict:
    """Market cap, trailing P/E, P/S, P/B, FCF yield, EV, EV/EBITDA and optional forward P/E.
    EV needs debt, cash, preferred_stock and noncontrolling_interest (pass '0' only if verified zero).
    forward_period: FY1|FY2|NTM; forward_basis: GAAP|ADJUSTED."""
    return calc_tools.valuation_multiples(
        price, shares_outstanding, valuation_date, financial_period, evidence_refs, ttm_eps=ttm_eps,
        ttm_revenue=ttm_revenue, common_equity=common_equity, ttm_operating_cash_flow=ttm_operating_cash_flow,
        ttm_capex=ttm_capex, debt=debt, cash=cash, preferred_stock=preferred_stock,
        noncontrolling_interest=noncontrolling_interest, ttm_ebitda=ttm_ebitda, forward_eps=forward_eps,
        forward_period=forward_period, forward_basis=forward_basis)


@server.tool(annotations=READ_ONLY)
def financial_ratios(ttm_net_income: str, ending_equity: str, ending_assets: str, current_assets: str,
                     current_liabilities: str, cash_and_equivalents: str, marketable_securities: str,
                     net_receivables: str, restricted_cash: str, interest_bearing_debt: str, ttm_ebit: str,
                     ttm_operating_cash_flow: str, ttm_sbc: str, ttm_revenue: str, evidence_refs: list[str],
                     beginning_equity: str | None = None, beginning_assets: str | None = None,
                     ttm_interest_expense: str | None = None) -> dict:
    """Liquidity, leverage, return and cash-quality ratios (current/quick/cash ratio, ROE, ROA, D/E,
    interest coverage, OCF/net income, SBC/revenue). No thresholds or scores."""
    return calc_tools.financial_ratios(
        ttm_net_income, ending_equity, ending_assets, current_assets, current_liabilities, cash_and_equivalents,
        marketable_securities, net_receivables, restricted_cash, interest_bearing_debt, ttm_ebit,
        ttm_operating_cash_flow, ttm_sbc, ttm_revenue, evidence_refs, beginning_equity=beginning_equity,
        beginning_assets=beginning_assets, ttm_interest_expense=ttm_interest_expense)


@server.tool(annotations=READ_ONLY)
def percent_change(earlier_value: str, later_value: str, earlier_period: str, later_period: str, unit: str,
                   evidence_refs: list[str]) -> dict:
    """Absolute and percentage change between two comparable periods (same unit)."""
    return calc_tools.percent_change(earlier_value, later_value, earlier_period, later_period, unit, evidence_refs)


@server.tool(annotations=READ_ONLY)
def ratio(numerator: str, denominator: str, numerator_period: str, denominator_period: str,
          numerator_unit: str, denominator_unit: str, evidence_refs: list[str]) -> dict:
    """numerator / denominator; rejects mismatched periods or units."""
    return calc_tools.ratio(numerator, denominator, numerator_period, denominator_period,
                            numerator_unit, denominator_unit, evidence_refs)


@server.tool(annotations=READ_ONLY)
def scenario_value(revenue: str, operating_margin: str, valuation_multiple: str, net_cash: str, shares: str,
                   period: str, assumptions: list[str], evidence_refs: list[str]) -> dict:
    """Per-share value for one explicit scenario: ((revenue x operating margin) x EV/EBIT multiple
    + net cash) / shares. State every assumption in `assumptions`."""
    return calc_tools.scenario_value(revenue, operating_margin, valuation_multiple, net_cash, shares, period,
                                     assumptions, evidence_refs)


@server.tool(annotations=LOCAL_WRITE)
def save_decision(ticker: str, action: str, confidence: str, horizon: str, thesis: str,
                  key_evidence: list[str], risks: list[str], invalidation: list[str], data_as_of: str,
                  report_markdown: str, price_at_decision: str | None = None,
                  no_trade_reason: str | None = None, host: str | None = None, model: str | None = None) -> dict:
    """Persist the final decision and full report to the private decision log (append-only).
    action: BUY|ADD|HOLD|REDUCE|EXIT|NO_TRADE; confidence: low|medium|high."""
    return decision_log.save_decision(
        ticker, action, confidence, horizon, thesis, key_evidence, risks, invalidation, data_as_of,
        report_markdown, price_at_decision=price_at_decision, no_trade_reason=no_trade_reason,
        host=host, model=model)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
