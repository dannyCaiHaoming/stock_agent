from __future__ import annotations

import copy
import inspect
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from product.demo.agents import (
    CioDemoAdapter,
    CompanyAnalystDemoAdapter,
    IndependentSkepticDemoAdapter,
)
from product.demo.contracts import (
    DemoValidationError,
    artifact_ref,
    load_demo_input,
    validate_agent_request,
    validate_agent_response,
    validate_demo_input,
    validate_dispatch_record,
)
from product.demo.runner import run_demo, run_single_agent
from product.demo.topology import build_agent_package_topology
from product.runtime.evidence_gate import run_evidence_gate
from product.runtime.fixture_mcp import GateScopedFixtureTools, ToolAccessError
from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import validate_schema_instance


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "agent-package-demo" / "mvp-demo.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def copy_input(directory: Path, mutate=None) -> Path:
    value = read_json(FIXTURE)
    if mutate:
        mutate(value)
    path = directory / "input.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


class DemoInputAndTopologyTests(unittest.TestCase):
    def test_demo_input_schema_and_required_identity(self):
        value = load_demo_input(FIXTURE)
        schema = read_json(ROOT / "product/schemas/demo/demo-input.schema.json")
        validate_schema_instance(value, schema)
        self.assertEqual(value["profile"], "DEMO_SCAFFOLD")
        self.assertTrue(value["synthetic"])
        self.assertTrue(value["advisory_only"])
        self.assertFalse(value["llm_used"])

    def test_all_demo_contract_schemas_are_versioned_json_objects(self):
        schemas = ROOT / "product" / "schemas" / "demo"
        expected = {
            "demo-input.schema.json",
            "agent-request.schema.json",
            "agent-response.schema.json",
            "dispatch-record.schema.json",
            "demo-decision-envelope.schema.json",
        }
        self.assertEqual({path.name for path in schemas.glob("*.json")}, expected)
        for name in expected:
            schema = read_json(schemas / name)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertTrue(schema["$id"].startswith("portfolio-council/"))
            self.assertEqual(schema["type"], "object")

    def test_missing_field_and_real_profile_impersonation_fail(self):
        value = read_json(FIXTURE)
        del value["research_question"]
        with self.assertRaisesRegex(DemoValidationError, "DEMO_INPUT_KEYS_INVALID"):
            validate_demo_input(value)
        value = read_json(FIXTURE)
        value["profile"] = "fixture-council/3.0.0"
        with self.assertRaisesRegex(DemoValidationError, "DEMO_PROFILE_REQUIRED"):
            validate_demo_input(value)

    def test_future_evidence_is_valid_input_but_excluded_by_pit(self):
        value = read_json(FIXTURE)
        value["evidence"][0]["as_of"] = "2026-02-02T00:00:00Z"
        value["evidence"][0]["retrieved_at"] = "2026-02-02T00:01:00Z"
        checked = validate_demo_input(value)
        gate = run_evidence_gate(checked, run_id=checked["run_id"]).artifact
        self.assertIn("ev-demo-price", gate["excluded_evidence_ids"])
        self.assertIn("FUTURE_AS_OF", gate["excluded"][0]["reason_codes"])

    def test_all_facts_have_required_provenance_and_subjective_content_is_fixture_owned(self):
        value = load_demo_input(FIXTURE)
        for fact in value["evidence"]:
            self.assertTrue(
                {"evidence_id", "source_id", "as_of", "retrieved_at"} <= set(fact)
            )
        source = inspect.getsource(CompanyAnalystDemoAdapter) + inspect.getsource(CioDemoAdapter)
        self.assertNotIn("SEC-DEMO", source)
        self.assertNotIn("财务压力暂未主导", source)
        self.assertIn("risk_veto_cio_sample", value)

    def test_topology_binds_actual_package_and_complete_capability_map(self):
        topology = build_agent_package_topology(ROOT)
        self.assertTrue(topology["binding_verified"])
        self.assertFalse(topology["reasoning_executed"])
        self.assertEqual(
            set(topology["agents"]),
            {"runtime_company_analyst", "runtime_skeptic", "runtime_cio"},
        )
        self.assertEqual(
            topology["mcp"]["tools"],
            ["fixture_evidence.query", "fixture_math.calculate"],
        )
        for mapping in topology["capability_map"].values():
            self.assertEqual(
                set(mapping),
                {"input", "tool_data", "skill_reasoning", "structured_output", "mvp_check"},
            )
        excluded = topology["excluded_agents"][0]
        self.assertEqual(excluded["name"], "runtime_market_catalyst")
        self.assertFalse(excluded["instantiated"])
        self.assertTrue(excluded["reason"])

    def test_missing_or_drifted_package_binding_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            shutil.copytree(ROOT / "product", repo / "product")
            (repo / "product/skills/company-research/SKILL.md").unlink()
            with self.assertRaisesRegex(DemoValidationError, "PACKAGE_BINDING_MISSING"):
                build_agent_package_topology(repo)
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            shutil.copytree(ROOT / "product", repo / "product")
            path = repo / "product/runtime-profile.json"
            value = read_json(path)
            value["agents"]["runtime_skeptic"]["skills"] = ["counter-thesis"]
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(DemoValidationError, "AGENT_SKILL_BINDING_DRIFT"):
                build_agent_package_topology(repo)


