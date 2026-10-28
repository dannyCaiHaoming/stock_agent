"""Point-in-time state tools built on local derived archives: market regime panel, FINRA short interest,
community/news attention. Descriptive only: no signal, score or sentiment label is computed here.

Every function respects as_of through `_cutoff` (end of that New York day for a bare date). Archives are read
from `.local/` (git-ignored); they are built by scripts/build-macro-panel.py, scripts/build-short-interest.py,
scripts/snapshot-daily.py and scripts/snapshot-news.py.
"""

from __future__ import annotations

import bisect
import html
import json
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from product.mcp import settings
from product.mcp.data_tools import NEW_YORK, DataToolError, _cutoff


def _derived_dir() -> Path:
    return settings.cache().root / "derived"


def _history_dir() -> Path:
    return settings.data_dir() / "history"


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _percentile(history: list[float], value: float) -> float | None:
    """Share (0-100) of history values <= value; None when history has fewer than 20 points."""
    if len(history) < 20:
        return None
    ordered = sorted(history)
    return round(100 * bisect.bisect_right(ordered, value) / len(ordered), 1)


# ---------------------------------------------------------------- market regime

REGIME_GROUPS: dict[str, list[str]] = {
    "rates": ["dfii10", "dfii10_chg5", "dfii10_chg20", "t10yie", "t10yie_chg5", "t10yie_chg20", "dgs2", "dgs2_chg5",
              "dgs2_chg20", "dgs10", "dgs10_chg5", "dgs10_chg20", "curve_10s2s", "curve_10s2s_chg20"],
    "volatility": ["vix", "vix_chg5", "vix_chg20", "vix9d", "vix9d_chg5", "vix9d_chg20", "vix3m", "vix3m_chg5",
                   "vix3m_chg20", "vix6m", "vix6m_chg5", "vix6m_chg20", "vix9d_vix", "vix_vix3m", "vix_vix3m_chg5",
                   "move", "move_chg5", "move_chg20"],
    "credit": ["hyg_ief_log", "hyg_ief_chg5", "hyg_ief_chg20", "lqd_ief_log", "lqd_ief_chg5", "lqd_ief_chg20",
               "hy_oas", "hy_oas_chg5", "hy_oas_chg20", "ig_oas", "ig_oas_chg5", "ig_oas_chg20"],
    "breadth": ["rsp_spy_rel5", "rsp_spy_rel20", "sector_above50_share", "sector_above50_share_chg20"],
    "financial_conditions": ["nfci", "nfci_chg4w"],
}
REGIME_OBS_DATES = ["dfii10_obs", "t10yie_obs", "dgs2_obs", "dgs10_obs", "hy_oas_obs", "ig_oas_obs", "nfci_obs",
                    "nfci_known"]
KNOWN_AT_RULES = {
    "fred_daily": "dfii10/t10yie/dgs2/dgs10/hy_oas/ig_oas: observation of the previous trading day or earlier (value on "
                  "row date d uses observations < d; see *_obs for the actual observation date). Series update "
                  "unevenly, so *_obs can differ across series.",
    "yahoo_daily": "VIX family, MOVE, HYG/LQD/IEF, RSP/SPY, sector ETFs: close of the row date (known after the close "
                   "of date d; an as_of earlier than 16:00 New York time uses the previous trading day).",
    "nfci": "First-release value only (ALFRED vintage): published Wednesday 08:30 ET for the week ending the previous "
            "Friday; usable from nfci_known. Later revisions are deliberately not used.",
    "hy_oas_ig_oas": "ICE BofA OAS available on FRED only from 2023-10-27 (license); null before that.",
}


def _regime_limit_date(cutoff: datetime) -> date:
    local = cutoff.astimezone(NEW_YORK)
    return local.date() if (local.hour, local.minute) >= (16, 0) else local.date() - timedelta(days=1)


