"""完整事实字节分页的零模型接缝；不模拟原生作者、来源或宿主执行。"""
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
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.tools.evidence import EvidenceTools
from product.tools.report_submission import queried_evidence
from product.tools.research import ADAPTER_VERSION, MAX_QUERY_BYTES, ResearchTools, prepare_task
from product.tools.research_connection import ResearchConnection, prepare_connection
from tests.test_native_research_submission import company_draft
from tests.test_native_research_tools import AT, ROOT, SECURITY, frozen_gate
from tests.test_single_stock_input import alb_request


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def large_gate():
    gate = frozen_gate()
    for index in range(30):
        gate["allowed_evidence"].append(dict(gate["allowed_evidence"][0], evidence_id=f"ev-large-{index:02d}"))
    for fact in gate["allowed_evidence"]:
        fact["source_excerpt"] = "完整事实🙂" * 250
    gate["allowed_evidence_ids"] = [fact["evidence_id"] for fact in gate["allowed_evidence"]]
    gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
    return gate


def expected_page(gate, ids, start, end):
    by_id = {fact["evidence_id"]: fact for fact in gate["allowed_evidence"]}
    facts = [by_id[ref] for ref in ids[start:end]]
    return {"adapter_version": ADAPTER_VERSION, "run_id": gate["run_id"], "evidence": facts,
            "result_hash": content_hash(facts), "total": len(ids), "offset": start,
            "next_offset": end if end < len(ids) else None}


class NativeQueryPaginationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.sequence = 0

    def tearDown(self):
        self.tmp.cleanup()

    def tools(self, gate=None):
        self.sequence += 1
        gate = copy.deepcopy(gate if gate is not None else large_gate())
        gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
        root = Path(self.tmp.name)/str(self.sequence)
        grant = prepare_task(root, research_input=alb_request(), gate=gate,
                             security_id=SECURITY, capability="COMPANY_RESEARCH")
        return ResearchTools(root, access_token=grant["access_token"])

    def events(self, tools):
        return [json.loads(path.read_text()) for path in (tools.root/"tools").glob("*.json")]

    def assert_no_success(self, tools):
        self.assertEqual(self.events(tools), [])
        self.assertFalse((tools.root/"submissions").exists())
        self.assertFalse((tools.root/"calculations").exists())

    def test_small_implicit_response_and_legacy_query_remain_unchanged(self):
        gate = frozen_gate()
        tools = self.tools(gate)
        ids = ["ev-revenue", "ev-income"]
        legacy = EvidenceTools(gate, run_id=gate["run_id"], agent="runtime_company_analyst", invocation_id="legacy",
                               adapter_version=ADAPTER_VERSION)
        expected = legacy.query(run_id=gate["run_id"], agent="runtime_company_analyst", invocation_id="legacy",
                                evidence_ids=ids)
        result = tools.query(evidence_ids=ids)
        self.assertEqual(result, expected)
        self.assertEqual(set(result), {"adapter_version", "run_id", "evidence", "result_hash"})
        event = self.events(tools)[0]
        self.assertEqual(event["input_hash"], canonical_hash({"evidence_ids": ids}))
        self.assertEqual(event["evidence_ids"], ids)
        self.assertEqual(event["output_hash"], canonical_hash(result))
        context = tools.context()
        self.assertEqual(context["query_limits"], {"max_ids": 64, "max_bytes": 65536,
                                                "default_offset": 0, "default_limit": 64})
        self.assertIn("next_offset", context["query_format"])
        self.assertTrue(context["directory_is_not_evidence_query"])

    def test_large_default_returns_longest_complete_prefix_then_all_pages_in_request_order(self):
        gate = large_gate()
        before = copy.deepcopy(gate)
        tools = self.tools(gate)
        files = {path.name: path.read_bytes() for path in tools.root.glob("*.json")}
        ids = list(reversed(tools.context()["allowed_evidence_ids"]))
        self.assertEqual(len(ids), 32)
        original = expected_page(gate, ids, 0, len(ids))
        self.assertGreater(encoded_size(original), MAX_QUERY_BYTES)
        result = tools.query(evidence_ids=ids)
        self.assertEqual(len(self.events(tools)), 1)  # No automatic query of subsequent pages.
        actual, offset = [], 0
        while True:
            end = result["next_offset"] if result["next_offset"] is not None else len(ids)
            self.assertEqual(result, expected_page(gate, ids, offset, end))
            self.assertLessEqual(encoded_size(result), MAX_QUERY_BYTES)
            if end < len(ids):
                self.assertGreater(encoded_size(expected_page(gate, ids, offset, end + 1)), MAX_QUERY_BYTES)
            event = next(event for event in self.events(tools) if event["output_hash"] == canonical_hash(result))
            inputs = {"evidence_ids": ids} if offset == 0 else {"evidence_ids": ids, "offset": offset}
            self.assertEqual(event["input_hash"], canonical_hash(inputs))
            self.assertEqual(event["evidence_ids"], ids[offset:end])
            self.assertEqual(event["event_hash"], canonical_hash({k: v for k, v in event.items() if k != "event_hash"}))
            actual.extend(fact["evidence_id"] for fact in result["evidence"])
            if result["next_offset"] is None:
                break
            offset = result["next_offset"]
            result = tools.query(evidence_ids=ids, offset=offset)
        self.assertEqual(actual, ids)
        self.assertEqual(len(set(actual)), 32)
        self.assertEqual(queried_evidence(tools), set(ids))
        self.assertEqual(gate, before)
        self.assertEqual(files, {path.name: path.read_bytes() for path in tools.root.glob("*.json")})

    def test_explicit_small_pages_and_original_parameters_are_hash_bound(self):
        gate = frozen_gate()
        tools = self.tools(gate)
        ids = ["ev-revenue", "ev-income"]
        for arguments, start, end in (({"offset": 0}, 0, 2), ({"limit": 1}, 0, 1),
                                      ({"offset": 1, "limit": 64}, 1, 2)):
            result = tools.query(evidence_ids=ids, **arguments)
            self.assertEqual(result, expected_page(gate, ids, start, end))
            event = next(event for event in self.events(tools) if event["input_hash"] == canonical_hash({"evidence_ids": ids, **arguments}))
            self.assertEqual(event["evidence_ids"], ids[start:end])
            self.assertEqual(event["output_hash"], canonical_hash(result))

    def test_exact_utf8_page_envelope_boundary_and_single_fact_overflow(self):
        gate = frozen_gate()
        fact = gate["allowed_evidence"][0]
        fact["source_excerpt"] = "🙂" * 16000
        size = encoded_size(expected_page(gate, ["ev-revenue"], 0, 1))
        fact["source_excerpt"] += "x" * (MAX_QUERY_BYTES - size)
        self.assertEqual(encoded_size(expected_page(gate, ["ev-revenue"], 0, 1)), MAX_QUERY_BYTES)
        tools = self.tools(gate)
        result = tools.query(evidence_ids=["ev-revenue"], offset=0)
        self.assertEqual(encoded_size(result), MAX_QUERY_BYTES)
        self.assertEqual(result["evidence"][0], fact)
        gate["allowed_evidence"][0]["source_excerpt"] += "x"
        tools = self.tools(gate)
        with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
            tools.query(evidence_ids=["ev-revenue"], offset=0)
        self.assert_no_success(tools)
        # The same fact still fits the legacy envelope; page metadata must count toward the limit.
        self.assertLessEqual(encoded_size(tools.query(evidence_ids=["ev-revenue"])), MAX_QUERY_BYTES)
        gate["allowed_evidence"][0]["source_excerpt"] = "🙂" * 17000
        tools = self.tools(gate)
        self.assertLess(len(json.dumps(expected_page(gate, ["ev-revenue"], 0, 1), ensure_ascii=False)), MAX_QUERY_BYTES)
        with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
            tools.query(evidence_ids=["ev-revenue"])
        self.assert_no_success(tools)

    def test_oversized_middle_fact_is_not_truncated_or_skipped(self):
        gate = frozen_gate()
        gate["allowed_evidence"][1]["source_excerpt"] = "x" * MAX_QUERY_BYTES
        ids = ["ev-revenue", "ev-income", "ev-revenue-copy"]
        # A legal later fact cannot be silently substituted for the oversized middle one.
        gate["allowed_evidence"].append(dict(gate["allowed_evidence"][0], evidence_id=ids[-1]))
        gate["allowed_evidence_ids"].append(ids[-1])
        tools = self.tools(gate)
        first = tools.query(evidence_ids=ids)
        self.assertEqual(first, expected_page(gate, ids, 0, 1))
        before = self.events(tools)
        with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
            tools.query(evidence_ids=ids, offset=1)
        self.assertEqual(self.events(tools), before)
        self.assertEqual(queried_evidence(tools), {"ev-revenue"})
        self.assertFalse((tools.root/"submissions").exists())

    def test_invalid_page_parameters_and_id_shapes_never_write(self):
        tools = self.tools(frozen_gate())
        for key, values in (("offset", (-1, True, False, 1.5, "0", None, 2)),
                            ("limit", (0, -1, 65, True, False, 1.5, "1", None))):
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, "PAGE_INVALID"):
                    tools.query(evidence_ids=["ev-revenue", "ev-income"], **{key: value})
        for ids in ([], ["ev-revenue"] * 2, [None], [str(index) for index in range(65)], ("ev-revenue",)):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, "QUERY_INVALID"):
                tools.query(evidence_ids=ids)
        for arguments in ({"offset": None}, {"limit": True}, {"offset": 64}, {"unknown": 1}):
            response = dispatch(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_query", "arguments": {"evidence_ids": ["ev-revenue"], **arguments}}})
            self.assertTrue(response["result"]["isError"], response)
        self.assert_no_success(tools)

    def test_entire_selection_is_authorized_even_outside_returned_page(self):
        tools = self.tools()
        ids = tools.context()["allowed_evidence_ids"]
        for forbidden in ("unknown", "ev-excluded", "ev-other"):
            for offset in (0, 1):
                with self.subTest(forbidden=forbidden, offset=offset), self.assertRaises(ValueError):
                    tools.query(evidence_ids=[*ids, forbidden], offset=offset, limit=1)
        self.assert_no_success(tools)

    def test_credentials_and_resource_drift_are_rechecked_on_later_pages(self):
        tools = self.tools()
        other = self.tools()
        ids = tools.context()["allowed_evidence_ids"]
        first = tools.query(evidence_ids=ids, limit=1)
        before = self.events(tools)
        for token in (None, "", "x" * 40, other.access_token):
            with self.subTest(token_is_other=token == other.access_token), self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
                ResearchTools(tools.root, access_token=token).query(evidence_ids=ids, offset=first["next_offset"])
        with patch("product.tools.resource_bindings.resource_bindings", return_value={"drift": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "RESOURCE_DRIFT"):
                tools.query(evidence_ids=ids, offset=first["next_offset"])
        self.assertEqual(self.events(tools), before)
        self.assertFalse((tools.root/"submissions").exists())
        self.assertEqual(tools.query(evidence_ids=ids, offset=1, limit=1)["offset"], 1)

    def test_future_gate_fact_and_task_or_input_tampering_reject_before_success(self):
        for name in ("future", "gate", "task", "input"):
            tools = self.tools()
            ids = tools.context()["allowed_evidence_ids"]
            file = "gate" if name in {"future", "gate"} else name
            path = tools.root/(file + ".json")
            value = json.loads(path.read_text())
            if name == "future":
                value["allowed_evidence"][-1]["as_of"] = "2026-10-03T00:00:00Z"
                value["allowed_evidence"][-1]["retrieved_at"] = "2026-10-03T00:00:00Z"
                value["bundle_hash"] = legacy_envelope_hash(value, hash_field="bundle_hash")
            elif name == "gate":
                value["allowed_evidence"][-1]["value"] = "changed"
            elif name == "task":
                value["allowed_evidence_ids"].append("ev-other")
            else:
                value["tampered"] = True
            path.write_text(json.dumps(value))
            with self.subTest(name=name), self.assertRaises(ValueError):
                tools.query(evidence_ids=ids, offset=0, limit=1)
            self.assert_no_success(tools)

    def test_old_evidence_tools_still_return_full_selection_without_native_paging(self):
        gate = large_gate()
        ids = [fact["evidence_id"] for fact in gate["allowed_evidence"] if fact["security_id"] == SECURITY]
        tools = EvidenceTools(gate, run_id=gate["run_id"], agent="runtime_company_analyst", invocation_id="legacy")
        result = tools.query(run_id=gate["run_id"], agent="runtime_company_analyst", invocation_id="legacy", evidence_ids=ids)
        self.assertEqual([fact["evidence_id"] for fact in result["evidence"]], ids)
        self.assertNotIn("next_offset", result)
        self.assertGreater(encoded_size(result), MAX_QUERY_BYTES)

    def connection(self):
        root = Path(self.tmp.name)/"connection"
        prepared = prepare_connection(root, research_input=alb_request(), gate=large_gate(), role="runtime_company_analyst")
        connection = ResearchConnection(root, connection_token=prepared["connection_token"])
        task = connection.prepare_task(security_id=SECURITY, capability="COMPANY_RESEARCH")
        tools = connection.task_tools(task_ref=task["task_ref"], task_token=task["task_token"])
        return root, prepared, task, tools

    def stdio(self, root, prepared, task, calls):
        messages = [{"jsonrpc": "2.0", "id": index, "method": "tools/call", "params": {
            "name": name, "arguments": {"task_ref": task["task_ref"], "task_token": task["task_token"], **arguments}}}
                    for index, (name, arguments) in enumerate(calls, 1)]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", STOCK_AGENT_COMPANY_CONNECTION=str(root),
                   STOCK_AGENT_COMPANY_TOKEN=prepared["connection_token"])
        run = subprocess.run([sys.executable, "-B", "-m", "product.mcp.research", "--connection-env-prefix", "STOCK_AGENT_COMPANY"],
                             input="\n".join(json.dumps(message) for message in messages) + "\n", text=True,
                             capture_output=True, env=env, cwd=ROOT, timeout=15, check=True)
        for token in (prepared["connection_token"], task["task_token"]):
            self.assertNotIn(token, run.stdout + run.stderr)
        replies = [json.loads(line)["result"] for line in run.stdout.splitlines()]
        self.assertEqual(len(replies), len(calls))
        return replies

    def test_routed_stdio_unread_later_fact_submission_is_rejected(self):
        root, prepared, task, tools = self.connection()
        ids = [ref for ref in tools.context()["allowed_evidence_ids"] if ref != "ev-revenue"] + ["ev-revenue"]
        replies = self.stdio(root, prepared, task, [
            ("research_query", {"evidence_ids": ids, "task_token": "x" * 40}),
            ("research_query", {"evidence_ids": ids}),
            ("research_submit", {"draft": company_draft()}),
        ])
        self.assertTrue(replies[0]["isError"])
        self.assertFalse(replies[1]["isError"], replies[1])
        page = json.loads(replies[1]["content"][0]["text"])
        self.assertLessEqual(len(replies[1]["content"][0]["text"].encode("utf-8")), MAX_QUERY_BYTES)
        self.assertIsNotNone(page["next_offset"])
        self.assertNotIn("ev-revenue", queried_evidence(tools))
        receipt = json.loads(replies[2]["content"][0]["text"])
        self.assertFalse(receipt["accepted"], receipt)
        self.assertEqual(receipt["validation_error"], "NATIVE_RESEARCH_EVIDENCE_NOT_QUERIED")
        self.assertEqual(len(self.events(tools)), 1)
        saved = tools.root/"submissions/1.json"
        before = saved.read_bytes()
        with self.assertRaisesRegex(ValueError, "RESPONSE_TOO_LARGE"):
            # A rejected query neither consumes the revision slot nor overwrites the original draft.
            with patch("product.tools.research.MAX_QUERY_BYTES", 1):
                tools.query(evidence_ids=ids, offset=page["next_offset"])
        self.assertEqual(saved.read_bytes(), before)
        self.assertFalse((tools.root/"submissions/2.json").exists())
        with self.assertRaisesRegex(ValueError, "RECEIPT_BINDING_INVALID"):
            tools.read_submission(draft_ref=receipt["draft_ref"])

    def test_routed_stdio_all_pages_save_and_exact_readback(self):
        root, prepared, task, tools = self.connection()
        ids = [ref for ref in tools.context()["allowed_evidence_ids"] if ref != "ev-revenue"] + ["ev-revenue"]
        before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*.json")}
        actual, arguments = [], {"evidence_ids": ids}
        while True:
            reply = self.stdio(root, prepared, task, [("research_query", arguments)])[0]
            self.assertFalse(reply["isError"], reply)
            text = reply["content"][0]["text"]
            self.assertLessEqual(len(text.encode("utf-8")), MAX_QUERY_BYTES)
            page = json.loads(text)
            actual.extend(fact["evidence_id"] for fact in page["evidence"])
            if page["next_offset"] is None:
                break
            arguments = {"evidence_ids": ids, "offset": page["next_offset"], "limit": 64}
        self.assertEqual(actual, ids)
        self.assertEqual(queried_evidence(tools), set(ids))
        reply = self.stdio(root, prepared, task, [("research_submit", {"draft": company_draft()})])[0]
        self.assertFalse(reply["isError"], reply)
        receipt = json.loads(reply["content"][0]["text"])
        self.assertTrue(receipt["accepted"], receipt)
        reply = self.stdio(root, prepared, task, [("research_read_submission", {"draft_ref": receipt["draft_ref"]})])[0]
        self.assertFalse(reply["isError"], reply)
        report = json.loads(reply["content"][0]["text"])
        self.assertEqual(report["report_id"], receipt["report_id"])
        self.assertEqual(report["evidence_refs"], ["ev-revenue"])
        self.assertEqual(report["research"]["claims"][0]["statement"], company_draft()["claims"][0]["statement"])
        self.assertEqual(report["business_validation"], "VALIDATED")
        self.assertEqual(report["host_execution"], "UNVERIFIED")
        self.assertEqual(report["content_verdict"], "NOT_REVIEWED")
        self.assertTrue(report["advisory_only"])
        self.assertTrue(all(report[key] for key in ("source_id", "as_of", "retrieved_at")))
        self.assertEqual(before, {name: (root/name).read_bytes() for name in before})

    def test_mcp_manifests_expose_only_optional_bounded_page_arguments(self):
        for manifest in (tool_manifest(), routed_tool_manifest()):
            query = next(item for item in manifest if item["name"] == "research_query")
            schema = query["inputSchema"]
            self.assertEqual(set(schema["properties"]) - set(schema["required"]), {"offset", "limit"})
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(schema["properties"]["offset"], {"type": "integer", "minimum": 0, "maximum": 63})
            self.assertEqual(schema["properties"]["limit"], {"type": "integer", "minimum": 1, "maximum": 64})
            self.assertIn("65536 UTF-8", query["description"])
            self.assertIn("next_offset", query["description"])
