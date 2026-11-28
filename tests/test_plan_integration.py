"""L1 integration: plan tools through the MCP server module, scripts/score-plans.py, scripts/dev-research.sh.

Offline: STOCK_AGENT_DATA_DIR points at a temp dir, get_price_history is mocked, no model is called.
"""
import asyncio
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from mcp.server.mcpserver.exceptions import ToolError

from product.deterministic import decision_scoring as ds
from product.mcp import data_tools, server
from tests.test_plan_ledger import PLAN_REPORT, REVIEW_REPORT, plan_args, review_args  # noqa: F401 - fixtures only

REPO = Path(__file__).resolve().parents[1]
TOOLS = {"size_trade_plan", "save_plan_candidate", "save_trade_plan", "revise_trade_plan", "save_plan_review",
         "record_plan_choice", "get_trade_plan", "list_trade_plans"}


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server_args = plan_args  # every plan_args key is a parameter of the server tool


def weekdays(start: str, end: str) -> list[str]:
    day, last, out = date.fromisoformat(start), date.fromisoformat(end), []
    while day <= last:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


# NVDA bars (open, close). Hand calculation for plan 1 (frozen 2026-03-02 23:59:59 NY, 100 shares, R0 = 1000,
# stop 90, cap_date 2026-04-01, cost 10 bp per side):
#   fill  2026-03-03 open 100 -> buy 100 x 100 = 10,000.00
#   review EXIT effective 2026-03-06 23:59:59 -> sell at 2026-03-09 open 104 = 10,400.00
#     plan:        gross +400.00, costs 10.00 + 10.40 = 20.40, net +379.60, R +0.380
#   close 2026-03-10 = 89 <= 90 -> simple exit sells at 2026-03-11 open 84 = 8,400.00
#     simple_exit: gross -1,600.00, costs 10.00 + 8.40 = 18.40, net -1,618.40, R -1.618 (gap past the stop: R < -1)
#   hold to cap day 2026-04-01 close 106 = 10,600.00
#     hold:        gross +600.00, costs 10.00 + 10.60 = 20.60, net +579.40, R +0.579; lowest close 85 -> R -1.500
#   pairs: plan - hold = 379.60 - 579.40 = -199.80 (R -0.200); plan - simple = 379.60 + 1,618.40 = +1,998.00 (R +1.998)
# Plan 2 (frozen 2026-03-12): next open 2026-03-13 = 110, outside [98, 102] -> unfilled.
NVDA = {"2026-03-03": (100, 100), "2026-03-04": (100, 101), "2026-03-05": (101, 102), "2026-03-06": (102, 103),
        "2026-03-09": (104, 105), "2026-03-10": (105, 89), "2026-03-11": (84, 85), "2026-03-13": (110, 110),
        "2026-04-01": (95, 106)}
CALENDAR = weekdays("2026-02-16", "2026-04-10")


