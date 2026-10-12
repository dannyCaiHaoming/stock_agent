"""从冻结研究附件生成可搬移的静态图文报告；图层不新增投资判断。"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from html import escape
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash, file_hash
from product.deterministic.equity_valuation import (
    validate_fundamental_supplement,
    validate_peer_comparison,
    validate_valuation_history,
)


VISUAL_VERSION = "research-visual-bundle/1.0.0"
MANIFEST_VERSION = "research-visual-manifest/1.0.0"
CHART_DATA_VERSION = "research-chart-data/1.0.0"
CORE_CHARTS = (
    "price_volume_sma", "relative_performance_drawdown",
    "financial_trends", "trailing_pe_history",
)
SUPPLEMENT_TITLES = {
    "guidance": "公司指引与版本对照",
    "earnings_quality": "盈利质量、SBC、回购与股数",
    "debt_liquidity": "债务期限与流动性",
    "operating_kpis": "经营 KPI 与集中度",
    "governance": "治理核实卡",
    "earnings_expectations": "实际与预期口径核对",
    "financial_ratios": "资本效率、流动性与杠杆比率",
}


class ResearchVisualError(ValueError):
    pass


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ResearchVisualError(f"VISUAL_NUMBER_INVALID:{name}") from exc
    if not result.is_finite():
        raise ResearchVisualError(f"VISUAL_NUMBER_INVALID:{name}")
    return result


def _numeric_series(rows: Sequence[Mapping[str, Any]], key: str) -> bool:
    """只在全部非空值都是有限数时绘制该字段。"""
    values = [row.get(key) for row in rows if isinstance(row, Mapping) and row.get(key) is not None]
    if not values or any(isinstance(value, bool) for value in values):
        return False
    try:
        return all(Decimal(str(value)).is_finite() for value in values)
    except (InvalidOperation, TypeError, ValueError):
        return False


def _hash_without(value: Mapping[str, Any], field: str) -> str:
    return canonical_hash({key: item for key, item in value.items() if key != field})


def _refs(rows: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    return sorted({str(ref) for row in rows for ref in row.get(key, []) if isinstance(ref, str) and ref})


def _sma(values: Sequence[Any | None], window: int) -> list[str | None]:
    result: list[str | None] = []
    active: list[Decimal] = []
    for value in values:
        if value is None:
            active = []
            result.append(None)
            continue
        active.append(_decimal(value, "sma"))
        if len(active) > window:
            active.pop(0)
        result.append(format(sum(active) / Decimal(window), "f") if len(active) == window else None)
    return result


def _chart(
    chart_id: str, title: str, *, unit: str, rows: Sequence[Mapping[str, Any]],
    status: str = "AVAILABLE", limitations: Sequence[str] = (),
    evidence_refs: Sequence[str] = (), calculation_refs: Sequence[str] = (),
    basis: str | None = None,
) -> dict[str, Any]:
    data = [deepcopy(dict(item)) for item in rows]
    value = {
        "chart_data_version": CHART_DATA_VERSION, "chart_id": chart_id,
        "title": title, "unit": unit, "status": status, "basis": basis,
        "window": {
            "start": data[0].get("date") or data[0].get("period") if data else None,
            "end": data[-1].get("date") or data[-1].get("period") if data else None,
            "points": len(data),
        },
        "limitations": list(limitations), "evidence_refs": sorted(set(evidence_refs)),
        "calculation_refs": sorted(set(calculation_refs)), "data": data,
    }
    value["data_hash"] = canonical_hash(data)
    return value


def _price_chart(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted((deepcopy(dict(row)) for row in rows), key=lambda row: str(row.get("date", "")))
    output = []
    closes: list[Any | None] = []
    refs: list[str] = []
    for row in ordered:
        required = ("date", "open", "high", "low", "close", "volume")
        if any(key not in row for key in required):
            raise ResearchVisualError("VISUAL_OHLCV_FIELD_MISSING")
        if row["close"] is None:
            closes.append(None)
            output.append({"date": row["date"], "gap": True})
            refs.extend(row.get("evidence_refs", []))
            continue
        values = {key: _decimal(row[key], key) for key in required[1:]}
        if values["volume"] < 0 or values["high"] < max(values["open"], values["close"], values["low"]):
            raise ResearchVisualError("VISUAL_OHLCV_VALUE_INVALID")
        if values["low"] > min(values["open"], values["close"], values["high"]):
            raise ResearchVisualError("VISUAL_OHLCV_VALUE_INVALID")
        close = format(values["close"], "f")
        closes.append(close)
        output.append({
            "date": row["date"], "open": format(values["open"], "f"),
            "high": format(values["high"], "f"), "low": format(values["low"], "f"),
            "close": close, "volume": format(values["volume"], "f"), "gap": False,
        })
        refs.extend(row.get("evidence_refs", []))
    for window in (20, 60, 200):
        values = _sma(closes, window)
        for index, value in enumerate(values):
            output[index][f"sma{window}"] = value
    limitations = []
    for window in (20, 60, 200):
        if not any(row.get(f"sma{window}") is not None for row in output):
            limitations.append(f"SMA{window}_INSUFFICIENT_HISTORY")
    if any(row["gap"] for row in output):
        limitations.append("EXPLICIT_PRICE_GAPS_NOT_CONNECTED")
    status = "AVAILABLE" if any(not row["gap"] for row in output) else "LIMITED"
    return _chart(
        "price_volume_sma", "日 K、成交量与均线", unit="price_and_volume",
        rows=output, status=status, limitations=limitations, evidence_refs=refs,
        basis="OHLC/SMA 使用拆股调整但不含分红复权的 Close；成交量为原始口径",
    )


def _relative_chart(
    security_rows: Sequence[Mapping[str, Any]], benchmark_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    left = {str(row["date"]): row for row in security_rows if row.get("adjusted_close") is not None}
    right = {str(row["date"]): row for row in benchmark_rows if row.get("adjusted_close") is not None}
    dates = sorted(set(left) & set(right))
    if len(dates) < 2:
        return _chart(
            "relative_performance_drawdown", "相对基准表现与回撤", unit="percent",
            rows=[], status="LIMITED", limitations=["COMMON_TRADING_DAYS_INSUFFICIENT"],
            evidence_refs=_refs(list(left.values()) + list(right.values()), "evidence_refs"),
            basis="Total-return adjusted close；只使用共同交易日",
        )
    security_base = _decimal(left[dates[0]]["adjusted_close"], "security_base")
    benchmark_base = _decimal(right[dates[0]]["adjusted_close"], "benchmark_base")
    if security_base <= 0 or benchmark_base <= 0:
        raise ResearchVisualError("VISUAL_RELATIVE_BASE_INVALID")
    security_peak = benchmark_peak = Decimal(0)
    output = []
    for current in dates:
        security_value = _decimal(left[current]["adjusted_close"], "security_close")
        benchmark_value = _decimal(right[current]["adjusted_close"], "benchmark_close")
        security_peak = max(security_peak, security_value)
        benchmark_peak = max(benchmark_peak, benchmark_value)
        output.append({
            "date": current,
            "security_index": format(security_value / security_base * 100, "f"),
            "benchmark_index": format(benchmark_value / benchmark_base * 100, "f"),
            "security_drawdown_pct": format((security_value / security_peak - 1) * 100, "f"),
            "benchmark_drawdown_pct": format((benchmark_value / benchmark_peak - 1) * 100, "f"),
        })
    refs = _refs([left[day] for day in dates] + [right[day] for day in dates], "evidence_refs")
    return _chart(
        "relative_performance_drawdown", "相对基准表现与回撤", unit="percent",
        rows=output, evidence_refs=refs,
        calculation_refs=["calc:relative-index", "calc:running-peak-drawdown"],
        basis="Total-return adjusted close；共同交易日；起点=100",
    )


def _financial_chart(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted((deepcopy(dict(row)) for row in rows), key=lambda row: str(row.get("period", "")))
    fields = ("revenue", "gross_margin_pct", "operating_margin_pct", "operating_cash_flow", "capex", "fcf", "diluted_shares")
    output, refs = [], []
    for row in ordered:
        if not row.get("period"):
            raise ResearchVisualError("VISUAL_FINANCIAL_PERIOD_MISSING")
        normalized = {"period": row["period"], "period_kind": row.get("period_kind"), "discontinuity": bool(row.get("discontinuity"))}
        for field in fields:
            normalized[field] = None if row.get(field) is None else format(_decimal(row[field], field), "f")
        output.append(normalized)
        refs.extend(row.get("evidence_refs", []))
    limitations = []
    if any(row["discontinuity"] for row in output):
        limitations.append("ACCOUNTING_OR_ENTITY_DISCONTINUITY_NOT_CONNECTED")
    if not output:
        limitations.append("FINANCIAL_PERIODS_UNAVAILABLE")
    return _chart(
        "financial_trends", "财务趋势分面", unit="mixed_separate_panels",
        rows=output, status="AVAILABLE" if output else "LIMITED",
        limitations=limitations, evidence_refs=refs,
        calculation_refs=["calc:fcf=operating_cash_flow-abs(capex)"],
        basis="收入/现金流、利润率和股数分面显示，不混合量纲",
    )


def _valuation_chart(history: Mapping[str, Any] | None) -> dict[str, Any]:
    if history is None:
        return _chart(
            "trailing_pe_history", "Trailing P/E 历史", unit="ratio", rows=[],
            status="LIMITED", limitations=["VALUATION_HISTORY_ATTACHMENT_MISSING"],
        )
    validate_valuation_history(history)
    points = [deepcopy(dict(item)) for item in history.get("points", [])]
    refs = _refs(points, "evidence_refs")
    limitations = list(history.get("data_gaps", []))
    if history.get("percentile_status") != "AVAILABLE":
        limitations.append("HISTORY_COVERAGE_BELOW_ACCEPTANCE_THRESHOLD")
    rows = [{
        "date": item.get("valuation_date"), "value": item.get("value"),
        "status": item.get("status"), "segment": item.get("segment_id"),
        "financial_period": item.get("financial_period"),
    } for item in points]
    return _chart(
        "trailing_pe_history", "Trailing P/E 历史", unit="ratio", rows=rows,
        status="AVAILABLE" if any(item.get("value") is not None for item in rows) else "LIMITED",
        limitations=limitations, evidence_refs=refs,
        calculation_refs=[str(ref) for ref in history.get("calculation_refs", [])],
        basis="按各观察点当时已公开财务版本事后重建；当前点从历史统计中去重",
    )


def _supplement_charts(
    supplement: Mapping[str, Any] | None, peer_comparison: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    if supplement is None:
        for name in ("guidance", "earnings_quality", "debt_liquidity", "operating_kpis", "governance", "earnings_expectations"):
            charts.append(_chart(f"supplement_{name}", name, unit="mixed", rows=[], status="LIMITED", limitations=["SUPPLEMENT_GROUP_MISSING"]))
    else:
        validate_fundamental_supplement(supplement)
        for name, group in supplement.get("groups", {}).items():
            items = group.get("items", [])
            charts.append(_chart(
                f"supplement_{name}", SUPPLEMENT_TITLES.get(name, name), unit="mixed", rows=items,
                status="AVAILABLE" if items else "LIMITED",
                limitations=[] if items else [str(group.get("reason") or "GROUP_HAS_NO_VERIFIED_ITEMS")],
                evidence_refs=_refs(items, "evidence_refs"),
                calculation_refs=[str(item["calculation_ref"]) for item in items if item.get("calculation_ref")],
            ))
    if peer_comparison is not None:
        validate_peer_comparison(peer_comparison)
    peers = [] if peer_comparison is None else [
        peer_comparison["target"], *list(peer_comparison.get("peers", []))
    ]
    peer_rows = []
    for peer in peers:
        for metric in peer.get("metrics", []):
            peer_rows.append({
                "security_id": peer.get("security_id"),
                "fiscal_period": peer.get("fiscal_period"),
                "currency": peer.get("currency"),
                "metric": metric.get("name"), "value": metric.get("value"),
                "metric_basis_id": metric.get("metric_basis_id"),
                "unit": metric.get("unit"), "status": metric.get("status"),
                "basis": metric.get("basis"),
                "source_id": metric.get("source_id"), "as_of": metric.get("as_of"),
                "retrieved_at": metric.get("retrieved_at"), "published_at": metric.get("published_at"),
                "period": metric.get("period"), "calculation_ref": metric.get("calculation_ref"),
                "comparability_notes": peer.get("comparability_notes", []),
                "evidence_refs": metric.get("evidence_refs", []),
            })
    charts.append(_chart(
        "peer_comparison_table", "有限同行比较", unit="mixed", rows=peer_rows,
        status="AVAILABLE" if peer_comparison is not None and peer_comparison.get("coverage_status") == "COMPLETE" else "LIMITED",
        limitations=[] if peer_comparison is not None and peer_comparison.get("coverage_status") == "COMPLETE" else ["PEER_CORE_MATRIX_INCOMPLETE"],
        evidence_refs=_refs([metric for peer in peers for metric in peer.get("metrics", [])], "evidence_refs"),
        basis="固定候选清单；逐字段可比性；无综合评分或排名",
    ))
    return charts


def build_visual_bundle(
    *, bundle_id: str, report_id: str, run_id: str, security_id: str,
    decision_cutoff: str, daily_prices: Sequence[Mapping[str, Any]],
    benchmark_prices: Sequence[Mapping[str, Any]], financial_periods: Sequence[Mapping[str, Any]],
    valuation_history: Mapping[str, Any] | None,
    fundamental_supplement: Mapping[str, Any] | None = None,
    peer_comparison: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    parse_timestamp(decision_cutoff)
    for artifact in (valuation_history, fundamental_supplement, peer_comparison):
        if artifact is None:
            continue
        artifact_security = artifact.get("security_id") or artifact.get("target_security_id")
        if artifact_security != security_id or artifact.get("decision_cutoff") != iso_utc(decision_cutoff):
            raise ResearchVisualError("VISUAL_ATTACHMENT_BINDING_MISMATCH")
    charts = [
        _price_chart(daily_prices), _relative_chart(daily_prices, benchmark_prices),
        _financial_chart(financial_periods), _valuation_chart(valuation_history),
        *_supplement_charts(fundamental_supplement, peer_comparison),
    ]
    value = {
        "schema_version": VISUAL_VERSION, "bundle_id": bundle_id,
        "report_id": report_id, "run_id": run_id, "security_id": security_id,
        "decision_cutoff": iso_utc(decision_cutoff), "charts": charts,
    }
    value["bundle_hash"] = canonical_hash(value)
    validate_visual_bundle(value)
    return value


def validate_visual_bundle(value: Mapping[str, Any]) -> None:
    expected = {"schema_version", "bundle_id", "report_id", "run_id", "security_id", "decision_cutoff", "charts", "bundle_hash"}
    if set(value) != expected or value.get("schema_version") != VISUAL_VERSION:
        raise ResearchVisualError("VISUAL_BUNDLE_SHAPE_INVALID")
    parse_timestamp(value["decision_cutoff"])
    charts = value.get("charts")
    if not isinstance(charts, list) or len({chart.get("chart_id") for chart in charts if isinstance(chart, Mapping)}) != len(charts):
        raise ResearchVisualError("VISUAL_CHART_SET_INVALID")
    if not set(CORE_CHARTS) <= {chart.get("chart_id") for chart in charts}:
        raise ResearchVisualError("VISUAL_CORE_CHART_MISSING")
    for chart in charts:
        if chart.get("chart_data_version") != CHART_DATA_VERSION or chart.get("status") not in {"AVAILABLE", "LIMITED"}:
            raise ResearchVisualError("VISUAL_CHART_INVALID")
        if chart.get("data_hash") != canonical_hash(chart.get("data")):
            raise ResearchVisualError("VISUAL_CHART_DATA_HASH_MISMATCH")
        if chart.get("window", {}).get("points") != len(chart.get("data", [])):
            raise ResearchVisualError("VISUAL_CHART_WINDOW_INVALID")
    if value.get("bundle_hash") != _hash_without(value, "bundle_hash"):
        raise ResearchVisualError("VISUAL_BUNDLE_HASH_MISMATCH")


def _segments(rows: Sequence[Mapping[str, Any]], key: str) -> list[list[Decimal]]:
    segments: list[list[Decimal]] = []
    active: list[Decimal] = []
    for row in rows:
        value = row.get(key)
        if value is None or row.get("gap") or row.get("discontinuity"):
            if active:
                segments.append(active)
                active = []
            continue
        active.append(_decimal(value, key))
    if active:
        segments.append(active)
    return segments


def _scaled_paths(
    rows: Sequence[Mapping[str, Any]], keys: Sequence[str], *,
    left: float, top: float, width: float, height: float,
) -> tuple[list[tuple[str, str]], Decimal, Decimal]:
    values = [_decimal(row[key], key) for row in rows for key in keys if row.get(key) is not None]
    low, high = (min(values), max(values)) if values else (Decimal(0), Decimal(1))
    if high == low:
        high = low + Decimal(1)
    denominator = max(1, len(rows) - 1)
    result: list[tuple[str, str]] = []
    for key in keys:
        active: list[str] = []
        for index, row in enumerate(rows):
            if row.get(key) is None or row.get("gap"):
                if active:
                    result.append((key, " ".join(active)))
                    active = []
                continue
            if row.get("discontinuity") and active:
                result.append((key, " ".join(active)))
                active = []
            x = left + index / denominator * width
            y = top + height - float((_decimal(row[key], key) - low) / (high - low)) * height
            active.append(f"{x:.2f},{y:.2f}")
        if active:
            result.append((key, " ".join(active)))
    return result, low, high


def _render_price_svg(chart: Mapping[str, Any]) -> str:
    rows = chart["data"]
    valid = [row for row in rows if not row.get("gap")]
    values = [_decimal(row[key], key) for row in valid for key in ("high", "low")]
    low, high = (min(values), max(values)) if values else (Decimal(0), Decimal(1))
    if high == low:
        high = low + Decimal(1)
    max_volume = max((_decimal(row["volume"], "volume") for row in valid), default=Decimal(1)) or Decimal(1)
    denominator = max(1, len(rows) - 1)
    candles, volumes = [], []
    for index, row in enumerate(rows):
        if row.get("gap"):
            continue
        x = 65 + index / denominator * 830
        high_y = 55 + float((high - _decimal(row["high"], "high")) / (high - low)) * 230
        low_y = 55 + float((high - _decimal(row["low"], "low")) / (high - low)) * 230
        open_y = 55 + float((high - _decimal(row["open"], "open")) / (high - low)) * 230
        close_y = 55 + float((high - _decimal(row["close"], "close")) / (high - low)) * 230
        color = "#dc2626" if _decimal(row["close"], "close") >= _decimal(row["open"], "open") else "#059669"
        candles.append(f'<line class="wick" x1="{x:.2f}" y1="{high_y:.2f}" x2="{x:.2f}" y2="{low_y:.2f}" stroke="{color}"/><rect class="candle" x="{x - 2.5:.2f}" y="{min(open_y, close_y):.2f}" width="5" height="{max(1, abs(close_y - open_y)):.2f}" fill="{color}"/>')
        volume_height = float(_decimal(row["volume"], "volume") / max_volume) * 60
        volumes.append(f'<rect class="volume" x="{x - 2.5:.2f}" y="{375 - volume_height:.2f}" width="5" height="{volume_height:.2f}" fill="#64748b" opacity=".55"/>')
    paths, _, _ = _scaled_paths(rows, ("sma20", "sma60", "sma200"), left=65, top=55, width=830, height=230)
    colors = {"sma20": "#2563eb", "sma60": "#d97706", "sma200": "#7c3aed"}
    polylines = [
        (f'<circle class="{key}" cx="{points.split(",")[0]}" cy="{points.split(",")[1]}" r="2.5" fill="{colors[key]}"/>' if " " not in points else
         f'<polyline class="{key}" points="{points}" fill="none" stroke="{colors[key]}" stroke-width="1.6"/>')
        for key, points in paths
    ]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="420" viewBox="0 0 960 420" role="img" aria-label="日 K、成交量与均线">'
        '<rect width="960" height="420" fill="white"/><text x="65" y="28" font-size="18">日 K、成交量与 SMA20/60/200</text>'
        '<line x1="65" y1="285" x2="895" y2="285" stroke="#94a3b8"/><line x1="65" y1="375" x2="895" y2="375" stroke="#94a3b8"/>'
        + "".join(candles + polylines + volumes)
        + '<text x="65" y="305" font-size="11">成交量</text><text x="580" y="28" font-size="11" fill="#2563eb">SMA20</text><text x="650" y="28" font-size="11" fill="#d97706">SMA60</text><text x="720" y="28" font-size="11" fill="#7c3aed">SMA200</text>'
        + f'<text x="65" y="412" font-size="10" fill="#6b7280">限制：{escape("；".join(chart["limitations"]) or "无")}</text></svg>\n'
    )


def _render_relative_svg(chart: Mapping[str, Any]) -> str:
    rows = chart["data"]
    upper, _, _ = _scaled_paths(rows, ("security_index", "benchmark_index"), left=65, top=50, width=830, height=145)
    lower, _, _ = _scaled_paths(rows, ("security_drawdown_pct", "benchmark_drawdown_pct"), left=65, top=235, width=830, height=105)
    colors = {"security_index": "#2563eb", "benchmark_index": "#d97706", "security_drawdown_pct": "#2563eb", "benchmark_drawdown_pct": "#d97706"}
    paths = [
        (f'<circle cx="{points.split(",")[0]}" cy="{points.split(",")[1]}" r="3" fill="{colors[key]}"/>' if " " not in points else
         f'<polyline points="{points}" fill="none" stroke="{colors[key]}" stroke-width="2"/>')
        for key, points in upper + lower
    ]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="420" viewBox="0 0 960 420" role="img" aria-label="相对表现与回撤">'
        '<rect width="960" height="420" fill="white"/><text x="65" y="28" font-size="18">相对基准表现与回撤</text>'
        '<text x="65" y="46" font-size="11">共同交易日起点=100</text><text x="65" y="228" font-size="11">回撤（%）</text>'
        + "".join(paths)
        + '<text x="650" y="28" font-size="11" fill="#2563eb">证券</text><text x="710" y="28" font-size="11" fill="#d97706">基准</text>'
        + f'<text x="65" y="412" font-size="10" fill="#6b7280">限制：{escape("；".join(chart["limitations"]) or "无")}</text></svg>\n'
    )


def _render_financial_svg(chart: Mapping[str, Any]) -> str:
    rows = chart["data"]
    panels = (
        ("收入", ("revenue",)), ("利润率 %", ("gross_margin_pct", "operating_margin_pct")),
        ("现金流", ("operating_cash_flow", "capex", "fcf")), ("稀释股数", ("diluted_shares",)),
    )
    colors = {"revenue": "#2563eb", "gross_margin_pct": "#059669", "operating_margin_pct": "#d97706", "operating_cash_flow": "#2563eb", "capex": "#dc2626", "fcf": "#059669", "diluted_shares": "#7c3aed"}
    rendered = []
    for index, (label, keys) in enumerate(panels):
        left = 55 + (index % 2) * 455
        top = 50 + (index // 2) * 170
        paths, low, high = _scaled_paths(rows, keys, left=left, top=top, width=390, height=115)
        rendered.append(f'<text x="{left}" y="{top - 10}" font-size="13">{escape(label)}</text><text x="{left + 385}" y="{top - 10}" text-anchor="end" font-size="9">{escape(format(low, "f"))} … {escape(format(high, "f"))}</text>')
        rendered.extend(
            (f'<circle cx="{points.split(",")[0]}" cy="{points.split(",")[1]}" r="3" fill="{colors[key]}"/>' if " " not in points else
             f'<polyline points="{points}" fill="none" stroke="{colors[key]}" stroke-width="2"/>')
            for key, points in paths
        )
        rendered.append(f'<line x1="{left}" y1="{top + 115}" x2="{left + 390}" y2="{top + 115}" stroke="#cbd5e1"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="420" viewBox="0 0 960 420" role="img" aria-label="财务趋势分面">'
        '<rect width="960" height="420" fill="white"/><text x="55" y="28" font-size="18">财务趋势（不同量纲分面）</text>'
        + "".join(rendered)
        + f'<text x="55" y="412" font-size="10" fill="#6b7280">限制：{escape("；".join(chart["limitations"]) or "无")}</text></svg>\n'
    )


def _render_svg(chart: Mapping[str, Any]) -> str:
    if chart["chart_id"] == "price_volume_sma":
        return _render_price_svg(chart)
    if chart["chart_id"] == "relative_performance_drawdown":
        return _render_relative_svg(chart)
    if chart["chart_id"] == "financial_trends":
        return _render_financial_svg(chart)
    if chart.get("unit") == "mixed":
        limitation = "；".join(str(item) for item in chart.get("limitations", [])) or "无"
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="220" viewBox="0 0 960 220" role="img" '
            f'aria-label="{escape(str(chart["title"]))}"><rect width="960" height="220" fill="#ffffff"/>'
            f'<text x="70" y="42" font-size="18" font-family="sans-serif">{escape(str(chart["title"]))}</text>'
            '<rect x="70" y="70" width="820" height="82" rx="10" fill="#f8fafc" stroke="#cbd5e1"/>'
            '<text x="90" y="105" font-size="15" fill="#334155">混合量纲数据不绘制跨字段折线</text>'
            f'<text x="90" y="132" font-size="12" fill="#64748b">共 {len(chart.get("data", []))} 条冻结记录；请核对下方分单位数据表。</text>'
            f'<text x="70" y="198" font-size="10" fill="#6b7280">限制：{escape(limitation)}</text></svg>\n'
        )
    rows = chart["data"]
    width, height = 960, 420
    numeric_keys = []
    for key in ("close", "sma20", "sma60", "sma200", "security_index", "benchmark_index", "security_drawdown_pct", "benchmark_drawdown_pct", "revenue", "gross_margin_pct", "operating_margin_pct", "operating_cash_flow", "capex", "fcf", "diluted_shares", "value"):
        if _numeric_series(rows, key):
            numeric_keys.append(key)
    all_values = [_decimal(row[key], key) for row in rows for key in numeric_keys if row.get(key) is not None]
    low, high = (min(all_values), max(all_values)) if all_values else (Decimal(0), Decimal(1))
    if high == low:
        high = low + Decimal(1)
    palette = ("#2563eb", "#d97706", "#059669", "#7c3aed", "#dc2626", "#0891b2", "#4b5563")
    lines = []
    denom = max(1, len(rows) - 1)
    for key, color in zip(numeric_keys, palette):
        parts, active = [], []
        for index, row in enumerate(rows):
            if row.get(key) is None or row.get("gap") or row.get("discontinuity"):
                if active:
                    parts.append(active)
                    active = []
                continue
            x = 70 + index / denom * 820
            y = 340 - float((_decimal(row[key], key) - low) / (high - low)) * 270
            active.append(f"{x:.2f},{y:.2f}")
        if active:
            parts.append(active)
        for points in parts:
            if len(points) == 1:
                x, y = points[0].split(",")
                lines.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"/>')
            else:
                lines.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>')
    legend = "".join(f'<text x="{70 + (index % 4) * 210}" y="{375 + (index // 4) * 18}" font-size="12" fill="{palette[index % len(palette)]}">{escape(key)}</text>' for index, key in enumerate(numeric_keys))
    limitation = "；".join(str(item) for item in chart.get("limitations", [])) or "无"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(str(chart["title"]))}">'
        '<rect width="960" height="420" fill="#ffffff"/><line x1="70" y1="340" x2="890" y2="340" stroke="#9ca3af"/>'
        f'<text x="70" y="30" font-size="18" font-family="sans-serif">{escape(str(chart["title"]))}</text>'
        f'<text x="70" y="50" font-size="11" fill="#4b5563">口径：{escape(str(chart.get("basis") or "见数据附件"))}</text>'
        + "".join(lines) + legend
        + f'<text x="70" y="414" font-size="10" fill="#6b7280">限制：{escape(limitation)}</text></svg>\n'
    )


def _safe_directory(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or not name or ".." in relative.parts:
        raise ResearchVisualError("VISUAL_OUTPUT_PATH_INVALID")
    resolved_root = Path(root).resolve()
    target = (resolved_root / Path(*relative.parts)).resolve()
    if not target.is_relative_to(resolved_root):
        raise ResearchVisualError("VISUAL_OUTPUT_PATH_ESCAPES_ROOT")
    return target


def _table(chart: Mapping[str, Any]) -> str:
    rows = chart["data"]
    if not rows:
        return f'<p class="limit">数据不足：{escape("；".join(chart.get("limitations", [])))}</p>'
    keys = list(dict.fromkeys(key for row in rows for key in row if key != "evidence_refs"))
    head = "".join(f"<th>{escape(str(key))}</th>" for key in keys)
    def display(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, bool):
            return "是" if value else "否"
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return str(value)
        if not number.is_finite():
            return str(value)
        rendered = format(number.quantize(Decimal("0.0001")), "f")
        return rendered.rstrip("0").rstrip(".") or "0"
    body = "".join("<tr>" + "".join(
        f"<td>{escape(display(row.get(key)))}</td>" for key in keys
    ) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def persist_visual_report(
    output_root: Path, *, directory_name: str, report: Mapping[str, Any],
    bundle: Mapping[str, Any] | None, legacy_markdown: str | None = None,
) -> dict[str, Any]:
    """落盘完整离线报告；无附件时不改写旧报告。"""

    if bundle is None:
        return {"mode": "LEGACY_UNCHANGED", "legacy_markdown": legacy_markdown}
    validate_visual_bundle(bundle)
    report_id = report.get("report_id") or report.get("research_id")
    run_id = report.get("run_id") or report.get("bindings", {}).get("run_id")
    security_id = report.get("security_id") or report.get("security", {}).get("security_id")
    cutoff = report.get("decision_cutoff") or report.get("bindings", {}).get("decision_cutoff")
    if (report_id, run_id, security_id, cutoff) != (bundle["report_id"], bundle["run_id"], bundle["security_id"], bundle["decision_cutoff"]):
        raise ResearchVisualError("VISUAL_REPORT_BINDING_MISMATCH")
    target = _safe_directory(Path(output_root), directory_name)
    if target.exists():
        raise ResearchVisualError("VISUAL_OUTPUT_EXISTS")
    charts_dir, data_dir = target / "charts", target / "data"
    charts_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    (target / "research.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (data_dir / "visual-bundle.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    entries = []
    sections_html, sections_md = [], []
    for chart in bundle["charts"]:
        chart_id = chart["chart_id"]
        data_path = data_dir / f"{chart_id}.json"
        svg_path = charts_dir / f"{chart_id}.svg"
        data_path.write_text(json.dumps(chart, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        svg_path.write_text(_render_svg(chart), encoding="utf-8")
        entries.append({
            "chart_id": chart_id, "status": chart["status"],
            "svg_ref": f"charts/{chart_id}.svg", "data_ref": f"data/{chart_id}.json",
            "svg_sha256": file_hash(svg_path), "data_sha256": file_hash(data_path),
            "data_hash": chart["data_hash"],
        })
        sections_html.append(f'<section><h2>{escape(str(chart["title"]))}</h2><img src="charts/{escape(chart_id)}.svg" alt="{escape(str(chart["title"]))}"/>{_table(chart)}</section>')
        sections_md.extend([f'## {chart["title"]}', "", f'![{chart["title"]}](charts/{chart_id}.svg)', "", f'- 数据附件：`data/{chart_id}.json`', f'- 状态：`{chart["status"]}`', f'- 限制：{"；".join(chart["limitations"]) or "无"}', ""])
    manifest = {
        "schema_version": MANIFEST_VERSION, "report_id": bundle["report_id"],
        "run_id": bundle["run_id"], "security_id": bundle["security_id"],
        "decision_cutoff": bundle["decision_cutoff"], "bundle_hash": bundle["bundle_hash"],
        "entries": entries,
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    title = escape(str(report.get("title") or security_id))
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    limitations = report.get("limitations") if isinstance(report.get("limitations"), list) else []
    summary_rows = "".join(
        f'<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>'
        for key, value in summary.items()
    ) or '<tr><td>未提供确定性摘要</td></tr>'
    limitation_items = "".join(f'<li>{escape(str(item))}</li>' for item in limitations) or '<li>无额外限制记录</li>'
    interpretations = report.get("interpretations") if isinstance(report.get("interpretations"), list) else []
    interpretation_items = "".join(f'<li>{escape(str(item))}</li>' for item in interpretations) or '<li>模型研究解释待专项消费验收；本报告不自行补写投资判断。</li>'
    overview_html = (
        '<section id="report-overview"><h2>估值摘要与覆盖说明</h2>'
        f'<div class="table-wrap"><table><tbody>{summary_rows}</tbody></table></div>'
        f'<h3>覆盖限制</h3><ul>{limitation_items}</ul>'
        f'<h3>既有研究解释</h3><ul>{interpretation_items}</ul></section>'
    )
    html = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} 研究报告</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Noto Sans CJK SC",sans-serif;color:#172033;max-width:1180px;margin:auto;padding:24px;background:#f5f7fb}}header,section{{background:white;border:1px solid #dbe2ea;border-radius:12px;padding:20px;margin:0 0 18px}}img{{display:block;width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #dbe2ea;padding:6px;text-align:left;vertical-align:top;word-break:break-word}}.table-wrap{{overflow-x:auto}}.limit{{color:#9a3412;overflow-wrap:anywhere}}@media(max-width:640px){{body{{padding:8px}}header,section{{padding:12px}}.table-wrap table{{min-width:900px}}}}@page{{size:A4 landscape;margin:8mm}}@media print{{body{{background:white;max-width:none;padding:0}}header{{break-inside:avoid}}section{{break-inside:auto}}header,section{{border:0;border-bottom:1px solid #bbb}}section h2{{break-after:avoid-page}}section h2,section img{{break-inside:avoid}}.table-wrap{{overflow:visible}}table{{font-size:8px;table-layout:fixed}}th,td{{padding:3px;overflow-wrap:anywhere}}}}
</style></head><body><header><h1>{title} 研究报告</h1><p>资料截止：{escape(str(bundle["decision_cutoff"]))}</p><p>本页只展示冻结研究数据与既有报告，不产生新的投资判断或交易动作。</p></header>{overview_html}{''.join(sections_html)}</body></html>'''
    if "<script" in html.lower() or "http://" in html.lower() or "https://" in html.lower():
        raise ResearchVisualError("VISUAL_HTML_EXTERNAL_OR_SCRIPT_CONTENT")
    (target / "report.html").write_text(html, encoding="utf-8")
    summary_md = ["## 估值摘要与覆盖说明", "", *[f"- {key}：`{value}`" for key, value in summary.items()], "", "### 覆盖限制", "", *[f"- {item}" for item in limitations], "", "### 既有研究解释", "", *[f"- {item}" for item in interpretations]]
    if not interpretations:
        summary_md.append("- 模型研究解释待专项消费验收；本报告不自行补写投资判断。")
    markdown = "\n".join([f"# {report.get('title') or security_id} 研究报告", "", f"资料截止：`{bundle['decision_cutoff']}`", "", "本报告不产生交易动作。", "", *summary_md, "", *sections_md]).rstrip() + "\n"
    (target / "report.md").write_text(markdown, encoding="utf-8")
    validate_persisted_visual_report(target)
    return {"mode": "VISUAL", "directory": str(target), "manifest": str(target / "manifest.json"), "html": str(target / "report.html"), "markdown": str(target / "report.md")}


def validate_persisted_visual_report(directory: Path) -> None:
    root = Path(directory).resolve()
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        bundle = json.loads((root / "data/visual-bundle.json").read_text(encoding="utf-8"))
        html = (root / "report.html").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchVisualError("VISUAL_PERSISTED_ARTIFACT_UNREADABLE") from exc
    validate_visual_bundle(bundle)
    if manifest.get("manifest_hash") != _hash_without(manifest, "manifest_hash") or manifest.get("bundle_hash") != bundle["bundle_hash"]:
        raise ResearchVisualError("VISUAL_MANIFEST_HASH_MISMATCH")
    for entry in manifest.get("entries", []):
        for ref_key, hash_key in (("svg_ref", "svg_sha256"), ("data_ref", "data_sha256")):
            ref = PurePosixPath(entry[ref_key])
            path = (root / Path(*ref.parts)).resolve()
            if ref.is_absolute() or ".." in ref.parts or not path.is_relative_to(root) or file_hash(path) != entry[hash_key]:
                raise ResearchVisualError("VISUAL_MANIFEST_PATH_OR_HASH_INVALID")
    if "<script" in html.lower() or "http://" in html.lower() or "https://" in html.lower():
        raise ResearchVisualError("VISUAL_HTML_EXTERNAL_OR_SCRIPT_CONTENT")
