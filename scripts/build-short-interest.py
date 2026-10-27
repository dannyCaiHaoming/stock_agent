#!/usr/bin/env python
"""FINRA 半月度 short interest（持仓口径，非日度 short sale volume）→ 点时表。

输出 .local/cache/derived/short/si.jsonl。每行 = 一个 (ticker, settlement_date)。
- publication_date = settlement_date 之后第 7 个 NYSE 交易日（FINRA 公布日历规则，脚本内以 2026 官方表自检）。
- shares_outstanding 取 SEC companyfacts dei:EntityCommonStockSharesOutstanding 中 filed <= publication_date 的最新一条。
- FINRA 只服务“当前版本”，无法还原当年首次发布值；revision_flag / chain_mismatch 标记可见的修订痕迹。
用法: .venv/bin/python -I scripts/build-short-interest.py
"""
from __future__ import annotations

import datetime as D
import json
import os
import sys
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import settings  # noqa: E402
from product.mcp.live.sec_client import SecClient  # noqa: E402

OUT = settings.cache().root / "derived" / "short"
RAW = REPO / ".local" / "runs" / "short-probe"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
API = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"

# ------------------------------------------------------------ NYSE 交易日
def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    j, k = c // 4, c % 4
    m = (a + 11 * h) // 319
    r = (2 * e + 2 * j - k - h + m + 32) % 7
    n = (h - m + r + 90) // 25
    p = (h - m + r + n + 19) % 32
    return D.date(y, n, p)


def _nth(y, m, wd, n):
    d = D.date(y, m, 1)
    d += D.timedelta((wd - d.weekday()) % 7 + 7 * (n - 1))
    return d


def holidays(y):
    def obs(d):
        return d - D.timedelta(1) if d.weekday() == 5 else d + D.timedelta(1) if d.weekday() == 6 else d
    h = {obs(D.date(y, 1, 1)), _nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _easter(y) - D.timedelta(2),
         D.date(y, 5, 31) - D.timedelta((D.date(y, 5, 31).weekday()) % 7), obs(D.date(y, 7, 4)),
         _nth(y, 9, 0, 1), _nth(y, 11, 3, 4), obs(D.date(y, 12, 25))}
    if y >= 2022:
        h.add(obs(D.date(y, 6, 19)))
    if y == 2025:
        h.add(D.date(2025, 1, 9))  # Carter 国葬休市
    if y == 2018:
        h.add(D.date(2018, 12, 5))  # Bush 国葬休市
    # 12/31 周五 → 1/1 观察日落在上一年，NYSE 不休市；上面 obs(1/1) 周六不提前，故剔除
    h.discard(D.date(y, 12, 31))
    return h


def is_bd(d):
    return d.weekday() < 5 and d not in holidays(d.year)


def add_bd(d, n):
    while n:
        d += D.timedelta(1)
        if is_bd(d):
            n -= 1
    return d


OFFICIAL_2026 = {  # FINRA 官方日历（2026-10-27 抓取）：settlement -> publication
    "2026-01-15": "2026-01-27", "2026-01-30": "2026-02-10", "2026-02-13": "2026-02-25", "2026-02-27": "2026-03-10",
    "2026-03-13": "2026-03-24", "2026-03-31": "2026-04-10", "2026-04-15": "2026-04-24", "2026-04-30": "2026-05-11",
    "2026-05-15": "2026-05-27", "2026-05-29": "2026-06-09", "2026-06-15": "2026-06-25", "2026-06-30": "2026-07-10",
    "2026-07-15": "2026-07-24", "2026-07-31": "2026-08-11", "2026-08-14": "2026-08-25", "2026-08-31": "2026-09-10",
    "2026-09-15": "2026-09-24", "2026-09-30": "2026-10-09", "2026-10-15": "2026-10-26",
    "2025-11-14": "2025-11-25", "2025-11-28": "2025-12-09", "2025-12-15": "2025-12-24", "2025-12-31": "2026-01-12",
}


def publication_date(settle: str) -> str:
    return add_bd(D.date.fromisoformat(settle), 7).isoformat()


def selfcheck():
    bad = {k: (v, publication_date(k)) for k, v in OFFICIAL_2026.items() if publication_date(k) != v}
    if bad:
        raise SystemExit(f"publication rule mismatch: {bad}")