def get_market_regime(as_of: str | None = None) -> dict[str, Any]:
    """Latest macro/market risk-state row at or before the cutoff with percentiles within history to the cutoff."""
    path = _derived_dir() / "macro" / "panel.jsonl"
    if not path.exists():
        raise DataToolError("MACRO_PANEL_NOT_BUILT: run scripts/build-macro-panel.py")
    cutoff = _cutoff(as_of)
    limit = _regime_limit_date(cutoff).isoformat()
    rows = [r for r in _read_jsonl(path) if str(r.get("date", "")) <= limit]
    if not rows:
        raise DataToolError(f"MACRO_PANEL_EMPTY_BEFORE_CUTOFF: no panel row on or before {limit}")
    latest = max(rows, key=lambda r: r["date"])
    groups: dict[str, dict] = {}
    for group, columns in REGIME_GROUPS.items():
        block = {}
        for col in columns:
            value = latest.get(col)
            hist = [r[col] for r in rows if r.get(col) is not None]
            block[col] = {"value": value, "percentile": _percentile(hist, value) if value is not None else None,
                          "history_n": len(hist)}
        groups[group] = block
    return {
        "as_of": cutoff.isoformat(),
        "row_date": latest["date"],
        "stale_days": (_regime_limit_date(cutoff) - date.fromisoformat(latest["date"])).days,
        "groups": groups,
        "lagged_dates": {k: latest.get(k) for k in REGIME_OBS_DATES},
        "known_at_rules": KNOWN_AT_RULES,
        "history": {"first": min(r["date"] for r in rows), "last": latest["date"], "rows": len(rows)},
        "provenance": {
            "source_id": "derived-macro-panel (FRED, ALFRED NFCI first release, Yahoo chart)",
            "built_by": "scripts/build-macro-panel.py",
            "notes": ["Descriptive state only, not a signal or forecast. Percentile = share of panel history up to the "
                      "cutoff with value <= current (history since 2018-01; regimes are persistent, so effective "
                      "sample is small; hy_oas history only since 2023-10).",
                      "Validated findings and their limits live in evals/macro/; do not read a percentile as evidence "
                      "for or against a stock without them.",
                      "Target (tgt_*) columns of the panel are never returned."]},
    }


# ---------------------------------------------------------------- short interest

def get_short_interest(ticker: str, periods: int = 6, as_of: str | None = None) -> dict[str, Any]:
    """FINRA semi-monthly short interest rows usable at the cutoff (publication_date before the cutoff NY date)."""
    path = _derived_dir() / "short" / "si.jsonl"
    if not path.exists():
        raise DataToolError("SHORT_INTEREST_NOT_BUILT: run scripts/build-short-interest.py")
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
        raise DataToolError(f"TICKER_INVALID: {ticker!r}")
    periods = max(1, min(int(periods), 24))
    cutoff = _cutoff(as_of)
    cutoff_day = cutoff.astimezone(NEW_YORK).date().isoformat()
    # Usable from the trading day after publication_date: publication_date must be strictly before the cutoff day.
    rows = sorted((r for r in _read_jsonl(path) if r.get("ticker") == symbol
                   and str(r.get("publication_date", "9999")) < cutoff_day), key=lambda r: r["settlement_date"])
    if not rows:
        return {"ticker": symbol, "as_of": cutoff.isoformat(), "periods": [], "note": "NO_SHORT_INTEREST_USABLE_AT_CUTOFF"}
    dtc = [r["days_to_cover"] for r in rows if r.get("days_to_cover") is not None]
    pct_rows = [r["si_pct_shares_out"] for r in rows if r.get("si_pct_shares_out") is not None and not r.get("shares_stale")]
    out = []
    for r in rows[-periods:]:
        usable_pct = r.get("si_pct_shares_out") is not None and not r.get("shares_stale")
        out.append({
            "settlement_date": r["settlement_date"], "publication_date": r["publication_date"],
            "usable_from": "trading day after publication_date",
            "short_interest": r.get("short_interest"), "change_pct": r.get("change_pct"),
            "avg_daily_volume": r.get("avg_daily_volume"), "days_to_cover": r.get("days_to_cover"),
            "si_pct_shares_out": r.get("si_pct_shares_out"), "shares_stale": bool(r.get("shares_stale")),
            "shares_outstanding": r.get("shares_outstanding"),
            "denominator_source": r.get("shares_outstanding_source"),
            "denominator_filed": r.get("shares_outstanding_filed"),
            "split_flag": r.get("split_flag"), "revision_flag": r.get("revision_flag"),
            "chain_mismatch": bool(r.get("chain_mismatch")),
            "days_to_cover_percentile": _percentile(dtc, r["days_to_cover"]) if r.get("days_to_cover") is not None else None,
            "si_pct_percentile": _percentile(pct_rows, r["si_pct_shares_out"]) if usable_pct else None})
    latest = rows[-1]
    return {
        "ticker": symbol, "as_of": cutoff.isoformat(), "periods": out,
        "history": {"n_periods": len(rows), "first_settlement": rows[0]["settlement_date"],
                    "last_settlement": latest["settlement_date"],
                    "percentile_basis": "ticker's own periods usable at the cutoff; si_pct uses non-stale denominators only; "
                                        "needs >= 20 periods"},
        "provenance": {
            "source_id": "finra-api consolidatedShortInterest (current version)", "built_by": "scripts/build-short-interest.py",
            "notes": ["FINRA data, non-commercial research use only; do not redistribute.",
                      "Revised values only: FINRA returns the current version, the first-release value is not "
                      "recoverable (about 3% of rows were revised).",
                      "Semi-monthly position snapshot at settlement_date, published ~7 trading days later; this is not "
                      "daily short sale volume.",
                      "Share counts are not split-adjusted; change fields are unreliable around split_flag rows. "
                      "Denominator is total shares from SEC cover pages, not float; shares_stale rows or multi-class "
                      "tickers have unusable si_pct_shares_out."]}}


