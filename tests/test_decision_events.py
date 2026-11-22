import random
import statistics
import unittest
from datetime import date, timedelta
from unittest import mock

from product.deterministic import decision_events as de
from product.mcp import decision_tools


def weekdays(n: int, start: date = date(2025, 1, 2)) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def walk(n: int, tail: list[float] | None = None) -> tuple[list[str], dict[str, float], dict[str, float]]:
    """Stock alternating +1% / -1% (vol ~1%), flat benchmark, then optional extra daily returns for the stock."""
    dates = weekdays(n)
    stock, bench, s = {}, {}, 100.0
    for k, d in enumerate(dates):
        r = (tail[k - (n - len(tail))] if tail and k >= n - len(tail) else (0.01 if k % 2 else -0.01))
        s *= 1 + r
        stock[d], bench[d] = s, 100.0
    return dates, stock, bench


def moment(dates, i, name="platform_breakdown"):
    return {"moment": name, "date": dates[i], "index": i, "detail": {}}


def original_deviation(p, b, dates, i, window=5):
    """scripts/sample-idiosyncratic-moments.py `deviation`, as it was before the move (prices already loaded)."""
    day = dates[i]
    if day not in p:
        return None
    if i < 121:
        return None
    rets = [p[dates[k]] / p[dates[k - 1]] - 1 for k in range(i - 120, i - window + 1)]
    vol = statistics.pstdev(rets)
    d0 = dates[i - window]
    if not vol or d0 not in b or day not in b:
        return None
    excess = (p[day] / p[d0] - 1) - (b[day] / b[d0] - 1)
    return excess / (vol * window ** 0.5)


class DeviationTests(unittest.TestCase):
    def test_equals_the_original_on_random_series(self):
        rng = random.Random(3)
        dates = weekdays(400)
        p, b, ps, bs = {}, {}, 50.0, 80.0
        for d in dates:
            ps *= 1 + rng.gauss(0, 0.02)
            bs *= 1 + rng.gauss(0, 0.01)
            p[d], b[d] = ps, bs
        checked = 0
        for i in range(len(dates)):
            self.assertEqual(de.deviation_z(p, b, dates, i), original_deviation(p, b, dates, i))
            checked += i >= 121
        self.assertGreater(checked, 200)

    def test_none_when_history_short_vol_zero_or_benchmark_missing(self):
        dates, stock, bench = walk(200)
        self.assertIsNone(de.deviation_z(stock, bench, dates, 120))
        self.assertIsNotNone(de.deviation_z(stock, bench, dates, 121))
        flat = {d: 100.0 for d in dates}
        self.assertIsNone(de.deviation_z(flat, bench, dates, 150))
        gap = dict(bench)
        del gap[dates[145]]  # D0 of i = 150
        self.assertIsNone(de.deviation_z(stock, gap, dates, 150))

    def test_sign_follows_the_relative_move(self):
        dates, stock, bench = walk(300, tail=[0, 0, 0, 0, -0.10])
        self.assertLess(de.deviation_z(stock, bench, dates, 299), -2)
        dates, stock, bench = walk(300, tail=[0, 0, 0, 0, 0.10])
        self.assertGreater(de.deviation_z(stock, bench, dates, 299), 2)


class PeadD0Tests(unittest.TestCase):
    # 2025-01-02 Thu, 03 Fri, 06 Mon, 07 Tue ...
    dates = weekdays(10)

    def test_before_open_same_day_is_d0(self):
        self.assertEqual(de.pead_d0("2025-01-06T07:30", self.dates), (1, 2))
        self.assertEqual(de.pead_d0("2025-01-06T09:29", self.dates), (1, 2))

    def test_intraday_d0_is_next_session(self):
        self.assertEqual(de.pead_d0("2025-01-06T09:30", self.dates), (1, 3))
        self.assertEqual(de.pead_d0("2025-01-06T15:59", self.dates), (1, 3))

    def test_after_close_d0_is_next_session_and_p_is_that_day(self):
        self.assertEqual(de.pead_d0("2025-01-06T16:00", self.dates), (2, 3))
        self.assertEqual(de.pead_d0("2025-01-03T17:30", self.dates), (1, 2))  # Friday evening -> Monday

    def test_non_trading_day_uses_last_session_before_it(self):
        self.assertEqual(de.pead_d0("2025-01-04T10:00", self.dates), (1, 2))  # Saturday
        self.assertEqual(de.pead_d0("2025-01-05T22:00", self.dates), (1, 2))  # Sunday

    def test_exclusions(self):
        self.assertEqual(de.pead_d0("2025-01-06", self.dates), "no_time")
        self.assertEqual(de.pead_d0("2024-12-30T10:00", self.dates), "outside_price_calendar")
        self.assertEqual(de.pead_d0("2025-02-10T10:00", self.dates), "outside_price_calendar")
        self.assertEqual(de.pead_d0("2025-01-02T07:00", self.dates), "insufficient_history")

    def test_d0_can_be_beyond_the_last_session(self):
        self.assertEqual(de.pead_d0("2025-01-14T17:00", weekdays(9)), (8, 9))


