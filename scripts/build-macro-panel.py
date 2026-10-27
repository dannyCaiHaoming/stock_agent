"""宏观与市场风险状态日面板（时点正确，仅数据，不含任何收益统计）。

用法：.venv/bin/python -I scripts/build-macro-panel.py
输出：.local/cache/derived/macro/panel.jsonl 与 meta.json
行 = 2018-01-01 起的每个美股交易日 t（以 SPY 日线为日历）。特征只用 t 收盘时已知的信息；
目标列全部以 tgt_ 开头，从 t+1 开盘起算（t+1 开盘进场，t+h 收盘出场）。

已知时点规则：
- Yahoo 价格/指数（VIX 系列、MOVE、ETF）：当日收盘即已知。
- FRED 日度序列（DFII10、T10YIE、DGS2、DGS10、BAMLH0A0HYM2）：观测日 d 的值，保守地视为 d 之后的下一个交易日才可用，
  即 t 收盘时只使用观测日 <= 上一个交易日的最新值（FRED 页面通常次日早晨更新，H.15 当日约 16:15 发布）。
  同时输出 *_obs（所用观测日），可审计滞后。
- NFCI（周度，周五观测）：通常次周三 8:30 ET 发布。FRED 只给当前版本，且整段历史每周重估（修订很大），
  因此逐周三向 ALFRED 取 vintage_date=该周三 的快照，取其中最新观测作为“首发值”；t >= 该周三（收盘）才可用。
  nfci_chg4w 取同一快照内最新观测与 4 周前观测之差（版本内一致）。若周三快照没有新观测（假日推迟），顺延到随后日期。
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.request import Request

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import context_tools as ctx, data_tools  # noqa: E402

OUT = REPO / ".local/cache/derived/macro"
START = "2018-01-01"
FETCH_START = "2016-06-01"
END = (date.today() - timedelta(days=1)).isoformat()
FRED = ["DFII10", "T10YIE", "DGS2", "DGS10", "BAMLH0A0HYM2", "BAMLC0A0CM"]
SECTORS = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC"]
TARGETS = ["SPY", "QQQ", "XLK", "SMH"]
YAHOO = ["^VIX", "^VIX9D", "^VIX3M", "^VIX6M", "^MOVE", "HYG", "IEF", "LQD", "RSP", "SPY", "QQQ", "SMH"] + SECTORS
ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=NFCI&vintage_date={v}&cosd={c}&coed={v}"


def fred_series(sid: str) -> list[tuple[str, float]]:
    raw, _ = ctx._fetch({"provider": "fred-csv", "series": sid}, Request(ctx.FRED_CSV.format(series=sid), headers=ctx.HEADERS), final=False)
    out = []
    for line in raw.decode().strip().split("\n")[1:]:
        d, _, v = line.partition(",")
        if v not in ("", "."):
            out.append((d, float(v)))
    return out


def nfci_first_release() -> list[dict]:
    """ALFRED 每周三与周四的快照（多 vintage 批量取）-> [{known, obs, value, chg4w}]。
    known = 最新观测首次出现的快照日期（假日推迟时落在周四）；缺失的快照日（非工作日）ALFRED 返回最近一次版本。"""
    vints, w = [], date(2017, 11, 1)
    while w.weekday() != 2:
        w += timedelta(days=1)
    while w <= date.today() - timedelta(days=1):
        vints += [w, w + timedelta(days=1)]
        w += timedelta(days=7)
    vints = [v for v in vints if v <= date.today() - timedelta(days=1)]
    res, seen = [], set()
    for b0 in range(0, len(vints), 12):
        batch = vints[b0:b0 + 12]
        url = ("https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=" + ",".join(["NFCI"] * len(batch))
               + "&vintage_date=" + ",".join(v.isoformat() for v in batch))
        for attempt in range(6):  # ALFRED 偶发超时；已成功的批次由缓存复用
            try:
                raw, _ = ctx._fetch({"provider": "alfred-csv-batch", "series": "NFCI", "vintages": [v.isoformat() for v in batch]},
                                    Request(url, headers=ctx.HEADERS), final=True)
                break
            except ValueError:
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"ALFRED batch failed: {batch[0]}")
        lines = raw.decode().strip().split("\n")
        cols = lines[0].split(",")[1:]
        table = [l.split(",") for l in lines[1:]]
        for c, name in enumerate(cols):
            v = datetime.strptime(name.split("_")[1], "%Y%m%d").date()
            obs = [(row[0], row[c + 1]) for row in table if c + 1 < len(row) and row[c + 1] not in ("", ".")]
            if len(obs) < 5 or obs[-1][0] in seen or (v - date.fromisoformat(obs[-1][0])).days > 12:
                continue
            seen.add(obs[-1][0])
            res.append({"known": v.isoformat(), "obs": obs[-1][0], "value": float(obs[-1][1]),
                        "chg4w": float(obs[-1][1]) - float(obs[-5][1])})
    return sorted(res, key=lambda x: x["known"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    px = {}
    for t in YAHOO:
        r = data_tools.get_price_history(t, start=FETCH_START, end=END, max_rows=10000)
        px[t] = {row[0]: [row[0], *(float(x) if x is not None else None for x in row[1:6]), row[6]] for row in r["rows"]}  # date, open, high, low, close, adj, volume
        print(t, len(r["rows"]), r["rows"][0][0], r["rows"][-1][0], file=sys.stderr)
    days = sorted(d for d in px["SPY"])
    fred = {s: fred_series(s) for s in FRED}
    fred_keys = {s: [d for d, _ in v] for s, v in fred.items()}
    nfci = nfci_first_release()
    nfci_known = [x["known"] for x in nfci]
    idx = {d: i for i, d in enumerate(days)}

    def close(t, d):
        r = px[t].get(d)
        return r[4] if r else None

    def adj(t, d):
        r = px[t].get(d)
        return r[5] if r else None

    # 已知的 FRED 值按交易日对齐：t 收盘用观测日 <= 上一交易日
    fred_aligned = {s: {} for s in FRED}
    for s in FRED:
        for i, d in enumerate(days):
            prev = days[i - 1] if i else None
            j = bisect_right(fred_keys[s], prev) if prev else 0
            fred_aligned[s][d] = fred[s][j - 1] if j else None

    def lagged(getter, d, n):
        i = idx[d]
        return getter(days[i - n]) if i - n >= 0 else None

    def chg(cur, old):
        return None if cur is None or old is None else cur - old

    def pct(cur, old):
        return None if cur is None or old is None or old == 0 else cur / old - 1

    rows = []
    for d in days:
        if d < START:
            continue
        i = idx[d]
        r = {"date": d}
        for s, name in (("DFII10", "dfii10"), ("T10YIE", "t10yie"), ("DGS2", "dgs2"), ("DGS10", "dgs10"),
                        ("BAMLH0A0HYM2", "hy_oas"), ("BAMLC0A0CM", "ig_oas")):
            a = fred_aligned[s][d]
            r[name], r[name + "_obs"] = (a[1], a[0]) if a else (None, None)
            for n in (5, 20):
                old = lagged(lambda x: (fred_aligned[s][x] or (None, None))[1], d, n)
                r[f"{name}_chg{n}"] = chg(r[name], old)
        r["curve_10s2s"] = chg(r["dgs10"], r["dgs2"])
        r["curve_10s2s_chg20"] = chg(r["curve_10s2s"], lagged(lambda x: chg(fred_aligned["DGS10"][x][1] if fred_aligned["DGS10"][x] else None, fred_aligned["DGS2"][x][1] if fred_aligned["DGS2"][x] else None), d, 20))
        for t, name in (("^VIX", "vix"), ("^VIX9D", "vix9d"), ("^VIX3M", "vix3m"), ("^VIX6M", "vix6m"), ("^MOVE", "move")):
            r[name] = close(t, d)
            for n in (5, 20):
                r[f"{name}_chg{n}"] = chg(r[name], lagged(lambda x: close(t, x), d, n))
        r["vix9d_vix"] = r["vix9d"] / r["vix"] if r["vix9d"] and r["vix"] else None
        r["vix_vix3m"] = r["vix"] / r["vix3m"] if r["vix"] and r["vix3m"] else None
        r["vix_vix3m_chg5"] = chg(r["vix_vix3m"], lagged(lambda x: (close("^VIX", x) / close("^VIX3M", x)) if close("^VIX", x) and close("^VIX3M", x) else None, d, 5))
        # 信用代理：总回报比（复权收盘）HYG/IEF、LQD/IEF 的对数；下降 = 信用相对承压
        for num, name in (("HYG", "hyg_ief"), ("LQD", "lqd_ief")):
            f = lambda x, num=num: math.log(adj(num, x) / adj("IEF", x)) if adj(num, x) and adj("IEF", x) else None
            r[name + "_log"] = f(d)
            for n in (5, 20):
                r[f"{name}_chg{n}"] = chg(f(d), lagged(f, d, n))
        # 广度代理
        r["rsp_spy_rel20"] = chg(pct(adj("RSP", d), lagged(lambda x: adj("RSP", x), d, 20)), pct(adj("SPY", d), lagged(lambda x: adj("SPY", x), d, 20)))
        r["rsp_spy_rel5"] = chg(pct(adj("RSP", d), lagged(lambda x: adj("RSP", x), d, 5)), pct(adj("SPY", d), lagged(lambda x: adj("SPY", x), d, 5)))
        above, n_ok = 0, 0
        for t in SECTORS:
            if i >= 49 and all(px[t].get(days[k]) for k in range(i - 49, i + 1)):
                sma = sum(px[t][days[k]][4] for k in range(i - 49, i + 1)) / 50
                n_ok += 1
                above += px[t][d][4] > sma
        r["sector_n"] = n_ok
        r["sector_above50_share"] = above / n_ok if n_ok else None
        r["sector_above50_share_chg20"] = None  # 下方二次填充
        for t in TARGETS:
            r[f"{t.lower()}_close"] = close(t, d)
            for n in (5, 20):
                r[f"{t.lower()}_ret{n}"] = pct(adj(t, d), lagged(lambda x: adj(t, x), d, n))
        # NFCI 首发值
        j = bisect_right(nfci_known, d)
        if j:
            x = nfci[j - 1]
            r.update(nfci=x["value"], nfci_obs=x["obs"], nfci_known=x["known"], nfci_chg4w=x["chg4w"])
        else:
            r.update(nfci=None, nfci_obs=None, nfci_known=None, nfci_chg4w=None)
        # 目标（t+1 开盘起）
        for t in TARGETS:
            for k in ("fwd5", "fwd20", "rv20", "mdd20"):
                r[f"tgt_{t.lower()}_{k}"] = None
            if i + 20 < len(days) and all(days[i + m] in px[t] for m in range(1, 21)):
                row1 = px[t][days[i + 1]]
                fac = row1[5] / row1[4] if row1[4] else 1.0
                o = row1[1] * fac
                path = [adj(t, days[i + m]) for m in range(1, 21)]
                r[f"tgt_{t.lower()}_fwd5"] = path[4] / o - 1
                r[f"tgt_{t.lower()}_fwd20"] = path[19] / o - 1
                levels = [o] + path
                lr = [math.log(levels[m + 1] / levels[m]) for m in range(20)]
                mean = sum(lr) / 20
                r[f"tgt_{t.lower()}_rv20"] = math.sqrt(sum((x - mean) ** 2 for x in lr) / 19) * math.sqrt(252)
                peak, mdd = levels[0], 0.0
                for v in levels:
                    peak = max(peak, v)
                    mdd = min(mdd, v / peak - 1)
                r[f"tgt_{t.lower()}_mdd20"] = mdd
            elif i + 5 < len(days) and all(days[i + m] in px[t] for m in range(1, 6)):
                row1 = px[t][days[i + 1]]
                fac = row1[5] / row1[4] if row1[4] else 1.0
                r[f"tgt_{t.lower()}_fwd5"] = adj(t, days[i + 5]) / (row1[1] * fac) - 1
        rows.append(r)
    for k, r in enumerate(rows):  # sector_above50_share 20 日变化
        if k >= 20 and r["sector_above50_share"] is not None and rows[k - 20]["sector_above50_share"] is not None:
            r["sector_above50_share_chg20"] = r["sector_above50_share"] - rows[k - 20]["sector_above50_share"]
    with open(OUT / "panel.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}, ensure_ascii=False) + "\n")
    nonnull = {k: sum(r[k] is not None for r in rows) for k in rows[0]}
    meta = {"built_at": datetime.now(UTC).isoformat(), "rows": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"],
            "nonnull": nonnull, "nfci_releases": len(nfci), "yahoo_first_dates": {t: min(px[t]) for t in YAHOO}}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(json.dumps({k: meta[k] for k in ("rows", "first", "last", "nfci_releases")}), file=sys.stderr)


if __name__ == "__main__":
    main()