def fake_price_history(fail=(), splits=None, incomplete=(), calls=None):
    """Emulates data_tools.get_price_history. NVDA bars are as traded; like Yahoo, every split shifts earlier rows to
    the post-split per-share basis, and with `as_of` the splits after that day are undone (and not returned).
    `splits` = {ticker: [[ex_date, "2:1"], ...]}; `incomplete` = tickers whose last row is flagged as unfinished."""
    splits = splits or {}

    def get(ticker, start=None, end=None, max_rows=None, as_of=None, **_):
        if calls is not None:
            calls.append({"ticker": ticker, "as_of": as_of, "end": end})
        if ticker in fail:
            raise data_tools.DataToolError("YAHOO_DOWN: simulated outage")
        def factor_of(ratio):      # an unreadable ratio ("N/A") still shifts nothing here; the script must not guess
            try:
                return float(ratio.split(":")[0]) / float(ratio.split(":")[1])
            except (ValueError, IndexError):
                return 1.0
        applied = [(d, factor_of(r)) for d, r in splits.get(ticker, []) if as_of is None or d <= as_of]
        rows = []
        for day in CALENDAR:
            if end is not None and day > end:
                continue
            if ticker == "SPY":
                o = c = 500.0
            elif day in NVDA:
                o, c = NVDA[day]
            elif day < "2026-03-03":
                o = c = 99
            elif day <= "2026-03-31":
                o = c = 95
            else:
                o = c = 107
            for d, factor in applied:
                if day < d:
                    o, c = o / factor, c / factor
            rows.append([day, o, o, c, c, c, 1000])
        last = rows[-1][0]
        return {"ticker": ticker, "rows": rows, "last_row_incomplete_session": ticker in incomplete,
                "splits": [[d, r] for d, r in splits.get(ticker, []) if d in {x for x, _ in applied} and d <= last]}
    return get


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"STOCK_AGENT_DATA_DIR": self.tmp.name}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for var in ("STOCK_AGENT_REPLAY_AS_OF", "STOCK_AGENT_RUN_MODEL"):
            os.environ.pop(var, None)
        self.root = Path(self.tmp.name).resolve()

    def rows(self, kind=None):
        path = self.root / "trade_plans.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if kind is None or r["kind"] == kind]

    def chain(self):
        """candidate(wait), candidate(not_formed), plan 1 -> EXIT review -> plan 2 on the same ticker (all replays)."""
        server.save_plan_candidate("AMD", "wait", "等财报日期确认。", replay_as_of="2026-03-02")
        server.save_plan_candidate("TSLA", "not_formed", "没有可核实的放弃理由。", replay_as_of="2026-03-02")
        first = server.save_trade_plan(**server_args())
        with self.assertRaises(ToolError) as caught:  # still in progress
            server.save_trade_plan(**server_args(replay_as_of="2026-03-04"))
        self.assertIn("ACTIVE_PLAN_EXISTS", str(caught.exception))
        review = server.save_plan_review(**review_args(first["plan_id"], replay_as_of="2026-03-06"))
        second = server.save_trade_plan(**server_args(replay_as_of="2026-03-12", review_dates=["2026-03-25"]))
        return first, review, second


class ServerToolsCase(Base):
    def test_eight_tools_registered_with_the_right_annotations(self):
        tools = {t.name: t for t in asyncio.run(server.server.list_tools())}
        self.assertLessEqual(TOOLS, set(tools))
        for name in TOOLS:
            read_only = bool(tools[name].annotations.read_only_hint)
            self.assertEqual(read_only, name in {"size_trade_plan", "get_trade_plan", "list_trade_plans"}, name)
        for name in ("save_trade_plan", "save_plan_review"):  # docstring tells the model what the tool generates
            self.assertIn("GENERATED BY THE TOOL", tools[name].description)

    def test_save_review_exit_reopen_chain(self):
        first, review, second = self.chain()
        self.assertEqual((first["shares_planned"], first["r0"]), (100, 1000.0))
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        self.assertEqual(review["reviewed_at_effective"], "2026-03-07T04:59:59Z")
        with self.assertRaises(ToolError) as caught:  # a replay plan is invisible to a live session
            server.get_trade_plan(first["plan_id"])
        self.assertIn("PLAN_REPLAY_MISMATCH", str(caught.exception))
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-12"}):
            old, new = server.get_trade_plan(first["plan_id"]), server.get_trade_plan(second["plan_id"])
        self.assertEqual((old["active"], old["active_reason"]), (False, "exit_review"))
        self.assertEqual((new["active"], new["reviews"]), (True, []))
        self.assertEqual([r["action"] for r in old["reviews"]], ["EXIT"])
        self.assertIn("## 论点", old["report_markdown"])
        listed = server.list_trade_plans()
        self.assertEqual([p["plan_id"] for p in listed["plans"]], [])  # replay plans are not listed in a live session
        self.assertEqual(len(self.rows("candidate")), 4)  # wait, not_formed, plan, plan

    def test_replay_session_lists_and_defaults_replay_date(self):
        os.environ["STOCK_AGENT_REPLAY_AS_OF"] = "2026-03-02"
        os.environ["STOCK_AGENT_RUN_MODEL"] = "gpt-6.1-terra"
        saved = server.save_trade_plan(**server_args(replay_as_of=None, model="self-reported-x"))
        self.assertTrue(saved["replay"])
        self.assertEqual(saved["frozen_at"], "2026-03-03T04:59:59Z")
        plan = self.rows("plan")[0]
        self.assertEqual(plan["model_recorded"], {"value": "gpt-6.1-terra", "source": "run_env"})
        listed = server.list_trade_plans()
        self.assertEqual([p["plan_id"] for p in listed["plans"]], [saved["plan_id"]])
        self.assertEqual(listed["active_count"], 1)
        # a same-day revision is refused: it must be effective after the freeze
        with self.assertRaises(ToolError) as caught:
            server.revise_trade_plan(saved["plan_id"], "新事实", ["8-K"], {"price_invalidation": 91.0})
        self.assertIn("EFFECTIVE_NOT_AFTER_FROZEN", str(caught.exception))

    def test_errors_reach_the_model_with_codes(self):
        with self.assertRaises(ToolError) as caught:
            server.size_trade_plan(100, 100)
        self.assertIn("STOP_NOT_BELOW_ENTRY", str(caught.exception))
        self.assertEqual(server.size_trade_plan(100, 90, 1000), {"risk_per_share": 10.0, "shares": 100, "r0": 1000.0})
        with self.assertRaises(ToolError) as caught:  # the tool signature has no generated fields at all
            server.save_trade_plan(**server_args(), plan_id="x")
        self.assertIn("unexpected keyword argument 'plan_id'", str(caught.exception))
        self.assertEqual(self.rows(), [])
        with self.assertRaises(ToolError) as caught:
            server.record_plan_choice("nope", "nope", "followed", "")
        self.assertIn("PLAN_NOT_FOUND", str(caught.exception))
        self.assertEqual(server.get_trade_plan("nope"), {"found": False, "plan_id": "nope"})