class ClassifyTests(unittest.TestCase):
    N = 300

    def run_case(self, tail, moments=(), earnings=(), bench=True, lookback=3, n=None):
        dates, stock, b = walk(n or self.N, tail=tail)
        ms = [moment(dates, i) if isinstance(i, int) else moment(dates, *i) for i in moments]
        es = [{"accession": a, "accepted_ny": dates[i] + t} for a, i, t in earnings]
        return dates, de.classify(dates, stock, b if bench else None, ms, es, lookback_sessions=lookback)

    def test_e2_down_is_group_e2_with_reduce(self):
        dates, r = self.run_case([0, 0, 0, 0, -0.10], moments=[self.N - 1])
        self.assertEqual((r["group"], r["horizon_days"], r["b1_action"]), ("E2", 60, "REDUCE"))
        self.assertEqual((r["e2"]["direction"], r["e2"]["date"], r["event_date"]), ("down", dates[-1], dates[-1]))
        self.assertLess(r["e2"]["deviation_z"], -2)
        self.assertEqual((r["overlap"], r["late_sessions"], r["e1"]), (False, 0, None))

    def test_e2_up_is_hold(self):
        _, r = self.run_case([0, 0, 0, 0, 0.10], moments=[self.N - 1])
        self.assertEqual((r["group"], r["b1_action"], r["e2"]["direction"]), ("E2", "HOLD", "up"))

    def test_moment_with_small_deviation_is_not_e2(self):
        _, r = self.run_case([0, 0, 0, 0, -0.01], moments=[self.N - 1])
        self.assertEqual((r["group"], r["horizon_days"], r["b1_action"]), ("E0", 60, "HOLD"))

    def test_e1_earnings_drop_uses_20_sessions_and_reduces(self):
        dates, r = self.run_case([-0.08], earnings=[("A1", self.N - 2, "T17:00")])  # accepted after close -> D0 = last
        self.assertEqual((r["group"], r["horizon_days"], r["b1_action"]), ("E1", 20, "REDUCE"))
        self.assertEqual((r["e1"]["accession"], r["e1"]["d0"], r["event_date"]), ("A1", dates[-1], dates[-1]))
        self.assertLess(r["e1"]["reaction_excess"], -0.05)
        self.assertIsNone(r["e2"])

    def test_small_earnings_reaction_is_not_e1(self):
        _, r = self.run_case([-0.03], earnings=[("A1", self.N - 2, "T17:00")])
        self.assertEqual(r["group"], "E0")

    def test_overlap_goes_to_e2(self):
        _, r = self.run_case([0, 0, 0, 0, -0.10], moments=[self.N - 1], earnings=[("A1", self.N - 2, "T17:00")])
        self.assertEqual((r["group"], r["horizon_days"], r["overlap"]), ("E2", 60, True))
        self.assertEqual(r["e1"]["accession"], "A1")
        self.assertEqual(r["b1_action"], "REDUCE")

    def test_e2_then_e1_on_a_later_day_is_e1_without_overlap(self):
        # E2 at index N-3 (drop persists), earnings D0 = last session with a further -8% reaction
        dates, stock, b = walk(self.N, tail=[0, 0, -0.10, 0, -0.08])
        ms = [moment(dates, self.N - 3)]
        es = [{"accession": "A1", "accepted_ny": dates[self.N - 2] + "T17:00"}]
        r = de.classify(dates, stock, b, ms, es, lookback_sessions=3)
        self.assertEqual((r["group"], r["overlap"], r["event_date"], r["late_sessions"]), ("E1", False, dates[-1], 0))
        self.assertIsNone(r["e2"])
        self.assertEqual((r["horizon_days"], r["b1_action"]), (20, "REDUCE"))

    def test_e1_then_e2_on_a_later_day_is_e2_without_overlap(self):
        dates, stock, b = walk(self.N, tail=[-0.08, 0, 0, 0, -0.10])
        es = [{"accession": "A1", "accepted_ny": dates[self.N - 6] + "T17:00"}]  # D0 = N-5
        ms = [moment(dates, self.N - 1)]
        r = de.classify(dates, stock, b, ms, es, lookback_sessions=6)
        self.assertEqual((r["group"], r["overlap"], r["event_date"], r["late_sessions"]), ("E2", False, dates[-1], 0))
        self.assertIsNone(r["e1"])
        self.assertEqual((r["horizon_days"], r["e2"]["direction"]), (60, "down"))

    def test_same_day_e1_and_e2_is_overlap_and_keeps_e1(self):
        dates, stock, b = walk(self.N, tail=[0, 0, 0, 0, -0.10])
        es = [{"accession": "A1", "accepted_ny": dates[self.N - 2] + "T17:00"}]
        r = de.classify(dates, stock, b, [moment(dates, self.N - 1)], es)
        self.assertEqual((r["group"], r["overlap"], r["e1"]["d0"], r["e2"]["date"]), ("E2", True, dates[-1], dates[-1]))

    def test_e0_when_nothing_qualifies(self):
        dates, r = self.run_case(None)
        self.assertEqual((r["group"], r["horizon_days"], r["event_date"], r["late_sessions"], r["b1_action"]),
                         ("E0", 60, dates[-1], 0, "HOLD"))

    def test_no_sector_cannot_be_e2_or_e1(self):
        _, r = self.run_case([0, 0, 0, 0, -0.10], moments=[self.N - 1], earnings=[("A1", self.N - 2, "T17:00")],
                             bench=False)
        self.assertEqual((r["group"], r["overlap"], r["e2"], r["e1"]), ("E0", False, None, None))

    def test_e1_ignores_everything_after_d0_close(self):
        n = self.N
        dates, stock, b = walk(n, tail=[-0.08, 0, 0, 0])
        d0 = n - 4
        es = [{"accession": "A1", "accepted_ny": dates[d0 - 1] + "T17:00"}]
        base = de.classify(dates[:d0 + 1], stock, b, [], es, lookback_sessions=3)
        self.assertEqual(base["group"], "E1")
        polluted, bp = dict(stock), dict(b)
        for d in dates[d0 + 1:]:
            polluted[d], bp[d] = 1e-6, 1e9  # prices after D0 that would flip any reaction
        again = de.classify(dates[:d0 + 1], polluted, bp, [], es, lookback_sessions=3)
        self.assertEqual(again, base)
        # D0 close later than as_of: accepted after the last session's close -> D0 not observed -> no E1
        late = de.classify(dates[:d0 + 1], stock, b, [], [{"accession": "A2", "accepted_ny": dates[d0] + "T17:00"}])
        self.assertEqual(late["group"], "E0")

    def test_lookback_window_and_late_sessions(self):
        tail = [0, 0, 0, 0, -0.10, 0, 0, 0]
        dates, r = self.run_case(tail, moments=[self.N - 4], lookback=3)
        self.assertEqual(r["group"], "E0")  # event is 3 sessions back: outside a 3-session window
        dates, r = self.run_case(tail, moments=[self.N - 4], lookback=4)
        self.assertEqual((r["group"], r["late_sessions"], r["event_date"]), ("E2", 3, dates[-4]))

    def test_most_recent_candidate_wins_and_same_day_takes_first_moment(self):
        n = self.N
        tail = [0, 0, 0, 0, -0.10, 0, 0, 0]
        dates, stock, b = walk(n, tail=tail)
        ms = [moment(dates, n - 3, "platform_breakdown"), moment(dates, n - 1, "failed_breakout"),
              moment(dates, n - 1, "uptrend_break"), moment(dates, n - 1, "baseline_days")]
        r = de.classify(dates, stock, b, ms, [], lookback_sessions=3)
        self.assertEqual((r["group"], r["e2"]["moment"], r["event_date"]), ("E2", "failed_breakout", dates[-1]))

    def test_duplicate_8k_for_same_d0_counts_once(self):
        n = self.N
        dates, stock, b = walk(n, tail=[-0.08])
        es = [{"accession": "A2", "accepted_ny": dates[n - 2] + "T18:00"},
              {"accession": "A1", "accepted_ny": dates[n - 2] + "T17:00"}]
        r = de.classify(dates, stock, b, [], es)
        self.assertEqual(r["e1"]["accession"], "A1")


