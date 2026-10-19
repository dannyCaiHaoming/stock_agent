"""信号统计核查报告：同日对照、扣成本、整群置信区间、按年份差值（确定性计算）。

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
         "对照：同一日期全股票池对照样本的平均超额收益（同日对照）。置信区间：按股票、按月份整群自助抽样（1000 次）。", ""]
for h in HORIZONS:
    lines += [f"## 持有 {h} 个交易日", "",
              "| 信号 | n | 股票数 | 均值 | 中位 | 胜率 | 平均盈/亏 | 盈亏比 | 相对同日对照 | 95% CI（按股票） | 95% CI（按月份） | 扣成本后均值 | 状态 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in signals:
        r = reference_tools.get_signal_stats(s, h, as_of=args.as_of)
        m = r["summary"]
        if not m.get("n"):
            lines.append(f"| {s} | 0 | | | | | | | | | | | {r['status']} |")
            continue
        lines.append(f"| {s} | {m['n']} | {m['distinct_tickers']} | {m['mean_excess_pct']}% | {m['median_excess_pct']}% | "
                     f"{m['hit_rate']} | {m['avg_win_pct']}% / {m['avg_loss_pct']}% | {m['payoff_ratio']} | "
                     f"{m['mean_vs_matched_control_pp']}pp | {m['ci95_cluster_by_ticker_pp']} | {m['ci95_cluster_by_month_pp']} | "
                     f"{m['mean_excess_after_cost_pct']}% | {r['status']} |")
    lines.append("")
lines += ["## 按年份（60 日，相对同日对照，pp）", "", "| 信号 | " + " | ".join(str(y) for y in range(2019, 2027)) + " |",
          "|---|" + "---|" * 8]
for s in signals:
    by = reference_tools.get_signal_stats(s, 60, as_of=args.as_of)["by_year_vs_matched_control"]
    lines.append(f"| {s} | " + " | ".join(f"{by[str(y)]['mean_vs_matched_control_pp']} (n={by[str(y)]['n']})"
                                          if str(y) in by else "—" for y in range(2019, 2027)) + " |")
text = "\n".join(lines) + "\n"
if args.out:
    Path(args.out).write_text(text)
print(text)
