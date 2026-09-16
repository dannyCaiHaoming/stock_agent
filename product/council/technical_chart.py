"""从冻结日线生成可审计 SVG；图表不增加研究判断。"""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any, Mapping, Sequence


def _number(value: Any) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("TECHNICAL_CHART_VALUE_INVALID")
    return number


def render_relative_performance_svg(
    security_rows: Sequence[Mapping[str, Any]],
    benchmark_rows: Sequence[Mapping[str, Any]],
    *, security_label: str, benchmark_label: str,
) -> str:
    """生成证券/基准归一化表现和成交量图。"""

    benchmark = {str(item["date"]): item for item in benchmark_rows}
    aligned = [(item, benchmark[str(item["date"])]) for item in security_rows if str(item["date"]) in benchmark]
    if len(aligned) < 2:
        raise ValueError("TECHNICAL_CHART_HISTORY_INSUFFICIENT")
    security_values = [_number(item[0].get("adjusted_close")) for item in aligned]
    benchmark_values = [_number(item[1].get("adjusted_close")) for item in aligned]
    volumes = [_number(item[0].get("volume", 0)) for item in aligned]
    if security_values[0] <= 0 or benchmark_values[0] <= 0 or any(item < 0 for item in volumes):
        raise ValueError("TECHNICAL_CHART_VALUE_INVALID")
    security_index = [item / security_values[0] * Decimal(100) for item in security_values]
    benchmark_index = [item / benchmark_values[0] * Decimal(100) for item in benchmark_values]
    all_index = security_index + benchmark_index
    low, high = min(all_index), max(all_index)
    spread = high - low or Decimal(1)
    width, height = Decimal(900), Decimal(420)
    left, top, chart_width, chart_height = Decimal(60), Decimal(35), Decimal(800), Decimal(245)
    step = chart_width / Decimal(len(aligned) - 1)

    def points(values: Sequence[Decimal]) -> str:
        return " ".join(
            f"{float(left + step * index):.2f},{float(top + (high - value) / spread * chart_height):.2f}"
            for index, value in enumerate(values)
        )

    max_volume = max(volumes) or Decimal(1)
    bars = []
    for index, volume in enumerate(volumes):
        bar_height = volume / max_volume * Decimal(90)
        x = left + step * index - Decimal(2)
        y = Decimal(390) - bar_height
        bars.append(
            f'<rect x="{float(x):.2f}" y="{float(y):.2f}" width="4" height="{float(bar_height):.2f}" fill="#6b7280" opacity="0.55"/>'
        )
    first_day, last_day = str(aligned[0][0]["date"]), str(aligned[-1][0]["date"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="420" viewBox="0 0 900 420" role="img" '
        f'aria-label="{escape(security_label)} 相对 {escape(benchmark_label)} 表现与成交量">'
        '<rect width="900" height="420" fill="white"/>'
        f'<text x="60" y="22" font-size="15">复权表现（起点=100）：{escape(security_label)} / {escape(benchmark_label)}</text>'
        f'<polyline points="{points(security_index)}" fill="none" stroke="#2563eb" stroke-width="2"/>'
        f'<polyline points="{points(benchmark_index)}" fill="none" stroke="#f59e0b" stroke-width="2"/>'
        + "".join(bars)
        + f'<text x="60" y="410" font-size="12">{escape(first_day)}</text>'
        + f'<text x="780" y="410" font-size="12">{escape(last_day)}</text>'
        + '<text x="60" y="300" font-size="12">成交量（同源日线）</text>'
        + '</svg>\n'
    )
