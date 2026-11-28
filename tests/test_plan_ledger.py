"""Offline tests for plan/v1 records (product/mcp/plan_ledger.py).

Every test points STOCK_AGENT_DATA_DIR at a temp dir; nothing touches .local/data or evals/.
product.deterministic.plan_math is used when present; until then a stand-in with the same interface is injected.
"""
import hashlib
import json
import math
import os
import sys
import tempfile
import threading
import types
import unittest
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

from product.mcp import plan_ledger, settings
from product.mcp.decision_ledger import NY
from product.mcp.decision_log import DecisionLogError


def _stand_in_plan_math() -> types.ModuleType:
    module = types.ModuleType("product.deterministic.plan_math")

    class PlanMathError(ValueError):
        pass

    def size_position(entry_ref, price_invalidation, risk_budget):
        for value in (entry_ref, price_invalidation, risk_budget):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise PlanMathError("INVALID_NUMBER: positive finite numbers only")
        if price_invalidation >= entry_ref:
            raise PlanMathError("STOP_NOT_BELOW_ENTRY: price_invalidation must be below entry_ref")
        risk = entry_ref - price_invalidation
        shares = math.floor(risk_budget / risk)
        if shares < 1:
            raise PlanMathError("RISK_BUDGET_TOO_SMALL: budget buys less than one share")
        return {"risk_per_share": risk, "shares": shares, "r0": risk * shares}

    module.PlanMathError, module.size_position = PlanMathError, size_position
    return module


def setUpModule():
    try:
        import product.deterministic.plan_math  # noqa: F401
    except ImportError:
        patcher = mock.patch.dict(sys.modules, {"product.deterministic.plan_math": _stand_in_plan_math()})
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


PLAN_REPORT = """# NVDA 交易计划
## 论点
财报后数据中心指引超预期。
## 催化剂
2026-03-04 财报。
## 放弃理由的事实
指引下修。
## 价格失效位与预算亏损
收盘跌破 90；预算 1000。
## 持有依据与复核日
持有到下个财报前。
## 数据缺口
无
## 来源
8-K
"""

REVIEW_REPORT = """# NVDA 复核
## 论点复核
论点被财报证伪。
## 价格与动作
离场。
## 数据缺口
无
## 来源
8-K
"""

FACT = {"document": "8-K 2026-03-04", "fact": "数据中心指引下修"}


def plan_args(**over):
    args = dict(
        ticker="NVDA", template="catalyst_event", thesis="财报后数据中心指引被低估。",
        market_misread="市场只看了本季，没算新品放量。", catalyst="2026-03-04 财报与电话会",
        abandon_facts=[dict(FACT)], price_invalidation=90.0, entry_ref=100.0, entry_band=[98.0, 102.0],
        hold_basis="持有到新品首批出货确认。", review_dates=["2026-03-20"], horizon_cap_days=30,
        report_markdown=PLAN_REPORT, risk_budget=1000, replay_as_of="2026-03-02", host="codex", model="gpt-6.1-terra")
    args.update(over)
    return args


def evidence(published="2026-03-05", **over):
    item = {"kind": "filing", "source": "8-K 2026-03-05", "published_at": published,
            "claim": "公司下修数据中心指引。", "original_condition": "放弃理由的事实：指引下修"}
    item.update(over)
    return item


def review_args(plan_id, **over):
    args = dict(plan_id=plan_id, thesis_verdict="broken", evidence=[evidence()], action="EXIT",
                action_reason="放弃理由的事实已出现。", report_markdown=REVIEW_REPORT, replay_as_of="2026-03-10",
                host="codex", model="gpt-6.1-terra")
    args.update(over)
    return args


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"STOCK_AGENT_DATA_DIR": self.tmp.name}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("STOCK_AGENT_REPLAY_AS_OF", None)
        os.environ.pop("STOCK_AGENT_RUN_MODEL", None)
        self.root = Path(self.tmp.name).resolve()

    def rows(self, kind=None):
        path = self.root / "trade_plans.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if kind is None or r["kind"] == kind]

    def save(self, **over):
        if over.get("replay_as_of", "x") is None and "review_dates" not in over:  # live: dates must follow today
            over["review_dates"] = [(date.today() + timedelta(days=20)).isoformat()]
        return plan_ledger.save_trade_plan(**plan_args(**over))

    def review(self, plan_id, **over):
        return plan_ledger.save_plan_review(**review_args(plan_id, **over))

    def refuse(self, code, fn, *args, **kwargs):
        before = self.rows()
        with self.assertRaises(DecisionLogError) as ctx:
            fn(*args, **kwargs)
        self.assertIn(code, str(ctx.exception))
        self.assertEqual(self.rows(), before)  # a refusal writes nothing

    def refuse_plan(self, code, **over):
        self.refuse(code, plan_ledger.save_trade_plan, **plan_args(**over))

    def replay(self, day):
        """A replay session as of `day` (reads and choices on replay plans need one)."""
        return mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": day})

    def get(self, plan_id, day="2026-03-20", **kwargs):
        with self.replay(day):
            return plan_ledger.get_trade_plan(plan_id, **kwargs)

    def choose(self, plan_id, ref_id, choice, note, day="2026-03-12"):
        with self.replay(day):
            return plan_ledger.record_plan_choice(plan_id, ref_id, choice, note)

    def refuse_choice(self, code, plan_id, ref_id, choice, note, day="2026-03-12"):
        with self.replay(day):
            self.refuse(code, plan_ledger.record_plan_choice, plan_id, ref_id, choice, note)