def price_rows(dates, closes, ticker):
    return [[d, closes[d], closes[d], closes[d], closes[d], closes[d], 1000] for d in dates]


class ClassifyDecisionEventTests(unittest.TestCase):
    """The MCP function with mocked data tools (no network, nothing written)."""

    def setUp(self):
        self.dates = [d for d in weekdays(900, date(2023, 7, 3)) if d <= "2026-06-30"]
        self.n = len(self.dates)
        _, self.stock, self.bench = walk_over(self.dates, tail=[-0.08])

    def run_tool(self, as_of, benchmark="XLK", filings=None):
        def history(ticker, start=None, end=None, as_of=None, max_rows=1200, **_):
            src = self.stock if ticker == "ABC" else self.bench
            rows = [r for r in price_rows(self.dates, src, ticker) if (start or "") <= r[0] <= (end or "9999")]
            return {"rows": rows, "provenance": {"source_id": f"yahoo-chart:{ticker}", "as_of": rows[-1][0],
                                                 "retrieved_at": "2026-11-22T00:00:00Z"}}

        def list_filings(ticker, forms=None, limit=20, as_of=None):
            rows = filings if filings is not None else [
                ["acc-1", "8-K", "2026-06-29", "2026-06-29T21:00:00Z", "http://x", "2.02,9.01"],
                ["acc-0", "8-K", "2026-06-01", "2026-06-01T11:00:00Z", "http://x", "5.02"]]
            return {"rows": rows, "provenance": {"source_id": "sec-submissions-1", "as_of": "x",
                                                 "retrieved_at": "2026-11-22T00:00:00Z"}}

        with mock.patch.object(decision_tools.data_tools, "get_price_history", history), \
                mock.patch.object(decision_tools.data_tools, "list_filings", list_filings), \
                mock.patch.object(decision_tools, "_benchmark_with_source",
                                  lambda t: (benchmark, "none" if benchmark == "no_sector" else "signals_meta")):
            return decision_tools.classify_decision_event("ABC", as_of=as_of)

    def test_e1_from_a_filing_accepted_after_the_close(self):
        r = self.run_tool("2026-06-30")
        self.assertEqual((r["group"], r["horizon_days"], r["benchmark"], r["as_of"]), ("E1", 20, "XLK", "2026-06-30"))
        self.assertEqual((r["e1"]["accession"], r["e1"]["d0"], r["e1"]["accepted_ny"]),
                         ("acc-1", "2026-06-30", "2026-06-29T17:00"))
        self.assertEqual(r["provenance"]["source_id"], "decision-events-v1")
        self.assertEqual([p["source_id"] for p in r["provenance"]["inputs"]],
                         ["yahoo-chart:ABC", "yahoo-chart:XLK", "sec-submissions-1"])
        self.assertTrue(r["provenance"]["retrieved_at"])

    def test_as_of_before_the_close_drops_that_session(self):
        r = self.run_tool("2026-06-30T15:00:00-04:00")
        self.assertEqual((r["as_of"], r["group"]), ("2026-06-29", "E0"))  # D0 close not known yet

    def test_no_sector_is_e0_with_benchmark_flag(self):
        r = self.run_tool("2026-06-30", benchmark=de.NO_SECTOR)
        self.assertEqual((r["group"], r["benchmark"]), ("E0", "no_sector"))
        self.assertEqual(len(r["provenance"]["inputs"]), 2)

    def test_short_history_still_gives_e1_but_not_e2(self):
        self.dates = self.dates[-200:]
        _, self.stock, self.bench = walk_over(self.dates, tail=[-0.08])
        r = self.run_tool("2026-06-30")
        self.assertEqual((r["group"], r["e2_available"], r["history_sessions"]), ("E1", False, 200))

    def test_non_earnings_8k_is_ignored(self):
        rows = [["acc-9", "8-K", "2026-06-29", "2026-06-29T21:00:00Z", "http://x", "5.02"]]
        self.assertEqual(self.run_tool("2026-06-30", filings=rows)["group"], "E0")


