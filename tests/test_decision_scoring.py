"""decision_scoring：协议 v1 §3–§6、§8 的复算。纯函数用手造价格；脚本用打补丁的取价跑一个临时账本。"""

import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

import numpy as np

from product.deterministic import decision_scoring as ds

REPO = Path(__file__).resolve().parents[1]


def business_days(start: str, n: int) -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


DAYS = business_days("2026-01-05", 40)  # no holidays; index 0 is a Monday


def rows(override=None, dates=DAYS):
    """Flat 100 series [date, open, high, low, close, adj_close, volume]; override[index] = dict(open=…, close=…, adj=…)."""
    out, override = [], override or {}
    for i, d in enumerate(dates):
        if i in override and override[i] is None:      # the series has no row at all for this session
            continue
        o = override.get(i, {})
        out.append([d, o.get("open", 100.0), 101.0, 99.0, o.get("close", 100.0), o.get("adj", 100.0), 1000])
    return out


def record(decided_index=2, h=5, action="REDUCE", w0=1.0, w1=0.5, group="E2", z=-2.5, cut=False, **kw):
    rec = {"schema": "decision/v2", "decision_id": kw.pop("decision_id", "d1"), "ticker": "AAA", "source": "scan",
           "group": group, "event": {"event_date": DAYS[decided_index], "deviation_z": z}, "benchmark": "XLK",
           "action": action, "w0": w0, "w1": w1, "horizon_days": h,
           "decided_at": f"{DAYS[decided_index]}T21:00:00Z", "decided_at_effective": f"{DAYS[decided_index]}T21:00:00Z",
           "replay": False, "attribution": {"explicit_guidance_cut": cut}, "p_outperform": {"case": 0.4}}
    rec.update(kw)
    return rec


def run(rec, stock_rows, etf_rows, calendar=DAYS):
    return ds.score_record(rec, calendar, ds.align_prices(calendar, stock_rows), ds.align_prices(calendar, etf_rows))


class Protocol8(unittest.TestCase):
    """协议 §8 三行：ETF 口径、现金口径、B0 = 0。"""

    def check(self, w0, w1, rs, re_, d_etf, d_cash):
        etf_d, etf_cost = ds.delta(w0, w1, rs, re_, "sector_etf")
        cash_d, cash_cost = ds.delta(w0, w1, rs, re_, "cash")
        self.assertAlmostEqual(etf_d, d_etf)
        self.assertAlmostEqual(cash_d, d_cash)
        self.assertAlmostEqual(etf_cost, 0.2 * abs(w1 - w0) * 2)
        self.assertAlmostEqual(cash_cost, 0.2 * abs(w1 - w0))
        self.assertEqual(ds.delta(w0, w0, rs, re_, "sector_etf"), (0.0, 0.0))  # HOLD / WAIT = 0, B0 = 0

    def test_example1_reduce_then_rebound(self):
        self.check(1, 0.5, 12, 5, -3.7, -6.1)

    def test_example2_up_but_underperforms_etf(self):
        self.check(1, 0.5, 3, 8, 2.3, -1.6)

    def test_example3_not_held_buy(self):
        self.check(0, 0.5, 6, 2, 1.8, 2.9)

    def test_examples_end_to_end_from_prices(self):
        for (rs, re_, w0, w1, action, d_etf, d_cash, state) in (
                (12, 5, 1.0, 0.5, "REDUCE", -3.7, -6.1, "held"), (3, 8, 1.0, 0.5, "REDUCE", 2.3, -1.6, "held"),
                (6, 2, 0.0, 0.5, "BUY", 1.8, 2.9, "not_held")):
            stock = rows({3 + 5 - 1: {"adj": 100 + rs, "close": 100 + rs}})  # entry index 3, exit index 7
            etf = rows({7: {"adj": 100 + re_, "close": 100 + re_}})
            res = run(record(action=action, w0=w0, w1=w1, group="E0", z=None), stock, etf)
            self.assertEqual(res["status"], "scored")
            self.assertAlmostEqual(res["delta_etf"], d_etf)
            self.assertAlmostEqual(res["delta_cash"], d_cash)

    def test_b1_paired_difference_is_zero_when_b1_also_reduces(self):
        stock = rows({7: {"adj": 112, "close": 112}})
        etf = rows({7: {"adj": 105, "close": 105}})
        res = run(record(z=-2.5), stock, etf)
        self.assertAlmostEqual(res["delta_etf"] - res["delta_b1_etf"], 0.0)
        self.assertAlmostEqual(res["delta_etf"], -3.7)


