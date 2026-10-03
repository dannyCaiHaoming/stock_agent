from copy import deepcopy
import unittest

from product.trading_journal.analysis import analyze_records
from product.trading_journal.charts import chart_payload
from product.trading_journal.reflection import ReflectionError, assemble_report, validate_report, lesson_events, render_markdown, prepare_reflection
from tests.test_trading_journal_reflection import packet, report, evidence, snapshot, rehash_snapshot


def lesson():
    return {
        "finding_ref": "finding-1", "focus_record_ref": "buy-win",
        "chart_window": {"start": "2026-01-05", "end": "2026-01-08", "record_refs": ["buy-win", "sell-win"], "focus_instrument_key": "US:AAPL:USD"},
        "beginner": {"read_chart": "合成图窗入场与退出", "why_it_matters": "完整日K属于事后观察", "terms": [{"term": "结果", "meaning": "后续路径", "case_application": "不是入场时已有信息"}], "record_refs": ["buy-win"], "evidence_refs": []},
        "practice": {"possible_error": "候选记录缺口", "exercise": "保存原始计划", "next_inputs": ["时间戳"], "verification": "复查信息时钟", "record_refs": ["buy-win"], "evidence_refs": []},
        "advanced": {"alternative_explanation": "有计划但没有保存", "falsifier": "取得当时计划", "additional_evidence": "原始日志", "record_refs": ["sell-win"], "evidence_refs": []},
        "event_links": [], "limits": ["合成案例，不证明研究质量"],
    }


def with_lessons(p=None, lessons=None):
    p = p or packet()
    old = report(p)
    kwargs = {key: old[key] for key in ("findings", "improvement_plan", "model_version", "skill_version", "phase_coverage", "report_as_of")}
    return assemble_report(p, **kwargs, analyzed_episode_ids=old["progress"]["analyzed_episode_ids"], case_lessons=[lesson()] if lessons is None else lessons)


def date_focus_packet(source_timezone, **preparation):
    value = snapshot()
    focus = value["records"][0]
    focus.update(occurred_at="2026-01-05", as_of="2026-01-05", time_precision="DATE")
    if source_timezone is not None:
        focus["source_timezone"] = source_timezone
    else:
        focus.pop("source_timezone", None)
    value["analysis"] = analyze_records(value["records"], opening_positions=value["opening_positions"])
    rehash_snapshot(value)
    return prepare_reflection(value, chart_refs=["chart:frozen-snapshot-test"], **preparation)


