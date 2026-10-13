"""Deterministic calculation tools. No judgement, scoring or action output.

Thin wrappers over product.deterministic. Inputs are numbers (as strings or
numbers) plus `evidence_refs` naming the source_id / accession behind them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from product.deterministic import market_analysis, valuation
from product.deterministic.equity_valuation import (
    calculate_financial_ratios, derive_current_valuation, derive_forward_pe, midrank_percentile,
)
from product.mcp import data_tools
from product.mcp.provenance import iso_utc

SOURCE_ID = "stock-data:calculation"


class CalcToolError(ValueError):
    pass


def _tidy(value: Any) -> Any:
    """Round long decimal strings to 6 places to keep tool output compact."""
    if isinstance(value, dict):
        return {k: _tidy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_tidy(v) for v in value]
    if isinstance(value, str) and len(value) > 12:
        try:
            number = Decimal(value)
        except Exception:
            return value
        if number.is_finite() and "." in value:
            text = format(round(number, 6), "f")
            return text.rstrip("0").rstrip(".")
    return value


def _now() -> str:
    return iso_utc(datetime.now(UTC))


def _refs(evidence_refs: list[str] | None) -> list[str]:
    refs = sorted({str(r) for r in (evidence_refs or []) if str(r).strip()})
    if not refs:
        raise CalcToolError("EVIDENCE_REFS_REQUIRED: cite the source_id or accession behind the inputs")
    return refs


def _artifact(result) -> dict[str, Any]:
    return _tidy({"formula": result.formula, "inputs": result.inputs, "outputs": result.outputs,
            "units": result.units, "periods": result.periods, "calculation_id": result.artifact_id})


def valuation_multiples(price: str, shares_outstanding: str, valuation_date: str, financial_period: str,
                        evidence_refs: list[str], ttm_eps: str | None = None, ttm_revenue: str | None = None,
                        common_equity: str | None = None, ttm_operating_cash_flow: str | None = None,
                        ttm_capex: str | None = None, debt: str | None = None, cash: str | None = None,
                        preferred_stock: str | None = None, noncontrolling_interest: str | None = None,
                        ttm_ebitda: str | None = None, forward_eps: str | None = None,
                        forward_period: str | None = None, forward_basis: str | None = None) -> dict[str, Any]:
    refs = _refs(evidence_refs)
    at = iso_utc(f"{valuation_date}T21:00:00Z") if len(valuation_date) == 10 else iso_utc(valuation_date)
    retrieved = _now()
    metrics = derive_current_valuation(
        price=price, shares_outstanding=shares_outstanding, ttm_eps=ttm_eps, ttm_revenue=ttm_revenue,
        common_equity=common_equity, ttm_operating_cash_flow=ttm_operating_cash_flow, ttm_capex=ttm_capex,
        debt=debt, cash=cash, preferred_stock=preferred_stock, noncontrolling_interest=noncontrolling_interest,
        ttm_ebitda=ttm_ebitda, security_id="input", valuation_at=at, financial_period=financial_period,
        currency="USD", source_id=SOURCE_ID, retrieved_at=retrieved, evidence_refs=refs)
    if forward_eps is not None:
        metrics.append(derive_forward_pe(price=price, forecast_eps=forward_eps, forecast_period=forward_period,
                                         accounting_basis=forward_basis, source_id=SOURCE_ID, valuation_at=at,
                                         retrieved_at=retrieved, evidence_refs=refs, currency="USD"))
    return _tidy({
        "market_cap": format(Decimal(str(price)) * Decimal(str(shares_outstanding)), "f"),
        "metrics": [{"name": m["name"], "value": m["value"], "status": m["status"], "reason": m["reason"],
                     "formula": m["formula"]} for m in metrics],
        "evidence_refs": refs,
        "notes": "Missing EV components are never treated as zero; status explains unavailable metrics.",
    })


def financial_ratios(ttm_net_income: str, ending_equity: str, ending_assets: str, current_assets: str,
                     current_liabilities: str, cash_and_equivalents: str, marketable_securities: str,
                     net_receivables: str, restricted_cash: str, interest_bearing_debt: str, ttm_ebit: str,
                     ttm_operating_cash_flow: str, ttm_sbc: str, ttm_revenue: str, evidence_refs: list[str],
                     beginning_equity: str | None = None, beginning_assets: str | None = None,
                     ttm_interest_expense: str | None = None) -> dict[str, Any]:
    refs = _refs(evidence_refs)
    ratios = calculate_financial_ratios(
        ttm_net_income=ttm_net_income, beginning_equity=beginning_equity, ending_equity=ending_equity,
        beginning_assets=beginning_assets, ending_assets=ending_assets, current_assets=current_assets,
        current_liabilities=current_liabilities, cash_and_equivalents=cash_and_equivalents,
        marketable_securities=marketable_securities, net_receivables=net_receivables,
        restricted_cash=restricted_cash, interest_bearing_debt=interest_bearing_debt, ttm_ebit=ttm_ebit,
        ttm_interest_expense=ttm_interest_expense, ttm_operating_cash_flow=ttm_operating_cash_flow,
        ttm_sbc=ttm_sbc, ttm_revenue=ttm_revenue, evidence_refs=refs)
    return _tidy({"ratios": ratios, "evidence_refs": refs})


def percent_change(earlier_value: str, later_value: str, earlier_period: str, later_period: str, unit: str,
                   evidence_refs: list[str]) -> dict[str, Any]:
    refs = tuple(_refs(evidence_refs))
    return _artifact(valuation.comparable_period_change(
        earlier_value=earlier_value, later_value=later_value, earlier_period=earlier_period,
        later_period=later_period, unit=unit, as_of=_now(), assumption_ids=(), evidence_fact_ids=refs))


def ratio(numerator: str, denominator: str, numerator_period: str, denominator_period: str,
          numerator_unit: str, denominator_unit: str, evidence_refs: list[str]) -> dict[str, Any]:
    refs = tuple(_refs(evidence_refs))
    return _artifact(valuation.financial_ratio(
        numerator=numerator, denominator=denominator, numerator_period=numerator_period,
        denominator_period=denominator_period, numerator_unit=numerator_unit,
        denominator_unit=denominator_unit, as_of=_now(), assumption_ids=(), evidence_fact_ids=refs))


def scenario_value(revenue: str, operating_margin: str, valuation_multiple: str, net_cash: str, shares: str,
                   period: str, assumptions: list[str], evidence_refs: list[str]) -> dict[str, Any]:
    """One explicit scenario: ((revenue * margin) * EV/EBIT multiple + net cash) / shares."""
    if not assumptions:
        raise CalcToolError("ASSUMPTIONS_REQUIRED: state each scenario assumption in words")
    refs = tuple(_refs(evidence_refs))
    result = valuation.operating_scenario_value_per_share(
        revenue=revenue, operating_margin=operating_margin, valuation_multiple=valuation_multiple,
        net_cash=net_cash, shares=shares, period=period, currency="USD", as_of=_now(),
        assumption_ids=tuple(f"assumption:{i}" for i in range(1, len(assumptions) + 1)), evidence_fact_ids=refs)
    return {**_artifact(result), "assumptions": assumptions}


def _rows(prices: dict) -> list[dict]:
    index = prices["columns"].index
    return [{"date": r[index("date")], "close": r[index("close")], "adjusted_close": r[index("adj_close")],
             "volume": r[index("volume")], "evidence_ids": [prices["provenance"]["source_id"]]}
            for r in prices["rows"] if r[index("close")] is not None]


def _sma(values: list[Decimal], n: int) -> Decimal | None:
    return sum(values[-n:], Decimal(0)) / n if len(values) >= n else None


def technical_stats(ticker: str, benchmark: str = "SPY", as_of: str | None = None) -> dict[str, Any]:
    end = date.fromisoformat(as_of[:10]) if as_of else None
    start = ((end or date.today()) - timedelta(days=420)).isoformat()
    security = data_tools.get_price_history(ticker, start=start, as_of=as_of)
    bench = data_tools.get_price_history(benchmark, start=start, as_of=as_of)
    rows = _rows(security)
    if security["last_row_incomplete_session"]:
        rows = rows[:-1]
    stats = market_analysis.calculate_technical_statistics(
        rows, _rows(bench), security_id=security["ticker"], benchmark_id=bench["ticker"],
        as_of=iso_utc(f"{rows[-1]['date']}T21:00:00Z"))
    adjusted = [Decimal(r["adjusted_close"] or r["close"]) for r in rows]
    last = adjusted[-1]
    moving = {}
    for n in (50, 200):
        avg = _sma(adjusted, n)
        moving[f"sma_{n}"] = None if avg is None else {"value": format(round(avg, 4), "f"),
                                                       "price_vs_sma": format(round(last / avg - 1, 4), "f")}
    return {"ticker": security["ticker"], "benchmark": bench["ticker"], "last_date": rows[-1]["date"],
            "statistics": _tidy(stats), "moving_averages_adjusted_close": moving,
            "provenance": {"prices": security["provenance"], "benchmark": bench["provenance"]},
            "notes": "Returns use adjusted close; volatility is annualized from daily returns."}


def pe_history(ticker: str, years: int = 5, as_of: str | None = None) -> dict[str, Any]:
    """Monthly trailing P/E using fiscal-year diluted EPS (latest restated values, split-consistent)."""
    years = max(2, min(int(years), 10))
    statements = data_tools.get_financial_statements(ticker, period="annual", limit=years + 1, as_of=as_of)
    eps_row = statements["lines"].get("eps_diluted")
    if not eps_row:
        raise CalcToolError("ANNUAL_DILUTED_EPS_UNAVAILABLE")
    fiscal = [(p["end"], Decimal(v)) for p, v in zip(statements["periods"], eps_row) if v is not None]
    end = date.fromisoformat(as_of[:10]) if as_of else date.today()
    prices = data_tools.get_price_history(ticker, start=(end - timedelta(days=365 * years)).isoformat(),
                                          interval="1mo", as_of=as_of)
    points = []
    for row in prices["rows"]:
        day, close = row[0], row[4]
        # Use EPS of the latest fiscal year ending at least ~60 days before the month (10-K filing lag proxy).
        known = [eps for fy_end, eps in fiscal
                 if date.fromisoformat(fy_end) + timedelta(days=60) <= date.fromisoformat(day)]
        if not known or close is None:
            continue
        eps = known[-1]
        points.append([day, close, format(eps, "f"),
                       format(round(Decimal(close) / eps, 2), "f") if eps > 0 else None])
    values = [Decimal(p[3]) for p in points if p[3] is not None]
    # "current" is the latest month only; a loss-making latest fiscal year means P/E is not applicable.
    current = Decimal(points[-1][3]) if points and points[-1][3] is not None else None
    return {
        "ticker": statements["ticker"], "columns": ["month", "close", "fy_diluted_eps", "trailing_pe"],
        "rows": points,
        "summary": None if not values else {
            "current": format(current, "f") if current is not None else None,
            "current_status": "AVAILABLE" if current is not None else "NOT_APPLICABLE_NON_POSITIVE_EPS",
            "median": format(sorted(values)[len(values) // 2], "f"),
            "min": format(min(values), "f"), "max": format(max(values), "f"), "points": len(values),
            "current_percentile_0_100": format(round(midrank_percentile(current, values[:-1]), 1), "f") if current is not None and len(values) > 1 else None},
        "provenance": {"prices": prices["provenance"], "eps": statements["provenance"]},
        "limitations": ["EPS is fiscal-year diluted EPS (latest restated), not quarterly TTM and not as originally reported.",
                        "A 60-day filing lag is assumed between fiscal year end and EPS availability.",
                        "A historical percentile describes the past range only; it is not a valuation conclusion."],
    }


def forward_returns(ticker: str, dates: list[str], horizons_days: list[int] | None = None,
                    benchmark: str = "SPY", as_of: str | None = None) -> dict[str, Any]:
    """Historical check: total return (adjusted close) after each date over N trading days, vs a benchmark.

    Each date is moved to the first trading day on or after it. Horizons that end after the cutoff are null.
    """
    horizons = sorted({int(h) for h in (horizons_days or [63, 126, 252]) if 1 <= int(h) <= 1260})
    days = sorted({date.fromisoformat(str(d)[:10]) for d in dates})[:40]
    if not days or not horizons:
        raise CalcToolError("DATES_AND_HORIZONS_REQUIRED")
    start = (days[0] - timedelta(days=7)).isoformat()
    series = {}
    provenance = {}
    for symbol in (ticker, benchmark):
        prices = data_tools.get_price_history(symbol, start=start, interval="1d", as_of=as_of, max_rows=20000)
        rows = _rows(prices)
        series[symbol] = [(r["date"], Decimal(r["adjusted_close"] or r["close"])) for r in rows]
        provenance[symbol] = prices["provenance"]
    bench_index = {d: i for i, (d, _) in enumerate(series[benchmark])}
    table, excess_by_h = [], {h: [] for h in horizons}
    stock = series[ticker]
    for day in days:
        index = next((i for i, (d, _) in enumerate(stock) if d >= day.isoformat()), None)
        if index is None:
            continue
        base_date, base = stock[index]
        b_index = bench_index.get(base_date)
        row = {"date": day.isoformat(), "base_date": base_date, "base_price": format(round(base, 4), "f")}
        for h in horizons:
            if index + h >= len(stock) or b_index is None or b_index + h >= len(series[benchmark]):
                row[f"ret_{h}d_pct"] = row[f"excess_{h}d_pct"] = None
                continue
            ret = stock[index + h][1] / base - 1
            bret = series[benchmark][b_index + h][1] / series[benchmark][b_index][1] - 1
            row[f"ret_{h}d_pct"] = format(round(ret * 100, 2), "f")
            row[f"excess_{h}d_pct"] = format(round((ret - bret) * 100, 2), "f")
            excess_by_h[h].append(ret - bret)
        table.append(row)
    summary = {}
    for h, values in excess_by_h.items():
        if values:
            ordered = sorted(values)
            summary[f"{h}d"] = {"n": len(values),
                                "median_excess_pct": format(round(ordered[len(ordered) // 2] * 100, 2), "f"),
                                "hit_rate_excess_positive": format(round(Decimal(sum(v > 0 for v in values)) / len(values), 2), "f")}
    return {"ticker": data_tools._ticker(ticker), "benchmark": data_tools._ticker(benchmark), "rows": table,
            "summary": summary, "provenance": provenance,
            "limitations": ["Small samples: a few historical instances are anecdotes, not statistics.",
                            "Overlapping windows are not independent; regime and company changes limit comparability.",
                            "Trading-day horizons: 63 ~ 3 months, 126 ~ 6 months, 252 ~ 1 year."]}

