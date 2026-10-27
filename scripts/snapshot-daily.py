"""每日快照：积累免费数据源没有提供的历史（分析师一致预期、社区讨论）。

用法：.venv/bin/python -I scripts/snapshot-daily.py [--tickers AAPL,MSFT] [--only estimates|community] [--out-dir DIR] [--rerun]
  --out-dir 把 history 写到别处（调试用）；--rerun 忽略“当天已完成”，同日追加新一行（盘中多次抓取，事后按帖子 id 去重）。
  stock_feed 单次最多 50 条、无分页（见 evals/community/data-sources-2026-10-27.md），热门股 50 条只覆盖约 6–8 小时，需一天多次抓取才能覆盖 24 小时。
股票池：evals/replay/universe.txt，加上 .local/data/watchlist.txt（每行一个代码，可选）。
输出（追加、同一天重跑会跳过已完成的代码）：
  .local/data/history/estimates/<YYYY-MM-DD>.jsonl   Yahoo 一致预期、预期趋势与修正家数、目标价、评级、下次财报日
  .local/data/history/community/<YYYY-MM-DD>.jsonl   moomoo 社区讨论（帖子 id、时间、标题与正文纯文本）
原始响应同时存入共享缓存 .local/cache（内容寻址）。日期按纽约时间。
"""

from __future__ import annotations

import argparse
import hashlib
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


def _author_hash(value) -> str:
    """作者标识加盐哈希；盐存放在 .local/data/community-salt（不入库）。原始 ID/昵称不落盘。"""
    path = settings.data_dir() / "community-salt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(os.urandom(16).hex())
    return hashlib.sha256((path.read_text().strip() + str(value)).encode()).hexdigest()[:16]


def _post(p: dict) -> dict:
    raw = (p.get("title") or "") + " " + (p.get("desc") or "")
    text = _text(p.get("desc", ""))
    out = {"id": p.get("id"), "publish_time": p.get("publish_time"), "title": _text(p.get("title", ""))[:500],
           "text": text[:2000],
           # 新增：帖内 $标的$ 标签（话题集中度）、中文字符占比（语言混合）、全文长度
           "mentions": sorted(set(re.findall(r'stocksymbol="([^"]+)"', raw))),
           "cjk_ratio": round(len(re.findall(r"[\u4e00-\u9fff]", text)) / max(len(text), 1), 3), "text_len": len(text)}
    # 已知接口目前只返回 id/title/desc/publish_time；若上游以后加入作者或互动字段，自动保留（作者加盐哈希）
    for key in ("uid", "user_id", "author_id", "nick", "nickname", "author"):
        if p.get(key) not in (None, ""):
            out["author_hash"] = _author_hash(p[key])
            break
    for key in ("like_count", "likes", "comment_count", "comments", "reply_count", "view_count", "views", "share_count", "lang"):
        if key in p:
            out[key] = p[key]
    out["extra_fields"] = sorted(set(p) - {"id", "title", "desc", "publish_time", "uid", "user_id", "author_id", "nick", "nickname", "author",
                                           "like_count", "likes", "comment_count", "comments", "reply_count", "view_count", "views", "share_count", "lang"})
    return out


def community_row(ticker: str) -> dict:
    url = f"{STOCK_FEED}?{urlencode({'keyword': ticker, 'size': '50'})}"
    response = macro._http(Request(url, headers=FEED_HEADERS))
    if response.status != 200:
        raise RuntimeError(f"HTTP_{response.status}")
    retrieved_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = settings.cache().store({"provider": "moomoo-stock-feed", "ticker": ticker, "size": 50,
                                     "day": retrieved_at[:10]}, response.body, retrieved_at=retrieved_at)
    body = json.loads(response.body)
    if body.get("code") not in (0, None):
        raise RuntimeError(f"FEED_{body.get('code')}: {str(body.get('message'))[:100]}")
    posts = [_post(p) for p in body.get("data") or []]
    times = [int(p["publish_time"]) for p in posts if str(p.get("publish_time") or "").isdigit()]
    # 单次请求无法翻页：记录这 50 条实际覆盖的时间跨度（小时）
    span = {"earliest": min(times), "latest": max(times), "hours": round((max(times) - min(times)) / 3600, 2)} if times else None
    return {"ticker": ticker, "retrieved_at": retrieved_at, "raw_content_hash": record["raw_content_hash"], "request_size": 50,
            "span": span,
            "source": "moomoo stock_feed（第三方社区内容，只作研究参考）", "posts": posts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers")
    parser.add_argument("--only", choices=["estimates", "community"])
    parser.add_argument("--out-dir", help="history 输出目录，默认 .local/data/history")
    parser.add_argument("--rerun", action="store_true", help="忽略当天已完成的代码，追加新一行（仅社区快照盘中多次抓取用）")
    args = parser.parse_args()
    day = datetime.now(data_tools.NEW_YORK).date().isoformat()
    root = Path(args.out_dir) if args.out_dir else settings.data_dir() / "history"
    jobs = [("estimates", estimates_row, 0.5), ("community", community_row, 1.0)]
    summary = {}
    for name, build, pause in jobs:
        if args.only and args.only != name:
            continue
        path = root / name / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        skip = set() if (args.rerun and name == "community") else done(path)
        ok, failed = 0, {}
        for ticker in tickers(args.tickers):
            if ticker in skip:
                continue
            try:
                try:
                    row = build(ticker)
                except Exception:  # noqa: BLE001 - transient network failures: one retry
                    time.sleep(3)
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