class ScorePlansCase(Base):
    def setUp(self):
        super().setUp()
        self.script = load_script("score-plans")

    def run_script(self, *args, fail=()):
        out = io.StringIO()
        with mock.patch.object(data_tools, "get_price_history", fake_price_history(fail)), redirect_stdout(out):
            code = self.script.main(["--plans", str(self.root / "trade_plans.jsonl"), *args])
        return code, out.getvalue()

    def test_three_lines_pairs_funnel_hand_checkable(self):
        first, _, second = self.chain()
        out_file = self.root / "out" / "plans.md"
        code, printed = self.run_script("--as-of", "2026-04-10", "--out", str(out_file))
        self.assertEqual(code, 0)
        self.assertIn("wrote", printed)
        text = out_file.read_text(encoding="utf-8")
        # sections for both plans, cap status stated per plan
        self.assertIn(first["plan_id"], text)
        self.assertIn(second["plan_id"], text)
        self.assertIn("cap_date = 2026-04-01，已到期（cap 交易日 2026-04-01）", text)
        self.assertIn("cap_date = 2026-04-11，未到期，open 估值", text)
        # plan 1: three lines with legs (date, price, shares, reason) and the hand-calculated numbers
        for label in ("照计划", "持有对照", "简单退出对照"):
            self.assertIn(f"**{label}成交明细**", text)
        self.assertIn("| 2026-03-03 | 买入 | 100 | 100 | 10,000.00 | 10.00 | 成交 |", text)
        self.assertIn("| 2026-03-09 | 卖出 | 104 | 100 | 10,400.00 | 10.40 | 复核 |", text)
        self.assertIn("| 2026-03-11 | 卖出 | 84 | 100 | 8,400.00 | 8.40 | 止损 |", text)
        self.assertIn("收盘 89 在 2026-03-10 ≤ 失效价 90", text)
        self.assertIn("| 2026-04-01 | 卖出 | 106 | 100 | 10,600.00 | 10.60 | cap |", text)
        self.assertIn("| 照计划 | closed | 400.00 | 20.40 | +379.60 | +0.380 |", text)
        self.assertIn("| 简单退出对照 | closed | -1,600.00 | 18.40 | -1,618.40 | -1.618 |", text)
        self.assertIn("| 持有对照 | closed | 600.00 | 20.60 | +579.40 | +0.579 | +5.79 | -1.500 |", text)
        self.assertIn("照计划 − 持有 = -199.80 / -0.200", text)
        self.assertIn("照计划 − 简单退出 = +1,998.00 / +1.998", text)
        # plan 2 never filled: status, no amounts
        self.assertIn("成交：状态 unfilled；日期 2026-03-13；开盘 110", text)
        # funnel: candidate outcomes and settlement statuses (all replay records)
        funnel = text[text.index("## 漏斗"):]
        self.assertRegex(funnel, r"\| plan \| 0 \| 2 \|")
        self.assertRegex(funnel, r"\| wait \| 0 \| 1 \|")
        self.assertRegex(funnel, r"\| not_formed \| 0 \| 1 \|")
        self.assertRegex(funnel, r"\| closed \| 0 \| 1 \|")
        self.assertRegex(funnel, r"\| unfilled \| 0 \| 1 \|")

    def test_open_valuation_before_cap_is_labelled(self):
        self.chain()
        code, text = self.run_script("--as-of", "2026-03-20")
        self.assertEqual(code, 0)
        self.assertIn("cap_date = 2026-04-01，未到期，open 估值", text)
        self.assertIn("估值（未实现）", text)  # the hold line is valued at the last close, not closed
        self.assertIn("| 持有对照 | open（未实现） |", text)

    def test_price_failure_is_reported_not_treated_as_no_data(self):
        self.chain()
        code, text = self.run_script("--as-of", "2026-04-10", fail=("NVDA",))
        self.assertEqual(code, 1)
        self.assertIn("price_error", text)
        self.assertIn("YAHOO_DOWN", text)
        self.assertIn("## 警告", text)
        self.assertRegex(text[text.index("## 漏斗"):], r"\| price_error \| 0 \| 2 \|")
        err = io.StringIO()
        with mock.patch.object(data_tools, "get_price_history", fake_price_history(("SPY",))), \
                mock.patch("sys.stderr", err), redirect_stdout(io.StringIO()):
            code = self.script.main(["--plans", str(self.root / "trade_plans.jsonl"), "--as-of", "2026-04-10"])
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", err.getvalue())

    def test_empty_ledger(self):
        code, text = self.run_script("--as-of", "2026-04-10")
        self.assertEqual(code, 0)
        self.assertIn("（无计划）", text)
        self.assertIn("## 漏斗", text)