class Fill(unittest.TestCase):
    def fill(self, stamp, rws=None):
        r = rws or rows()
        return ds.fill(stamp, [x[0] for x in r], [x[1] for x in r], [x[4] for x in r], [x[5] for x in r])

    def test_before_open_uses_same_day(self):
        got = self.fill("2026-01-07T14:29:00Z")  # 09:29 EST Wednesday
        self.assertEqual((got["status"], got["date"]), ("ok", "2026-01-07"))

    def test_at_or_after_open_uses_next_day(self):
        self.assertEqual(self.fill("2026-01-07T14:30:00Z")["date"], "2026-01-08")  # 09:30 sharp: already open
        self.assertEqual(self.fill("2026-01-07T21:00:01Z")["date"], "2026-01-08")  # after the close

    def test_dst_offset(self):
        summer = business_days("2026-06-01", 10)
        r = rows(dates=summer)
        self.assertEqual(self.fill("2026-06-03T13:29:00Z", r)["date"], "2026-06-03")  # 09:29 EDT
        self.assertEqual(self.fill("2026-06-03T13:30:00Z", r)["date"], "2026-06-04")

    def test_weekend_goes_to_monday(self):
        self.assertEqual(self.fill("2026-01-09T22:00:00Z")["date"], "2026-01-12")  # Friday evening
        self.assertEqual(self.fill("2026-01-10T12:00:00Z")["date"], "2026-01-12")  # Saturday
        self.assertEqual(self.fill("2026-01-10T01:00:00Z")["date"], "2026-01-12")  # Friday 20:00 NY... Saturday UTC
        self.assertEqual(self.fill("2026-01-11T13:00:00Z")["date"], "2026-01-12")  # Sunday morning

    def test_missing_open_is_not_fillable_never_close_substituted(self):
        r = rows({3: {"open": None}})
        got = self.fill("2026-01-07T21:00:00Z", r)  # entry day index 3 (2026-01-08)
        self.assertEqual(got["status"], "not_fillable")
        self.assertNotIn("adj_open", got)

    def test_missing_close_or_adj_is_not_fillable(self):
        for key in ("close", "adj"):
            self.assertEqual(self.fill("2026-01-07T21:00:00Z", rows({3: {key: None}}))["status"], "not_fillable")

    def test_no_later_session_is_pending(self):
        self.assertEqual(self.fill(f"{DAYS[-1]}T21:00:00Z")["status"], "pending")

    def test_adjusted_open(self):
        r = rows({3: {"open": 50.0, "close": 100.0, "adj": 80.0}})
        self.assertAlmostEqual(self.fill("2026-01-07T21:00:00Z", r)["adj_open"], 40.0)


class Returns(unittest.TestCase):
    def test_window_return_counts_entry_day_as_day_one(self):
        r = rows({3: {"open": 100.0}, 5: {"adj": 130.0, "close": 130.0}, 7: {"adj": 150.0, "close": 150.0}})
        args = ([x[1] for x in r], [x[4] for x in r], [x[5] for x in r])
        self.assertAlmostEqual(ds.window_return(*args, 3, 3), 30.0)   # day 3 = index 5
        self.assertAlmostEqual(ds.window_return(*args, 3, 5), 50.0)   # day 5 = index 7
        self.assertIsNone(ds.window_return(*args, len(r) - 2, 5))     # beyond data
        self.assertAlmostEqual(ds.path_min(*args, 3, 5), 0.0)

    def test_window_return_missing_exit_is_none(self):
        r = rows({7: {"adj": None}})
        self.assertIsNone(ds.window_return([x[1] for x in r], [x[4] for x in r], [x[5] for x in r], 3, 5))


