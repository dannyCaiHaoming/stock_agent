"""plan_math：风险算术与三线结算。全部用手造 Bars，离线；每个数值用例的手算过程写在注释里。

日历（无假日）：idx0 3/2 周一、1 3/3、2 3/4、3 3/5、4 3/6、5 3/9 周一、6 3/10、7 3/11、8 3/12、9 3/13 ...
基准计划：3/2 17:00 纽约冻结，成交 = idx1（3/3）开盘；entry_band [99, 101]、失效价 95、200 股、r0 = (100-95)*200 = 1000、
horizon 7 天 → cap_date 3/9 → cap 交易日 idx5。成本每边 10bp。
"""

import unittest
from datetime import date, timedelta

from product.deterministic import plan_math as pm
from product.deterministic.plan_math import Bars, PlanMathError, settle, size_position

FROZEN = "2026-03-02T17:00:00-05:00"


def business_days(start: str, n: int) -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


DAYS = business_days("2026-03-02", 16)

# Base path: fills at 100 on idx1, never touches 95, cap close (idx5) = 105.
OPEN = [99, 100, 101, 102, 103, 104, 105, 106]
CLOSE = [99.5, 101, 102, 103, 104, 105, 106, 107]
# Gap path: close 94 on idx2 (<= 95) then the next open gaps to 90.
GAP_OPEN = [99, 100, 98, 90, 89, 88, 87, 86]
GAP_CLOSE = [99.5, 99, 94, 89, 88, 87, 86, 85]


def mk_plan(**kw):
    p = {"frozen_at": FROZEN, "entry_band": [99, 101], "price_invalidation": 95, "shares_planned": 200,
         "r0": 1000, "horizon_cap_days": 7}
    p.update(kw)
    return p


def mk_bars(opens, closes, adj=None):
    n = len(opens)
    return Bars(DAYS[:n], list(opens), list(closes), list(closes) if adj is None else list(adj))


def run(opens=OPEN, closes=CLOSE, as_of="2026-03-11", plan=None, revisions=(), reviews=(), adj=None, **kw):
    return settle(plan or mk_plan(), list(revisions), list(reviews), mk_bars(opens, closes, adj), as_of, **kw)


def rev(at, **changes):
    return {"effective_at": at, "changes": changes}


def review(rid, at, action):
    return {"review_id": rid, "reviewed_at_effective": at, "action": action}


def legs(line):
    return [(g["date"], g["side"], g["price"], g["shares"], g["reason"]) for g in line["legs"]]


class SizePositionTests(unittest.TestCase):
    def test_values(self):
        # 100 - 95 = 5 per share; 1000 / 5 = 200 shares; r0 = 5 * 200 = 1000
        self.assertEqual(size_position(100, 95, 1000), {"risk_per_share": 5.0, "shares": 200, "r0": 1000.0})
        # 50 - 47 = 3; floor(1000 / 3) = 333; r0 = 999
        self.assertEqual(size_position(50, 47, 1000), {"risk_per_share": 3.0, "shares": 333, "r0": 999.0})
        # decimal arithmetic: 10.1 - 10.0 = 0.1 exactly → 1000 / 0.1 = 10000 (float would give 9999.99..)
        s = size_position(10.1, 10.0, 1000)
        self.assertEqual(s["shares"], 10000)
        self.assertAlmostEqual(s["r0"], 1000.0)

    def test_invalid_number(self):
        for args in [(float("nan"), 95, 1000), (100, 0, 1000), (100, 95, -1), (-5, 95, 1000),
                     (100, 95, float("inf")), (100, "95", 1000), (True, 95, 1000), (100, None, 1000)]:
            with self.assertRaises(PlanMathError, msg=str(args)) as cm:
                size_position(*args)
            self.assertTrue(str(cm.exception).startswith("INVALID_NUMBER:"), str(cm.exception))

    def test_stop_not_below_entry(self):
        for stop in (100, 101):
            with self.assertRaises(PlanMathError) as cm:
                size_position(100, stop, 1000)
            self.assertTrue(str(cm.exception).startswith("STOP_NOT_BELOW_ENTRY:"))

    def test_budget_too_small(self):
        with self.assertRaises(PlanMathError) as cm:      # 4 / 5 → 0 shares
            size_position(100, 95, 4)
        self.assertTrue(str(cm.exception).startswith("RISK_BUDGET_TOO_SMALL:"))