class ScoreReworkCase(Base):
    """Rework 1: splits, cutting at the scoring day, unfinished sessions, expired plans (astra review #1 #3 #5 #6).

    Plan P (frozen 2026-03-02 23:59:59 NY, 100 shares, R0 = 1000, stop 90, horizon 5 -> cap_date 03-07, cap day 03-06):
      fill 03-03 open 100 (buy 10,000.00); closes 03-03..03-06 = 100, 101, 102, 103, never <= 90
      cap close 103 -> sell 10,300.00; gross +300.00; costs 10.00 + 10.30 = 20.30; net +279.70; R +0.280 (0.2797)
    Plan Q = P with horizon 8 (cap_date 03-10, close 89): hold to 03-09 close 105 -> gross +500, costs 10, net +490, R +0.490;
      to the 03-10 cap close 89 -> gross -1,100, costs 10.00 + 8.90 = 18.90, net -1,118.90, R -1.119.
    """

    def setUp(self):
        super().setUp()
        self.script = load_script("score-plans")
        self.path = self.root / "trade_plans.jsonl"

    def score(self, as_of, now=None, **mock_kw):
        calls = []
        rows = self.script.read_ledger(self.path)
        with mock.patch.object(data_tools, "get_price_history", fake_price_history(calls=calls, **mock_kw)):
            text, code = self.script.score(rows, as_of, source="ledger", now=now)
        return text, code, calls

    def plan_p(self, **over):
        return server.save_trade_plan(**server_args(horizon_cap_days=5, review_dates=["2026-03-05"], **over))

    HOLD_CLOSED_P = "| 持有对照 | closed | 300.00 | 20.30 | +279.70 | +0.280 |"

    def test_baseline_without_splits(self):
        self.plan_p()
        text, code, calls = self.score("2026-03-20")
        self.assertEqual(code, 0)
        self.assertIn(self.HOLD_CLOSED_P, text)
        self.assertTrue(all(c["as_of"] == "2026-03-20" for c in calls), calls)  # the tool must undo later splits

    def test_split_inside_the_window_is_not_settleable(self):
        self.plan_p()
        text, code, _ = self.score("2026-03-20", splits={"NVDA": [["2026-03-05", "2:1"]]})
        self.assertEqual(code, 0)
        self.assertIn("| 持有对照 | not_settleable | — | — | — |", text)
        self.assertIn("split_in_window", text)
        self.assertIn("冻结日至结束日之间有拆股", text)
        self.assertRegex(text[text.index("## 漏斗"):], r"\| not_settleable \| 0 \| 1 \|")

    def test_split_after_the_position_ended_is_restored_and_ignored(self):
        self.plan_p()
        # ex-date 03-10: Yahoo shows 03-03..03-06 halved (open 50, close 50.5 ...); the script restores them
        text, _, _ = self.score("2026-03-20", splits={"NVDA": [["2026-03-10", "2:1"]]})
        self.assertIn(self.HOLD_CLOSED_P, text)
        self.assertNotIn("split_in_window", text)
        self.assertIn("成交：状态 filled", text)

    def test_unparsed_split_ratio_after_the_freeze_is_not_settleable(self):
        self.plan_p()
        text, code, _ = self.score("2026-03-20", splits={"NVDA": [["2026-03-10", "N/A"]]})   # after the position ended
        self.assertEqual(code, 0)
        self.assertIn("| 持有对照 | not_settleable | — | — | — |", text)
        self.assertIn("| 照计划 | not_settleable | — | — | — |", text)
        self.assertIn("| 简单退出对照 | not_settleable | — | — | — |", text)
        self.assertIn("split_ratio_unparsed", text)
        self.assertNotIn(self.HOLD_CLOSED_P, text)
        self.assertRegex(text[text.index("## 漏斗"):], r"\| not_settleable \| 0 \| 1 \|")

    def test_unparsed_split_ratio_before_the_freeze_does_not_block_settlement(self):
        self.plan_p()
        text, _, _ = self.score("2026-03-20", splits={"NVDA": [["2026-02-27", "N/A"]]})   # frozen 03-02: rows unaffected
        self.assertIn(self.HOLD_CLOSED_P, text)
        self.assertNotIn("split_ratio_unparsed", text.split("## 警告")[0])
        self.assertIn("拆股比例无法解析", text)

    def test_split_after_the_scoring_day_does_not_matter(self):
        self.plan_p()
        text, _, calls = self.score("2026-03-10", splits={"NVDA": [["2026-03-20", "2:1"]]})
        self.assertIn(self.HOLD_CLOSED_P, text)
        self.assertTrue(calls and all(c["as_of"] == "2026-03-10" for c in calls), calls)

    def test_scoring_cuts_the_ledger_at_the_scoring_day(self):
        saved = server.save_trade_plan(**server_args())                                    # frozen 03-02
        server.revise_trade_plan(saved["plan_id"], "新事实", ["8-K"], {"price_invalidation": 91.0},
                                 replay_as_of="2026-03-04")                                # effective 03-04 23:59:59
        review = server.save_plan_review(**review_args(saved["plan_id"], replay_as_of="2026-03-06"))
        later = server.save_trade_plan(**server_args(ticker="AAPL", replay_as_of="2026-03-12", review_dates=["2026-03-25"]))
        server.save_plan_candidate("TSLA", "wait", "等待。", replay_as_of="2026-03-09")
        early, _, _ = self.score("2026-03-03")
        self.assertIn(saved["plan_id"], early)
        for future in (review["review_id"], later["plan_id"], "v2 = 91", "AAPL", "TSLA"):
            self.assertNotIn(future, early)
        self.assertIn("v1 = 90", early)
        # dropped as later: revision, review, the AAPL plan and its candidate row, the TSLA candidate
        self.assertIn("已排除：5 条", early)
        funnel = early[early.index("## 漏斗"):]
        self.assertRegex(funnel, r"\| plan \| 0 \| 1 \|")
        self.assertRegex(funnel, r"\| wait \| 0 \| 0 \|")
        self.assertRegex(funnel, r"\| open \| 0 \| 1 \|")
        full, _, _ = self.score("2026-04-10")
        for known in (review["review_id"], later["plan_id"], "v2 = 91"):
            self.assertIn(known, full)
        self.assertRegex(full[full.index("## 漏斗"):], r"\| wait \| 0 \| 1 \|")

    def test_cut_rows_by_kind_and_choice_fallback(self):
        rows = [{"kind": "candidate", "created_at_effective": "2026-03-03T04:59:59Z"},
                {"kind": "candidate", "created_at_effective": "2026-03-04T04:59:59Z"},
                {"kind": "plan", "frozen_at": "2026-03-03T04:59:59Z"},
                {"kind": "revision", "effective_at": "2026-03-04T04:59:59Z", "recorded_at": "2026-03-01T00:00:00Z"},
                {"kind": "review", "reviewed_at_effective": "2026-03-07T04:59:59Z"},
                {"kind": "choice", "effective_at": "2026-03-02T10:00:00-05:00", "recorded_at": "2026-03-09T00:00:00Z"},
                {"kind": "choice", "recorded_at": "2026-03-09T00:00:00Z"},      # old record: falls back to recorded_at
                {"kind": "choice", "recorded_at": "2026-03-02T12:00:00Z"},
                {"kind": "plan"}]                                                 # no time at all
        kept, later, undatable = self.script.cut_rows(rows, "2026-03-02")        # cutoff 03-02 23:59:59 NY = 03-03 04:59:59Z
        self.assertEqual((len(kept), later, undatable), (4, 4, 1))
        self.assertEqual([r["kind"] for r in kept], ["candidate", "plan", "choice", "choice"])

    def test_unfinished_session_is_not_used_before_the_close(self):
        server.save_trade_plan(**server_args(horizon_cap_days=8, review_dates=["2026-03-05"]))
        before = datetime(2026, 3, 10, 11, 0, tzinfo=ds.NY)
        text, _, calls = self.score("2026-03-10", now=before)
        self.assertIn("实际截止：2026-03-09", text)
        self.assertIn("尚未收盘", text)
        self.assertIn("| 持有对照 | open（未实现） | 500.00 | 10.00 | +490.00 | +0.490 |", text)   # not the 03-10 close of 89
        self.assertTrue(all(c["end"] == "2026-03-09" for c in calls), calls)
        after = datetime(2026, 3, 10, 17, 0, tzinfo=ds.NY)
        text, _, _ = self.score("2026-03-10", now=after)
        self.assertNotIn("尚未收盘", text)
        self.assertIn("| 持有对照 | closed | -1,100.00 | 18.90 | -1,118.90 | -1.119 |", text)

    def test_tool_flag_incomplete_session_drops_the_last_row(self):
        server.save_trade_plan(**server_args(horizon_cap_days=8, review_dates=["2026-03-05"]))
        text, _, _ = self.score("2026-03-10", now=datetime(2026, 3, 10, 17, 0, tzinfo=ds.NY), incomplete=("NVDA", "SPY"))
        self.assertIn("| 持有对照 | open（未实现） | 500.00 | 10.00 | +490.00 | +0.490 |", text)
        self.assertIn("2026-03-10 的行情未完成", text)

    def test_plan_expired_before_any_open(self):
        # frozen Friday 2026-03-06 23:59:59, horizon 1 -> cap_date Saturday 03-07; the first open is Monday 03-09
        server.save_trade_plan(**server_args(replay_as_of="2026-03-06", horizon_cap_days=1, review_dates=["2026-03-20"]))
        text, code, _ = self.score("2026-03-20")
        self.assertEqual(code, 0)
        self.assertIn("成交：状态 expired_unfilled", text)
        self.assertIn("| 持有对照 | expired_unfilled | — | — | — |", text)
        self.assertIn("（无成交）", text)
        self.assertRegex(text[text.index("## 漏斗"):], r"\| expired_unfilled \| 0 \| 1 \|")


