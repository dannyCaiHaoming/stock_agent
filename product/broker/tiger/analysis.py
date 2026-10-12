"""Deterministic v1 trade-history analysis over a frozen private ledger view."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from statistics import mean, median
from typing import Any, Iterable
from uuid import uuid4

from .contracts import finalize_contract


FORMULA_VERSION = "trade-history-formula/1.0.0"
SUPPORTED_ASSETS = frozenset({"COMMON_STOCK", "ETF", "LISTED_OPTION"})
EXPECTED_SYNC_CATEGORIES = frozenset({
    "ORDERS_EXECUTIONS_CHARGES", "ASSET_POINTS", "FUND_DETAILS", "FUNDING_HISTORY",
})
ECONOMIC_TYPES = frozenset({
    "ORDER", "EXECUTION", "CHARGE", "DIVIDEND", "TAX", "CORPORATE_ACTION",
    "CASH_ACTIVITY", "FUNDING_ACTIVITY", "FOREX_ACTIVITY", "POSITION", "ACCOUNT_SNAPSHOT",
})


class TradeAnalysisError(ValueError):
    """Stable deterministic analysis error."""


@dataclass(frozen=True)
class FrozenAnalysisInput:
    account_ref: str
    cutoff: str
    ledger_hash: str
    coverage_status: str
    activities: tuple[dict[str, Any], ...]
    asset_points: tuple[dict[str, Any], ...]
    sync_windows: tuple[dict[str, Any], ...]
    included_count: int
    excluded_count: int
    unknown_count: int


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _included_activity(item: dict[str, Any]) -> tuple[bool, bool]:
    if item.get("activity_type") not in ECONOMIC_TYPES:
        return False, True
    currency = item.get("currency")
    market = item.get("market")
    activity_type = item.get("activity_type")
    if activity_type == "ACCOUNT_SNAPSHOT":
        return True, False
    if currency in (None, "UNKNOWN"):
        return False, True
    if currency != "USD":
        return False, False
    if activity_type == "FUNDING_ACTIVITY":
        return True, False
    if market in (None, "UNKNOWN"):
        return False, True
    if market != "US":
        return False, False
    asset_type = item.get("asset_type")
    if activity_type in {"ORDER", "EXECUTION", "CHARGE", "POSITION"} and asset_type not in SUPPORTED_ASSETS:
        return False, asset_type in (None, "UNKNOWN")
    return True, False


def assemble_analysis_input(ledger: object, *, account_ref: str, cutoff: str) -> FrozenAnalysisInput:
    activities = ledger.read_current_activities(account_ref=account_ref, cutoff=cutoff)
    asset_points = [item for item in ledger.read_current_asset_points(account_ref=account_ref, cutoff=cutoff) if item.get("currency") == "USD"]
    observed_windows = ledger.read_sync_windows(account_ref=account_ref, cutoff=cutoff)
    latest_windows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in observed_windows:
        key = (
            str(item.get("category") or ""),
            str(item.get("window_start") or ""),
            str(item.get("window_end") or ""),
        )
        # The ledger returns receipts oldest-first, including row insertion order
        # for equal timestamps. A successful retry therefore supersedes the prior
        # failed observation for coverage, while both receipts stay auditable.
        latest_windows[key] = item
    windows = sorted(latest_windows.values(), key=lambda item: (
        str(item.get("window_start") or ""),
        str(item.get("category") or ""),
        str(item.get("window_end") or ""),
    ))
    observed_categories = {str(item.get("category") or "") for item in windows}
    coverage = (
        "API_COMPLETE_WITHIN_DECLARED_WINDOW"
        if EXPECTED_SYNC_CATEGORIES.issubset(observed_categories)
        and all(item.get("status") == "COMPLETE" for item in windows)
        else "PARTIAL"
    )
    included: list[dict[str, Any]] = []
    excluded_count = unknown_count = 0
    for item in activities:
        accepted, unknown = _included_activity(item)
        if accepted:
            included.append(deepcopy(item))
        elif unknown:
            unknown_count += 1
        else:
            excluded_count += 1
    return FrozenAnalysisInput(
        account_ref=account_ref,
        cutoff=cutoff,
        ledger_hash=ledger.ledger_hash(account_ref=account_ref, cutoff=cutoff),
        coverage_status=coverage,
        activities=tuple(included),
        asset_points=tuple(deepcopy(asset_points)),
        sync_windows=tuple(deepcopy(windows)),
        included_count=len(included),
        excluded_count=excluded_count,
        unknown_count=unknown_count,
    )


def _iso_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _metric(metric_id: str, value: float | int | None, unit: str, *, status: str | None = None, reason: str | None = None) -> dict[str, Any]:
    resolved_status = status or ("AVAILABLE" if value is not None else "UNAVAILABLE")
    return {
        "metric_id": metric_id,
        "value": round(float(value), 10) if isinstance(value, float) else value,
        "unit": unit,
        "status": resolved_status,
        "reason": reason,
    }


def _fees_complete(value: FrozenAnalysisInput) -> bool:
    return _category_complete(value, "ORDERS_EXECUTIONS_CHARGES")


def _category_complete(value: FrozenAnalysisInput, category: str) -> bool:
    relevant = [item for item in value.sync_windows if item.get("category") == category]
    return bool(relevant) and all(item.get("status") == "COMPLETE" for item in relevant)


def _latest_snapshot_positions(value: FrozenAnalysisInput) -> list[dict[str, Any]]:
    snapshots = [item for item in value.activities if item.get("activity_type") == "ACCOUNT_SNAPSHOT"]
    positions = [item for item in value.activities if item.get("activity_type") == "POSITION"]
    if not snapshots:
        return positions
    latest = max(
        snapshots,
        key=lambda item: (
            str(item.get("as_of") or ""),
            str(item.get("retrieved_at") or ""),
            str(item.get("batch_id") or ""),
        ),
    )
    batch_id = latest.get("batch_id")
    return [item for item in positions if item.get("batch_id") == batch_id]


def _fifo_episodes(value: FrozenAnalysisInput) -> tuple[list[dict[str, Any]], list[str]]:
    executions = [item for item in value.activities if item.get("activity_type") == "EXECUTION"]
    executions.sort(key=lambda item: (item.get("occurred_at_utc") or item.get("as_of") or "", item.get("provider_id") or ""))
    charge_by_order: dict[str, float] = defaultdict(float)
    for item in value.activities:
        if item.get("activity_type") == "CHARGE" and item.get("order_id"):
            amount = _finite(item.get("amount"))
            if amount is not None:
                charge_by_order[str(item["order_id"])] += abs(amount)
    execution_qty_by_order: dict[str, float] = defaultdict(float)
    for item in executions:
        quantity = _finite(item.get("quantity"))
        if item.get("order_id") and quantity is not None:
            execution_qty_by_order[str(item["order_id"])] += abs(quantity)
    fees_known = _fees_complete(value)
    lots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    episodes: list[dict[str, Any]] = []
    limitations: list[str] = []
    for execution in executions:
        key = execution.get("instrument_key")
        quantity = _finite(execution.get("quantity"))
        price = _finite(execution.get("price"))
        direction = str(execution.get("direction") or "").upper()
        timestamp = execution.get("occurred_at_utc") or execution.get("as_of")
        if not key or quantity is None or quantity <= 0 or price is None or direction not in {"BUY", "SELL"} or not timestamp:
            limitations.append("存在身份、方向、数量、价格或时间不完整的成交，未强行闭合 episode。")
            continue
        multiplier = _finite(execution.get("contract_multiplier")) or 1.0
        order_id = str(execution.get("order_id") or "")
        total_qty = execution_qty_by_order.get(order_id, 0)
        execution_fee = charge_by_order.get(order_id, 0) * quantity / total_qty if fees_known and total_qty else 0.0
        fee_per_unit = execution_fee / quantity if fees_known else None
        remaining = quantity
        closing_side = "SHORT" if direction == "BUY" else "LONG"
        opening_side = "LONG" if direction == "BUY" else "SHORT"
        open_lots = lots[str(key)]
        while remaining > 1e-12 and open_lots and open_lots[0]["side"] == closing_side:
            lot = open_lots[0]
            closed = min(remaining, lot["remaining"])
            gross = ((price - lot["price"]) if closing_side == "LONG" else (lot["price"] - price)) * closed * multiplier
            fees = None
            if fees_known:
                fees = closed * ((lot["fee_per_unit"] or 0) + (fee_per_unit or 0))
            net = gross - fees if fees is not None else None
            opened_seconds = _iso_seconds(lot["time"])
            closed_seconds = _iso_seconds(str(timestamp))
            holding = max(0.0, closed_seconds - opened_seconds) if opened_seconds is not None and closed_seconds is not None else None
            source_refs = [lot["record_id"], execution["_ledger"]["record_id"]]
            episodes.append({
                "episode_id": f"episode:{len(episodes) + 1}",
                "instrument_key": str(key),
                "display_symbol": str(execution.get("display_symbol") or lot["symbol"]),
                "opened_at": lot["time"],
                "closed_at": str(timestamp),
                "quantity": closed,
                "gross_pnl": round(gross, 10),
                "fees": round(fees, 10) if fees is not None else None,
                "net_pnl": round(net, 10) if net is not None else None,
                "holding_seconds": holding,
                "status": "CLOSED",
                "source_refs": source_refs,
            })
            lot["remaining"] -= closed
            remaining -= closed
            if lot["remaining"] <= 1e-12:
                open_lots.pop(0)
        if remaining > 1e-12:
            open_lots.append({
                "side": opening_side,
                "remaining": remaining,
                "price": price,
                "time": str(timestamp),
                "fee_per_unit": fee_per_unit,
                "record_id": execution["_ledger"]["record_id"],
                "symbol": execution.get("display_symbol") or "UNKNOWN",
            })
    for key, open_lots in lots.items():
        for lot in open_lots:
            episodes.append({
                "episode_id": f"episode:{len(episodes) + 1}",
                "instrument_key": key,
                "display_symbol": str(lot["symbol"]),
                "opened_at": lot["time"],
                "closed_at": None,
                "quantity": lot["remaining"] if lot["side"] == "LONG" else -lot["remaining"],
                "gross_pnl": None,
                "fees": None,
                "net_pnl": None,
                "holding_seconds": None,
                "status": "OPEN",
                "source_refs": [lot["record_id"]],
            })
    if not fees_known:
        limitations.append("费用覆盖未完成，净盈亏、胜率、盈亏比、Profit Factor 与期望不可用。")
    if any(item.get("activity_type") == "CORPORATE_ACTION" for item in value.activities):
        limitations.append("存在公司行动记录；系统不会以事件文本强行重建或闭合交易批次。")
    return episodes, sorted(set(limitations))


def _return_series(asset_points: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    points = sorted(asset_points, key=lambda item: (item.get("business_date") or "", item.get("as_of") or ""))
    current_by_date: dict[str, dict[str, Any]] = {}
    for item in points:
        current_by_date[str(item["business_date"])] = item
    ordered = [current_by_date[key] for key in sorted(current_by_date)]
    if len(ordered) < 2:
        return [], [], "至少需要两个完整 USD 资产点。"
    series = []
    cumulative = 1.0
    peak = 1.0
    drawdowns = []
    for previous, current in zip(ordered, ordered[1:]):
        start = _finite(previous.get("asset_value"))
        end = _finite(current.get("asset_value"))
        flow = _finite(current.get("net_external_flow"))
        if start is None or end is None or flow is None or start == 0:
            return [], [], "资产值、外部现金流缺失或期初资产为零。"
        daily = (end - flow) / start - 1
        cumulative *= 1 + daily
        peak = max(peak, cumulative)
        drawdown = cumulative / peak - 1 if peak else None
        series.append({
            "date": current["business_date"], "asset_value": end, "net_external_flow": flow,
            "daily_return": round(daily, 10), "cumulative_return": round(cumulative - 1, 10),
        })
        drawdowns.append({"date": current["business_date"], "drawdown": round(drawdown, 10) if drawdown is not None else None})
    return series, drawdowns, None


def _chart(chart_id: str, title: str, kind: str, unit: str, status: str, start: str, end: str, points: list[dict[str, Any]], limitations: list[str]) -> dict[str, Any]:
    return {
        "chart_id": chart_id, "title": title, "kind": kind, "unit": unit,
        "status": status, "window_start": start, "window_end": end,
        "formula_version": FORMULA_VERSION, "points": points, "limitations": limitations,
    }


def analyze_history(
    ledger: object,
    *,
    account_ref: str,
    cutoff: str,
    retrieved_at: str,
) -> dict[str, Any]:
    frozen = assemble_analysis_input(ledger, account_ref=account_ref, cutoff=cutoff)
    episodes, limitations = _fifo_episodes(frozen)
    closed = [item for item in episodes if item["status"] == "CLOSED"]
    net_known = [item for item in closed if item["net_pnl"] is not None]
    profits = [float(item["net_pnl"]) for item in net_known if float(item["net_pnl"]) > 0]
    losses = [float(item["net_pnl"]) for item in net_known if float(item["net_pnl"]) < 0]
    holdings = [float(item["holding_seconds"]) for item in closed if item["holding_seconds"] is not None]
    fees_complete = _fees_complete(frozen)
    fund_details_complete = _category_complete(frozen, "FUND_DETAILS")
    charges = [_finite(item.get("amount")) for item in frozen.activities if item.get("activity_type") == "CHARGE"]
    fees = sum(abs(item) for item in charges if item is not None) if fees_complete and all(item is not None for item in charges) else None
    dividends = (
        sum(_finite(item.get("amount")) or 0 for item in frozen.activities if item.get("activity_type") == "DIVIDEND")
        if fund_details_complete else None
    )
    taxes = (
        sum(abs(_finite(item.get("amount")) or 0) for item in frozen.activities if item.get("activity_type") == "TAX")
        if fund_details_complete else None
    )
    realized = sum(float(item["net_pnl"]) for item in net_known) if len(net_known) == len(closed) else None
    positions = _latest_snapshot_positions(frozen)
    unrealized_values = [
        _finite((item.get("position") or {}).get("unrealized_pnl")) for item in positions
    ]
    unrealized = sum(item for item in unrealized_values if item is not None) if unrealized_values and all(item is not None for item in unrealized_values) else None
    broker_reported_values = [
        _finite(item.get("reported_realized_pnl"))
        for item in frozen.activities if item.get("activity_type") == "EXECUTION"
    ]
    broker_reported_realized = (
        sum(item for item in broker_reported_values if item is not None)
        if broker_reported_values and all(item is not None for item in broker_reported_values)
        else None
    )

    returns, drawdowns, return_reason = _return_series(frozen.asset_points)
    cumulative_return = returns[-1]["cumulative_return"] if returns else None
    max_drawdown = min((item["drawdown"] for item in drawdowns if item["drawdown"] is not None), default=None)
    metrics = [
        _metric("cumulative_return", cumulative_return, "RATIO", reason=return_reason),
        _metric("max_drawdown", max_drawdown, "RATIO", reason=return_reason),
        _metric("realized_pnl", realized, "USD", reason=None if realized is not None else "费用或已闭合 episode 不完整。"),
        _metric("broker_reported_realized_pnl", broker_reported_realized, "USD", reason=None if broker_reported_realized is not None else "券商逐笔成交未完整提供 reported realized P&L。"),
        _metric("unrealized_pnl", unrealized, "USD", reason=None if unrealized is not None else "缺少完整当前持仓未实现盈亏。"),
        _metric("fees", fees, "USD", reason=None if fees is not None else "订单费用覆盖未完成。"),
        _metric("dividends", dividends, "USD", reason=None if dividends is not None else "资金明细覆盖未完成。"),
        _metric("taxes", taxes, "USD", reason=None if taxes is not None else "资金明细覆盖未完成。"),
        _metric("closed_episode_count", len(closed), "COUNT"),
        _metric("win_rate", len(profits) / len(net_known) if net_known else None, "RATIO", reason=None if net_known else "没有净结果已知的已闭合 episode。"),
        _metric("payoff_ratio", mean(profits) / abs(mean(losses)) if profits and losses and mean(losses) != 0 else None, "RATIO", reason=None if profits and losses else "需要至少一个盈利和一个亏损 episode。"),
        _metric("profit_factor", sum(profits) / abs(sum(losses)) if profits and losses and sum(losses) != 0 else None, "RATIO", reason=None if profits and losses else "需要至少一个盈利和一个亏损 episode。"),
        _metric("expectancy", mean(float(item["net_pnl"]) for item in net_known) if net_known else None, "USD_PER_EPISODE", reason=None if net_known else "没有净结果已知的已闭合 episode。"),
        _metric("average_holding_seconds", mean(holdings) if holdings else None, "SECONDS", reason=None if holdings else "没有可计算持有期的已闭合 episode。"),
        _metric("median_holding_seconds", median(holdings) if holdings else None, "SECONDS", reason=None if holdings else "没有可计算持有期的已闭合 episode。"),
    ]
    orders = [item for item in frozen.activities if item.get("activity_type") == "ORDER"]
    metrics.append(_metric("order_count", len(orders), "COUNT"))
    for status in ("FILLED", "PARTIALLY_FILLED", "CANCELLED", "INVALID"):
        metrics.append(_metric(f"order_status_{status.lower()}", sum(str(item.get("status") or "").upper() == status for item in orders), "COUNT"))

    security: dict[str, dict[str, Any]] = {}
    for item in episodes:
        key = item["instrument_key"]
        row = security.setdefault(key, {"instrument_key": key, "display_symbol": item["display_symbol"], "closed_episode_count": 0, "open_episode_count": 0, "gross_pnl": 0.0, "fees": 0.0, "net_pnl": 0.0, "net_pnl_status": "AVAILABLE"})
        if item["status"] == "CLOSED":
            row["closed_episode_count"] += 1
            row["gross_pnl"] += item["gross_pnl"] or 0
            if item["fees"] is None or item["net_pnl"] is None:
                row["net_pnl_status"] = "UNAVAILABLE"
            else:
                row["fees"] += item["fees"]
                row["net_pnl"] += item["net_pnl"]
        else:
            row["open_episode_count"] += 1
    by_security = sorted(security.values(), key=lambda item: (item["display_symbol"], item["instrument_key"]))
    for item in by_security:
        for field in ("gross_pnl", "fees", "net_pnl"):
            item[field] = round(item[field], 10)
        item["system_review_net_pnl"] = item["net_pnl"] if item["net_pnl_status"] == "AVAILABLE" else None
        reported = [
            _finite(activity.get("reported_realized_pnl"))
            for activity in frozen.activities
            if activity.get("activity_type") == "EXECUTION" and activity.get("instrument_key") == item["instrument_key"]
        ]
        item["broker_reported_realized_pnl"] = (
            round(sum(value for value in reported if value is not None), 10)
            if reported and all(value is not None for value in reported)
            else None
        )

    monthly_returns: dict[str, float] = defaultdict(lambda: 1.0)
    for item in returns:
        monthly_returns[item["date"][:7]] *= 1 + item["daily_return"]
    monthly_pnl: dict[str, float] = defaultdict(float)
    for item in net_known:
        monthly_pnl[item["closed_at"][:7]] += float(item["net_pnl"])
    months = sorted(set(monthly_returns) | set(monthly_pnl))
    by_month = [
        {
            "month": month,
            "cash_flow_adjusted_return": round(monthly_returns[month] - 1, 10) if month in monthly_returns else None,
            "net_realized_pnl": round(monthly_pnl[month], 10) if month in monthly_pnl else None,
            "return_unit": "RATIO",
            "pnl_unit": "USD",
        }
        for month in months
    ]

    start_candidates = [item.get("business_date") for item in frozen.asset_points] + [item.get("market_date") for item in frozen.activities]
    valid_dates = sorted(str(item) for item in start_candidates if item)
    window_start = valid_dates[0] if valid_dates else cutoff[:10]
    window_end = valid_dates[-1] if valid_dates else cutoff[:10]
    limited = "LIMITED" if frozen.coverage_status == "PARTIAL" else "AVAILABLE"
    return_status = limited if returns else "UNAVAILABLE"
    timeline_points = [
        {
            "date": item.get("market_date"), "time": item.get("occurred_at_utc"),
            "category": item.get("activity_type"), "symbol": item.get("display_symbol"),
            "direction": item.get("direction"), "status": item.get("status"),
        }
        for item in frozen.activities if item.get("occurred_at_utc")
    ]
    charts = [
        _chart("equity-flow-return", "资产、净入金与现金流调整收益", "LINE", "USD_AND_RATIO", return_status, window_start, window_end, returns, [return_reason] if return_reason else []),
        _chart("drawdown", "回撤", "LINE", "RATIO", return_status, window_start, window_end, drawdowns, [return_reason] if return_reason else []),
        _chart("monthly-return", "月度现金流调整收益率", "HEATMAP", "RATIO", return_status, window_start, window_end, [{"month": item["month"], "value": item["cash_flow_adjusted_return"]} for item in by_month], ["不得与月度净盈亏混用。"]),
        _chart("security-pnl-fees", "证券净盈亏与费用", "BAR", "USD", limited if by_security else "UNAVAILABLE", window_start, window_end, by_security, [] if by_security else ["没有可用交易 episode。"]),
        _chart("holding-period", "持有期与净盈亏", "SCATTER", "SECONDS_AND_USD", limited if closed else "UNAVAILABLE", window_start, window_end, [{"episode_id": item["episode_id"], "symbol": item["display_symbol"], "holding_seconds": item["holding_seconds"], "net_pnl": item["net_pnl"]} for item in closed], [] if closed else ["没有已闭合 episode。"]),
        _chart("activity-timeline", "交易活动时间线", "TIMELINE", "EVENT", limited if timeline_points else "UNAVAILABLE", window_start, window_end, timeline_points, [] if timeline_points else ["没有带时间的活动记录。"]),
    ]
    if frozen.excluded_count:
        limitations.append(f"已排除 {frozen.excluded_count} 条非 US/非 USD 活动。")
    if frozen.unknown_count:
        limitations.append(f"有 {frozen.unknown_count} 条身份、市场或币种未知记录未聚合。")
    if frozen.coverage_status == "PARTIAL":
        limitations.append("同步覆盖存在 gap 或缺少完整窗口，结果为 LIMITED。")

    analysis = finalize_contract({
        "schema_version": "trade-history-analysis/1.0.0",
        "analysis_id": f"trade-analysis:{uuid4().hex}",
        "account_ref": account_ref,
        "source_id": "private-broker-ledger:trade-history-analysis",
        "as_of": cutoff,
        "retrieved_at": retrieved_at,
        "ledger_hash": frozen.ledger_hash,
        "formula_version": FORMULA_VERSION,
        "window_start": window_start,
        "window_end": window_end,
        "coverage_status": frozen.coverage_status,
        "included_count": frozen.included_count,
        "excluded_count": frozen.excluded_count,
        "unknown_count": frozen.unknown_count,
        "metrics": metrics,
        "episodes": episodes,
        "by_security": by_security,
        "by_month": by_month,
        "charts": charts,
        "limitations": sorted(set(limitations)),
        "advisory_only": True,
        "tax_report": False,
        "broker_statement": False,
        "backtest": False,
    })
    ledger.save_analysis(analysis)
    return analysis
