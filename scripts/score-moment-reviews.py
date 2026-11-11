"""消息面复盘的事后对照：把盲写的复盘（moment_reviews.jsonl）与关键时刻事件表里的结果对上，
按主要原因、持有者动作分组看之后 20/60 个交易日的收益与相对板块收益。

用法：
  .venv/bin/python -I scripts/score-moment-reviews.py .local/runs/*-news*/moment_reviews.jsonl [--md 输出.md]

同一 (ticker, moment, 日期) 有多条复盘时取最后一条。结果来自 .local/cache/derived/signals/key-moments.jsonl
（scripts/build-key-moments.py 建表）；“同类全部”= 事件表里同一时刻类型的全部样本，作对照。
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import settings  # noqa: E402

HORIZONS = ("20", "60")


def cell(values: list[float]) -> str:
    if not values:
        return "—"
    return f"{statistics.mean(values):+.1f} / {sum(v > 0 for v in values) / len(values):.0%}"


def table(title: str, groups: dict[str, list[dict]]) -> list[str]:
    head = " | ".join(f"{h} 日收益 均值/上涨比例 | {h} 日相对板块 均值/跑赢比例" for h in HORIZONS)
    lines = [f"## {title}", "", f"| 分组 | 次数 | {head} |", "|---|---|" + "---|" * (2 * len(HORIZONS))]
    for name, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        cells = []
        for h in HORIZONS:
            outs = [r["outcome"][h] for r in rows if r["outcome"].get(h)]
            cells += [cell([o["ret"] * 100 for o in outs]),
                      cell([o["excess"] * 100 for o in outs if o["excess"] is not None])]
        lines.append(f"| {name} | {len(rows)} | " + " | ".join(cells) + " |")
    return lines + [""]


def excess(rows: list[dict], h: str) -> list[float]:
    return [r["outcome"][h]["excess"] * 100 for r in rows if r["outcome"].get(h) and r["outcome"][h]["excess"] is not None]


def median_gap(a: list[dict], b: list[dict], h: str, draws: int = 5000) -> tuple[float, float, float] | None:
    """median(a) - median(b) of excess at horizon h, with a 90% bootstrap interval (fixed seed)."""
    xa, xb = excess(a, h), excess(b, h)
    if len(xa) < 3 or len(xb) < 3:
        return None
    rng = random.Random(20261112)
    gaps = sorted(statistics.median(rng.choices(xa, k=len(xa))) - statistics.median(rng.choices(xb, k=len(xb)))
                  for _ in range(draws))
    return statistics.median(xa) - statistics.median(xb), gaps[int(0.05 * draws)], gaps[int(0.95 * draws)]


def registered(joined: list[dict], sample: Path) -> list[str]:
    """Tests registered in evals/key-moments/news-review-idio-plan-2026-11-12.md."""
    dev = {(x["ticker"], x["date"]): x["deviation_vs_sector"] for x in json.loads(sample.read_text())}
    rows = [r for r in joined if (r["ticker"], r["moment_date"]) in dev]
    down = [r for r in rows if dev[(r["ticker"], r["moment_date"])] < 0]
    up = [r for r in rows if dev[(r["ticker"], r["moment_date"])] > 0]
    pick = lambda g, a: [r for r in g if r.get("holder_action") == a]  # noqa: E731
    lines = ["## 事先登记的检验", "", f"样本内复盘 {len(rows)} 条：向下偏离 {len(down)}、向上偏离 {len(up)}。", ""]
    for name, group, act in (("P1 向下偏离：REDUCE − HOLD，60 日相对板块中位数", down, "REDUCE"),
                             ("P3 向上偏离：ADD − HOLD，60 日相对板块中位数", up, "ADD")):
        a, b = pick(group, act), pick(group, "HOLD")
        g = median_gap(a, b, "60")
        verdict = "样本不足（每组至少 8 个）" if len(a) < 8 or len(b) < 8 or not g else (
            ("通过" if (g[0] <= -3 and g[2] < 0) else "未通过") if act == "REDUCE" else
            ("通过" if (g[0] >= 3 and g[1] > 0) else "未通过"))
        lines.append(f"- {name}：{act} {len(a)} 个、HOLD {len(b)} 个；"
                     + (f"差 {g[0]:+.1f} 个百分点，90% 区间 [{g[1]:+.1f}, {g[2]:+.1f}]" if g else "无法计算")
                     + f" → {verdict}")
    red20 = excess(pick(down, "REDUCE"), "20")
    if red20:
        share = sum(v > 0 for v in red20) / len(red20)
        lines.append(f"- P2 向下偏离且 REDUCE 的 20 日相对板块：中位数 {statistics.median(red20):+.1f}%，"
                     f"跑赢比例 {share:.0%}（{len(red20)} 个）→ {'先反弹' if statistics.median(red20) > 0 and share > 0.5 else '没有先反弹'}")
    return lines + [""]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--md")
    parser.add_argument("--sample", help="抽样文件（含 deviation_vs_sector），给出事先登记的检验")
    args = parser.parse_args()
    reviews: dict[tuple, dict] = {}
    for p in args.paths:
        for line in Path(p).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                reviews[(r["ticker"], r["moment"], r["moment_date"])] = r
    events = {}
    for line in (settings.cache().root / "derived/signals/key-moments.jsonl").open():
        e = json.loads(line)
        events[(e["ticker"], e["moment"], e["date"])] = e
    joined, missing = [], []
    for key, r in reviews.items():
        e = events.get(key)
        (joined if e else missing).append({**r, "outcome": e["outcome"] if e else {}})
    by_cause, by_action, by_both = {}, {}, {}
    for r in joined:
        by_cause.setdefault(r["primary_cause"], []).append(r)
        by_action.setdefault(r.get("holder_action") or "（旧版无动作）", []).append(r)
        by_both.setdefault(f"{r['primary_cause']} · {r.get('holder_action') or '—'}", []).append(r)
    moments = {r["moment"] for r in joined}
    reference = {f"同类全部 {m}": [e for e in events.values() if e["moment"] == m] for m in sorted(moments)}
    lines = ["# 消息面复盘的事后对照", "",
             f"复盘 {len(reviews)} 条，对上事件表 {len(joined)} 条，未对上 {len(missing)} 条。"
             "收益从信号日下一个交易日收盘起算。每格为“均值 / 正值比例”。", ""]
    if args.sample:
        lines += registered(joined, Path(args.sample))
    lines += table("按主要原因", by_cause) + table("按持有者动作", by_action) + table("原因 × 动作", by_both)
    lines += table("对照：事件表里同类时刻的全部样本", reference)
    if missing:
        lines += ["未对上：" + "，".join(f"{t} {m} {d}" for t, m, d in (k for k in reviews if k not in events)), ""]
    text = "\n".join(lines)
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
