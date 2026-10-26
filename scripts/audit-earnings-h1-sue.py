"""财报事件 H1（SUE）检验（严格按 evals/signals/earnings-h1-sue-preregistration-2026-10-27.md；确定性计算）。

用法：.venv/bin/python -I scripts/audit-earnings-h1-sue.py [--out evals/signals/earnings-h1-sue-latest.md]
状态：历史开发数据，不是样本外检验；不含任何未登记的探索。
"""

from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import settings  # noqa: E402
from product.mcp.data_tools import get_price_history  # noqa: E402

H = "20"
COST_PP, TRIVIAL_PP, MIN_N, REPS, SEED = 0.2, 0.5, 30, 1000, 0
FIRST_TEST_YEAR, MIN_GROUP, DEN_MIN = 2020, 5, 0.01
BUCKETS = ["strong_down", "down", "flat", "up", "strong_up"]
H2H3_P = {"H2a": 0.142, "H2b": 0.150, "H3": 0.924}


def winsor_stats(pool):
    lo, hi = np.percentile(pool, [1, 99])
    return float(lo), float(hi), float(np.clip(pool, lo, hi).mean())


def etf_closes(etf):
    rows = get_price_history(etf, start="2018-01-01", max_rows=6000)["rows"]
    return [r[0] for r in rows], np.array([float(r[5]) for r in rows])


def days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def build_sue(evid):
    """返回 {accession: dict(sue=..|None, reason=..|None)}；只用 verified 行。"""
    ver = collections.defaultdict(list)
    for r in evid:
        if r["status"] == "verified":
            ver[r["ticker"]].append(r)
    out = {}
    for tk, rows in ver.items():
        rows.sort(key=lambda r: r["fiscal_period_end"])
        for i, r in enumerate(rows):
            if not r.get("chain9_ok"):
                out[r["accession"]] = dict(sue=None, reason="chain9_not_ok"); continue
            if i < 8:
                out[r["accession"]] = dict(sue=None, reason="chain_gap_check_failed"); continue
            win = rows[i - 8:i + 1]
            gaps_ok = all(55 <= days(a["fiscal_period_end"], b["fiscal_period_end"]) <= 125 for a, b in zip(win, win[1:]))
            if not gaps_ok:
                out[r["accession"]] = dict(sue=None, reason="chain_gap_check_failed"); continue
            assert all(w["accepted_ny"] <= r["accepted_ny"] for w in win)  # 无前视：所用公告受理时间均 ≤ 当前事件
            if len({w.get("eps_basis", "as_labelled") for w in win}  # 正文句子行无 eps_basis 字段，按 as_labelled 处理（解释性选择，已在报告说明）
            ) != 1:
                out[r["accession"]] = dict(sue=None, reason="eps_basis_inconsistent"); continue
            d = [w["eps_current"] - w["eps_year_ago"] for w in win]
            den = float(np.std(d[:8], ddof=1))
            if den <= DEN_MIN:
                out[r["accession"]] = dict(sue=None, reason="denominator_le_0.01"); continue
            out[r["accession"]] = dict(sue=d[8] / den, reason=None,
                                       all_table=all((w.get("evidence") or {}).get("kind") != "prose_sentence" for w in win))
    return out


def pooled(sue_tier, strata_key, rel, mask, min_group=MIN_GROUP):
    """层内 高−低；按 2*nh*nl/(nh+nl) 加权合并。返回 (估计, 使用层数, 跳过层数)。"""
    num = den = 0.0; used = skipped = 0
    for k in np.unique(strata_key[mask]):
        m = mask & (strata_key == k)
        h, l = m & (sue_tier == "high"), m & (sue_tier == "low")
        nh, nl = int(h.sum()), int(l.sum())
        if nh < min_group or nl < min_group:
            skipped += 1; continue
        w = 2 * nh * nl / (nh + nl)
        num += w * (rel[h].mean() - rel[l].mean()); den += w; used += 1
    return (num / den if den else None), used, skipped


