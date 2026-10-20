"""每日快照：积累免费数据源没有提供的历史（分析师一致预期、社区讨论）。

用法：.venv/bin/python -I scripts/snapshot-daily.py [--tickers AAPL,MSFT] [--only estimates|community]
股票池：evals/replay/universe.txt，加上 .local/data/watchlist.txt（每行一个代码，可选）。
输出（追加、同一天重跑会跳过已完成的代码）：
  .local/data/history/estimates/<YYYY-MM-DD>.jsonl   Yahoo 一致预期、预期趋势与修正家数、目标价、评级、下次财报日
  .local/data/history/community/<YYYY-MM-DD>.jsonl   moomoo 社区讨论（帖子 id、时间、标题与正文纯文本）
原始响应同时存入共享缓存 .local/cache（内容寻址）。日期按纽约时间。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import data_tools, settings  # noqa: E402
from product.mcp.live import macro  # noqa: E402

STOCK_FEED = "https://ai-news-search.moomoo.com/stock_feed"
FEED_HEADERS = {"User-Agent": "moomoo-comment-sentiment/0.0.2 (Skill)"}


def tickers(arg: str | None) -> list[str]:
    if arg:
        return [t.strip().upper() for t in arg.split(",") if t.strip()]
    names = []
    for path in (REPO / "evals/replay/universe.txt", settings.data_dir() / "watchlist.txt"):
        if path.exists():
            names += [t for line in path.read_text().splitlines() if not line.startswith("#") for t in line.split()]
    return list(dict.fromkeys(n.upper() for n in names))


def done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["ticker"] for line in path.read_text().splitlines() if line.strip()}


def estimates_row(ticker: str) -> dict:
    snap = data_tools.get_analyst_snapshot(ticker)
    return {"ticker": ticker, "retrieved_at": snap["provenance"].get("retrieved_at"),
            "raw_content_hash": snap["provenance"].get("raw_content_hash"),
            "price": snap.get("price", {}).get("regularMarketPrice"),
            "consensus": snap.get("analyst_consensus", {}), "estimates": snap.get("estimates", []),
            "recommendation_trend": snap.get("recommendation_trend"), "next_earnings": snap.get("next_earnings"),
            "key_statistics": {k: snap.get("key_statistics", {}).get(k)
                               for k in ("trailingPE", "forwardPE", "shortPercentOfFloat", "shortRatio",
                                         "heldPercentInstitutions", "sharesOutstanding")}}


def _text(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).split())


def community_row(ticker: str) -> dict:
    url = f"{STOCK_FEED}?{urlencode({'keyword': ticker, 'size': '50'})}"
    response = macro._http(Request(url, headers=FEED_HEADERS))
    if response.status != 200:
        raise RuntimeError(f"HTTP_{response.status}")
    retrieved_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = settings.cache().store({"provider": "moomoo-stock-feed", "ticker": ticker, "size": 50,
                                     "day": retrieved_at[:10]}, response.body, retrieved_at=retrieved_at)
    body = json.loads(response.body)
    posts = [{"id": p.get("id"), "publish_time": p.get("publish_time"), "title": _text(p.get("title", ""))[:500],
              "text": _text(p.get("desc", ""))[:2000]} for p in body.get("data") or []]
    return {"ticker": ticker, "retrieved_at": retrieved_at, "raw_content_hash": record["raw_content_hash"],
            "source": "moomoo stock_feed（第三方社区内容，只作研究参考）", "posts": posts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers")
    parser.add_argument("--only", choices=["estimates", "community"])
    args = parser.parse_args()
    day = datetime.now(data_tools.NEW_YORK).date().isoformat()
    root = settings.data_dir() / "history"
    jobs = [("estimates", estimates_row, 0.5), ("community", community_row, 1.0)]
    summary = {}
    for name, build, pause in jobs:
        if args.only and args.only != name:
            continue
        path = root / name / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        skip = done(path)
        ok, failed = 0, {}
        for ticker in tickers(args.tickers):
            if ticker in skip:
                continue
            try:
                row = build(ticker)
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"snapshot_date": day, **row}, ensure_ascii=False) + "\n")
                ok += 1
            except Exception as exc:  # noqa: BLE001 - record and continue
                failed[ticker] = f"{type(exc).__name__}: {exc}"[:200]
            time.sleep(pause)
        summary[name] = {"file": str(path), "written": ok, "skipped_existing": len(skip), "failed": failed}
    log = root / "snapshot-log.jsonl"
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"run_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "day": day,
                                 **summary}, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