class StatusRules(unittest.TestCase):
    def test_stock_exit_missing_is_unscorable_for_all_bases(self):
        res = run(record(), rows({7: {"adj": None}}), rows())
        self.assertEqual(res["status"], "unscorable")
        self.assertNotIn("delta_cash", res)
        self.assertNotIn("delta_etf", res)

    def test_etf_missing_cash_still_scored(self):
        for etf in (rows({7: {"adj": None}}), rows({3: {"open": None}}), None):
            stock = rows({7: {"adj": 112, "close": 112}})
            res = run(record(), stock, etf)
            self.assertEqual(res["status"], "etf_unscorable")
            self.assertAlmostEqual(res["delta_cash"], -6.1)
            self.assertIsNone(res["delta_etf"])

    def test_not_fillable(self):
        self.assertEqual(run(record(), rows({3: {"open": None}}), rows())["status"], "not_fillable")

    def test_whole_missing_row_does_not_move_fill_or_exit(self):
        stock_missing_entry = run(record(), rows({3: None}), rows())          # entry session 2026-01-08: no stock row
        self.assertEqual((stock_missing_entry["status"], stock_missing_entry["fill_date"]), ("not_fillable", DAYS[3]))
        etf_missing_entry = run(record(), rows({7: {"adj": 112, "close": 112}}), rows({3: None, 7: {"adj": 105, "close": 105}}))
        self.assertEqual((etf_missing_entry["status"], etf_missing_entry["fill_date"]), ("etf_unscorable", DAYS[3]))
        # a session missing from BOTH stock and ETF, inside the window, still counts as a session
        stock = rows({5: None, 7: {"adj": 112, "close": 112}})
        etf = rows({5: None, 7: {"adj": 105, "close": 105}})
        res = run(record(), stock, etf)
        self.assertEqual((res["status"], res["exit_date"]), ("scored", DAYS[7]))
        self.assertAlmostEqual(res["delta_etf"], -3.7)
        # no_sector (no ETF) stock missing a mid-window row: exit date unchanged
        res = run(record(benchmark="no_sector"), rows({5: None, 7: {"adj": 112, "close": 112}}), None)
        self.assertEqual((res["status"], res["exit_date"]), ("etf_unscorable", DAYS[7]))
        self.assertAlmostEqual(res["delta_cash"], -6.1)
        # the exit session itself missing for the stock: unscorable, not "settle on the next row"
        res = run(record(), rows({7: None, 8: {"adj": 300, "close": 300}}), rows())
        self.assertEqual((res["status"], res["exit_date"]), ("unscorable", DAYS[7]))

    def test_rows_outside_the_calendar_are_ignored(self):
        cal = DAYS[:10]
        prices = ds.align_prices(cal, rows())
        self.assertEqual(prices.dates, cal)
        self.assertEqual(len(prices.adj), 10)
        self.assertIsNone(ds.align_prices(cal, None))

    def test_maturity_is_independent_of_fillability(self):
        short = DAYS[:8]                              # entry index 3, h=60 → far from matured; h=5 exit index 7 is in
        bad_entry = rows({3: {"open": None}})
        self.assertEqual(run(record(h=60), bad_entry, rows(), calendar=short)["status"], "pending")
        self.assertEqual(run(record(h=5), bad_entry, rows(), calendar=short)["status"], "not_fillable")
        self.assertFalse(ds.matured("2026-01-07T21:00:00Z", short, 60))
        self.assertTrue(ds.matured("2026-01-07T21:00:00Z", short, 5))
        self.assertFalse(ds.matured("2026-01-07T21:00:00Z", short, 6))

    def test_pending_keeps_known_fill_date_without_exit_date(self):
        res = run(record(h=60), rows(), rows())
        self.assertEqual((res["status"], res["fill_date"]), ("pending", DAYS[3]))
        self.assertNotIn("exit_date", res)

    def test_price_error_only_after_the_window_has_matured(self):
        self.assertEqual(ds.score_record(record(), DAYS, None, None)["status"], "price_error")
        self.assertEqual(ds.score_record(record(h=60), DAYS, None, None)["status"], "pending")
        res = ds.score_record(record(), DAYS, None, None)
        self.assertEqual(res["fill_date"], DAYS[3])

    def test_pending_before_entry_and_before_exit(self):
        self.assertEqual(run(record(decided_index=len(DAYS) - 1), rows(), rows())["status"], "pending")
        self.assertEqual(run(record(decided_index=len(DAYS) - 4, h=5), rows(), rows())["status"], "pending")

    def test_late_when_fill_is_more_than_three_sessions_after_event(self):
        r = record(decided_index=2)
        r["event"]["event_date"] = DAYS[2]
        ok = run(r, rows(), rows())
        self.assertEqual((ok["status"], ok["late_sessions"]), ("scored", 1))
        r["event"]["event_date"] = DAYS[0]           # fill index 3, event index 0 → 3 sessions: still on time
        self.assertEqual(run(r, rows(), rows())["status"], "scored")
        r["decided_at"] = r["decided_at_effective"] = f"{DAYS[3]}T21:00:00Z"   # fill index 4 → 4 sessions
        late = run(r, rows(), rows())
        self.assertEqual((late["status"], late["late"], late["late_sessions"]), ("late", True, 4))
        self.assertIsNotNone(late["delta_etf"])        # scored, just not in the main sample

    def test_replay_uses_effective_time(self):
        r = record(decided_index=2)
        r.update(replay=True, decided_at="2026-11-22T10:00:00Z")   # actual run time far in the future
        self.assertEqual(run(r, rows(), rows())["fill_date"], DAYS[3])

    def test_hold_scores_zero(self):
        res = run(record(action="HOLD", w1=1.0), rows({7: {"adj": 150, "close": 150}}), rows())
        self.assertEqual((res["delta_etf"], res["delta_cash"]), (0.0, 0.0))


