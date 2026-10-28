"""每日新闻前向存档：moomoo news_search（news_type 1 新闻、3 研报聚合），只存标题/时间/URL，不存正文。

用法：.venv/bin/python -I scripts/snapshot-news.py [--tickers AAPL,MSFT] [--types 1,3] [--out-dir DIR] [--rerun]
调用方式严格按 product/skills/moomoo-news-search/SKILL.md（GET /news_search，size=50，sort_type=2，lang=en）。
股票池：evals/replay/universe.txt + 可选 .local/data/watchlist.txt（去重）。串行，每次调用间隔 1–2 秒，失败重试一次。
输出（追加；同日已完成的 (ticker, news_type) 会跳过，--rerun 则同日追加新行）：
  <out-dir>/news/<YYYY-MM-DD>.jsonl   每个 (ticker, news_type) 一行，含 items[]
  <out-dir>/news/first-seen.jsonl     news_id 首次被我们观察到的时间（追加，不改写；点时证据）
默认 out-dir = .local/data/history。日期按纽约时间。退出码 1 表示有失败。
"""

from __future__ import annotations

import argparse
import html
import json
import random
import re
import ssl
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import certifi

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

REPO = Path(__file__).resolve().parents[1]
SOURCE_ID = "moomoo-news-search"
BASE = "https://ai-news-search.moomoo.com/news_search"
HEADERS = {"User-Agent": "moomoo-news-search/0.0.2 (Skill)"}
SIZE, SORT_TYPE, LANG = 50, 2, "en"


def tickers(arg: str | None) -> list[str]:
    if arg:
        return [t.strip().upper() for t in arg.split(",") if t.strip()]
    names: list[str] = []
    for path in (REPO / "evals/replay/universe.txt", REPO / ".local/data/watchlist.txt"):
        if path.exists():
            names += [t for line in path.read_text().splitlines() if not line.startswith("#") for t in line.split()]
    return list(dict.fromkeys(n.upper() for n in names))


def clean(title: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", title or "")).split())


def utc_iso(raw) -> str | None:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if v > 10**11:  # 毫秒
        v //= 1000
    return datetime.fromtimestamp(v, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(ticker: str, news_type: int) -> list[dict]:
    params = {"keyword": ticker, "size": SIZE, "news_type": news_type, "lang": LANG, "sort_type": SORT_TYPE}
    last = None
    for attempt in range(2):
        try:
            with urlopen(Request(f"{BASE}?{urlencode(params)}", headers=HEADERS), timeout=30, context=SSL_CONTEXT) as r:
                body = json.loads(r.read().decode())
            if body.get("code") != 0:
                raise RuntimeError(f"code={body.get('code')} message={body.get('message')}")
            return body.get("data") or []
        except Exception as exc:  # noqa: BLE001 - 单次失败重试一次
            last = exc
            time.sleep(3)
    raise RuntimeError(str(last))


def item_row(rank: int, raw: dict) -> dict:
    url = raw.get("url") or ""
    return {"rank": rank, "news_id": str(raw.get("news_id")), "news_type": raw.get("news_type"),
            "title_raw": raw.get("title"), "title_clean": clean(raw.get("title")),
            "publish_time": {"raw": raw.get("publish_time"), "utc": utc_iso(raw.get("publish_time"))},
            "url": url, "domain": urlparse(url).netloc}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append(path: Path, rows: list[dict]) -> None:
    with path.open("a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers")
    ap.add_argument("--types", default="1,3")
    ap.add_argument("--out-dir", default=str(REPO / ".local/data/history"))
    ap.add_argument("--rerun", action="store_true")
    args = ap.parse_args()
    types = [int(t) for t in args.types.split(",")]
    news_dir = Path(args.out_dir) / "news"
    news_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    day_file, seen_file = news_dir / f"{today}.jsonl", news_dir / "first-seen.jsonl"
    done = set() if args.rerun else {(r["ticker"], r["query"]["news_type"]) for r in read_jsonl(day_file)}
    seen = {r["news_id"] for r in read_jsonl(seen_file)}
    summary = {"date": today, "done": 0, "skipped": 0, "failed": [], "items": 0, "new_news_ids": 0}
    first = True
    for t in tickers(args.tickers):
        for nt in types:
            if (t, nt) in done:
                summary["skipped"] += 1
                continue
            if not first:
                time.sleep(random.uniform(1, 2))
            first = False
            retrieved = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                data = fetch(t, nt)
            except Exception as exc:  # noqa: BLE001
                summary["failed"].append({"ticker": t, "news_type": nt, "error": str(exc)[:200]})
                print(f"FAIL {t} type={nt}: {exc}", file=sys.stderr)
                continue
            items = [item_row(i + 1, d) for i, d in enumerate(data)]
            append(day_file, [{"ticker": t, "retrieved_at": retrieved, "source_id": SOURCE_ID,
                               "query": {"keyword": t, "size": SIZE, "news_type": nt, "lang": LANG, "sort_type": SORT_TYPE},
                               "items": items}])
            fresh = []
            for it in items:
                if it["news_id"] not in seen:
                    seen.add(it["news_id"])
                    fresh.append({"news_id": it["news_id"], "ticker": t, "first_seen_at": retrieved,
                                  "publish_time": it["publish_time"], "news_type": it["news_type"]})
            append(seen_file, fresh)
            summary["done"] += 1
            summary["items"] += len(items)
            summary["new_news_ids"] += len(fresh)
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
