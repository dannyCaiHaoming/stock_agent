"""信号统计核查报告：同日横截面百分位、扣成本、整群置信区间、按年份百分位（确定性计算）。

用法：.venv/bin/python -I scripts/audit-signal-stats.py [--as-of YYYY-MM-DD] [--out evals/signals/audit.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.deterministic.signal_events import FUNDAMENTAL_SIGNALS, HORIZONS, TECHNICAL_SIGNALS  # noqa: E402
from product.mcp import reference_tools  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--as-of")
parser.add_argument("--out")
args = parser.parse_args()
signals = [s for s in {**TECHNICAL_SIGNALS, **FUNDAMENTAL_SIGNALS} if not s.startswith("baseline")]
lines = [f"# 信号统计核查（as_of {args.as_of or '最新'}）", "",
         "收益：相对所属板块 ETF 的超额收益，信号次日收盘入场，扣成本前；“扣成本后”减去 0.2pp 往返成本。",
         "对照：事件在同一日期全股票池对照样本中的百分位（中间名次），平均百分位−50 以百分位点计；不受极端赢家影响。置信区间：按股票、按月份整群自助抽样（1000 次），两者都不含 0 才算可靠。", ""]
for h in HORIZONS:
    lines += [f"## 持有 {h} 个交易日", "",
              "| 信号 | n | 股票数 | 上涨概率 | 平均超额 | 中位超额 | 平均盈/亏 | 盈亏比 | 平均百分位−50 | 95% CI（按股票） | 95% CI（按月份） | 扣成本后均值 | 结论 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in signals:
        r = reference_tools.get_signal_stats(s, h, as_of=args.as_of)
        m = r["summary"]
        if not m.get("n"):
            lines.append(f"| {s} | 0 | | | | | | | | | | | {r['status']} |")
            continue
        lines.append(f"| {s} | {m['n']} | {m['distinct_tickers']} | {m['hit_rate']} | {m['mean_excess_pct']}% | {m['median_excess_pct']}% | "
                     f"{m['avg_win_pct']}% / {m['avg_loss_pct']}% | {m['payoff_ratio']} | "
                     f"{m['mean_percentile_minus_50']} | {m['ci95_cluster_by_ticker_pts']} | {m['ci95_cluster_by_month_pts']} | "
                     f"{m['mean_excess_after_cost_pct']}% | {r['status']} |")
    lines.append("")
lines += ["## 按年份（60 日，平均百分位−50）", "", "| 信号 | " + " | ".join(str(y) for y in range(2019, 2027)) + " |",
          "|---|" + "---|" * 8]
for s in signals:
    by = reference_tools.get_signal_stats(s, 60, as_of=args.as_of)["by_year_percentile_minus_50"]
    lines.append(f"| {s} | " + " | ".join(f"{by[str(y)]['mean_percentile_minus_50']} (n={by[str(y)]['n']})"
                                          if str(y) in by else "—" for y in range(2019, 2027)) + " |")
text = "\n".join(lines) + "\n"
if args.out:
    Path(args.out).write_text(text)
print(text)