# ---------------------------------------------------------------- attention

STOPWORDS = set("""about after again also been before being could does doing down from have here into just like more most
much only other over said some such than that their them then there these they this those very what when which while
will with would your you the and for are but not has was were its our out all can get how may now one new per who why
stock stocks share shares today market price going still will think buy sell""".split())
TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})\.US\)")
CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")
CJK_RE = re.compile(r"[一-鿿]+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{3,}")


def _strip(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or ""))


def _union_hours(intervals: list[tuple[float, float]], lo: float, hi: float) -> float:
    clipped = sorted((max(a, lo), min(b, hi)) for a, b in intervals if min(b, hi) > max(a, lo))
    total, end = 0.0, None
    for a, b in clipped:
        if end is None or a > end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total / 3600


def _load_community(symbol: str, cutoff: datetime) -> tuple[dict[str, dict], list[tuple[float, float]], list[float]]:
    """(posts by id, covered intervals in epoch secs, snapshot retrieval times) using rows retrieved <= cutoff."""
    root = _history_dir() / "community"
    posts: dict[str, dict] = {}
    intervals: list[tuple[float, float]] = []
    retrievals: list[float] = []
    if not root.is_dir():
        return posts, intervals, retrievals
    cutoff_ts = cutoff.timestamp()
    for path in sorted(root.glob("*.jsonl")):
        for row in _read_jsonl(path):
            if row.get("ticker") != symbol or not row.get("retrieved_at"):
                continue
            retrieved = _parse_utc(row["retrieved_at"]).timestamp()
            if retrieved > cutoff_ts:
                continue
            times = []
            for p in row.get("posts") or []:
                try:
                    pt = float(p["publish_time"])
                except (KeyError, TypeError, ValueError):
                    continue
                if pt > cutoff_ts:
                    continue
                times.append(pt)
                posts.setdefault(str(p.get("id")), {**p, "_t": pt})
            span = row.get("span") or {}
            start = span.get("earliest") or (min(times) if times else None)
            if start is not None:
                # A full request (50 posts) is complete from its earliest post to retrieval time.
                intervals.append((float(start), retrieved))
            retrievals.append(retrieved)
    return posts, intervals, retrievals


def _rate(posts: dict[str, dict], intervals: list[tuple[float, float]], lo: float, hi: float) -> dict[str, Any]:
    hours = _union_hours(intervals, lo, hi)
    n = sum(1 for p in posts.values() if lo < p["_t"] <= hi)
    return {"window_hours": round((hi - lo) / 3600, 1), "covered_hours": round(hours, 1), "posts": n,
            "posts_per_covered_hour": round(n / hours, 2) if hours >= 1 else None}


def _post_text(p: dict) -> str:
    return _strip(p.get("title") or "") + " " + _strip(p.get("text") or "")


def _news(symbol: str, cutoff: datetime, limit: int = 15) -> dict | None:
    root = _history_dir() / "news"
    if not root.is_dir():
        return None
    first_seen: dict[str, str] = {}
    seen_path = root / "first-seen.jsonl"
    if seen_path.exists():
        for r in _read_jsonl(seen_path):
            nid, ts = str(r.get("news_id")), r.get("first_seen_at")
            if ts and (nid not in first_seen or ts < first_seen[nid]):
                first_seen[nid] = ts
    items: dict[str, dict] = {}
    files = [p for p in sorted(root.glob("*.jsonl")) if p.name != "first-seen.jsonl"]
    for path in files:
        for row in _read_jsonl(path):
            if row.get("ticker") != symbol or not row.get("retrieved_at") or _parse_utc(row["retrieved_at"]) > cutoff:
                continue
            for it in row.get("items") or []:
                nid = str(it.get("news_id"))
                seen = first_seen.get(nid) or row["retrieved_at"]
                pub = (it.get("publish_time") or {}).get("utc")
                if _parse_utc(seen) > cutoff or (pub and _parse_utc(pub) > cutoff) or nid in items:
                    continue
                items[nid] = {"news_id": nid, "title": it.get("title_clean"), "publish_time": pub,
                              "first_seen_at": seen, "domain": it.get("domain"), "url": it.get("url"),
                              "news_type": it.get("news_type")}
    if not files:
        return None
    ordered = sorted(items.values(), key=lambda x: x["publish_time"] or "", reverse=True)
    return {"count_known": len(ordered), "recent": ordered[:limit],
            "archive_first_file": files[0].stem, "note": "titles/URLs only; third-party headlines, reference only"}