def boot_pooled(day, nb_total, rel, sue_tier, strata_key, block, mask, fixed_strata):
    nb = nb_total // block + 1
    cl = day // block
    idx = np.random.default_rng(SEED).integers(0, nb, size=(REPS, nb))
    num = np.zeros(REPS); den = np.zeros(REPS)
    for k in fixed_strata:
        m = mask & (strata_key == k)
        parts = []
        for g in ("high", "low"):
            mg = m & (sue_tier == g)
            s = np.bincount(cl[mg], weights=rel[mg], minlength=nb)
            c = np.bincount(cl[mg], minlength=nb).astype(float)
            parts.append((s[idx].sum(1), c[idx].sum(1)))
        (sh, ch), (sl, cl_) = parts
        ok = (ch > 0) & (cl_ > 0)
        with np.errstate(invalid="ignore", divide="ignore"):
            w = 2 * ch * cl_ / (ch + cl_)
            d = sh / ch - sl / cl_
        num += np.where(ok, w * d, 0); den += np.where(ok, w, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        d = num / den
    d = d[den > 0]
    ds = np.sort(d)
    ci = (float(ds[int(0.025 * len(ds))]), float(ds[int(0.975 * len(ds)) - 1]))
    p = min(1.0, 2 * min(float(np.mean(d <= 0)), float(np.mean(d >= 0))))
    return ci, p, len(d)


def read_h2h3_p(path):
    txt = path.read_text()
    got = {}
    for key, pat in (("H2a", r"\| H2a[^|]*\|"), ("H2b", r"\| H2b[^|]*\|"), ("H3", r"\| H3[^|]*\|")):
        line = next(l for l in txt.splitlines() if re.match(pat, l))
        cells = [c.strip() for c in line.strip("|").split("|")]
        got[key] = float(cells[4])
    return got


def holm(ps):
    order = sorted(ps, key=lambda k: ps[k]); m = len(ps); run = 0.0; out = {}
    for i, k in enumerate(order):
        run = max(run, min(1.0, (m - i) * ps[k])); out[k] = run
    return out


def analyse(events, sue_map, ctrl_ctx, label, table_only=False, accession_kind=None):
    pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    t0 = time.time()
    root = settings.cache().root / "derived"
    evid = [json.loads(l) for l in (root / "sue" / "eps-evidence.jsonl").open()]
    by_acc = {r["accession"]: r for r in evid}
    by_tk_sd = {(r["ticker"], r["signal_date"]): r for r in evid}
    sue_map = build_sue(evid)

    events, ctrl, calendar = [], {}, set()
    for line in (root / "signals" / "events-pead-v2.jsonl").open():
        r = json.loads(line)
        calendar.add(r["signal_date"])
        if r["kind"] == "control":
            if r.get(H) is not None:
                ctrl.setdefault(r["signal_date"], []).append(r[H])
        else:
            events.append(r)
    cal = sorted(calendar); cal_pos = {d: i for i, d in enumerate(cal)}
    pools = {d: np.array(v) for d, v in ctrl.items() if len(v) >= 10}
    pool_sorted = {d: np.sort(v) for d, v in pools.items()}
    wstat = {d: winsor_stats(v) for d, v in pools.items()}

    # ---- 连接与排除计数（全部 2019+ 财报事件）----
    join = collections.Counter()
    excl = collections.Counter(); excl_year = collections.defaultdict(collections.Counter)
    excl_etf = collections.defaultdict(collections.Counter)
    elig = []
    for e in events:
        ev = by_acc.get(e["accession"]); how = "accession"
        if ev is None:
            ev = by_tk_sd.get((e["ticker"], e["signal_date"])); how = "ticker+signal_date"
            if ev is None:
                how = None
        join[how or "none"] += 1
        reason = None; s = None
        if ev is None:
            reason = "no_evidence_row"
        elif ev["status"] != "verified":
            reason = "evidence_not_verified:" + ev["status"].split(":")[0]
        else:
            m = sue_map[ev["accession"]]
            reason = m["reason"]; s = m["sue"]; all_table = m.get("all_table")
        if reason is None and e.get("pre_run_60") is None:
            reason = "missing_pre_run_60"
        if reason:
            excl[reason] += 1; excl_year[reason][e["signal_date"][:4]] += 1; excl_etf[reason][e["benchmark"]] += 1
            continue
        kind = "table" if all_table else "prose"  # table = 9 个季度的证据全是表格
        elig.append(dict(e=e, sue=s, how=how, kind=kind, year=int(e["signal_date"][:4]), d0=e["signal_date"]))

    # ---- 逐年向前三分位（SUE 与 pre_run_60，均取自入选事件，D0 < 当年 1 月 1 日）----
    thr = {}
    for y in range(FIRST_TEST_YEAR, 2027):
        pr = [x for x in elig if x["d0"] < f"{y}-01-01"]
        sv = np.array([x["sue"] for x in pr]); pv = np.array([x["e"]["pre_run_60"] for x in pr])
        thr[y] = (np.quantile(sv, 1 / 3), np.quantile(sv, 2 / 3), np.quantile(pv, 1 / 3), np.quantile(pv, 2 / 3), len(pr))

    etfs = {}; pexcl = collections.Counter(); rows = []
    for x in elig:
        e = x["e"]
        if x["year"] < FIRST_TEST_YEAR:
            continue
        pexcl["eligible_2020+"] += 1
        d0 = x["d0"]
        if e.get(H) is None or e.get(f"exit_{H}") is None:
            pexcl["missing_20d"] += 1; continue
        assert e["entry_date"] > d0
        if d0 not in pools:
            pexcl["missing_pool"] += 1; continue
        s1, s2, p1, p2, _ = thr[x["year"]]
        st = "high" if x["sue"] >= s2 else "low" if x["sue"] <= s1 else "mid"
        pt = "high" if e["pre_run_60"] >= p2 else "low" if e["pre_run_60"] <= p1 else "mid"
        pt_i = {"low": 0, "mid": 1, "high": 2}[pt]
        lo, hi, bmean = wstat[d0]
        v = e[H]; pool = pool_sorted[d0]
        pct = (bisect.bisect_left(pool, v) + bisect.bisect_right(pool, v)) / 2 / len(pool)
        rows.append(dict(year=x["year"], bucket=e["bucket"], sue_t=st, pre_t=pt_i, kind=x["kind"], how=x["how"],
                         rel=(min(max(v, lo), hi) - bmean) * 100, pm=(pct - .5) * 100, day=cal_pos[d0],
                         stratum=BUCKETS.index(e["bucket"]) * 3 + pt_i, sue=x["sue"]))
    A = {k: np.array([r[k] for r in rows]) for k in rows[0]}
    n_all = len(rows)
    allm = np.ones(n_all, bool)

    def run_h1(mask):
        est, used, skipped = pooled(A["sue_t"], A["stratum"], A["rel"], mask)
        fixed = [k for k in range(15) if (mask & (A["stratum"] == k) & (A["sue_t"] == "high")).sum() >= MIN_GROUP
                 and (mask & (A["stratum"] == k) & (A["sue_t"] == "low")).sum() >= MIN_GROUP]
        r = dict(est=est, used=used, skipped=skipped)
        if est is None:
            return r
        for b in (20, 40):
            ci, p, valid = boot_pooled(A["day"], len(cal), A["rel"], A["sue_t"], A["stratum"], b, mask, fixed)
            r[f"ci{b}"] = ci; r[f"p{b}"] = p
        return r

    main_r = run_h1(allm)
    tab_r = run_h1(A["kind"] == "table")
    nh = int(((A["sue_t"] == "high")).sum()); nl = int(((A["sue_t"] == "low")).sum())

    h2p = read_h2h3_p(REPO / "evals" / "signals" / "earnings-h2h3-latest.md")
    assert h2p == H2H3_P, h2p
    ps = {"H1": main_r["p20"], **h2p}
    hm = holm(ps)
    lo_ci, hi_ci = main_r["ci20"]
    if min(nh, nl) < MIN_N:
        verdict = "样本不足（仅报告 n）"
    elif hm["H1"] < 0.05:
        verdict = "有证据（" + ("正向" if main_r["est"] > 0 else "负向") + "）"
    elif lo_ci >= -TRIVIAL_PP and hi_ci <= TRIVIAL_PP:
        verdict = "效果太小"
    else:
        verdict = "尚无法确认"

    def f2(x):
        return "—" if x is None else f"{x:.2f}"

    out = ["# 财报事件 H1（SUE）检验结果", "",
           "**状态：历史开发数据。** 2019–2026 年的财报事件此前都已看过，不是样本外检验；严格按 "
           "`evals/signals/earnings-h1-sue-preregistration-2026-10-27.md` 执行，未做任何未登记的探索。", "",
           "口径：20 日相对同日基准超额（v2.1：事件与同 D0 全股票池对照均按该池 1/99 百分位截尾，事件减对照均值），D1 开盘入场；"
           "SUE = ΔEPS_q ÷ 前 8 个季度 ΔEPS 的样本标准差（ddof=1），ΔEPS 取自各季度自己那份公告；SUE 与 pre_run_60 的三分位门槛逐年向前"
           "（只用 D0 早于当年 1 月 1 日的入选事件）；15 层 = 反应 5 组 × pre_run_60 三分位；层内 SUE 高−低，按 2·n高·n低/(n高+n低) 加权合并；"
           "任一组 <5 的层不参与（层集合按原始样本固定，重抽样内某组为空时该层当次跳过）。CI：按 D0 交易日连续块重抽样（块 20；敏感性块 40），1000 次，种子 0；p 双侧；单位百分点。", "",
           "## 一、主要结果（2020 年起合并）", "",
           f"- 进入检验的事件 n = {n_all}（SUE 高三分位 {nh}，低三分位 {nl}，中间 {int((A['sue_t']=='mid').sum())}）。",
           f"- 参与合并的层 {main_r['used']}，因任一组 <5 跳过 {main_r['skipped']}（共 15 层）。", "",
           "| 检验 | 估计 pp | 95% CI 块20 | 95% CI 块40 | 原始 p | Holm p（4 项） | 结论 |", "|---|---|---|---|---|---|---|",
           f"| H1 SUE 高−低（分层合并） | {main_r['est']:.2f} | ({lo_ci:.2f}, {hi_ci:.2f}) | ({main_r['ci40'][0]:.2f}, {main_r['ci40'][1]:.2f}) | "
           f"{main_r['p20']:.3f} | {hm['H1']:.3f} | {verdict} |", "",
           f"块 40 敏感性的原始 p = {main_r['p40']:.3f}。Holm 的 4 个原始 p：H1 {ps['H1']:.3f}，H2a {ps['H2a']:.3f}，H2b {ps['H2b']:.3f}，H3 {ps['H3']:.3f}"
           f"（H2a/H2b/H3 由 `earnings-h2h3-latest.md` 读取并核对）；Holm p：" + "，".join(f"{k} {v:.3f}" for k, v in hm.items()) + "。", "",
           "### 敏感性：只用表格证据", ""]
    nt = int((A["kind"] == "table").sum())
    if tab_r["est"] is None:
        out.append(f"表格证据样本 n={nt}，无可用层。")
    else:
        out.append(f"表格证据样本（9 个季度的证据全为表格）n={nt}（其余含正文句子证据 {n_all-nt}）；估计 {tab_r['est']:.2f} pp，CI 块20 ({tab_r['ci20'][0]:.2f}, {tab_r['ci20'][1]:.2f})，"
                   f"块40 ({tab_r['ci40'][0]:.2f}, {tab_r['ci40'][1]:.2f})，原始 p {tab_r['p20']:.3f}；使用 {tab_r['used']} 层，跳过 {tab_r['skipped']} 层。")
    # 描述
    out += ["", "## 二、描述（不参与判定）", "", "### 1. 未分层 SUE 三分位（相对基准超额均值 / 百分位−50）", "",
            "| SUE 组 | n | 平均相对基准超额 % | 平均百分位−50 |", "|---|---|---|---|"]
    for g in ("low", "mid", "high"):
        m = A["sue_t"] == g
        out.append(f"| {g} | {int(m.sum())} | {A['rel'][m].mean():.2f} | {A['pm'][m].mean():.2f} |")
    h, l = A["sue_t"] == "high", A["sue_t"] == "low"
    out.append(f"\n未分层 高−低：相对基准超额 {A['rel'][h].mean()-A['rel'][l].mean():.2f} pp；百分位−50 {A['pm'][h].mean()-A['pm'][l].mean():.2f}。")
    out += ["", "### 2. 逐年 H1 估计（同一合并规则，层内每组 <5 跳过；点估计 pp）", "",
            "| 年 | n | 使用层 | 跳过层 | H1 估计 pp | 百分位−50 口径（高−低） |", "|---|---|---|---|---|---|"]
    signs = [0, 0]
    for y in range(FIRST_TEST_YEAR, 2027):
        ym = A["year"] == y
        est, used, sk = pooled(A["sue_t"], A["stratum"], A["rel"], ym)
        pm, _, _ = pooled(A["sue_t"], A["stratum"], A["pm"], ym)
        if est is not None:
            signs[int(est > 0)] += 1
        out.append(f"| {y} | {int(ym.sum())} | {used} | {sk} | {f2(est)} | {f2(pm)} |")
    pm_all, _, _ = pooled(A["sue_t"], A["stratum"], A["pm"], allm)
    out += ["", f"逐年方向计数（负/正的年数）：{signs[0]}/{signs[1]}。合并样本的百分位−50 口径分层合并估计：{f2(pm_all)}。", "",
            "### 3. 同样本基准：只按反应分组（同一批入选事件）", "",
            "| 反应组 | n | 平均相对基准超额 % | 平均百分位−50 |", "|---|---|---|---|"]
    for b in BUCKETS:
        m = A["bucket"] == b
        out.append(f"| {b} | {int(m.sum())} | {f2(A['rel'][m].mean()) if m.any() else '—'} | {f2(A['pm'][m].mean()) if m.any() else '—'} |")
    out.append(f"\n全样本平均相对基准超额 {A['rel'].mean():.2f} pp。对照：反应分组内的 SUE 高−低分层合并估计为 {main_r['est']:.2f} pp"
               f"（反应组均值最大差 {max(A['rel'][A['bucket']==b].mean() for b in BUCKETS)-min(A['rel'][A['bucket']==b].mean() for b in BUCKETS):.2f} pp）。")
    out += ["", "### 4. 15 层样本数（SUE 高 / 低）", "", "| 反应组 | pre_run 低 | pre_run 中 | pre_run 高 |", "|---|---|---|---|"]
    for bi, b in enumerate(BUCKETS):
        cells = []
        for t in range(3):
            k = bi * 3 + t
            cells.append(f"{int(((A['stratum']==k)&h).sum())}/{int(((A['stratum']==k)&l).sum())}")
        out.append(f"| {b} | " + " | ".join(cells) + " |")
    # 排除
    out += ["", "## 三、入选与排除", "",
            f"- 财报事件总数（2019–2026，events-pead-v2）：{len(events)}。连接：按 accession {join['accession']}，"
            f"按 ticker+signal_date（accession 未连上后补）{join['ticker+signal_date']}，未连上 {join['none']}。",
            f"- 入选（有 SUE 且有 pre_run_60，含 2019 年用于提供门槛）：{len(elig)}；其中 2020 年起 {pexcl['eligible_2020+']}，"
            f"缺 20 日结果 {pexcl['missing_20d']}，缺同日对照池 {pexcl['missing_pool']}，最终进入检验 {n_all}。",
            f"- 进入检验样本中，通过 ticker+signal_date 连接的 {int((A['how']=='ticker+signal_date').sum())} 个；9 季全为表格证据 {nt}，链中含正文句子证据 {n_all-nt}。正文句子行没有 eps_basis 字段，口径一致性检查中按 as_labelled 处理。", "",
            "排除原因（事件数，2019–2026 全部事件，按第一个触发的原因）：", "",
            "| 原因 | 事件数 | " + " | ".join(str(y) for y in range(2019, 2027)) + " |", "|---|---|" + "---|" * 8]
    for rsn, c in excl.most_common():
        out.append(f"| {rsn} | {c} | " + " | ".join(str(excl_year[rsn][str(y)]) for y in range(2019, 2027)) + " |")
    etf_list = sorted({b for r in excl_etf.values() for b in r})
    out += ["", "按板块 ETF：", "", "| 原因 | " + " | ".join(etf_list) + " |", "|---|" + "---|" * len(etf_list)]
    for rsn, c in excl.most_common():
        out.append(f"| {rsn} | " + " | ".join(str(excl_etf[rsn][b]) for b in etf_list) + " |")
    out += ["", "## 四、三分位门槛", "", "| 年 | SUE 下 | SUE 上 | pre_run_60 下 | pre_run_60 上 | 事件数 |", "|---|---|---|---|---|---|"]
    for y, (a, b, c, d, n) in thr.items():
        out.append(f"| {y} | {a:.3f} | {b:.3f} | {c:.4f} | {d:.4f} | {n} |")
    out += ["", "## 五、无前视自检", "",
            "- 每个事件所用的 9 个季度公告，断言其 EDGAR 受理时间均 ≤ 当前事件的受理时间。",
            "- 季度链：按 fiscal_period_end 排序的已核实季度，且相邻季度间隔 55–125 天（独立复核 chain9_ok，不一致者按 chain_gap_check_failed 排除并计数）。",
            "- SUE、pre_run_60 的三分位门槛只用 D0 早于当年 1 月 1 日的入选事件。",
            "- 断言 entry_date（D1）> D0；收益从 D1 开盘起算。",
            f"- p 值精度受重抽样次数限制（1/{REPS}）；运行耗时 {time.time()-t0:.1f}s。", ""]
    text = "\n".join(out)
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
