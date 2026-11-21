"""Offline tests for the next-session-open entry rule (outcome_open) and its use in get_key_moments."""
import importlib.util
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from product.deterministic import key_moments as km
from product.mcp import reference_tools


def series(n=100):
    dates = [f"2020-{1 + d // 28:02d}-{1 + d % 28:02d}" for d in range(n)]  # labels only, strictly increasing
    opens = [100.0 + d for d in range(n)]
    closes = [100.5 + d for d in range(n)]
    return dates, opens, closes


class OutcomeOpenTest(unittest.TestCase):
    def test_entry_is_next_open_exit_is_close_of_day_h_with_entry_day_as_day_one(self):
        dates, opens, closes = series()
        bench_open = {d: 50.0 for d in dates}
        bench_close = {d: 50.0 for d in dates}
        i = 10
        out = km.outcome_open(dates, opens, closes, bench_open, bench_close, i)
        self.assertEqual(out["entry_date"], dates[11])
        entry = opens[11]  # 111.0
        for h in km.HORIZONS:
            cell = out[str(h)]
            self.assertEqual(cell["exit_date"], dates[i + h])  # entry day is day 1
            self.assertAlmostEqual(cell["ret"], closes[i + h] / entry - 1, places=5)
            self.assertAlmostEqual(cell["excess"], cell["ret"], places=5)  # flat benchmark
            self.assertAlmostEqual(cell["worst"], closes[11] / entry - 1, places=5)  # rising series: lowest close is day 1

    def test_hand_computed_values_with_benchmark_and_a_dip(self):
        dates = [f"d{k}" for k in range(10)]
        opens = [10, 10, 20, 20, 20, 20, 20, 20, 20, 20]
        closes = [10, 10, 25, 15, 30, 30, 30, 30, 30, 30]
        i = 1  # moment on d1; entry = d2 open = 20; day 5 = d6 close = 30
        bench_open = {"d2": 100.0}
        bench_close = {"d6": 110.0}
        with mock.patch.object(km, "HORIZONS", (5,)):
            out = km.outcome_open(dates, opens, closes, bench_open, bench_close, i)
        cell = out["5"]
        self.assertEqual(out["entry_date"], "d2")
        self.assertEqual(cell["exit_date"], "d6")
        self.assertEqual(cell["ret"], 0.5)                    # 30 / 20 - 1
        self.assertEqual(cell["excess"], 0.4)                 # 0.5 - (110 / 100 - 1)
        self.assertEqual(cell["worst"], -0.25)                # lowest close d2..d6 is 15 on d3: 15 / 20 - 1

    def test_worst_can_be_positive_when_every_close_is_above_the_open(self):
        dates = [f"d{k}" for k in range(8)]
        opens = [10, 10, 10, 10, 10, 10, 10, 10]
        closes = [10, 10, 12, 13, 14, 15, 16, 17]
        with mock.patch.object(km, "HORIZONS", (5,)):
            cell = km.outcome_open(dates, opens, closes, {}, {}, 1)["5"]
        self.assertEqual(cell["worst"], 0.2)

    def test_missing_prices_return_none_and_nothing_is_substituted(self):
        dates, opens, closes = series()
        bench = {d: 50.0 for d in dates}
        i = 10
        # no entry open -> every horizon None, and the close is not used instead
        no_open = list(opens)
        no_open[11] = None
        out = km.outcome_open(dates, no_open, closes, bench, bench, i)
        self.assertEqual(out["entry_date"], dates[11])
        self.assertTrue(all(out[str(h)] is None for h in km.HORIZONS))
        # missing exit close only hurts that horizon
        no_close = list(closes)
        no_close[i + 20] = None
        out = km.outcome_open(dates, opens, no_close, bench, bench, i)
        self.assertIsNone(out["20"])
        self.assertIsNotNone(out["5"])
        self.assertIsNotNone(out["60"])
        # missing benchmark keeps the stock cell with excess None
        out = km.outcome_open(dates, opens, closes, {}, bench, i)
        self.assertIsNotNone(out["20"]["ret"])
        self.assertIsNone(out["20"]["excess"])
        # window beyond the data
        out = km.outcome_open(dates, opens, closes, bench, bench, 90)
        self.assertIsNone(out["20"])
        self.assertIsNone(out["60"])

    def test_last_session_has_no_entry(self):
        dates, opens, closes = series()
        out = km.outcome_open(dates, opens, closes, {}, {}, len(dates) - 1)
        self.assertIsNone(out["entry_date"])
        self.assertTrue(all(out[str(h)] is None for h in km.HORIZONS))

    def test_legacy_outcome_is_unchanged(self):
        dates, opens, closes = series()
        bench = {d: 50.0 for d in dates}
        out = km.outcome(dates, closes, bench, 10)
        self.assertEqual(out["entry_date"], dates[11])
        self.assertEqual(out["5"]["exit_date"], dates[16])  # next close + h sessions
        self.assertEqual(out["5"]["ret"], round(closes[16] / closes[11] - 1, 5))


ROWS = [  # date, open, high, low, close, adj_close, volume
    ["d0", "10", "11", "9", "10", "5", "1"],
    ["d1", "10", "11", "9", "10", None, "1"],    # adj_close missing: legacy series falls back to close, strict ones do not
    ["d2", None, "11", "9", "10", "5", "1"],     # open missing
    ["d3", "20", "21", "19", "20", "10", "1"],
    ["d4", "20", "21", "19", None, None, "1"],   # no close at all: dropped from every series
]


