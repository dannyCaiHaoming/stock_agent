"""财报后漂移统计：按反应分组 × 趋势阶段 × 成交量放大，比较同日对照与同日同阶段对照（确定性计算）。

用法：.venv/bin/python -I scripts/audit-pead-stats.py [--as-of YYYY-MM-DD] [--out evals/signals/pead-latest.md]
只统计结果窗口在 as_of 之前结束的样本。置信区间：按股票、按月份整群自助抽样（1000 次）。
"""

from __future__ import annotations

import argparse
import bisect
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import settings  # noqa: E402

HORIZONS = ("5", "20", "60", "126", "252")
BUCKETS = ("strong_up", "up", "flat", "down", "strong_down")
LABEL = {"strong_up": "大涨 >+5%", "up": "小涨 +2～+5%", "flat": "持平 ±2%", "down": "小跌 −5～−2%",
         "strong_down": "大跌 <−5%"}


def ci(rows: list[dict], key: str, reps: int = 1000) -> tuple[float, float] | None:
    groups: dict[str, list[float]] = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r["ab"])
    names = list(groups)
    if len(names) < 5:
        return None
    rng = random.Random(0)
    means = sorted(statistics.mean([v for n in (rng.choice(names) for _ in names) for v in groups[n]])
                   for _ in range(reps))
    return round(means[int(0.025 * reps)] * 100, 2), round(means[int(0.975 * reps)] * 100, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default="9999-12-31")
    parser.add_argument("--out")
    args = parser.parse_args()
    path = settings.cache().root / "derived" / "signals" / "events-pead.jsonl"
    events, ctrl_all, ctrl_stage, ctrl_ticker = [], {}, {}, {}
    for line in path.open():
        r = json.loads(line)
        for h in HORIZONS:
            if r.get(h) is None or r.get(f"exit_{h}", "9999") >= args.as_of:
                continue
            if r["kind"] == "control":
                ctrl_all.setdefault((h, r["entry_date"]), []).append(r[h])
                ctrl_stage.setdefault((h, r["entry_date"], r["stage"]), []).append(r[h])
                ctrl_ticker.setdefault((h, r["ticker"], r["entry_date"][:4]), []).append(r[h])
        if r["kind"] == "event":
            events.append(r)
    sorted_all = {k: sorted(v) for k, v in ctrl_all.items() if len(v) >= 10}  # rank against same-date cross-section
    sorted_stage = {k: sorted(v) for k, v in ctrl_stage.items() if len(v) >= 5}

    def table(title: str, select, groups: list[tuple[str, str]], against: str) -> list[str]:
        out = [f"### {title}", "", "| 分组 | 持有日 | n | 上涨概率 | 中位超额 | 平均百分位−50 | 95% CI（按股票） | 95% CI（按月份） | 结论 |",
               "|---|---|---|---|---|---|---|---|---|"]
        for gname, glabel in groups:
            for h in HORIZONS:
                rows = []
                for e in events:
                    if not select(e, gname) or e.get(h) is None or e.get(f"exit_{h}", "9999") >= args.as_of:
                        continue
                    pool = sorted_all.get((h, e["entry_date"])) if against == "all" else \
                        sorted_stage.get((h, e["entry_date"], e["stage"]))
                    if not pool:
                        continue
                    pct = (bisect.bisect_left(pool, e[h]) + bisect.bisect_right(pool, e[h])) / 2 / len(pool)
                    rows.append({"ab": pct - 0.5, "x": e[h], "ticker": e["ticker"], "month": e["entry_date"][:7]})
                if len(rows) < 30:
                    out.append(f"| {glabel} | {h} | {len(rows)} | | | | | | 需要验证 |")
                    continue
                a, b = ci(rows, "ticker"), ci(rows, "month")
                verdict = "高于对照" if a and b and a[0] > 0 and b[0] > 0 else \
                    "低于对照" if a and b and a[1] < 0 and b[1] < 0 else "无可靠差异"
                out.append(f"| {glabel} | {h} | {len(rows)} | {round(sum(r['x'] > 0 for r in rows) / len(rows), 3)} | "
                           f"{round(statistics.median(r['x'] for r in rows) * 100, 2)}% | "
                           f"{round(statistics.mean(r['ab'] for r in rows) * 100, 2)} | {a} | {b} | {verdict} |")
        return out + [""]

    lines = [f"# 财报后漂移（as_of {args.as_of if args.as_of != '9999-12-31' else '最新'}）", "",
             "事件：8-K 2.02；反应 = 公告前收盘到入场收盘的板块超额涨跌；入场在反应可见后的收盘。收益扣成本前。",
             f"财报事件 {len(events)} 个。", ""]
    lines += table("按反应分组（同日全股票池百分位）", lambda e, g: e["bucket"] == g,
                   [(b, LABEL[b]) for b in BUCKETS], "all")
    for stage in ("stage2", "stage4", "other"):
        lines += table(f"反应分组 × 入场时趋势阶段 = {stage}（同日、同趋势阶段百分位）",
                       lambda e, g, s=stage: e["bucket"] == g and e["stage"] == s,
                       [(b, LABEL[b]) for b in ("strong_up", "strong_down")], "stage")
    lines += table("大涨/大跌 × 成交量放大 ≥ 2 倍（同日全股票池百分位）",
                   lambda e, g: e["bucket"] == g and (e.get("volume_ratio") or 0) >= 2,
                   [(b, LABEL[b] + "，放量") for b in ("strong_up", "strong_down")], "all")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
