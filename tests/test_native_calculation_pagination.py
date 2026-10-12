"""真实统计任务的有界目录/精确血缘页；不启动宿主或模型。"""
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
from product.mcp.research import dispatch, routed_tool_manifest, tool_manifest
from product.runtime.hashing import canonical_hash, canonical_json, legacy_envelope_hash
from product.runtime.schema_validation import validate_schema_instance
from product.tools.report_submission import calculation_catalog, queried_evidence
from product.tools.research import MAX_QUERY_BYTES, ResearchTools, prepare_task
from product.tools.research_connection import ResearchConnection, prepare_connection
from product.tools.report_contracts import semantic_schema
from tests.test_native_query_pagination import encoded_size
from tests.test_native_research_reading import complete_gate
from tests.test_native_research_tools import ROOT, SECURITY, frozen_gate
from tests.test_multidimensional_research_contracts import _report
from tests.test_single_stock_input import alb_request


def statistics_gate():
    gate = complete_gate()
    for fact in gate["allowed_evidence"]:
        if fact["evidence_id"].startswith("series-"):
            fact["evidence_id"] += "-long-lineage-" * 90
    gate["allowed_evidence_ids"] = [fact["evidence_id"] for fact in gate["allowed_evidence"]]
    gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
    return gate


def technical_draft(ref):
    old = _report(capability="TECHNICAL_STRUCTURE")
    fields = semantic_schema("TECHNICAL_STRUCTURE")["properties"]
    draft = {key: copy.deepcopy(value) for key, value in old.items() if key in fields}
    draft["calculation_selections"] = [{"calculation_ref": ref, "claim_ids": [draft["claims"][0]["claim_id"]]}]
    draft["document_selections"] = []
    for claim in draft["claims"]:
        claim.pop("calculation_refs", None)
        claim["evidence_refs"] = []
    for condition in draft["observation_conditions"]:
        condition["evidence_refs"] = []
    return draft


class NativeCalculationPaginationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.base = Path(self.tmp.name)
        self.gate = statistics_gate()
        self.prepared = prepare_task(self.base/"task", research_input=alb_request(), gate=self.gate,
                                     security_id=SECURITY, capability="TECHNICAL_STRUCTURE", benchmark_id="US:SPY")
        self.tools = ResearchTools(self.base/"task", access_token=self.prepared["access_token"])

    def tearDown(self):
        self.tmp.cleanup()

    def files(self):
        return {str(p.relative_to(self.tools.root)): p.read_bytes() for p in self.tools.root.rglob("*") if p.is_file()}

    def test_large_default_compacts_without_mutating_full_catalog_or_querying_raw_facts(self):
        before = self.files()
        catalog = calculation_catalog(self.tools)
        self.assertGreater(encoded_size({"calculations": list(catalog.values())}), 3_000_000)
        page = self.tools.calculations()
        self.assertLessEqual(encoded_size(page), MAX_QUERY_BYTES)
        self.assertEqual(page["mode"], "CATALOG")
        self.assertEqual(page["total"], len(catalog))
        self.assertTrue(page["directory_is_not_evidence_query"])
        self.assertTrue(all(page[key] for key in ("source_id", "as_of", "retrieved_at")))
        for item in page["calculations"]:
            original = catalog[item["calculation_ref"]]
            refs = original["calculation"]["input_evidence_refs"]
            self.assertEqual(item["receipt_hash"], original["receipt_hash"])
            self.assertEqual(item["calculation"], {k: v for k, v in original["calculation"].items() if k != "input_evidence_refs"})
            self.assertEqual(item["input_evidence_total"], len(refs))
            self.assertEqual(item["input_evidence_hash"], canonical_hash(refs))
            self.assertFalse(item["input_evidence_complete"])
        self.assertEqual(self.tools.context()["allowed_evidence_total"], 0)
        self.assertEqual(queried_evidence(self.tools), set())
        self.assertEqual(self.files(), before)
        self.assertEqual(calculation_catalog(self.tools), catalog)

    def test_explicit_directory_pages_preserve_all_exact_references_in_order(self):
        expected = list(calculation_catalog(self.tools))
        actual, offset = [], 0
        while True:
            page = self.tools.calculations(offset=offset, limit=3)
            self.assertEqual(page["offset"], offset)
            self.assertLessEqual(encoded_size(page), MAX_QUERY_BYTES)
            actual.extend(item["calculation_ref"] for item in page["calculations"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual)), len(actual))

    def test_exact_lineage_pages_restore_complete_original_ids_and_hash(self):
        ref, entry = next(iter(calculation_catalog(self.tools).items()))
        expected = entry["calculation"]["input_evidence_refs"]
        actual, offset = [], 0
        before = self.files()
        while True:
            page = self.tools.calculations(calculation_ref=ref, evidence_offset=offset, evidence_limit=64)
            self.assertEqual(page["mode"], "INPUT_LINEAGE")
            self.assertLessEqual(encoded_size(page), MAX_QUERY_BYTES)
            item = page["calculations"][0]
            self.assertEqual(item["calculation_ref"], ref)
            self.assertEqual(item["input_evidence_hash"], canonical_hash(expected))
            self.assertEqual(item["evidence_offset"], offset)
            actual.extend(item["calculation"]["input_evidence_refs"])
            if item["next_evidence_offset"] is None:
                break
            self.assertGreater(item["next_evidence_offset"], offset)
            offset = item["next_evidence_offset"]
        self.assertEqual(actual, expected)
        self.assertEqual(canonical_hash(actual), canonical_hash(expected))
        self.assertEqual(self.files(), before)
        self.assertEqual(queried_evidence(self.tools), set())

    def test_directory_choice_submission_expands_trusted_full_lineage_not_projection(self):
        page = self.tools.calculations(offset=0, limit=1)
        ref = page["calculations"][0]["calculation_ref"]
        expected = calculation_catalog(self.tools)[ref]
        result = self.tools.submit(draft=technical_draft(ref))
        self.assertTrue(result["accepted"], result)
        report = self.tools.read_submission(draft_ref=result["draft_ref"])
        self.assertEqual(report["calculation_support"], [expected])
        self.assertEqual(report["research"]["calculations"], [expected["calculation"]])
        self.assertEqual(report["host_execution"], "UNVERIFIED")
        self.assertEqual(report["content_verdict"], "NOT_REVIEWED")
        self.assertNotIn("input_evidence_hash", report["calculation_support"][0])

    def test_small_implicit_legacy_response_is_unchanged_and_empty_directory_is_legal(self):
        grant = prepare_task(self.base/"company", research_input=alb_request(), gate=frozen_gate(),
                             security_id=SECURITY, capability="COMPANY_RESEARCH")
        tools = ResearchTools(self.base/"company", access_token=grant["access_token"])
        self.assertEqual(tools.calculations(), {"calculations": []})
        page = tools.calculations(offset=0, limit=1)
        self.assertEqual(page["total"], 0)
        self.assertIsNone(page["next_offset"])
        tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        self.assertEqual(tools.calculations(), {"calculations": list(calculation_catalog(tools).values())})

    def test_invalid_pages_modes_and_unknown_reference_have_no_writes(self):
        ref = next(iter(calculation_catalog(self.tools)))
        cases = [{"offset": x} for x in (-1, True, 999, None, 1.5)]
        cases += [{"limit": x} for x in (0, 65, False, None, 1.5)]
        cases += [{"calculation_ref": ref, "evidence_offset": x} for x in (-1, True, 999, None)]
        cases += [{"calculation_ref": ref, "evidence_limit": x} for x in (0, 65, False, None)]
        cases += [{"evidence_offset": 0}, {"evidence_limit": 32}, {"calculation_ref": ref, "offset": 0},
                  {"calculation_ref": ref, "limit": 1}, {"calculation_ref": None},
                  {"calculation_ref": "k."+"a"*12+"."+"b"*24}]
        before = self.files()
        for args in cases:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.tools.calculations(**args)
            self.assertEqual(self.files(), before)

    def test_mcp_nullable_calculation_modes_survive_strict_required_projection(self):
        schema = next(item["inputSchema"] for item in tool_manifest() if item["name"] == "research_calculations")
        self.assertEqual(schema["required"], [])
        strict = copy.deepcopy(schema)
        strict["required"] = list(strict["properties"])
        ref = next(iter(calculation_catalog(self.tools)))
        empty = dict.fromkeys(strict["required"])
        cases = (empty, {**empty, "offset": 0, "limit": 2},
                 {**empty, "calculation_ref": ref, "evidence_offset": 0, "evidence_limit": 2})
        before = self.files()
        with patch("product.tools.research._utc_now", return_value="2026-10-11T04:07:29Z"):
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    original = copy.deepcopy(arguments)
                    validate_schema_instance(arguments, schema)
                    validate_schema_instance(arguments, strict)
                    expected = self.tools.calculations(**{key: value for key, value in arguments.items() if value is not None})
                    response = dispatch(self.tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                        "name": "research_calculations", "arguments": arguments}})
                    self.assertFalse(response["result"]["isError"], response)
                    actual = json.loads(response["result"]["content"][0]["text"])
                    self.assertEqual(actual, expected)
                    self.assertLessEqual(encoded_size(actual), MAX_QUERY_BYTES)
                    self.assertEqual(arguments, original)
        actual, offset = [], 0
        while True:
            arguments = {**empty, "offset": offset, "limit": 3}
            validate_schema_instance(arguments, strict)
            response = dispatch(self.tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_calculations", "arguments": arguments}})
            self.assertFalse(response["result"]["isError"], response)
            page = json.loads(response["result"]["content"][0]["text"])
            actual.extend(item["calculation_ref"] for item in page["calculations"])
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        self.assertEqual(actual, list(calculation_catalog(self.tools)))
        actual, offset = [], 0
        expected = calculation_catalog(self.tools)[ref]["calculation"]["input_evidence_refs"]
        while True:
            arguments = {**empty, "calculation_ref": ref, "evidence_offset": offset, "evidence_limit": 64}
            validate_schema_instance(arguments, strict)
            response = dispatch(self.tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_calculations", "arguments": arguments}})
            self.assertFalse(response["result"]["isError"], response)
            page = json.loads(response["result"]["content"][0]["text"])
            item = page["calculations"][0]
            self.assertEqual(item["input_evidence_hash"], canonical_hash(expected))
            self.assertLessEqual(encoded_size(page), MAX_QUERY_BYTES)
            actual.extend(item["calculation"]["input_evidence_refs"])
            if item["next_evidence_offset"] is None:
                break
            offset = item["next_evidence_offset"]
        self.assertEqual(actual, expected)
        self.assertEqual(self.files(), before)
        self.assertEqual(queried_evidence(self.tools), set())

    def test_mcp_nullable_calculations_preserve_authorization_modes_and_resource_checks(self):
        root = self.base/"nullable-connection"
        prepared = prepare_connection(root, research_input=alb_request(), gate=self.gate, role="runtime_market_catalyst")
        connection = ResearchConnection(root, connection_token=prepared["connection_token"])
        grant = connection.prepare_task(security_id=SECURITY, capability="TECHNICAL_STRUCTURE", benchmark_id="US:SPY")
        tools = connection.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
        ref = next(iter(calculation_catalog(tools)))
        other = connection.prepare_task(security_id=SECURITY, capability="TECHNICAL_STRUCTURE", benchmark_id="US:SPY")
        foreign = next(iter(calculation_catalog(connection.task_tools(task_ref=other["task_ref"], task_token=other["task_token"]))))
        arguments = {"task_ref": grant["task_ref"], "task_token": grant["task_token"],
                     "offset": None, "limit": None, "calculation_ref": None,
                     "evidence_offset": None, "evidence_limit": None}
        before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}

        def call(values):
            return dispatch(connection, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_calculations", "arguments": values}})

        cases = [({"offset": True}, "SCHEMA_TYPE_INVALID"), ({"offset": -1}, "SCHEMA_MINIMUM"),
                 ({"offset": 10**9}, "NATIVE_RESEARCH_PAGE_INVALID"), ({"limit": 1.5}, "SCHEMA_TYPE_INVALID"),
                 ({"limit": 65}, "SCHEMA_MAXIMUM"), ({"evidence_offset": False}, "SCHEMA_TYPE_INVALID"),
                 ({"evidence_limit": 0}, "SCHEMA_MINIMUM"), ({"calculation_ref": "bad"}, "SCHEMA_PATTERN_INVALID"),
                 ({"offset": 0, "limit": 1, "calculation_ref": ref, "evidence_offset": 0, "evidence_limit": 1},
                  "NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID"),
                 ({"calculation_ref": "k."+"a"*12+"."+"b"*24}, "NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID"),
                 ({"offset": 0, "calculation_ref": ref}, "NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID"),
                 ({"limit": 1, "calculation_ref": ref}, "NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID"),
                 ({"evidence_offset": 0}, "NATIVE_RESEARCH_PAGE_INVALID"),
                 ({"calculation_ref": foreign}, "NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID"),
                 ({"task_ref": None}, "SCHEMA_TYPE_INVALID"), ({"task_token": None}, "SCHEMA_TYPE_INVALID"),
                 ({"task_token": "x"*43}, "NATIVE_RESEARCH_ACCESS_INVALID"),
                 ({"task_ref": other["task_ref"]}, "NATIVE_RESEARCH_ACCESS_INVALID"),
                 ({"unknown": None}, "SCHEMA_EXTRA_PROPERTY")]
        for changes, code in cases:
            with self.subTest(changes=changes):
                response = call({**arguments, **changes})
                self.assertTrue(response["result"]["isError"], response)
                self.assertEqual(response["result"]["content"][0]["text"], code)
                self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()})
        for key in ("task_ref", "task_token"):
            missing = {name: value for name, value in arguments.items() if name != key}
            response = call(missing)
            self.assertTrue(response["result"]["isError"])
            self.assertEqual(response["result"]["content"][0]["text"], "SCHEMA_REQUIRED_MISSING")
        response = dispatch(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "research_catalog", "arguments": {"offset": None}}})
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(response["result"]["content"][0]["text"], "SCHEMA_TYPE_INVALID")
        from product.tools.resource_bindings import resource_bindings
        resources = resource_bindings("TECHNICAL_STRUCTURE", "runtime_market_catalyst")
        with patch("product.tools.resource_bindings.resource_bindings", return_value={**resources, "mcp/research.py": "a"*64}):
            response = call(arguments)
            self.assertTrue(response["result"]["isError"], response)
            self.assertEqual(response["result"]["content"][0]["text"], "NATIVE_RESEARCH_RESOURCE_DRIFT")
        self.assertFalse(call(arguments)["result"]["isError"])
        self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()})
        self.assertEqual(queried_evidence(tools), set())
        for secret in (grant["task_token"], other["task_token"], prepared["connection_token"]):
            self.assertNotIn(secret, json.dumps(response))

    def test_wrong_credentials_skeptic_and_cross_task_ref_are_rejected(self):
        before = self.files()
        with self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
            ResearchTools(self.tools.root, access_token="x"*43).calculations(offset=0)
        for capability in ("TECHNICAL_STRUCTURE", "INDEPENDENT_FIRST_PASS"):
            path = self.base/capability
            prepared = prepare_task(path, research_input=alb_request(), gate=self.gate,
                                    security_id=SECURITY, capability=capability, benchmark_id="US:SPY")
            other = ResearchTools(path, access_token=prepared["access_token"])
            with self.assertRaisesRegex(ValueError, "CALCULATION_SELECTION_INVALID|CALCULATION_FORBIDDEN"):
                other.calculations(calculation_ref=next(iter(calculation_catalog(self.tools))))
            response = dispatch(other, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_calculations", "arguments": {
                    "offset": None, "limit": None, "calculation_ref": next(iter(calculation_catalog(self.tools))),
                    "evidence_offset": None, "evidence_limit": None}}})
            self.assertTrue(response["result"]["isError"], response)
            expected = "NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID" if capability == "TECHNICAL_STRUCTURE" else "NATIVE_RESEARCH_CALCULATION_FORBIDDEN"
            self.assertEqual(response["result"]["content"][0]["text"], expected)
            self.assertFalse((path/"tools").exists())
        self.assertEqual(self.files(), before)

    def test_precomputed_disk_drift_rejected_on_every_page(self):
        ref = next(iter(calculation_catalog(self.tools)))
        self.tools.calculations(calculation_ref=ref, evidence_offset=0, evidence_limit=1)
        path = next((self.tools.root/"precomputed").glob("*.json"))
        original = path.read_bytes()
        value = json.loads(original)
        value["evidence_fact_ids"] = []
        path.write_text(json.dumps(value))
        before = self.files()
        for args in ({"offset": 0}, {"calculation_ref": ref, "evidence_offset": 1}):
            with self.assertRaisesRegex(ValueError, "PRECOMPUTED_FILE_DRIFT"):
                self.tools.calculations(**args)
            self.assertEqual(self.files(), before)
        path.write_bytes(original)
        self.assertTrue(self.tools.calculations()["calculations"])

    def test_resource_drift_rejected_before_return_and_recovered(self):
        from product.tools.resource_bindings import resource_bindings
        original = resource_bindings("TECHNICAL_STRUCTURE", "runtime_market_catalyst")
        before = self.files()
        with patch("product.tools.resource_bindings.resource_bindings", return_value={**original, "synthetic-drift": "a"*64}):
            with self.assertRaisesRegex(ValueError, "RESOURCE_DRIFT"):
                self.tools.calculations(offset=0)
        self.assertEqual(self.files(), before)
        self.assertTrue(self.tools.calculations()["calculations"])

    def test_utf8_complete_page_budget_and_single_entry_overflow_reject_without_writes(self):
        ref = next(iter(calculation_catalog(self.tools)))
        before = self.files()
        with patch("product.tools.research._utc_now", return_value="2026-10-08T10:00:00Z"):
            size = encoded_size(self.tools.calculations(calculation_ref=ref, evidence_limit=1))
            with patch("product.tools.research.MAX_QUERY_BYTES", size):
                page = self.tools.calculations(calculation_ref=ref, evidence_limit=64)
                self.assertEqual(encoded_size(page), size)
                self.assertEqual(len(page["calculations"][0]["calculation"]["input_evidence_refs"]), 1)
            with patch("product.tools.research.MAX_QUERY_BYTES", size - 1):
                with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
                    self.tools.calculations(calculation_ref=ref, evidence_limit=1)
        with patch("product.tools.research.MAX_QUERY_BYTES", 100):
            for args in ({"offset": 0}, {"calculation_ref": ref}):
                with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
                    self.tools.calculations(**args)
        self.assertEqual(self.files(), before)

    def test_report_mcp_pages_restore_exact_large_report_and_leave_internal_readers_full(self):
        connection_root = self.base/"report-connection"
        prepared = prepare_connection(connection_root, research_input=alb_request(), gate=self.gate,
                                      role="runtime_market_catalyst")
        connection = ResearchConnection(connection_root, connection_token=prepared["connection_token"])
        grant = connection.prepare_task(security_id=SECURITY, capability="TECHNICAL_STRUCTURE", benchmark_id="US:SPY")
        tools = connection.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
        ref = next(iter(calculation_catalog(tools)))
        saved = tools.submit(draft=technical_draft(ref))
        self.assertTrue(saved["accepted"], saved)
        full = tools.read_submission(draft_ref=saved["draft_ref"])
        payload = canonical_json(full)
        self.assertGreater(encoded_size(full), MAX_QUERY_BYTES)
        before = {str(p.relative_to(connection_root)): p.read_bytes() for p in connection_root.rglob("*") if p.is_file()}
        messages = [{"jsonrpc": "2.0", "id": 0, "method": "tools/list"}]
        for offset in range(0, len(payload), 8192):
            arguments = {"task_ref": grant["task_ref"], "task_token": grant["task_token"], "draft_ref": saved["draft_ref"]}
            if offset:
                arguments["offset"] = offset
            messages.append({"jsonrpc": "2.0", "id": len(messages), "method": "tools/call", "params": {
                "name": "research_read_submission", "arguments": arguments}})
        prefix = "STOCK_AGENT_MARKET"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env[prefix+"_CONNECTION"], env[prefix+"_TOKEN"] = str(connection_root), prepared["connection_token"]
        run = subprocess.run([sys.executable, "-B", "-m", "product.mcp.research", "--connection-env-prefix", prefix],
            cwd=ROOT, env=env, input="".join(json.dumps(m)+"\n" for m in messages), text=True,
            capture_output=True, timeout=60, check=True)
        replies = [json.loads(line) for line in run.stdout.splitlines()]
        manifest = next(item for item in replies[0]["result"]["tools"] if item["name"] == "research_read_submission")
        self.assertEqual(manifest["inputSchema"]["properties"]["limit"]["maximum"], 8192)
        fragments = []
        for index, reply in enumerate(replies[1:]):
            self.assertFalse(reply["result"]["isError"])
            text = reply["result"]["content"][0]["text"]
            self.assertLessEqual(len(text.encode("utf-8")), MAX_QUERY_BYTES)
            page = json.loads(text)
            self.assertEqual(page["mode"], "REPORT_JSON_PAGE")
            self.assertEqual(page["offset"], index*8192)
            self.assertEqual(page["total"], len(payload))
            self.assertEqual(page["next_offset"], (index+1)*8192 if (index+1)*8192 < len(payload) else None)
            self.assertEqual(page["offset_unit"], "UNICODE_CODE_POINT")
            self.assertFalse(page["report_complete"])
            self.assertEqual(page["draft_ref"], saved["draft_ref"])
            self.assertEqual(page["payload_hash"], canonical_hash(full))
            for key in ("report_id", "report_hash", "source_id", "as_of", "retrieved_at"):
                self.assertEqual(page[key], full[key])
            fragments.append(page["report_json_fragment"])
        self.assertEqual("".join(fragments), payload)
        self.assertEqual(json.loads("".join(fragments)), full)
        self.assertEqual(tools.read_submission(draft_ref=saved["draft_ref"]), full)
        self.assertEqual(before, {str(p.relative_to(connection_root)): p.read_bytes() for p in connection_root.rglob("*") if p.is_file()})
        for secret in (grant["task_token"], prepared["connection_token"]):
            self.assertNotIn(secret, run.stdout+run.stderr)

    def test_report_small_implicit_format_and_explicit_unicode_pages_budget(self):
        grant = prepare_task(self.base/"small-report", research_input=alb_request(), gate=complete_gate(),
                             security_id=SECURITY, capability="TECHNICAL_STRUCTURE", benchmark_id="US:SPY")
        tools = ResearchTools(self.base/"small-report", access_token=grant["access_token"])
        draft = technical_draft(next(iter(calculation_catalog(tools))))
        draft["summary"] = "合成量价🙂\n\"反证\""*50
        saved = tools.submit(draft=draft)
        self.assertTrue(saved["accepted"], saved)
        full = tools.read_submission(draft_ref=saved["draft_ref"])
        self.assertLessEqual(encoded_size(full), MAX_QUERY_BYTES)
        self.assertEqual(tools.read_submission_page(draft_ref=saved["draft_ref"]), full)
        response = dispatch(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "research_read_submission", "arguments": {"draft_ref": saved["draft_ref"]}}})
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), full)
        payload = canonical_json(full)
        offset = payload.index("合成量价")
        page = tools.read_submission_page(draft_ref=saved["draft_ref"], offset=offset, limit=17)
        self.assertEqual(page["report_json_fragment"], payload[offset:offset+17])
        size = encoded_size(page)
        self.assertGreater(size, len(json.dumps(page, ensure_ascii=False, allow_nan=False)))
        with patch("product.tools.research.MAX_QUERY_BYTES", size):
            self.assertEqual(tools.read_submission_page(draft_ref=saved["draft_ref"], offset=offset, limit=17), page)
        with patch("product.tools.research.MAX_QUERY_BYTES", size-1):
            with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
                tools.read_submission_page(draft_ref=saved["draft_ref"], offset=offset, limit=17)
        one = tools.read_submission_page(draft_ref=saved["draft_ref"], offset=0, limit=1)
        self.assertEqual(one["report_json_fragment"], "{")
        self.assertFalse(one["report_complete"])

    def test_report_page_invalid_parameters_wrong_credentials_and_drift_have_no_writes(self):
        saved = self.tools.submit(draft=technical_draft(next(iter(calculation_catalog(self.tools)))))
        self.assertTrue(saved["accepted"], saved)
        receipt = saved["draft_ref"]
        before = self.files()
        cases = [{"offset": x} for x in (-1, True, 10**9, None, 1.5)]
        cases += [{"limit": x} for x in (0, 8193, False, None, 1.5)]
        for args in cases:
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, "PAGE_INVALID"):
                self.tools.read_submission_page(draft_ref=receipt, **args)
            response = dispatch(self.tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_read_submission", "arguments": {"draft_ref": receipt, **args}}})
            self.assertTrue(response["result"]["isError"])
            self.assertEqual(self.files(), before)
        other_grant = prepare_task(self.base/"foreign-report", research_input=alb_request(), gate=self.gate,
                                   security_id=SECURITY, capability="TECHNICAL_STRUCTURE", benchmark_id="US:SPY")
        other = ResearchTools(self.base/"foreign-report", access_token=other_grant["access_token"])
        foreign = other.submit(draft=technical_draft(next(iter(calculation_catalog(other)))))
        self.assertTrue(foreign["accepted"], foreign)
        with self.assertRaisesRegex(ValueError, "RECEIPT_BINDING_INVALID"):
            self.tools.read_submission_page(draft_ref=foreign["draft_ref"])
        self.assertEqual(self.files(), before)
        wrong = ResearchTools(self.tools.root, access_token="x"*43)
        with self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
            wrong.read_submission_page(draft_ref=receipt)
        with self.assertRaisesRegex(ValueError, "RECEIPT_BINDING_INVALID"):
            self.tools.read_submission_page(draft_ref=receipt[:-1]+("A" if receipt[-1] != "A" else "B"))
        record_path = self.tools.root/"submissions/1.json"
        record = json.loads(record_path.read_bytes())
        record["report"]["research"]["summary"] += "drift"
        record["content_hash"] = canonical_hash({k: v for k, v in record.items() if k != "content_hash"})
        record_path.write_text(json.dumps(record))
        drifted = self.files()
        with self.assertRaisesRegex(ValueError, "REPORT_HASH_INVALID"):
            self.tools.read_submission_page(draft_ref=receipt, offset=1)
        self.assertEqual(self.files(), drifted)
        record_path.write_bytes(before["submissions/1.json"])
        from product.tools.resource_bindings import resource_bindings
        original = resource_bindings("TECHNICAL_STRUCTURE", "runtime_market_catalyst")
        with patch("product.tools.resource_bindings.resource_bindings", return_value={**original, "drift": "a"*64}):
            with self.assertRaisesRegex(ValueError, "RESOURCE_DRIFT"):
                self.tools.read_submission_page(draft_ref=receipt, offset=1)
        self.assertEqual(self.files(), before)
        self.assertTrue(self.tools.read_submission_page(draft_ref=receipt)["report_json_fragment"])

    def test_calculation_and_report_pages_revalidate_gate_pit_input_and_task(self):
        ref = next(iter(calculation_catalog(self.tools)))
        saved = self.tools.submit(draft=technical_draft(ref))
        self.assertTrue(saved["accepted"], saved)
        calls = (lambda: self.tools.calculations(calculation_ref=ref, evidence_offset=1),
                 lambda: self.tools.read_submission_page(draft_ref=saved["draft_ref"], offset=1))
        for name, code in (("gate.json", "PIT_INVALID"), ("input.json", "INPUT_BINDING_INVALID"),
                           ("task.json", "TASK_BINDING_INVALID")):
            path = self.tools.root/name
            original = path.read_bytes()
            value = json.loads(original)
            if name == "gate.json":
                value["allowed_evidence"][0]["as_of"] = "2027-01-01T00:00:00Z"
                value["bundle_hash"] = legacy_envelope_hash(value, hash_field="bundle_hash")
            else:
                value["research_question"] += " drift"
                if name == "input.json":
                    value["request_hash"] = content_hash({k: v for k, v in value.items() if k != "request_hash"})
            path.write_text(json.dumps(value))
            before = self.files()
            for call in calls:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, code):
                    call()
                self.assertEqual(self.files(), before)
            path.write_bytes(original)
        self.assertTrue(self.tools.calculations()["calculations"])
        self.assertTrue(self.tools.read_submission_page(draft_ref=saved["draft_ref"])["report_json_fragment"])

    def test_real_routed_stdio_catalog_and_exact_lineage_schema(self):
        connection_root = self.base/"market-connection"
        prepared = prepare_connection(connection_root, research_input=alb_request(), gate=self.gate,
                                      role="runtime_market_catalyst")
        connection = ResearchConnection(connection_root, connection_token=prepared["connection_token"])
        grant = connection.prepare_task(security_id=SECURITY, capability="TECHNICAL_STRUCTURE", benchmark_id="US:SPY")
        tools = connection.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
        ref = next(iter(calculation_catalog(tools)))
        nullable = {"offset": None, "limit": None, "calculation_ref": None, "evidence_offset": None, "evidence_limit": None}
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]
        for number, args in enumerate(({"offset": 0, "limit": 2},
                                       {"calculation_ref": ref, "evidence_offset": 0, "evidence_limit": 2},
                                       {**nullable, "offset": 0, "limit": 2},
                                       {**nullable, "calculation_ref": ref, "evidence_offset": 0, "evidence_limit": 2},
                                       nullable, {"offset": True}), 2):
            messages.append({"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": {
                "name": "research_calculations", "arguments": {"task_ref": grant["task_ref"],
                    "task_token": grant["task_token"], **args}}})
        prefix = "STOCK_AGENT_MARKET"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        env[prefix+"_CONNECTION"], env[prefix+"_TOKEN"] = str(connection_root), prepared["connection_token"]
        run = subprocess.run([sys.executable, "-B", "-m", "product.mcp.research", "--connection-env-prefix", prefix],
            cwd=ROOT, env=env, input="".join(json.dumps(m)+"\n" for m in messages), text=True,
            capture_output=True, timeout=30, check=True)
        replies = [json.loads(line) for line in run.stdout.splitlines()]
        manifest = next(item for item in replies[0]["result"]["tools"] if item["name"] == "research_calculations")
        self.assertEqual(manifest["inputSchema"], next(item for item in routed_tool_manifest() if item["name"] == "research_calculations")["inputSchema"])
        self.assertEqual(manifest["inputSchema"]["required"], ["task_ref", "task_token"])
        strict = copy.deepcopy(manifest["inputSchema"])
        strict["required"] = list(strict["properties"])
        for message in messages[3:6]:
            validate_schema_instance(message["params"]["arguments"], strict)
        for reply, mode in zip(replies[1:6], ("CATALOG", "INPUT_LINEAGE", "CATALOG", "INPUT_LINEAGE", "CATALOG")):
            self.assertFalse(reply["result"]["isError"], reply)
            self.assertLessEqual(len(reply["result"]["content"][0]["text"].encode()), MAX_QUERY_BYTES)
            self.assertEqual(json.loads(reply["result"]["content"][0]["text"])["mode"], mode)
        self.assertTrue(replies[6]["result"]["isError"])
        self.assertNotIn(grant["task_token"], run.stdout+run.stderr)
        self.assertNotIn(prepared["connection_token"], run.stdout+run.stderr)
        self.assertFalse((tools.root/"tools").exists())
        self.assertFalse((tools.root/"submissions").exists())
