"""8-K 事项事件统计表：每类事项之后 1/5/20/60 日相对同日对照的表现（确定性计算）。

用法：.venv/bin/python -I scripts/audit-8k-stats.py [--as-of YYYY-MM-DD] [--out evals/signals/8k-latest.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.deterministic.signal_events import EVENT_HORIZONS, FORM_8K_ITEMS  # noqa: E402
from product.mcp import reference_tools  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--as-of")
parser.add_argument("--out")
args = parser.parse_args()
lines = [f"# 8-K 事项事件统计（as_of {args.as_of or '最新'}）", "",
         "收益：相对所属板块 ETF 的超额收益，可交易时点入场（16:00 前受理用当天收盘，否则次日收盘），扣成本前。",
         "“相对同日对照”减去同一日期全股票池的平均超额收益；置信区间为按股票、按月份整群自助抽样。", ""]
for h in EVENT_HORIZONS:
    lines += [f"## 持有 {h} 个交易日", "",
              "| 事项 | 含义 | n | 股票数 | 上涨概率 | 均值 | 中位 | 相对同日对照 | 95% CI（按股票） | 95% CI（按月份） | 状态 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for code, label in FORM_8K_ITEMS.items():
        r = reference_tools.get_signal_stats(f"8k_item_{code}", h, as_of=args.as_of)
        m = r["summary"]
        if not m.get("n"):
            continue
        lines.append(f"| {code} | {label} | {m['n']} | {m['distinct_tickers']} | {m['hit_rate']} | {m['mean_excess_pct']}% | "
                     f"{m['median_excess_pct']}% | {m['mean_vs_matched_control_pp']}pp | {m['ci95_cluster_by_ticker_pp']} | "
                     f"{m['ci95_cluster_by_month_pp']} | {r['status']} |")
    lines.append("")
text = "\n".join(lines) + "\n"
if args.out:
    Path(args.out).write_text(text)
print(text)
