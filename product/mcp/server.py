"""stock-data MCP server: read-only US equity data and deterministic calculations.

Run with: python -m product.mcp.server  (stdio transport)
Environment: STOCK_AGENT_DATA_DIR (default <repo>/.local/data), STOCK_AGENT_CACHE_DIR (default <repo>/.local/cache),
SEC_USER_AGENT ("app contact@email").
"""

from __future__ import annotations

from datetime import UTC, datetime
import functools
import inspect

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations

from product.mcp import calc_tools, congress_tools, context_tools, data_tools, decision_log, ownership_tools, settings

server = MCPServer(
    name="stock-data",
    instructions=(
        "Read-only US equity research data and deterministic financial calculations. "
        "Every result carries provenance (source_id, as_of, retrieved_at). Use calculation tools for "
        "all arithmetic. `as_of` limits data to what was published by that date. No trading capability."
    ),
)

def explain_errors(fn):
    """Surface the real failure reason to the model (the SDK masks non-ToolError exceptions)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001 - every failure must be explained to the caller
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc
    return wrapper


def point_in_time(fn):
    """Replay mode: default as_of to the replay date and refuse anything later."""
    signature = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        replay = settings.replay_as_of()
        if replay:
            bound = signature.bind_partial(*args, **kwargs)
            requested = bound.arguments.get("as_of")
            if not requested:
                bound.arguments["as_of"] = replay
            elif str(requested)[:10] > replay:
                raise ToolError(f"REPLAY_AS_OF_EXCEEDED: this is a replay as of {replay}; later data is not allowed")
            return fn(*bound.args, **bound.kwargs)
        return fn(*args, **kwargs)
    return wrapper


def current_only(fn):
    """Replay mode: refuse tools that only return today's data (it would leak the future)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        replay = settings.replay_as_of()
        if replay:
            raise ToolError(f"NOT_POINT_IN_TIME: replay as of {replay}; this tool only returns current data. "
                            "Record it as a data gap (SOURCE_UNSUPPORTED) and continue.")
        return fn(*args, **kwargs)
    return wrapper


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
LOCAL_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
@explain_errors
def ping() -> dict[str, str]:
    """Health check: confirms the stock-data server is reachable."""
    return {"status": "ok", "server": "stock-data", "time": datetime.now(UTC).isoformat()}


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_price_history(ticker: str, start: str | None = None, end: str | None = None,
                      interval: str = "1d", as_of: str | None = None) -> dict:
    """Daily/weekly/monthly OHLCV, adjusted close, dividends and splits (Yahoo).
    Defaults to the last 365 days. Dates are YYYY-MM-DD. Max 800 rows; use 1wk/1mo for long ranges."""
    return data_tools.get_price_history(ticker, start=start, end=end, interval=interval, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@current_only
def get_analyst_snapshot(ticker: str) -> dict:
    """Current company profile, key statistics, analyst consensus (targets, ratings), EPS/revenue
    estimates with 7-90 day estimate trend and revisions, and next earnings date (Yahoo, current-only)."""
    return data_tools.get_analyst_snapshot(ticker)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_financial_statements(ticker: str, period: str = "annual", limit: int = 5,
                             as_of: str | None = None) -> dict:
    """Standardized income statement, cash flow and balance sheet lines from SEC XBRL (as reported).
    period: annual | quarterly (quarterly derives discrete quarters from YTD filings and has a TTM block
    with eps_diluted_approx). Includes derived ebitda and free_cash_flow, lease liabilities, preferred stock
    and noncontrolling interest. Cells are strings in USD unless noted; null means not reported (not zero)."""
    return data_tools.get_financial_statements(ticker, period=period, limit=limit, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_sec_concept(ticker: str, tag: str, taxonomy: str = "us-gaap", limit: int = 12,
                    as_of: str | None = None) -> dict:
    """All periods of one XBRL concept (e.g. tag='OperatingLeaseLiability'), latest version per period,
    with accession and publication time. Use for lines missing from get_financial_statements."""
    return data_tools.get_sec_concept(ticker, tag, taxonomy=taxonomy, limit=limit, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def list_filings(ticker: str, forms: list[str] | None = None, limit: int = 20,
                 as_of: str | None = None) -> dict:
    """Recent SEC filings (accession, form, report date, acceptance time). forms e.g. ['10-K','10-Q','8-K']."""
    return data_tools.list_filings(ticker, forms=forms, limit=limit, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def list_filing_documents(ticker: str, accession: str, as_of: str | None = None) -> dict:
    """All documents in one SEC filing: primary document and exhibits (e.g. 8-K EX-99.1 earnings press
    release). Read one with get_filing_text(accession=..., document=<file name>)."""
    return data_tools.list_filing_documents(ticker, accession, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_filing_text(ticker: str, accession: str | None = None, form: str = "10-K",
                    section: str = "management_discussion", offset: int = 0, max_chars: int = 12000,
                    query: str | None = None, document: str | None = None, match_offset: int = 0,
                    as_of: str | None = None) -> dict:
    """Text of a 10-K/10-Q/8-K or one of its exhibits.
    section: business | risk_factors | management_discussion | full_text. Without accession, uses the
    latest filing of `form`. `document` (with accession) reads an exhibit file from list_filing_documents.
    Page with offset/next_offset. `query` returns excerpts: exact phrase first, else passages containing
    all query words; total_matches and next_match_offset allow paging; cover/TOC hits are listed last.
    Search contract terms (convertible, preferred, covenant, lease) in section=full_text."""
    return data_tools.get_filing_text(ticker, accession=accession, form=form, section=section, offset=offset,
                                      max_chars=max_chars, query=query, document=document,
                                      match_offset=match_offset, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_macro_snapshot(as_of: str | None = None) -> dict:
    """US macro as of a date: 3M/2Y/10Y/30Y Treasury yields with 10Y-2Y spread (latest and 20/60/250 sessions
    earlier), CPI and core CPI YoY, unemployment, payroll changes (only months already released), the latest FOMC
    statement text, and upcoming BLS releases (current dates only). Works for historical dates."""
    return context_tools.get_macro_snapshot(as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_market_context(as_of: str | None = None) -> dict:
    """Market state: SPY, 11 sector ETFs, TLT, UUP, GLD, USO, HYG and VIX with last close and 5/20/60-session
    % change, plus recent market headlines. ETF values are proxies."""
    return context_tools.get_market_context(as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@current_only
def get_peer_candidates(ticker: str) -> dict:
    """Unverified peer candidates (Yahoo related symbols; popularity-based, often noisy)."""
    return context_tools.get_peer_candidates(ticker)


@server.tool(annotations=READ_ONLY)
@explain_errors
@current_only
def get_peer_snapshot(tickers: list[str]) -> dict:
    """Side-by-side provider-reported statistics for up to 6 tickers: sector, industry, market cap, P/E,
    forward P/E, EV/revenue, EV/EBITDA, P/B, growth, margins, ROE, debt/equity, 52-week change."""
    return context_tools.get_peer_snapshot(tickers)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def technical_stats(ticker: str, benchmark: str = "SPY", as_of: str | None = None) -> dict:
    """20/60/252-session total and relative return, annualized volatility, max drawdown, volume ratio,
    window high/low, and 50/200-day moving averages, versus a benchmark ETF."""
    return calc_tools.technical_stats(ticker, benchmark=benchmark, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def pe_history(ticker: str, years: int = 5, as_of: str | None = None) -> dict:
    """Monthly trailing P/E from fiscal-year diluted EPS with min/median/max and current percentile."""
    return calc_tools.pe_history(ticker, years=years, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def forward_returns(ticker: str, dates: list[str], horizons_days: list[int] | None = None,
                    benchmark: str = "SPY", as_of: str | None = None) -> dict:
    """Historical validation: what happened after given dates (e.g. past instances of a similar setup)?
    Returns total and excess return vs benchmark over N trading days (default 63/126/252) per date,
    with median excess and hit rate. Use to test whether a signal was reliable in the past."""
    return calc_tools.forward_returns(ticker, dates, horizons_days=horizons_days, benchmark=benchmark, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
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
@explain_errors
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
@explain_errors
def percent_change(earlier_value: str, later_value: str, earlier_period: str, later_period: str, unit: str,
                   evidence_refs: list[str]) -> dict:
    """Absolute and percentage change between two comparable periods (same unit)."""
    return calc_tools.percent_change(earlier_value, later_value, earlier_period, later_period, unit, evidence_refs)


@server.tool(annotations=READ_ONLY)
@explain_errors
def ratio(numerator: str, denominator: str, numerator_period: str, denominator_period: str,
          numerator_unit: str, denominator_unit: str, evidence_refs: list[str]) -> dict:
    """numerator / denominator. Both period labels must be the same string (e.g. "FQ4 FY26") and units must match."""
    return calc_tools.ratio(numerator, denominator, numerator_period, denominator_period,
                            numerator_unit, denominator_unit, evidence_refs)


@server.tool(annotations=READ_ONLY)
@explain_errors
def scenario_value(revenue: str, operating_margin: str, valuation_multiple: str, net_cash: str, shares: str,
                   period: str, assumptions: list[str], evidence_refs: list[str]) -> dict:
    """Per-share value for one explicit scenario: ((revenue x operating margin) x EV/EBIT multiple
    + net cash) / shares. State every assumption in `assumptions`."""
    return calc_tools.scenario_value(revenue, operating_margin, valuation_multiple, net_cash, shares, period,
                                     assumptions, evidence_refs)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_insider_transactions(ticker: str, days: int = 180, as_of: str | None = None) -> dict:
    """Insider trades from SEC Form 4 filed in the `days` before as_of: open-market purchases and sales (who,
    role, shares, price, value, 10b5-1 plan flag) with totals; grants, option exercises and tax withholding are
    only counted. Point in time by filing acceptance time."""
    return ownership_tools.get_insider_transactions(ticker, days=days, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_fund_holdings(ticker: str, as_of: str | None = None) -> dict:
    """Positions of ~18 well-known funds (Berkshire, Bridgewater, Renaissance, Pershing Square, Tiger, Coatue,
    Viking, Third Point, Duquesne, Soros, Scion, Elliott, D1, Icahn...) in this stock from their latest two
    13F-HR reports filed before as_of: shares, quarter-over-quarter change, new/exited, put/call. A fixed sample of
    managers, 45-day reporting lag, long positions only. First call per quarter can take ~2 minutes."""
    return ownership_tools.get_fund_holdings(ticker, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_congress_trades(ticker: str, days: int = 365, as_of: str | None = None) -> dict:
    """U.S. House members' trades in this stock from Periodic Transaction Reports filed in the `days` before as_of:
    member, owner (self/spouse/joint/child), purchase/sale, trade date, amount range. Point in time by filing date
    (trades may be reported up to 45 days late). Senate not covered."""
    return congress_tools.get_congress_trades(ticker, days=days, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_member_track_record(member: str, horizon_days: int = 252, as_of: str | None = None) -> dict:
    """Past record of one House member's disclosed trades (name substring, e.g. 'Pelosi'): hit rate and median
    excess return vs SPY over `horizon_days` sessions after each filing date, for purchases and sales, using only
    trades whose horizon ended before as_of. Use it to judge whether a member's trades in get_congress_trades
    deserve weight."""
    return congress_tools.get_member_track_record(member, horizon_days=horizon_days, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
@point_in_time
def get_news_history(ticker: str, days: int = 30, query: str | None = None, as_of: str | None = None) -> dict:
    """English news headlines mentioning the company (GDELT) within `days` (max 90) before as_of, newest first,
    with domain and URL. Headlines only; name matching is noisy. Optional `query` replaces the default finance
    keywords, e.g. '(lawsuit OR investigation)'. Works for historical dates."""
    return context_tools.get_news_history(ticker, days=days, query=query, as_of=as_of)


@server.tool(annotations=READ_ONLY)
@explain_errors
def probability_weighted_value(values: list[str], probabilities: list[str], price: str,
                               labels: list[str] | None = None) -> dict:
    """Probability-weighted value of scenario values (e.g. from scenario_value) with subjective probabilities
    summing to 1 (or 100): weighted per-share value, expected return versus price, probability of a loss."""
    return calc_tools.probability_weighted_value(values, probabilities, price, labels)


@server.tool(annotations=READ_ONLY)
@explain_errors
def implied_assumption(price: str, shares: str, net_cash: str, revenue: str, period: str,
                       evidence_refs: list[str], operating_margin: str | None = None,
                       valuation_multiple: str | None = None) -> dict:
    """Inverse of scenario_value. Give a price (current or a candidate BUY price) and exactly one of
    operating_margin or valuation_multiple; returns the EV/EBIT multiple or operating margin that
    price implies: EV = price x shares - net cash."""
    return calc_tools.implied_assumption(price, shares, net_cash, revenue, period, evidence_refs,
                                         operating_margin, valuation_multiple)


@server.tool(annotations=LOCAL_WRITE)
@explain_errors
def save_decision(ticker: str, action: str, confidence: str, horizon: str, thesis: str,
                  key_evidence: list[str], risks: list[str], invalidation: list[str], data_as_of: str,
                  report_markdown: str, price_at_decision: str | None = None,
                  no_trade_reason: str | None = None, host: str | None = None, model: str | None = None,
                  forecasts: list[dict] | None = None, expected_return_pct: str | None = None,
                  variant: str | None = None) -> dict:
    """Persist the final decision and full report to the private decision log (append-only).
    action: BUY|ADD|HOLD|REDUCE|EXIT|NO_TRADE; confidence: low|medium|high.
    price_at_decision: plain number only, e.g. "541.15" (required unless NO_TRADE).
    data_as_of: date of the data used, YYYY-MM-DD (put source details in the report, not here).
    report_markdown must use the investment-decision template "## " headings; missing sections are rejected.
    forecasts (required, also for NO_TRADE): list of {target, direction, probability, basis} for
      revenue_growth (accelerate|decelerate|flat: YoY growth in the 2nd quarter after the latest reported one
        vs YoY growth in the latest reported quarter, ±1pp),
      operating_margin (expand|contract|flat: GAAP margin in that quarter vs the same quarter a year earlier, ±0.5pp),
      relative_return_126d (outperform|underperform: next 126 sessions vs the sector ETF),
      optional guidance (raise|cut|maintain|not_applicable). probability = chance the stated direction happens.
    expected_return_pct: probability-weighted expected return from the scenarios, e.g. "12.5".
    variant: experiment label if the task names one."""
    return decision_log.save_decision(
        ticker, action, confidence, horizon, thesis, key_evidence, risks, invalidation, data_as_of,
        report_markdown, price_at_decision=price_at_decision, no_trade_reason=no_trade_reason,
        host=host, model=model, forecasts=forecasts, expected_return_pct=expected_return_pct, variant=variant)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