class DemoContractAndPortTests(unittest.TestCase):
    def setUp(self):
        self.demo_input = load_demo_input(FIXTURE)
        self.gate = run_evidence_gate(
            self.demo_input, run_id=self.demo_input["run_id"]
        ).artifact
        self.request = {
            "schema_version": "demo-agent-request/1.0.0",
            "run_id": self.demo_input["run_id"],
            "invocation_id": "inv-test",
            "sender": "demo_orchestrator",
            "recipient": "runtime_company_analyst",
            "input_refs": [artifact_ref("input", self.demo_input)],
            "portfolio_summary": {"positions": []},
            "research_question": "test",
            "decision_cutoff": self.demo_input["decision_cutoff"],
            "allowed_evidence_ids": self.gate["allowed_evidence_ids"],
            "demo_payload": self.demo_input["role_samples"]["analyst"],
            "upstream_responses": [],
        }

    def test_same_outer_request_contract_accepts_three_roles_with_cio_upstream(self):
        validate_agent_request(self.request)
        skeptic = {**self.request, "recipient": "runtime_skeptic"}
        validate_agent_request(skeptic)
        stub = {
            "schema_version": "demo-agent-response/1.0.0",
            "run_id": self.demo_input["run_id"],
            "invocation_id": "stub",
            "agent_name": "runtime_company_analyst",
            "status": "COMPLETE",
            "input_refs": self.request["input_refs"],
            "output": {},
            "producer_type": "deterministic_demo",
            "llm_used": False,
            "skill_reasoning_executed": False,
        }
        cio = {
            **self.request,
            "recipient": "runtime_cio",
            "upstream_responses": [stub, {**stub, "agent_name": "runtime_skeptic"}],
        }
        validate_agent_request(cio)

    def test_cio_rejects_missing_or_duplicate_specialist_identity(self):
        stub = {
            "schema_version": "demo-agent-response/1.0.0",
            "run_id": self.demo_input["run_id"],
            "invocation_id": "stub",
            "agent_name": "runtime_company_analyst",
            "status": "COMPLETE",
            "input_refs": self.request["input_refs"],
            "output": {},
            "producer_type": "deterministic_demo",
            "llm_used": False,
            "skill_reasoning_executed": False,
        }
        missing = {
            **self.request,
            "recipient": "runtime_cio",
            "upstream_responses": [stub],
        }
        with self.assertRaisesRegex(DemoValidationError, "CIO_REQUIRES_TWO"):
            validate_agent_request(missing)
        duplicated = {
            **missing,
            "upstream_responses": [stub, copy.deepcopy(stub)],
        }
        validate_agent_request(duplicated)
        topology = build_agent_package_topology(ROOT)
        tools = GateScopedFixtureTools(
            self.gate,
            run_id=self.demo_input["run_id"],
            agent="runtime_cio",
            invocation_id=duplicated["invocation_id"],
            allowed_tools=("fixture_evidence.query",),
        )
        from product.demo.ports import EvidenceQueryPort
        with self.assertRaisesRegex(DemoValidationError, "CIO_SPECIALIST_IDENTITIES_INVALID"):
            CioDemoAdapter().respond(
                duplicated, evidence=EvidenceQueryPort(tools), topology=topology
            )

    def test_bad_request_response_and_dispatch_identity_fail(self):
        with self.assertRaisesRegex(DemoValidationError, "REQUEST_ROUTE_INVALID"):
            validate_agent_request({**self.request, "sender": "runtime_skeptic"})
        response = {
            "schema_version": "demo-agent-response/1.0.0",
            "run_id": "wrong-run",
            "invocation_id": "inv-test",
            "agent_name": "runtime_company_analyst",
            "status": "COMPLETE",
            "input_refs": self.request["input_refs"],
            "output": {},
            "producer_type": "deterministic_demo",
            "llm_used": False,
            "skill_reasoning_executed": False,
        }
        with self.assertRaisesRegex(DemoValidationError, "CROSS_RUN_OUTPUT"):
            validate_agent_response(response, request=self.request)
        dispatch = {
            "schema_version": "demo-dispatch-record/1.0.0",
            "run_id": self.demo_input["run_id"],
            "dispatch_id": "d1",
            "from": "runtime_company_analyst",
            "to": "runtime_cio",
            "artifact_ref": artifact_ref("response", response),
            "validation_status": "VALIDATED",
        }
        with self.assertRaisesRegex(DemoValidationError, "DISPATCH_RECIPIENT_MISMATCH"):
            validate_dispatch_record(dispatch, expected_recipient="runtime_skeptic")

    def test_agent_response_cannot_choose_next_recipient(self):
        response = {
            "schema_version": "demo-agent-response/1.0.0",
            "run_id": self.request["run_id"],
            "invocation_id": self.request["invocation_id"],
            "agent_name": self.request["recipient"],
            "status": "COMPLETE",
            "input_refs": self.request["input_refs"],
            "output": {"next_recipient": "runtime_cio"},
            "producer_type": "deterministic_demo",
            "llm_used": False,
            "skill_reasoning_executed": False,
        }
        with self.assertRaisesRegex(DemoValidationError, "AGENT_ROUTING_DECISION_FORBIDDEN"):
            validate_agent_response(response, request=self.request)

    def test_gate_scoped_port_rejects_unknown_excluded_cross_run_and_identity(self):
        tools = GateScopedFixtureTools(
            self.gate,
            run_id=self.demo_input["run_id"],
            agent="runtime_company_analyst",
            invocation_id="inv-test",
        )
        result = tools.query(
            run_id=self.demo_input["run_id"],
            agent="runtime_company_analyst",
            invocation_id="inv-test",
            evidence_ids=["ev-demo-price"],
        )
        self.assertEqual(result["evidence"][0]["evidence_id"], "ev-demo-price")
        with self.assertRaisesRegex(ToolAccessError, "UNKNOWN_EVIDENCE"):
            tools.query(
                run_id=self.demo_input["run_id"],
                agent="runtime_company_analyst",
                invocation_id="inv-test",
                evidence_ids=["unknown"],
            )
        with self.assertRaisesRegex(ToolAccessError, "CROSS_RUN_QUERY"):
            tools.query(
                run_id="other",
                agent="runtime_company_analyst",
                invocation_id="inv-test",
                evidence_ids=["ev-demo-price"],
            )
        self.assertFalse(hasattr(tools, "fixture_path"))