def load_build_script():
    spec = importlib.util.spec_from_file_location("build_key_moments", Path(__file__).resolve().parents[1] / "scripts/build-key-moments.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PriceLayerIsStrictTest(unittest.TestCase):
    def test_price_series_never_substitutes_close_for_adjusted_values(self):
        dates, closes, opens_adj, closes_adj = km.price_series(ROWS)
        self.assertEqual(dates, ["d0", "d1", "d2", "d3"])
        self.assertEqual(closes, [5.0, 10.0, 5.0, 10.0])          # legacy: adj_close, else close
        self.assertEqual(closes_adj, [5.0, None, 5.0, 10.0])      # strict: adj_close only
        self.assertEqual(opens_adj, [5.0, None, None, 10.0])      # open x adj / close; None if any of the three is missing

    def test_build_script_price_layer_does_not_substitute(self):
        build = load_build_script()
        with mock.patch.object(build.data_tools, "get_price_history", return_value={"rows": ROWS}):
            dates, closes, opens_adj, closes_adj = build.prices("AAA", "2020-01-01", "2020-12-31")
        self.assertEqual(closes_adj[1], None)
        self.assertEqual(closes[1], 10.0)  # legacy series (and so legacy `outcome`) keeps the fallback
        self.assertEqual(opens_adj[1], None)
        # and the strict values flow into outcome_open: a missing exit adj_close is None, not the plain close
        bench = {d: 1.0 for d in dates}
        with mock.patch.object(km, "HORIZONS", (1,)):
            cell = km.outcome_open(dates, opens_adj, closes_adj, bench, bench, 0)["1"]
        self.assertIsNone(cell)  # entry d1 has no adjusted open

    def test_missing_adjusted_close_on_the_path_or_exit(self):
        dates = [f"d{k}" for k in range(6)]
        opens = [10.0] * 6
        closes = [10.0, 10.0, 12.0, None, 14.0, 15.0]
        with mock.patch.object(km, "HORIZONS", (3, 4)):
            out = km.outcome_open(dates, opens, closes, {}, {}, 0)
        self.assertIsNone(out["3"])                  # exit close (d3) missing: no substitute
        self.assertEqual(out["4"]["worst"], 0.0)     # missing close on the path is ignored, none invented
        self.assertEqual(out["4"]["ret"], 0.4)


class GetKeyMomentsReadsOpenOutcomeTest(unittest.TestCase):
    def test_statistics_use_outcome_open_and_provenance_says_so(self):
        n = 300
        dates = [f"{2019 + d // 250}-{1 + (d % 250) // 21:02d}-{1 + (d % 250) % 21:02d}" for d in range(n)]
        closes = [100.0 + 0.01 * d for d in range(n)]
        rows = [[d, str(c), str(c), str(c), str(c), str(c), "1"] for d, c in zip(dates, closes)]
        legacy = {"entry_date": "x", "5": {"exit_date": "2000-01-01", "ret": 0.5, "excess": 0.5, "worst": 0.0}}
        opened = {"entry_date": "x", "5": {"exit_date": "2000-01-01", "ret": -0.02, "excess": -0.01, "worst": -0.03}}
        event = {"moment": km.BASELINE, "ticker": "AAA", "date": "2000-01-01", "outcome": legacy, "outcome_open": opened}
        meta = {"built_at": "t", "start": "2012-01-01"}
        with mock.patch("product.mcp.data_tools.get_price_history", return_value={"rows": rows}), \
                mock.patch.object(reference_tools, "_key_moment_events", return_value=({km.BASELINE: [event]}, meta)):
            result = reference_tools.get_key_moments("AAA", days=5, as_of="2021-06-30")
        base = result["baseline_any_day"]["5d"]
        self.assertEqual(base["n"], 1)
        self.assertEqual(base["ret_pct_q25_median_q75"][1], -2.0)  # from outcome_open, not the legacy +50
        self.assertIn("next session open", result["provenance"]["notes"])

    def test_todays_row_is_not_used_before_the_close(self):
        n = 300
        dates = [f"{2019 + d // 250}-{1 + (d % 250) // 21:02d}-{1 + (d % 250) % 21:02d}" for d in range(n)]
        rows = [[d, "100", "100", "100", "100", "100", "1"] for d in dates]
        seen = {}
        real_state = km.state

        def spy(ds, cs):
            seen["last"] = ds[-1]
            return real_state(ds, cs)

        def run(now, as_of):
            fake = datetime.fromisoformat(now).astimezone(UTC)
            with mock.patch("product.mcp.data_tools.get_price_history", return_value={"rows": rows}), \
                    mock.patch.object(reference_tools, "_key_moment_events", return_value=({}, {"start": "2012"})), \
                    mock.patch.object(km, "state", spy), \
                    mock.patch("product.mcp.reference_tools._cutoff", return_value=fake):
                reference_tools.get_key_moments("AAA", days=5, as_of=as_of)
            return seen["last"]

        today = dates[-1]
        self.assertEqual(run(f"{today}T14:00:00-05:00", None), dates[-2])   # before 16:00 New York: today's row is dropped
        self.assertEqual(run(f"{today}T16:30:00-05:00", None), today)       # after the close: used
        self.assertEqual(run(f"{today}T09:35:00-05:00", f"{today}T09:35:00-05:00"), dates[-2])  # replay at an intraday as_of


if __name__ == "__main__":
    unittest.main()