class TradingLessonTests(unittest.TestCase):
    def test_new_version_and_old_read_compatibility(self):
        p = packet()
        old = report(p)
        self.assertEqual(old["schema_version"], "1.0.0")
        new = with_lessons(p)
        self.assertEqual(new["schema_version"], "1.1.0")
        self.assertNotIn("case_lessons", old)
        validate_report(old, p)
        self.assertIn("#### 图表讲解", render_markdown(new, p))

    def test_incomplete_duplicate_and_unknown_transport_rejected(self):
        with self.assertRaisesRegex(ReflectionError, "完整覆盖"):
            with_lessons(lessons=[])
        with self.assertRaisesRegex(ReflectionError, "重复"):
            with_lessons(lessons=[lesson(), lesson()])
        body = lesson()
        body["account_ref"] = "forbidden"
        with self.assertRaisesRegex(ReflectionError, "未知字段"):
            with_lessons(lessons=[body])

    def test_wrong_focus_identity_window_or_unrelated_record_rejected(self):
        for field, value in [("focus_record_ref", "buy-loss"), ("focus_instrument_key", "wrong"), ("start", "2026-01-06"), ("end", "2027-01-01")]:
            body = lesson()
            if field == "focus_record_ref":
                body[field] = value
            else:
                body["chart_window"][field] = value
            with self.subTest(field=field), self.assertRaises(ReflectionError):
                with_lessons(lessons=[body])
        body = lesson()
        body["practice"]["record_refs"] = ["option-open"]
        with self.assertRaisesRegex(ReflectionError, "引用无效"):
            with_lessons(lessons=[body])

    def test_source_clock_and_per_fill_layers_not_one_episode_label(self):
        p = packet(evidence=[evidence("event", "2026-01-05T22:00:00Z", record_refs=["buy-win", "sell-win"], content="合成公告")])
        base = report(p)
        base["findings"][0]["outcome_evidence_refs"] = ["event"]
        body = lesson()
        body["event_links"] = [{"evidence_ref": "event", "record_refs": ["buy-win", "sell-win"], "anchor_role": "AVAILABLE_AT", "relevance_note": "先后并不等于因果"}]
        new = assemble_report(p, findings=base["findings"], improvement_plan=base["improvement_plan"], phase_coverage=base["phase_coverage"], model_version="synthetic", skill_version="1.1.0", case_lessons=[body])
        event = lesson_events(new, p, body)[0]
        self.assertEqual(event["anchor_at"], "2026-01-05T22:00:00Z")
        self.assertEqual([row["layer"] for row in event["layers"]], ["outcome", "contemporaneous"])
        split = deepcopy(body)
        split["event_links"] = [{**link, "record_refs": [rid]} for link in body["event_links"] for rid in link["record_refs"]]
        kwargs = {key: base[key] for key in ("findings", "improvement_plan", "phase_coverage", "model_version", "skill_version")}
        assemble_report(p, **kwargs, case_lessons=[split])
        split["event_links"].append(deepcopy(split["event_links"][0]))
        with self.assertRaisesRegex(ReflectionError, "重复"):
            assemble_report(p, **kwargs, case_lessons=[split])
        for key in ("source_id", "as_of", "retrieved_at"):
            self.assertEqual(event[key], p["evidence"][0][key])

    def test_unknown_clock_remains_unplaced_and_llm_timestamp_rejected(self):
        p = packet(evidence=[evidence("unknown", None, publication_date="2026-01-05")])
        base = report(p)
        base["findings"][0]["uncertain_evidence_refs"] = ["unknown"]
        body = lesson()
        body["event_links"] = [{"evidence_ref": "unknown", "record_refs": ["buy-win"], "anchor_role": "UNPLACED", "relevance_note": "首发时刻未知"}]
        kwargs = {key: base[key] for key in ("findings", "improvement_plan", "phase_coverage", "model_version", "skill_version")}
        new = assemble_report(p, **kwargs, case_lessons=[body])
        self.assertIsNone(lesson_events(new, p, body)[0]["date"])
        changed = deepcopy(body)
        changed["event_links"][0]["anchor_role"] = "AVAILABLE_AT"
        with self.assertRaisesRegex(ReflectionError, "UNPLACED"):
            assemble_report(p, **kwargs, case_lessons=[changed])
        changed = deepcopy(body)
        changed["event_links"][0]["anchor_at"] = "2026-01-05T00:00:00Z"
        with self.assertRaisesRegex(ReflectionError, "来源派生"):
            assemble_report(p, **kwargs, case_lessons=[changed])
        for invalid_role in ({"role": "UNPLACED"}, ["UNPLACED"]):
            with self.subTest(anchor_role=invalid_role):
                changed = deepcopy(body)
                changed["event_links"][0]["anchor_role"] = invalid_role
                with self.assertRaisesRegex(ReflectionError, "锚点角色"):
                    assemble_report(p, **kwargs, case_lessons=[changed])

    def test_date_focus_preserves_source_calendar_and_uncertain_per_fill_information(self):
        for source_zone in ("America/New_York", "Asia/Shanghai", None):
            with self.subTest(source_timezone=source_zone):
                material = evidence("prior", "2026-01-04T18:00:00Z", record_refs=["buy-win", "sell-win"])
                p = date_focus_packet(source_zone, evidence=[material])
                frozen = deepcopy(p)
                base = report(p)
                base["findings"][0]["uncertain_evidence_refs"] = ["prior"]
                body = lesson()
                body["chart_window"].update(end="2026-01-05", record_refs=["buy-win"])
                body["beginner"]["evidence_refs"] = ["prior"]
                body["event_links"] = [{"evidence_ref": "prior", "record_refs": ["buy-win", "sell-win"],
                                        "anchor_role": "AVAILABLE_AT", "relevance_note": "来源有精确发布时刻，但焦点成交只有日期"}]
                kwargs = {key: base[key] for key in ("findings", "improvement_plan", "phase_coverage", "model_version", "skill_version", "report_as_of")}
                new = assemble_report(p, **kwargs, case_lessons=[body])
                validate_report(new, p)
                self.assertEqual(p, frozen)
                self.assertEqual(new["case_lessons"][0]["chart_window"]["start"], "2026-01-05")
                self.assertEqual(new["case_lessons"][0]["chart_window"]["end"], "2026-01-05")
                self.assertEqual([row["layer"] for row in lesson_events(new, p, body)[0]["layers"]], ["uncertain", "contemporaneous"])
                row = next(row for row in chart_payload(p["snapshot"])["records"] if row["record_id"] == "buy-win")
                self.assertEqual(row["display_date"], "2026-01-05")
                self.assertEqual(row["time_precision"], "DATE")
                self.assertIsNone(row["local_time"])
                self.assertEqual(row["date_basis"], "EXCHANGE_DATE" if source_zone == "America/New_York" else "SOURCE_DATE")
                self.assertEqual(row["exchange_date_status"], "DATE_ONLY" if source_zone == "America/New_York" else "UNDETERMINED")
                upgraded = deepcopy(new)
                upgraded["findings"][0]["decision_evidence_refs"] = ["prior"]
                with self.assertRaisesRegex(ReflectionError, "当时背景"):
                    validate_report(upgraded, p)

    def test_date_focus_window_cutoff_uses_source_calendar_without_inventing_an_instant(self):
        cases = [("Asia/Shanghai", "2026-09-30T23:00:00Z", "2026-10-01", "2026-10-02"),
                 (None, "2026-09-30T00:30:00Z", "2026-09-29", "2026-09-30"),
                 ("America/New_York", "2026-09-30T00:30:00Z", "2026-09-29", "2026-09-30")]
        for source_zone, cutoff, valid_end, future_end in cases:
            with self.subTest(source_timezone=source_zone, cutoff=cutoff):
                p = date_focus_packet(source_zone, cutoff=cutoff)
                body = lesson()
                body["chart_window"]["end"] = valid_end
                new = with_lessons(p, lessons=[body])
                self.assertEqual(new["case_lessons"][0]["chart_window"]["end"], valid_end)
                body["chart_window"]["end"] = future_end
                with self.assertRaisesRegex(ReflectionError, "图表窗口"):
                    with_lessons(p, lessons=[body])

    def test_unknown_source_date_at_cutoff_matches_frozen_input_calendar(self):
        cutoff = "2026-09-30T00:30:00Z"
        value = snapshot()
        focus = value["records"][0]
        value["records"] = [focus]
        focus.update(occurred_at="2026-09-30", as_of="2026-09-30", time_precision="DATE")
        focus.pop("source_timezone", None)
        value["analysis"] = analyze_records(value["records"], opening_positions=value["opening_positions"])
        rehash_snapshot(value)
        material = evidence("prior", "2026-01-04T18:00:00Z", retrieved_at=cutoff)
        preparation = {"cutoff": cutoff, "evidence": [material], "chart_refs": ["chart:frozen-snapshot-test"]}
        with self.assertRaisesRegex(ReflectionError, "日期记录"):
            prepare_reflection(value, **preparation)

        focus.update(occurred_at="2026-09-29", as_of="2026-09-29")
        value["analysis"] = analyze_records(value["records"], opening_positions=value["opening_positions"])
        rehash_snapshot(value)
        p = prepare_reflection(value, **preparation)
        frozen = deepcopy(p)
        base = report()
        finding = base["findings"][0]
        finding.update(record_refs=["buy-win"], episode_refs=["activity:buy-win"], calculation_refs=[], financial_claims=[],
                       process_observation="仅日期成交，来源时区未知", result_observation="非闭合片段，不计算净结果",
                       uncertain_evidence_refs=["prior"], alternative_explanations=[{"text": "原始账单可能提供更精确时区与成交时刻，当前无法恢复",
                           "record_refs": ["buy-win"], "episode_refs": ["activity:buy-win"], "evidence_refs": ["prior"]}])
        body = lesson()
        body["chart_window"].update(start="2026-09-29", end="2026-09-29", record_refs=["buy-win"])
        for name in ("beginner", "practice", "advanced"):
            body[name].update(record_refs=["buy-win"], evidence_refs=["prior"])
        kwargs = {key: base[key] for key in ("findings", "improvement_plan", "phase_coverage", "model_version", "skill_version", "report_as_of")}
        new = assemble_report(p, **kwargs, case_lessons=[body])
        validate_report(new, p)
        self.assertEqual(p, frozen)
        row = chart_payload(p["snapshot"])["records"][0]
        self.assertEqual((row["display_date"], row["time_precision"], row["date_basis"]), ("2026-09-29", "DATE", "SOURCE_DATE"))
        self.assertIsNone(row["local_time"])
        self.assertFalse(p["record_layers"]["buy-win"]["contemporaneous"])
        self.assertEqual(p["record_layers"]["buy-win"]["uncertain"][0]["evidence_id"], "prior")
        body["chart_window"]["end"] = "2026-09-30"
        with self.assertRaisesRegex(ReflectionError, "图表窗口"):
            assemble_report(p, **kwargs, case_lessons=[body])