def get_attention_snapshot(ticker: str, days: int = 7, as_of: str | None = None) -> dict[str, Any]:
    """Community post-rate, keywords and recent headlines from forward-collected moomoo archives, cutoff-filtered."""
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
        raise DataToolError(f"TICKER_INVALID: {ticker!r}")
    days = max(1, min(int(days), 60))
    cutoff = _cutoff(as_of)
    now = cutoff.timestamp()
    posts, intervals, retrievals = _load_community(symbol, cutoff)
    notes = ["Archive of community snapshots starts 2026-10-20 (moomoo stock_feed returns only the latest 50 posts, no "
             "history endpoint): coverage has gaps and percentiles rest on a short own history.",
             "Moomoo content is third-party and reference-only; posts have no author or engagement fields. No sentiment "
             "label is computed here; read titles and judge."]
    result: dict[str, Any] = {"ticker": symbol, "as_of": cutoff.isoformat(), "notes": notes}
    if not posts:
        result["community"] = None
        result["news"] = _news(symbol, cutoff)
        notes.append("NO_COMMUNITY_POSTS_AT_CUTOFF")
        return result
    last24 = _rate(posts, intervals, now - 86400, now)
    window = _rate(posts, intervals, now - days * 86400, now)
    # Own-history distribution: 24h windows ending at each earlier snapshot, with >= 12 covered hours.
    history = []
    for end in sorted(set(retrievals)):
        r = _rate(posts, intervals, end - 86400, end)
        if r["covered_hours"] >= 12 and r["posts_per_covered_hour"] is not None:
            history.append(r["posts_per_covered_hour"])
    current = last24["posts_per_covered_hour"]
    in_window = sorted((p for p in posts.values() if now - days * 86400 < p["_t"] <= now), key=lambda p: -p["_t"])
    words: Counter = Counter()
    tickers: Counter = Counter()
    cjk = 0
    for p in in_window:
        text = _post_text(p)
        found = set(p.get("mentions") or []) or {m + ".US" for m in TICKER_RE.findall(text)}
        found |= {c + ".US" for c in CASHTAG_RE.findall(text)}
        for sym in found:
            if sym.removesuffix(".US") != symbol:
                tickers[sym.removesuffix(".US")] += 1
        words.update({w.lower() for w in WORD_RE.findall(re.sub(r"\$[^$]*\$", " ", text))
                      if w.lower() not in STOPWORDS and w.lower() != symbol.lower()})
        for seq in CJK_RE.findall(text):
            words.update({seq[i:i + 2] for i in range(len(seq) - 1)})
        if p.get("cjk_ratio") is not None:
            cjk += 1 if p["cjk_ratio"] >= 0.3 else 0
    n = len(in_window)
    result["community"] = {
        "last_24h": last24, f"last_{days}d": window,
        "own_history": {"windows": len(history), "percentile_of_last_24h": _percentile_short(history, current),
                        "basis": "24h windows ending at each earlier snapshot with >= 12 covered hours"},
        "archive_coverage": {"first_post": datetime.fromtimestamp(min(p["_t"] for p in posts.values()), UTC).isoformat(),
                             "snapshots": len(retrievals), "posts_known": len(posts)},
        "cjk_share": round(cjk / n, 3) if n else None,
        "top_tickers_mentioned": tickers.most_common(10),
        "top_keywords": [(w, c) for w, c in words.most_common(30) if c >= 2][:15],
        "recent_titles": [{"publish_time": datetime.fromtimestamp(p["_t"], UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "title": (_strip(p.get("title") or "") or _strip(p.get("text") or ""))[:140].strip()}
                          for p in in_window[:10]]}
    result["news"] = _news(symbol, cutoff)
    if result["news"] is None:
        notes.append("NEWS_ARCHIVE_ABSENT: .local/data/history/news/ not found; no news headlines returned")
    return result


def _percentile_short(history: list[float], value: float | None) -> float | None:
    """Percentile within a short own history (needs >= 5 windows); reported with the window count by the caller."""
    if value is None or len(history) < 5:
        return None
    return round(100 * sum(1 for h in history if h <= value) / len(history), 1)
