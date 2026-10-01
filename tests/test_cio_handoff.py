"""真实准备器/只读工具/装配器接缝；不调用模型。"""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from product.runtime.cio_handoff import COUNCIL_METADATA, NATIVE_CIO_VERSION, build_cio_reference_map, cio_model_view
from product.runtime.multidimensional_references import translate_references
from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError, serve_stdio
from product.runtime.invocation import verify_invocation_manifest, create_invocation_manifest, build_native_council_schema
from product.runtime.nested_codex import launch_nested_codex
from product.runtime.smoke_prompt import build_smoke_prompt
from product.runtime.run_package import prepare_run, prepare_cio, finalize_cio
from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import validate_schema_instance
from tests.test_native_run_package import specialist_outputs, cio_output, write_json, read_json

REPO = Path(__file__).resolve().parents[1]


class CioHandoffTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.run = Path(directory.name) / "council"
        prepare_run(REPO, fixture_path=REPO / "evals/fixtures/codex-native/normal-research.json",
                    run_dir=self.run, run_id="cio-native-test", model="gpt-5.6-terra",
                    research_question="公司研究交接", authenticity_required=False)
        specialist_outputs(self.run)
        prepare_cio(REPO, run_dir=self.run, model="gpt-5.6-terra")
        self.invocation = read_json(self.run / "invocations/runtime_cio.json")
        self.mapping = build_cio_reference_map(self.run, self.invocation, self.invocation["report_catalog"])
        self.tools = StatelessFixtureTools(default_run_dir=self.run)
        formal = cio_output(self.run)
        self.draft = {key: value for key, value in formal.items() if key not in COUNCIL_METADATA}
        self.draft.update(schema_version=NATIVE_CIO_VERSION, report_selections=["runtime_company_analyst"])
        self.draft = cio_model_view(self.draft, self.mapping)

    def read(self, ids):
        result = self.tools.read_reports(run_id=self.invocation["run_id"], agent="runtime_cio",
                                         invocation_id=self.invocation["invocation_id"],
                                         report_ids=cio_model_view({"report_ids": ids}, self.mapping)["report_ids"])
        path = self.run / "events/mcp/events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as stream:
            stream.write(json.dumps(self.tools.events[-1]) + "\n")
        return result

    def finalize(self, draft=None):
        write_json(self.run / "cio/runtime_cio.json", self.draft if draft is None else draft)
        return finalize_cio(REPO, run_dir=self.run)

    def failure(self, code):
        self.finalize()
        error = read_json(self.run / "run_error.json")
        self.assertIn(code, error["message"])
        self.assertEqual(error["terminal_state"], "FAILED_VALIDATION")
        self.assertFalse((self.run / "decision.json").exists())
        self.assertFalse((self.run / "cio/native-draft.json").exists())

    def test_real_read_and_native_assembly_preserve_decision_then_risk(self):
        ids = [item["report_id"] for item in self.invocation["report_catalog"]]
        result = self.read(ids)
        self.assertEqual(translate_references(result, self.mapping)["reports"][0]["report"],
                         read_json(self.run / "agents/runtime_company_analyst.json"))
        self.assertEqual(self.finalize()["next_state"], "COMPLETED")
        formal = read_json(self.run / "cio/runtime_cio.json")
        for key, value in translate_references(self.draft, self.mapping).items():
            if key not in {"schema_version", "report_selections"}:
                self.assertEqual(formal[key], value)
        self.assertEqual(formal["skill_execution"], self.invocation["skill_execution"])
        self.assertEqual(formal["consumed_reports"], [item["identity"] for item in self.invocation["report_catalog"]])
        trace = read_json(self.run / "decision_trace.json")
        consumption = next(item["proof"] for item in trace["events"] if item["stage"] == "CIO_REPORT_CONSUMPTION_VERIFIED")
        self.assertEqual(consumption["selected_report_ids"], ["runtime_company_analyst"])
        self.assertEqual(consumption["read_report_ids"], sorted(ids))
        self.assertNotIn("cio_report_consumption", trace)
        self.assertTrue(trace["risk_lineage"])
        self.assertEqual(read_json(self.run / "cio/native-draft.json"), self.draft)

    def test_catalog_does_not_prove_read(self):
        self.failure("CIO_SELECTED_REPORT_NOT_READ")

    def test_native_risk_revision_still_uses_original_hard_bounds(self):
        self.read(["runtime_company_analyst", "runtime_skeptic"])
        self.draft["target_weight_range"] = [0.55, 0.8]
        self.assertEqual(self.finalize()["next_state"], "ONE_CIO_REVISION_REQUIRED")
        trace = read_json(self.run / "decision_trace.json")
        self.assertEqual(trace["risk_lineage"][0]["result"]["check"]["status"], "REVISE_REQUIRED")
        self.assertFalse((self.run / "decision.json").exists())

    def test_tool_is_discoverable_before_cio_prepare_but_cannot_read_without_invocation(self):
        invocation_path = self.run / "invocations/runtime_cio.json"
        invocation_path.rename(self.run / "invocations/cio-not-prepared.json")
        self.assertIn("read_reports", {tool["name"] for tool in self.tools.available_tools()})
        with self.assertRaisesRegex(ValueError, "RUN_PACKAGE_BINDING_MISSING"):
            self.tools.read_reports(run_id=self.invocation["run_id"], agent="runtime_cio",
                                    invocation_id=self.invocation["invocation_id"],
                                    report_ids=["runtime_company_analyst"])

    def test_all_required_reports_must_be_read(self):
        self.read(["runtime_company_analyst"])
        self.failure("CIO_REQUIRED_REPORT_NOT_READ")

    def test_corrupt_read_event_fails(self):
        self.read(["runtime_company_analyst", "runtime_skeptic"])
        path = self.run / "events/mcp/events.jsonl"
        event = json.loads(path.read_text())
        event["output_hash"] = "0" * 64
        path.write_text(json.dumps(event) + "\n")
        self.failure("CIO_REPORT_READ_EVENT_INVALID")

    def test_report_changes_after_read_fail(self):
        self.read(["runtime_company_analyst", "runtime_skeptic"])
        report = read_json(self.run / "agents/runtime_skeptic.json")
        report["confidence"] = 0.2
        write_json(self.run / "agents/runtime_skeptic.json", report)
        self.failure("CIO_REPORT_DRIFT")

    def test_other_role_cannot_read_reports(self):
        with self.assertRaisesRegex(ToolAccessError, "CIO_REPORT_READ_NOT_AUTHORIZED"):
            self.tools.read_reports(run_id=self.invocation["run_id"], agent="runtime_skeptic",
                                    invocation_id=self.invocation["invocation_id"],
                                    report_ids=["runtime_company_analyst"])
        self.assertFalse((self.run / "events/mcp/events.jsonl").exists())

    def test_native_schema_rejects_identity_unknown_report_and_no_trade_zero(self):
        schema = read_json(Path(self.invocation["output_schema"]))
        for change in ({"run_id": "spoof"}, {"consumed_reports": []},
                       {"report_selections": ["unknown"]},
                       {"action": "NO_TRADE", "target_weight_range": None, "maximum_notional": 0,
                        "no_trade_reason": "DATA_GAP", "no_trade_explanation": "缺资料",
                        "reevaluation_conditions": ["获得资料"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_schema_instance({**self.draft, **change}, schema)

    def test_invocation_permission_and_catalog_tampering_rejected(self):
        original = copy.deepcopy(self.invocation)
        for field, value in (("tool_permissions", ["fixture_evidence.query"]), ("report_catalog", [])):
            manifest = {**original, field: value}
            manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "NATIVE_CIO_BINDING_INVALID"):
                verify_invocation_manifest(REPO, manifest, agent_input=read_json(self.run / "inputs/runtime_cio.json"))

    def test_actual_stdio_binds_model_view_to_canonical_report_and_query_events(self):
        requests = []
        for name, arguments in (("read_reports", {"report_ids": list(self.mapping["reports"])}),
                                ("query", {"evidence_ids": list(self.mapping["evidence"])})):
            requests.append({"id": len(requests) + 1, "method": "tools/call", "params": {
                "name": name, "arguments": {"run_id": self.invocation["run_id"], "agent": "runtime_cio",
                                            "invocation_id": self.invocation["invocation_id"], **arguments}}})
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n")), patch("sys.stdout", output):
            serve_stdio(stateless=True, default_run_dir=self.run, event_log=self.run / "events/mcp/events.jsonl")
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(all("error" not in response for response in responses), responses)
        delivered = responses[0]["result"]["structuredContent"]
        self.assertEqual(set(item["report_id"] for item in delivered["reports"]), set(self.mapping["reports"]))
        events = [json.loads(line) for line in (self.run / "events/mcp/events.jsonl").read_text().splitlines()]
        self.assertEqual(events[1]["canonical_event_hash"], events[0]["event_hash"])
        self.assertEqual(events[1]["output_hash"], canonical_hash(delivered))
        self.assertEqual(set(events[2]["evidence_ids"]), set(self.mapping["evidence"].values()))
        self.assertEqual(self.finalize()["next_state"], "COMPLETED")
        trace = read_json(self.run / "decision_trace.json")
        consumption = next(item["proof"] for item in trace["events"] if item["stage"] == "CIO_REPORT_CONSUMPTION_VERIFIED")
        self.assertEqual(consumption["reference_map_hash"], self.mapping["map_hash"])
        self.assertEqual(consumption["semantic_output_hash"], canonical_hash(self.draft))
        self.assertTrue(trace["risk_lineage"])
        self.assertTrue((self.run / "report.md").is_file())

    def test_cio_short_enum_rejects_raw_decorated_other_type_and_foreign_run(self):
        evidence = next(iter(self.mapping["evidence"]))
        report = next(iter(self.mapping["reports"]))
        schema = read_json(Path(self.invocation["output_schema"]))
        for key, invalid in (("evidence_refs", ["ev-normal-debt"]),
                             ("evidence_refs", [evidence + "|source=sec"]),
                             ("evidence_refs", [evidence + "|as_of=2026-01-01"]),
                             ("evidence_refs", [report]), ("evidence_refs", ["e.foreign-run.1"]),
                             ("report_selections", ["runtime_company_analyst"]),
                             ("report_selections", [report + "|source=fixture"]),
                             ("report_selections", [evidence]), ("report_selections", ["p.foreign-run.1"])):
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                validate_schema_instance({**self.draft, key: invalid}, schema)
        with self.assertRaisesRegex(ToolAccessError, "CIO_REPORT_REFERENCE_UNKNOWN"):
            self.tools.read_reports(run_id=self.invocation["run_id"], agent="runtime_cio",
                                    invocation_id=self.invocation["invocation_id"], report_ids=["runtime_company_analyst"])

    def test_model_input_tampering_is_rejected_by_actual_tool_and_finalizer(self):
        path = self.run / "inputs/runtime_cio.model.json"
        model_input = read_json(path)
        model_input["portfolio_metrics"]["invented"] = 1
        write_json(path, model_input)
        with self.assertRaisesRegex(ToolAccessError, "CIO_MODEL_INPUT_DRIFT"):
            self.read(["runtime_company_analyst", "runtime_skeptic"])
        self.failure("CIO_MODEL_INPUT_DRIFT")

    def test_actual_model_input_and_prompt_use_shared_schema_refs_not_hashes(self):
        from product.runtime.cio_handoff import fixture_cio_model_input
        canonical = read_json(self.run / "inputs/runtime_cio.json")
        projected = read_json(self.run / "inputs/runtime_cio.model.json")
        self.assertEqual(projected, fixture_cio_model_input(self.run, canonical))
        self.assertEqual(projected["allowed_evidence_ids"], list(self.mapping["evidence"]))
        self.assertEqual(projected["portfolio_metrics"], canonical["portfolio_metrics"])
        for item in projected["report_catalog"]:
            self.assertEqual(set(item), {"report_id", "role"})
        self.assertNotIn("validated_report_hashes", projected)
        prompt = build_smoke_prompt(self.run, repository_root=REPO)
        self.assertIn("inputs/runtime_cio.model.json", prompt)
        self.assertNotIn("读取 `inputs/runtime_cio.json`", prompt)

    def test_resigned_invocation_cannot_switch_identity_or_protocol(self):
        source = read_json(self.run / "inputs/runtime_cio.json")
        for change, error in (({"invocation_id": "inv_forged"}, "NATIVE_CIO_IDENTITY_BINDING_INVALID"),
                              ({"reference_transport_version": "unknown/9"}, "NATIVE_CIO_BINDING_INVALID")):
            candidate = {**self.invocation, **change}
            candidate["manifest_hash"] = canonical_hash({k: v for k, v in candidate.items() if k != "manifest_hash"})
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, error):
                verify_invocation_manifest(REPO, candidate, agent_input=source)

    def test_legacy_fixture_input_readable_but_new_execution_and_write_retired(self):
        # 仅在临时包中构造真实旧格式；不改历史运行/版本锁。
        source = read_json(self.run / "inputs/runtime_cio.json")
        del source["reference_transport_version"]
        write_json(self.run / "inputs/runtime_cio.json", source)
        schema_path = Path(self.invocation["output_schema"])
        write_json(schema_path, build_native_council_schema(REPO, [item["report_id"] for item in source["report_catalog"]]))
        invocation = create_invocation_manifest(REPO, run_id=source["run_id"], agent_name="runtime_cio",
            agent_input=source, task_prompt=(self.run / "prompts/runtime_cio.txt").read_text(),
            model="gpt-5.6-terra", evidence_ids=source["allowed_evidence_ids"], output_schema_path=schema_path)
        write_json(self.run / "invocations/runtime_cio.json", invocation)
        manifest = read_json(self.run / "run_manifest.json")
        del manifest["cio_reference_transport_version"]
        write_json(self.run / "run_manifest.json", manifest)
        self.invocation, self.mapping = invocation, None
        before = {str(path.relative_to(self.run)): path.read_bytes() for path in self.run.rglob("*") if path.is_file()}
        verify_invocation_manifest(REPO, invocation, agent_input=source)
        self.tools.read_reports(run_id=source["run_id"], agent="runtime_cio", invocation_id=invocation["invocation_id"],
                                report_ids=["runtime_company_analyst", "runtime_skeptic"])
        self.assertEqual(before, {str(path.relative_to(self.run)): path.read_bytes() for path in self.run.rglob("*") if path.is_file()})
        with patch("product.runtime.nested_codex.subprocess.run") as process:
            with self.assertRaisesRegex(ValueError, "CIO_LEGACY_REFERENCE_EXECUTION_RETIRED"):
                launch_nested_codex(REPO, run_dir=self.run)
            process.assert_not_called()
        self.failure("CIO_LEGACY_REFERENCE_WRITE_RETIRED")


if __name__ == "__main__":
    unittest.main()
