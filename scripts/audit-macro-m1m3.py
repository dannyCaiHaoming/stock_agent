"""宏观 M1–M3 检验（严格按 evals/macro/preregistration-2026-10-28.md；确定性计算）。

用法：.venv/bin/python -I scripts/audit-macro-m1m3.py [--out evals/macro/m1m3-latest.md]
状态：历史开发数据，不是样本外检验；不含任何未登记的探索。
"""

from __future__ import annotations

import argparse
import json
from datetime import date as _d
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
PANEL = REPO / ".local" / "cache" / "derived" / "macro" / "panel.jsonl"
REPS, SEED, BLOCKS = 1000, 0, (20, 40)
FIRST_TEST_YEAR = 2019
TRIV = {"ret": 0.005, "vol": 0.01}


def load():
    rows = [json.loads(l) for l in PANEL.open()]
    return rows


def col(rows, k):
    return np.array([np.nan if r.get(k) is None else float(r[k]) for r in rows])


def wf_terciles(feat, years, test_years_from=FIRST_TEST_YEAR):
    """逐年门槛：只用面板中年份 < Y 的行的特征分位数。返回 (lo, hi) 数组（每行对应其年份的门槛）。"""
    lo, hi = np.full(len(feat), np.nan), np.full(len(feat), np.nan)
    for y in sorted(set(years)):
        if y < test_years_from:
            continue
        pool = feat[(years < y) & ~np.isnan(feat)]
        if len(pool) < 60:
            continue
        q = np.percentile(pool, [100 / 3, 200 / 3])
        m = years == y
        lo[m], hi[m] = q
    return lo, hi


def trailing_rv20(close):
    lr = np.diff(np.log(close), prepend=np.nan)
    rv = np.full(len(close), np.nan)
    for i in range(20, len(close)):
        rv[i] = np.std(lr[i - 19:i + 1], ddof=1) * np.sqrt(252)  # 仅用 <= t 的 20 个收益
    return rv


def eff_windows(idx):
    n, last = 0, -10**9
    for i in sorted(idx):
        if i - last >= 20:
            n += 1
            last = i
    return n


class Boot:
    """连续交易日块（按面板行序号 // block 分簇）重抽样；每个 stat 在同一次重抽样内计算。"""

    def __init__(self, n_rows, block):
        self.cl = np.arange(n_rows) // block
        self.nb = n_rows // block + 1
        self.idx = np.random.default_rng(SEED).integers(0, self.nb, size=(REPS, self.nb))

    def group(self, mask, val):
        s = np.bincount(self.cl[mask], weights=val[mask], minlength=self.nb)
        c = np.bincount(self.cl[mask], minlength=self.nb).astype(float)
        return s[self.idx].sum(1), c[self.idx].sum(1)

    def mean(self, mask, val):
        s, c = self.group(mask, val)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(c > 0, s / c, np.nan)


def finish(est, d):
    d = d[~np.isnan(d)]
    ds = np.sort(d)
    ci = (float(ds[int(0.025 * len(ds))]), float(ds[int(0.975 * len(ds)) - 1]))
    p = min(1.0, 2 * min(float(np.mean(d <= 0)), float(np.mean(d >= 0))))
    return {"est": est, "ci": ci, "p": p}


def diff_test(boots, A, B, val):
    out = {}
    for b, bt in boots.items():
        out[b] = finish(float(val[A].mean() - val[B].mean()), bt.mean(A, val) - bt.mean(B, val))
    return out


def strat_test(boots, A, B, val, strata):
    """分层差值（A−B），按各层 A、B 样本数的调和平均加权合并；重抽样内用重抽样后的样本数重算权重。"""
    def hm(a, b):
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where((a > 0) & (b > 0), 2 / (1 / a + 1 / b), 0.0)
    ws, ests = [], []
    for S in strata:
        a, b = (A & S), (B & S)
        na, nb_ = a.sum(), b.sum()
        ests.append(float(val[a].mean() - val[b].mean()) if na and nb_ else 0.0)
        ws.append(hm(float(na), float(nb_)))
    est = float(np.dot(ws, ests) / sum(ws))
    out = {}
    for blk, bt in boots.items():
        num, den = np.zeros(REPS), np.zeros(REPS)
        for S in strata:
            sa, ca = bt.group(A & S, val)
            sb, cb = bt.group(B & S, val)
            with np.errstate(invalid="ignore", divide="ignore"):
                dm = sa / ca - sb / cb
                w = np.where((ca > 0) & (cb > 0), 2 / (1 / ca + 1 / cb), 0.0)
            ok = (ca > 0) & (cb > 0)
            num += np.where(ok, w * dm, 0.0)
            den += w
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.where(den > 0, num / den, np.nan)
        out[blk] = finish(est, d)
    return out