class SaveTests(LedgerCase):
    def test_live_plan_saved_with_candidate_report_and_numbers(self):
        # risk/share = 100 - 90 = 10; shares = floor(1000 / 10) = 100; r0 = 10 * 100 = 1000
        out = self.save(replay_as_of=None)
        self.assertTrue(out["saved"])
        self.assertEqual((out["shares_planned"], out["r0"]), (100, 1000))
        self.assertFalse(out["replay"])
        candidate, plan = self.rows("candidate")[0], self.rows("plan")[0]
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(candidate["outcome"], "plan")
        self.assertEqual(candidate["plan_id"], plan["plan_id"])
        self.assertEqual(plan["candidate_id"], candidate["candidate_id"])
        self.assertEqual(out["plan_id"], plan["plan_id"])
        self.assertEqual(plan["schema"], "plan/v1")
        self.assertEqual(plan["frozen_at"], plan["decided_at"])
        self.assertEqual((plan["fill_rule"], plan["stop_rule"], plan["cost_bps_per_side"]),
                         ("limit_band_within_entry_valid_sessions", "close_at_or_below_then_next_open", 10))
        self.assertIn("commit", plan["code_version"])
        report = Path(plan["report_path"])
        self.assertEqual(report.parent.parent, self.root / "plan-reports")
        self.assertEqual(report.name, f"NVDA-{plan['plan_id']}.md")
        self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), plan["report_sha256"])
        self.assertEqual(out["report_path"], plan["report_path"])
        self.assertFalse((self.root / "trade_decisions.jsonl").exists())  # decision/v2 log untouched

    def test_shares_floor_and_r0(self):
        # risk/share = 47.3 - 44.1 = 3.2; shares = floor(1000 / 3.2) = floor(312.5) = 312; r0 = 3.2 * 312 = 998.4
        out = self.save(entry_ref=47.3, entry_band=[47.0, 48.0], price_invalidation=44.1, ticker="amd")
        self.assertEqual(out["shares_planned"], 312)
        self.assertAlmostEqual(out["r0"], 998.4, places=6)
        self.assertEqual(self.rows("plan")[0]["ticker"], "AMD")

    def test_generated_fields_refused(self):
        for name in plan_ledger.GENERATED_FIELDS:
            with self.subTest(name=name):
                self.refuse("GENERATED_FIELD_NOT_ACCEPTED", plan_ledger.save_trade_plan, **plan_args(), **{name: "x"})

    def test_unknown_field_refused(self):
        self.refuse("UNKNOWN_FIELDS", plan_ledger.save_trade_plan, **plan_args(), confidence="high")

    def test_abandon_facts_validated(self):
        for facts in ([], None, [{"document": "8-K"}], [{"fact": "x"}], [{"document": " ", "fact": "x"}],
                      [{"document": "d", "fact": ""}], ["text"], [{"document": "d", "fact": "f", "extra": 1}]):
            with self.subTest(facts=facts):
                self.refuse_plan("ABANDON_FACTS", abandon_facts=facts)

    def test_entry_band_and_stop_order(self):
        self.refuse_plan("ENTRY_BAND_ORDER", entry_band=[102.0, 98.0])
        self.refuse_plan("ENTRY_BAND_INVALID", entry_band=[98.0])
        self.refuse_plan("ENTRY_REF_OUTSIDE_BAND", entry_band=[101.0, 105.0])
        self.refuse_plan("ENTRY_REF_OUTSIDE_BAND", entry_band=[95.0, 99.0])
        self.refuse_plan("PRICE_INVALIDATION_NOT_BELOW_BAND", price_invalidation=98.0)
        self.refuse_plan("PRICE_INVALIDATION_NOT_BELOW_BAND", price_invalidation=99.0)
        self.refuse_plan("PRICE_INVALIDATION_INVALID", price_invalidation=0)
        self.refuse_plan("PRICE_INVALIDATION_INVALID", price_invalidation=True)
        self.refuse_plan("ENTRY_REF_INVALID", entry_ref=float("nan"))
        self.save(entry_band=[100.0, 100.0])  # lo == ref == hi is allowed

    def test_budget_too_small_is_refused_as_ledger_error(self):
        self.refuse_plan("RISK_BUDGET_TOO_SMALL", risk_budget=5)  # risk/share 10 > 5 -> 0 shares

    def test_horizon_cap_bounds(self):
        for value in (0, 121, -3, 1.5, True, "30", None):
            with self.subTest(value=value):
                self.refuse_plan("HORIZON_CAP_DAYS_INVALID", horizon_cap_days=value)
        self.save(horizon_cap_days=120)
        self.save(horizon_cap_days=1, ticker="AMD")

    def test_template_must_be_catalyst_event(self):
        self.refuse_plan("TEMPLATE_INVALID", template="trend_follow")

    def test_text_and_dates_validated(self):
        self.refuse_plan("THESIS_MUST_BE_ONE_LINE", thesis="第一行\n第二行")
        self.refuse_plan("MARKET_MISREAD_REQUIRED", market_misread=" ")
        self.refuse_plan("REVIEW_DATES_REQUIRED", review_dates=[])
        self.refuse_plan("REVIEW_DATES_INVALID", review_dates=["2026-03-02"])  # not after the decision day
        self.refuse_plan("REVIEW_DATES_INVALID", review_dates=["2026-03-20", "2026-03-01"])
        self.refuse_plan("REVIEW_DATES_INVALID", review_dates=["03/20/2026"])
        self.refuse_plan("TICKER_INVALID", ticker="no way")

    def test_report_sections_required(self):
        self.refuse_plan("REPORT_SECTIONS_MISSING", report_markdown=PLAN_REPORT.replace("## 催化剂", "## 其他"))
        self.refuse_plan("REPORT_SECTIONS_MISSING", report_markdown="只有一段话")
        self.refuse_plan("REPORT_MARKDOWN_REQUIRED", report_markdown="  ")

    def test_model_recorded_sources(self):
        self.save(ticker="AAA")
        with mock.patch.dict(os.environ, {"STOCK_AGENT_RUN_MODEL": "gpt-6.1-terra-run"}):
            self.save(ticker="BBB", model="self-claim")
        a, b = self.rows("plan")
        self.assertEqual(a["model_recorded"], {"value": "gpt-6.1-terra", "source": "self_reported"})
        self.assertEqual(b["model_recorded"], {"value": "gpt-6.1-terra-run", "source": "run_env"})
        self.assertEqual(b["model"], "self-claim")  # what the caller said is kept apart from what the run says

    def test_model_recorded_without_any_model(self):
        self.save(model=None)
        self.assertEqual(self.rows("plan")[0]["model_recorded"], {"value": None, "source": "self_reported"})

    def test_ids_differ_between_plans(self):
        self.assertNotEqual(self.save(ticker="AAA")["plan_id"], self.save(ticker="BBB")["plan_id"])


class ReplayTests(LedgerCase):
    def test_replay_effective_time_is_end_of_new_york_day(self):
        out = self.save(replay_as_of="2026-03-02")
        # 23:59:59 EST (UTC-5, before the 2026-03-08 DST change) = 04:59:59 UTC next day
        self.assertEqual(out["frozen_at"], "2026-03-03T04:59:59Z")
        plan = self.rows("plan")[0]
        self.assertTrue(plan["replay"])
        self.assertNotEqual(plan["decided_at"], plan["frozen_at"])
        self.assertTrue(self.rows("candidate")[0]["replay"])

    def test_replay_daylight_saving_offset(self):
        out = self.save(replay_as_of="2026-07-01", review_dates=["2026-07-20"])
        self.assertEqual(out["frozen_at"], "2026-07-02T03:59:59Z")  # EDT, UTC-4

    def test_replay_date_must_be_a_finished_day(self):
        self.refuse_plan("REPLAY_AS_OF_INVALID", replay_as_of="2999-01-01")
        self.refuse_plan("REPLAY_AS_OF_INVALID", replay_as_of=date.today().isoformat())

    def test_env_replay_is_picked_up_and_must_agree(self):
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-02"}):
            self.save(replay_as_of=None)
            self.refuse_plan("REPLAY_AS_OF_MISMATCH", replay_as_of="2026-03-09", ticker="AMD")
        self.assertTrue(self.rows("plan")[0]["replay"])

    def test_replay_and_live_do_not_mix_in_checks(self):
        self.save(replay_as_of=None)  # live NVDA in progress
        self.save(replay_as_of="2026-03-02")  # replay NVDA is allowed next to it
        for ticker in ("A1", "A2", "A3", "A4", "A5", "A6", "A7"):
            self.save(ticker=ticker, replay_as_of=None)  # 8 live plans now
        self.refuse_plan("ACTIVE_PLAN_LIMIT", ticker="A8", replay_as_of=None,
                         review_dates=[(date.today() + timedelta(days=20)).isoformat()])
        self.save(ticker="A8", replay_as_of="2026-03-02")  # the replay side still has room (NVDA + A8)
        self.assertEqual(len(plan_ledger.active_plans(date(2026, 3, 2), True)), 2)
        self.assertEqual(len(plan_ledger.active_plans(date.today(), False)), 8)

    def test_list_shows_only_the_kind_of_the_session(self):
        self.save(replay_as_of=None)
        self.save(ticker="AMD", replay_as_of="2026-03-02")
        live = plan_ledger.list_trade_plans()
        self.assertEqual([p["ticker"] for p in live["plans"]], ["NVDA"])
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-02"}):
            replay = plan_ledger.list_trade_plans()
        self.assertEqual([p["ticker"] for p in replay["plans"]], ["AMD"])


