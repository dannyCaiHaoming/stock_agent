"""普通股语义草稿的真实 MCP、业务装配与落盘；不模拟宿主执行。"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.council.common_stock_research import envelope_equity_research_draft
from product.council.research_output import persist_equity_research_report, render_equity_research_markdown
from product.runtime import common_stock_stage as stage
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.fixture_mcp import serve_stdio
from product.runtime.hashing import canonical_hash
from product.runtime.multidimensional_references import build_reference_map, translate_references
from tests import test_common_stock_research_contracts as fixtures


class CommonStockSemanticHandoffTests(unittest.TestCase):
    def prepare(self, directory, *, attachment=False):
        helper = fixtures.CommonStockNativeStageTests()
        if attachment:
            root = Path(directory)
            handoff = fixtures.stock_handoff(1)
            gate = fixtures.gate_for(handoff, "native-stage-run")
            security_id = handoff["portfolio"]["positions"][0]["security_id"]
            item = {
                "item_id": "synthetic-derived-ratio", "claim_status": "VERIFIED_FACT",
                "source_id": "synthetic-sec", "as_of": "2026-06-30T00:00:00Z",
                "retrieved_at": "2026-07-01T00:00:00Z", "published_at": "2026-07-01T00:00:00Z",
                "period": "2026Q2", "definition": "仅验证冻结计算引用传递的合成附件",
                "unit": "ratio", "value": "0.2", "origin": "DERIVED",
                "formula": "synthetic input one / input two",
                "evidence_refs": gate["allowed_evidence_ids"], "calculation_ref": "calc:synthetic-frozen",
            }
            groups = {name: {"status": "PARTIAL", "coverage": "synthetic attachment handoff",
                             "reason": None, "items": [item] if name == "financial_ratios" else []}
                      for name in ("guidance", "earnings_quality", "debt_liquidity", "operating_kpis",
                                   "governance", "earnings_expectations", "financial_ratios")}
            supplement = fixtures.build_fundamental_supplement(
                supplement_id="synthetic-selection-supplement", security_id=security_id,
                decision_cutoff=gate["decision_cutoff"], groups=groups)
            package = fixtures.build_equity_research_package(
                package_id="synthetic-selection-package", run_id=gate["run_id"], security_id=security_id,
                decision_cutoff=gate["decision_cutoff"], gate_bundle_hash=gate["bundle_hash"],
                artifacts={"fundamental_supplement": supplement})
            for name, value in (("handoff.json", handoff), ("gate.json", gate), ("attachments.json", package)):
                (root / name).write_text(json.dumps(value))
            run = root / "run"
            stage.prepare_common_stock_stage_run(
                fixtures.ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                run_dir=run, run_id=gate["run_id"], model="gpt-5.6-terra",
                equity_research_package_paths=[root / "attachments.json"])
        else:
            run, _ = helper.prepare_stage(directory, count=1)
        task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
        packet = self.frozen_packet(run, task)
        view = json.loads(stage.serialize_common_stock_dispatch_context(packet))
        request = json.loads((run / task["request_path"]).read_text())
        return run, task, request, view

    def call(self, run, request, tool, *, expect_failure=False, **extra):
        args = {key: request[key] for key in ("run_id", "invocation_id")}
        args.update(agent="runtime_company_analyst", **extra)
        message = {"id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(message) + "\n")), patch("sys.stdout", stdout):
            serve_stdio(stateless=True, default_run_dir=run)
        response = json.loads(stdout.getvalue())
        if expect_failure:
            self.assertIn("error", response)
            return response["error"]
        self.assertNotIn("error", response)
        return response["result"]["structuredContent"]

    def draft(self, request, packet=None):
        return fixtures.CommonStockDispatchTests.semantic_draft(fixtures.valid_report(request), packet=packet)

    def frozen_packet(self, run, task):
        return stage.build_common_stock_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def read_report(self, run, task, draft):
        # 只验证合成任务的业务绑定，不签发作者身份、Skill 执行或接受证明。
        stage.validate_common_stock_stage_run_package(fixtures.ROOT, run)
        packet = self.frozen_packet(run, task)
        request = json.loads((run / task["request_path"]).read_text())
        assembled = stage.assemble_common_stock_semantic_draft(
            fixtures.ROOT, draft, request=request, packet=packet)
        invocation = json.loads((run / task["invocation_path"]).read_text())
        calculations = stage._calculation_ids_for_invocation(run, task["invocation_id"])
        report = envelope_equity_research_draft(
            assembled, request=request, skill_execution=invocation["skill_execution"],
            report_id="synthetic-business-report", calculation_artifact_ids=calculations)
        if task.get("equity_research_package_path"):
            stage.validate_delivered_research_references(
                report, run_dir=run, invocation_id=task["invocation_id"])
        gate = json.loads((run / "evidence/gate.json").read_text())
        evidence = [item for item in gate["allowed_evidence"] if item["evidence_id"] in request["allowed_evidence_ids"]]
        render_equity_research_markdown(
            report, request=request, evidence=evidence, calculation_artifact_ids=calculations)
        return report, request, evidence, calculations

    def save_report(self, run, task, draft):
        report, request, evidence, calculations = self.read_report(run, task, draft)
        output = persist_equity_research_report(
            run / "research/reports", report=report, request=request,
            evidence=evidence, calculation_artifact_ids=calculations)
        return report, output

    def assert_no_execution(self, run):
        self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
        self.assertFalse((run / "invocation/subagent-dispatches.jsonl").exists())

    def test_business_assembly_preserves_research_and_exact_calculation_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, request, packet = self.prepare(directory)
            self.assertEqual(packet["output_schema"]["$id"], stage.SEMANTIC_OUTPUT_VERSION)
            for key in ("run_id", "invocation_id", "agent", "artifact_refs", "bindings", "skill_execution"):
                self.assertNotIn(key, packet["output_schema"]["properties"])
            frozen = self.frozen_packet(run, task)
            evidence = self.call(run, request, "query", evidence_ids=packet["allowed_evidence_ids"])
            self.assertEqual({item["evidence_id"] for item in evidence["evidence"]}, set(packet["allowed_evidence_ids"]))
            calculation = self.call(run, request, "calculate", evidence_ids=list(reversed(packet["allowed_evidence_ids"])), operation="ratio")
            self.assertEqual(calculation["value"], "5")
            draft = self.draft(request, frozen)
            draft["claims"][0]["evidence_refs"] = list(reversed(packet["allowed_evidence_ids"]))
            draft["calculation_selections"] = [{"calculation_ref": calculation["calculation_ref"], "claim_ids": [draft["claims"][0]["claim_id"]]}]
            before = copy.deepcopy(draft)
            report, output = self.save_report(run, task, draft)
            events = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
            actual = next(item for item in events if item.get("tool") == "fixture_math.calculate")
            self.assertEqual(actual["evidence_ids"], [frozen["reference_map"]["evidence"][ref] for ref in reversed(packet["allowed_evidence_ids"])])
            assembled = stage.assemble_common_stock_semantic_draft(fixtures.ROOT, before, request=request, packet=frozen)
            for key, value in assembled.items():
                self.assertEqual(report[key], value)
            self.assertEqual(report["artifact_refs"], [actual["calculation_id"]])
            self.assertEqual(report["run_id"], request["run_id"])
            self.assertEqual(report["bindings"]["holding_research_request_hash"], request["request_hash"])
            self.assertEqual(json.loads(Path(output["json"]).read_text()), report)
            self.assertTrue(Path(output["markdown"]).is_file())
            self.assertEqual(draft, before)
            self.assert_no_execution(run)

    def test_technical_echo_and_conflicting_identity_fail_without_formal_report(self):
        for extra in ({"artifact_refs": []}, {"run_id": "foreign"}, {"invocation_id": "foreign"},
                      {"agent": "runtime_independent_skeptic"}, {"run_id": "native-stage-run"}):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                run, task, request, _ = self.prepare(directory)
                with self.assertRaisesRegex(ValueError, "SCHEMA_EXTRA_PROPERTY"):
                    self.read_report(run, task, {**self.draft(request, self.frozen_packet(run, task)), **extra})
                self.assertFalse((run / "research/reports").exists())

    def test_calculation_selection_schema_and_results_do_not_require_mechanical_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, request, view = self.prepare(directory)
            schema = view["output_schema"]
            self.assertIn("calculation_selections", schema["required"])
            self.assertNotIn("calculation_refs", schema["$defs"]["claim"]["properties"])
            self.assertNotIn("calculation_context", view)
            self.assertIn("calculation_selections", view["instruction"])
            self.assertNotIn("成功返回的 calculation_id", view["instruction"])
            self.assertNotIn("并引用其 calculation_id", view["instruction"])
            result = self.call(run, request, "calculate", operation="ratio", evidence_ids=view["allowed_evidence_ids"])
            self.assertTrue(result["calculation_ref"].startswith("k."))
            for technical in ("calculation_id", "receipt_hash", "artifact_ref"):
                self.assertNotIn(technical, result)
            receipt = json.loads((run / task["calculation_ledger_ref"]).read_text())
            self.assertEqual(result["value"], receipt["output"]["value"])
            self.assertEqual(request["invocation_id"], receipt["invocation_id"])

    def test_choice_cannot_replace_value_claim_identity_or_accept_failed_calculation(self):
        failures = {"unknown": "COMMON_STOCK_CALCULATION_SELECTION_UNKNOWN", "unknown-claim": "COMMON_STOCK_CALCULATION_SELECTION_CLAIM_UNKNOWN",
                    "duplicate": "COMMON_STOCK_CALCULATION_SELECTION_DUPLICATE", "copied-value": "SCHEMA_EXTRA_PROPERTY",
                    "mixed": "SCHEMA_EXTRA_PROPERTY", "cross-type": "SCHEMA_PATTERN_INVALID"}
        for kind in failures:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                run, task, request, view = self.prepare(directory)
                result = self.call(run, request, "calculate", operation="ratio", evidence_ids=view["allowed_evidence_ids"])
                draft = self.draft(request, self.frozen_packet(run, task))
                choice = {"calculation_ref": result["calculation_ref"], "claim_ids": [draft["claims"][0]["claim_id"]]}
                draft["calculation_selections"] = [choice]
                if kind == "unknown":
                    choice["calculation_ref"] = "k." + "0" * 12 + "." + "0" * 24
                elif kind == "unknown-claim":
                    choice["claim_ids"] = ["not-an-existing-claim"]
                elif kind == "duplicate":
                    draft["calculation_selections"].append({**choice, "claim_ids": [draft["claims"][1]["claim_id"]]})
                elif kind == "copied-value":
                    choice["value"] = "999"
                elif kind == "mixed":
                    draft["claims"][0]["calculation_refs"] = []
                else:
                    choice["calculation_ref"] = view["allowed_evidence_ids"][0]
                before = copy.deepcopy(draft)
                with self.assertRaisesRegex(ValueError, failures[kind]):
                    self.read_report(run, task, draft)
                self.assertFalse((run / "research/reports").exists())
                self.assertEqual(draft, before)
        with tempfile.TemporaryDirectory() as directory:
            run, task, request, view = self.prepare(directory)
            self.call(run, request, "calculate", operation="ratio", evidence_ids=[view["allowed_evidence_ids"][0]], expect_failure=True)
            self.assertEqual((run / task["calculation_ledger_ref"]).read_bytes(), b"")

    def test_calculation_selection_revalidates_event_input_order_and_receipt_integrity(self):
        for kind in ("order", "value", "event-hash"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                run, task, request, view = self.prepare(directory)
                result = self.call(run, request, "calculate", operation="ratio", evidence_ids=view["allowed_evidence_ids"])
                draft = self.draft(request, self.frozen_packet(run, task))
                draft["calculation_selections"] = [{"calculation_ref": result["calculation_ref"], "claim_ids": [draft["claims"][0]["claim_id"]]}]
                if kind == "event-hash":
                    path = run / "events/mcp/events.jsonl"
                    events = [json.loads(line) for line in path.read_text().splitlines()]
                    next(event for event in events if event.get("tool") == "fixture_math.calculate")["output_hash"] = "0" * 64
                    path.write_text("\n".join(json.dumps(event) for event in events) + "\n")
                else:
                    path = run / task["calculation_ledger_ref"]
                    receipt = json.loads(path.read_text())
                    if kind == "order":
                        receipt["evidence_ids"].reverse()
                    else:
                        receipt["output"]["value"] = "999"
                    receipt["receipt_hash"] = canonical_hash({k: v for k, v in receipt.items() if k != "receipt_hash"})
                    path.write_text(json.dumps(receipt) + "\n")
                with self.assertRaisesRegex(ValueError, "CALCULATION_EVENT_INVALID"):
                    self.read_report(run, task, draft)
                self.assertFalse((run / "research/reports").exists())

    def test_calculation_aliases_do_not_cross_tasks_or_runs(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            run, task, request, view = self.prepare(first)
            other, other_task, other_request, other_view = self.prepare(second)
            result = self.call(run, request, "calculate", operation="ratio", evidence_ids=view["allowed_evidence_ids"])
            self.call(other, other_request, "calculate", operation="ratio", evidence_ids=other_view["allowed_evidence_ids"])
            draft = self.draft(other_request, self.frozen_packet(other, other_task))
            draft["calculation_selections"] = [{"calculation_ref": result["calculation_ref"], "claim_ids": [draft["claims"][0]["claim_id"]]}]
            with self.assertRaisesRegex(ValueError, "COMMON_STOCK_CALCULATION_SELECTION_UNKNOWN"):
                self.read_report(other, other_task, draft)
            self.assertFalse((other / "research/reports").exists())

    def test_frozen_attachment_calculation_requires_actual_read_and_keeps_original_value(self):
        from product.runtime.calculation_handoff import build_common_stock_calculation_catalog
        for read in (False, True):
            with self.subTest(actual_attachment_read=read), tempfile.TemporaryDirectory() as directory:
                run, task, request, view = self.prepare(directory, attachment=True)
                packet = self.frozen_packet(run, task)
                source = run / task["equity_research_package_path"]
                original_bytes = source.read_bytes()
                original = json.loads(original_bytes)
                frozen_item = original["artifacts"][0]["artifact"]["groups"]["financial_ratios"]["items"][0]
                ref, entry = next(iter(build_common_stock_calculation_catalog(run, packet).items()))
                self.assertEqual(entry["kind"], "ATTACHMENT")
                self.assertEqual(entry["calculation_id"], frozen_item["calculation_ref"])
                self.call(run, request, "query", evidence_ids=view["allowed_evidence_ids"])
                if read:
                    delivered = self.call(run, request, "equity_research_attachments.query", security_id=request["security"]["security_id"],
                                          decision_cutoff=original["decision_cutoff"], kinds=["fundamental_supplement"])
                    delivered_item = delivered["artifacts"]["fundamental_supplement"]["groups"]["financial_ratios"]["items"][0]
                    self.assertEqual(delivered_item["calculation_ref"], ref)
                    for key in ("value", "unit", "period", "definition", "formula", "source_id", "as_of", "retrieved_at", "published_at"):
                        self.assertEqual(delivered_item[key], frozen_item[key], key)
                    self.assertEqual(delivered["canonical_result_hash"], canonical_hash({"fundamental_supplement": original["artifacts"][0]["artifact"]}))
                    self.assertEqual(delivered["result_hash"], canonical_hash(delivered["artifacts"]))
                draft = self.draft(request, packet)
                draft["claims"][0]["statement"] = "合成冻结比值为 0.2，只用于验证传递，不证明公司估值便宜。"
                draft["calculation_selections"] = [{"calculation_ref": ref, "claim_ids": [draft["claims"][0]["claim_id"]]}]
                if not read:
                    with self.assertRaisesRegex(ValueError, "EQUITY_RESEARCH_CALCULATION_REFERENCE_DANGLING"):
                        self.read_report(run, task, draft)
                    self.assertFalse((run / "research/reports").exists())
                else:
                    report, output = self.save_report(run, task, draft)
                    self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
                    self.assertEqual(report["claims"][0]["calculation_refs"], [frozen_item["calculation_ref"]])
                    self.assertEqual(report["artifact_refs"], [frozen_item["calculation_ref"]])
                    self.assertIn(draft["claims"][0]["statement"], Path(output["markdown"]).read_text())
                self.assertEqual(source.read_bytes(), original_bytes)
                self.assert_no_execution(run)

    def test_calculation_projection_only_changes_identity_fields_and_aliases_are_stable(self):
        from product.runtime.calculation_handoff import common_stock_calculation_view, build_common_stock_calculation_catalog
        with tempfile.TemporaryDirectory() as directory:
            run, task, request, view = self.prepare(directory)
            first = self.call(run, request, "calculate", operation="ratio", evidence_ids=view["allowed_evidence_ids"])
            packet = self.frozen_packet(run, task)
            before = build_common_stock_calculation_catalog(run, packet)[first["calculation_ref"]]
            second = self.call(run, request, "calculate", operation="ratio", evidence_ids=list(reversed(view["allowed_evidence_ids"])))
            catalog = build_common_stock_calculation_catalog(run, packet)
            self.assertEqual(catalog[first["calculation_ref"]], before)
            self.assertNotEqual(first["calculation_ref"], second["calculation_ref"])
            self.assertNotEqual(first["value"], second["value"])
            identifier = before["calculation_id"]
            source = {"calculation_ref": identifier, "calculation_refs": [identifier], "value": {"calculation_id": identifier, "unit": "ratio"},
                      "metadata": {"calculation_ref": identifier}, "statement": identifier + " 不应改写正文"}
            delivered = common_stock_calculation_view(source, catalog)
            self.assertEqual(delivered["calculation_ref"], first["calculation_ref"])
            self.assertEqual(delivered["calculation_refs"], [first["calculation_ref"]])
            for field in ("value", "metadata", "statement"):
                self.assertEqual(delivered[field], source[field])

    def test_calculation_protocol_and_ledger_cannot_drift_after_resigning_wrappers(self):
        for defect in ("version", "downgrade", "ledger-path"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run, task, request, _ = self.prepare(directory)
                draft = self.draft(request, self.frozen_packet(run, task))
                index_path, manifest_path = run / "research/dispatch-index.json", run / "run_manifest.json"
                index, manifest = json.loads(index_path.read_text()), json.loads(manifest_path.read_text())
                changed = index["tasks"][0]
                invocation_path = run / task["invocation_path"]
                invocation = json.loads(invocation_path.read_text())
                if defect == "ledger-path":
                    changed["calculation_ledger_ref"] = "research/calculations/other-task/tool-results.jsonl"
                    invocation["calculation_ledger_ref"] = changed["calculation_ledger_ref"]
                elif defect == "version":
                    for value in (changed, invocation, manifest):
                        value["calculation_selection_version"] = "unknown/9"
                else:
                    changed.pop("calculation_selection_version")
                invocation["manifest_hash"] = canonical_hash({k: v for k, v in invocation.items() if k != "manifest_hash"})
                invocation_path.write_text(json.dumps(invocation))
                index["index_hash"] = canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
                index_path.write_text(json.dumps(index))
                manifest["dispatch_index_hash"] = index["index_hash"]
                manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises(stage.CommonStockStageError):
                    self.read_report(run, task, draft)
                self.assertFalse((run / "research/reports").exists())

    def test_body_structure_precedes_damaged_calculation_events(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, request, _ = self.prepare(directory)
            draft = self.draft(request, self.frozen_packet(run, task))
            events = run / "events/mcp/events.jsonl"
            events.parent.mkdir(parents=True)
            events.write_text("damaged event\n")
            draft.pop("research_summary")
            with self.assertRaisesRegex(ValueError, "SCHEMA_REQUIRED_MISSING"):
                self.read_report(run, task, draft)

    def test_unknown_evidence_and_unexecuted_calculation_do_not_gain_validity_from_assembly(self):
        for field, ref in (("evidence_refs", "ev-unknown"), ("calculation_refs", "never-executed")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                run, task, request, _ = self.prepare(directory)
                draft = self.draft(request, self.frozen_packet(run, task))
                if field == "calculation_refs":
                    draft["calculation_selections"] = [{"calculation_ref": "k." + "0" * 12 + "." + "0" * 24, "claim_ids": [draft["claims"][0]["claim_id"]]}]
                else:
                    draft["claims"][0][field] = [ref]
                before = copy.deepcopy(draft)
                with self.assertRaisesRegex(ValueError, "COMMON_STOCK_CALCULATION_SELECTION_UNKNOWN" if field == "calculation_refs" else "SCHEMA_ENUM_INVALID"):
                    self.read_report(run, task, draft)
                self.assertFalse((run / "research/reports").exists())
                self.assertEqual(draft, before)

    def test_task_protocol_drift_rejected_even_after_resigning_index(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, request, _ = self.prepare(directory)
            path = run / "research/dispatch-index.json"
            index = json.loads(path.read_text())
            index["tasks"][0].pop("semantic_output_version")
            index["index_hash"] = canonical_hash({key: value for key, value in index.items() if key != "index_hash"})
            path.write_text(json.dumps(index))
            manifest_path = run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["dispatch_index_hash"] = index["index_hash"]
            manifest["manifest_hash"] = canonical_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(stage.CommonStockStageError):
                self.read_report(run, task, self.draft(request))
            self.assertFalse((run / "research/reports").exists())

    def test_history_business_draft_and_formal_reader_stay_byte_equivalent(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, request, _ = self.prepare(directory)
            historical = fixtures.valid_report(request)
            original = json.dumps(historical, ensure_ascii=False, sort_keys=True)
            fixtures.validate_equity_research_report(historical, request=request)
            self.assertEqual(json.dumps(historical, ensure_ascii=False, sort_keys=True), original)
            result = stage.assemble_common_stock_semantic_draft(fixtures.ROOT, self.draft(request), request=request)
            self.assertEqual(result, fixtures.CommonStockDispatchTests.draft(historical))

    def test_model_catalog_schema_and_query_share_exact_map_without_technical_map_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, request, context = self.prepare(directory)
            packet = self.frozen_packet(run, task)
            mapping = packet["reference_map"]
            self.assertNotIn("reference_map", context)
            self.assertEqual(context["allowed_evidence_ids"], list(mapping["evidence"]))
            self.assertEqual(context["output_schema"]["$defs"]["evidence_id"]["enum"], list(mapping["evidence"]))
            self.assertEqual(context["context_budget"]["actual_bytes"], len(stage.serialize_common_stock_dispatch_context(packet).encode()))
            facts = {item["evidence_id"]: item for item in json.loads((run / "evidence/gate.json").read_text())["allowed_evidence"]}
            result = self.call(run, request, "query", evidence_ids=context["allowed_evidence_ids"])
            for fact in result["evidence"]:
                self.assertEqual({**fact, "evidence_id": mapping["evidence"][fact["evidence_id"]]}, facts[mapping["evidence"][fact["evidence_id"]]])
            events = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
            self.assertEqual(events[0]["evidence_ids"], [mapping["evidence"][ref] for ref in context["allowed_evidence_ids"]])
            self.assertEqual(events[1]["reference_map_hash"], mapping["map_hash"])
            self.assertEqual(events[1]["canonical_event_hash"], events[0]["event_hash"])

    def test_short_output_rejects_wrong_type_task_run_raw_and_decorated_reference(self):
        for defect in ("type", "task", "run", "raw", "source", "time", "unknown"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run, task, request, context = self.prepare(directory)
                packet = self.frozen_packet(run, task)
                short = context["allowed_evidence_ids"][0]
                ref = {"type": short.replace("e.", "d.", 1), "task": "e.foreign-task.1", "run": "e.foreign-run.1",
                       "raw": request["allowed_evidence_ids"][0], "source": short + "|source=synthetic-sec",
                       "time": short + "|as_of=2026-06-30", "unknown": "e.unknown.999"}[defect]
                draft = self.draft(request, packet)
                draft["claims"][0]["evidence_refs"] = [ref]
                before = copy.deepcopy(draft)
                with self.assertRaisesRegex(ValueError, "SCHEMA_ENUM_INVALID"):
                    self.read_report(run, task, draft)
                self.assertFalse((run / "research/reports").exists())
                self.assertEqual(before, draft)

    def test_different_security_and_run_cannot_exchange_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _ = fixtures.CommonStockNativeStageTests().prepare_stage(directory, count=2)
            tasks = json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
            left, right = (self.frozen_packet(run, task) for task in tasks)
            self.assertFalse(set(left["reference_map"]["evidence"]) & set(right["reference_map"]["evidence"]))
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                translate_references({"evidence_refs": list(left["reference_map"]["evidence"])}, right["reference_map"])
            with tempfile.TemporaryDirectory() as another:
                second, _, _, _ = self.prepare(another)
                other = self.frozen_packet(second, json.loads((second / "research/dispatch-index.json").read_text())["tasks"][0])
                self.assertFalse(set(left["reference_map"]["evidence"]) & set(other["reference_map"]["evidence"]))

    def test_resigned_mapping_cannot_substitute_frozen_evidence_or_protocol(self):
        for defect in ("map", "downgrade", "unknown"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run, task, request, _ = self.prepare(directory)
                packet = self.frozen_packet(run, task)
                index_path, manifest_path = run / "research/dispatch-index.json", run / "run_manifest.json"
                index, manifest = json.loads(index_path.read_text()), json.loads(manifest_path.read_text())
                if defect == "map":
                    base = {k: v for k, v in packet.items() if k not in {"reference_map", "context_budget"}}
                    base["allowed_evidence_ids"] = ["ev-forged"]
                    packet.update(base)
                    packet["reference_map"] = build_reference_map(base, canonical_hash(json.loads((run / "evidence/gate.json").read_text())), str(run))
                elif defect == "downgrade":
                    index["tasks"][0].pop("reference_transport_version")
                    packet.pop("reference_map")
                    packet.pop("reference_transport_version")
                else:
                    manifest["reference_transport_version"] = "unknown/9"
                (run / task["packet_path"]).write_text(json.dumps(packet))
                index["tasks"][0]["packet_hash"] = canonical_hash(packet)
                index["index_hash"] = canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
                index_path.write_text(json.dumps(index))
                manifest["dispatch_index_hash"] = index["index_hash"]
                manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaises(stage.CommonStockStageError):
                    self.frozen_packet(run, index["tasks"][0])
                error = self.call(run, request, "query", expect_failure=True, evidence_ids=request["allowed_evidence_ids"])
                self.assertRegex(error["message"], "COMMON_STOCK_(DISPATCH_PACKET_BINDING_INVALID|REFERENCE_PROTOCOL_INVALID)")
                if (run / "events/mcp/events.jsonl").exists():
                    events = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
                    self.assertFalse(any(item.get("event_type") == "mcp_tool_result" for item in events))

    def test_translation_preserves_prose_nested_values_metadata_order_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, _ = self.prepare(directory)
            packet = self.frozen_packet(run, task)
            mapping = packet["reference_map"]
            originals = list(reversed(packet["allowed_evidence_ids"]))
            value = {"evidence_refs": originals, "statement": "否定结论；脚注与来源限制 ev-aapl-cash 不应替换。",
                     "value": {"evidence_id": "ev-aapl-cash", "evidence_refs": originals, "unit": "USD"},
                     "metadata": {"evidence_ids": originals, "period_start": "2026-01-01"}}
            before = copy.deepcopy(value)
            model = translate_references(value, mapping, to_model=True)
            for field in ("statement", "value", "metadata"):
                self.assertEqual(model[field], value[field])
            self.assertEqual(translate_references(model, mapping), before)
            self.assertEqual(value, before)
            historical = {"identity": packet["identity"], "evidence_catalog": packet["evidence_catalog"], "output_schema": packet["output_schema"], "value": value}
            original_bytes = json.dumps(historical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.assertEqual(stage.serialize_common_stock_dispatch_context(historical), original_bytes)

    def test_old_full_reference_package_is_readable_but_new_execution_and_write_are_retired(self):
        self.check_old_calculation_packet(short_evidence=False)

    def test_old_short_evidence_packet_is_readable_but_cannot_bypass_calculation_migration(self):
        self.check_old_calculation_packet(short_evidence=True)

    def check_old_calculation_packet(self, *, short_evidence):
        with tempfile.TemporaryDirectory() as directory:
            helper = fixtures.CommonStockNativeStageTests()
            run, _ = helper.prepare_stage(directory, count=1)
            # 显式旧运输格式读取向量；不回写真实历史，不伪造执行证明。
            index_path, manifest_path = run / "research/dispatch-index.json", run / "run_manifest.json"
            index, manifest = json.loads(index_path.read_text()), json.loads(manifest_path.read_text())
            task = index["tasks"][0]
            if not short_evidence:
                task.pop("reference_transport_version")
            task.pop("calculation_selection_version")
            task.pop("calculation_ledger_ref")
            invocation_path = run / task["invocation_path"]
            invocation = json.loads(invocation_path.read_text())
            if not short_evidence:
                invocation.pop("reference_transport_version")
            invocation.pop("calculation_selection_version")
            invocation.pop("calculation_ledger_ref")
            invocation["manifest_hash"] = canonical_hash({k: v for k, v in invocation.items() if k != "manifest_hash"})
            invocation_path.write_text(json.dumps(invocation))
            old_fingerprint = stage._research_input_fingerprint_for_holding(
                fixtures.ROOT, request=json.loads((run / task["request_path"]).read_text()),
                gate=json.loads((run / "evidence/gate.json").read_text()), attachment=None,
                model=invocation["model"], agent=manifest["agent_binding"], skills=manifest["skill_bindings"], calculation_selection_version=None)
            task["research_input_fingerprint"] = old_fingerprint
            from product.runtime.research_memory import report_reuse_key
            task["reuse_key"] = report_reuse_key(task["security_id"], old_fingerprint)
            packet = stage._build_common_stock_dispatch_packet(fixtures.ROOT, run, task)
            (run / task["packet_path"]).write_text(json.dumps(packet))
            task["packet_hash"] = canonical_hash(packet)
            index["index_hash"] = canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
            index_path.write_text(json.dumps(index))
            if not short_evidence:
                manifest.pop("reference_transport_version")
            manifest.pop("calculation_selection_version")
            manifest["dispatch_index_hash"] = index["index_hash"]
            manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
            manifest_path.write_text(json.dumps(manifest))
            originals = {path: path.read_bytes() for path in run.rglob("*") if path.is_file()}
            self.assertEqual(self.frozen_packet(run, task), packet)
            stage.validate_common_stock_stage_run_package(fixtures.ROOT, run)
            context = json.loads(stage.serialize_common_stock_dispatch_context(packet))
            self.assertNotIn("reference_map", context)
            with patch('subprocess.Popen') as process, self.assertRaisesRegex(stage.CommonStockStageError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                stage.launch_common_stock_stage(fixtures.ROOT, run_dir=run)
            process.assert_not_called()
            with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                handle_hook_event({"hook_event_name": "SubagentStop", "last_assistant_message": "{}"}, environ=helper.hook_environment(run))
            self.assertFalse((run / "research/reports").exists())
            self.assertEqual({path: path.read_bytes() for path in run.rglob("*") if path.is_file()}, originals)