# ------------------------------------------------------------ FINRA
def universe():
    seen, out = set(), []
    for line in (REPO / "evals/replay/universe.txt").read_text().splitlines():
        if line.startswith("#"):
            continue
        for t in line.split():
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


def finra(tickers):
    rows, off = [], 0
    while True:
        body = json.dumps({"limit": 5000, "offset": off, "domainFilters": [{"fieldName": "symbolCode", "values": tickers}]}).encode()
        res = subprocess.run(["curl", "-sS", "-m", "120", "-X", "POST", API, "-H", "Content-Type: application/json",
                              "-H", "Accept: application/json", "-d", body.decode()], capture_output=True, check=True)
        page = json.loads(res.stdout)
        if not isinstance(page, list):
            raise SystemExit(f"FINRA error: {page}")
        rows += page
        if len(page) < 5000:
            return rows
        off += 5000


# ------------------------------------------------------------ SEC shares outstanding
def shares_table(tickers):
    client = SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=10**6)
    tmap = {r["ticker"].upper(): r["cik"] for r in client.read_ticker_map(max_age_seconds=7 * 86400)["mapping"]}
    out = {}
    for t in tickers:
        cik = tmap.get(t)
        if not cik:
            out[t] = None
            continue
        try:
            rec = client.companyfacts(cik, max_age_seconds=30 * 86400)
            facts = json.loads(client.cache.read(rec))
            units = facts["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"]
        except Exception as e:  # noqa: BLE001
            print("shares fail", t, type(e).__name__, file=sys.stderr)
            out[t] = None
            continue
        out[t] = sorted(({"value": u["val"], "end": u["end"], "filed": u["filed"], "form": u.get("form"), "accn": u.get("accn")}
                         for u in units), key=lambda u: (u["filed"], u["end"]))
    return out


def main():
    selfcheck()
    tickers = universe()
    raw = finra(tickers)
    (RAW / "finra-raw.json").write_text(json.dumps(raw))
    by = {}
    for r in raw:
        by.setdefault(r["symbolCode"], []).append(r)
    shares = shares_table(tickers)
    n = 0
    with (OUT / "si.jsonl").open("w") as f:
        for t in tickers:
            rs = sorted(by.get(t, []), key=lambda r: r["settlementDate"])
            for i, r in enumerate(rs):
                pub = publication_date(r["settlementDate"])
                si, adv = r["currentShortPositionQuantity"], r["averageDailyVolumeQuantity"]
                prev_in_chain = rs[i - 1]["currentShortPositionQuantity"] if i else None
                so = None
                for u in shares.get(t) or []:
                    if u["filed"] <= pub:
                        so = u
                row = {
                    "ticker": t, "settlement_date": r["settlementDate"], "publication_date": pub,
                    "short_interest": si, "prior_short_interest": r["previousShortPositionQuantity"],
                    "change": r["changePreviousNumber"], "change_pct": r["changePercent"],
                    "avg_daily_volume": adv, "days_to_cover_finra": r["daysToCoverQuantity"],
                    "days_to_cover": round(si / adv, 2) if adv else None,
                    "revision_flag": r["revisionFlag"], "split_flag": r["stockSplitFlag"],
                    "chain_mismatch": prev_in_chain is not None and prev_in_chain != r["previousShortPositionQuantity"],
                    "shares_outstanding": so["value"] if so else None,
                    "shares_outstanding_end": so["end"] if so else None,
                    "shares_outstanding_filed": so["filed"] if so else None,
                    "shares_outstanding_source": f"sec-companyfacts dei:EntityCommonStockSharesOutstanding {so['form']} {so['accn']}" if so else None,
                    "shares_stale": bool(so) and (D.date.fromisoformat(pub) - D.date.fromisoformat(so["filed"])).days > 150,
                    "si_pct_shares_out": round(100 * si / so["value"], 3) if so and so["value"] else None,
                    "source": "finra-api consolidatedShortInterest (current version)",
                }
                f.write(json.dumps(row) + "\n")
                n += 1
    print("rows", n, "tickers_with_finra", len(by), "of", len(tickers))


if __name__ == "__main__":
    main()