class ActiveRuleTests(LedgerCase):
    def test_ninth_active_plan_refused(self):
        for ticker in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"):
            self.save(ticker=ticker)
        self.refuse_plan("ACTIVE_PLAN_LIMIT", ticker="A9")

    def test_same_ticker_in_progress_refused(self):
        self.save()
        self.refuse_plan("ACTIVE_PLAN_EXISTS", replay_as_of="2026-03-04")

    def test_exit_review_frees_ticker_and_new_plan_id_differs(self):
        first = self.save()
        self.review(first["plan_id"])
        second = self.save(replay_as_of="2026-03-11", review_dates=["2026-03-25"])
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        got_first, got_second = (self.get(p["plan_id"]) for p in (first, second))
        self.assertEqual(len(got_first["reviews"]), 1)
        self.assertEqual(got_second["reviews"], [])  # nothing leaks between the two plan_ids
        self.assertFalse(got_first["active"])
        self.assertEqual(got_first["active_reason"], "exit_review")
        self.assertEqual([r["kind"] for r in self.rows()], ["candidate", "plan", "review", "candidate", "plan"])

    def test_reduce_and_hold_reviews_do_not_free_ticker(self):
        first = self.save()
        self.review(first["plan_id"], action="REDUCE", thesis_verdict="weakened")
        self.refuse_plan("ACTIVE_PLAN_EXISTS", replay_as_of="2026-03-11")

    def test_cap_expiry_ends_in_progress(self):
        # decision day 2026-03-02 + 5 calendar days = cap 2026-03-07: still in progress on the cap day, over after it
        first = self.save(horizon_cap_days=5, review_dates=["2026-03-05"])
        self.refuse_plan("ACTIVE_PLAN_EXISTS", replay_as_of="2026-03-07", review_dates=["2026-03-20"])
        second = self.save(replay_as_of="2026-03-08", review_dates=["2026-03-20"])
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        got = self.get(first["plan_id"], "2026-03-09")
        self.assertFalse(got["active"])
        self.assertEqual((got["active_reason"], got["cap_date"]), ("cap_passed", "2026-03-07"))

    def test_expired_plan_cannot_be_reviewed_or_revised(self):
        plan = self.save(horizon_cap_days=5, review_dates=["2026-03-05"])
        self.refuse("PLAN_NOT_ACTIVE", plan_ledger.save_plan_review, **review_args(plan["plan_id"]))
        self.refuse("PLAN_NOT_ACTIVE", plan_ledger.revise_trade_plan, plan["plan_id"], "x", ["8-K"],
                    {"price_invalidation": 95}, replay_as_of="2026-03-10")

    def test_abandoned_frees_ticker_and_counts_out_of_limit(self):
        plan = self.save()
        self.choose(plan["plan_id"], plan["plan_id"], "abandoned", "数据变了，不做了", day="2026-03-03")
        self.assertEqual(plan_ledger.active_plans(date(2026, 3, 5), True), [])
        self.save(replay_as_of="2026-03-04", review_dates=["2026-03-20"])

    def test_active_plans_function_filters_by_date(self):
        self.save(horizon_cap_days=5, review_dates=["2026-03-05"])
        self.assertEqual(len(plan_ledger.active_plans(date(2026, 3, 7), True)), 1)
        self.assertEqual(plan_ledger.active_plans(date(2026, 3, 8), True), [])
        self.assertEqual(plan_ledger.active_plans(date(2026, 3, 7), False), [])  # live never sees replay records
        self.assertEqual(plan_ledger.active_plans(date(2026, 3, 1), True), [])  # not frozen yet on that day