class Baselines(unittest.TestCase):
    def test_e2_by_direction(self):
        self.assertEqual(ds.baselines(record(z=-2.0))["B1"], 0.5)
        self.assertEqual(ds.baselines(record(z=-3.1))["B1"], 0.5)
        self.assertEqual(ds.baselines(record(z=2.4))["B1"], 1.0)
        self.assertIsNone(ds.baselines(record(z=None))["B1"])

    def test_e1_always_reduces_and_e0_holds(self):
        self.assertEqual(ds.baselines(record(group="E1", z=None))["B1"], 0.5)
        self.assertEqual(ds.baselines(record(group="E0", z=None))["B1"], 1.0)

    def test_b2_follows_explicit_guidance_cut_and_b0_holds(self):
        self.assertEqual(ds.baselines(record(cut=True))["B2"], 0.5)
        self.assertEqual(ds.baselines(record(cut=False))["B2"], 1.0)
        self.assertEqual(ds.baselines(record(cut=True))["B0"], 1.0)
        rec = record(w0=0.0, w1=0.5, action="BUY", group="E0", cut=True)
        self.assertEqual(ds.baselines(rec), {"B0": 0.0, "B1": 0.0, "B2": 0.0})


class Bootstrap(unittest.TestCase):
    def sample(self, weeks=40, per=3):
        rng = np.random.default_rng(1)
        wk, vals = [], []
        for w in range(weeks):
            for _ in range(per):
                wk.append(2900 + w)
                vals.append(float(rng.normal(0.3, 2.0)))
        return vals, wk

    def test_fixed_seed_reproducible(self):
        v, w = self.sample()
        self.assertEqual(ds.block_bootstrap(v, w, 12), ds.block_bootstrap(v, w, 12))
        self.assertNotEqual(ds.block_bootstrap(v, w, 12), ds.block_bootstrap(v, w, 12, seed=1))

    def test_too_few_weeks_returns_none(self):
        v, w = self.sample(weeks=35)           # W = 35 < 3*12
        self.assertIsNone(ds.block_bootstrap(v, w, 12))
        v, w = self.sample(weeks=36)           # W = 36 = 3L
        self.assertIsNotNone(ds.block_bootstrap(v, w, 12))
        v, w = self.sample(weeks=11)
        self.assertIsNone(ds.block_bootstrap(v, w, 4))   # E1: needs 12
        self.assertIsNotNone(ds.block_bootstrap(*self.sample(weeks=12), 4))

    def test_matches_naive_loop_with_same_draws(self):
        v, w = self.sample(weeks=40, per=2)
        reps, L = 500, 12
        first, W = min(w), max(w) - min(w) + 1
        by_week = {}
        for x, k in zip(v, w):
            by_week.setdefault(k - first, []).append(x)
        k = -(-W // L)
        starts = np.random.default_rng(ds.SEED).integers(0, W, size=(reps, k))
        means = []
        for row in starts:
            pool = [x for s in row for j in range(L) for x in by_week.get((s + j) % W, [])]
            means.append(sum(pool) / len(pool))
        lo, hi = np.percentile(means, [5, 95])
        got = ds.block_bootstrap(v, w, L, reps=reps)
        self.assertAlmostEqual(got[0], lo)
        self.assertAlmostEqual(got[1], hi)

    def test_two_statistics_share_the_same_draws(self):
        v, w = self.sample()
        a = ds.block_bootstrap(v, w, 12)
        b = ds.block_bootstrap([x + 5.0 for x in v], w, 12)
        self.assertAlmostEqual(b[0], a[0] + 5.0)
        self.assertAlmostEqual(b[1], a[1] + 5.0)

    def test_empty_weeks_count_toward_w(self):
        v = [1.0, 2.0, 3.0, 4.0]
        w = [100, 100, 140, 140]               # W = 41 including empty weeks
        self.assertIsNotNone(ds.block_bootstrap(v, w, 12))
        self.assertIsNone(ds.block_bootstrap(v, [100, 100, 110, 110], 12))

    def test_week_index_is_monday_based_and_continuous(self):
        self.assertEqual(ds.week_index("2026-01-05"), ds.week_index("2026-01-11"))      # Mon … Sun
        self.assertEqual(ds.week_index("2026-01-12"), ds.week_index("2026-01-11") + 1)
        self.assertEqual(ds.week_index("2026-12-28"), ds.week_index("2027-01-03"))      # across the year end
        self.assertEqual(ds.week_index("2027-01-04"), ds.week_index("2027-01-03") + 1)


class Verdict(unittest.TestCase):
    def test_not_worth_when_upper_bound_below_mue(self):
        self.assertEqual(ds.verdict((-0.5, 0.15), (0.1, 0.4)), "not_worth")

    def test_not_worth_beats_supported(self):
        # lower bounds positive, but the upper bound of Δ is still under MUE → rule 1 wins (mutually exclusive)
        self.assertEqual(ds.verdict((0.05, 0.19), (0.05, 0.3)), "not_worth")

    def test_supported_needs_both_lower_bounds_positive(self):
        self.assertEqual(ds.verdict((0.1, 0.9), (0.05, 0.8)), "supported")
        self.assertEqual(ds.verdict((0.1, 0.9), (-0.05, 0.8)), "insufficient")
        self.assertEqual(ds.verdict((-0.1, 0.9), (0.05, 0.8)), "insufficient")
        self.assertEqual(ds.verdict((0.0, 0.9), (0.05, 0.8)), "insufficient")     # lower bound must be > 0

    def test_mue_boundary(self):
        self.assertEqual(ds.verdict((-1.0, 0.20), None), "insufficient")          # upper == MUE is not < MUE
        self.assertEqual(ds.verdict((-1.0, 0.1999), None), "not_worth")

    def test_unusable_interval_is_insufficient(self):
        self.assertEqual(ds.verdict(None, None), "insufficient")
        self.assertEqual(ds.verdict((0.1, 0.9), None), "insufficient")

    def test_interim_can_only_stop(self):
        self.assertEqual(ds.verdict((-0.5, 0.1), (0, 1), interim=True), "stop_not_worth")
        self.assertEqual(ds.verdict((0.1, 0.9), (0.05, 0.8), interim=True), "continue")
        self.assertEqual(ds.verdict(None, None, interim=True), "continue")

    def test_is_final_and_cap(self):
        self.assertFalse(ds.is_final(254, "2027-01-01"))
        self.assertTrue(ds.is_final(255, "2027-01-01"))
        self.assertFalse(ds.is_final(10, "2028-06-29"))
        self.assertTrue(ds.is_final(10, "2028-06-30"))
        sample = [{"fill_date": f"2026-01-{1 + i // 2:02d}", "decision_id": str(i)} for i in range(6)]
        self.assertEqual(len(ds.cap_sample(sample, cap=3)), 4)    # 3rd event's fill day has a 4th event: all kept
        self.assertEqual(len(ds.cap_sample(sample, cap=4)), 4)
        self.assertEqual(len(ds.cap_sample(sample, cap=10)), 6)


def weekly_sample(n, start="2026-01-05", per_week=3, delta_etf=1.0, b1=0.0):
    """n scored main-sample rows, `per_week` events on distinct weekdays of each consecutive week."""
    out, monday = [], date.fromisoformat(start)
    for k in range(n):
        d = monday + timedelta(weeks=k // per_week, days=k % per_week)
        out.append({"decision_id": f"e{k:04d}", "fill_date": d.isoformat(), "delta_etf": delta_etf, "delta_b1_etf": b1})
    return out


class InterimSnapshot(unittest.TestCase):
    def test_not_triggered_below_100_or_below_3L(self):
        self.assertIsNone(ds.interim_snapshot(weekly_sample(99, per_week=3), 12))      # 33 weeks, 99 events
        self.assertIsNone(ds.interim_snapshot(weekly_sample(120, per_week=5), 12))     # 24 weeks: W < 36

    def test_first_100_is_the_snapshot_and_later_samples_do_not_change_it(self):
        base = weekly_sample(140, per_week=3)       # 47 weeks: W >= 36 long before 100 events? 100 events = 34 weeks
        snap100 = ds.interim_snapshot(base[:100], 12)
        self.assertIsNone(snap100)                  # 100 events, W = 34 < 36 → postponed
        base = weekly_sample(150, per_week=4)       # 100 events reached at week 25: W binds → look at week 36
        snap = ds.interim_snapshot(base, 12)
        self.assertEqual(snap["W"], 36)
        self.assertEqual(snap["n"], 36 * 4)         # postponed look takes the whole fill week
        self.assertEqual(snap, ds.interim_snapshot(weekly_sample(220, per_week=4), 12))   # more data: same snapshot
        self.assertEqual(snap, ds.interim_snapshot(weekly_sample(400, per_week=4), 12))

    def test_first_100_with_w_already_enough_cuts_at_that_fill_day(self):
        s = weekly_sample(130, per_week=1)          # one event per week, 130 weeks; 100th event is at week 100
        snap = ds.interim_snapshot(s, 12)
        self.assertEqual((snap["n"], snap["W"], snap["cutoff_fill_date"]), (100, 100, s[99]["fill_date"]))
        # same-day events are all included: two events on the 100th fill day
        s2 = weekly_sample(98, per_week=1) + [
            {"decision_id": "z1", "fill_date": s[98]["fill_date"], "delta_etf": 1.0, "delta_b1_etf": 0.0},
            {"decision_id": "z2", "fill_date": s[99]["fill_date"], "delta_etf": 1.0, "delta_b1_etf": 0.0},
            {"decision_id": "z3", "fill_date": s[99]["fill_date"], "delta_etf": 1.0, "delta_b1_etf": 0.0}]
        snap2 = ds.interim_snapshot(s2, 12)
        self.assertEqual(snap2["n"], 101)

    def test_first_hundred_continue_then_120_does_not_stop(self):
        """First 100: Δ clearly useful → continue. A later sample of 120 whose extra events drag the mean down would stop
        if re-judged; the snapshot must stay the first one (no second stop chance)."""
        first = weekly_sample(100, per_week=1, delta_etf=1.0)               # 100 weeks, mean +1.0
        late = [{"decision_id": f"l{k}", "fill_date": (date.fromisoformat(first[-1]["fill_date"]) + timedelta(weeks=1 + k)).isoformat(),
                 "delta_etf": -50.0, "delta_b1_etf": 0.0} for k in range(20)]
        snap_first = ds.interim_snapshot(first, 12)
        self.assertEqual(snap_first["verdict"], "continue")
        snap_later = ds.interim_snapshot(first + late, 12)
        self.assertEqual(snap_later, snap_first)
        # the later, larger sample really is different (mean now negative), yet the interim result did not move
        full = ds.summarize(first + late, "delta_etf", 12, "delta_b1_etf")
        self.assertLess(full["mean"], 0)

    def test_week_straddling_trigger_is_stable_across_runs(self):
        """Review repro: 4 events a week; the run that sees 141 matured events must not output a look (3 events of the
        trigger week are still pending); after they mature the snapshot is the whole trigger week (144 events, cutoff
        the last fill day of that week) and every later run reproduces exactly that."""
        every = weekly_sample(200, per_week=4)
        run1 = ds.interim_snapshot(every[:141], 12, pending=every[141:144])
        self.assertEqual(run1["state"], "pending")
        self.assertEqual((run1["n"], run1["n_pending"], run1["W"]), (141, 3, 36))
        self.assertNotIn("verdict", run1)
        self.assertNotIn("ci_delta", run1)
        run2 = ds.interim_snapshot(every[:144], 12, pending=[])
        self.assertEqual(run2["state"], "ready")
        self.assertEqual((run2["n"], run2["W"], run2["cutoff_fill_date"]), (144, 36, every[143]["fill_date"]))
        d = date.fromisoformat(every[140]["fill_date"])
        self.assertEqual(run2["trigger_week_start"], (d - timedelta(days=d.weekday())).isoformat())
        # later runs: more events matured, more pending in later weeks (which must not block)
        run3 = ds.interim_snapshot(every[:160], 12, pending=every[160:170])
        run4 = ds.interim_snapshot(every, 12, pending=[])
        self.assertEqual(run2, run3)
        self.assertEqual(run2, run4)

    def test_pending_in_earlier_week_also_delays_the_look(self):
        every = weekly_sample(200, per_week=4)
        held = every[100:102]                       # two events of an earlier week are still pending
        matured = [r for r in every[:144] if r not in held]
        self.assertEqual(ds.interim_snapshot(matured, 12, pending=held)["state"], "pending")
        self.assertEqual(ds.interim_snapshot(every[:144], 12, pending=[])["state"], "ready")

    def test_pending_in_later_weeks_does_not_block(self):
        every = weekly_sample(200, per_week=4)
        snap = ds.interim_snapshot(every[:150], 12, pending=every[150:154])    # weeks 37.. pending; trigger week is 36
        self.assertEqual(snap["state"], "ready")
        self.assertEqual(snap["n"], 144)

    def test_pending_without_fill_date_is_ignored(self):
        every = weekly_sample(150, per_week=4)
        self.assertEqual(ds.interim_snapshot(every, 12, pending=[{"status": "pending"}])["state"], "ready")

    def test_first_hundred_stop_is_stop_and_never_supported(self):
        bad = weekly_sample(100, per_week=1, delta_etf=-1.0)
        self.assertEqual(ds.interim_snapshot(bad, 12)["verdict"], "stop_not_worth")
        good = weekly_sample(100, per_week=1, delta_etf=5.0, b1=0.0)
        snap = ds.interim_snapshot(good, 12)
        self.assertEqual(snap["verdict"], "continue")     # even a clear win is never declared "supported" at interim


def scored(status, **kw):
    return {"status": status, "decision_id": kw.pop("decision_id", status), "fill_date": "2026-02-02", **kw}


def event(i, selected=True, decision=True, failure=False, status="scored", matured_missing=False, group="E2",
          source="scan", replay=False):  # selected: True / False / None (no selection row)
    return {"ticker": f"T{i}", "event_date": "2026-01-30", "group": group, "source": source, "selected": selected,
            "decision": {"decision_id": str(i)} if decision else None, "failure": failure, "replay": replay,
            "scored": scored(status, decision_id=str(i)) if decision else None,
            "no_decision_matured": matured_missing}


class Funnel(unittest.TestCase):
    def test_counts_layers_and_missing_rate_denominator(self):
        evs = (
            [event(i, selected=False, decision=False) for i in range(3)]                        # not selected
            + [event(4, selected=None)]                                                          # scan decision, no selection row
            + [event(10, decision=False, failure=True, matured_missing=True)]                   # failure, matured
            + [event(11, decision=False, failure=True, matured_missing=False)]                  # failure, unmatured
            + [event(12, decision=False, matured_missing=True)]                                 # no record, matured
            + [event(20, status="pending")]                                                      # not yet matured
            + [event(25, status="price_error")]                                                  # matured, stock prices failed
            + [event(21, status="not_fillable")]
            + [event(22, status="unscorable")]
            + [event(23, status="etf_unscorable")]
            + [event(24, status="late")]
            + [event(i, status="scored") for i in range(30, 36)]                                 # 6 main
            # never counted: replay, on_demand, E1
            + [event(40, replay=True), event(41, source="on_demand"), event(42, group="E1")]
        )
        fn = ds.funnel(evs, "E2")
        self.assertEqual((fn["candidates"], fn["selected"], fn["decided"], fn["matured"], fn["priced"]), (19, 15, 12, 11, 10))
        self.assertEqual((fn["fillable"], fn["scorable"], len(fn["main"])), (9, 7, 6))
        ex = fn["excluded"]
        self.assertEqual((ex["not_selected"], ex["no_selection"], ex["failure"], ex["awaiting_decision"]), (3, 1, 2, 1))
        self.assertEqual((ex["pending"], ex["price_error"], ex["not_fillable"], ex["unscorable"], ex["late"]), (1, 1, 1, 2, 1))
        self.assertEqual(ex["no_decision_unmatured"], 1)
        self.assertEqual([r["decision_id"] for r in fn["pending"]], ["20"])
        self.assertEqual([e["ticker"] for e in fn["no_selection"]], ["T4"])
        # numerator: failure(matured) 1 + no record(matured) 1 + price_error 1 + not_fillable 1 + unscorable 2 = 6
        # denominator: selected and matured = 2 no-decision + 11 decided-and-matured = 13; unmatured (1 failure, 1 pending) out
        self.assertEqual((fn["missing"], fn["matured_selected"]), (6, 13))
        self.assertAlmostEqual(fn["missing_rate"], 6 / 13)
        self.assertTrue(fn["missing_high"])

    def test_no_selection_row_never_reaches_the_main_sample(self):
        fn = ds.funnel([event(1, selected=None), event(2)], "E2")
        self.assertEqual([r["decision_id"] for r in fn["main"]], ["2"])
        self.assertEqual((fn["selected"], fn["matured_selected"], fn["missing"]), (1, 1, 0))

    def test_not_fillable_with_unmatured_window_is_in_neither_part(self):
        # score_record gives such a record the status pending, so the funnel never sees not_fillable for it
        res = run(record(h=60), rows({3: {"open": None}}), rows(), calendar=DAYS[:8])
        fn = ds.funnel([event(1, status=res["status"])], "E2")
        self.assertEqual((fn["missing"], fn["matured_selected"], fn["excluded"]["pending"]), (0, 0, 1))
        self.assertIsNone(fn["missing_rate"])

    def test_missing_rate_flag_threshold(self):
        evs = [event(i) for i in range(9)] + [event(99, status="not_fillable")]      # exactly 10%
        fn = ds.funnel(evs, "E2")
        self.assertAlmostEqual(fn["missing_rate"], 0.10)
        self.assertFalse(fn["missing_high"])                                           # flagged only when > 10%
        fn = ds.funnel(evs + [event(98, status="price_error")], "E2")
        self.assertTrue(fn["missing_high"])

    def test_no_selected_events_gives_no_rate(self):
        self.assertIsNone(ds.funnel([event(1, selected=False, decision=False)], "E2")["missing_rate"])


class BuildEvents(unittest.TestCase):
    def test_join_by_ticker_and_event_date(self):
        dec = record(decision_id="a")
        dec.update(kind="decision")
        evs = ds.build_events([
            {"kind": "selection", "ticker": "AAA", "group": "E2", "event_date": DAYS[2], "selected": True},
            dec,
            {"kind": "selection", "ticker": "BRK.B", "group": "E2", "event_date": DAYS[2], "selected": False},
            {"kind": "failure", "ticker": "CCC", "group": "E2", "event_date": DAYS[2]},
            {"kind": "not_fillable", "ticker": "AAA", "event_date": DAYS[2]},
        ])
        by = {e["ticker"]: e for e in evs}
        self.assertEqual(set(by), {"AAA", "BRK-B", "CCC"})
        self.assertIs(by["AAA"]["decision"], dec)
        self.assertFalse(by["BRK-B"]["selected"])
        self.assertTrue(by["CCC"]["failure"] and by["CCC"]["decision"] is None)

    def test_scan_decision_without_selection_row_is_not_selected(self):
        evs = ds.build_events([record(decision_id="a")])
        self.assertIsNone(evs[0]["selected"])

    def test_duplicate_decisions_keep_the_earliest(self):
        early, late = record(decision_id="a"), record(decision_id="b", decided_at="2026-01-08T21:00:00Z",
                                                      decided_at_effective="2026-01-08T21:00:00Z")
        evs = ds.build_events([late, early])
        self.assertEqual(evs[0]["decision"]["decision_id"], "a")


class ScriptSmoke(unittest.TestCase):
    """score-decisions.py on a small constructed ledger, with prices patched in (no network)."""

    def load(self):
        spec = importlib.util.spec_from_file_location("score_decisions_script", REPO / "scripts" / "score-decisions.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_runs_and_reports_everything(self):
        mod = self.load()
        stock = rows({7: {"adj": 112, "close": 112}})
        etf = rows({7: {"adj": 105, "close": 105}})
        table = {"AAA": stock, "BBB": rows({3: {"open": None}}), "CCC": stock, "XLK": etf, "SPY": rows()}
        ledger_rows = [
            {"kind": "selection", "ticker": "AAA", "group": "E2", "event_date": DAYS[2], "selected": True},
            {"kind": "selection", "ticker": "BBB", "group": "E2", "event_date": DAYS[2], "selected": True},
            dict(record(decision_id="nosel", ticker="CCC"), kind="decision"),
            dict(record(decision_id="live1"), kind="decision"),
            dict(record(decision_id="live2", ticker="BBB"), kind="decision"),
            dict(record(decision_id="rep1", replay=True, decided_at="2026-11-22T10:00:00Z"), kind="decision"),
            dict(record(decision_id="od1", source="on_demand", position_state="not_held", group="E0", w0=0.0, w1=0.5,
                        action="BUY", z=None), kind="decision"),
            {"kind": "selection", "ticker": "ZZZ", "group": "E2", "event_date": DAYS[1], "selected": False},
            {"kind": "failure", "ticker": "YYY", "group": "E2", "event_date": DAYS[1]},
        ]
        scratch = REPO / ".local" / "runs"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            ledger, out = Path(tmp) / "ledger.jsonl", Path(tmp) / "report.md"
            ledger.write_text("\n".join(json.dumps(r) for r in ledger_rows) + "\n")

            def fake_history(ticker, start=None, end=None, max_rows=0, **_):
                return {"rows": table[ticker]}
            argv = ["score-decisions.py", "--ledger", str(ledger), "--out", str(out), "--as-of", DAYS[-1]]
            with mock.patch.object(mod.data_tools, "get_price_history", fake_history), \
                    mock.patch("sys.argv", argv):
                mod.main()
            text = out.read_text()
        for needle in ("## 漏斗", "## 主检验", "## 次要报告", "## 逐条（非回放）", "## 回放记录",
                       "live1", "rep1", "od1", "not_fillable", "缺失率"):
            self.assertIn(needle, text)
        self.assertIn("-3.70", text)                                   # Δ(ETF) of the §8 example 1
        self.assertIn("收集中", text)                                    # few events: no verdict yet
        self.assertIn("候选 | 5 |", text)                                # AAA, BBB, CCC, ZZZ, YYY; replay/on_demand excluded
        self.assertIn("无 selection 记录 2", text)                       # CCC (decision) and YYY (failure) have no selection row
        self.assertIn("nosel", text.split("## 主检验")[0])               # listed in the funnel warning
        self.assertIn("中期查看（只有一次", text)
        self.assertTrue(text.index("## 逐条（非回放）") < text.index("live1") < text.index("## 回放记录") < text.index("rep1"))
        main_section = text.split("## 逐条")[0]
        self.assertNotIn("rep1", main_section)


if __name__ == "__main__":
    unittest.main()