class FillTests(unittest.TestCase):
    def test_pending_no_later_session(self):
        # only the frozen day exists in the (cut) calendar → no entry session yet
        r = run(as_of="2026-03-02")
        self.assertEqual(r["fill"]["status"], "pending")
        self.assertEqual({k: v["status"] for k, v in r["lines"].items()},
                         {"plan": "pending", "hold": "pending", "simple_exit": "pending"})
        self.assertEqual(r["pairs"], {"plan_minus_hold": None, "plan_minus_simple": None})
        r2 = settle(mk_plan(), [], [], mk_bars(OPEN[:1], CLOSE[:1]), "2026-03-06")
        self.assertEqual(r2["fill"]["status"], "pending")

    def test_unfilled_outside_band(self):
        o = list(OPEN)
        o[1] = 101.5                                       # 101.5 > hi 101
        r = run(opens=o)
        self.assertEqual(r["fill"]["status"], "unfilled")
        self.assertEqual({v["status"] for v in r["lines"].values()}, {"unfilled"})
        self.assertEqual(r["lines"]["plan"]["legs"], [])
        self.assertIsNone(r["lines"]["plan"]["net"])
        o[1] = 98.9
        self.assertEqual(run(opens=o)["fill"]["status"], "unfilled")

    def test_band_endpoints_fill(self):
        for px in (99, 101):
            o = list(OPEN)
            o[1] = px
            r = run(opens=o)
            self.assertEqual(r["fill"]["status"], "filled")
            self.assertEqual(r["lines"]["hold"]["legs"][0]["price"], px)

    def test_not_fillable_missing_open(self):
        o = list(OPEN)
        o[1] = None
        r = run(opens=o)
        self.assertEqual(r["fill"]["status"], "not_fillable")
        self.assertEqual({v["status"] for v in r["lines"].values()}, {"not_fillable"})

    def test_cap_date_uses_new_york_date(self):
        # 2026-03-03 03:00Z = 3/2 22:00 New York → date 3/2, + 7 = 3/9
        r = run(plan=mk_plan(frozen_at="2026-03-03T03:00:00Z"))
        self.assertEqual(r["cap_date"], "2026-03-09")
        self.assertEqual(run()["cap_date"], "2026-03-09")


