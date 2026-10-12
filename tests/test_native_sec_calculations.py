"""原生SEC金额接缝；合成事实与真实业务工具，不执行模型或来源请求。"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from product.mcp.provenance import content_hash
from product.runtime.hashing import legacy_envelope_hash
from product.tools.evidence import EvidenceTools
from product.tools.research import ResearchTools, prepare_task
from product.tools.research_connection import ResearchConnection, prepare_connection
from tests.test_native_research_submission import company_draft
from tests.test_native_research_tools import AT, ROOT, SECURITY, frozen_gate
from tests.test_single_stock_input import alb_request


def sec_gate():
    gate = frozen_gate()
    for fact in gate["allowed_evidence"][:2]:
        ref, amount = fact["evidence_id"], fact["value"]
        parent = "ev-sec-" + ref
        fact.update({
            "schema_version": "research-supplement-fact/1.1.0", "dataset": "financial_history",
            "source_family": "sec", "source_id": "sec-companyfacts-0000000001:" + parent,
            "semantic_field": "sec_financial_fact:" + ref,
            "value": {"amount": amount, "unit": "USD", "accession": "synthetic-accession",
                      "taxonomy": "us-gaap", "tag": "Revenue" if ref == "ev-revenue" else "NetIncomeLoss",
                      "context_type": "duration", "period_start": "2026-01-01",
                      "period_end": AT[:10], "parent_evidence_id": parent},
        })
    gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
    return gate


class NativeSecCalculationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.sequence = 0

    def tearDown(self):
        self.tmp.cleanup()

    def tools(self, gate=None, capability="COMPANY_RESEARCH"):
        self.sequence += 1
        gate = copy.deepcopy(gate if gate is not None else sec_gate())
        gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
        root = Path(self.tmp.name)/str(self.sequence)
        grant = prepare_task(root, research_input=alb_request(), gate=gate,
                             security_id=SECURITY, capability=capability)
        return ResearchTools(root, access_token=grant["access_token"])

    def assert_no_success(self, tools):
        self.assertFalse((tools.root/"calculations").exists())
        self.assertFalse((tools.root/"tools").exists())
        self.assertFalse((tools.root/"submissions").exists())

    def test_ratio_preserves_original_facts_and_exact_selection_through_submission(self):
        gate = sec_gate()
        before = copy.deepcopy(gate)
        tools = self.tools(gate)
        files = {p.name: p.read_bytes() for p in tools.root.glob("*.json")}
        result = tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assertEqual(result["value"], "0.2")
        self.assertEqual(result["evidence_ids"], ["ev-income", "ev-revenue"])
        for item, fact in zip(result["numeric_inputs"], reversed(gate["allowed_evidence"][:2])):
            self.assertEqual(item["source_fact_hash"], content_hash(fact))
            self.assertEqual(item["value_path"], "value.amount")
            for field in ("source_id", "as_of", "retrieved_at"):
                self.assertEqual(item[field], fact[field])
            for field in ("unit", "period_start", "period_end", "amount", "accession", "tag"):
                self.assertEqual(item[field], fact["value"][field])
        saved = json.loads(next((tools.root/"calculations").glob("*.json")).read_text())
        self.assertEqual(saved, result)
        catalog = tools.calculations()["calculations"]
        tools.query(evidence_ids=["ev-income", "ev-revenue"])
        draft = company_draft()
        draft["calculation_selections"] = [{"calculation_ref": catalog[0]["calculation_ref"],
                                            "claim_ids": [draft["claims"][0]["claim_id"]]}]
        receipt = tools.submit(draft=draft)
        self.assertTrue(receipt["accepted"], receipt)
        report = tools.read_submission(draft_ref=receipt["draft_ref"])
        self.assertEqual(report["calculation_support"][0]["calculation"]["value"], "0.2")
        self.assertEqual(report["host_execution"], "UNVERIFIED")
        self.assertEqual(report["content_verdict"], "NOT_REVIEWED")
        self.assertEqual(gate, before)
        self.assertEqual(files, {p.name: p.read_bytes() for p in tools.root.glob("*.json")})

    def test_instant_ratio_keeps_frame_and_mixed_scalar_is_not_coerced(self):
        gate = sec_gate()
        for fact in gate["allowed_evidence"][:2]:
            fact["value"].update(context_type="instant", period_start=None)
        result = self.tools(gate).calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assertEqual(result["value"], "0.2")
        self.assertTrue(all(item["context_type"] == "instant" and item["period_start"] is None
                            for item in result["numeric_inputs"]))
        gate["allowed_evidence"][0]["value"] = "100"
        tools = self.tools(gate)
        with self.assertRaisesRegex(ValueError, "SEC_NUMERIC_EVIDENCE_INVALID"):
            tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assert_no_success(tools)

    def test_monetary_scale_uses_base_usd_and_never_infers_tax_basis(self):
        gate = sec_gate()
        gate["allowed_evidence"][0]["value"].update(
            amount="1250000000", context_type="instant", period_start=None,
        )
        tools = self.tools(gate)
        result = tools.calculate(operation="monetary_scale", evidence_ids=["ev-revenue"], target_scale="billion")
        conversion = result["conversions"][0]
        self.assertEqual(conversion["converted_value"], "1.25")
        self.assertEqual(conversion["source_scale"], "one")
        self.assertEqual(conversion["currency"], "USD")
        self.assertEqual(conversion["tax_basis"], "UNSPECIFIED")
        self.assertEqual(json.loads(conversion["source_text"]), gate["allowed_evidence"][0]["value"])
        self.assertEqual(tools.calculations()["calculations"][0]["calculation"]["unit"], "USD/billion")

    def test_unknown_objects_invalid_amounts_and_periods_leave_no_success_records(self):
        mutations = [
            ("amount", "NaN"), ("amount", "Infinity"), ("amount", True), ("amount", "USD 100"),
            ("amount", None), ("amount", {"number": "100"}), ("amount", 1.5),
            ("period_start", "2026-12-01"), ("period_end", "not-a-date"),
            ("period_end", "2026-10-03"), ("context_type", "unknown"), ("unit", ""),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                gate = sec_gate()
                gate["allowed_evidence"][0]["value"][field] = value
                tools = self.tools(gate)
                with self.assertRaisesRegex(ValueError, "SEC_NUMERIC_EVIDENCE_INVALID"):
                    tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
                self.assert_no_success(tools)
        for field, value in (("source_family", "other"), ("schema_version", "unknown"),
                             ("semantic_field", "arbitrary_amount"), ("source_id", "not-sec")):
            with self.subTest(field=field):
                gate = sec_gate()
                gate["allowed_evidence"][0][field] = value
                tools = self.tools(gate)
                with self.assertRaisesRegex(ValueError, "SEC_NUMERIC_EVIDENCE_INVALID"):
                    tools.calculate(operation="monetary_scale", evidence_ids=["ev-revenue"], target_scale="million")
                self.assert_no_success(tools)

    def test_ratio_never_silently_aligns_units_accessions_or_periods(self):
        for field, value in (("unit", "EUR"), ("accession", "restated"), ("taxonomy", "ifrs-full"),
                             ("period_start", "2026-05-03"), ("period_end", "2026-10-01")):
            with self.subTest(field=field):
                gate = sec_gate()
                gate["allowed_evidence"][0]["value"][field] = value
                tools = self.tools(gate)
                with self.assertRaisesRegex(ValueError, "SEC_NUMERIC_FRAME_MISMATCH"):
                    tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
                self.assert_no_success(tools)
        gate = sec_gate()
        gate["allowed_evidence"][0]["value"].update(context_type="instant", period_start=None)
        tools = self.tools(gate)
        with self.assertRaisesRegex(ValueError, "SEC_NUMERIC_FRAME_MISMATCH"):
            tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assert_no_success(tools)
        tools = self.tools()
        with self.assertRaisesRegex(ValueError, "SEC_NUMERIC_OPERATION_UNSUPPORTED"):
            tools.calculate(operation="percent_change", evidence_ids=["ev-income", "ev-revenue"])
        self.assert_no_success(tools)
        gate = sec_gate()
        gate["allowed_evidence"][0]["value"]["amount"] = "0"
        tools = self.tools(gate)
        with self.assertRaisesRegex(ValueError, "INVALID_NUMERIC_EVIDENCE"):
            tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assert_no_success(tools)
        self.assertEqual(self.tools().calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])["value"], "0.2")

    def test_non_usd_and_nonmonetary_facts_remain_rejected(self):
        gate = sec_gate()
        gate["allowed_evidence"][0]["value"]["unit"] = "EUR"
        tools = self.tools(gate)
        with self.assertRaisesRegex(ValueError, "SEC_MONETARY_UNIT_INVALID"):
            tools.calculate(operation="monetary_scale", evidence_ids=["ev-revenue"], target_scale="million")
        self.assert_no_success(tools)
        gate = frozen_gate()
        gate["allowed_evidence"][0].update(value="159075", unit="thousands_persons")
        tools = self.tools(gate)
        with self.assertRaisesRegex(ValueError, "MONETARY_MENTION_NOT_FOUND"):
            tools.calculate(operation="monetary_scale", evidence_ids=["ev-revenue"], target_scale="million")
        self.assert_no_success(tools)

    def test_legacy_default_does_not_enable_structured_sec_calculations(self):
        gate = sec_gate()
        tools = EvidenceTools(gate, run_id=gate["run_id"], agent="runtime_company_analyst", invocation_id="legacy")
        for operation, refs, extra, error in (
            ("ratio", ["ev-income", "ev-revenue"], {}, "INVALID_NUMERIC_EVIDENCE"),
            ("monetary_scale", ["ev-income"], {"target_scale": "million"}, "MONETARY_MENTION_NOT_FOUND"),
        ):
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, error):
                tools.calculate(run_id=gate["run_id"], agent="runtime_company_analyst", invocation_id="legacy",
                                calculation_id="legacy", operation=operation, evidence_ids=refs, **extra)
        self.assertEqual(tools.events, [])

    def test_authorization_scope_pit_and_resource_checks_precede_structured_math(self):
        tools = self.tools()
        with self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
            ResearchTools(tools.root, access_token="x"*40).calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        with self.assertRaises(ValueError):
            tools.calculate(operation="ratio", evidence_ids=["ev-other", "ev-revenue"])
        with patch("product.tools.resource_bindings.resource_bindings", return_value={"drift": "0"*64}):
            with self.assertRaisesRegex(ValueError, "RESOURCE_DRIFT"):
                tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assert_no_success(tools)
        gate = sec_gate()
        gate["allowed_evidence"][0]["as_of"] = "2026-10-03T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "PIT_INVALID"):
            self.tools(gate)
        skeptic = self.tools(capability="INDEPENDENT_FIRST_PASS")
        with self.assertRaisesRegex(ValueError, "CALCULATION_FORBIDDEN"):
            skeptic.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assert_no_success(skeptic)

    def test_routed_stdio_refuses_wrong_token_then_preserves_success_and_catalog(self):
        root = Path(self.tmp.name)/"connection"
        prepared = prepare_connection(root, research_input=alb_request(), gate=sec_gate(), role="runtime_company_analyst")
        connection = ResearchConnection(root, connection_token=prepared["connection_token"])
        task = connection.prepare_task(security_id=SECURITY, capability="COMPANY_RESEARCH")
        def message(identifier, name, **arguments):
            return {"jsonrpc": "2.0", "id": identifier, "method": "tools/call", "params": {
                "name": name, "arguments": {"task_ref": task["task_ref"], "task_token": task["task_token"], **arguments}}}
        calls = [message(1, "research_calculate", task_token="x"*40, operation="ratio", evidence_ids=["ev-income", "ev-revenue"]),
                 message(2, "research_calculate", operation="ratio", evidence_ids=["ev-income", "ev-revenue"]),
                 message(3, "research_calculations")]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", STOCK_AGENT_COMPANY_CONNECTION=str(root),
                   STOCK_AGENT_COMPANY_TOKEN=prepared["connection_token"])
        run = subprocess.run([sys.executable, "-B", "-m", "product.mcp.research", "--connection-env-prefix", "STOCK_AGENT_COMPANY"],
                             input="\n".join(json.dumps(m) for m in calls)+"\n", text=True, capture_output=True,
                             env=env, cwd=ROOT, timeout=15, check=True)
        replies = [json.loads(line)["result"] for line in run.stdout.splitlines()]
        self.assertTrue(replies[0]["isError"])
        self.assertFalse(replies[1]["isError"], replies[1])
        self.assertFalse(replies[2]["isError"], replies[2])
        self.assertEqual(json.loads(replies[1]["content"][0]["text"])["value"], "0.2")
        self.assertEqual(len(json.loads(replies[2]["content"][0]["text"])["calculations"]), 1)
        for secret in (task["task_token"], prepared["connection_token"]):
            self.assertNotIn(secret, run.stdout + run.stderr)
        task_root = root/"tasks"/task["task_ref"]
        self.assertEqual(len(list((task_root/"calculations").glob("*.json"))), 1)
        self.assertEqual(len(list((task_root/"tools").glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
