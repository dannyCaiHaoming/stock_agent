"""财报事件 H2a/H2b/H3 检验（严格按 evals/signals/earnings-h2h3-preregistration-2026-10-27.md；确定性计算）。

用法：.venv/bin/python -I scripts/audit-earnings-h2h3.py [--out evals/signals/earnings-h2h3-latest.md]
状态：历史开发数据，不是样本外检验；不含任何未登记的探索。
"""

from __future__ import annotations

import argparse
import bisect
import json
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
FIRST_TEST_YEAR = 2020


def etf_closes(etf: str) -> tuple[list[str], np.ndarray]:
    rows = get_price_history(etf, start="2018-01-01", max_rows=6000)["rows"]
    return [r[0] for r in rows], np.array([float(r[5]) for r in rows])  # 复权收盘


def winsor_stats(pool: np.ndarray) -> tuple[float, float, float]:
    lo, hi = np.percentile(pool, [1, 99])
    return float(lo), float(hi), float(np.clip(pool, lo, hi).mean())


def boot_diff(day: np.ndarray, nb_total: int, val: np.ndarray, plus: list[np.ndarray], minus: list[np.ndarray],
              block: int) -> dict:
    """统计量 = mean(plus 组之和 的均值之差)：sum_k mean(plus_k) - sum_k mean(minus_k)（H3 为两对差之差）。
    plus/minus 为布尔掩码列表；同一次重抽样内计算。"""
    nb = nb_total // block + 1
    cl = day // block
    def stats(mask):
        s = np.bincount(cl[mask], weights=val[mask], minlength=nb)
        c = np.bincount(cl[mask], minlength=nb).astype(float)
        return s, c
    idx = np.random.default_rng(SEED).integers(0, nb, size=(REPS, nb))
    def gm(mask):
        s, c = stats(mask)
        cs = c[idx].sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(cs > 0, s[idx].sum(axis=1) / cs, np.nan), float(val[mask].mean())
    est, d = 0.0, np.zeros(REPS)
    for m in plus:
        g, p = gm(m); d = d + g; est += p
    for m in minus:
        g, p = gm(m); d = d - g; est -= p
    d = d[~np.isnan(d)]
    ds = np.sort(d)
    ci = (float(ds[int(0.025 * len(ds))]), float(ds[int(0.975 * len(ds)) - 1]))
    p = min(1.0, 2 * min(float(np.mean(d <= 0)), float(np.mean(d >= 0))))
    return {"est": est, "ci": ci, "p": p, "valid": len(d)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    t0 = time.time()
    path = settings.cache().root / "derived" / "signals" / "events-pead-v2.jsonl"
    events, ctrl, calendar = [], {}, set()
    for line in path.open():
        r = json.loads(line)
        calendar.add(r["signal_date"])
        if r["kind"] == "control":
            if r.get(H) is not None:
                ctrl.setdefault(r["signal_date"], []).append(r[H])
        else:
            events.append(r)
    cal = sorted(calendar)
    cal_pos = {d: i for i, d in enumerate(cal)}
    pools = {d: np.array(v) for d, v in ctrl.items() if len(v) >= 10}
    pool_sorted = {d: np.sort(v) for d, v in pools.items()}
    wstat = {d: winsor_stats(v) for d, v in pools.items()}

    # 三分位门槛：年份 Y 只用 D0 < Y-01-01 的全部财报事件（不分反应组）
    all_pre = [(e["signal_date"], e["pre_run_60"]) for e in events if e.get("pre_run_60") is not None]
    thr = {}
    for y in range(FIRST_TEST_YEAR, 2027):
        v = np.array([p for d, p in all_pre if d < f"{y}-01-01"])
        thr[y] = (float(np.quantile(v, 1 / 3)), float(np.quantile(v, 2 / 3)), len(v))

    etfs = {}
    excl = {"test_events_2020+": 0, "missing_pre_run_60": 0, "missing_20d": 0, "missing_pool": 0, "missing_etf": 0,
            "not_big_move": 0}
    rows = []
    for e in events:
        if e["signal_date"] < f"{FIRST_TEST_YEAR}-01-01":
            continue
        excl["test_events_2020+"] += 1
        if e["bucket"] not in ("strong_up", "strong_down"):
            excl["not_big_move"] += 1
            continue
        if e.get("pre_run_60") is None:
            excl["missing_pre_run_60"] += 1; continue
        if e.get(H) is None or e.get(f"exit_{H}") is None:
            excl["missing_20d"] += 1; continue
        d0 = e["signal_date"]
        assert e["entry_date"] > d0  # 结果窗口从 D1 开盘开始
        if d0 not in pools:
            excl["missing_pool"] += 1; continue
        if e["benchmark"] not in etfs:
            etfs[e["benchmark"]] = etf_closes(e["benchmark"])
        dates, cl = etfs[e["benchmark"]]
        i = bisect.bisect_right(dates, d0) - 1  # 只用 ≤ D0 的收盘
        if i < 20:
            excl["missing_etf"] += 1; continue
        assert dates[i] <= d0
        env_ret = cl[i] / cl[i - 20] - 1
        y = int(d0[:4]); t1, t2, _ = thr[y]
        tier = "high" if e["pre_run_60"] >= t2 else "low" if e["pre_run_60"] <= t1 else "mid"
        lo, hi, bmean = wstat[d0]
        v = e[H]
        pool = pool_sorted[d0]
        pct = (bisect.bisect_left(pool, v) + bisect.bisect_right(pool, v)) / 2 / len(pool)
        rows.append(dict(year=y, bucket=e["bucket"], tier=tier, up=env_ret > 0, rel=(min(max(v, lo), hi) - bmean) * 100,
                         raw=v * 100, pm=(pct - 0.5) * 100, pmin=e[f"path_min_{H}"] * 100, day=cal_pos[d0]))
    A = {k: np.array([r[k] for r in rows]) for k in ("year", "rel", "raw", "pm", "pmin", "day")}
    A["bucket"] = np.array([r["bucket"] for r in rows]); A["tier"] = np.array([r["tier"] for r in rows])
    A["up"] = np.array([r["up"] for r in rows])
    su, sd = A["bucket"] == "strong_up", A["bucket"] == "strong_down"
    hi_, lo_ = A["tier"] == "high", A["tier"] == "low"
    envu, envd = A["up"], ~A["up"]
    groups = {"大涨·高": su & hi_, "大涨·低": su & lo_, "大跌·高": sd & hi_, "大跌·低": sd & lo_,
              "大涨·高·板块下行": su & hi_ & envd, "大涨·低·板块下行": su & lo_ & envd,
              "大涨·高·板块上行": su & hi_ & envu, "大涨·低·板块上行": su & lo_ & envu}
    tests = {
        "H2a 大涨：高−低": ([groups["大涨·高"]], [groups["大涨·低"]], ["大涨·高", "大涨·低"]),
        "H2b 大跌：高−低": ([groups["大跌·高"]], [groups["大跌·低"]], ["大跌·高", "大跌·低"]),
        "H3 大涨：(下行 高−低)−(上行 高−低)": (
            [groups["大涨·高·板块下行"], groups["大涨·低·板块上行"]],
            [groups["大涨·低·板块下行"], groups["大涨·高·板块上行"]],
            ["大涨·高·板块下行", "大涨·低·板块下行", "大涨·高·板块上行", "大涨·低·板块上行"]),
    }
    res = {}
    for name, (pl, mi, gl) in tests.items():
        ns = {g: int(groups[g].sum()) for g in gl}
        if min(ns.values()) < MIN_N:
            res[name] = {"ns": ns, "insufficient": True}; continue
        r20 = boot_diff(A["day"], len(cal), A["rel"], pl, mi, 20)
        r40 = boot_diff(A["day"], len(cal), A["rel"], pl, mi, 40)
        res[name] = {"ns": ns, "r20": r20, "r40": r40, "insufficient": False}
    # Holm
    live = sorted([(r["r20"]["p"], n) for n, r in res.items() if not r["insufficient"]])
    m = len(tests); run = 0.0
    for k, (p, n) in enumerate(live):
        run = max(run, min(1.0, (m - k) * p)); res[n]["holm"] = run
    for n, r in res.items():
        if r["insufficient"]:
            r["verdict"] = "样本不足（仅报告 n）"; continue
        lo_ci, hi_ci = r["r20"]["ci"]
        if r["holm"] < 0.05:
            r["verdict"] = "有证据（" + ("正向" if r["r20"]["est"] > 0 else "负向") + "）"
        elif lo_ci >= -TRIVIAL_PP and hi_ci <= TRIVIAL_PP:
            r["verdict"] = "效果太小"
        else:
            r["verdict"] = "尚无法确认"

    out = ["# 财报事件 H2／H3 检验结果", "",
           "**状态：历史开发数据。** 2019–2026 年的财报事件此前都已看过，不是样本外检验；严格按 "
           "`evals/signals/earnings-h2h3-preregistration-2026-10-27.md` 执行，未做任何未登记的探索。", "",
           "口径：20 日相对同日基准超额（事件与同 D0 全股票池对照均按该池 1/99 百分位截尾，事件减对照均值），D1 开盘入场；"
           "三分位门槛为逐年向前（D0 早于当年 1 月 1 日的全部财报事件）；板块环境 = 所属板块 ETF 在 D0 收盘相对 20 个交易日前的复权收盘涨跌（>0 为上行）。"
           "CI：按 D0 交易日连续块重抽样（块 20；敏感性块 40），1000 次，种子 0；p 为双侧，Holm 校正 3 个检验；单位百分点。", "",
           "## 一、主要结果（2020 年起合并）", "",
           "| 检验 | 估计 pp | 95% CI 块20 | 95% CI 块40 | 原始 p | Holm p | 结论 |", "|---|---|---|---|---|---|---|"]
    for n, r in res.items():
        if r["insufficient"]:
            out.append(f"| {n} | — | — | — | — | — | {r['verdict']}；n={r['ns']} |")
        else:
            out.append(f"| {n} | {r['r20']['est']:.2f} | ({r['r20']['ci'][0]:.2f}, {r['r20']['ci'][1]:.2f}) | "
                       f"({r['r40']['ci'][0]:.2f}, {r['r40']['ci'][1]:.2f}) | {r['r20']['p']:.3f} | {r['holm']:.3f} | {r['verdict']} |")
    out += ["", "各检验所涉分组 n：", ""]
    for n, r in res.items():
        out.append(f"- {n}：" + "，".join(f"{g} {k}" for g, k in r["ns"].items()))
    out += ["", "## 二、分组描述（不参与判定；h=20）", "",
            "| 分组 | n | 平均相对基准超额 % | 平均百分位−50 | 扣成本后均值超额 % | 路径最低点中位数 % |", "|---|---|---|---|---|---|"]
    for g, mk in groups.items():
        n = int(mk.sum())
        if n < MIN_N:
            out.append(f"| {g} | {n} | — | — | — | — |"); continue
        out.append(f"| {g} | {n} | {A['rel'][mk].mean():.2f} | {A['pm'][mk].mean():.2f} | {A['raw'][mk].mean() - COST_PP:.2f} | "
                   f"{np.median(A['pmin'][mk]):.2f} |")
    out += ["", "## 三、逐年差值（点估计 pp，描述性；任一组 n<5 记 —）", "",
            "| 年 | H2a 差值 (n高/n低) | H2b 差值 (n高/n低) | H3 差值 |", "|---|---|---|---|"]
    def mm(mask):
        return float(A["rel"][mask].mean()) if mask.sum() >= 5 else None
    dir_count = {"H2a": [0, 0], "H2b": [0, 0], "H3": [0, 0]}
    for y in range(FIRST_TEST_YEAR, 2027):
        yy = A["year"] == y
        cells = []
        for key, (a, b) in (("H2a", (groups["大涨·高"], groups["大涨·低"])), ("H2b", (groups["大跌·高"], groups["大跌·低"]))):
            ma, mb = mm(a & yy), mm(b & yy)
            if ma is None or mb is None:
                cells.append(f"— ({int((a & yy).sum())}/{int((b & yy).sum())})")
            else:
                d = ma - mb; dir_count[key][d > 0] += 1
                cells.append(f"{d:.2f} ({int((a & yy).sum())}/{int((b & yy).sum())})")
        c = [mm(groups[k] & yy) for k in ("大涨·高·板块下行", "大涨·低·板块下行", "大涨·高·板块上行", "大涨·低·板块上行")]
        if None in c:
            cells.append("—")
        else:
            d = (c[0] - c[1]) - (c[2] - c[3]); dir_count["H3"][d > 0] += 1; cells.append(f"{d:.2f}")
        out.append(f"| {y} | " + " | ".join(cells) + " |")
    out += ["", "方向计数（负/正的年数）：" + "；".join(f"{k} {v[0]}/{v[1]}" for k, v in dir_count.items()), "",
            "## 四、三分位门槛（pre_run_60，小数）", "", "| 年 | 下三分位 | 上三分位 | 用于计算的事件数 |", "|---|---|---|---|"]
    for y, (a, b, n) in thr.items():
        out.append(f"| {y} | {a:.4f} | {b:.4f} | {n} |")
    out += ["", "## 五、排除统计", "",
            f"- 2020 年起财报事件：{excl['test_events_2020+']}；其中非大涨/大跌（不属本检验）{excl['not_big_move']}。",
            f"- 缺 pre_run_60：{excl['missing_pre_run_60']}；缺 20 日结果：{excl['missing_20d']}；"
            f"缺同日对照池：{excl['missing_pool']}；缺板块 ETF 历史（不足 20 个交易日）：{excl['missing_etf']}。",
            f"- 进入检验的大涨/大跌事件：{len(rows)}（大涨 {int(su.sum())}，大跌 {int(sd.sum())}；中间三分位 {int((A['tier']=='mid').sum())} 个不进入任何比较）。", "",
            "## 六、无前视自检", "",
            "- 三分位门槛只用 D0 早于当年 1 月 1 日的事件。",
            "- 板块环境只用 ETF 日期 ≤ D0 的复权收盘；断言 ETF 取点日期 ≤ D0。",
            "- 结果窗口：断言 entry_date（D1）> D0；收益从 D1 开盘起算（事件文件口径）。",
            f"- p 值精度受重抽样次数限制（1/{REPS}）；运行耗时 {time.time()-t0:.1f}s。", ""]
    text = "\n".join(out)
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