class DemoFlowTests(unittest.TestCase):
    def test_complete_flow_generates_all_artifacts_and_raw_handoffs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run = run_demo(ROOT, input_path=FIXTURE, output_dir=output)
            self.assertEqual(run["terminal_state"], "DEMO_COMPLETED")
            for relative in run["artifacts"]:
                self.assertTrue((output / relative).is_file(), relative)
            analyst = read_json(output / "agents/responses/runtime_company_analyst.json")
            skeptic = read_json(output / "agents/responses/runtime_skeptic.json")
            cio_request = read_json(output / "agents/requests/runtime_cio.json")
            self.assertEqual(
                cio_request["upstream_responses"], [analyst, skeptic]
            )
            self.assertEqual(
                {item["agent"] for item in run["agent_invocations"]},
                {"runtime_company_analyst", "runtime_skeptic", "runtime_cio"},
            )
            self.assertEqual(len({item["invocation_id"] for item in run["agent_invocations"]}), 3)
            self.assertFalse(run["llm_used"])
            self.assertFalse(run["skill_reasoning_executed"])
            self.assertFalse(run["real_subagents_started"])
            self.assertFalse(run["main_thread_cio_executed"])
            self.assertFalse(run["advanced_assurance_run"])

    def test_specialist_first_passes_are_isolated_and_adapters_are_distinct(self):
        self.assertIsNot(CompanyAnalystDemoAdapter, IndependentSkepticDemoAdapter)
        self.assertIsNot(CompanyAnalystDemoAdapter, CioDemoAdapter)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run_demo(ROOT, input_path=FIXTURE, output_dir=output)
            analyst = read_json(output / "agents/requests/runtime_company_analyst.json")
            skeptic = read_json(output / "agents/requests/runtime_skeptic.json")
            self.assertEqual(analyst["upstream_responses"], [])
            self.assertEqual(skeptic["upstream_responses"], [])
            self.assertNotIn("analyst", json.dumps(skeptic).casefold())
            self.assertNotEqual(analyst["invocation_id"], skeptic["invocation_id"])

    def test_invalid_evidence_reference_fails_before_cio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = copy_input(
                root,
                lambda value: value["role_samples"]["analyst"]["claims"][0][
                    "evidence_refs"
                ].append("missing-evidence"),
            )
            output = root / "run"
            with self.assertRaisesRegex(DemoValidationError, "EVIDENCE_CLOSURE_FAILED"):
                run_demo(ROOT, input_path=path, output_dir=output)
            failure = read_json(output / "failure.json")
            self.assertEqual(failure["terminal_state"], "DEMO_FAILED_VALIDATION")
            self.assertFalse((output / "agents/requests/runtime_cio.json").exists())

    def test_all_evidence_excluded_is_pre_agent_safe_no_trade(self):
        def future(value):
            for fact in value["evidence"]:
                fact["as_of"] = "2026-02-02T00:00:00Z"
                fact["retrieved_at"] = "2026-02-02T00:01:00Z"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = copy_input(root, future)
            output = root / "run"
            run = run_demo(ROOT, input_path=path, output_dir=output)
            decision = read_json(output / "decision.json")
            self.assertEqual(run["terminal_state"], "DEMO_SAFE_NO_TRADE")
            self.assertEqual(decision["decision"]["action"], "NO_TRADE")
            self.assertIsNone(decision["decision"]["target_weight_range"])
            self.assertIsNone(decision["decision"]["maximum_notional"])
            self.assertEqual(run["agent_invocations"], [])
            self.assertFalse((output / "agents").exists())
            self.assertFalse((output / "risk").exists())

    def test_degraded_specialist_statuses_are_delivered_to_cio(self):
        def degraded(value):
            value["role_samples"]["analyst"]["status"] = "TIMEOUT"
            value["role_samples"]["skeptic"]["status"] = "LOW_CONFIDENCE"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = copy_input(root, degraded)
            output = root / "run"
            run_demo(ROOT, input_path=path, output_dir=output)
            cio_input = read_json(output / "agents/requests/runtime_cio.json")
            statuses = {item["status"] for item in cio_input["upstream_responses"]}
            self.assertEqual(statuses, {"TIMEOUT", "LOW_CONFIDENCE"})

    def test_risk_veto_cannot_be_overridden(self):
        def veto(value):
            value["role_samples"]["cio"] = copy.deepcopy(value["risk_veto_cio_sample"])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = copy_input(root, veto)
            output = root / "run"
            run = run_demo(ROOT, input_path=path, output_dir=output)
            risk = read_json(output / "risk/result.json")
            decision = read_json(output / "decision.json")["decision"]
            self.assertEqual(risk["check"]["status"], "REJECTED")
            self.assertEqual(run["terminal_state"], "DEMO_SAFE_NO_TRADE")
            self.assertEqual(decision["action"], "NO_TRADE")
            self.assertEqual(decision["no_trade_reason"], "RISK_VETO")
            self.assertIsNone(decision["target_weight_range"])
            self.assertIsNone(decision["maximum_notional"])

    def test_report_contains_required_sections_provenance_and_limitations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            run_demo(ROOT, input_path=FIXTURE, output_dir=output)
            report = (output / "report.md").read_text(encoding="utf-8")
            for text in (
                "Portfolio", "角色状态", "Thesis 与反证", "共识与冲突",
                "Evidence", "数据缺口", "失效条件", "决策与置信度",
                "deterministic Risk Engine", "合成示例", "未使用真实 LLM",
                "source_id=", "as_of=", "retrieved_at=", "不得作为投资建议",
            ):
                self.assertIn(text, report)

    def test_three_agents_can_be_called_individually_with_same_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analyst = root / "analyst.json"
            skeptic = root / "skeptic.json"
            cio = root / "cio.json"
            run_single_agent(
                ROOT, input_path=FIXTURE, agent="runtime_company_analyst",
                output_path=analyst,
            )
            run_single_agent(
                ROOT, input_path=FIXTURE, agent="runtime_skeptic",
                output_path=skeptic,
            )
            run_single_agent(
                ROOT, input_path=FIXTURE, agent="runtime_cio", output_path=cio,
                analyst_response_path=analyst, skeptic_response_path=skeptic,
            )
            values = [read_json(path) for path in (analyst, skeptic, cio)]
            self.assertEqual(
                {item["schema_version"] for item in values},
                {"demo-agent-response/1.0.0"},
            )
            self.assertEqual({item["agent_name"] for item in values}, {
                "runtime_company_analyst", "runtime_skeptic", "runtime_cio"
            })
            self.assertTrue(all(item["producer_type"] == "deterministic_demo" for item in values))
            self.assertTrue(all(item["llm_used"] is False for item in values))

    def test_explicit_cli_runs_without_nested_codex_or_assurance_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli-run"
            result = subprocess.run(
                [
                    sys.executable, "scripts/council-dev.py", "demo", "run",
                    "--repo", str(ROOT), "--input", str(FIXTURE),
                    "--output-dir", str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            run = read_json(output / "demo_run.json")
            self.assertFalse(run["advanced_assurance_run"])
            self.assertFalse((output / "eval").exists())
            self.assertFalse((output / "replay").exists())
            self.assertFalse((output / "promotion").exists())
            source = (ROOT / "product/demo/runner.py").read_text(encoding="utf-8")
            self.assertNotIn("nested_codex", source)
            self.assertNotIn("runtime_eval", source)


if __name__ == "__main__":
    unittest.main()
