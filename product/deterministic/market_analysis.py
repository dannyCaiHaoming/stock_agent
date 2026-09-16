"""量价研究的确定性统计与图表数据准备，不生成投资判断。"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Mapping, Sequence

from product.runtime.hashing import canonical_hash


TECHNICAL_CALCULATION_VERSION = "technical-calculation/1.0.0"
MARKET_STATE_CALCULATION_VERSION = "market-state-calculation/1.0.0"


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"TECHNICAL_NUMBER_INVALID:{field}") from exc
    if not number.is_finite():
        raise ValueError(f"TECHNICAL_NUMBER_INVALID:{field}")
    return number


def _normalize_rows(rows: Sequence[Mapping[str, Any]], *, label: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError(f"TECHNICAL_ROW_INVALID:{label}")
        day = raw.get("date")
        if not isinstance(day, str):
            raise ValueError(f"TECHNICAL_DATE_INVALID:{label}")
        date.fromisoformat(day)
        if day in seen:
            raise ValueError(f"TECHNICAL_DUPLICATE_DATE:{label}")
        seen.add(day)
        close = _decimal(raw.get("close"), f"{label}.close")
        adjusted_raw = raw.get("adjusted_close")
        adjusted = None if adjusted_raw is None else _decimal(adjusted_raw, f"{label}.adjusted_close")
        volume_raw = raw.get("volume")
        volume = None if volume_raw is None else _decimal(volume_raw, f"{label}.volume")
        if close <= 0 or (adjusted is not None and adjusted <= 0) or (volume is not None and volume < 0):
            raise ValueError(f"TECHNICAL_VALUE_OUT_OF_RANGE:{label}")
        evidence_ids = raw.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or any(
            not isinstance(item, str) or not item for item in evidence_ids
        ):
            raise ValueError(f"TECHNICAL_EVIDENCE_IDS_INVALID:{label}")
        normalized.append({
            "date": day,
            "close": close,
            "adjusted_close": adjusted,
            "volume": volume,
            "stock_split": _decimal(raw.get("stock_split", 0), f"{label}.stock_split"),
            "evidence_ids": list(evidence_ids),
        })
    normalized.sort(key=lambda item: item["date"])
    return normalized


def _returns(values: Sequence[Decimal]) -> list[Decimal]:
    return [values[index] / values[index - 1] - Decimal(1) for index in range(1, len(values))]


def _annualized_volatility(values: Sequence[Decimal]) -> Decimal:
    daily = _returns(values)
    if len(daily) < 2:
        raise ValueError("TECHNICAL_VOLATILITY_HISTORY_INSUFFICIENT")
    mean = sum(daily, Decimal(0)) / Decimal(len(daily))
    variance = sum(((item - mean) ** 2 for item in daily), Decimal(0)) / Decimal(len(daily))
    with localcontext() as context:
        context.prec = 28
        return variance.sqrt() * Decimal(252).sqrt()


def _max_drawdown(values: Sequence[Decimal]) -> Decimal:
    peak = values[0]
    worst = Decimal(0)
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - Decimal(1))
    return worst


def calculate_technical_statistics(
    security_rows: Sequence[Mapping[str, Any]],
    benchmark_rows: Sequence[Mapping[str, Any]],
    *,
    security_id: str,
    benchmark_id: str,
    as_of: str,
    windows: Sequence[int] = (20, 60, 252),
) -> dict[str, Any]:
    """计算多窗口收益、相对表现、波动、回撤和成交量统计。"""

    if not security_id or not benchmark_id or security_id == benchmark_id:
        raise ValueError("TECHNICAL_IDENTITY_INVALID")
    if not windows or any(type(item) is not int or item < 2 for item in windows):
        raise ValueError("TECHNICAL_WINDOWS_INVALID")
    if len(windows) != len(set(windows)):
        raise ValueError("TECHNICAL_WINDOWS_DUPLICATE")
    security = _normalize_rows(security_rows, label="security")
    benchmark = _normalize_rows(benchmark_rows, label="benchmark")
    benchmark_by_date = {item["date"]: item for item in benchmark}
    aligned = [(row, benchmark_by_date[row["date"]]) for row in security if row["date"] in benchmark_by_date]
    results: list[dict[str, Any]] = []
    used_evidence: set[str] = set()
    for window in windows:
        needed = window + 1
        if len(aligned) < needed:
            results.append({
                "window_sessions": window,
                "status": "INSUFFICIENT_HISTORY",
                "available_aligned_sessions": len(aligned),
                "metrics": None,
                "reason": f"需要至少 {needed} 个对齐交易日。",
            })
            continue
        sample = aligned[-needed:]
        security_sample = [item[0] for item in sample]
        benchmark_sample = [item[1] for item in sample]
        if any(item["adjusted_close"] is None for item in security_sample + benchmark_sample):
            split_present = any(item["stock_split"] > 0 for item in security_sample)
            results.append({
                "window_sessions": window,
                "status": "PRICE_DISCONTINUITY" if split_present else "ADJUSTED_CLOSE_MISSING",
                "available_aligned_sessions": len(aligned),
                "metrics": None,
                "reason": "复权收盘价不完整，不能可靠计算该窗口历史收益。",
            })
            continue
        security_prices = [item["adjusted_close"] for item in security_sample]
        benchmark_prices = [item["adjusted_close"] for item in benchmark_sample]
        assert all(item is not None for item in security_prices + benchmark_prices)
        security_values = [item for item in security_prices if item is not None]
        benchmark_values = [item for item in benchmark_prices if item is not None]
        security_return = security_values[-1] / security_values[0] - Decimal(1)
        benchmark_return = benchmark_values[-1] / benchmark_values[0] - Decimal(1)
        volumes = [item["volume"] for item in security_sample if item["volume"] is not None]
        prior_volumes = [item["volume"] for item in security_sample[:-1] if item["volume"] is not None]
        volume_average = (
            sum(volumes, Decimal(0)) / Decimal(len(volumes)) if volumes else None
        )
        latest_volume_ratio = (
            security_sample[-1]["volume"]
            / (sum(prior_volumes, Decimal(0)) / Decimal(len(prior_volumes)))
            if prior_volumes
            and security_sample[-1]["volume"] is not None
            and sum(prior_volumes, Decimal(0)) > 0
            else None
        )
        for row in security_sample + benchmark_sample:
            used_evidence.update(row["evidence_ids"])
        metrics = {
            "security_total_return": str(security_return),
            "benchmark_total_return": str(benchmark_return),
            "relative_return": str(security_return - benchmark_return),
            "annualized_volatility": str(_annualized_volatility(security_values)),
            "maximum_drawdown": str(_max_drawdown(security_values)),
            "average_volume": str(volume_average) if volume_average is not None else None,
            "latest_volume_ratio": str(latest_volume_ratio) if latest_volume_ratio is not None else None,
            "window_high": str(max(item["close"] for item in security_sample)),
            "window_low": str(min(item["close"] for item in security_sample)),
        }
        results.append({
            "window_sessions": window,
            "status": "COMPLETE",
            "available_aligned_sessions": len(aligned),
            "metrics": metrics,
            "reason": None,
        })
    artifact: dict[str, Any] = {
        "schema_version": TECHNICAL_CALCULATION_VERSION,
        "artifact_id": f"technical:{security_id}:{as_of}",
        "security_id": security_id,
        "benchmark_id": benchmark_id,
        "as_of": as_of,
        "price_basis": "provider_adjusted_close_for_return/provider_close_for_range",
        "volume_basis": "provider_daily_share_volume",
        "windows": results,
        "evidence_fact_ids": sorted(used_evidence),
    }
    artifact["artifact_hash"] = canonical_hash(artifact)
    return artifact


def calculate_market_state_statistics(
    market_rows: Sequence[Mapping[str, Any]],
    *,
    market_id: str,
    as_of: str,
    windows: Sequence[int] = (20, 60, 252),
) -> dict[str, Any]:
    """计算广泛市场基准的多窗口收益、波动、回撤和量价状态。"""

    if not market_id:
        raise ValueError("MARKET_STATE_IDENTITY_INVALID")
    if not windows or any(type(item) is not int or item < 2 for item in windows):
        raise ValueError("MARKET_STATE_WINDOWS_INVALID")
    if len(windows) != len(set(windows)):
        raise ValueError("MARKET_STATE_WINDOWS_DUPLICATE")
    market = _normalize_rows(market_rows, label="market")
    results: list[dict[str, Any]] = []
    used_evidence: set[str] = set()
    for window in windows:
        needed = window + 1
        if len(market) < needed:
            results.append({
                "window_sessions": window,
                "status": "INSUFFICIENT_HISTORY",
                "available_sessions": len(market),
                "metrics": None,
                "reason": f"需要至少 {needed} 个交易日。",
            })
            continue
        sample = market[-needed:]
        if any(item["adjusted_close"] is None for item in sample):
            split_present = any(item["stock_split"] > 0 for item in sample)
            results.append({
                "window_sessions": window,
                "status": "PRICE_DISCONTINUITY" if split_present else "ADJUSTED_CLOSE_MISSING",
                "available_sessions": len(market),
                "metrics": None,
                "reason": "复权收盘价不完整，不能可靠计算该窗口市场状态。",
            })
            continue
        prices = [item["adjusted_close"] for item in sample]
        assert all(item is not None for item in prices)
        values = [item for item in prices if item is not None]
        volumes = [item["volume"] for item in sample if item["volume"] is not None]
        prior_volumes = [item["volume"] for item in sample[:-1] if item["volume"] is not None]
        average_volume = (
            sum(volumes, Decimal(0)) / Decimal(len(volumes)) if volumes else None
        )
        latest_volume_ratio = (
            sample[-1]["volume"]
            / (sum(prior_volumes, Decimal(0)) / Decimal(len(prior_volumes)))
            if prior_volumes
            and sample[-1]["volume"] is not None
            and sum(prior_volumes, Decimal(0)) > 0
            else None
        )
        for row in sample:
            used_evidence.update(row["evidence_ids"])
        results.append({
            "window_sessions": window,
            "status": "COMPLETE",
            "available_sessions": len(market),
            "metrics": {
                "market_total_return": str(values[-1] / values[0] - Decimal(1)),
                "annualized_volatility": str(_annualized_volatility(values)),
                "maximum_drawdown": str(_max_drawdown(values)),
                "average_volume": str(average_volume) if average_volume is not None else None,
                "latest_volume_ratio": str(latest_volume_ratio) if latest_volume_ratio is not None else None,
                "window_high": str(max(item["close"] for item in sample)),
                "window_low": str(min(item["close"] for item in sample)),
            },
            "reason": None,
        })
    artifact: dict[str, Any] = {
        "schema_version": MARKET_STATE_CALCULATION_VERSION,
        "artifact_id": f"market-state:{market_id}:{as_of}",
        "market_id": market_id,
        "as_of": as_of,
        "price_basis": "provider_adjusted_close_for_return/provider_close_for_range",
        "volume_basis": "provider_daily_share_volume",
        "windows": results,
        "evidence_fact_ids": sorted(used_evidence),
    }
    artifact["artifact_hash"] = canonical_hash(artifact)
    return artifact


def verify_technical_calculation(value: Mapping[str, Any]) -> None:
    expected = canonical_hash({key: copy.deepcopy(item) for key, item in value.items() if key != "artifact_hash"})
    if value.get("schema_version") != TECHNICAL_CALCULATION_VERSION:
        raise ValueError("TECHNICAL_CALCULATION_VERSION_INVALID")
    if value.get("artifact_hash") != expected:
        raise ValueError("TECHNICAL_CALCULATION_HASH_MISMATCH")
    if not value.get("evidence_fact_ids"):
        completed = [item for item in value.get("windows", []) if item.get("status") == "COMPLETE"]
        if completed:
            raise ValueError("TECHNICAL_CALCULATION_LINEAGE_MISSING")


def verify_market_state_calculation(value: Mapping[str, Any]) -> None:
    expected = canonical_hash({key: copy.deepcopy(item) for key, item in value.items() if key != "artifact_hash"})
    if value.get("schema_version") != MARKET_STATE_CALCULATION_VERSION:
        raise ValueError("MARKET_STATE_CALCULATION_VERSION_INVALID")
    if value.get("artifact_hash") != expected:
        raise ValueError("MARKET_STATE_CALCULATION_HASH_MISMATCH")
    if not value.get("evidence_fact_ids"):
        completed = [item for item in value.get("windows", []) if item.get("status") == "COMPLETE"]
        if completed:
            raise ValueError("MARKET_STATE_CALCULATION_LINEAGE_MISSING")
