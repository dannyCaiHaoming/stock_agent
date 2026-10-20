"""通用事件统计：对 events-insider / events-congress 等事件表按 signal 分组，比较同日对照，并按入场时趋势阶段交叉。

用法：.venv/bin/python -I scripts/audit-event-stats.py <events-*.jsonl 名称，如 insider> [--as-of YYYY-MM-DD] [--out 文件]
对照与趋势阶段取自 events-pead.jsonl 的每日对照行（先运行 build-pead-events.py）。只统计结果窗口在 as_of 之前结束的样本。
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


def ci(rows, key, reps=1000):
    groups = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r["ab"])
    names = list(groups)
    if len(names) < 5:
        return None
    rng = random.Random(0)
    means = sorted(statistics.mean([v for n in (rng.choice(names) for _ in names) for v in groups[n]]) for _ in range(reps))
    return round(means[int(0.025 * reps)] * 100, 2), round(means[int(0.975 * reps)] * 100, 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--as-of", default="9999-12-31")
    parser.add_argument("--out")
    args = parser.parse_args()
    root = settings.cache().root / "derived" / "signals"
    ctrl_all, ctrl_stage, stage_of, ctrl_ticker = {}, {}, {}, {}
    for line in (root / "events-pead.jsonl").open():
        r = json.loads(line)
        if r["kind"] != "control":
            continue
        stage_of[(r["ticker"], r["entry_date"])] = r["stage"]
        for h in HORIZONS:
            if r.get(h) is not None and r.get(f"exit_{h}", "9999") < args.as_of:
                ctrl_all.setdefault((h, r["entry_date"]), []).append(r[h])
                ctrl_stage.setdefault((h, r["entry_date"], r["stage"]), []).append(r[h])
                ctrl_ticker.setdefault((h, r["ticker"], r["entry_date"][:4]), []).append(r[h])
    sorted_all = {k: sorted(v) for k, v in ctrl_all.items() if len(v) >= 10}  # rank against same-date cross-section
    sorted_stage = {k: sorted(v) for k, v in ctrl_stage.items() if len(v) >= 5}
    events = [json.loads(line) for line in (root / f"events-{args.name}.jsonl").open()]
    for e in events:
        e["stage"] = stage_of.get((e["ticker"], e["entry_date"]), "other")
    signals = sorted({e["signal"] for e in events})
    lines = [f"# {args.name} 事件统计（as_of {args.as_of if args.as_of != '9999-12-31' else '最新'}）", "",
             "收益：相对所属板块 ETF 的超额收益，申报日后第一个交易日收盘入场，扣成本前。置信区间：按股票、按月份整群自助抽样。", ""]

    def block(title, pick, against):
        out = [f"### {title}", "", "| 信号 | 持有日 | n | 上涨概率 | 中位超额 | 平均百分位−50 | 95% CI（按股票） | 95% CI（按月份） | 结论 |",
               "|---|---|---|---|---|---|---|---|---|"]
        for s in signals:
            for h in HORIZONS:
                rows = []
                for e in events:
                    if e["signal"] != s or not pick(e) or e.get(h) is None or e.get(f"exit_{h}", "9999") >= args.as_of:
                        continue
                    pool = sorted_all.get((h, e["entry_date"])) if against == "all" else \
                        sorted_stage.get((h, e["entry_date"], e["stage"]))
                    if not pool:
                        continue
                    pct = (bisect.bisect_left(pool, e[h]) + bisect.bisect_right(pool, e[h])) / 2 / len(pool)
                    rows.append({"ab": pct - 0.5, "x": e[h], "ticker": e["ticker"], "month": e["entry_date"][:7]})
                if len(rows) < 30:
                    out.append(f"| {s} | {h} | {len(rows)} | | | | | | 需要验证 |")
                    continue
                a, b = ci(rows, "ticker"), ci(rows, "month")
                verdict = "高于对照" if a and b and a[0] > 0 and b[0] > 0 else "低于对照" if a and b and a[1] < 0 and b[1] < 0 else "无可靠差异"
                out.append(f"| {s} | {h} | {len(rows)} | {round(sum(r['x'] > 0 for r in rows) / len(rows), 3)} | "
                           f"{round(statistics.median(r['x'] for r in rows) * 100, 2)}% | {round(statistics.mean(r['ab'] for r in rows) * 100, 2)} | {a} | {b} | {verdict} |")
        return out + [""]
    lines += block("全部（同日全股票池百分位）", lambda e: True, "all")
    for stage in ("stage2", "stage4"):
        lines += block(f"入场时趋势阶段 = {stage}（同日、同趋势阶段百分位）", lambda e, s=stage: e["stage"] == s, "stage")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
