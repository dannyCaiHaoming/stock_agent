"""组合信号检验（按 evals/signals/combo-preregistration-2026-10-26.md 事先登记的定义执行，确定性计算）。

用法：.venv/bin/python -I scripts/audit-combo-stats.py [--as-of YYYY-MM-DD] [--out evals/signals/combo-latest.md]
面板 = events-pead.jsonl 的对照行（股票 × 交易日）；同日横截面中位秩百分位，ab = 百分位 − 0.5。
只统计该持有期结果日 < as_of 的样本。置信区间：按股票、按月份整群自助抽样（1000 次，seed 0）；
组间差值用同一次重抽样的配对差。
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import settings  # noqa: E402

HORIZONS = ("5", "20", "60")
REPS = 1000
GROUPS = ("0", "1", "2", "3+")
BULL = {"revenue_growth_acceleration": 63, "operating_margin_expansion": 63}
BEAR = {"revenue_growth_deceleration": 63, "operating_margin_contraction": 63}


def boot_means(cid: np.ndarray, vals: np.ndarray, mask_a: np.ndarray, mask_b: np.ndarray | None):
    """cid: 整数簇编号；返回 (a 组均值估计, b 组均值估计, 差值) 的重抽样数组。"""
    k = int(cid.max()) + 1
    out = []
    for m in (mask_a, mask_b):
        if m is None:
            out.append(None)
            continue
        s = np.bincount(cid[m], weights=vals[m], minlength=k)
        c = np.bincount(cid[m], minlength=k).astype(float)
        out.append((s, c))
    rng = np.random.default_rng(0)
    draws = rng.integers(0, k, size=(REPS, k))
    res = []
    for sc in out:
        if sc is None:
            res.append(None)
            continue
        s, c = sc
        ss, cc = s[draws].sum(1), c[draws].sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            res.append(ss / cc)
    return res


def ci_of(x: np.ndarray):
    x = x[~np.isnan(x)]
    if len(x) < 100:
        return None
    return float(np.percentile(x, 2.5)) * 100, float(np.percentile(x, 97.5)) * 100


def fmt(c):
    return "n/a" if c is None else f"[{c[0]:.2f}, {c[1]:.2f}]"


def group_table(title, rows_ab, rows_x, gidx, tick, month, labels):
    """rows_*: numpy 数组；gidx: 组下标。返回表格行与各组均值。"""
    out = [f"### {title}", "", "| 分组 | n | 上涨概率 | 中位超额 | 平均百分位−50 | 95% CI（按股票） | 95% CI（按月份） |", "|---|---|---|---|---|---|---|"]
    means = []
    for gi, lab in enumerate(labels):
        m = gidx == gi
        n = int(m.sum())
        if n < 30:
            out.append(f"| {lab} | {n} | | | | | |")
            means.append(None)
            continue
        cis = []
        for cid in (tick, month):
            ba, _ = boot_means(cid, rows_ab, m, None)
            cis.append(ci_of(ba))
        means.append(float(rows_ab[m].mean()))
        out.append(f"| {lab} | {n} | {(rows_x[m] > 0).mean():.3f} | {np.median(rows_x[m]) * 100:.2f}% | "
                   f"{rows_ab[m].mean() * 100:.2f} | {fmt(cis[0])} | {fmt(cis[1])} |")
    return out + [""], means


def diff_line(ab, ma, mb, tick, month, name):
    """a 组减 b 组差值及配对自助 CI。"""
    if ma.sum() < 30 or mb.sum() < 30:
        return f"| {name} | {int(ma.sum())} / {int(mb.sum())} | 样本不足 | | |", None
    d = (ab[ma].mean() - ab[mb].mean()) * 100
    cis = []
    for cid in (tick, month):
        a, b = boot_means(cid, ab, ma, mb)
        cis.append(ci_of(a - b))
    return (f"| {name} | {int(ma.sum())} / {int(mb.sum())} | {d:.2f} | {fmt(cis[0])} | {fmt(cis[1])} |"), (d, cis)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default="9999-12-31")
    parser.add_argument("--out")
    args = parser.parse_args()
    base = settings.cache().root / "derived" / "signals"
    ctrl, events = [], []
    for line in (base / "events-pead.jsonl").open():
        r = json.loads(line)
        (ctrl if r["kind"] == "control" else events).append(r)
    # 每只股票的有序交易日（来自对照行）
    tdates: dict[str, list[str]] = defaultdict(list)
    for r in ctrl:
        tdates[r["ticker"]].append(r["entry_date"])
    for t in tdates:
        tdates[t].sort()
    # 事件入场日 → 该股票交易日序号
    ev: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))

    def pos(t, d):
        return bisect.bisect_left(tdates[t], d)

    for r in events:
        if r["ticker"] in tdates and r["bucket"] in ("strong_up", "strong_down"):
            ev[r["ticker"]]["pead_" + r["bucket"]].append(pos(r["ticker"], r["entry_date"]))
    for line in (base / "events.jsonl").open():
        r = json.loads(line)
        if r["ticker"] in tdates and r["signal"] in {*BULL, *BEAR}:
            ev[r["ticker"]][r["signal"]].append(pos(r["ticker"], r["entry_date"]))
    for t in ev:
        for k in ev[t]:
            ev[t][k].sort()

    def recent(t, key, i, n):
        lst = ev[t].get(key)
        if not lst:
            return False
        j = bisect.bisect_right(lst, i) - 1  # 不晚于当日的最近事件
        return j >= 0 and i - lst[j] < n

    # 面板：每行的看多/看空计数
    P_t, P_d, P_bull, P_bear = [], [], [], []
    idx_of = {}
    for r in ctrl:
        t, d = r["ticker"], r["entry_date"]
        i = pos(t, d)
        bull = (r["stage"] == "stage2") + recent(t, "pead_strong_up", i, 20) + \
            recent(t, "revenue_growth_acceleration", i, 63) + recent(t, "operating_margin_expansion", i, 63)
        bear = (r["stage"] == "stage4") + recent(t, "pead_strong_down", i, 20) + \
            recent(t, "revenue_growth_deceleration", i, 63) + recent(t, "operating_margin_contraction", i, 63)
        P_bull.append(bull)
        P_bear.append(bear)
    P_bull, P_bear = np.array(P_bull), np.array(P_bear)
    P_tick = np.array([r["ticker"] for r in ctrl])
    P_date = np.array([r["entry_date"] for r in ctrl])
    P_month = np.array([r["entry_date"][:7] for r in ctrl])

    def pct_rank(h):
        """控制行 h 日超额的同日中位秩百分位；返回 (有效掩码, 值, 百分位)。"""
        x = np.array([np.nan if (r.get(h) is None or r.get(f"exit_{h}", "9999") >= args.as_of) else r[h] for r in ctrl])
        ok = ~np.isnan(x)
        pools = {}
        order = np.argsort(P_date, kind="stable")
        sd = P_date[order]
        bounds = np.flatnonzero(np.r_[True, sd[1:] != sd[:-1], True])
        pct = np.full(len(x), np.nan)
        for a, b in zip(bounds[:-1], bounds[1:]):
            ids = order[a:b]
            ids = ids[ok[ids]]
            if len(ids) < 10:
                continue
            pool = np.sort(x[ids])
            pools[sd[a]] = pool
            pct[ids] = (np.searchsorted(pool, x[ids], "left") + np.searchsorted(pool, x[ids], "right")) / 2 / len(pool)
        return x, pct, pools

    def codes(arr):
        return np.unique(arr, return_inverse=True)[1]

    tick_c, month_c = codes(P_tick), codes(P_month)
    lines = ["# 组合信号检验（事先登记版）", "",
             f"as_of {args.as_of if args.as_of != '9999-12-31' else '最新'}；定义见 `combo-preregistration-2026-10-26.md`，本文未做任何调整。",
             f"面板 {len(ctrl)} 行（股票 × 交易日），PEAD 事件 {len(events)} 个。百分位为同日全股票池（≥10）中位秩，ab = 百分位 − 0.5。", ""]
    verdicts, body = {}, []
    for h in HORIZONS:
        x, pct, pools = pct_rank(h)
        ok = ~np.isnan(pct)
        ab = pct - 0.5
        for name, cnt, sign in (("H1 看多叠加", P_bull, +1), ("H2 看空叠加", P_bear, -1)):
            g = np.minimum(cnt, 3)
            sel = ok
            t, tab_means = group_table(f"{name}，持有 {h} 日（分组 = 条件计数 0/1/2/3+）", ab[sel], x[sel], g[sel],
                                       tick_c[sel], month_c[sel], GROUPS)
            body += t
            m3, m0 = sel & (g == 3), sel & (g == 0)
            row, res = diff_line(ab, m3, m0, tick_c, month_c, f"{name}：3+ 组 − 0 组（{h} 日）")
            body += ["| 比较 | n（3+ / 0） | 差值（百分位点） | 95% CI（按股票） | 95% CI（按月份） |", "|---|---|---|---|---|", row, ""]
            if h == "20":
                mono = None
                vals = [m for m in tab_means]
                if all(v is not None for v in vals):
                    mono = all((b - a) * sign >= 0 for a, b in zip(vals, vals[1:]))
                good = bool(res and sign * res[0] > 0 and all(c and (c[0] > 0 if sign > 0 else c[1] < 0) for c in res[1]))
                verdicts[name[:2]] = (good and bool(mono), res, vals, mono)
        # H3
        sub = [e for e in events if e["bucket"] in ("strong_up", "strong_down") and (e.get("volume_ratio") or 0) >= 2
               and e.get(h) is not None and e.get(f"exit_{h}", "9999") < args.as_of and e["entry_date"] in pools]
        for name, bucket, st, sign in (("H3a 大涨放量：stage2 − 非 stage2", "strong_up", "stage2", +1),
                                       ("H3b 大跌放量：stage4 − 非 stage4", "strong_down", "stage4", -1)):
            rs = [e for e in sub if e["bucket"] == bucket]
            pool_pct = np.array([(bisect.bisect_left(pools[e["entry_date"]], e[h]) + bisect.bisect_right(pools[e["entry_date"]], e[h])) / 2
                                 / len(pools[e["entry_date"]]) - 0.5 for e in rs])
            xs = np.array([e[h] for e in rs])
            ingrp = np.array([e["stage"] == st for e in rs])
            tc, mc = codes(np.array([e["ticker"] for e in rs])), codes(np.array([e["entry_date"][:7] for e in rs]))
            t, _ = group_table(f"{name[:3]} 子组，持有 {h} 日", pool_pct, xs, np.where(ingrp, 0, 1), tc, mc, (f"{st}", f"非 {st}"))
            row, res = diff_line(pool_pct, ingrp, ~ingrp, tc, mc, f"{name}（{h} 日）")
            body += t + ["| 比较 | n（组 / 对照） | 差值（百分位点） | 95% CI（按股票） | 95% CI（按月份） |", "|---|---|---|---|---|", row, ""]
            if h == "20":
                good = bool(res and all(c and (c[0] > 0 if sign > 0 else c[1] < 0) for c in res[1]) and sign * res[0] > 0)
                verdicts[name[:3]] = (good, res, None, None)
    lines += ["## 结论", "", "20 日为主要持有期；判定规则：两种 CI 都不含 0 且方向与预期一致（H1/H2 另需各组均值单调）；样本 < 30 不下结论。", "",
              "| 检验 | 判定 | 差值（百分位点） | CI（按股票） | CI（按月份） | 单调 |", "|---|---|---|---|---|---|"]
    for k in ("H1", "H2", "H3a", "H3b"):
        good, res, vals, mono = verdicts[k]
        lines.append(f"| {k} | {'成立' if good else '不成立'} | {res[0]:.2f} | {fmt(res[1][0])} | {fmt(res[1][1])} | "
                     f"{'-' if mono is None else ('是' if mono else '否')} |" if res else f"| {k} | 不成立（样本不足） | | | | |")
    lines += ["", "多重检验说明：共 4 个主要检验，每个检验各用两种 95% CI（需同时通过），未做 Bonferroni 校正；"
              "若按 4 个检验校正（每个约 98.75% 水平），边缘通过的结论应降级为“需要验证”。5/60 日与各中间组仅作描述。",
              "同一股票相邻交易日的重叠窗口高度相关，已用按股票整群抽样处理；按月份抽样处理共同的市场环境。", "",
              "## 明细", ""] + body
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
