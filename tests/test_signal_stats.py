"""signal_stats 与 get_signal_stats：同日横截面百分位、时点过滤、新事件表的信号。"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from product.deterministic import signal_stats
from product.mcp import reference_tools


def _ev(x, date="2024-03-01", ticker="AAA", h="20", exit_date="2024-03-29"):
    return {"signal": "s", "ticker": ticker, "entry_date": date, "excess": {h: x}, "exit_dates": {h: exit_date}}


class PercentileTests(unittest.TestCase):
    def test_mid_rank_with_ties(self):
        pool = sorted([0.0] * 10 + [1.0] * 10)
        self.assertEqual(signal_stats.percentile(pool, 2.0), 1.0)
        self.assertEqual(signal_stats.percentile(pool, -1.0), 0.0)
        self.assertEqual(signal_stats.percentile(pool, 0.0), 0.25)  # ties share the middle of ranks 0..10
        self.assertEqual(signal_stats.percentile(pool, 1.0), 0.75)

    def test_matched_uses_rank_not_mean_and_date_gap(self):
        pool = {"2024-03-01": [float(i) for i in range(10)] + [1000.0]}  # extreme winner would skew a mean
        hit = signal_stats.matched([_ev(5.5)], pool, "20")
        self.assertAlmostEqual(hit[0]["pct_minus_50"], 6 / 11 - 0.5)
        self.assertTrue(signal_stats.matched([_ev(5.5, date="2024-03-08")], pool, "20"))  # 7 days matches
        self.assertFalse(signal_stats.matched([_ev(5.5, date="2024-03-09")], pool, "20"))  # 8 days dropped
        self.assertFalse(signal_stats.matched([_ev(5.5, date="2024-02-28")], pool, "20"))  # control is later
        self.assertFalse(signal_stats.matched([_ev(5.5)], {"2024-03-01": [1.0] * 9}, "20"))  # < 10 values


class GetSignalStatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        cache = mock.Mock(root=root)
        patches = [mock.patch.object(reference_tools.settings, "cache", lambda: cache),
                   mock.patch.object(reference_tools, "_cutoff",
                                     lambda as_of: datetime.fromisoformat(as_of + "T12:00:00+00:00"))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        reference_tools._EVENTS.clear()
        self.addCleanup(reference_tools._EVENTS.clear)
        self.addCleanup(self.tmp.cleanup)
        controls = [{"kind": "control", "ticker": f"C{i}", "entry_date": d, "stage": "other",
                     "20": i / 100, "exit_20": e}
                    for d, e in (("2024-03-01", "2024-03-29"), ("2024-06-03", "2024-07-01")) for i in range(20)]
        events = [{"kind": "event", "ticker": t, "entry_date": d, "bucket": "strong_up", "stage": "other",
                   "volume_ratio": v, "20": 0.5, "exit_20": e}
                  for t, d, e, v in (("T1", "2024-03-01", "2024-03-29", 2.5), ("T2", "2024-06-03", "2024-07-01", 1.0))]
        insider = [{"kind": "event", "signal": "insider_buy_officer", "ticker": "T1", "entry_date": "2024-03-01",
                    "20": 0.5, "exit_20": "2024-03-29"}]
        self._write("events-pead.jsonl", controls + events, "meta-pead.json")
        self._write("events-insider.jsonl", insider, "meta-insider.json")

    def _write(self, name, rows, meta):
        d = Path(self.tmp.name) / "derived" / "signals"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        (d / meta).write_text(json.dumps({"built_at": "t", "universe_note": ""}))

    def test_pead_signal_and_point_in_time(self):
        r = reference_tools.get_signal_stats("pead_strong_up", 20, as_of="2025-01-01")
        self.assertEqual(r["summary"]["n"], 2)
        self.assertAlmostEqual(r["summary"]["mean_percentile_minus_50"], 50.0)  # 0.5 beats every control
        self.assertEqual(reference_tools.get_signal_stats("pead_strong_up", 20, as_of="2024-04-01")["summary"]["n"], 1)
        # exit date == cutoff is excluded
        self.assertEqual(reference_tools.get_signal_stats("pead_strong_up", 20, as_of="2024-03-29")["summary"]["n"], 0)

    def test_high_volume_and_insider(self):
        self.assertEqual(reference_tools.get_signal_stats("pead_strong_up_high_volume", 20,
                                                          as_of="2025-01-01")["summary"]["n"], 1)
        r = reference_tools.get_signal_stats("insider_buy_officer", 20, as_of="2025-01-01")
        self.assertEqual(r["summary"]["n"], 1)
        self.assertEqual(r["status"], "需要验证")  # below 30 events
        with self.assertRaises(reference_tools.DataToolError):
            reference_tools.get_signal_stats("insider_buy_officer", 1, as_of="2025-01-01")
        with self.assertRaises(reference_tools.DataToolError):
            reference_tools.get_signal_stats("nope", 20)


if __name__ == "__main__":
    unittest.main()
