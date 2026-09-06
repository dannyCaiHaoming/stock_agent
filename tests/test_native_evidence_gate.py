from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.evidence_gate import (
    FixtureValidationError,
    load_fixture,
    run_evidence_gate,
    validate_fixture,
)
from product.runtime.fixture_mcp import (
    GateScopedFixtureTools,
    StatelessFixtureTools,
    ToolAccessError,
)
from product.runtime.run_package import prepare_run


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures" / "codex-native"


class NativeFixtureTests(unittest.TestCase):
    def test_four_versioned_scenarios_are_valid_and_provenanced(self):
        expected = {
            "normal-research.json": "normal",
            "future-or-stale.json": "future_or_stale",
            "evidence-conflict.json": "evidence_conflict",
            "risk-veto.json": "risk_veto",
        }
        for filename, scenario_type in expected.items():
            fixture = load_fixture(FIXTURES / filename)
            self.assertEqual(fixture["fixture_version"], "2.0.0")
            self.assertEqual(fixture["scenario_type"], scenario_type)
            for fact in fixture["evidence"]:
                for field in ("evidence_id", "source_id", "as_of", "retrieved_at"):
                    self.assertTrue(fact[field])

    def test_risk_boundary_draft_is_explicitly_not_llm_output(self):
        fixture = load_fixture(FIXTURES / "risk-veto.json")
        boundary = json.loads(
            (FIXTURES / fixture["boundary_draft_fixture"]).read_text(encoding="utf-8")
        )
        self.assertEqual(boundary["producer"], "fixture")
        self.assertTrue(boundary["not_llm_output"])

    def test_missing_provenance_fails_fixture_validation(self):
        fixture = load_fixture(FIXTURES / "normal-research.json")
        broken = copy.deepcopy(fixture)
        del broken["evidence"][0]["retrieved_at"]
        with self.assertRaisesRegex(FixtureValidationError, "missing provenance"):
            validate_fixture(broken)


class EvidenceGateTests(unittest.TestCase):
    def test_future_as_of_future_retrieval_and_stale_are_precisely_excluded(self):
        fixture = load_fixture(FIXTURES / "future-or-stale.json")
        result = run_evidence_gate(fixture, run_id="run-temporal").artifact
        self.assertEqual(result["allowed_evidence_ids"], [])
        reasons = {
            item["evidence_id"]: item["reason_codes"] for item in result["excluded"]
        }
        self.assertEqual(
            reasons["ev-future-asof"],
            ["FUTURE_AS_OF", "FUTURE_RETRIEVAL"],
        )
        self.assertEqual(reasons["ev-future-retrieval"], ["FUTURE_RETRIEVAL"])
        self.assertEqual(reasons["ev-stale-update"], ["STALE"])

    def test_conflict_gate_preserves_sources_and_values_without_a_winner(self):
        fixture = load_fixture(FIXTURES / "evidence-conflict.json")
        result = run_evidence_gate(fixture, run_id="run-conflict").artifact
        self.assertEqual(len(result["conflicts"]), 1)
        conflict = result["conflicts"][0]
        self.assertEqual(
            conflict["evidence_ids"],
            ["ev-conflict-revenue-a", "ev-conflict-revenue-b"],
        )
        self.assertEqual(
            conflict["source_ids"],
            ["fixture-filing-source-a", "fixture-filing-source-b"],
        )
        self.assertEqual({item["value"] for item in conflict["observations"]}, {1000000, 1250000})
        self.assertNotIn("winner", conflict)
        self.assertNotIn("materiality", conflict)

    def test_gate_artifact_is_reproducibly_hashed(self):
        fixture = load_fixture(FIXTURES / "normal-research.json")
        first = run_evidence_gate(fixture, run_id="run-stable").artifact
        second = run_evidence_gate(fixture, run_id="run-stable").artifact
        self.assertEqual(first, second)
        self.assertEqual(len(first["bundle_hash"]), 64)
        self.assertEqual(
            set(first["input_evidence_ids"]),
            set(first["allowed_evidence_ids"]) | set(first["excluded_evidence_ids"]),
        )