class SettlementTests(unittest.TestCase):
    def test_hold_to_cap_three_lines_equal(self):
        r = run()
        # fill 100 x 200 on 3/3; cap trading day idx5 (3/9) close 105
        # gross = (105 - 100) * 200 = 1000; costs = 100*200*10bp = 20 + 105*200*10bp = 21 → 41
        # net = 959; R = 959 / 1000 = 0.959; return = 959 / 20000 = 4.795%; min close while held = 101 → 0.2 R
        self.assertEqual(r["cap_trading_day"], "2026-03-09")
        for name in ("plan", "hold", "simple_exit"):
            ln = r["lines"][name]
            self.assertEqual(ln["status"], "closed", name)
            self.assertEqual(legs(ln), [("2026-03-03", "buy", 100, 200, "fill"),
                                        ("2026-03-09", "sell", 105, 200, "cap")], name)
            self.assertEqual((ln["gross"], ln["costs"], ln["net"], ln["r"]), (1000.0, 41.0, 959.0, 0.959), name)
            self.assertAlmostEqual(ln["return_pct"], 4.795, delta=0.006)
            self.assertEqual(ln["min_close_r"], 0.2)
            self.assertEqual(ln["flags"], [])
            self.assertFalse(ln["unrealized"])
        self.assertEqual(r["pairs"]["plan_minus_hold"], {"usd": 0.0, "r": 0.0})
        self.assertEqual(r["pairs"]["plan_minus_simple"], {"usd": 0.0, "r": 0.0})

    def test_cost_both_sides_and_parameter(self):
        # 0 bp → net = gross = 1000
        self.assertEqual(run(cost_bps_per_side=0)["lines"]["hold"]["net"], 1000.0)
        # 25 bp: buy 20000 * .0025 = 50, sell 21000 * .0025 = 52.5 → costs 102.5, net 897.5
        ln = run(cost_bps_per_side=25)["lines"]["hold"]
        self.assertEqual((ln["costs"], ln["net"]), (102.5, 897.5))

    def test_gap_below_stop_r_below_minus_one(self):
        r = run(opens=GAP_OPEN, closes=GAP_CLOSE)
        # idx2 close 94 <= 95 → exit at idx3 open 90 (gap). gross = (90-100)*200 = -2000;
        # costs = 20 + 90*200*10bp = 18 → 38; net = -2038; R = -2.038; min close while held = 94 → -1.2 R
        plan = r["lines"]["plan"]
        self.assertEqual(legs(plan), [("2026-03-03", "buy", 100, 200, "fill"),
                                      ("2026-03-05", "sell", 90, 200, "stop")])
        self.assertEqual(plan["legs"][1]["trigger_date"], "2026-03-04")
        self.assertEqual(plan["legs"][1]["trigger_close"], 94)
        self.assertEqual(plan["legs"][1]["stop"], 95)
        self.assertEqual((plan["gross"], plan["costs"], plan["net"], plan["r"]), (-2000.0, 38.0, -2038.0, -2.038))
        self.assertLess(plan["r"], -1)
        self.assertEqual(plan["min_close_r"], -1.2)
        # hold: cap close idx5 = 87 → gross -2600, costs 20 + 87*200*10bp = 17.4 → 37.4, net -2637.4, R -2.637
        hold = r["lines"]["hold"]
        self.assertEqual((hold["gross"], hold["costs"], hold["net"], hold["r"]), (-2600.0, 37.4, -2637.4, -2.637))
        self.assertEqual(hold["min_close_r"], -2.6)                      # closes 99,94,89,88,87 → (87-100)*200/1000
        # simple exit uses the same initial stop → same as plan
        self.assertEqual(r["lines"]["simple_exit"]["net"], -2038.0)
        # plan - hold = -2038 + 2637.4 = 599.4 → 0.599 R; plan - simple = 0
        self.assertEqual(r["pairs"]["plan_minus_hold"], {"usd": 599.4, "r": 0.599})
        self.assertEqual(r["pairs"]["plan_minus_simple"], {"usd": 0.0, "r": 0.0})

    def test_revision_raises_stop(self):
        o = [99, 100, 100.5, 99, 98, 97, 96, 95]
        c = [99.5, 101, 99.5, 98, 97, 96, 95, 94]
        # revision 2 → stop 100, effective 3/3 10:00 (before 16:00 of 3/3). idx1 close 101 > 100: no trigger;
        # idx2 close 99.5 <= 100 → exit idx3 open 99. gross = -200; costs = 20 + 99*200*10bp = 19.8 → 39.8; net -239.8
        r = run(opens=o, closes=c, revisions=[rev("2026-03-03T10:00:00-05:00", price_invalidation=100)])
        plan = r["lines"]["plan"]
        self.assertEqual(legs(plan)[-1], ("2026-03-05", "sell", 99, 200, "stop"))
        self.assertEqual(plan["legs"][-1]["stop"], 100)
        self.assertEqual((plan["gross"], plan["costs"], plan["net"], plan["r"]), (-200.0, 39.8, -239.8, -0.24))
        # hold: cap close idx5 = 96 → gross -800, costs 20 + 19.2 = 39.2, net -839.2; simple (stop 95) never hit → same
        self.assertEqual(r["lines"]["hold"]["net"], -839.2)
        self.assertEqual(r["lines"]["simple_exit"]["net"], -839.2)
        self.assertEqual(r["lines"]["simple_exit"]["legs"][-1][("reason")], "cap")
        # plan - hold = -239.8 + 839.2 = 599.4
        self.assertEqual(r["pairs"]["plan_minus_hold"], {"usd": 599.4, "r": 0.599})
        self.assertEqual(r["pairs"]["plan_minus_simple"], {"usd": 599.4, "r": 0.599})
        self.assertEqual([v["price_invalidation"] for v in r["stop_versions"]], [95, 100])
        self.assertEqual(r["stop_versions"][1]["version"], 2)

    def test_revision_effective_at_close_applies_next_day(self):
        o = [99, 100, 100.5, 99, 98, 97, 96, 95]
        c = [99.5, 101, 99.5, 98, 97, 96, 95, 94]
        # effective exactly 3/4 16:00 is not "earlier than 16:00" → idx2 close 99.5 is not checked against 100.
        # idx3 close 98 <= 100 → exit idx4 open (open[4] = 98) → gross -400; costs 20 + 19.6 = 39.6; net -439.6
        r = run(opens=o, closes=c, revisions=[rev("2026-03-04T16:00:00-05:00", price_invalidation=100)])
        plan = r["lines"]["plan"]
        self.assertEqual(legs(plan)[-1], ("2026-03-06", "sell", 98, 200, "stop"))
        self.assertEqual(plan["legs"][-1]["trigger_date"], "2026-03-05")
        self.assertEqual(plan["net"], -439.6)

    def test_revision_without_stop_keeps_stop_chain(self):
        o = [99, 100, 100.5, 99, 98, 97, 96, 95]
        c = [99.5, 101, 99.5, 98, 97, 96, 95, 94]
        r = run(opens=o, closes=c, revisions=[rev("2026-03-03T10:00:00-05:00", price_invalidation=100),
                                              rev("2026-03-03T11:00:00-05:00", hold_basis="new basis")])
        self.assertEqual(r["lines"]["plan"]["net"], -239.8)            # still stop 100, not reset to 95
        self.assertEqual([v["version"] for v in r["stop_versions"]], [1, 2])

    def test_review_reduce_then_exit(self):
        o = [99, 100, 102, 103, 104, 105, 106, 107]
        c = [99.5, 101, 102, 103, 104, 105, 106, 107]
        revs = [review("r1", "2026-03-03T17:00:00-05:00", "REDUCE"),      # executes idx2 open (3/4) 102
                review("r2", "2026-03-05T17:00:00-05:00", "EXIT")]        # executes idx4 open (3/6) 104
        r = run(opens=o, closes=c, reviews=revs)
        plan = r["lines"]["plan"]
        # REDUCE sells floor(200/2) = 100 at 102; EXIT sells the remaining 100 at 104
        # gross = (102-100)*100 + (104-100)*100 = 600; costs = 20 + 10.2 + 10.4 = 40.6; net 559.4; R 0.559
        self.assertEqual(legs(plan), [("2026-03-03", "buy", 100, 200, "fill"),
                                      ("2026-03-04", "sell", 102, 100, "review"),
                                      ("2026-03-06", "sell", 104, 100, "review")])
        self.assertEqual([g.get("review_id") for g in plan["legs"]], [None, "r1", "r2"])
        self.assertEqual((plan["gross"], plan["costs"], plan["net"], plan["r"]), (600.0, 40.6, 559.4, 0.559))
        self.assertEqual(plan["min_close_r"], 0.2)                         # held closes 101, 102, 103 → min 101
        # hold: cap close 105 → net 959 (see base test). plan - hold = 559.4 - 959 = -399.6 → -0.4 R
        self.assertEqual(r["lines"]["hold"]["net"], 959.0)
        self.assertEqual(r["pairs"]["plan_minus_hold"], {"usd": -399.6, "r": -0.4})
        # review actions never touch the simple-exit line
        self.assertEqual(r["lines"]["simple_exit"]["net"], 959.0)

    def test_reduce_with_one_share_sells_all(self):
        # 1 share, r0 = 5: floor(1/2) = 0 → sell all 1 at idx2 open 102. gross 2; costs 0.1 + 0.102 = 0.202; net 1.798
        o = [99, 100, 102, 103, 104, 105, 106, 107]
        r = run(opens=o, plan=mk_plan(shares_planned=1, r0=5),
                reviews=[review("r1", "2026-03-03T17:00:00-05:00", "REDUCE")])
        plan = r["lines"]["plan"]
        self.assertEqual(legs(plan)[1:], [("2026-03-04", "sell", 102, 1, "review")])
        self.assertEqual(plan["status"], "closed")
        self.assertAlmostEqual(plan["net"], 1.8, places=2)
        self.assertAlmostEqual(plan["r"], 0.36, places=3)                   # 1.798 / 5 = 0.3596

    def test_review_hold_has_no_effect(self):
        r = run(reviews=[review("r1", "2026-03-03T17:00:00-05:00", "HOLD")])
        self.assertEqual(r["lines"]["plan"]["net"], 959.0)

    def test_exit_review_before_fill_cancels_plan_line(self):
        # reviewed 3/2 18:00 (after the freeze, before the fill open) → executes at the fill open idx1 → cancelled
        r = run(reviews=[review("r1", "2026-03-02T18:00:00-05:00", "EXIT")])
        plan = r["lines"]["plan"]
        self.assertEqual((plan["status"], plan["legs"], plan["net"]), ("cancelled_before_fill", [], None))
        self.assertEqual(r["lines"]["hold"]["status"], "closed")           # the comparison lines still fill
        self.assertEqual(r["lines"]["hold"]["net"], 959.0)
        self.assertEqual(r["pairs"], {"plan_minus_hold": None, "plan_minus_simple": None})

    def test_reduce_review_before_fill_is_ignored(self):
        r = run(reviews=[review("r1", "2026-03-02T18:00:00-05:00", "REDUCE")])
        plan = r["lines"]["plan"]
        self.assertEqual(plan["net"], 959.0)
        self.assertIn("review_ignored_before_fill", plan["flags"])

    def test_stop_and_exit_review_same_open_executes_once(self):
        # stop triggers idx2 (close 94); EXIT and REDUCE also execute at idx3 open (reviewed 3/4 17:00) → one sell, EXIT wins
        revs = [review("r_red", "2026-03-04T17:00:00-05:00", "REDUCE"),
                review("r_exit", "2026-03-04T17:30:00-05:00", "EXIT")]
        plan = run(opens=GAP_OPEN, closes=GAP_CLOSE, reviews=revs)["lines"]["plan"]
        sells = [g for g in plan["legs"] if g["side"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertEqual((sells[0]["reason"], sells[0]["review_id"], sells[0]["shares"]), ("review", "r_exit", 200))
        # stop + REDUCE only → the stop's full exit wins
        plan = run(opens=GAP_OPEN, closes=GAP_CLOSE,
                   reviews=[review("r_red", "2026-03-04T17:00:00-05:00", "REDUCE")])["lines"]["plan"]
        sells = [g for g in plan["legs"] if g["side"] == "sell"]
        self.assertEqual([(g["reason"], g["shares"]) for g in sells], [("stop", 200)])

    def test_open_valued_at_as_of(self):
        r = run(as_of="2026-03-04")                          # as_of idx2 < cap_date 3/9 → still held
        # value at 3/4 close 102: gross = (102-100)*200 = 400; costs = buy only 20 (no sell cost on a valuation); net 380
        for name in ("plan", "hold", "simple_exit"):
            ln = r["lines"][name]
            self.assertEqual(ln["status"], "open", name)
            self.assertTrue(ln["unrealized"])
            self.assertEqual(legs(ln)[-1], ("2026-03-04", "sell", 102, 200, "value"), name)
            self.assertEqual((ln["gross"], ln["costs"], ln["net"], ln["r"]), (400.0, 20.0, 380.0, 0.38), name)
            self.assertEqual(ln["min_close_r"], 0.2)          # closes 101, 102
        self.assertIsNone(r["cap_trading_day"])
        self.assertEqual(r["pairs"]["plan_minus_hold"], {"usd": 0.0, "r": 0.0})

    def test_open_with_pending_stop_exit(self):
        # stop triggered on the as_of close (idx2); the exit open (idx3) is not on the calendar yet
        r = run(opens=GAP_OPEN, closes=GAP_CLOSE, as_of="2026-03-04")
        plan = r["lines"]["plan"]
        self.assertEqual(plan["status"], "open")
        self.assertIn("exit_pending_at_as_of", plan["flags"])
        # valued at 94: gross -1200, costs 20, net -1220
        self.assertEqual((plan["gross"], plan["net"]), (-1200.0, -1220.0))

    def test_bars_after_as_of_are_ignored(self):
        cut = run(opens=GAP_OPEN[:3], closes=GAP_CLOSE[:3], as_of="2026-03-04")
        full = run(opens=GAP_OPEN, closes=GAP_CLOSE, as_of="2026-03-04")
        self.assertEqual(cut, full)

    def test_cap_reached_only_when_as_of_reaches_cap_date(self):
        # horizon 5 → cap_date 3/7 (Saturday) → cap trading day idx4 (3/6), close 104
        p = mk_plan(horizon_cap_days=5)
        before = run(plan=p, as_of="2026-03-06")                  # as_of < cap_date: conservative, still open
        self.assertEqual(before["lines"]["hold"]["status"], "open")
        after = run(plan=p, as_of="2026-03-09")
        hold = after["lines"]["hold"]
        # gross = (104-100)*200 = 800; costs = 20 + 104*200*10bp = 20.8 → 40.8; net 759.2
        self.assertEqual((after["cap_trading_day"], hold["status"], hold["net"]), ("2026-03-06", "closed", 759.2))
        self.assertEqual(legs(hold)[-1], ("2026-03-06", "sell", 104, 200, "cap"))

    def test_horizon_one_day_exits_on_fill_day_close(self):
        # cap_date 3/3 = fill day: sell at idx1 close 101. gross 200; costs 20 + 20.2 = 40.2; net 159.8
        r = run(plan=mk_plan(horizon_cap_days=1))
        self.assertEqual(legs(r["lines"]["plan"])[-1], ("2026-03-03", "sell", 101, 200, "cap"))
        self.assertEqual(r["lines"]["plan"]["net"], 159.8)

    def test_cap_beats_stop_on_cap_day(self):
        c = [99.5, 101, 102, 103, 104, 94, 93, 92]           # idx5 (cap day) close 94 <= stop
        r = run(closes=c)
        plan = r["lines"]["plan"]
        # cap exit at close 94: gross -1200; costs 20 + 18.8 = 38.8; net -1238.8; no stop leg
        self.assertEqual(legs(plan)[-1], ("2026-03-09", "sell", 94, 200, "cap"))
        self.assertEqual(plan["net"], -1238.8)

    def test_missing_open_delays_stop_exit(self):
        o = list(GAP_OPEN)
        o[3] = None                                            # exit open missing → next open (idx4 = 89)
        r = run(opens=o, closes=GAP_CLOSE)
        plan = r["lines"]["plan"]
        # gross = (89-100)*200 = -2200; costs 20 + 17.8 = 37.8; net -2237.8
        self.assertEqual(legs(plan)[-1], ("2026-03-06", "sell", 89, 200, "stop"))
        self.assertEqual(plan["net"], -2237.8)
        self.assertIn("delayed_exit", plan["flags"])
        self.assertNotIn("delayed_exit", r["lines"]["hold"]["flags"])

    def test_missing_close_delays_cap(self):
        c = list(CLOSE)
        c[5] = None                                            # cap close missing → next close idx6 = 106
        r = run(closes=c)
        # gross = 1200; costs 20 + 106*200*10bp = 21.2 → 41.2; net 1158.8
        for name in ("plan", "hold", "simple_exit"):
            ln = r["lines"][name]
            self.assertEqual(legs(ln)[-1], ("2026-03-10", "sell", 106, 200, "cap"), name)
            self.assertEqual(ln["net"], 1158.8, name)
            self.assertIn("delayed_cap", ln["flags"], name)
        self.assertEqual(r["cap_trading_day"], "2026-03-09")

    def test_missing_close_skips_stop_check(self):
        c = list(CLOSE)
        c[2] = None
        r = run(closes=c)
        self.assertIn("missing_close", r["lines"]["plan"]["flags"])
        self.assertIn("missing_close", r["lines"]["simple_exit"]["flags"])
        self.assertNotIn("missing_close", r["lines"]["hold"]["flags"])      # hold has no stop rule
        self.assertEqual(r["lines"]["plan"]["status"], "closed")

    def test_corporate_action_marks_not_settleable(self):
        # 2:1 split inside the window: adj/close ratio 0.5 on idx0-2, 1.0 afterwards → drift 100% > 1.5%
        adj = [c * 0.5 if k <= 2 else c for k, c in enumerate(CLOSE)]
        r = run(adj=adj)
        for name in ("plan", "hold", "simple_exit"):
            ln = r["lines"][name]
            self.assertEqual(ln["status"], "not_settleable", name)
            self.assertIn("corporate_action_suspect", ln["flags"], name)
            self.assertIsNone(ln["net"], name)
        self.assertEqual(r["pairs"], {"plan_minus_hold": None, "plan_minus_simple": None})

    def test_small_adj_drift_is_tolerated(self):
        # ratio 1.01 vs 1.00 → 1.0% <= 1.5% (adjustment before the fill day is outside the window)
        adj = [c * 1.01 if k <= 3 else c for k, c in enumerate(CLOSE)]
        self.assertEqual(run(adj=adj)["lines"]["hold"]["status"], "closed")
        adj = [c * 1.02 if k <= 3 else c for k, c in enumerate(CLOSE)]      # 2% > 1.5%
        self.assertEqual(run(adj=adj)["lines"]["hold"]["status"], "not_settleable")
        adj = [c * 2.0 if k == 0 else c for k, c in enumerate(CLOSE)]       # change only before the fill day
        self.assertEqual(run(adj=adj)["lines"]["hold"]["status"], "closed")


class ReworkTests(unittest.TestCase):
    """Rework 1 (astra review #1, #3, #6, #7): splits, cutting at as_of, expired plans, same-day revisions."""

    def statuses(self, r):
        return {k: v["status"] for k, v in r["lines"].items()}

    def test_split_after_fill_before_as_of_is_not_settleable(self):
        # 2:1 split on 3/5 (idx3), after the 3/3 fill and before as_of 3/11 -> window holds a split
        r = run(splits=[["2026-03-05", "2:1"]])
        self.assertEqual(self.statuses(r), {"plan": "not_settleable", "hold": "not_settleable",
                                            "simple_exit": "not_settleable"})
        for ln in r["lines"].values():
            self.assertIn("split_in_window", ln["flags"])
            self.assertIsNone(ln["net"])
        self.assertEqual(r["pairs"], {"plan_minus_hold": None, "plan_minus_simple": None})

    def test_split_after_position_ended_does_not_matter(self):
        # cap close on 3/9 (idx5) ends every line; a split on 3/10 is after the end -> same numbers as the base case
        r = run(splits=[["2026-03-10", "2:1"]])
        self.assertEqual(r, run())
        self.assertEqual(r["lines"]["hold"]["net"], 959.0)
        self.assertNotIn("split_in_window", r["lines"]["hold"]["flags"])

    def test_split_after_as_of_is_ignored_by_bars_cut(self):
        # as_of 3/4: only idx0-2 exist; a split dated 3/10 is later than the window end (last bar 3/4)
        r = run(as_of="2026-03-04", splits=[["2026-03-10", "2:1"]])
        self.assertEqual(r["lines"]["hold"]["status"], "open")
        self.assertEqual(r["lines"]["hold"]["net"], 380.0)

    def test_split_between_freeze_and_fill_is_not_settleable(self):
        # frozen 3/2 17:00, fill 3/3 open; ex-date 3/3 means the band (pre-split) and the open are on different bases
        r = run(splits=[["2026-03-03", "2:1"]])
        self.assertEqual(r["fill"]["status"], "not_settleable")
        self.assertEqual(set(self.statuses(r).values()), {"not_settleable"})
        self.assertIn("split_in_window", r["lines"]["plan"]["flags"])

    def test_split_on_freeze_day_counts_and_before_it_does_not(self):
        self.assertEqual(run(splits=[["2026-03-02", "2:1"]])["lines"]["hold"]["status"], "not_settleable")
        self.assertEqual(run(splits=[["2026-03-01", "2:1"]])["lines"]["hold"]["status"], "closed")

    def test_invalid_splits(self):
        for bad in ([["03/05/2026", "2:1"]], [[None, "2:1"]], [5]):
            with self.assertRaises(PlanMathError, msg=str(bad)) as cm:
                run(splits=bad)
            self.assertTrue(str(cm.exception).startswith("INVALID_SPLITS:"))

    def test_future_revisions_and_reviews_are_ignored(self):
        o = [99, 100, 100.5, 99, 98, 97, 96, 95]
        c = [99.5, 101, 99.5, 98, 97, 96, 95, 94]
        # as_of 3/3: the revision (stop 100) effective 3/4 10:00 and the EXIT review of 3/4 17:00 are not known yet
        r = run(opens=o, closes=c, as_of="2026-03-03",
                revisions=[rev("2026-03-04T10:00:00-05:00", price_invalidation=100)],
                reviews=[review("rx", "2026-03-04T17:00:00-05:00", "EXIT")])
        self.assertEqual([v["price_invalidation"] for v in r["stop_versions"]], [95])
        for ln in r["lines"].values():
            self.assertEqual(ln["status"], "open")
            self.assertEqual(ln["flags"], [])
        # identical to a ledger that never contained them
        self.assertEqual(r, run(opens=o, closes=c, as_of="2026-03-03"))

    def test_revision_known_at_as_of_close_is_kept_but_later_is_not(self):
        o = [99, 100, 100.5, 99, 98, 97, 96, 95]
        c = [99.5, 101, 99.5, 98, 97, 96, 95, 94]
        kept = run(opens=o, closes=c, as_of="2026-03-04", revisions=[rev("2026-03-04T16:00:00-05:00", price_invalidation=100)])
        self.assertEqual([v["version"] for v in kept["stop_versions"]], [1, 2])
        late = run(opens=o, closes=c, as_of="2026-03-04", revisions=[rev("2026-03-04T16:00:01-05:00", price_invalidation=100)])
        self.assertEqual([v["version"] for v in late["stop_versions"]], [1])

    def test_expired_unfilled_over_a_weekend(self):
        # frozen Friday 3/6 17:00, horizon 1 -> cap_date Saturday 3/7; the first open after freezing is Monday 3/9
        r = run(plan=mk_plan(frozen_at="2026-03-06T17:00:00-05:00", horizon_cap_days=1), as_of="2026-03-11")
        self.assertEqual(r["cap_date"], "2026-03-07")
        self.assertEqual(r["fill"]["status"], "expired_unfilled")
        self.assertEqual(self.statuses(r), {"plan": "expired_unfilled", "hold": "expired_unfilled",
                                            "simple_exit": "expired_unfilled"})
        for ln in r["lines"].values():
            self.assertEqual((ln["legs"], ln["costs"], ln["net"]), ([], None, None))
        self.assertIsNone(r["cap_trading_day"])
        self.assertEqual(r["pairs"], {"plan_minus_hold": None, "plan_minus_simple": None})

    def test_expired_unfilled_over_a_closed_day(self):
        # frozen Wed 3/4 17:00, horizon 1 -> cap_date Thu 3/5, but 3/5 is a holiday (not on the calendar) -> next open 3/6
        days = [d for d in DAYS[:8] if d != "2026-03-05"]
        n = len(days)
        bars = Bars(days, [100.0] * n, [100.0] * n, [100.0] * n)
        r = settle(mk_plan(frozen_at="2026-03-04T17:00:00-05:00", horizon_cap_days=1), [], [], bars, "2026-03-11")
        self.assertEqual(r["fill"]["status"], "expired_unfilled")
        self.assertEqual(r["fill"]["date"], "2026-03-06")

    def test_expired_as_soon_as_the_cap_date_is_reached_without_waiting_for_the_next_session(self):
        # frozen Friday 3/6 17:00, horizon 1 -> cap Saturday 3/7; the calendar ends Friday 3/6 (no Monday yet)
        plan = mk_plan(frozen_at="2026-03-06T17:00:00-05:00", horizon_cap_days=1)
        bars = Bars(DAYS[:5], [100.0] * 5, [100.0] * 5, [100.0] * 5)
        self.assertEqual(bars.dates[-1], "2026-03-06")
        for as_of in ("2026-03-07", "2026-03-08"):
            r = settle(plan, [], [], bars, as_of)
            self.assertEqual(r["fill"]["status"], "expired_unfilled", as_of)
            self.assertEqual(self.statuses(r), {"plan": "expired_unfilled", "hold": "expired_unfilled",
                                                "simple_exit": "expired_unfilled"})
            self.assertIsNone(r["cap_trading_day"])
        # the day before the cap date it is still pending; a calendar that stops before the freeze is "missing", not expired
        self.assertEqual(settle(plan, [], [], bars, "2026-03-06")["fill"]["status"], "pending")
        short = Bars(DAYS[:3], [100.0] * 3, [100.0] * 3, [100.0] * 3)
        self.assertEqual(settle(plan, [], [], short, "2026-03-08")["fill"]["status"], "pending")
        self.assertEqual(settle(plan, [], [], Bars([], [], [], []), "2026-03-08")["fill"]["status"], "pending")

    def test_unparsed_split_after_the_freeze_is_not_settleable(self):
        r = run(unparsed_splits=["2026-03-10"])
        self.assertEqual(r["fill"]["status"], "not_settleable")
        for ln in r["lines"].values():
            self.assertEqual((ln["status"], ln["flags"], ln["net"]), ("not_settleable", ["split_ratio_unparsed"], None))
        # on or before the freeze day: the bars used are all on the post-split basis
        self.assertEqual(run(unparsed_splits=["2026-03-02"])["lines"]["hold"]["status"], "closed")
        self.assertEqual(run(unparsed_splits=["2026-02-20"]), run())
        # combined with a split in the window both flags are reported
        both = run(splits=[["2026-03-03", "2:1"]], unparsed_splits=["2026-03-03"])
        self.assertEqual(both["lines"]["plan"]["flags"], ["split_in_window", "split_ratio_unparsed"])

    def test_cap_on_the_fill_day_is_not_expired(self):
        # frozen Mon 3/2 17:00, horizon 1 -> cap 3/3 = fill day -> still fills and exits at that close
        r = run(plan=mk_plan(horizon_cap_days=1))
        self.assertEqual(r["fill"]["status"], "filled")
        self.assertEqual(r["lines"]["hold"]["status"], "closed")

    def test_revision_between_1300_and_1600_is_flagged(self):
        o = [99, 100, 100.5, 99, 98, 97, 96, 95]
        c = [99.5, 101, 99.5, 98, 97, 96, 95, 94]
        r = run(opens=o, closes=c, revisions=[rev("2026-03-04T14:00:00-05:00", price_invalidation=100)])
        self.assertIn("revision_same_day_check", r["lines"]["plan"]["flags"])
        self.assertNotIn("revision_same_day_check", r["lines"]["hold"]["flags"])
        for at in ("2026-03-04T12:59:59-05:00", "2026-03-04T16:00:00-05:00"):
            r = run(opens=o, closes=c, revisions=[rev(at, price_invalidation=100)])
            self.assertNotIn("revision_same_day_check", r["lines"]["plan"]["flags"], at)


class InputValidationTests(unittest.TestCase):
    def test_errors_carry_codes(self):
        cases = [
            (dict(as_of="03/11/2026"), "INVALID_AS_OF"),
            (dict(plan=mk_plan(horizon_cap_days=0)), "INVALID_PLAN"),
            (dict(plan=mk_plan(horizon_cap_days=121)), "INVALID_PLAN"),
            (dict(plan=mk_plan(entry_band=[101, 99])), "INVALID_PLAN"),
            (dict(plan=mk_plan(shares_planned=0)), "INVALID_PLAN"),
            (dict(plan=mk_plan(r0=0)), "INVALID_NUMBER"),
            (dict(reviews=[review("r", "2026-03-03T17:00:00-05:00", "BUY")]), "INVALID_REVIEW"),
            (dict(revisions=[rev("2026-03-03T10:00:00-05:00", price_invalidation=-1)]), "INVALID_REVISION"),
        ]
        for kw, code in cases:
            with self.assertRaises(PlanMathError, msg=str(kw)) as cm:
                run(**kw)
            self.assertTrue(str(cm.exception).startswith(code + ":"), f"{kw}: {cm.exception}")

    def test_bad_bars(self):
        bad = Bars(["2026-03-03", "2026-03-02"], [1, 1], [1, 1], [1, 1])
        with self.assertRaises(PlanMathError) as cm:
            settle(mk_plan(), [], [], bad, "2026-03-11")
        self.assertTrue(str(cm.exception).startswith("INVALID_BARS:"))
        short = Bars(DAYS[:3], [1, 1], [1, 1, 1], [1, 1, 1])
        with self.assertRaises(PlanMathError):
            settle(mk_plan(), [], [], short, "2026-03-11")

    def test_constants(self):
        self.assertEqual((pm.COST_BPS_PER_SIDE, pm.CORP_ACTION_TOL, pm.MAX_HORIZON_DAYS), (10, 0.015, 120))


if __name__ == "__main__":
    unittest.main()
