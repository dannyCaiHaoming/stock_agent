"""空头拥挤 × 财报催化 S1/S2 检验（严格按 evals/short/preregistration-2026-10-28.md；确定性计算）。

用法：.venv/bin/python -I scripts/audit-short-s1s2.py [--out evals/short/s1s2-latest.md]
状态：历史开发数据，不是样本外检验；不含任何未登记的探索。
"""

from __future__ import annotations

import argparse
import bisect
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import settings  # noqa: E402

_spec = importlib.util.spec_from_file_location("h2h3", REPO / "scripts" / "audit-earnings-h2h3.py")
h2h3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h2h3)  # 复用 winsor_stats / boot_diff / etf_closes（主函数受 __main__ 保护）

H, H5 = "20", "5"
TRIVIAL_PP, MIN_N, REPS = 0.5, 30, h2h3.REPS
FIRST_TEST_YEAR = 2019


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    t0 = time.time()
    root = settings.cache().root / "derived"
    events, ctrl, calendar = [], {}, set()
    for line in (root / "signals" / "events-pead-v2.jsonl").open():
        r = json.loads(line)
        calendar.add(r["signal_date"])
        if r["kind"] == "control":
            for h in (H, H5):
                if r.get(h) is not None:
                    ctrl.setdefault((h, r["signal_date"]), []).append(r[h])
        else:
            events.append(r)
    cal = sorted(calendar)
    cal_pos = {d: i for i, d in enumerate(cal)}
    wstat = {k: h2h3.winsor_stats(np.array(v)) for k, v in ctrl.items() if len(v) >= 10}

    # 交易日历（用于“公布日的下一个交易日”）
    tdays, _ = h2h3.etf_closes("SPY")

    def next_td(d: str) -> str:
        return tdays[bisect.bisect_right(tdays, d)]

    si: dict[str, list[dict]] = {}
    si_rows_2018 = []
    for line in (root / "short" / "si.jsonl").open():
        r = json.loads(line)
        r["usable"] = next_td(r["publication_date"])
        si.setdefault(r["ticker"], []).append(r)
        if r["publication_date"][:4] == "2018":
            si_rows_2018.append(r)
    for t in si:
        si[t].sort(key=lambda r: r["usable"])
    usable_keys = {t: [r["usable"] for r in v] for t, v in si.items()}

    def latest(ticker: str, d0: str):
        v = si.get(ticker)
        if not v:
            return None
        i = bisect.bisect_right(usable_keys[ticker], d0) - 1  # usable_date <= D0
        if i < 0:
            return None
        row = v[i]
        assert row["usable"] <= d0 and row["publication_date"] < d0  # 前视自检
        return row

    excl = {"events_total": len(events), "not_big_move": 0, "no_si_row": 0, "split_flag": 0, "missing_dtc": 0,
            "missing_outcome": 0, "missing_pool": 0, "missing_si_pct(敏感性)": 0}
    # 全部财报事件的 SI 度量（用于逐年门槛）；不分反应组
    info = []
    for e in events:
        d0 = e["signal_date"]
        assert e["entry_date"] > d0
        row = latest(e["ticker"], d0)
        info.append((e, row))
    thr = {}
    for Y in range(FIRST_TEST_YEAR, 2027):
        for key, getv in (("dtc", lambda r: r["days_to_cover"]),
                          ("pct", lambda r: r["si_pct_shares_out"] if (not r["shares_stale"]) else None)):
            if Y == FIRST_TEST_YEAR:  # 2019：财报事件史尚无，用 2018 年（公布日在 2018 年）的 FINRA 行
                rows_ = [r for r in si_rows_2018 if not r.get("split_flag")]
                src = "2018 年 FINRA 行"
            else:
                rows_ = [r for e, r in info if r is not None and e["signal_date"] < f"{Y}-01-01" and not r.get("split_flag")]
                src = "D0<当年1月1日的财报事件"
            v = np.array([getv(r) for r in rows_ if getv(r) is not None], dtype=float)
            thr[(key, Y)] = (float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3)), len(v), src)

    rows = []
    for e, row in info:
        if e["bucket"] not in ("strong_up", "strong_down"):
            excl["not_big_move"] += 1; continue
        d0 = e["signal_date"]
        if row is None:
            excl["no_si_row"] += 1; continue
        if row.get("split_flag"):
            excl["split_flag"] += 1; continue
        if row["days_to_cover"] is None:
            excl["missing_dtc"] += 1; continue
        if e.get(H) is None or e.get(H5) is None:
            excl["missing_outcome"] += 1; continue
        if (H, d0) not in wstat or (H5, d0) not in wstat:
            excl["missing_pool"] += 1; continue
        y = int(d0[:4])
        rel = {}
        for h in (H, H5):
            lo, hi, bm = wstat[(h, d0)]
            rel[h] = (min(max(e[h], lo), hi) - bm) * 100
        t1, t2, _, _ = thr[("dtc", y)]
        dv = row["days_to_cover"]
        tier = "high" if dv >= t2 else "low" if dv <= t1 else "mid"
        pct_tier = None
        if (not row["shares_stale"]) and row["si_pct_shares_out"] is not None:
            p1, p2, _, _ = thr[("pct", y)]
            pv = row["si_pct_shares_out"]
            pct_tier = "high" if pv >= p2 else "low" if pv <= p1 else "mid"
        else:
            excl["missing_si_pct(敏感性)"] += 1
        rows.append(dict(year=y, bucket=e["bucket"], tier=tier, ptier=pct_tier, rel20=rel[H], rel5=rel[H5],
                         day=cal_pos[d0]))
    A = {k: np.array([r[k] for r in rows]) for k in ("year", "rel20", "rel5", "day")}
    for k in ("bucket", "tier"):
        A[k] = np.array([r[k] for r in rows])
    A["ptier"] = np.array([r["ptier"] or "" for r in rows])
    su, sd = A["bucket"] == "strong_up", A["bucket"] == "strong_down"
    G = {}
    for nm, bk in (("S1", su), ("S2", sd)):
        G[nm] = (bk & (A["tier"] == "high"), bk & (A["tier"] == "low"))
    GP = {nm: (bk & (A["ptier"] == "high"), bk & (A["ptier"] == "low")) for nm, bk in (("S1", su), ("S2", sd))}
    names = {"S1": "S1 大涨：高回补天数 − 低", "S2": "S2 大跌：高回补天数 − 低"}

    def run(groups, val, block):
        res = {}
        for k, (hi_m, lo_m) in groups.items():
            ns = {"高": int(hi_m.sum()), "低": int(lo_m.sum())}
            if min(ns.values()) < MIN_N:
                res[k] = {"ns": ns, "insufficient": True}; continue
            res[k] = {"ns": ns, "insufficient": False,
                      "r": h2h3.boot_diff(A["day"], len(cal), val, [hi_m], [lo_m], block)}
        return res

    r20, r40 = run(G, A["rel20"], 20), run(G, A["rel20"], 40)
    live = sorted([(r20[k]["r"]["p"], k) for k in r20 if not r20[k]["insufficient"]])
    m = len(G); runm = 0.0; holm = {}
    for i, (p, k) in enumerate(live):
        runm = max(runm, min(1.0, (m - i) * p)); holm[k] = runm

    def verdict(r, hp):
        if r["insufficient"]:
            return "样本不足（仅报告 n）"
        lo, hi = r["r"]["ci"]
        if hp is not None and hp < 0.05:
            return "有证据（" + ("差值>0" if r["r"]["est"] > 0 else "差值<0") + "）"
        if lo >= -TRIVIAL_PP and hi <= TRIVIAL_PP:
            return "效果太小"
        return "尚无法确认"

    # 敏感性：si_pct 三分位（rel20、块 20，原始 p；不参与 Holm 与结论）
    sens = run(GP, A["rel20"], 20)
    # 描述：5 日
    d5 = run(G, A["rel5"], 20)

    out = ["# 空头拥挤 × 财报催化 S1／S2 检验结果", "",
           "**状态：历史开发数据。** 财报事件 2019–2026 此前都已看过，不是样本外检验；严格按 "
           "`evals/short/preregistration-2026-10-28.md` 执行，未做任何未登记的探索。", "",
           "**局限：FINRA 只提供修订后的版本，无法还原当时首发数字**（约 3.4% 的行曾被修订）；历史 SI 为终值，可能与当时公布值有小幅出入。", "",
           "口径：拥挤度 = 回补天数（days_to_cover，本地重算值）；信号日 D0 取 usable_date ≤ D0 的最新一期，"
           "usable_date = 公布日（结算日后第 7 个交易日）的下一个交易日（交易日历取 SPY 价格日期）。"
           "20 日相对同日基准超额（v2.1：事件与同 D0 对照均按该 D0 对照 1/99 百分位截尾，事件减对照均值），D1 开盘入场；单位百分点。"
           "三分位门槛逐年向前：年份 Y 只用 D0 早于 Y 年 1 月 1 日的全部财报事件（不分反应组）对应的回补天数（2019 年用公布日在 2018 年的 FINRA 行）。"
           "CI：按 D0 连续交易日块重抽样（块 20；敏感性块 40），1000 次，种子 0；双侧 p；Holm 校正 2 个检验；结论门槛 ±0.5pp。", "",
           "## 一、主要结果（2019 年起合并）", "",
           "| 检验 | 估计 pp | 95% CI 块20 | 95% CI 块40 | 原始 p | Holm p | 结论 |", "|---|---|---|---|---|---|---|"]
    for k, nm in names.items():
        r = r20[k]
        if r["insufficient"]:
            out.append(f"| {nm} | — | — | — | — | — | 样本不足；n={r['ns']} |"); continue
        out.append(f"| {nm} | {r['r']['est']:.2f} | ({r['r']['ci'][0]:.2f}, {r['r']['ci'][1]:.2f}) | "
                   f"({r40[k]['r']['ci'][0]:.2f}, {r40[k]['r']['ci'][1]:.2f}) | {r['r']['p']:.3f} | {holm[k]:.3f} | "
                   f"{verdict(r, holm[k])} |")
    out += ["", "各检验分组 n：", ""]
    for k, nm in names.items():
        out.append(f"- {nm}：高 {r20[k]['ns']['高']}，低 {r20[k]['ns']['低']}")
    out += ["", "## 二、分组描述（不参与判定）", "",
            "| 分组 | n | 20 日相对超额均值 % | 5 日相对超额均值 % |", "|---|---|---|---|"]
    for k in ("S1", "S2"):
        for lab, mk in (("高", G[k][0]), ("低", G[k][1])):
            n = int(mk.sum())
            out.append(f"| {k}·{lab} | {n} | {A['rel20'][mk].mean():.2f} | {A['rel5'][mk].mean():.2f} |")
    out += ["", "5 日差值（描述，块 20 CI，不参与判定）：", ""]
    for k, nm in names.items():
        r = d5[k]
        if r["insufficient"]:
            out.append(f"- {nm}：样本不足"); continue
        out.append(f"- {nm}：{r['r']['est']:.2f} pp，95% CI ({r['r']['ci'][0]:.2f}, {r['r']['ci'][1]:.2f})，原始 p {r['r']['p']:.3f}")
    out += ["", "## 三、敏感性：以 si_pct_shares_out 三分位（仅 shares_stale=false 行；20 日、块 20；不参与 Holm 与结论）", "",
            "| 检验 | n高/n低 | 估计 pp | 95% CI | 原始 p |", "|---|---|---|---|---|"]
    for k, nm in names.items():
        nm = nm.replace("回补天数", "SI 占股本比例")
        r = sens[k]
        if r["insufficient"]:
            out.append(f"| {nm} | {r['ns']['高']}/{r['ns']['低']} | — | — | 样本不足 |"); continue
        out.append(f"| {nm} | {r['ns']['高']}/{r['ns']['低']} | {r['r']['est']:.2f} | "
                   f"({r['r']['ci'][0]:.2f}, {r['r']['ci'][1]:.2f}) | {r['r']['p']:.3f} |")
    out += ["", "## 四、逐年差值（点估计 pp，描述性；任一组 n<5 记 —；括号为 n高/n低）", "",
            "| 年 | S1 | S2 |", "|---|---|---|"]
    dc = {"S1": [0, 0], "S2": [0, 0]}
    for y in range(FIRST_TEST_YEAR, 2027):
        yy = A["year"] == y
        cells = []
        for k in ("S1", "S2"):
            a, b = G[k][0] & yy, G[k][1] & yy
            na, nb_ = int(a.sum()), int(b.sum())
            if na < 5 or nb_ < 5:
                cells.append(f"— ({na}/{nb_})"); continue
            d = float(A["rel20"][a].mean() - A["rel20"][b].mean())
            dc[k][d > 0] += 1
            cells.append(f"{d:.2f} ({na}/{nb_})")
        out.append(f"| {y} | " + " | ".join(cells) + " |")
    out += ["", "方向计数（负/正的年数）：" + "；".join(f"{k} {v[0]}/{v[1]}" for k, v in dc.items()), "",
            "## 五、回补天数三分位门槛", "", "| 年 | 下三分位 | 上三分位 | 用于计算的行数 | 来源 |", "|---|---|---|---|---|"]
    for Y in range(FIRST_TEST_YEAR, 2027):
        a, b, n, s = thr[("dtc", Y)]
        out.append(f"| {Y} | {a:.2f} | {b:.2f} | {n} | {s} |")
    out += ["", "## 六、排除统计", "",
            f"- 财报事件总数 {excl['events_total']}；非大涨/大跌（不属本检验）{excl['not_big_move']}。",
            f"- 大涨/大跌事件中排除：无可用空头数据行 {excl['no_si_row']}；拆股期（所用行 split_flag=S）{excl['split_flag']}；"
            f"回补天数缺失 {excl['missing_dtc']}；缺 20 日或 5 日结果 {excl['missing_outcome']}；缺同日对照池 {excl['missing_pool']}。",
            f"- 敏感性中因 shares_stale 或分母缺失而无 si_pct 的进入检验事件：{excl['missing_si_pct(敏感性)']}。",
            f"- 进入检验的大涨/大跌事件：{len(rows)}（大涨 {int(su.sum())}，大跌 {int(sd.sum())}；中间三分位 {int((A['tier']=='mid').sum())} 个不进入比较）。", "",
            "## 七、无前视自检", "",
            "- 断言：所用 SI 行 usable_date ≤ D0 且 publication_date < D0（usable = 公布日的下一个交易日）。",
            "- 三分位门槛只用 D0 早于当年 1 月 1 日的事件（2019 年用公布日在 2018 年的 FINRA 行）。",
            "- 断言 entry_date（D1）> D0；收益自 D1 开盘起算（事件文件口径）。",
            "- 残留：FINRA 数值为修订后终值（见局限）；公布日 2018–2025 由规则推算，未逐期对照官方历史表。",
            f"- p 值精度受重抽样次数限制（1/{REPS}）；运行耗时 {time.time()-t0:.1f}s。", ""]
    text = "\n".join(out)
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
