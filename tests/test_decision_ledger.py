"""Offline tests for decision/v2 records (save_trade_decision) and scripts/decision-record.py.

Every test points STOCK_AGENT_DATA_DIR at a temp dir; nothing touches .local/data or evals/forward.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from product.mcp import decision_ledger, settings
from product.mcp.decision_log import CAUSES, DecisionLogError

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "decision-record.py"

REPORT = """# INTU · E2 · 2026-03-06 收盘 · 持有
动作：REDUCE（0.5）｜主窗口：60 日｜类型：有判断

## 结论
软件板块抛售中的个股性下杀，先减半。

## 概率与收益
相对板块 p_outperform 0.42（基准 0.48）。

## 消息归因
earnings_guidance｜公司原因 是｜明确指引下修 否

## 上次决策
无。

## 复核条件
收盘跌破 420；下季度指引上调

## 数据缺口
无

## 来源
get_key_moments；8-K
"""


def base(**over):
    args = dict(
        ticker="INTU", source="on_demand", position_state="held", group="E2",
        event={"event_date": "2026-03-05", "moment": "break_down", "deviation_z": -2.4},
        benchmark="IGV", action="REDUCE", cash_destination="cash",
        p_outperform={"baseline": 0.48, "case": 0.42, "basis": "指引偏弱"},
        review_triggers=["收盘跌破 420", "下季度指引上调"], thesis="个股性下杀，先减半。",
        report_markdown=REPORT,
        attribution={"primary_cause": "earnings_guidance", "company_cause": True, "explicit_guidance_cut": False},
        hold_type=None, prior_decision_id=None, host="codex", model="gpt-6.1-terra")
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
        self.root = Path(self.tmp.name).resolve()

    def save(self, **over):
        return decision_ledger.save_trade_decision(**base(**over))

    def rows(self):
        path = self.root / "trade_decisions.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def rejected(self, code, **over):
        with self.assertRaises(DecisionLogError) as ctx:
            self.save(**over)
        self.assertIn(code, str(ctx.exception))
        self.assertEqual(self.rows(), [])


class SaveTests(LedgerCase):
    def test_saves_record_and_report_in_data_dir(self):
        out = self.save()
        row = self.rows()[0]
        self.assertEqual(row["schema"], "decision/v2")
        self.assertEqual(row["decision_id"], out["decision_id"])
        self.assertEqual(row["info_cutoff"], row["decided_at"])
        self.assertEqual(row["decided_at_effective"], row["decided_at"])
        self.assertFalse(row["replay"])
        self.assertEqual(row["fill_rule"], "next_regular_open_after_decided_at")
        self.assertIn("commit", row["code_version"])
        report = Path(row["report_path"])
        self.assertEqual(report.parent.parent, self.root / "trade-reports")
        self.assertEqual(report.name, f"INTU-{row['decision_id']}.md")
        self.assertEqual(hashlib.sha256(report.read_bytes()).hexdigest(), row["report_sha256"])
        self.assertFalse((self.root / "decisions.jsonl").exists())  # old log untouched

    def test_ticker_normalised(self):
        self.save(ticker=" brk.b ", report_markdown=REPORT.replace("INTU", "BRK-B"))
        self.assertEqual(self.rows()[0]["ticker"], "BRK-B")

    def test_generated_fields_are_refused(self):
        for name in ("decision_id", "decided_at", "info_cutoff", "w0", "w1", "horizon_days", "schema",
                     "fill_rule", "code_version", "report_sha256"):
            with self.subTest(name=name):
                with self.assertRaises(DecisionLogError) as ctx:
                    decision_ledger.save_trade_decision(**base(), **{name: "x"})
                self.assertIn("GENERATED_FIELD_NOT_ACCEPTED", str(ctx.exception))
        self.assertEqual(self.rows(), [])

    def test_unknown_field_refused(self):
        with self.assertRaises(DecisionLogError) as ctx:
            decision_ledger.save_trade_decision(**base(), confidence="high")
        self.assertIn("UNKNOWN_FIELDS", str(ctx.exception))

    def test_w_and_horizon_from_action_and_group(self):
        table = [("EXIT", 0), ("REDUCE", 0.5), ("HOLD", 1), ("ADD", 1.5)]
        for action, w1 in table:
            with self.subTest(action=action):
                over = {"hold_type": "no_edge"} if action == "HOLD" else {}
                self.save(action=action, **over)
                row = self.rows()[-1]
                self.assertEqual((row["w0"], row["w1"]), (1, w1))
        self.save(position_state="not_held", action="WAIT", hold_type="no_edge")
        self.assertEqual((self.rows()[-1]["w0"], self.rows()[-1]["w1"]), (0, 0))
        self.save(position_state="not_held", action="BUY")
        self.assertEqual((self.rows()[-1]["w0"], self.rows()[-1]["w1"]), (0, 0.5))
        horizons = {}
        for group in ("E0", "E1", "E2"):
            ev = {"event_date": "2026-03-05", "deviation_z": -2.1} if group == "E2" else {"event_date": "2026-03-05"}
            attr = None if group == "E0" else base()["attribution"]
            self.save(group=group, event=ev, attribution=attr)
            horizons[group] = self.rows()[-1]["horizon_days"]
        self.assertEqual(horizons, {"E0": 60, "E1": 20, "E2": 60})

    def test_action_must_match_position_state(self):
        self.rejected("ACTION_INVALID", position_state="held", action="BUY")
        self.rejected("ACTION_INVALID", position_state="held", action="WAIT")
        self.rejected("ACTION_INVALID", position_state="not_held", action="REDUCE")
        self.rejected("ACTION_INVALID", position_state="not_held", action="HOLD", hold_type="no_edge")

    def test_scan_must_be_held(self):
        self.rejected("SCAN_REQUIRES_HELD", source="scan", position_state="not_held", action="BUY")
        self.save(source="scan")
        self.assertEqual(self.rows()[0]["source"], "scan")

    def test_hold_type_rules(self):
        self.rejected("HOLD_TYPE_REQUIRED", action="HOLD")
        self.rejected("HOLD_TYPE_REQUIRED", action="HOLD", hold_type="maybe")
        self.rejected("HOLD_TYPE_REQUIRED", position_state="not_held", action="WAIT")
        self.rejected("HOLD_TYPE_NOT_ALLOWED", action="REDUCE", hold_type="no_edge")
        self.save(action="HOLD", hold_type="has_view")
        self.assertEqual(self.rows()[0]["hold_type"], "has_view")

    def test_review_triggers(self):
        self.rejected("REVIEW_TRIGGERS_TOO_FEW", review_triggers=["收盘跌破 420"])
        self.rejected("REVIEW_TRIGGERS_NO_NUMBER", review_triggers=["指引下修", "管理层变动"])
        self.rejected("REVIEW_TRIGGERS_MUST_BE_LIST_OF_TEXT", review_triggers=["跌破 420", ""])
        self.save(review_triggers=["指引下修", "收盘跌破 420"])

    def test_attribution_required_and_valid_for_e1_e2(self):
        for group in ("E1", "E2"):
            ev = {"event_date": "2026-03-05", "deviation_z": -2.1}
            self.rejected("ATTRIBUTION_REQUIRED", group=group, event=ev, attribution=None)
        self.rejected("PRIMARY_CAUSE_INVALID", attribution={"primary_cause": "vibes", "company_cause": True,
                                                            "explicit_guidance_cut": False})
        self.rejected("COMPANY_CAUSE_INVALID", attribution={"primary_cause": CAUSES[0], "company_cause": "yes",
                                                            "explicit_guidance_cut": False})
        self.rejected("EXPLICIT_GUIDANCE_CUT_INVALID", attribution={"primary_cause": CAUSES[0],
                                                                    "company_cause": False,
                                                                    "explicit_guidance_cut": "no"})
        for cause in CAUSES:
            self.save(attribution={"primary_cause": cause, "company_cause": "unconfirmed",
                                   "explicit_guidance_cut": False})
        self.assertEqual(len(self.rows()), len(CAUSES))

    def test_e0_attribution_optional_but_checked_if_given(self):
        self.save(group="E0", event={"event_date": "2026-03-05"}, attribution=None)
        self.assertIsNone(self.rows()[0]["attribution"])
        self.rejected_after_one("PRIMARY_CAUSE_INVALID", group="E0", event={"event_date": "2026-03-05"},
                                attribution={"primary_cause": "x", "company_cause": True,
                                             "explicit_guidance_cut": False})

    def rejected_after_one(self, code, **over):
        before = len(self.rows())
        with self.assertRaises(DecisionLogError) as ctx:
            self.save(**over)
        self.assertIn(code, str(ctx.exception))
        self.assertEqual(len(self.rows()), before)

    def test_e2_needs_deviation_z_and_sector(self):
        self.rejected("EVENT_DEVIATION_Z_REQUIRED", event={"event_date": "2026-03-05", "moment": "break_down"})
        self.rejected("E2_REQUIRES_SECTOR", benchmark="no_sector")

    def test_no_sector_allowed_outside_e2_without_etf_destination(self):
        self.rejected("SECTOR_ETF_WITHOUT_BENCHMARK", group="E0", event={"event_date": "2026-03-05"},
                      attribution=None, benchmark="no_sector", cash_destination="sector_etf")
        no_rel = {"baseline": None, "case": None, "basis": "无板块映射，相对栏缺失"}
        self.rejected("P_OUTPERFORM_NOT_APPLICABLE", group="E0", event={"event_date": "2026-03-05"}, attribution=None,
                      benchmark="no_sector")  # a 0.5 for "unknown" is refused
        self.save(group="E0", event={"event_date": "2026-03-05"}, attribution=None, benchmark="no_sector",
                  p_outperform=no_rel)
        self.assertEqual(self.rows()[0]["benchmark"], "no_sector")
        self.assertIsNone(self.rows()[0]["p_outperform"]["case"])

    def test_p_outperform(self):
        self.rejected("P_OUTPERFORM.CASE_INVALID", p_outperform={"baseline": 0.5, "case": 1.2, "basis": "x"})
        self.rejected("P_OUTPERFORM.BASELINE_INVALID", p_outperform={"baseline": True, "case": 0.5, "basis": "x"})
        self.rejected("P_OUTPERFORM.BASIS_REQUIRED", p_outperform={"baseline": 0.5, "case": 0.5, "basis": " "})
        self.rejected("P_OUTPERFORM_UNKNOWN_FIELDS", p_outperform={"baseline": 0.5, "case": 0.5, "basis": "x",
                                                                    "up": 1})
        self.save(p_outperform={"baseline": 0.5, "case": 0.5, "basis": "无优势"})  # 0.5 allowed
        self.assertEqual(self.rows()[0]["p_outperform"]["case"], 0.5)

    def test_event_validation(self):
        self.rejected("EVENT_DATE_INVALID", event={"event_date": "2026-13-01", "deviation_z": -2})
        self.rejected("EVENT_UNKNOWN_FIELDS", event={"event_date": "2026-03-05", "deviation_z": -2, "w1": 0})
        self.rejected("EVENT_DATE_IN_FUTURE", event={"event_date": "2999-01-01", "deviation_z": -2})

    def test_report_sections(self):
        self.assertEqual(decision_ledger.REQUIRED_SECTIONS,
                         ("结论", "概率与收益", "消息归因", "上次决策", "复核条件", "数据缺口", "来源"))
        for name in decision_ledger.REQUIRED_SECTIONS:
            with self.subTest(name=name):
                with self.assertRaises(DecisionLogError) as ctx:
                    self.save(report_markdown=REPORT.replace(f"## {name}", f"### {name}"))
                self.assertIn("REPORT_SECTIONS_MISSING", str(ctx.exception))
                self.assertIn(name, str(ctx.exception))
        self.assertEqual(self.rows(), [])
        self.rejected("REPORT_SECTIONS_MISSING", report_markdown="就这样吧")
        # E0 may say 不适用 under 消息归因, order is free
        e0 = REPORT.replace("earnings_guidance｜公司原因 是｜明确指引下修 否", "不适用")
        self.save(group="E0", event={"event_date": "2026-03-05"}, attribution=None, report_markdown=e0)
        parts = REPORT.split("\n## ")
        reordered = parts[0] + "".join("\n## " + x for x in reversed(parts[1:]))
        self.save(report_markdown=reordered)

    def test_thesis_one_line(self):
        self.rejected("THESIS_MUST_BE_ONE_LINE", thesis="第一句。\n第二句。")
        self.rejected("THESIS_REQUIRED", thesis="  ")

    def test_prior_decision_must_exist_in_same_file(self):
        self.rejected("PRIOR_DECISION_NOT_FOUND", prior_decision_id="deadbeef0000")
        first = self.save()["decision_id"]
        second = self.save(prior_decision_id=first)
        self.assertEqual(self.rows()[1]["prior_decision_id"], first)
        self.assertNotEqual(first, second["decision_id"])
        with self.assertRaises(DecisionLogError):
            self.save(prior_decision_id="deadbeef0000")
        self.assertEqual(len(self.rows()), 2)


class ReplayTests(LedgerCase):
    def test_replay_as_of_sets_effective_time_after_close(self):
        self.save(replay_as_of="2026-03-06", event={"event_date": "2026-03-05", "deviation_z": -2.4})
        row = self.rows()[0]
        self.assertTrue(row["replay"])
        self.assertEqual(row["decided_at_effective"], "2026-03-07T04:59:59Z")  # 23:59:59 EST
        self.assertEqual(row["info_cutoff"], row["decided_at_effective"])
        self.assertGreater(row["decided_at"], row["decided_at_effective"])  # real run time stays recorded

    def test_replay_uses_daylight_saving_offset(self):
        self.save(replay_as_of="2026-07-01", event={"event_date": "2026-06-30", "deviation_z": -2.4})
        self.assertEqual(self.rows()[0]["decided_at_effective"], "2026-07-02T03:59:59Z")  # 23:59:59 EDT

    def test_event_after_replay_date_refused(self):
        self.rejected("EVENT_DATE_IN_FUTURE", replay_as_of="2026-03-06",
                      event={"event_date": "2026-03-09", "deviation_z": -2.4})

    def test_replay_env_is_picked_up_and_must_agree(self):
        with mock.patch.dict(os.environ, {"STOCK_AGENT_REPLAY_AS_OF": "2026-03-06"}):
            self.save()
            self.assertTrue(self.rows()[0]["replay"])
            self.assertEqual(self.rows()[0]["decided_at_effective"], "2026-03-07T04:59:59Z")
            self.rejected_after_one("REPLAY_AS_OF_MISMATCH", replay_as_of="2026-03-09")

    def test_replay_as_of_validated(self):
        self.rejected("REPLAY_AS_OF_INVALID", replay_as_of="2999-01-01")
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        self.rejected("REPLAY_AS_OF_INVALID", replay_as_of=today)  # the day is not over yet
        self.rejected("REPLAY_AS_OF_INVALID", replay_as_of="yesterday")

    def rejected_after_one(self, code, **over):
        before = len(self.rows())
        with self.assertRaises(DecisionLogError) as ctx:
            self.save(**over)
        self.assertIn(code, str(ctx.exception))
        self.assertEqual(len(self.rows()), before)


class RecordScriptTests(LedgerCase):
    def run_script(self, decision_id, ledger, data_dir=None):
        env = {k: v for k, v in os.environ.items() if k != "STOCK_AGENT_REPLAY_AS_OF"}
        env["STOCK_AGENT_DATA_DIR"] = data_dir or str(self.root)
        return subprocess.run([sys.executable, "-I", str(SCRIPT), decision_id, "--ledger", str(ledger)],
                              capture_output=True, text=True, env=env)

    def test_appends_once_and_refuses_duplicate(self):
        ledger = self.root / "ledger" / "decision-ledger.jsonl"
        first, second = self.save()["decision_id"], self.save(action="EXIT")["decision_id"]
        done = self.run_script(first, ledger)
        self.assertEqual(done.returncode, 0, done.stderr)
        before = ledger.read_text()
        dup = self.run_script(first, ledger)
        self.assertNotEqual(dup.returncode, 0)
        self.assertIn("already in", dup.stderr)
        self.assertEqual(ledger.read_text(), before)  # nothing rewritten
        self.assertEqual(self.run_script(second, ledger).returncode, 0)
        text = ledger.read_text()
        self.assertTrue(text.startswith(before))  # append-only
        rows = [json.loads(x) for x in text.splitlines()]
        self.assertEqual([r["decision_id"] for r in rows], [first, second])
        self.assertEqual(rows[0]["kind"], "decision")
        self.assertEqual(rows[0]["report_sha256"], self.rows()[0]["report_sha256"])

    def test_refuses_unknown_id_and_tampered_report(self):
        ledger = self.root / "decision-ledger.jsonl"
        self.assertNotEqual(self.run_script("nope00000000", ledger).returncode, 0)
        out = self.save()
        Path(out["report_path"]).write_text("changed\n", encoding="utf-8")
        bad = self.run_script(out["decision_id"], ledger)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("sha256", bad.stderr)
        self.assertFalse(ledger.exists())

    def test_default_ledger_is_never_used_by_tests(self):
        # sanity: the repo ledger path is only the script default; the tests above always pass --ledger
        self.assertFalse(str(settings.data_dir()).startswith(str(REPO / ".local" / "data")))


if __name__ == "__main__":
    unittest.main()
