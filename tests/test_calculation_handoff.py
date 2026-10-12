"""实际stdio工具/预计算 → 明确选择 → 纯业务报告与历史读取；零LLM。"""
from __future__ import annotations

import copy
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.calculation_handoff import (
    assemble_calculation_selections, build_calculation_catalog, calculation_reference,
    load_tool_receipts, receipt_calculation, selection_draft_schema,
    semantic_selection_draft_schema, validate_semantic_selection_draft,
)
from product.runtime.calculation_handoff import validate_tool_calculations as _validate_multidimensional_tool_calculations
from product.runtime.fixture_mcp import StatelessFixtureTools, serve_stdio
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.runtime.multidimensional_stage import (
    build_multidimensional_dispatch_packet, serialize_multidimensional_initial_context,
    serialize_multidimensional_model_context,
)
from product.runtime.schema_validation import validate_schema_instance
from tests import test_multidimensional_stage as fixtures
from tests import test_research_submission as submissions


class CalculationHandoffTests(unittest.TestCase):
    helper = fixtures.MultidimensionalStageTests()

    def prepared(self, root, capability="FUNDAMENTAL_EVENT", *, daily=False):
        run = (self.helper.prepare_mrvl_daily_run(root, include_spy=True) if daily else
               self.helper.prepare(root, count=1)[0])
        index = json.loads((run / "research/dispatch-index.json").read_text())
        task = next(t for t in index["tasks"] if t["capability"] == capability)
        packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
        return run, task, packet

    def call(self, run, task, name, **arguments):
        arguments.update({key: task[key] for key in ("run_id", "agent", "invocation_id")})
        request = {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
            serve_stdio(stateless=True, default_run_dir=run)
        return json.loads(output.getvalue())

    def successful_ratio(self, run, task, packet, *, reverse=False):
        refs = list(packet["reference_map"]["evidence"])[:2]
        if reverse:
            refs.reverse()
        query = self.call(run, task, "query", evidence_ids=refs)
        self.assertNotIn("error", query)
        result = self.call(run, task, "calculate", operation="ratio", evidence_ids=refs)
        self.assertNotIn("error", result)
        return result["result"]["structuredContent"]

    def draft(self, task, ref, evidence_refs=()):
        draft = self.helper.dimension_draft(task)
        for key in ("run_id", "agent", "invocation_id", "calculations", "artifact_refs", "documents"):
            draft.pop(key, None)
        draft["document_selections"] = []
        draft.update(status="LOW_CONFIDENCE", sufficiency="PARTIAL",
                     summary="仅用于验证同期间结果传递，不作投资结论。")
        draft["claims"] = [{"claim_id": "comparison", "question": "数值关系及局限是什么？",
                            "statement": "这个比值保留来源期间和工具输入顺序，不能单独证明估值便宜。",
                            "kind": "INTERPRETATION", "evidence_refs": list(evidence_refs),
                            "research_claim_refs": [], "document_refs": [], "assumption_ids": []}]
        draft["calculation_selections"] = [{"calculation_ref": ref, "claim_ids": ["comparison"]}]
        return draft

    def test_actual_stdio_to_business_report_preserves_prose_and_exact_result(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            result = self.successful_ratio(run, task, packet)
            draft = self.draft(task, result["calculation_ref"], result["evidence_ids"])
            original = copy.deepcopy(draft)
            report, output = self.helper.save_dimension_fixture(run, task, draft)
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
            receipt = json.loads((run / task["calculation_ledger_ref"]).read_text())
            self.assertEqual(report["calculations"], [receipt_calculation(receipt, task["calculation_ledger_ref"])])
            self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
            self.assertEqual(report["claims"][0]["calculation_refs"], [result["calculation_id"]])
            self.assertEqual(report["artifact_refs"], [task["calculation_ledger_ref"]])
            self.assertNotIn("calculation_selections", report)
            self.assertEqual(draft, original)
            self.assertIn(result["value"], Path(output["markdown"]).read_text())
            moved = Path(directory) / "moved-calculation-package"
            shutil.copytree(run, moved)
            preserved = Path(directory) / "original-outside-declared-path"
            run.rename(preserved)
            try:
                invocation = json.loads((moved / task["invocation_path"]).read_text())
                _validate_multidimensional_tool_calculations(report, task=task,
                                                            invocation=invocation, run_dir=moved)
                ledger = moved / task["calculation_ledger_ref"]
                ledger.unlink()
                with self.assertRaises(ValueError):
                    _validate_multidimensional_tool_calculations(report, task=task,
                                                                invocation=invocation, run_dir=moved)
            finally:
                preserved.rename(run)

    def test_reference_is_stable_after_more_calls_but_order_changes_result(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            first = self.successful_ratio(run, task, packet)
            first_record = build_calculation_catalog(run, packet)[first["calculation_ref"]]
            second = self.successful_ratio(run, task, packet, reverse=True)
            catalog = build_calculation_catalog(run, packet)
            self.assertEqual(catalog[first["calculation_ref"]], first_record)
            self.assertNotEqual(first["calculation_ref"], second["calculation_ref"])
            self.assertNotEqual(first["value"], second["value"])
            self.assertEqual(catalog[second["calculation_ref"]]["calculation"]["input_evidence_refs"],
                             list(reversed(first_record["calculation"]["input_evidence_refs"])))

    def test_no_successful_receipt_or_missing_event_cannot_be_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            invalid = self.call(run, task, "calculate", operation="ratio", evidence_ids=[])
            self.assertIn("error", invalid)
            self.assertEqual(build_calculation_catalog(run, packet), {})
            ref = calculation_reference(packet["reference_map"], "f" * 64)
            with self.assertRaisesRegex(ValueError, "SELECTION_UNKNOWN"):
                assemble_calculation_selections(run, packet, self.draft(task, ref))
            result = self.successful_ratio(run, task, packet)
            (run / "events/mcp/events.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "CALCULATION_EVENT_INVALID"):
                assemble_calculation_selections(run, packet, self.draft(task, result["calculation_ref"]))

    def test_selection_shape_unknown_type_task_and_claim_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            result = self.successful_ratio(run, task, packet)
            draft = self.draft(task, result["calculation_ref"])
            for ref in (next(iter(packet["reference_map"]["evidence"])), "k." + "0"*12 + "." + "f"*24):
                bad = copy.deepcopy(draft)
                bad["calculation_selections"][0]["calculation_ref"] = ref
                with self.subTest(ref=ref), self.assertRaises(ValueError):
                    assemble_calculation_selections(run, packet, bad)
            for mutation in ("mixed_result", "mixed_claim", "unknown_claim", "duplicate", "injected_value"):
                bad = copy.deepcopy(draft)
                if mutation == "mixed_result":
                    bad["calculations"] = []
                elif mutation == "mixed_claim":
                    bad["claims"][0]["calculation_refs"] = []
                elif mutation == "unknown_claim":
                    bad["calculation_selections"][0]["claim_ids"] = ["not-there"]
                elif mutation == "duplicate":
                    bad["calculation_selections"] *= 2
                else:
                    bad["calculation_selections"][0]["value"] = "999"
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    assemble_calculation_selections(run, packet, bad)
            other = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                         if t["capability"] == "OWNERSHIP_DISCLOSURE")
            other_packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, other["task_name"])
            with self.assertRaisesRegex(ValueError, "SELECTION_UNKNOWN"):
                assemble_calculation_selections(run, other_packet, draft)

    def test_rehashed_ledger_cannot_override_actual_event_or_report_result(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            result = self.successful_ratio(run, task, packet)
            invocation = json.loads((run / task["invocation_path"]).read_text())
            assembled = assemble_calculation_selections(run, packet, self.draft(task, result["calculation_ref"]))
            for field, value in (("value", "999"), ("unit", "%"), ("method", "fake")):
                wrong = copy.deepcopy(assembled)
                wrong["calculations"][0][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "RESULT_MISMATCH"):
                    _validate_multidimensional_tool_calculations(wrong, task=task, invocation=invocation, run_dir=run)
            wrong = copy.deepcopy(assembled)
            wrong["calculations"][0]["input_evidence_refs"].reverse()
            with self.assertRaisesRegex(ValueError, "INPUT_MISMATCH"):
                _validate_multidimensional_tool_calculations(wrong, task=task, invocation=invocation, run_dir=run)
            ledger = run / task["calculation_ledger_ref"]
            receipt = json.loads(ledger.read_text())
            receipt["output"]["value"] = "999"
            receipt["receipt_hash"] = legacy_envelope_hash(receipt, hash_field="receipt_hash")
            ledger.write_text(json.dumps(receipt) + "\n")
            with self.assertRaisesRegex(ValueError, "EVENT_INVALID"):
                load_tool_receipts(run, task, invocation)

    def test_derived_schema_and_both_actual_delivery_paths_omit_mechanical_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            guide = selection_draft_schema(packet["output_schema"], document_refs=[])
            result = self.successful_ratio(run, task, packet)
            draft = self.draft(task, result["calculation_ref"], list(packet["reference_map"]["evidence"].values())[:2])
            validate_schema_instance(draft, guide)
            for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                context = json.loads(serialize(packet))
                guide = context["output_format_guide"]
                for key in ("run_id", "agent", "invocation_id", "calculations", "artifact_refs"):
                    self.assertNotIn(key, guide["required"])
                    self.assertNotIn(key, guide["properties"])
                self.assertNotIn("calculation_refs", guide["$defs"]["claim"]["properties"])
                self.assertIn("calculation_selections", guide["required"])
                self.assertEqual(context["calculation_selection_contract"]["prepared_results"], [])

    def test_whole_draft_structure_precedes_damaged_receipt_at_business_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            result = self.successful_ratio(run, task, packet)
            draft = self.draft(task, result["calculation_ref"])
            draft["claims"][0].pop("question")
            original = copy.deepcopy(draft)
            (run / task["calculation_ledger_ref"]).write_text("not-json\n")
            with self.assertRaisesRegex(ValueError, r"SCHEMA_REQUIRED_MISSING:\$\.claims\[0\]:question"):
                self.helper.read_dimension_draft(run, task, draft)
            self.assertEqual(draft, original)
            self.assertFalse(list((run / "research/reports").glob("*/dimension-report.json")))

    def test_entire_native_structure_is_checked_without_reading_calculation_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            ref = calculation_reference(packet["reference_map"], "f" * 64)
            draft = self.draft(task, ref)
            cases = [("summary", {**draft, "summary": 1}, "SCHEMA_TYPE_INVALID:$.summary"),
                     ("missing", {key: value for key, value in draft.items() if key != "assumptions"},
                      "SCHEMA_REQUIRED_MISSING:$:assumptions")]
            wrong = copy.deepcopy(draft)
            wrong["claims"][0]["evidence_refs"] = True
            cases.append(("nested", wrong, "SCHEMA_TYPE_INVALID:$.claims[0].evidence_refs"))
            for label, bad, error in cases:
                with self.subTest(label=label), patch("product.runtime.calculation_handoff.build_calculation_catalog") as catalog:
                    with self.assertRaises(ValueError) as caught:
                        validate_semantic_selection_draft(bad, packet)
                    self.assertEqual(str(caught.exception), error)
                    catalog.assert_not_called()
            validate_semantic_selection_draft(draft, packet)
            with self.assertRaisesRegex(ValueError, "SELECTION_UNKNOWN"):
                assemble_calculation_selections(run, packet, draft)

    def test_current_selection_fields_are_mandatory_without_legacy_fallback(self):
        for field in ("calculation_selections", "document_selections"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                run, task, packet = self.prepared(Path(directory))
                draft = self.helper.dimension_draft(task)
                draft.pop(field)
                with patch("product.runtime.calculation_handoff.build_calculation_catalog") as catalog:
                    with self.assertRaisesRegex(ValueError, "SCHEMA_REQUIRED_MISSING.*" + field):
                        validate_semantic_selection_draft(draft, packet)
                    catalog.assert_not_called()
                legacy = self.helper.formal_dimension_draft(task)
                original = copy.deepcopy(legacy)
                with self.assertRaises(ValueError):
                    validate_semantic_selection_draft(legacy, packet)
                # 只有显式历史读取装配保留旧稿，不回写或猜成当前协议。
                self.assertEqual(assemble_calculation_selections(run, packet, legacy), original)
                self.assertEqual(legacy, original)


    def test_submission_relation_structure_and_actual_guides_share_canonical_schema(self):
        from product.runtime.research_submission import _assemble_draft, BOUNDED_REVISION_VERSION
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = submissions.ResearchSubmissionTests().prepare(Path(directory), version=BOUNDED_REVISION_VERSION)
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            draft = self.draft(task, calculation_reference(packet["reference_map"], "f" * 64))
            draft["calculation_selections"] = []
            claim = draft["claims"][0]
            claim["core_statement"] = claim.pop("statement")
            claim["research_relation_clauses"] = []
            schema = semantic_selection_draft_schema(packet)
            validate_schema_instance(draft, schema)
            for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                guide = json.loads(serialize(packet))["submission_contract"]["draft_format_guide"]
                self.assertEqual(guide, schema)
            for key, value, error in [
                ("core_statement", 1, "SCHEMA_TYPE_INVALID:$.claims[0].core_statement"),
                ("research_relation_clauses", [{"research_claim_ref": "local"}],
                 "SCHEMA_REQUIRED_MISSING:$.claims[0].research_relation_clauses[0]:relation_statement"),
            ]:
                bad = copy.deepcopy(draft)
                bad["claims"][0][key] = value
                with self.subTest(field=key), patch("product.runtime.calculation_handoff.build_calculation_catalog") as catalog:
                    with self.assertRaises(ValueError) as caught:
                        _assemble_draft(bad, packet, root=run)
                    self.assertEqual(str(caught.exception), error)
                    from product.runtime.research_submission import _preflight_bounded
                    result, assembled, selections = _preflight_bounded(run, packet, bad)
                    self.assertEqual(result["failure_code"], error)
                    self.assertIsNone(assembled)
                    self.assertEqual(selections, [])
                    catalog.assert_not_called()
            self.assertFalse((run / "research/submissions").exists())

    def test_native_structural_pass_does_not_authorize_unknown_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            result = self.successful_ratio(run, task, packet)
            draft = self.draft(task, result["calculation_ref"], ["e." + "0" * 12 + ".1"])
            validate_semantic_selection_draft(draft, packet)
            original = copy.deepcopy(draft)
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                self.helper.read_dimension_draft(run, task, draft)
            self.assertEqual(draft, original)
            self.assertFalse((run / "research/reports").exists())

    def test_precomputed_windows_only_offer_complete_values_with_exact_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory), "TECHNICAL_STRUCTURE", daily=True)
            catalog = build_calculation_catalog(run, packet)
            chosen = next((ref, entry) for ref, entry in catalog.items()
                          if entry["calculation"]["method"] == "security_total_return:20_sessions")
            draft = self.draft(task, chosen[0])
            assembled = assemble_calculation_selections(run, packet, draft)
            raw = json.loads((run / packet["prepared_analysis"]["calculation_ref"]).read_text())
            self.assertEqual(assembled["calculations"][0]["value"], raw["windows"][0]["metrics"]["security_total_return"])
            self.assertEqual(assembled["calculations"][0]["input_evidence_refs"], raw["evidence_fact_ids"])
            self.assertTrue(all(entry["window_sessions"] == 20 for entry in catalog.values()))
            self.assertEqual(chosen[1]["as_of"], raw["as_of"])
            self.assertEqual(chosen[1]["price_basis"], raw["price_basis"])
            context = json.loads(serialize_multidimensional_model_context(packet))
            self.assertNotIn("allowed_calculation_evidence_ids", context["task"])
            for entry in context["calculation_selection_contract"]["prepared_results"]:
                self.assertNotIn("input_evidence_refs", entry)
                self.assertEqual(entry["input_fact_count"], len(raw["evidence_fact_ids"]))
            from product.council.multidimensional_research import validate_research_dimension_report
            report, _, _ = self.helper.read_dimension_draft(run, task, draft)
            self.assertEqual(task["allowed_evidence_ids"], [])
            self.assertTrue(task["allowed_calculation_evidence_ids"])
            report["claims"][0]["evidence_refs"] = [raw["evidence_fact_ids"][0]]
            report["report_hash"] = legacy_envelope_hash(report, hash_field="report_hash")
            with self.assertRaisesRegex(ValueError, "EVIDENCE_CLOSURE_FAILED"):
                validate_research_dimension_report(report, expected_bindings=self.helper.research_bindings(run),
                    allowed_security_ids=task["security_ids"], allowed_evidence_ids=[],
                    allowed_calculation_evidence_ids=task["allowed_calculation_evidence_ids"])
            modified = copy.deepcopy(raw)
            modified["windows"][0]["metrics"]["security_total_return"] = "999"
            modified["artifact_hash"] = legacy_envelope_hash(modified, hash_field="artifact_hash")
            (run / packet["prepared_analysis"]["calculation_ref"]).write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError, "PRECOMPUTED_BINDING_INVALID"):
                build_calculation_catalog(run, packet)

    def test_symlink_ledger_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run, task, packet = self.prepared(root)
            result = self.successful_ratio(run, task, packet)
            ledger = run / task["calculation_ledger_ref"]
            outside = root / "outside.jsonl"
            outside.write_bytes(ledger.read_bytes())
            ledger.unlink()
            ledger.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "CALCULATION_PATH_INVALID"):
                assemble_calculation_selections(run, packet, self.draft(task, result["calculation_ref"]))

    def test_source_calculation_to_historical_selection_survives_reopen(self):
        from product.runtime.research_submission import selected_calculations_for_report, FORMAL_VERSION
        with tempfile.TemporaryDirectory() as directory:
            # 实际stdio计算生成收据，纯业务装配生成依赖；目标为显式v4历史读取向量。
            # 不生成当前Hook、作者或宿主执行证明。
            def reserve_invocation_directory(run, index):
                (run / "invocation").mkdir(exist_ok=True)
            with patch.object(fixtures.MultidimensionalStageTests, "save_fundamental_dependency", side_effect=reserve_invocation_directory):
                f, run, task = submissions.ResearchSubmissionTests().prepare(Path(directory), version=FORMAL_VERSION)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            source_task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            source_packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, source_task["task_name"])
            result = self.successful_ratio(run, source_task, source_packet)
            draft = self.draft(source_task, result["calculation_ref"], result["evidence_ids"])
            _, source_output = f.save_dimension_fixture(run, source_task, draft)
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            catalog = build_calculation_catalog(run, packet)
            ref, entry = next((ref, entry) for ref, entry in catalog.items() if entry["kind"] == "DEPENDENCY")
            downstream = self.draft(task, ref)
            claim = downstream["claims"][0]
            claim["core_statement"] = claim.pop("statement")
            claim["research_claim_refs"] = [entry["source_claim_ref"]]
            claim["research_relation_clauses"] = [{"research_claim_ref": entry["source_claim_ref"],
                                                   "relation_statement": "上游计算只提供同期间比值背景，不证明投资方向。"}]
            original = copy.deepcopy(downstream)
            unbound = copy.deepcopy(downstream)
            unbound["claims"][0]["research_claim_refs"] = []
            with self.assertRaisesRegex(ValueError, "DEPENDENCY_CLAIM_MISMATCH"):
                assemble_calculation_selections(run, packet, unbound)
            for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                context = json.loads(serialize(packet))
                self.assertNotIn("upstream_calculation_selections", context["submission_contract"]["draft_format_guide"]["properties"])
                self.assertEqual(context["calculation_selection_contract"]["prepared_results"][0]["calculation_ref"], ref)
            denied = self.call(run, task, "calculate", operation="ratio", evidence_ids=task["allowed_evidence_ids"][:2])
            self.assertIn("error", denied)
            from tests.historical_submission_fixture import store_historical_report_fixture
            output = submissions.ResearchSubmissionTests().submit(
                StatelessFixtureTools(default_run_dir=run), task, downstream)
            report, _, _ = store_historical_report_fixture(run, task, output["final_message"])
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
            selected = selected_calculations_for_report(run, report)
            self.assertEqual(selected[0]["calculation_id"], result["calculation_id"])
            self.assertEqual(selected[0]["verified_output"]["value"], result["value"])
            self.assertEqual(report["calculations"], [])
            self.assertEqual(report["claims"][0]["statement"],
                             claim["core_statement"] + " " + claim["research_relation_clauses"][0]["relation_statement"])
            self.assertEqual(downstream, original)
            moved = Path(directory) / "native-history"
            shutil.copytree(run, moved)
            preserved = Path(directory) / "native-original-unavailable"
            run.rename(preserved)
            try:
                self.assertEqual(selected_calculations_for_report(moved, report, for_execution=False), selected)
                with self.assertRaises(ValueError):
                    selected_calculations_for_report(moved, report)
                (moved / source_task["calculation_ledger_ref"]).unlink()
                with self.assertRaises(ValueError):
                    selected_calculations_for_report(moved, report, for_execution=False)
            finally:
                preserved.rename(run)
            marker = Path(source_output["json"])
            modified = json.loads(marker.read_text())
            modified["claims"][0]["statement"] += " changed"
            modified["report_hash"] = legacy_envelope_hash(modified, hash_field="report_hash")
            marker.write_text(json.dumps(modified))
            with self.assertRaisesRegex(ValueError, "DEPENDENCY_BINDING_INVALID"):
                build_calculation_catalog(run, packet)

    def test_actual_monetary_scale_keeps_all_amounts_tax_basis_and_original_units(self):
        original_gate = fixtures.gate_for
        def monetary_gate(handoff):
            gate = original_gate(handoff)
            fact = next(f for f in gate["allowed_evidence"] if f["evidence_id"] == "ev-aapl-revenue")
            fact["value"] = ("Gain of $1.75 billion pre-tax. " + "Separate disclosure context. " * 4
                             + "Gain of $0.25 billion after-tax.")
            gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
            return gate
        with tempfile.TemporaryDirectory() as directory, patch.object(fixtures, "gate_for", side_effect=monetary_gate):
            run, task, packet = self.prepared(Path(directory))
            ref = next(ref for ref, full in packet["reference_map"]["evidence"].items() if full == "ev-aapl-revenue")
            self.call(run, task, "query", evidence_ids=[ref])
            returned = self.call(run, task, "calculate", operation="monetary_scale", evidence_ids=[ref], target_scale="million")
            self.assertNotIn("error", returned)
            value = returned["result"]["structuredContent"]
            assembled = assemble_calculation_selections(run, packet, self.draft(task, value["calculation_ref"]))
            calculation = assembled["calculations"][0]
            self.assertEqual(json.loads(calculation["value"]), value["conversions"])
            self.assertEqual(calculation["unit"], "USD million")
            self.assertEqual([c["converted_value"] for c in json.loads(calculation["value"])], ["1750", "250"])
            self.assertEqual({c["source_scale"] for c in json.loads(calculation["value"])}, {"billion"})
            self.assertEqual({c["tax_basis"] for c in json.loads(calculation["value"])}, {"PRE_TAX", "AFTER_TAX"})

    def test_compound_period_projection_keeps_periods_and_mixed_original_fields(self):
        output = {"earlier_period": "2026/Q1", "later_period": "2026/Q2",
                  "changes": {"aggregate_holder_percent": {"earlier": "84.671", "later": "81.291", "absolute_change": "-3.380"},
                              "institution_count": {"earlier": "1860", "later": "2562", "absolute_change": "702"}}}
        receipt = {"calculation_id": "period-test", "operation": "institutional_period_change",
                   "evidence_ids": ["earlier", "later"], "output": output}
        calculated = receipt_calculation(receipt, "original/ledger.jsonl")
        self.assertEqual(json.loads(calculated["value"]), output)
        self.assertEqual(calculated["input_evidence_refs"], ["earlier", "later"])
        self.assertEqual(calculated["unit"], "mixed: institution_count / holder_quantity / holder_percent")

    def test_legacy_receipt_reader_preserves_original_unlabelled_unit_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            result = self.successful_ratio(run, task, packet)
            original = (run / task["calculation_ledger_ref"]).read_bytes()
            receipt = json.loads(original)
            calculation = receipt_calculation(receipt, task["calculation_ledger_ref"])
            calculation["unit"] = None  # Historical Schema explicitly allowed it.
            legacy_task = {key: value for key, value in task.items() if key != "calculation_selection_version"}
            invocation = json.loads((run / task["invocation_path"]).read_text())
            legacy_invocation = {key: value for key, value in invocation.items() if key != "calculation_selection_version"}
            _validate_multidimensional_tool_calculations({"calculations": [calculation]},
                task=legacy_task, invocation=legacy_invocation, run_dir=run)
            with self.assertRaisesRegex(ValueError, "RESULT_MISMATCH"):
                _validate_multidimensional_tool_calculations({"calculations": [calculation]},
                    task=task, invocation=invocation, run_dir=run)
            self.assertEqual((run / task["calculation_ledger_ref"]).read_bytes(), original)
