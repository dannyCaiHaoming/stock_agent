"""财报后漂移统计 v2（口径见 evals/signals/pead-v2-definition-2026-10-26.md；确定性计算）。

用法：.venv/bin/python -I scripts/audit-pead-stats-v2.py [--as-of YYYY-MM-DD] [--out evals/signals/pead-v2-latest.md]
- 百分位：事件与同一 D0 的全股票池（或同阶段）对照行比较，取中间名次百分位。只统计退出日早于 as_of 的样本。
- 主要置信区间：按交易日期连续块（块长 = h 个交易日，不重叠切分）重抽样，块内所有事件一起保留；1000 次，种子 0。
  敏感性：块长 2h；辅助：按股票整群。统计量为事件加权均值（块内求和再相除）。
- v2.1：主要指标 = 相对基准超额 = 事件超额 − 同一 D0 对照池均值超额（两者按该池第 1/99 百分位截尾；全股票池分组用全池，阶段分组用同阶段池，与百分位对照一致）。结论依据其主要 CI：完全在 ±0.5pp 内 = 效果太小（优先）；否则不含 0 为正 = 有增益证据、为负 = 有负向证据；其余尚无法确认。'v2 首轮结论' 为原始均值超额 CI 的旧判断。
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import settings  # noqa: E402

HORIZONS = ("5", "20", "60")
BUCKETS = ("strong_up", "up", "flat", "down", "strong_down")
LABEL = {"strong_up": "大涨 >+5%", "up": "小涨 +2～+5%", "flat": "持平 ±2%", "down": "小跌 −5～−2%",
         "strong_down": "大跌 <−5%"}
COST_PP = 0.2
TRIVIAL_PP = 0.5
MIN_N = 30
REPS = 1000


def boot(cluster: np.ndarray, n_clusters: int, values: np.ndarray, seed: int = 0) -> tuple[float, float] | None:
    """95% CI (in the values' units) of the event-weighted mean when whole clusters are resampled."""
    if n_clusters < 5:
        return None
    sums = np.bincount(cluster, weights=values, minlength=n_clusters)
    cnts = np.bincount(cluster, minlength=n_clusters).astype(float)
    idx = np.random.default_rng(seed).integers(0, n_clusters, size=(REPS, n_clusters))
    tot = cnts[idx].sum(axis=1)
    ok = tot > 0
    means = np.sort(sums[idx].sum(axis=1)[ok] / tot[ok])
    return float(means[int(0.025 * len(means))]), float(means[int(0.975 * len(means)) - 1])


_BASE: dict[int, tuple[float, float, float]] = {}


def base_stats(pool: list[float]) -> tuple[float, float, float]:
    """(1st pct, 99th pct, mean of the winsorized pool) of a control pool, cached by identity."""
    k = id(pool)
    if k not in _BASE:
        a = np.array(pool)
        lo, hi = np.percentile(a, [1, 99])
        _BASE[k] = (float(lo), float(hi), float(np.clip(a, lo, hi).mean()))
    return _BASE[k]


def fmt(ci: tuple[float, float] | None) -> str:
    return "—" if ci is None else f"({ci[0]:.2f}, {ci[1]:.2f})"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default="9999-12-31")
    parser.add_argument("--out")
    args = parser.parse_args()
    path = settings.cache().root / "derived" / "signals" / "events-pead-v2.jsonl"
    events, ctrl_all, ctrl_stage, calendar = [], {}, {}, set()
    for line in path.open():
        r = json.loads(line)
        if r["kind"] == "control":
            calendar.add(r["signal_date"])
            for h in HORIZONS:
                if r.get(h) is not None and r[f"exit_{h}"] < args.as_of:
                    ctrl_all.setdefault((h, r["signal_date"]), []).append(r[h])
                    ctrl_stage.setdefault((h, r["signal_date"], r["stage"]), []).append(r[h])
        else:
            events.append(r)
            calendar.add(r["signal_date"])
    sorted_all = {k: sorted(v) for k, v in ctrl_all.items() if len(v) >= 10}
    sorted_stage = {k: sorted(v) for k, v in ctrl_stage.items() if len(v) >= 5}
    cal = sorted(calendar)
    cal_pos = {d: i for i, d in enumerate(cal)}

    def table(title: str, select, groups: list[tuple[str, str]], against: str) -> list[str]:
        out = [f"### {title}", "",
               "| 分组 | 持有日 | n | 上涨概率 | 平均百分位−50 | 均值超额 % | 中位超额 % | 扣成本后均值 % | 第10百分位 % | "
               "路径最低点中位数 % | 相对基准超额均值 % | 主要 CI 相对基准（块 h） | 主要 CI 百分位−50（块 h） | "
               "敏感 CI 相对基准（块 2h） | 按股票 CI 相对基准 | 结论（v2.1） | v2 首轮结论（原始均值 CI） |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for gname, glabel in groups:
            for h in HORIZONS:
                x, pm, mn, day, tick, rel = [], [], [], [], [], []
                for e in events:
                    if not select(e, gname) or e.get(h) is None or e[f"exit_{h}"] >= args.as_of:
                        continue
                    pool = sorted_all.get((h, e["signal_date"])) if against == "all" else \
                        sorted_stage.get((h, e["signal_date"], e["stage"]))
                    if not pool:
                        continue
                    v = e[h]
                    pct = (bisect.bisect_left(pool, v) + bisect.bisect_right(pool, v)) / 2 / len(pool)
                    lo, hi, bmean = base_stats(pool)
                    rel.append((min(max(v, lo), hi) - bmean) * 100)
                    x.append(v * 100)
                    pm.append((pct - 0.5) * 100)
                    mn.append(e[f"path_min_{h}"] * 100)
                    day.append(cal_pos[e["signal_date"]])
                    tick.append(e["ticker"])
                n = len(x)
                if n < MIN_N:
                    out.append(f"| {glabel} | {h} | {n} |" + " |" * 13 + " 样本不足 |")
                    continue
                x, pm, mn, day, rel = map(np.array, (x, pm, mn, day, rel))
                L = int(h)
                prim_x = boot(day // L, len(cal) // L + 1, x)
                prim = boot(day // L, len(cal) // L + 1, rel)
                prim_p = boot(day // L, len(cal) // L + 1, pm)
                sens = boot(day // (2 * L), len(cal) // (2 * L) + 1, rel)
                names = {t: i for i, t in enumerate(sorted(set(tick)))}
                clus = boot(np.array([names[t] for t in tick]), len(names), rel)

                def verdict_of(ci):
                    if ci is None:
                        return "尚无法确认"
                    if ci[0] >= -TRIVIAL_PP and ci[1] <= TRIVIAL_PP:
                        return "效果太小"
                    return "有增益证据" if ci[0] > 0 else "有负向证据" if ci[1] < 0 else "尚无法确认"

                out.append(f"| {glabel} | {h} | {n} | {np.mean(x > 0):.3f} | {pm.mean():.2f} | {x.mean():.2f} | "
                           f"{np.median(x):.2f} | {x.mean() - COST_PP:.2f} | {np.percentile(x, 10):.2f} | "
                           f"{np.median(mn):.2f} | {rel.mean():.2f} | {fmt(prim)} | {fmt(prim_p)} | {fmt(sens)} | "
                           f"{fmt(clus)} | {verdict_of(prim)} | {verdict_of(prim_x)} |")
        return out + [""]

    big = lambda e: (e.get("volume_ratio") or 0) >= 2  # noqa: E731
    lines = [
        f"# 财报后漂移 v2（as_of {args.as_of if args.as_of != '9999-12-31' else '最新'}）", "",
        "**状态：历史开发数据。** 2019–2026 年的财报事件此前都已看过，这不是未接触的验证集；结论不得当作样本外证据。", "",
        "口径：`evals/signals/pead-v2-definition-2026-10-26.md`。受理时间定信号日 D0，反应 = P 收盘到 D0 收盘的板块超额；"
        "D1 开盘入场，D_h 收盘退出（复权）；收益与路径最低点为个股相对板块 ETF 的超额；扣成本 = 减 0.2pp 往返。"
        "次日开盘是模拟成交假设。百分位与超额收益是两种口径，分开列。",
        "CI（95%，1000 次，种子 0）：主要 = 按交易日期连续块（块长 h 个交易日）重抽样；敏感 = 块长 2h；辅助 = 按股票整群；"
        "单位为百分点（超额）或百分位点。结论（v2.1，依据相对基准超额的主要 CI）：CI 完全落在 ±0.5pp 内 = 效果太小；否则不含 0 为正 = 有增益证据、为负 = 有负向证据；其余 = 尚无法确认。相对基准超额 = 事件超额 − 同 D0 对照池均值（均按该池 1/99 百分位截尾；阶段分组用同阶段池）。原始均值超额与 v2 首轮结论保留作对照。",
        f"财报事件 {len(events)} 个（对照行日历 {len(cal)} 个交易日）。", ""]
    lines += table("按反应分组（D0 同日全股票池百分位）", lambda e, g: e["bucket"] == g,
                   [(b, LABEL[b]) for b in BUCKETS], "all")
    for stage in ("stage2", "stage4", "other"):
        lines += table(f"反应分组 × D0 趋势阶段 = {stage}（D0 同日、同阶段百分位）",
                       lambda e, g, s=stage: e["bucket"] == g and e["stage"] == s,
                       [(b, LABEL[b]) for b in ("strong_up", "strong_down")], "stage")
    lines += table("大涨/大跌 × 成交量放大 ≥ 2 倍（D0 同日全股票池百分位）",
                   lambda e, g: e["bucket"] == g and big(e),
                   [(b, LABEL[b] + "，放量") for b in ("strong_up", "strong_down")], "all")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