def holm(ps):
    order = np.argsort(ps)
    adj, run = [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = run
    return adj


def verdict(hp, ci, kind):
    t = TRIV[kind]
    if hp < 0.05:
        return "有证据"
    if ci[0] >= -t and ci[1] <= t:
        return "效果太小"
    return "尚无法确认"


def fm(x, kind):
    return f"{x * 100:+.2f}pp" if kind == "ret" else f"{x * 100:+.2f} 波动点"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "evals" / "macro" / "m1m3-latest.md"))
    args = ap.parse_args()
    rows = load()
    N = len(rows)
    dates = [r["date"] for r in rows]
    years = np.array([int(d[:4]) for d in dates])
    test = years >= FIRST_TEST_YEAR
    boots = {b: Boot(N, b) for b in BLOCKS}

    # ---- 自检 ----
    chk = []
    obs_ok = all(r[k] is None or r[k] < r["date"] for r in rows for k in ("dfii10_obs", "t10yie_obs", "dgs2_obs", "dgs10_obs"))
    chk.append(f"FRED 观测日全部严格早于面板日期（t 当日不使用）：{obs_ok}")
    nf_ok = all(r["nfci_known"] <= r["date"] for r in rows)
    chk.append(f"NFCI 已知日 <= 面板日期（本检验未使用 NFCI）：{nf_ok}")
    qc, sc = col(rows, "qqq_close"), col(rows, "spy_close")
    r20 = np.full(N, np.nan); r20[20:] = sc[20:] / sc[:-20] - 1
    chk.append(f"spy_ret20 与收盘价重算的最大绝对差（价格列可能为未复权收盘而 ret 为复权口径，分红造成差异；仅作大致一致性检查）：{np.nanmax(np.abs(r20 - col(rows, 'spy_ret20'))):.4f}")
    f20 = col(rows, "tgt_spy_fwd20")
    impl = np.full(N, np.nan)
    for i in range(N - 20):
        if not np.isnan(f20[i]):
            impl[i] = sc[i + 20] / (1 + f20[i])  # 隐含的 t+1 开盘价
    gap = np.nanmean(np.abs(impl[:-20] / sc[1:N - 19] - 1))
    chk.append(f"tgt_spy_fwd20 隐含的 t+1 开盘价与 t+1 收盘的平均相对偏离 {gap:.4f}（接近 t+1 价格，而非 t 收盘，说明目标从 t+1 起算）")
    chk.append(f"末尾 20 行目标为空：{all(rows[i]['tgt_spy_fwd20'] is None for i in range(N - 20, N))}")
    trv = trailing_rv20(qc)
    chk.append("M2 当期波动 = 以 qqq_close 计 t-19..t 共 20 个对数收益的年化标准差（仅 <= t）；三分位门槛逐年只用此前年份的行")
    chk.append("三分位门槛逐年计算：年份 Y 只用年份 < Y 的行；2018 年无门槛、不进入检验")

    rel20 = col(rows, "tgt_qqq_fwd20") - col(rows, "tgt_spy_fwd20")
    rel5 = col(rows, "tgt_qqq_fwd5") - col(rows, "tgt_spy_fwd5")

    res, notes = {}, []
    # ---- M1 ----
    f = col(rows, "dfii10_chg20")
    lo, hi = wf_terciles(f, years)
    ok = test & ~np.isnan(rel20) & ~np.isnan(lo)
    top, bot = ok & (f >= hi), ok & (f <= lo)
    m1 = diff_test(boots, top, bot, np.nan_to_num(rel20))
    m1_5 = diff_test(boots, top & ~np.isnan(rel5), bot & ~np.isnan(rel5), np.nan_to_num(rel5))
    res["M1"] = dict(r=m1, kind="ret", gA=top, gB=bot, unc=float(np.nanmean(rel20[ok])), uncall=float(np.nanmean(rel20)),
                     la="DFII10 20 日变化最高三分位", lb="最低三分位", tgt="QQQ−SPY 之后 20 日相对收益")

    # ---- M2 ----
    vv = col(rows, "vix_vix3m")
    rv = col(rows, "tgt_qqq_rv20"); mdd = col(rows, "tgt_qqq_mdd20")
    lo2, hi2 = wf_terciles(trv, years)
    ok2 = test & ~np.isnan(rv) & ~np.isnan(lo2)
    A2, B2 = ok2 & (vv > 1), ok2 & (vv <= 1)
    strata = [ok2 & (trv <= lo2), ok2 & (trv > lo2) & (trv < hi2), ok2 & (trv >= hi2)]
    rvz, mddz = np.nan_to_num(rv), np.nan_to_num(mdd)
    m2 = strat_test(boots, A2, B2, rvz, strata)
    m2_mdd = strat_test(boots, A2, B2, mddz, strata)
    f5 = col(rows, "tgt_qqq_fwd5")
    res["M2"] = dict(r=m2, kind="vol", gA=A2, gB=B2, unc=float(np.nanmean(rv[ok2])), uncall=float(np.nanmean(rv)),
                     la="VIX/VIX3M > 1", lb="VIX/VIX3M <= 1", tgt="QQQ 之后 20 日实际波动率（分层合并）")
    strat_tab = []
    for k, S in enumerate(strata):
        a, b = A2 & S, B2 & S
        strat_tab.append((k, int(a.sum()), int(b.sum()),
                          float(rv[a].mean()) if a.any() else float("nan"), float(rv[b].mean()) if b.any() else float("nan")))
    # 未分层的原始差（仅描述）
    m2_raw = diff_test(boots, A2, B2, rvz)

    # ---- M3 ----
    f3 = col(rows, "hyg_ief_chg20")
    lo3, _ = wf_terciles(f3, years)
    rr, sh = col(rows, "rsp_spy_rel20"), col(rows, "sector_above50_share_chg20")
    spy20, spy5, spymdd = col(rows, "tgt_spy_fwd20"), col(rows, "tgt_spy_fwd5"), col(rows, "tgt_spy_mdd20")
    ok3 = test & ~np.isnan(spy20) & ~np.isnan(lo3) & (f3 <= lo3) & ~np.isnan(sh)
    A3, B3 = ok3 & (rr > 0) & (sh > 0), ok3 & (rr <= 0) & (sh <= 0)
    m3 = diff_test(boots, A3, B3, np.nan_to_num(spy20))
    res["M3"] = dict(r=m3, kind="ret", gA=A3, gB=B3, unc=float(np.nanmean(spy20[ok3])), uncall=float(np.nanmean(spy20)),
                     la="压力上升且宽度改善", lb="压力上升且宽度恶化", tgt="SPY 之后 20 日收益")
    mixed3 = int((ok3 & ~A3 & ~B3).sum())

    names = ["M1", "M2", "M3"]
    ps = [res[n]["r"][20]["p"] for n in names]
    hp = holm(ps)
    for n, h in zip(names, hp):
        res[n]["holm"] = h
        res[n]["verdict"] = verdict(h, res[n]["r"][20]["ci"], res[n]["kind"])

    # 描述
    d_m3_5 = diff_test(boots, A3 & ~np.isnan(spy5), B3 & ~np.isnan(spy5), np.nan_to_num(spy5))
    d_m3_mdd = diff_test(boots, A3, B3, np.nan_to_num(spymdd))
    d_m2_5 = strat_test(boots, A2 & ~np.isnan(f5), B2 & ~np.isnan(f5), np.nan_to_num(f5), [s & ~np.isnan(f5) for s in strata])

    # HY OAS 旁证
    hy = col(rows, "hy_oas"); hy20 = col(rows, "hy_oas_chg20")
    sub = np.array([d >= "2023-10-27" for d in dates])
    hyl = []
    for nm, g in (("改善", A3), ("恶化", B3)):
        m = g & sub & ~np.isnan(hy20)
        hyl.append((nm, int(g.sum() and (g & sub).sum()), int(m.sum()), float(hy[m].mean()) if m.any() else float("nan"),
                    float(hy20[m].mean()) if m.any() else float("nan"), float(np.nanmean(spy20[g & sub])) if (g & sub).any() else float("nan")))

    def pf(p):
        return f"{p:.3f}" if p > 0 else f"<{2 / REPS:.3f}（重抽样中无反向样本）"

    def ci_s(x, k):
        return f"[{fm(x[0], k)}, {fm(x[1], k)}]"

    L = []
    L += ["# 宏观 M1–M3 检验结果（按 preregistration-2026-10-28.md 执行）", "",
          "状态：**历史开发数据，不是样本外检验；不含任何未登记的探索。** 数据为 `.local/cache/derived/macro/panel.jsonl`（"
          f"{N} 行，{dates[0]} 至 {dates[-1]}），检验期 {FIRST_TEST_YEAR}-01 起；运行脚本 `scripts/audit-macro-m1m3.py`。", "",
          f"口径：逐年三分位门槛（年份 Y 只用此前年份的行）；连续交易日块重抽样，块长 20（判定用），40（敏感性）；{REPS} 次，种子 {SEED}；双侧 p；"
          "组间差值在同一次重抽样内计算；Holm 在 M1–M3 三个检验间。", "",
          "## 汇总", "",
          "| 检验 | 估计 | 95% CI（块 20） | 95% CI（块 40） | 原始 p（20/40） | Holm p | 结论 | 全样本无条件均值 |",
          "|---|---|---|---|---|---|---|---|"]
    for n in names:
        r = res[n]; k = r["kind"]
        L.append(f"| {n} {r['tgt']}：{r['la']} − {r['lb']} | {fm(r['r'][20]['est'], k)} | {ci_s(r['r'][20]['ci'], k)} | {ci_s(r['r'][40]['ci'], k)} | "
                 f"{pf(r['r'][20]['p'])} / {pf(r['r'][40]['p'])} | {pf(r['holm'])} | **{r['verdict']}** | "
                 f"检验期 {r['unc'] * 100:.2f}%（{FIRST_TEST_YEAR}+ 同条件行），全面板 {r['uncall'] * 100:.2f}% |")
    L += ["", "“效果太小”区间：收益 ±0.5pp，波动率 ±1 个年化点；用块 20 的 CI 判定。无条件均值为目标本身的均值（M3 为压力上升日子内的均值），不是差值。", "",
          "## 样本量与有效窗口", "",
          "日度行高度重叠（20 日目标），行数不等于独立样本；“不重叠窗口”= 按时间顺序贪心取间隔 >= 20 个交易日的行数。", "",
          "| 检验 | 组 | 行数 | 不重叠 20 日窗口 |", "|---|---|---|---|"]
    for n in names:
        r = res[n]
        for lab, g in ((r["la"], r["gA"]), (r["lb"], r["gB"])):
            L.append(f"| {n} | {lab} | {int(g.sum())} | {eff_windows(np.where(g)[0])} |")
    L.append(f"| M3 | （压力上升中被排除的宽度混合日） | {mixed3} | - |")
    L += ["", "M2 分层明细（当期实际波动三分位内，门槛逐年滚动）：", "",
          "| 层 | n(>1) | n(<=1) | 均值rv(>1) | 均值rv(<=1) |", "|---|---|---|---|---|"]
    for k, na, nb_, ma, mb in strat_tab:
        L.append(f"| {['低', '中', '高'][k]} | {na} | {nb_} | {ma * 100:.2f}% | {mb * 100:.2f}% |")
    L += [f"| （未分层原始差，仅描述） | {int(A2.sum())} | {int(B2.sum())} | 差 {fm(m2_raw[20]['est'], 'vol')} | CI {ci_s(m2_raw[20]['ci'], 'vol')} |", ""]
    L += ["## 描述性结果（不参与判定）", "",
          "| 项目 | 估计 | 95% CI（块 20） | 95% CI（块 40） |", "|---|---|---|---|"]
    for lab, r_, k in (("M1 5 日 QQQ−SPY 相对收益", m1_5, "ret"), ("M2 5 日 QQQ 收益（分层）", d_m2_5, "ret"),
                       ("M2 之后 20 日最大回撤 QQQ（分层，负数越小越深）", m2_mdd, "ret"),
                       ("M3 5 日 SPY 收益", d_m3_5, "ret"), ("M3 之后 20 日最大回撤 SPY", d_m3_mdd, "ret")):
        L.append(f"| {lab} | {fm(r_[20]['est'], k)} | {ci_s(r_[20]['ci'], k)} | {ci_s(r_[40]['ci'], k)} |")
    L += ["", "## M3 子样本旁证：ICE 高收益利差（2023-10-27 起，仅描述，不参与判定）", "",
          "| 组 | 2023-10 后行数 | 有利差变化数据行数 | 平均 HY OAS（%） | 平均 20 日 OAS 变化 | 之后 20 日 SPY 平均收益 |", "|---|---|---|---|---|---|"]
    for nm, a, m, h_, c_, sp in hyl:
        L.append(f"| 宽度{nm} | {a} | {m} | {h_:.2f} | {c_:+.3f} | {sp * 100:+.2f}% |")
    L += ["", "## 自检（无前视）", ""] + [f"- {c}" for c in chk]
    L += ["", "## 解读限制", "",
          "- 日度行重叠，p 值和 CI 已用块重抽样处理，但有效样本仍只有上表的不重叠窗口数，独立压力事件只有少数几次。",
          "- 三个检验的结论只对应登记的特征、门槛、持有期和目标资产，未做任何事后组合。"]
    Path(args.out).write_text("\n".join(L) + "\n")
    for n in names:
        r = res[n]
        print(n, r["r"][20], r["r"][40]["ci"], r["r"][40]["p"], r["holm"], r["verdict"])
    print("\n".join(chk))


main()