class RevisionTests(LedgerCase):
    def test_revision_appends_version_and_keeps_r0(self):
        plan = self.save()
        out = plan_ledger.revise_trade_plan(plan["plan_id"], "财报后上调预期", ["8-K 2026-03-05"],
                                            {"price_invalidation": 104.0, "hold_basis": "跟踪止盈"},
                                            replay_as_of="2026-03-06")
        self.assertEqual(out["version"], 2)
        self.assertEqual((out["r0"], out["shares_planned"]), (1000, 100))
        # a stop above the entry reference is allowed (protects profit); R0 stays the original budget
        self.assertEqual(out["current"]["price_invalidation"], 104.0)
        out3 = plan_ledger.revise_trade_plan(plan["plan_id"], "再上移", [{"source": "news", "published_at": "2026-03-08"}],
                                             {"review_dates": ["2026-03-25"]}, replay_as_of="2026-03-09")
        self.assertEqual(out3["version"], 3)
        got = self.get(plan["plan_id"])
        self.assertEqual([r["version"] for r in got["revisions"]], [2, 3])
        self.assertEqual(got["current"], {"version": 3, "price_invalidation": 104.0, "hold_basis": "跟踪止盈",
                                           "review_dates": ["2026-03-25"], "abandon_facts": [FACT]})
        frozen = got["plan"]  # the frozen plan itself is never rewritten
        self.assertEqual((frozen["price_invalidation"], frozen["r0"], frozen["shares_planned"]), (90.0, 1000, 100))
        self.assertEqual(got["revisions"][0]["effective_at"], "2026-03-07T04:59:59Z")

    def test_disallowed_fields_refused(self):
        plan = self.save()
        for field in ("r0", "shares_planned", "entry_ref", "entry_band", "thesis", "risk_budget", "ticker"):
            with self.subTest(field=field):
                self.refuse("REVISION_FIELD_NOT_ALLOWED", plan_ledger.revise_trade_plan, plan["plan_id"], "x",
                            ["8-K"], {field: 1}, replay_as_of="2026-03-06")
        self.refuse("REVISION_FIELD_NOT_ALLOWED", plan_ledger.revise_trade_plan, plan["plan_id"], "x", ["8-K"],
                    {"price_invalidation": 95, "r0": 5}, replay_as_of="2026-03-06")

    def test_revision_input_validation(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.refuse("CHANGES_REQUIRED", plan_ledger.revise_trade_plan, pid, "x", ["s"], {}, replay_as_of="2026-03-06")
        self.refuse("REASON_REQUIRED", plan_ledger.revise_trade_plan, pid, " ", ["s"], {"hold_basis": "h"},
                    replay_as_of="2026-03-06")
        self.refuse("SOURCES_REQUIRED", plan_ledger.revise_trade_plan, pid, "x", [], {"hold_basis": "h"},
                    replay_as_of="2026-03-06")
        self.refuse("PRICE_INVALIDATION_INVALID", plan_ledger.revise_trade_plan, pid, "x", ["s"],
                    {"price_invalidation": -1}, replay_as_of="2026-03-06")
        self.refuse("ABANDON_FACTS_REQUIRED", plan_ledger.revise_trade_plan, pid, "x", ["s"], {"abandon_facts": []},
                    replay_as_of="2026-03-06")
        self.refuse("REVIEW_DATES_INVALID", plan_ledger.revise_trade_plan, pid, "x", ["s"],
                    {"review_dates": ["2026-03-06"]}, replay_as_of="2026-03-06")
        self.refuse("PLAN_NOT_FOUND", plan_ledger.revise_trade_plan, "nope", "x", ["s"], {"hold_basis": "h"})

    def test_revision_time_rules(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.refuse("EFFECTIVE_NOT_AFTER_FROZEN", plan_ledger.revise_trade_plan, pid, "x", ["s"],
                    {"hold_basis": "h"}, replay_as_of="2026-03-02")
        self.refuse("PLAN_REPLAY_MISMATCH", plan_ledger.revise_trade_plan, pid, "x", ["s"], {"hold_basis": "h"})
        plan_ledger.revise_trade_plan(pid, "x", ["s"], {"hold_basis": "h"}, replay_as_of="2026-03-06")
        self.refuse("EFFECTIVE_NOT_AFTER_PREVIOUS", plan_ledger.revise_trade_plan, pid, "y", ["s"],
                    {"hold_basis": "h2"}, replay_as_of="2026-03-06")

    def test_revision_after_exit_refused(self):
        plan = self.save()
        self.review(plan["plan_id"])
        self.refuse("PLAN_NOT_ACTIVE", plan_ledger.revise_trade_plan, plan["plan_id"], "x", ["s"],
                    {"hold_basis": "h"}, replay_as_of="2026-03-12")


class ReviewTests(LedgerCase):
    def test_review_saved_with_effective_time_and_report(self):
        plan = self.save()
        out = self.review(plan["plan_id"])
        self.assertEqual(out["reviewed_at_effective"], "2026-03-11T03:59:59Z")  # 2026-03-10 23:59:59 EDT
        row = self.rows("review")[0]
        self.assertEqual((row["review_id"], row["plan_id"], row["action"]), (out["review_id"], plan["plan_id"], "EXIT"))
        self.assertTrue(row["replay"])
        self.assertFalse(row["plan_deviation"])
        report = Path(out["report_path"])
        self.assertEqual(report.name, f"NVDA-{out['review_id']}.md")
        self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), row["report_sha256"])
        got = self.get(plan["plan_id"])
        self.assertEqual(got["reviews"][0]["review_id"], out["review_id"])
        self.assertIn("## 论点", got["report_markdown"])

    def test_changed_verdict_without_new_evidence_refused(self):
        plan = self.save()
        # published before the plan froze (2026-03-02 23:59:59): not new
        self.refuse("NEW_EVIDENCE_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], evidence=[evidence("2026-03-01")]))
        # published on the freeze day itself: a bare date counts as that day's start, so it is not new either
        self.refuse("NEW_EVIDENCE_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], evidence=[evidence("2026-03-02")]))
        out = self.review(plan["plan_id"], evidence=[evidence("2026-03-01"), evidence("2026-03-05")])  # one new item is enough
        self.assertTrue(out["saved"])

    def test_unchanged_verdict_needs_no_new_evidence(self):
        plan = self.save()
        out = self.review(plan["plan_id"], thesis_verdict="unchanged", action="HOLD", evidence=[evidence("2026-03-01")])
        self.assertTrue(out["saved"])

    def test_verdict_compared_with_previous_review(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.review(pid, thesis_verdict="weakened", action="HOLD", replay_as_of="2026-03-05",
                    evidence=[evidence("2026-03-04")])
        # same verdict again: fine with old evidence
        self.review(pid, thesis_verdict="weakened", action="REDUCE", replay_as_of="2026-03-09",
                    evidence=[evidence("2026-03-04")])
        # change back to unchanged: the evidence must be newer than the previous review (2026-03-09 end of day)
        self.refuse("NEW_EVIDENCE_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(pid, thesis_verdict="unchanged", action="HOLD", replay_as_of="2026-03-12",
                                  evidence=[evidence("2026-03-09")]))
        out = self.review(pid, thesis_verdict="unchanged", action="HOLD", replay_as_of="2026-03-12",
                          evidence=[evidence("2026-03-10")])
        self.assertTrue(out["saved"])
        self.assertEqual(len(self.get(pid)["reviews"]), 3)

    def test_evidence_published_after_review_refused(self):
        plan = self.save()
        self.refuse("EVIDENCE_AFTER_REVIEW", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], evidence=[evidence("2026-03-11")]))
        self.refuse("EVIDENCE_AFTER_REVIEW", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], evidence=[evidence("2026-03-05"),
                                                             evidence("2026-03-11T00:00:00-04:00")]))
        # exactly on the effective instant is allowed (a datetime must carry its timezone)
        self.review(plan["plan_id"], evidence=[evidence("2026-03-10T23:59:59-04:00")])

    def test_evidence_shape_validated(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.refuse("EVIDENCE_REQUIRED", plan_ledger.save_plan_review, **review_args(pid, evidence=[]))
        self.refuse("EVIDENCE_KIND_INVALID", plan_ledger.save_plan_review, **review_args(pid, evidence=[evidence(kind="tweet")]))
        self.refuse("EVIDENCE_CLAIM_REQUIRED", plan_ledger.save_plan_review, **review_args(pid, evidence=[evidence(claim=" ")]))
        self.refuse("EVIDENCE_ORIGINAL_CONDITION_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(pid, evidence=[evidence(original_condition="")]))
        self.refuse("EVIDENCE_PUBLISHED_AT_INVALID", plan_ledger.save_plan_review,
                    **review_args(pid, evidence=[evidence("yesterday")]))
        self.refuse("EVIDENCE_INVALID", plan_ledger.save_plan_review, **review_args(pid, evidence=["text"]))

    def test_enums_validated(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.refuse("THESIS_VERDICT_INVALID", plan_ledger.save_plan_review, **review_args(pid, thesis_verdict="great"))
        self.refuse("ACTION_INVALID", plan_ledger.save_plan_review, **review_args(pid, action="BUY"))
        self.refuse("ACTION_REASON_REQUIRED", plan_ledger.save_plan_review, **review_args(pid, action_reason=""))

    def test_plan_deviation_needs_reason(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.refuse("DEVIATION_REASON_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(pid, plan_deviation=True))
        self.refuse("DEVIATION_REASON_NOT_ALLOWED", plan_ledger.save_plan_review,
                    **review_args(pid, deviation_reason="why"))
        out = self.review(pid, plan_deviation=True, deviation_reason="计划写了持有，但失效事实已出现，提前离场")
        self.assertTrue(out["saved"])
        self.assertTrue(self.rows("review")[0]["plan_deviation"])

    def test_report_sections_required(self):
        plan = self.save()
        self.refuse("REPORT_SECTIONS_MISSING", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], report_markdown=REVIEW_REPORT.replace("## 价格与动作", "## 动作")))
        self.refuse("REPORT_SECTIONS_MISSING", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], report_markdown="没有标题"))

    def test_review_time_rules(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.refuse("EFFECTIVE_NOT_AFTER_FROZEN", plan_ledger.save_plan_review,
                    **review_args(pid, replay_as_of="2026-03-02"))
        self.refuse("EFFECTIVE_NOT_AFTER_FROZEN", plan_ledger.save_plan_review,
                    **review_args(pid, replay_as_of="2026-03-01"))
        self.refuse("PLAN_REPLAY_MISMATCH", plan_ledger.save_plan_review, **review_args(pid, replay_as_of=None))
        self.review(pid, thesis_verdict="weakened", action="HOLD", replay_as_of="2026-03-06",
                    evidence=[evidence("2026-03-05")])
        self.refuse("EFFECTIVE_NOT_AFTER_PREVIOUS", plan_ledger.save_plan_review,
                    **review_args(pid, thesis_verdict="weakened", action="HOLD", replay_as_of="2026-03-06"))

    def test_live_review_of_live_plan_and_replay_flag(self):
        plan = self.save(replay_as_of=None)
        out = self.review(plan["plan_id"], replay_as_of=None, thesis_verdict="unchanged", action="HOLD",
                          evidence=[evidence("2026-03-01")])
        self.assertFalse(out["replay"])
        self.refuse("PLAN_REPLAY_MISMATCH", plan_ledger.save_plan_review, **review_args(plan["plan_id"]))

    def test_review_of_unknown_plan(self):
        self.refuse("PLAN_NOT_FOUND", plan_ledger.save_plan_review, **review_args("nope"))

    def test_review_model_recorded(self):
        plan = self.save()
        with mock.patch.dict(os.environ, {"STOCK_AGENT_RUN_MODEL": "run-model"}):
            self.review(plan["plan_id"])
        self.assertEqual(self.rows("review")[0]["model_recorded"], {"value": "run-model", "source": "run_env"})


class ChoiceAndReadTests(LedgerCase):
    def test_choice_followed_and_declined(self):
        plan = self.save()
        review = self.review(plan["plan_id"], action="REDUCE", thesis_verdict="weakened")
        out = self.choose(plan["plan_id"], review["review_id"], "followed", "")
        self.assertEqual(out["choice"], "followed")
        self.assertEqual(out["effective_at"], "2026-03-13T03:59:59Z")  # 2026-03-12 23:59:59 EDT
        self.choose(plan["plan_id"], plan["plan_id"], "declined", "没买")
        self.assertEqual([c["choice"] for c in self.get(plan["plan_id"])["choices"]], ["followed", "declined"])
        self.assertTrue(self.get(plan["plan_id"])["active"])  # only abandoned/EXIT end it

    def test_choice_validation(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.refuse_choice("CHOICE_INVALID", pid, pid, "maybe", "x")
        self.refuse_choice("REF_ID_NOT_FOUND", pid, "other", "followed", "x")
        self.refuse_choice("NOTE_REQUIRED", pid, pid, "declined", " ")
        self.refuse("PLAN_NOT_FOUND", plan_ledger.record_plan_choice, "nope", "nope", "followed", "x")

    def test_abandoned_refused_after_exit_review(self):
        plan = self.save()
        review = self.review(plan["plan_id"])
        self.refuse_choice("ABANDON_AFTER_EXIT", plan["plan_id"], plan["plan_id"], "abandoned", "算了")
        self.refuse_choice("ABANDON_AFTER_EXIT", plan["plan_id"], review["review_id"], "abandoned", "算了")

    def test_abandoned_twice_refused(self):
        plan = self.save()
        self.choose(plan["plan_id"], plan["plan_id"], "abandoned", "算了")
        self.refuse_choice("ALREADY_ABANDONED", plan["plan_id"], plan["plan_id"], "abandoned", "再算了")

    def test_get_trade_plan_not_found_and_shape(self):
        self.assertEqual(plan_ledger.get_trade_plan("nope"), {"found": False, "plan_id": "nope"})
        self.assertEqual(self.get("nope"), {"found": False, "plan_id": "nope"})
        plan = self.save()
        got = self.get(plan["plan_id"])
        self.assertTrue(got["found"])
        self.assertEqual({"found", "plan_id", "plan", "revisions", "current", "reviews", "choices", "active",
                          "report_markdown", "report_integrity", "active_reason", "cap_date"}, set(got))
        self.assertEqual(got["report_integrity"], "ok")
        self.assertEqual(got["current"]["version"], 1)
        self.assertEqual(got["cap_date"], "2026-04-01")  # 2026-03-02 + 30 days
        self.assertTrue(got["active"])

    def test_list_trade_plans(self):
        a = self.save(ticker="AAA", replay_as_of=None)
        b = self.save(ticker="BBB", replay_as_of=None)
        plan_ledger.record_plan_choice(b["plan_id"], b["plan_id"], "abandoned", "算了")  # live plan, live session
        active = plan_ledger.list_trade_plans()
        self.assertEqual([p["plan_id"] for p in active["plans"]], [a["plan_id"]])
        self.assertEqual((active["count"], active["active_count"]), (1, 1))
        self.assertNotIn("report_markdown", active["plans"][0])
        everything = plan_ledger.list_trade_plans(active_only=False)
        self.assertEqual({p["ticker"] for p in everything["plans"]}, {"AAA", "BBB"})
        self.assertEqual(everything["active_count"], 1)
        only_b = plan_ledger.list_trade_plans(ticker="bbb", active_only=False)
        self.assertEqual([p["plan_id"] for p in only_b["plans"]], [b["plan_id"]])
        self.assertEqual(only_b["active_count"], 1)  # counts all in-progress plans, not only the filtered ones
        self.assertEqual(plan_ledger.list_trade_plans(ticker="ZZZ")["plans"], [])

    def test_ledger_is_append_only(self):
        plan = self.save()
        before = (self.root / "trade_plans.jsonl").read_text()
        self.review(plan["plan_id"])
        self.choose(plan["plan_id"], plan["plan_id"], "followed", "")
        self.assertTrue((self.root / "trade_plans.jsonl").read_text().startswith(before))

    def test_corrupt_ledger_is_reported(self):
        (self.root / "trade_plans.jsonl").write_text("not json\n")
        with self.assertRaises(DecisionLogError) as ctx:
            self.save()
        self.assertIn("LEDGER_CORRUPT", str(ctx.exception))
        self.assertEqual((self.root / "trade_plans.jsonl").read_text(), "not json\n")


class ReplayVisibilityTests(LedgerCase):
    """Rework 1 #1: a read or write only sees records effective at the session cutoff; sessions do not mix."""

    def chain(self):
        """Plan frozen 03-02 (stop 90), revision 03-06 (stop 110), EXIT review 03-09, abandoned-type choice 03-12."""
        plan = self.save()
        pid = plan["plan_id"]
        plan_ledger.revise_trade_plan(pid, "涨了上移", ["8-K"], {"price_invalidation": 110.0}, replay_as_of="2026-03-06")
        review = self.review(pid, replay_as_of="2026-03-09", evidence=[evidence("2026-03-08")])
        self.choose(pid, review["review_id"], "followed", "", day="2026-03-12")
        return pid, review["review_id"]

    def test_get_hides_records_effective_after_the_replay_day(self):
        pid, _ = self.chain()
        early = self.get(pid, "2026-03-03")
        self.assertEqual((early["current"]["version"], early["current"]["price_invalidation"]), (1, 90.0))
        self.assertEqual((early["revisions"], early["reviews"], early["choices"]), ([], [], []))
        self.assertEqual((early["active"], early["active_reason"]), (True, "active"))
        mid = self.get(pid, "2026-03-06")
        self.assertEqual((mid["current"]["version"], mid["current"]["price_invalidation"]), (2, 110.0))
        self.assertEqual(mid["reviews"], [])
        self.assertTrue(mid["active"])
        late = self.get(pid, "2026-03-09")
        self.assertEqual([r["action"] for r in late["reviews"]], ["EXIT"])
        self.assertEqual((late["active"], late["active_reason"]), (False, "exit_review"))
        self.assertEqual(late["choices"], [])  # the choice is effective 03-12
        self.assertEqual(len(self.get(pid, "2026-03-12")["choices"]), 1)

    def test_plan_not_yet_frozen_is_not_found(self):
        pid, _ = self.chain()
        self.assertEqual(self.get(pid, "2026-03-01"), {"found": False, "plan_id": pid})
        with self.replay("2026-03-01"):
            self.assertEqual(plan_ledger.list_trade_plans(active_only=False)["plans"], [])
            self.assertEqual(plan_ledger.list_trade_plans()["active_count"], 0)

    def test_list_summary_uses_the_cutoff(self):
        pid, _ = self.chain()
        with self.replay("2026-03-03"):
            row = plan_ledger.list_trade_plans()["plans"][0]
        self.assertEqual((row["version"], row["price_invalidation"], row["review_count"], row["last_review"]),
                         (1, 90.0, 0, None))
        self.assertEqual(row["choices"], [])
        with self.replay("2026-03-09"):
            self.assertEqual(plan_ledger.list_trade_plans()["plans"], [])  # EXIT already effective: not in progress
            row = plan_ledger.list_trade_plans(active_only=False)["plans"][0]
        self.assertEqual((row["version"], row["price_invalidation"], row["last_review"]["action"]), (2, 110.0, "EXIT"))

    def test_thesis_view_is_cut_too(self):
        pid, _ = self.chain()
        with self.replay("2026-03-03"):
            view = plan_ledger.get_trade_plan(pid, view="thesis")
        self.assertEqual((view["current"]["version"], view["reviews"]), (1, []))

    def test_session_mode_must_match_the_plan(self):
        replay_plan = self.save()
        live_plan = self.save(ticker="AMD", replay_as_of=None)
        for pid in (replay_plan["plan_id"], live_plan["plan_id"]):
            wrong = self.replay("2026-03-20") if pid == live_plan["plan_id"] else nullcontext()
            with wrong:
                for call in (lambda: plan_ledger.get_trade_plan(pid), lambda: plan_ledger.get_trade_plan(pid, "thesis"),
                             lambda: plan_ledger.record_plan_choice(pid, pid, "declined", "x")):
                    self.refuse("PLAN_REPLAY_MISMATCH", call)

    def test_replay_session_cannot_abandon_a_live_plan(self):
        live = self.save(ticker="AMD", replay_as_of=None)
        self.refuse_choice("PLAN_REPLAY_MISMATCH", live["plan_id"], live["plan_id"], "abandoned", "回放里想放弃")
        self.assertEqual(plan_ledger.list_trade_plans()["active_count"], 1)  # the live slot is still taken

    def test_choice_has_an_effective_time(self):
        plan = self.save()
        self.refuse_choice("EFFECTIVE_NOT_AFTER_FROZEN", plan["plan_id"], plan["plan_id"], "declined", "x", day="2026-03-01")
        out = self.choose(plan["plan_id"], plan["plan_id"], "declined", "没买", day="2026-03-05")
        self.assertEqual(out["effective_at"], "2026-03-06T04:59:59Z")
        self.assertEqual(self.rows("choice")[0]["effective_at"], "2026-03-06T04:59:59Z")
        live = self.save(ticker="AMD", replay_as_of=None)
        out = plan_ledger.record_plan_choice(live["plan_id"], live["plan_id"], "declined", "没买")
        self.assertEqual(out["effective_at"], out["recorded_at"])  # live: effective now

    def test_a_later_abandon_does_not_change_an_earlier_active_state(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.choose(pid, pid, "abandoned", "后来放弃", day="2026-03-06")
        self.assertEqual(len(plan_ledger.active_plans(date(2026, 3, 5), True)), 1)  # not yet abandoned on 03-05
        self.assertEqual(plan_ledger.active_plans(date(2026, 3, 6), True), [])
        # so a new plan on the same ticker decided on 03-04 still hits the then-active one
        self.refuse_plan("ACTIVE_PLAN_EXISTS", replay_as_of="2026-03-04", review_dates=["2026-03-20"])
        self.save(replay_as_of="2026-03-07", review_dates=["2026-03-20"])

    def test_a_later_exit_does_not_change_an_earlier_active_state(self):
        plan = self.save()
        self.review(plan["plan_id"], replay_as_of="2026-03-10")
        self.assertEqual(len(plan_ledger.active_plans(date(2026, 3, 9), True)), 1)
        self.assertEqual(plan_ledger.active_plans(date(2026, 3, 10), True), [])
        self.refuse_plan("ACTIVE_PLAN_EXISTS", replay_as_of="2026-03-09", review_dates=["2026-03-20"])

    def test_choice_cannot_reference_a_review_that_is_not_yet_effective(self):
        plan = self.save()
        review = self.review(plan["plan_id"], replay_as_of="2026-03-10")
        # the plan has a later record, so the whole write is refused (and says nothing about what the record is)
        self.refuse_choice("HISTORY_WRITE_CONFLICT", plan["plan_id"], review["review_id"], "followed", "", day="2026-03-05")
        self.refuse_choice("REF_ID_NOT_FOUND", plan["plan_id"], "no-such-id", "followed", "", day="2026-03-11")
        self.choose(plan["plan_id"], review["review_id"], "followed", "", day="2026-03-11")


class ReworkTwoTests(LedgerCase):
    """Rework 2: no write into a past that already has later records; strict published_at; same-time choices."""

    def future_chain(self):
        """Plan frozen 03-02, EXIT review effective 03-09; a replay write on 03-03 has later records."""
        plan = self.save()
        pid = plan["plan_id"]
        review = self.review(pid, replay_as_of="2026-03-09", evidence=[evidence("2026-03-08")])
        return pid, review["review_id"]

    def test_history_write_conflict_reveals_nothing_about_later_records(self):
        pid, rid = self.future_chain()
        calls = [
            lambda: plan_ledger.revise_trade_plan(pid, "x", ["s"], {"price_invalidation": 91.0}, replay_as_of="2026-03-03"),
            lambda: plan_ledger.save_plan_review(**review_args(pid, replay_as_of="2026-03-03", thesis_verdict="unchanged",
                                                               action="HOLD", evidence=[evidence("2026-03-02")])),
        ]
        for call in calls:
            with self.assertRaises(DecisionLogError) as ctx:
                before = self.rows()
                call()
            self.assertEqual(str(ctx.exception), "HISTORY_WRITE_CONFLICT: this plan has records after the replay cutoff")
            self.assertEqual(self.rows(), before)
        for choice in ("abandoned", "declined", "followed"):
            with self.replay("2026-03-03"):
                with self.assertRaises(DecisionLogError) as ctx:
                    plan_ledger.record_plan_choice(pid, pid, choice, "x")
            text = str(ctx.exception)
            self.assertEqual(text, "HISTORY_WRITE_CONFLICT: this plan has records after the replay cutoff")
            for leak in ("EXIT", "ABANDON", "exit", "review"):
                self.assertNotIn(leak, text)

    def test_later_choice_also_blocks_an_earlier_abandon(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.choose(pid, pid, "abandoned", "后来放弃", day="2026-03-09")
        self.refuse_choice("HISTORY_WRITE_CONFLICT", pid, pid, "abandoned", "x", day="2026-03-04")

    def test_write_at_the_tail_is_unaffected(self):
        pid, rid = self.future_chain()
        self.choose(pid, rid, "followed", "", day="2026-03-12")
        self.refuse_choice("ABANDON_AFTER_EXIT", pid, pid, "abandoned", "x", day="2026-03-13")

    def test_published_at_accepts_only_date_or_datetime_with_timezone(self):
        pid = self.save()["plan_id"]
        for bad in ("20260303", "2026-03-03T10:00:00", "2026-03-03 10:00:00", "2026-3-3", "03/03/2026", "2026-03-03T10:00",
                    "20260303T100000Z", "yesterday"):
            self.refuse("PUBLISHED_AT_INVALID", plan_ledger.save_plan_review,
                        **review_args(pid, evidence=[evidence(bad)]))
        out = self.review(pid, evidence=[evidence("2026-03-03T10:00:00Z")])
        self.assertTrue(out["saved"])

    def test_published_at_bare_date_stays_an_interval(self):
        # same-day bare date at 10:00 is not usable (ambiguous), a bare date 20260303 never reaches that check
        self.assertEqual(plan_ledger._evidence_bounds("2026-03-03")[2], True)
        with self.assertRaises(DecisionLogError):
            plan_ledger._evidence_bounds("20260303")

    def test_choice_may_share_the_effective_time_of_the_plan_and_of_a_review(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.choose(pid, pid, "followed", "", day="2026-03-02")      # same instant as the freeze (replay day end)
        self.assertEqual(self.rows("choice")[0]["effective_at"], plan["frozen_at"])
        review = self.review(pid, thesis_verdict="unchanged", action="HOLD", replay_as_of="2026-03-09",
                             evidence=[evidence("2026-03-08")])
        self.choose(pid, review["review_id"], "followed", "", day="2026-03-09")
        self.assertEqual(len(self.rows("choice")), 2)
        # a revision or a review still needs a strictly later time
        plan2 = self.save(ticker="AMD")
        self.refuse("EFFECTIVE_NOT_AFTER_FROZEN", plan_ledger.save_plan_review,
                    **review_args(plan2["plan_id"], replay_as_of="2026-03-02"))
        # a reference to a review that is not effective yet is still refused
        review2 = self.review(plan2["plan_id"], replay_as_of="2026-03-10", evidence=[evidence("2026-03-08")])
        self.refuse_choice("HISTORY_WRITE_CONFLICT", plan2["plan_id"], review2["review_id"], "followed", "", day="2026-03-05")


class EvidenceTimeTests(LedgerCase):
    """Rework 1 #2: a bare date is the interval [00:00, 23:59:59] New York."""

    def live_plan(self):
        return self.save(replay_as_of=None)["plan_id"]

    def live_review(self, pid, published):
        return plan_ledger.save_plan_review(**review_args(pid, replay_as_of=None, thesis_verdict="unchanged",
                                                          action="HOLD", evidence=[evidence(published)]))

    def test_same_day_bare_date_is_ambiguous_in_a_live_review(self):
        pid = self.live_plan()
        today = datetime.now(NY).date()
        self.refuse("EVIDENCE_TIME_AMBIGUOUS", plan_ledger.save_plan_review,
                    **review_args(pid, replay_as_of=None, thesis_verdict="unchanged", action="HOLD",
                                  evidence=[evidence(today.isoformat())]))
        self.refuse("EVIDENCE_AFTER_REVIEW", plan_ledger.save_plan_review,
                    **review_args(pid, replay_as_of=None, thesis_verdict="unchanged", action="HOLD",
                                  evidence=[evidence((today + timedelta(days=1)).isoformat())]))
        # an earlier day is fine, and so is an exact time already past today
        self.live_review(pid, (today - timedelta(days=1)).isoformat())
        out = plan_ledger.save_plan_review(**review_args(pid, replay_as_of=None, thesis_verdict="unchanged",
                                                         action="HOLD", evidence=[evidence(datetime.combine(today, datetime.min.time(), tzinfo=NY).isoformat())]))
        self.assertTrue(out["saved"])

    def test_replay_review_may_cite_its_own_day_by_bare_date(self):
        plan = self.save()
        out = self.review(plan["plan_id"], thesis_verdict="unchanged", action="HOLD", replay_as_of="2026-03-10",
                          evidence=[evidence("2026-03-10")])
        self.assertTrue(out["saved"])  # upper bound 23:59:59 = the replay review's effective time
        self.refuse("EVIDENCE_AFTER_REVIEW", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], thesis_verdict="unchanged", action="HOLD", replay_as_of="2026-03-12",
                                  evidence=[evidence("2026-03-13")]))

    def test_newer_than_last_uses_the_lower_bound(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.review(pid, thesis_verdict="weakened", action="HOLD", replay_as_of="2026-03-05", evidence=[evidence("2026-03-04")])
        # bare 2026-03-05 could have been published before the 03-05 review: not provably new
        self.refuse("NEW_EVIDENCE_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(pid, thesis_verdict="broken", replay_as_of="2026-03-09", evidence=[evidence("2026-03-05")]))
        self.refuse("NEW_EVIDENCE_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(pid, thesis_verdict="broken", replay_as_of="2026-03-09",
                                  evidence=[evidence("2026-03-05T20:00:00-05:00")]))
        self.review(pid, thesis_verdict="broken", replay_as_of="2026-03-09", evidence=[evidence("2026-03-06")])

    def test_exact_time_in_a_live_plan_is_still_compared_exactly(self):
        pid = self.live_plan()
        past = (datetime.now(NY) - timedelta(hours=1)).replace(microsecond=0).isoformat()
        self.assertTrue(self.live_review(pid, past)["saved"])


class PriceEvidenceTests(LedgerCase):
    """Rework 1 #3: changing the verdict needs new evidence that is not a price move."""

    def test_price_only_new_evidence_cannot_change_the_verdict(self):
        plan = self.save()
        old_filing = evidence("2026-03-01")
        new_price = evidence("2026-03-05", kind="price", source="close", claim="收盘 -12%")
        self.refuse("NEW_EVIDENCE_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], evidence=[old_filing, new_price]))
        self.refuse("NEW_EVIDENCE_REQUIRED", plan_ledger.save_plan_review,
                    **review_args(plan["plan_id"], evidence=[new_price]))
        with self.assertRaises(DecisionLogError) as ctx:
            self.review(plan["plan_id"], evidence=[old_filing, new_price])
        self.assertIn("price move does not change the thesis conclusion", str(ctx.exception))
        out = self.review(plan["plan_id"], evidence=[new_price, evidence("2026-03-05", kind="news")])
        self.assertTrue(out["saved"])

    def test_price_evidence_is_fine_when_the_verdict_stays(self):
        plan = self.save()
        out = self.review(plan["plan_id"], thesis_verdict="unchanged", action="REDUCE",
                          evidence=[evidence("2026-03-05", kind="price", claim="收盘 -12%")])
        self.assertTrue(out["saved"])


class ThesisViewTests(LedgerCase):
    PRICE_KEYS = {"entry_ref", "entry_band", "price_invalidation", "r0", "shares_planned", "risk_budget",
                  "report_markdown", "report_path", "action", "action_reason", "plan_deviation", "deviation_reason"}

    def walk(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from self.walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from self.walk(item)

    def test_thesis_view_has_no_price_action_or_report(self):
        plan = self.save()
        pid = plan["plan_id"]
        plan_ledger.revise_trade_plan(pid, "上移", ["8-K"], {"price_invalidation": 104.0, "hold_basis": "新依据"},
                                      replay_as_of="2026-03-04")
        self.review(pid, thesis_verdict="weakened", action="REDUCE", replay_as_of="2026-03-06",
                    evidence=[evidence("2026-03-05"), evidence("2026-03-05", kind="price", claim="收盘 -9%")])
        view = self.get(pid, view="thesis")
        self.assertEqual(self.PRICE_KEYS & set(self.walk(view)), set())
        self.assertEqual(view["view"], "thesis")
        self.assertEqual(set(view["plan"]), {"thesis", "market_misread", "catalyst", "abandon_facts", "hold_basis",
                                             "review_dates", "frozen_at"})
        self.assertEqual(view["plan"]["hold_basis"], "持有到新品首批出货确认。")  # as frozen
        self.assertEqual(view["current"]["hold_basis"], "新依据")  # as currently effective
        self.assertEqual(view["current"]["version"], 2)
        self.assertEqual(set(view["current"]), {"version", "hold_basis", "review_dates", "abandon_facts"})
        review = view["reviews"][0]
        self.assertEqual((review["thesis_verdict"], review["reviewed_at_effective"]), ("weakened", "2026-03-07T04:59:59Z"))
        self.assertEqual([e["kind"] for e in review["evidence"]], ["filing"])  # the price item is dropped
        self.assertNotIn("110", json.dumps(view))
        self.assertNotIn("104", json.dumps(view))

    def test_full_view_is_unchanged_and_view_is_validated(self):
        plan = self.save()
        full = self.get(plan["plan_id"], view="full")
        self.assertEqual(full["plan"]["price_invalidation"], 90.0)
        self.assertIn("## 论点", full["report_markdown"])
        with self.replay("2026-03-20"):
            self.refuse("VIEW_INVALID", plan_ledger.get_trade_plan, plan["plan_id"], "everything")
            self.assertEqual(plan_ledger.get_trade_plan("nope", "thesis"), {"found": False, "plan_id": "nope"})


class ReportIntegrityTests(LedgerCase):
    def plan_file(self):
        return Path(self.rows("plan")[0]["report_path"])

    def test_ok_mismatch_and_missing(self):
        plan = self.save()
        pid = plan["plan_id"]
        self.assertEqual(self.get(pid)["report_integrity"], "ok")
        path = self.plan_file()
        original = path.read_text()
        path.write_text(original + "\n偷偷改了一句。\n")
        got = self.get(pid)
        self.assertEqual((got["report_integrity"], got["report_markdown"]), ("mismatch", None))
        self.assertTrue(got["found"])  # the record is still returned
        path.write_text(original)
        self.assertEqual(self.get(pid)["report_integrity"], "ok")
        path.unlink()
        got = self.get(pid)
        self.assertEqual((got["report_integrity"], got["report_markdown"]), ("missing", None))

    def test_the_stored_path_is_not_trusted(self):
        plan = self.save()
        real = self.plan_file()
        outside = self.root / "elsewhere.md"
        outside.write_text(PLAN_REPORT.rstrip() + "\n")  # same bytes, wrong place
        lines = [json.loads(x) for x in (self.root / "trade_plans.jsonl").read_text().splitlines()]
        for row in lines:
            if row["kind"] == "plan":
                row["report_path"] = str(outside)
        (self.root / "trade_plans.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in lines))
        # the file under plan-reports/ is still found by id, whatever the stored path says
        self.assertEqual(self.get(plan["plan_id"])["report_integrity"], "ok")
        real.unlink()
        self.assertEqual(self.get(plan["plan_id"])["report_integrity"], "missing")  # the outside copy is ignored
        real.symlink_to(outside)  # a link out of plan-reports/ does not count either
        got = self.get(plan["plan_id"])
        self.assertEqual((got["report_integrity"], got["report_markdown"]), ("missing", None))

    def test_a_missing_hash_cannot_be_verified(self):
        plan = self.save()
        lines = [json.loads(x) for x in (self.root / "trade_plans.jsonl").read_text().splitlines()]
        for row in lines:
            row.pop("report_sha256", None)
        (self.root / "trade_plans.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))
        got = self.get(plan["plan_id"])
        self.assertEqual((got["report_integrity"], got["report_markdown"]), ("mismatch", None))


class ConcurrencyTests(LedgerCase):
    """Rework 1 #6: check + append are one locked step. Each writer reads the ledger, then waits at a barrier so both
    hold the same stale snapshot; without the lock both would pass the check."""

    def race(self, *calls):
        barrier = threading.Barrier(len(calls), timeout=0.4)
        real = plan_ledger._read_rows

        def synced():
            rows = real()
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass  # the lock keeps the other writer out, so only one thread ever waits
            return rows

        results = [None] * len(calls)

        def run(index):
            try:
                results[index] = ("ok", calls[index]())
            except DecisionLogError as exc:
                results[index] = ("err", str(exc))

        with mock.patch.object(plan_ledger, "_read_rows", synced):
            threads = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
        return results

    def seven_live_plans(self):
        for ticker in ("A1", "A2", "A3", "A4", "A5", "A6", "A7"):
            self.save(ticker=ticker, replay_as_of=None)

    def test_two_writers_cannot_both_take_the_eighth_plus_one_slot(self):
        self.seven_live_plans()
        results = self.race(lambda: self.save(ticker="B1", replay_as_of=None),
                            lambda: self.save(ticker="B2", replay_as_of=None))
        self.assertEqual(sorted(r[0] for r in results), ["err", "ok"])
        self.assertIn("ACTIVE_PLAN_LIMIT", [r[1] for r in results if r[0] == "err"][0])
        self.assertEqual(len(self.rows("plan")), 8)
        self.assertEqual(len(self.rows("candidate")), 8)  # no orphan candidate row either

    def test_two_writers_cannot_open_the_same_ticker(self):
        results = self.race(lambda: self.save(replay_as_of=None), lambda: self.save(replay_as_of=None))
        self.assertEqual(sorted(r[0] for r in results), ["err", "ok"])
        self.assertIn("ACTIVE_PLAN_EXISTS", [r[1] for r in results if r[0] == "err"][0])
        self.assertEqual(len(self.rows("plan")), 1)

    def test_two_revisions_get_distinct_versions(self):
        pid = self.save(replay_as_of=None)["plan_id"]
        results = self.race(
            lambda: plan_ledger.revise_trade_plan(pid, "a", ["s"], {"hold_basis": "h1"}),
            lambda: plan_ledger.revise_trade_plan(pid, "b", ["s"], {"hold_basis": "h2"}))
        self.assertEqual([r[0] for r in results], ["ok", "ok"])
        self.assertEqual(sorted(r[1]["version"] for r in results), [2, 3])
        self.assertEqual(sorted(r["version"] for r in self.rows("revision")), [2, 3])

    def test_the_race_test_fails_without_the_lock(self):
        """Self-check: with the lock turned off the same race produces a 9th plan."""
        self.seven_live_plans()
        with mock.patch.object(plan_ledger, "_ledger_lock", lambda: nullcontext()):
            results = self.race(lambda: self.save(ticker="B1", replay_as_of=None),
                                lambda: self.save(ticker="B2", replay_as_of=None))
        self.assertEqual([r[0] for r in results], ["ok", "ok"])
        self.assertEqual(len(self.rows("plan")), 9)

    def test_lock_file_lives_next_to_the_ledger(self):
        self.save()
        self.assertTrue((self.root / "trade_plans.jsonl.lock").exists())


class CandidateTests(LedgerCase):
    def test_wait_and_not_formed_are_recorded(self):
        out = plan_ledger.save_plan_candidate("nvda", "wait", "财报还没出，等事实", host="codex", model="m")
        self.assertTrue(out["saved"])
        plan_ledger.save_plan_candidate("AMD", "not_formed", "找不到可核实的放弃事实", replay_as_of="2026-03-02")
        wait, nf = self.rows("candidate")
        self.assertEqual((wait["ticker"], wait["outcome"], wait["plan_id"], wait["replay"]), ("NVDA", "wait", None, False))
        self.assertEqual((nf["outcome"], nf["replay"]), ("not_formed", True))
        self.assertEqual(wait["candidate_id"], out["candidate_id"])
        self.assertEqual(wait["model_recorded"]["source"], "self_reported")

    def test_candidate_validation(self):
        self.refuse("OUTCOME_INVALID", plan_ledger.save_plan_candidate, "NVDA", "plan", "x")
        self.refuse("OUTCOME_INVALID", plan_ledger.save_plan_candidate, "NVDA", "skip", "x")
        self.refuse("REASON_REQUIRED", plan_ledger.save_plan_candidate, "NVDA", "wait", " ")
        self.refuse("TICKER_INVALID", plan_ledger.save_plan_candidate, "no way", "wait", "x")
        self.refuse("REPLAY_AS_OF_INVALID", plan_ledger.save_plan_candidate, "NVDA", "wait", "x", replay_as_of="2999-01-01")

    def test_candidate_does_not_count_as_active_plan(self):
        plan_ledger.save_plan_candidate("NVDA", "wait", "等财报")
        self.save(replay_as_of=None)  # still allowed


class EntryValidSessionsTests(LedgerCase):
    """Rework 3: the paper order is a limit buy valid for entry_valid_sessions sessions (1..10, default 5)."""

    def test_default_is_five_and_is_frozen_in_the_record(self):
        out = self.save()
        self.assertEqual(out["entry_valid_sessions"], 5)
        self.assertEqual(self.rows("plan")[0]["entry_valid_sessions"], 5)
        self.assertEqual(self.rows("plan")[0]["fill_rule"], "limit_band_within_entry_valid_sessions")   # unchanged

    def test_caller_value_is_stored(self):
        for n, ticker in ((1, "AMD"), (10, "MU"), (3, "NVDA")):
            out = self.save(entry_valid_sessions=n, ticker=ticker)
            self.assertEqual(out["entry_valid_sessions"], n)
        self.assertEqual([r["entry_valid_sessions"] for r in self.rows("plan")], [1, 10, 3])

    def test_bad_values_are_refused_and_write_nothing(self):
        for bad in (0, 11, -1, 2.5, True, "5", None):
            with self.subTest(bad=bad):
                self.refuse_plan("ENTRY_VALID_SESSIONS_INVALID", entry_valid_sessions=bad)

    def test_it_is_not_a_generated_field(self):
        self.assertNotIn("entry_valid_sessions", plan_ledger.GENERATED_FIELDS)

    def test_list_summary_shows_it_and_a_record_without_the_field_reads_as_one_session(self):
        new = self.save(entry_valid_sessions=7)
        legacy_id = self.save(ticker="AMD")["plan_id"]
        path = self.root / "trade_plans.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        for row in rows:                        # make AMD an old record: no field at all
            if row.get("plan_id") == legacy_id and row["kind"] == "plan":
                del row["entry_valid_sessions"]
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        with self.replay("2026-03-03"):
            plans = {p["ticker"]: p for p in plan_ledger.list_trade_plans()["plans"]}
        self.assertEqual(plans["NVDA"]["entry_valid_sessions"], 7)
        self.assertEqual(plans["AMD"]["entry_valid_sessions"], 1)
        self.assertEqual(new["entry_valid_sessions"], 7)


class SizeTests(LedgerCase):
    def test_size_trade_plan_passes_through(self):
        out = plan_ledger.size_trade_plan(100, 90)  # default budget 1000: floor(1000 / 10) = 100 shares, r0 = 1000
        self.assertEqual((out["risk_per_share"], out["shares"], out["r0"]), (10, 100, 1000))
        self.assertEqual(plan_ledger.size_trade_plan(100, 90, 1050)["shares"], 105)
        self.assertEqual(self.rows(), [])  # read-only

    def test_size_errors_become_ledger_errors_with_codes(self):
        for args, code in (((100, 100), "STOP_NOT_BELOW_ENTRY"), ((100, 110), "STOP_NOT_BELOW_ENTRY"),
                           ((100, 90, 5), "RISK_BUDGET_TOO_SMALL"), ((100, 90, 0), "INVALID_NUMBER"),
                           ((float("nan"), 90), "INVALID_NUMBER"), ((100, -1), "INVALID_NUMBER")):
            with self.subTest(args=args):
                with self.assertRaises(DecisionLogError) as ctx:
                    plan_ledger.size_trade_plan(*args)
                self.assertTrue(str(ctx.exception).startswith(code), str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
