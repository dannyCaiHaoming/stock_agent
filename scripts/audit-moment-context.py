"""关键时刻的情境检验：条件切分与相似案例（口径见 evals/key-moments/context-plan-2026-11-11.md）。

用法：.venv/bin/python -I scripts/audit-moment-context.py [--out 文件.md]
输入 .local/cache/derived/signals/key-moments-context.jsonl（scripts/build-moment-context.py 生成）。
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.deterministic import moment_context as mc  # noqa: E402
from product.mcp import settings  # noqa: E402

SPLIT = "2023-01-01"
LABELS = {"C1_sector_weak": "C1 板块同时走弱", "C2_market_stress": "C2 市场处于压力", "C3_just_reported": "C3 财报刚公布",
          "C4_growth_slowing": "C4 营收增速在放缓", "C5_margin_shrinking": "C5 利润率在收缩",
          "C6_company_filing": "C6 有公司公告", "C7_short_crowded": "C7 空头拥挤", "C8_big_run_up": "C8 之前涨幅大",
          "C9_no_clear_cause": "C9 找不到明显原因"}


def cell(rows: list[dict], h: int = 60) -> dict | None:
    xs = [r["outcome"][str(h)] for r in rows if r["outcome"].get(str(h))]
    exc = [x["excess"] for x in xs if x["excess"] is not None]
    if not exc:
        return None
    ret = [x["ret"] for x in xs]
    ups, downs = [r for r in ret if r > 0], [r for r in ret if r <= 0]
    p = len(ups) / len(ret)
    return {"n": len(exc), "p_exc": sum(e > 0 for e in exc) / len(exc), "med_exc": st.median(exc) * 100, "p_up": p,
            "expect": (p * (st.mean(ups) if ups else 0) + (1 - p) * (st.mean(downs) if downs else 0)) * 100}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()
    path = settings.cache().root / "derived" / "signals" / "key-moments-context.jsonl"
    rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    groups = {"向下": mc.dedupe([r for r in rows if r["moment"] in mc.DOWN]),
              "向上": mc.dedupe([r for r in rows if r["moment"] in mc.UP]),
              "对照（任意一天）": [r for r in rows if r["moment"] == "baseline_days"]}
    lines = ["# 关键时刻的情境检验", "",
             "口径与判定规则见 `context-plan-2026-11-11.md`（计算前写定）。两段时间：2019–2022 与 2023 年以后。"
             "“跑赢板块”= 之后 60 个交易日相对板块 ETF 的超额为正的比例。", "",
             "## 各组整体", "", "| 组 | 时段 | 次数 | 跑赢板块 | 超额中位数 | 上涨概率 | 期望 |", "|---|---|---|---|---|---|---|"]
    for name, g in groups.items():
        for label, part in (("2019–2022", [r for r in g if r["date"] < SPLIT]), ("2023 起", [r for r in g if r["date"] >= SPLIT])):
            c = cell(part)
            lines.append(f"| {name} | {label} | {c['n']} | {c['p_exc']:.0%} | {c['med_exc']:+.1f} | {c['p_up']:.0%} | {c['expect']:+.1f} |")
    lines += ["", "## 条件切分（60 日）", "",
              "| 组 | 条件 | 2019–2022 成立：次数 / 跑赢板块 | 不成立 | 差 | 2023 起 成立：次数 / 跑赢板块 | 不成立 | 差 | 判定 |",
              "|---|---|---|---|---|---|---|---|---|"]
    verdicts = []
    for name in ("向下", "向上", "对照（任意一天）"):
        for flag, label in LABELS.items():
            parts, diffs, ok = [], [], True
            for lo, hi in (("0", SPLIT), (SPLIT, "9")):
                g = [r for r in groups[name] if lo <= r["date"] < hi]
                a, b = cell([r for r in g if r["flags"].get(flag) is True]), cell([r for r in g if r["flags"].get(flag) is False])
                if not a or not b:
                    parts += ["—", "—", "—"]; ok = False
                    continue
                d = (a["p_exc"] - b["p_exc"]) * 100
                diffs.append(d)
                ok = ok and a["n"] >= 100
                parts += [f"{a['n']} / {a['p_exc']:.0%}", f"{b['p_exc']:.0%}", f"{d:+.0f}"]
            real = ok and len(diffs) == 2 and all(abs(d) >= 4 for d in diffs) and diffs[0] * diffs[1] > 0
            verdict = "有差别" if real else "没有可见差别"
            if name != "对照（任意一天）":
                verdicts.append((name, label, verdict, diffs))
            lines.append(f"| {name} | {label} | " + " | ".join(parts) + f" | {verdict} |")
    # Analogs: neighbours among earlier moments of the same group whose 60-day outcome was already known.
    lines += ["", "## 相似案例（验证段：2023 年以后）", "",
              "| 组 | 验证次数 | 参考值与实际超额的秩相关 | 最高档实际超额均值 | 最低档 | 差 | 随机 30 个的秩相关 | 判定 |", "|---|---|---|---|---|---|---|---|"]
    rng = random.Random(20261111)
    for name in ("向下", "向上"):
        g = sorted(groups[name], key=lambda r: r["date"])
        scaler = mc.fit_scaler([r for r in g if r["date"] < SPLIT])
        pool = [(r, mc.vector(r["context"], scaler)) for r in g]
        preds, rand, actual = [], [], []
        for r, v in pool:
            o = r["outcome"].get("60")
            if r["date"] < SPLIT or not o or o["excess"] is None:
                continue
            known = [(q, w) for q, w in pool if (q["outcome"].get("60") or {}).get("exit_date", "9") < r["date"]
                     and q["outcome"]["60"]["excess"] is not None]
            if len(known) < 200:
                continue
            near = mc.nearest(v, known, 30)
            preds.append(st.mean(q["outcome"]["60"]["excess"] for q, _ in near))
            rand.append(st.mean(q["outcome"]["60"]["excess"] for q, _ in rng.sample(known, 30)))
            actual.append(o["excess"])
        order = sorted(range(len(preds)), key=lambda i: preds[i])
        k = len(order) // 3
        lo, hi = st.mean(actual[i] for i in order[:k]) * 100, st.mean(actual[i] for i in order[-k:]) * 100
        rho, rho_r = mc.spearman(preds, actual), mc.spearman(rand, actual)
        good = rho >= 0.05 and hi - lo > 0
        lines.append(f"| {name} | {len(preds)} | {rho:+.2f} | {hi:+.1f} | {lo:+.1f} | {hi - lo:+.1f} | {rho_r:+.2f} | "
                     f"{'提供了额外信息' if good else '没有'} |")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