class ScoreEntryOrderCase(Base):
    """Rework 3 end to end: score-plans on a limit-fill plan and on an old record without entry_valid_sessions.

    Plan (server default entry_valid_sessions = 5): band [98, 102], entry_ref 100, stop 90, 100 shares, R0 = 1000, frozen
    2026-03-02 23:59:59 NY. Bars: 03-03 open 105 (above the top), close 101, low = close (the fake feed) = 101 <= 102
    -> limit fill at 102: buy 100 x 102 = 10,200.00 (cost 10.20), fill method "限价上限".
    hold to the 04-01 cap close 106: sell 10,600.00 (cost 10.60); gross +400.00; costs 20.80; net +379.20; R +0.379;
      lowest close 85 (03-11) -> R (85 - 102) x 100 / 1000 = -1.700
    plan = simple_exit: close 03-10 = 89 <= 90 -> sell 03-11 open 84 = 8,400.00 (cost 8.40); gross -1,800.00;
      costs 10.20 + 8.40 = 18.60; net -1,818.60; R -1.819
    The same bars with the field removed from the record (an old plan): the 03-03 open 105 is above the band -> unfilled.
    """

    def setUp(self):
        super().setUp()
        self.script = load_script("score-plans")
        patch = mock.patch.dict(NVDA, {"2026-03-03": (105, 101)})
        patch.start()
        self.addCleanup(patch.stop)

    def score(self):
        rows = self.script.read_ledger(self.root / "trade_plans.jsonl")
        with mock.patch.object(data_tools, "get_price_history", fake_price_history()):
            return self.script.score(rows, "2026-04-10", source="ledger")

    def test_limit_fill_at_the_band_top_with_hand_numbers(self):
        server.save_trade_plan(**server_args())
        text, code = self.score()
        self.assertEqual(code, 0)
        self.assertIn("挂单有效期 5 个交易日", text)
        self.assertIn("成交：状态 filled；日期 2026-03-03；开盘 105.0；成交价 102（限价上限）；已看 1 / 5 个交易日；股数 100", text)
        self.assertIn("| 2026-03-03 | 买入 | 102 | 100 | 10,200.00 | 10.20 | 成交 | 开盘 105 高于区间上限，当日最低触及上限，按上限成交 |", text)
        self.assertIn("| 持有对照 | closed | 400.00 | 20.80 | +379.20 | +0.379 | +3.72 | -1.700 |", text)
        self.assertIn("| 照计划 | closed | -1,800.00 | 18.60 | -1,818.60 | -1.819 |", text)
        self.assertIn("R0 = 1000", text)       # R0 unchanged by the actual fill price
        self.assertIn("限价挂单", text)

    def test_record_without_the_field_is_one_session_open_only(self):
        server.save_trade_plan(**server_args())
        path = self.root / "trade_plans.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        for row in rows:
            row.pop("entry_valid_sessions", None)
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
        text, code = self.score()
        self.assertEqual(code, 0)
        self.assertIn("旧记录无该字段，按 1 个交易日处理", text)
        self.assertIn("成交：状态 unfilled；日期 2026-03-03；开盘 105.0；股数 —", text)
        self.assertNotIn("；成交价", text)
        self.assertIn("| 持有对照 | unfilled | — | — | — |", text)

    def test_order_cancelled_by_a_close_below_the_stop_is_in_the_funnel(self):
        # 03-03 open 85 (below the band, no fill), close 85 <= stop 90 -> order cancelled before any fill
        with mock.patch.dict(NVDA, {"2026-03-03": (85, 85)}):
            server.save_trade_plan(**server_args())
            text, code = self.score()
        self.assertEqual(code, 0)
        self.assertIn("成交：状态 cancelled_stop_before_fill", text)
        self.assertIn("| 照计划 | cancelled_stop_before_fill | — | — | — |", text)
        self.assertRegex(text[text.index("## 漏斗"):], r"\| cancelled_stop_before_fill \| 0 \| 1 \|")


