"""原生研究业务边界的零模型测试；不模拟宿主Agent或证明研究内容。"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from product.mcp.research import dispatch, tool_manifest
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.tools.research import ResearchTools, prepare_task
from tests.test_single_stock_input import AT, alb_request

ROOT = Path(__file__).resolve().parents[1]
SECURITY = "US:COMMON_STOCK:ALB"


def frozen_gate():
    facts = [
        {"evidence_id": "ev-revenue", "security_id": SECURITY, "semantic_field": "revenue",
         "value": "100", "unit": "USD", "source_id": "synthetic-sec", "as_of": AT, "retrieved_at": AT},
        {"evidence_id": "ev-income", "security_id": SECURITY, "semantic_field": "net_income",
         "value": "20", "unit": "USD", "source_id": "synthetic-sec", "as_of": AT, "retrieved_at": AT},
        {"evidence_id": "ev-other", "security_id": "US:COMMON_STOCK:OTHER", "semantic_field": "revenue",
         "value": "900", "unit": "USD", "source_id": "synthetic-sec", "as_of": AT, "retrieved_at": AT},
    ]
    value = {"run_id": "native-synthetic", "decision_cutoff": AT,
             "allowed_evidence": facts, "allowed_evidence_ids": [f["evidence_id"] for f in facts],
             "excluded_evidence_ids": ["ev-excluded"]}
    value["bundle_hash"] = legacy_envelope_hash(value, hash_field="bundle_hash")
    return value


class NativeResearchToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)/"research"
        self.input, self.gate = alb_request(), frozen_gate()
        self.input_before = copy.deepcopy(self.input)
        self.gate_before = copy.deepcopy(self.gate)
        self.prepared = prepare_task(self.root, research_input=self.input, gate=self.gate,
                                     security_id=SECURITY, capability="COMPANY_RESEARCH")
        self.tools = ResearchTools(self.root, access_token=self.prepared["access_token"])

    def tearDown(self):
        self.assertEqual(self.input, self.input_before)
        self.assertEqual(self.gate, self.gate_before)
        self.tmp.cleanup()

    def test_prepare_keeps_source_identity_and_does_not_claim_host_execution(self):
        task = self.tools.context()
        self.assertEqual(task["input_binding"]["input_request_hash"], self.input["request_hash"])
        self.assertEqual(task["decision_cutoff"], AT)
        self.assertEqual(task["allowed_evidence_ids"], ["ev-income", "ev-revenue"])
        self.assertEqual(task["caller_authentication"], "UNVERIFIED")
        self.assertEqual(task["host_execution"], "UNVERIFIED")
        self.assertNotIn("access_token", task)
        self.assertNotIn("model", task)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.root.glob("*.json")))

    def test_large_context_pages_all_ids_and_stdio_retains_schema_without_querying_facts(self):
        from product.tools.report_contracts import semantic_schema
        from tests.test_native_research_submission import company_draft
        gate = copy.deepcopy(self.gate)
        for index in range(1396):
            fact = dict(gate["allowed_evidence"][0], evidence_id=f"ev-long-source-period-field-{index:04d}-" + "a"*50)
            gate["allowed_evidence"].append(fact)
            gate["allowed_evidence_ids"].append(fact["evidence_id"])
        gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
        root = Path(self.tmp.name)/"large"
        prepared = prepare_task(root, research_input=self.input, gate=gate,
                                security_id=SECURITY, capability="COMPANY_RESEARCH")
        tools = ResearchTools(root, access_token=prepared["access_token"])
        expected = prepared["task"]["allowed_evidence_ids"]
        self.assertGreater(len(json.dumps(expected)), 100000)
        before = {p.name: p.read_bytes() for p in root.glob("*.json")}
        context = tools.context()
        self.assertEqual(len(context["allowed_evidence_ids"]), 32)
        self.assertEqual(context["allowed_evidence_total"], 1398)
        self.assertEqual(context["next_evidence_offset"], 32)
        self.assertEqual(context["output_schema"], semantic_schema("COMPANY_RESEARCH"))
        self.assertLess(len(json.dumps(context, ensure_ascii=False)), 16384)
        actual, offset = [], 0
        while offset is not None:
            page = tools.context(evidence_offset=offset, evidence_limit=64)
            self.assertEqual(page["evidence_offset"], offset)
            self.assertTrue(page["directory_is_not_evidence_query"])
            actual.extend(page["allowed_evidence_ids"])
            offset = page["next_evidence_offset"]
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual)), 1398)
        self.assertEqual(tools.context(evidence_offset=1398)["allowed_evidence_ids"], [])
        self.assertFalse((root/"tools").exists())
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "research_context", "arguments": {"evidence_limit": 65}}},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                        "name": "research_context", "arguments": {}}},
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                        "name": "research_context", "arguments": {"evidence_offset": 1390, "evidence_limit": 64}}}]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", STOCK_AGENT_RESEARCH_TOKEN=prepared["access_token"])
        run = subprocess.run([sys.executable, "-B", "-m", "product.mcp.research", "--task-root", str(root)],
                             input="\n".join(json.dumps(m) for m in messages)+"\n", text=True,
                             capture_output=True, env=env, cwd=ROOT, timeout=10, check=True)
        replies = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertTrue(replies[1]["result"]["isError"])
        for reply in replies[2:]:
            self.assertFalse(reply["result"]["isError"], reply)
            self.assertLess(len(json.dumps(reply, ensure_ascii=False)), 20000)
            self.assertEqual(json.loads(reply["result"]["content"][0]["text"])["output_schema"], context["output_schema"])
        last = json.loads(replies[-1]["result"]["content"][0]["text"])
        self.assertEqual(last["allowed_evidence_ids"], expected[1390:])
        self.assertIsNone(last["next_evidence_offset"])
        self.assertNotIn(prepared["access_token"], run.stdout + run.stderr)
        self.assertFalse((root/"tools").exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in root.glob("*.json")})
        # Context is only a directory, not a query. Keep this rejected author's two-draft budget separate.
        self.tools.context()
        rejected = self.tools.submit(draft=company_draft())
        self.assertFalse(rejected["accepted"], rejected)
        tools.query(evidence_ids=["ev-revenue"])
        accepted = tools.submit(draft=company_draft())
        self.assertTrue(accepted["accepted"], accepted)
        with self.assertRaises(ValueError):
            tools.query(evidence_ids=["ev-other"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in root.glob("*.json")})

    def test_context_page_parameters_and_every_page_keep_authorization_checks(self):
        from unittest.mock import patch
        for arguments in ({"evidence_offset": -1}, {"evidence_offset": True}, {"evidence_offset": 1.5},
                          {"evidence_limit": 0}, {"evidence_limit": 65}, {"evidence_limit": False}):
            with self.subTest(arguments=arguments), self.assertRaisesRegex(ValueError, "PAGE_INVALID"):
                self.tools.context(**arguments)
        with self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
            ResearchTools(self.root, access_token="x"*40).context(evidence_offset=1)
        with patch("product.tools.resource_bindings.resource_bindings", return_value={"drift": "0"*64}):
            with self.assertRaisesRegex(ValueError, "RESOURCE_DRIFT"):
                self.tools.context(evidence_offset=1)
        self.assertFalse((self.root/"tools").exists())
        self.assertFalse((self.root/"submissions").exists())
        self.assertEqual(self.tools.context(evidence_offset=1)["allowed_evidence_ids"], ["ev-revenue"])

    def test_changed_business_resources_reject_before_query_or_submission_side_effects(self):
        from unittest.mock import patch
        from tests.test_native_research_submission import company_draft
        with patch("product.tools.resource_bindings.resource_bindings", return_value={"drift": "0"*64}):
            with self.assertRaisesRegex(ValueError, "RESOURCE_DRIFT"):
                self.tools.query(evidence_ids=["ev-revenue"])
            with self.assertRaisesRegex(ValueError, "RESOURCE_DRIFT"):
                self.tools.submit(draft=company_draft())
        self.assertFalse((self.root/"tools").exists())
        self.assertFalse((self.root/"submissions").exists())
        self.assertEqual(self.tools.query(evidence_ids=["ev-revenue"])["evidence"][0]["value"], "100")

    def test_invalid_credentials_reject_before_any_query_or_state_write(self):
        for token in (None, "", "wrong-token"):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
                ResearchTools(self.root, access_token=token).query(evidence_ids=["ev-revenue"])
        self.assertFalse((self.root/"tools").exists())
        self.assertEqual(self.tools.query(evidence_ids=["ev-revenue"])["evidence"][0]["value"], "100")

    def test_other_task_credentials_cannot_access_valid_target(self):
        other = prepare_task(Path(self.tmp.name)/"other", research_input=self.input, gate=self.gate,
                             security_id=SECURITY, capability="INDEPENDENT_FIRST_PASS")
        with self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
            ResearchTools(self.root, access_token=other["access_token"]).query(evidence_ids=["ev-revenue"])
        self.assertFalse((self.root/"tools").exists())

    def test_catalog_is_metadata_not_query_and_no_other_security(self):
        result = self.tools.catalog(limit=1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["next_offset"], 1)
        self.assertTrue(result["directory_is_not_evidence_query"])
        self.assertNotIn("value", result["records"][0])
        self.assertFalse((self.root/"tools").exists())
        with self.assertRaises(ValueError):
            self.tools.catalog(offset=True)

    def test_query_preserves_provenance_and_records_actual_ids(self):
        result = self.tools.query(evidence_ids=["ev-revenue"])
        self.assertEqual(result["evidence"][0], self.gate["allowed_evidence"][0])
        event = json.loads(next((self.root/"tools").glob("*.json")).read_text())
        self.assertEqual(event["evidence_ids"], ["ev-revenue"])
        self.assertEqual(event["output_hash"], canonical_hash(result))
        self.assertNotIn(self.prepared["access_token"], json.dumps(event))

    def test_unknown_excluded_and_other_security_fail_without_read_event(self):
        for ref in ("unknown", "ev-excluded", "ev-other"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                self.tools.query(evidence_ids=[ref])
        self.assertFalse((self.root/"tools").exists())

    def test_calculation_reuses_existing_method_and_preserves_order(self):
        result = self.tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assertEqual(result["value"], "0.2")
        self.assertEqual(result["evidence_ids"], ["ev-income", "ev-revenue"])
        saved = json.loads(next((self.root/"calculations").glob("*.json")).read_text())
        self.assertEqual(saved, result)
        with self.assertRaises(ValueError):
            self.tools.calculate(operation="arbitrary_expression", evidence_ids=["ev-income", "ev-revenue"])

    def test_skeptic_scope_contains_no_positive_reports_or_math(self):
        root = Path(self.tmp.name)/"skeptic"
        prepared = prepare_task(root, research_input=self.input, gate=self.gate,
                                security_id=SECURITY, capability="INDEPENDENT_FIRST_PASS")
        tools = ResearchTools(root, access_token=prepared["access_token"])
        context = tools.context()
        for forbidden in ("dependency_reports", "thesis", "bundle", "portfolio", "cash", "quantity"):
            self.assertNotIn(forbidden, context)
        with self.assertRaisesRegex(ValueError, "CALCULATION_FORBIDDEN"):
            tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])

    def test_tampered_gate_and_future_facts_reject(self):
        path = self.root/"gate.json"
        value = json.loads(path.read_text())
        value["allowed_evidence"][0]["value"] = "999"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "GATE_HASH_INVALID"):
            self.tools.query(evidence_ids=["ev-revenue"])
        bad = frozen_gate()
        bad["allowed_evidence"][0]["as_of"] = "2026-10-03T00:00:00Z"
        bad["allowed_evidence"][0]["retrieved_at"] = "2026-10-03T00:00:00Z"
        bad["bundle_hash"] = legacy_envelope_hash(bad, hash_field="bundle_hash")
        rejected = Path(self.tmp.name)/"future"
        with self.assertRaisesRegex(ValueError, "PIT_INVALID"):
            prepare_task(rejected, research_input=self.input, gate=bad,
                         security_id=SECURITY, capability="COMPANY_RESEARCH")
        self.assertFalse(rejected.exists())

    def test_task_hash_or_input_drift_rejected(self):
        path = self.root/"task.json"
        value = json.loads(path.read_text())
        value["allowed_evidence_ids"].append("ev-other")
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "TASK_BINDING_INVALID"):
            self.tools.query(evidence_ids=["ev-other"])

    def test_rehash_cannot_expand_authorized_task_scope(self):
        path = self.root/"task.json"
        value = json.loads(path.read_text())
        value["allowed_evidence_ids"].append("ev-other")
        value["task_hash"] = canonical_hash({k: v for k, v in value.items() if k != "task_hash"})
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "TASK_BINDING_INVALID"):
            self.tools.query(evidence_ids=["ev-other"])
        self.assertFalse((self.root/"tools").exists())

    def test_malformed_rpc_does_not_access_business_data(self):
        for value in ([], {"id": 1}, {"jsonrpc": "2.0", "id": 1, "params": []}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "RPC_INVALID"):
                dispatch(self.tools, value)
        self.assertFalse((self.root/"tools").exists())

    def test_output_in_source_and_symlink_rejected(self):
        for root in (ROOT/"native-not-allowed",):
            with self.assertRaisesRegex(ValueError, "MUST_BE_EXTERNAL"):
                prepare_task(root, research_input=self.input, gate=self.gate,
                             security_id=SECURITY, capability="COMPANY_RESEARCH")
        link = Path(self.tmp.name)/"linked"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "PATH_UNSAFE"):
            ResearchTools(link, access_token=self.prepared["access_token"])

    def test_transport_schema_does_not_accept_self_authored_identity(self):
        response = dispatch(self.tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                        "params": {"name": "research_query", "arguments": {
                                            "evidence_ids": ["ev-revenue"], "agent": "runtime_cio"}}})
        self.assertTrue(response["result"]["isError"])
        self.assertFalse((self.root/"tools").exists())
        self.assertTrue(all("run_id" not in t["inputSchema"]["properties"] for t in tool_manifest()))

    def test_actual_stdio_queries_and_error_then_valid_request(self):
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "research_query", "arguments": {"evidence_ids": ["ev-other"]}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "research_query", "arguments": {"evidence_ids": ["ev-revenue"]}}},
        ]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", STOCK_AGENT_RESEARCH_TOKEN=self.prepared["access_token"])
        result = subprocess.run([sys.executable, "-B", "-m", "product.mcp.research", "--task-root", str(self.root)],
                                input="\n".join(json.dumps(m) for m in messages)+"\n", text=True,
                                capture_output=True, env=env, cwd=ROOT, timeout=10, check=True)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4])
        self.assertTrue(replies[2]["result"]["isError"])
        self.assertFalse(replies[3]["result"]["isError"])
        self.assertNotIn(self.prepared["access_token"], result.stdout + result.stderr)
