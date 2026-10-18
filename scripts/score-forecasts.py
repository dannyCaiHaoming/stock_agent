"""给决策记录里的方向预测和动作打分（确定性计算，不做判断）。

用法：.venv/bin/python -I scripts/score-forecasts.py <索引.json|运行目录> ... [--cost-bp 10] [--out 文件.md]
  索引.json：replay-ablation.sh 产出的 {ticker: run_id}；也可直接给 .local/runs/<run-id> 目录。

第一层（预测是否发生）：Q0 = data_as_of 时已公布的最近一个财季，Q2 = 其后第二个财季。
  revenue_growth：Q2 同比增速 − Q0 同比增速，>+1pp 加速、<−1pp 放缓，否则持平；
  operating_margin：Q2 的 GAAP 营业利润率 − 去年同季，>+0.5pp 扩张、<−0.5pp 收缩，否则持平；
  relative_return_126d：之后 126 个交易日相对板块 ETF 的超额收益正负。
  每项记命中与否和 Brier 分数 (p − 命中)²。
第二层（交易结果）：63/126 日相对板块 ETF 超额收益，BUY/ADD 扣除往返成本（2 × 单边 cost-bp），
  以及 126 日内的最大回撤。NO_TRADE 也列出同样的数字作对照。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import calc_tools, context_tools, data_tools  # noqa: E402

SECTOR_ETF = {"Technology": "XLK", "Communication Services": "XLC", "Consumer Cyclical": "XLY",
              "Consumer Defensive": "XLP", "Healthcare": "XLV", "Financial Services": "XLF", "Industrials": "XLI",
              "Energy": "XLE", "Basic Materials": "XLB", "Utilities": "XLU", "Real Estate": "XLRE"}


def decisions(arg: str) -> list[tuple[str, dict]]:
    path = Path(arg)
    runs = [REPO / ".local/runs" / r for r in json.loads(path.read_text()).values() if r != "FAIL"] \
        if path.suffix == ".json" else [path]
    out = []
    for run in runs:
        log = run / "decisions.jsonl"
        if log.exists():
            lines = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
            if lines:
                out.append((run.name, lines[-1]))
    return out


def sector_etf(ticker: str, cache: dict) -> str:
    if ticker not in cache:
        rows = context_tools.get_peer_snapshot([ticker])["rows"]
        cache[ticker] = SECTOR_ETF.get(rows[0][1] if rows else "", "SPY")
    return cache[ticker]


def fundamentals_truth(ticker: str, as_of: str) -> dict:
    then = data_tools.get_financial_statements(ticker, period="quarterly", limit=1, as_of=as_of)
    q0_end = then["periods"][-1]["end"]
    now = data_tools.get_financial_statements(ticker, period="quarterly", limit=16)
    ends = [p["end"] for p in now["periods"]]
    if q0_end not in ends:
        return {"status": "Q0_NOT_FOUND", "q0_end": q0_end}
    i = ends.index(q0_end)
    if i + 2 >= len(ends):
        return {"status": "UNRESOLVED_Q2_NOT_REPORTED", "q0_end": q0_end}
    if i - 4 < 0:
        return {"status": "HISTORY_TOO_SHORT", "q0_end": q0_end}
    rev = now["lines"].get("revenue") or []
    oi = now["lines"].get("operating_income") or []

    def val(row, k):
        return Decimal(row[k]) if k < len(row) and row[k] is not None else None
    r = {k: val(rev, k) for k in (i - 4, i - 2, i, i + 2)}
    out = {"status": "RESOLVED", "q0_end": q0_end, "q2_end": ends[i + 2]}
    if all(r.values()) and r[i - 4] and r[i - 2]:
        delta = ((r[i + 2] / r[i - 2] - 1) - (r[i] / r[i - 4] - 1)) * 100
        out["revenue_growth"] = "accelerate" if delta > 1 else "decelerate" if delta < -1 else "flat"
        out["revenue_growth_delta_pp"] = float(round(delta, 2))
    o2, o_ago = val(oi, i + 2), val(oi, i - 2)
    if o2 is not None and o_ago is not None and r[i + 2] and r[i - 2]:
        delta = (o2 / r[i + 2] - o_ago / r[i - 2]) * 100
        out["operating_margin"] = "expand" if delta > Decimal("0.5") else "contract" if delta < Decimal("-0.5") else "flat"
        out["operating_margin_delta_pp"] = float(round(delta, 2))
    return out


def market_truth(ticker: str, as_of: str, etf: str) -> dict:
    out = {"benchmark": etf}
    result = calc_tools.forward_returns(ticker, [as_of], horizons_days=[63, 126], benchmark=etf)
    row = result["rows"][0] if result["rows"] else {}
    for h in (63, 126):
        value = row.get(f"excess_{h}d_pct")
        out[f"excess_{h}d_pct"] = float(value) if value is not None else None
    prices = data_tools.get_price_history(ticker, start=as_of, max_rows=400)["rows"][:127]
    closes = [float(r[5] or r[4]) for r in prices]
    peak, drawdown = closes[0] if closes else None, 0.0
    for c in closes:
        peak = max(peak, c)
        drawdown = min(drawdown, c / peak - 1)
    out["max_drawdown_126d_pct"] = round(drawdown * 100, 2) if closes else None
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--cost-bp", type=float, default=10)
    parser.add_argument("--out")
    args = parser.parse_args()
    etf_cache: dict = {}
    rows = []
    for arg in args.inputs:
        label = Path(arg).stem
        for run, d in decisions(arg):
            ticker, as_of = d["ticker"], d["data_as_of"]
            etf = sector_etf(ticker, etf_cache)
            truth = {**fundamentals_truth(ticker, as_of), **market_truth(ticker, as_of, etf)}
            if truth.get("excess_126d_pct") is not None:
                truth["relative_return_126d"] = "outperform" if truth["excess_126d_pct"] > 0 else "underperform"
            scored = []
            for f in d.get("forecasts") or []:
                actual = truth.get(f["target"])
                if actual is None:
                    scored.append({**f, "actual": None})
                    continue
                hit = f["direction"] == actual
                scored.append({**f, "actual": actual, "hit": hit,
                               "brier": round((float(f["probability"]) - (1.0 if hit else 0.0)) ** 2, 4)})
            cost = 2 * args.cost_bp / 100 if d["action"] in ("BUY", "ADD") else 0.0
            net = {h: (truth.get(f"excess_{h}d_pct") - cost if truth.get(f"excess_{h}d_pct") is not None else None)
                   for h in (63, 126)}
            rows.append({"set": label, "run": run, "ticker": ticker, "as_of": as_of, "action": d["action"],
                         "expected_return_pct": d.get("expected_return_pct"), "forecasts": scored, "truth": truth,
                         "net_excess_63d_pct": net[63], "net_excess_126d_pct": net[126]})
    lines = [f"# 方向预测与动作评分（单边成本 {args.cost_bp}bp）", ""]
    for label in dict.fromkeys(r["set"] for r in rows):
        group = [r for r in rows if r["set"] == label]
        lines += [f"## {label}", "", "| 股票 | 动作 | 期望% | 营收增速 预测→实际 | 利润率 预测→实际 | 126日相对 预测→实际 | 63日净超额% | 126日净超额% | 最大回撤% |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in group:
            f = {x["target"]: x for x in r["forecasts"]}

            def cell(t):
                x = f.get(t)
                if not x:
                    return "—"
                mark = "" if x.get("actual") is None else ("✅" if x.get("hit") else "❌")
                return f"{x['direction']}({x['probability']})→{x.get('actual') or '未出'} {mark}"
            lines.append(f"| {r['ticker']} | {r['action']} | {r['expected_return_pct'] or '—'} | {cell('revenue_growth')} | "
                         f"{cell('operating_margin')} | {cell('relative_return_126d')} | {r['net_excess_63d_pct']} | "
                         f"{r['net_excess_126d_pct']} | {r['truth'].get('max_drawdown_126d_pct')} |")
        lines.append("")
        for target in ("revenue_growth", "operating_margin", "relative_return_126d"):
            items = [x for r in group for x in r["forecasts"] if x["target"] == target and x.get("actual") is not None]
            if items:
                lines.append(f"- {target}：命中 {sum(x['hit'] for x in items)}/{len(items)}，"
                             f"平均 Brier {round(statistics.mean(x['brier'] for x in items), 3)}")
        for action in ("BUY", "NO_TRADE"):
            values = [r["net_excess_126d_pct"] for r in group if (r["action"] in ("BUY", "ADD")) == (action == "BUY")
                      and r["net_excess_126d_pct"] is not None]
            if values:
                lines.append(f"- {action} 组 126 日净超额：n={len(values)}，均值 {round(statistics.mean(values), 2)}%，"
                             f"中位 {round(statistics.median(values), 2)}%")
        lines.append("")
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
        Path(args.out).with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(text)


if __name__ == "__main__":
    main()