class GateScopedFixtureToolTests(unittest.TestCase):
    def setUp(self):
        fixture = load_fixture(FIXTURES / "normal-research.json")
        self.gate = run_evidence_gate(fixture, run_id="run-tools").artifact
        self.tools = GateScopedFixtureTools(
            self.gate,
            run_id="run-tools",
            agent="runtime_company_analyst",
            invocation_id="inv-tools",
        )

    def test_query_returns_only_gate_allowed_evidence_and_records_read_event(self):
        result = self.tools.query(
            run_id="run-tools",
            agent="runtime_company_analyst",
            invocation_id="inv-tools",
            evidence_ids=["ev-normal-price"],
        )
        self.assertEqual(result["evidence"][0]["evidence_id"], "ev-normal-price")
        self.assertEqual(self.tools.events[-1]["access_mode"], "read")
        self.assertEqual(self.tools.events[-1]["tool"], "fixture_evidence.query")
        self.assertEqual(self.tools.events[-1]["agent"], "runtime_company_analyst")
        self.assertEqual(self.tools.events[-1]["invocation_id"], "inv-tools")

    def test_unknown_excluded_and_cross_run_queries_fail_closed(self):
        with self.assertRaisesRegex(ToolAccessError, "UNKNOWN_EVIDENCE"):
            self.tools.query(
                run_id="run-tools",
                agent="runtime_company_analyst",
                invocation_id="inv-tools",
                evidence_ids=["does-not-exist"],
            )
        with self.assertRaisesRegex(ToolAccessError, "CROSS_RUN_QUERY"):
            self.tools.query(
                run_id="another-run",
                agent="runtime_company_analyst",
                invocation_id="inv-tools",
                evidence_ids=["ev-normal-price"],
            )

        temporal = load_fixture(FIXTURES / "future-or-stale.json")
        temporal_gate = run_evidence_gate(temporal, run_id="run-temporal").artifact
        temporal_tools = GateScopedFixtureTools(
            temporal_gate,
            run_id="run-temporal",
            agent="runtime_skeptic",
            invocation_id="inv-temporal",
            allowed_tools=("fixture_evidence.query",),
        )
        with self.assertRaisesRegex(ToolAccessError, "EXCLUDED_EVIDENCE"):
            temporal_tools.query(
                run_id="run-temporal", evidence_ids=["ev-future-asof"]
                , agent="runtime_skeptic", invocation_id="inv-temporal"
            )

    def test_calculation_uses_only_authorized_numeric_facts(self):
        result = self.tools.calculate(
            run_id="run-tools",
            agent="runtime_company_analyst",
            invocation_id="inv-tools",
            operation="ratio",
            evidence_ids=["ev-normal-debt", "ev-normal-revenue"],
        )
        self.assertEqual(result["value"], "0.15")
        self.assertEqual(self.tools.events[-1]["tool"], "fixture_math.calculate")

    def test_tool_manifest_has_no_write_or_broker_surface(self):
        manifest = GateScopedFixtureTools.tool_manifest()
        self.assertEqual({item["name"] for item in manifest}, {"query", "calculate"})
        searchable = json.dumps(manifest).casefold()
        for forbidden in ("write", "broker", "order", "account"):
            self.assertNotIn(forbidden, searchable)

    def test_agent_specific_tool_surface_rejects_ungranted_calculation(self):
        skeptic = GateScopedFixtureTools(
            self.gate,
            run_id="run-tools",
            agent="runtime_skeptic",
            invocation_id="inv-skeptic",
            allowed_tools=("fixture_evidence.query",),
        )
        self.assertEqual([item["name"] for item in skeptic.available_tools()], ["query"])
        with self.assertRaisesRegex(ToolAccessError, "TOOL_NOT_AUTHORIZED"):
            skeptic.calculate(
                run_id="run-tools",
                agent="runtime_skeptic",
                invocation_id="inv-skeptic",
                operation="ratio",
                evidence_ids=["ev-normal-debt", "ev-normal-revenue"],
            )

    def test_stateless_server_resolves_only_verified_run_and_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="stateless-run",
                model="gpt-5.6-terra",
                research_question="验证无状态 MCP。",
            )
            invocation = json.loads(
                (run_dir / "invocations" / "runtime_company_analyst.json").read_text()
            )
            tools = StatelessFixtureTools()
            result = tools.query(
                run_dir=str(run_dir),
                run_id="stateless-run",
                agent="runtime_company_analyst",
                invocation_id=invocation["invocation_id"],
                evidence_ids=["ev-normal-revenue"],
            )
            self.assertEqual(result["evidence"][0]["source_id"], "fixture-filing-primary")
            self.assertEqual(tools.events[-1]["invocation_id"], invocation["invocation_id"])
            with self.assertRaisesRegex(ToolAccessError, "INVOCATION_IDENTITY_MISMATCH"):
                tools.query(
                    run_dir=str(run_dir),
                    run_id="stateless-run",
                    agent="runtime_company_analyst",
                    invocation_id="wrong",
                    evidence_ids=["ev-normal-revenue"],
                )


if __name__ == "__main__":
    unittest.main()