class DevResearchCase(unittest.TestCase):
    script = REPO / "scripts" / "dev-research.sh"

    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(self.script)], check=True)

    def test_plan_and_review_are_exclusive_and_documented(self):
        done = subprocess.run(["bash", str(self.script), "codex", "NVDA", "--plan", "x", "--review", "y"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)  # refused before any run directory or model call
        for flag in ("--plan", "--review", "--seed-plans", "STOCK_AGENT_RUN_MODEL"):
            self.assertIn(flag, done.stdout)

    def test_replay_prompts_of_plan_and_review_separate_data_tools_from_plan_tools(self):
        lines = {k: [l for l in self.script.read_text(encoding="utf-8").splitlines() if f"按 {k} Skill 完成并保存，" in l]
                 for k in ("trade-plan", "plan-review", "decision-card")}
        for kind in ("trade-plan", "plan-review"):
            self.assertEqual(len(lines[kind]), 1, kind)
            self.assertIn("带 as_of 参数的数据工具都传 as_of=${as_of}；计划工具由会话回放设置自动限定。", lines[kind][0])
            self.assertNotIn("所有工具带", lines[kind][0])
        self.assertIn("所有工具带 as_of=${as_of}", lines["decision-card"][0])   # other modes unchanged

    def test_every_pair_of_task_modes_is_refused(self):
        modes = {"--decision": "held", "--plan": "x", "--review": "y", "--group": "AAPL MSFT", "--moment": "m"}
        flags = list(modes)
        for i, first in enumerate(flags):
            for second in flags[i + 1:]:
                done = subprocess.run(["bash", str(self.script), "codex", "NVDA", first, modes[first],
                                       second, modes[second], "--as-of", "2026-03-02"], capture_output=True, text=True)
                self.assertEqual(done.returncode, 2, f"{first} {second}")
                self.assertIn("任务模式", done.stdout)

    def test_run_json_lists_trade_plans(self):
        source = self.script.read_text(encoding="utf-8")
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY\n", source, re.S)
        self.assertEqual(len(blocks), 2)
        self.assertIn("STOCK_AGENT_RUN_MODEL", source)
        with tempfile.TemporaryDirectory() as run_dir:
            rows = [{"kind": "candidate", "outcome": "plan", "plan_id": "p1", "ticker": "NVDA"},
                    {"kind": "plan", "plan_id": "p1", "ticker": "NVDA", "shares_planned": 100, "r0": 1000.0,
                     "report_path": "/x/NVDA-p1.md", "replay": True},
                    {"kind": "review", "plan_id": "p1", "ticker": "NVDA", "review_id": "r1",
                     "thesis_verdict": "broken", "action": "EXIT"}]
            Path(run_dir, "trade_plans.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            done = subprocess.run([sys.executable, "-", run_dir, "rid", "codex", "m", "NVDA", "t0", "0", ""],
                                  input=blocks[1], capture_output=True, text=True, check=True)
            record = json.loads(Path(run_dir, "run.json").read_text())
            self.assertEqual(json.loads(done.stdout), record)
        self.assertEqual([p["kind"] for p in record["trade_plans"]], ["candidate", "plan", "review"])
        self.assertEqual(record["trade_plans"][1]["shares_planned"], 100)
        self.assertEqual(record["trade_plans"][2]["action"], "EXIT")
        self.assertEqual(record["trade_decisions"], [])  # existing keys are unchanged


if __name__ == "__main__":
    unittest.main()
