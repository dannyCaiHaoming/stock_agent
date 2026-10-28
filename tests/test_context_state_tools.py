import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from product.mcp import context_state_tools as cst
from product.mcp.data_tools import DataToolError


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.derived, self.history = self.tmp / "derived", self.tmp / "history"
        for name, target in (("_derived_dir", self.derived), ("_history_dir", self.history)):
            patcher = mock.patch.object(cst, name, return_value=target)
            patcher.start()
            self.addCleanup(patcher.stop)


class RegimeTest(Base):
    def test_not_built(self):
        with self.assertRaises(DataToolError) as ctx:
            cst.get_market_regime("2026-01-05")
        self.assertIn("MACRO_PANEL_NOT_BUILT", str(ctx.exception))

    def test_no_targets_no_future_rows(self):
        rows = []
        for i in range(40):
            d = (datetime(2026, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d")
            rows.append({"date": d, "vix": 10.0 + i, "vix_chg5": 1.0, "dfii10": 1.0, "dfii10_obs": "2025-12-31",
                         "tgt_spy_fwd5": 0.05, "tgt_spy_rv20": 0.2, "nfci": -0.5, "nfci_known": "2026-01-02"})
        write_jsonl(self.derived / "macro" / "panel.jsonl", rows)
        out = cst.get_market_regime("2026-01-30")
        self.assertEqual(out["row_date"], "2026-01-30")
        self.assertNotIn("tgt_", json.dumps(out["groups"]) + json.dumps(out["lagged_dates"]))
        vix = out["groups"]["volatility"]["vix"]
        self.assertEqual(vix["value"], 39.0)
        self.assertEqual(vix["history_n"], 30)  # rows after the cutoff are not in the percentile history
        self.assertEqual(vix["percentile"], 100.0)
        self.assertEqual(out["lagged_dates"]["dfii10_obs"], "2025-12-31")
        self.assertIsNone(out["groups"]["credit"]["hy_oas"]["value"])

    def test_intraday_cutoff_uses_previous_close(self):
        rows = [{"date": f"2026-01-{d:02d}", "vix": float(d)} for d in range(1, 29)]
        write_jsonl(self.derived / "macro" / "panel.jsonl", rows)
        # 2026-01-20 12:00 New York = 17:00Z: the 01-20 close is not known yet
        out = cst.get_market_regime("2026-01-20T17:00:00Z")
        self.assertEqual(out["row_date"], "2026-01-19")


class ShortTest(Base):
    def rows(self):
        base = {"ticker": "MU", "short_interest": 100, "change_pct": 1.0, "avg_daily_volume": 10, "shares_stale": False,
                "shares_outstanding_source": "sec", "split_flag": None, "revision_flag": None}
        out = []
        for i in range(25):
            settle = (datetime(2024, 1, 1) + timedelta(days=15 * i)).strftime("%Y-%m-%d")
            pub = (datetime(2024, 1, 1) + timedelta(days=15 * i + 10)).strftime("%Y-%m-%d")
            out.append({**base, "settlement_date": settle, "publication_date": pub, "days_to_cover": 1.0 + i,
                        "si_pct_shares_out": 1.0 + i})
        return out

    def test_publication_lag(self):
        write_jsonl(self.derived / "short" / "si.jsonl", self.rows())
        rows = self.rows()
        pub = rows[10]["publication_date"]
        same_day = cst.get_short_interest("mu", periods=3, as_of=pub)
        self.assertEqual(same_day["periods"][-1]["settlement_date"], rows[9]["settlement_date"])  # not usable on pub day
        next_day = (datetime.fromisoformat(pub) + timedelta(days=1)).strftime("%Y-%m-%d")
        later = cst.get_short_interest("MU", periods=3, as_of=next_day)
        last = later["periods"][-1]
        self.assertEqual(last["settlement_date"], rows[10]["settlement_date"])
        self.assertEqual(len(later["periods"]), 3)
        self.assertIsNone(last["days_to_cover_percentile"])  # only 11 periods of history

    def test_percentile_and_stale(self):
        rows = self.rows()
        rows[-1]["shares_stale"] = True
        write_jsonl(self.derived / "short" / "si.jsonl", rows)
        out = cst.get_short_interest("MU", periods=1, as_of="2026-10-27")
        p = out["periods"][0]
        self.assertEqual(p["days_to_cover_percentile"], 100.0)
        self.assertIsNone(p["si_pct_percentile"])
        self.assertTrue(p["shares_stale"])

    def test_unknown_ticker(self):
        write_jsonl(self.derived / "short" / "si.jsonl", self.rows())
        self.assertEqual(cst.get_short_interest("ZZZ", as_of="2026-10-27")["periods"], [])


class AttentionTest(Base):
    def snapshot(self, retrieved, ids_times, span_start=None):
        return {"ticker": "NVDA", "retrieved_at": retrieved.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "span": {"earliest": span_start or min(t for _, t in ids_times), "latest": max(t for _, t in ids_times)},
                "posts": [{"id": i, "publish_time": str(int(t)), "title": f"$NVIDIA (NVDA.US)$ Blackwell demand {i} $Micron(MU.US)$",
                           "text": "", "mentions": ["NVDA.US", "MU.US"], "cjk_ratio": 0.0} for i, t in ids_times]}

    def test_cutoff_filtering_and_dedupe(self):
        t0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        s1 = self.snapshot(t0, [("1", t0.timestamp() - 7200), ("2", t0.timestamp() - 3600)])
        t1 = t0 + timedelta(hours=6)
        s2 = self.snapshot(t1, [("2", t0.timestamp() - 3600), ("3", t1.timestamp() - 600)])
        write_jsonl(self.history / "community" / "2026-10-21.jsonl", [s1, s2])
        out = cst.get_attention_snapshot("NVDA", days=1, as_of="2026-10-21T13:00:00Z")
        c = out["community"]
        self.assertEqual(c["archive_coverage"]["posts_known"], 2)  # later snapshot and post 3 invisible
        self.assertEqual(c["last_24h"]["posts"], 2)
        self.assertEqual(c["last_24h"]["covered_hours"], 2.0)  # only the covered span, not 24h
        self.assertEqual(c["top_tickers_mentioned"][0], ("MU", 2))
        later = cst.get_attention_snapshot("NVDA", days=1, as_of="2026-10-22T00:00:00Z")
        self.assertEqual(later["community"]["last_24h"]["posts"], 3)
        self.assertIsNone(later["news"])
        self.assertTrue(any("NEWS_ARCHIVE_ABSENT" in n for n in later["notes"]))

    def test_news_first_seen_filter(self):
        t0 = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
        write_jsonl(self.history / "community" / "2026-10-21.jsonl", [self.snapshot(t0, [("1", t0.timestamp() - 60)])])
        item = lambda nid: {"news_id": nid, "title_clean": f"headline {nid}", "publish_time": {"utc": "2026-10-21T10:00:00Z"},
                            "url": "http://x", "domain": "x", "news_type": 1}
        write_jsonl(self.history / "news" / "2026-10-21.jsonl", [
            {"ticker": "NVDA", "retrieved_at": "2026-10-21T15:00:00Z", "items": [item("a"), item("b")]}])
        write_jsonl(self.history / "news" / "first-seen.jsonl", [
            {"news_id": "a", "first_seen_at": "2026-10-21T12:00:00Z"}, {"news_id": "b", "first_seen_at": "2026-10-21T15:00:00Z"}])
        out = cst.get_attention_snapshot("NVDA", as_of="2026-10-21T13:00:00Z")
        self.assertEqual(out["news"]["count_known"], 0)  # the only news row was retrieved after the cutoff
        out = cst.get_attention_snapshot("NVDA", as_of="2026-10-21T20:00:00Z")
        self.assertEqual({n["news_id"] for n in out["news"]["recent"]}, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