def walk_over(dates, tail):
    stock, bench, s = {}, {}, 100.0
    n = len(dates)
    for k, d in enumerate(dates):
        r = tail[k - (n - len(tail))] if k >= n - len(tail) else (0.01 if k % 2 else -0.01)
        s *= 1 + r
        stock[d], bench[d] = s, 100.0
    return dates, stock, bench


if __name__ == "__main__":
    unittest.main()


class BenchmarkFallbackTests(unittest.TestCase):
    """A stock outside the signals universe gets its sector ETF from the Yahoo profile sector (offline: mocked)."""

    def setUp(self):
        decision_tools._PROFILE_SECTOR.clear()
        self.addCleanup(decision_tools._PROFILE_SECTOR.clear)

    def lookup(self, sector=None, fail=False):
        from product.mcp import context_tools

        def snapshot(tickers):
            if fail:
                raise RuntimeError("yahoo down")
            return {"columns": ["ticker", "name", "sector"], "rows": [[tickers[0], "x", sector]] if sector else []}
        with mock.patch.object(context_tools, "get_peer_snapshot", snapshot):
            return decision_tools._benchmark_with_source("ZZZNOTINMETA")

    def test_profile_sector_maps_to_spdr_etf(self):
        self.assertEqual(self.lookup("Consumer Cyclical"), ("XLY", "yahoo_profile_current"))

    def test_unknown_sector_or_failure_is_no_sector(self):
        self.assertEqual(self.lookup("Something Else"), ("no_sector", "none"))
        decision_tools._PROFILE_SECTOR.clear()
        self.assertEqual(self.lookup(fail=True), ("no_sector", "none"))

