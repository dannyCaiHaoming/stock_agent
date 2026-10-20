"""内部人交易事件表：基于 SEC Insider Transactions Data Sets（季度 Form 3/4/5 结构化数据）。

用法：.venv/bin/python -I scripts/build-insider-events.py   （先运行 build-pead-events.py：复用其每日对照与趋势阶段）
数据：.local/cache/derived/insider-raw/<YYYY>q<N>_form345.zip（SEC 官方，按季度下载一次即可）。
事件（以申报日为公开时点，次一交易日收盘入场，持有 5/20/60/126/252 日，相对板块 ETF）：
  insider_buy           任一内部人公开市场买入（交易代码 P）
  insider_buy_large     单次申报买入金额 ≥ $100k
  insider_buy_officer   CEO/CFO/总裁/首席执行或财务官买入
  insider_buy_cluster   30 天内 ≥ 2 位不同内部人公开市场买入（在第二位申报日触发）
  insider_sell_cluster  30 天内 ≥ 3 位不同内部人公开市场卖出、且不属于 10b5-1 计划（计划标记 2023 年起才有）
输出：.local/cache/derived/signals/events-insider.jsonl 与 meta-insider.json。
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import data_tools, settings  # noqa: E402

HORIZONS = (5, 20, 60, 126, 252)
OFFICER = ("CEO", "CFO", "CHIEF EXECUTIVE", "CHIEF FINANCIAL", "PRESIDENT")
csv.field_size_limit(10_000_000)


def _date(text: str) -> str | None:
    try:
        return datetime.strptime(text.strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def read_quarter(path: Path, universe: set[str]) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8", errors="replace"), delimiter="\t")
        subs = {}
        for r in rows("SUBMISSION.tsv"):
            sym = (r.get("ISSUERTRADINGSYMBOL") or "").strip().upper()
            if sym in universe and r.get("DOCUMENT_TYPE", "").startswith("4"):
                subs[r["ACCESSION_NUMBER"]] = {"ticker": sym, "filed": _date(r["FILING_DATE"]),
                                               "plan": (r.get("AFF10B5ONE") or "").strip() in ("1", "true", "TRUE")}
        owners = {}
        for r in rows("REPORTINGOWNER.tsv"):
            if r["ACCESSION_NUMBER"] in subs:
                owners.setdefault(r["ACCESSION_NUMBER"], []).append(
                    {"cik": r.get("RPTOWNERCIK"), "name": r.get("RPTOWNERNAME"),
                     "role": f"{r.get('RPTOWNER_RELATIONSHIP') or ''} {r.get('RPTOWNER_TITLE') or ''}".upper()})
        trades = []
        for r in rows("NONDERIV_TRANS.tsv"):
            acc = r["ACCESSION_NUMBER"]
            if acc not in subs or r.get("TRANS_CODE") not in ("P", "S"):
                continue
            try:
                shares, price = float(r.get("TRANS_SHARES") or 0), float(r.get("TRANS_PRICEPERSHARE") or 0)
            except ValueError:
                continue
            trades.append({**subs[acc], "accession": acc, "code": r["TRANS_CODE"], "value": shares * price,
                           "owners": owners.get(acc, [])})
    return trades


def main() -> None:
    root = settings.cache().root / "derived"
    meta = json.loads((root / "signals" / "meta.json").read_text())
    universe = set(meta["tickers"])
    trades = []
    zips = sorted((root / "insider-raw").glob("*_form345.zip"))
    for path in zips:
        trades += read_quarter(path, universe)
        print(path.name, len(trades), file=sys.stderr, flush=True)
    # one row per filing (accession): aggregate value, owner identity
    filings: dict[str, dict] = {}
    for t in trades:
        f = filings.setdefault(t["accession"], {**{k: t[k] for k in ("ticker", "filed", "plan", "accession")},
                                                "buy": 0.0, "sell": 0.0, "owners": t["owners"]})
        f["buy" if t["code"] == "P" else "sell"] += t["value"]
    by_ticker: dict[str, list[dict]] = {}
    for f in filings.values():
        if f["filed"]:
            by_ticker.setdefault(f["ticker"], []).append(f)
    out = (root / "signals" / "events-insider.jsonl").open("w")
    counts: dict[str, int] = {}
    for ticker, fs in sorted(by_ticker.items()):
        fs.sort(key=lambda f: f["filed"])
        etf = meta["benchmarks"].get(ticker, "SPY")
        rows = data_tools.get_price_history(ticker, start="2018-01-01", max_rows=6000)["rows"]
        rows = [r for r in rows if (r[5] or r[4])]
        dates, closes = [r[0] for r in rows], [float(r[5] or r[4]) for r in rows]
        brow = data_tools.get_price_history(etf, start="2018-01-01", max_rows=6000)["rows"]
        bench = {r[0]: float(r[5] or r[4]) for r in brow if (r[5] or r[4])}

        def emit(signal: str, f: dict, extra: dict) -> None:
            i = next((k for k, d in enumerate(dates) if d > f["filed"]), None)  # filing time unknown: next session
            if i is None or dates[i] not in bench:
                return
            row = {"kind": "event", "signal": signal, "ticker": ticker, "filed": f["filed"], "entry_date": dates[i],
                   "benchmark": etf, "accession": f["accession"], **extra}
            for h in HORIZONS:
                j = i + h
                if j < len(dates) and dates[j] in bench:
                    row[str(h)] = (closes[j] / closes[i] - 1) - (bench[dates[j]] / bench[dates[i]] - 1)
                    row[f"exit_{h}"] = dates[j]
            out.write(json.dumps(row) + "\n")
            counts[signal] = counts.get(signal, 0) + 1

        for f in fs:
            names = {o["cik"] for o in f["owners"]}
            officer = any(any(k in o["role"] for k in OFFICER) for o in f["owners"])
            if f["buy"] > 0:
                emit("insider_buy", f, {"value": round(f["buy"])})
                if f["buy"] >= 100_000:
                    emit("insider_buy_large", f, {"value": round(f["buy"])})
                if officer:
                    emit("insider_buy_officer", f, {"value": round(f["buy"])})
                start = date.fromisoformat(f["filed"]) - timedelta(days=30)
                before = [g for g in fs if g["buy"] > 0 and g is not f and start <= date.fromisoformat(g["filed"]) <= date.fromisoformat(f["filed"])]
                earlier_buyers = {o["cik"] for g in before for o in g["owners"]}
                recent_cluster = any(g.get("_cluster_buy") and start <= date.fromisoformat(g["filed"]) for g in fs if g is not f)
                if earlier_buyers and names - earlier_buyers and not recent_cluster:
                    f["_cluster_buy"] = True  # a new, different insider buys within 30 days of another
                    emit("insider_buy_cluster", f, {"buyers_30d": len(earlier_buyers | names)})
            if f["sell"] > 0 and not f["plan"]:
                window = [g for g in fs if g["sell"] > 0 and not g["plan"] and
                          date.fromisoformat(f["filed"]) - timedelta(days=30) <= date.fromisoformat(g["filed"]) <= date.fromisoformat(f["filed"])]
                sellers = {o["cik"] for g in window for o in g["owners"]}
                if len(sellers) >= 3 and not any(
                        e.get("_cluster_sell") and date.fromisoformat(f["filed"]) - date.fromisoformat(e["filed"]) <= timedelta(days=30)
                        for e in fs if e["filed"] < f["filed"]):
                    f["_cluster_sell"] = True
                    emit("insider_sell_cluster", f, {"sellers_30d": len(sellers)})
    out.close()
    (root / "signals" / "meta-insider.json").write_text(json.dumps({
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "quarters": [p.name for p in zips],
        "events": counts, "definition": __doc__}, ensure_ascii=False, indent=2))
    print(counts)


if __name__ == "__main__":
    main()
