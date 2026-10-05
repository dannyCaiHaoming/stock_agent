"""真实 MCP 参数/收据接缝：由服务端编号，不调用模型。"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from product.runtime.fixture_mcp import StatelessFixtureTools, GateScopedFixtureTools, serve_stdio, ToolAccessError
from product.runtime.multidimensional_stage import build_multidimensional_dispatch_packet
from product.runtime.hashing import legacy_envelope_hash
from tests import test_multidimensional_stage as fixtures


class ServerCalculationIdentityTests(unittest.TestCase):
    def prepared(self, root):
        run, _ = fixtures.MultidimensionalStageTests().prepare(root, count=1)
        index = json.loads((run / "research/dispatch-index.json").read_text())
        task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
        packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
        return run, task, packet

    def arguments(self, task, packet):
        return {key: task[key] for key in ("run_id", "agent", "invocation_id")} | {
            "operation": "ratio", "evidence_ids": list(packet["reference_map"]["evidence"])[:2],
        }

    def test_server_assigns_id_with_real_ordered_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            tools = StatelessFixtureTools(default_run_dir=run)
            args = self.arguments(task, packet)
            schema = next(t["inputSchema"] for t in tools.available_tools() if t["name"] == "calculate")
            self.assertNotIn("calculation_id", schema["required"])
            first = tools.calculate(**args)
            second = tools.calculate(**(args | {"evidence_ids": list(reversed(args["evidence_ids"]))}))
            self.assertRegex(first["calculation_id"], r"^calc-[0-9a-f]{32}$")
            self.assertNotEqual(first["calculation_id"], second["calculation_id"])
            self.assertNotEqual(first["value"], second["value"])
            receipts = [json.loads(line) for line in (run / first["artifact_ref"]).read_text().splitlines()]
            for result, receipt, inputs in zip((first, second), receipts, (args["evidence_ids"], list(reversed(args["evidence_ids"])))):
                self.assertEqual(receipt["calculation_id"], result["calculation_id"])
                self.assertEqual(receipt["evidence_ids"], [packet["reference_map"]["evidence"][ref] for ref in inputs])
                self.assertEqual(receipt["receipt_hash"], legacy_envelope_hash(receipt, hash_field="receipt_hash"))
                self.assertEqual(receipt["output"]["value"], result["value"])

    def test_concurrent_calls_keep_unique_successful_records(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            def calculate(_):
                return StatelessFixtureTools(default_run_dir=run).calculate(**self.arguments(task, packet))
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(calculate, range(12)))
            self.assertEqual(len({item["calculation_id"] for item in results}), 12)
            lines = (run / results[0]["artifact_ref"]).read_text().splitlines()
            self.assertEqual(len(lines), 12)
            self.assertEqual({json.loads(line)["calculation_id"] for line in lines}, {item["calculation_id"] for item in results})

    def test_actual_stdio_parameter_contract_and_failure_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            arguments = self.arguments(task, packet)
            ledger = run / task["calculation_ledger_ref"]
            def invoke(args):
                request = {"id": 1, "method": "tools/call", "params": {"name": "calculate", "arguments": args}}
                output = io.StringIO()
                with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
                    serve_stdio(stateless=True, default_run_dir=run)
                return json.loads(output.getvalue())
            initial = ledger.read_bytes()
            for invalid in (arguments | {"unsupported": "value"}, arguments | {"calculation_id": ""},
                            arguments | {"invocation_id": "foreign"}, arguments | {"operation": "unknown"}):
                result = invoke(invalid)
                self.assertIn("error", result)
                self.assertEqual(ledger.read_bytes(), initial)
            result = invoke(arguments)
            self.assertNotIn("error", result)
            value = result["result"]["structuredContent"]
            self.assertRegex(value["calculation_id"], r"^calc-[0-9a-f]{32}$")
            self.assertEqual(json.loads(ledger.read_text())["calculation_id"], value["calculation_id"])

    def test_unbound_actual_stdio_accepts_current_server_ids_and_keeps_task_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            tools = StatelessFixtureTools()
            static_schema = next(t["inputSchema"] for t in tools.tool_manifest() if t["name"] == "calculate")
            schema = next(t["inputSchema"] for t in tools.available_tools() if t["name"] == "calculate")
            self.assertEqual(static_schema, schema)
            self.assertNotIn("calculation_id", schema["required"])
            self.assertIn("run_dir", schema["required"])
            request = {"id": 1, "method": "tools/call", "params": {"name": "calculate",
                "arguments": self.arguments(task, packet) | {"run_dir": str(run)}}}
            output = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
                serve_stdio(tools_override=tools)
            response = json.loads(output.getvalue())
            self.assertNotIn("error", response)
            self.assertRegex(response["result"]["structuredContent"]["calculation_id"], r"^calc-[0-9a-f]{32}$")
            index = json.loads((run / "research/dispatch-index.json").read_text())
            denied = next(t for t in index["tasks"] if t["capability"] == "OPTIONS_FLOW")
            before = (run / task["calculation_ledger_ref"]).read_bytes()
            request["params"]["arguments"].update({key: denied[key] for key in ("agent", "invocation_id")})
            output = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
                serve_stdio(tools_override=StatelessFixtureTools())
            response = json.loads(output.getvalue())
            self.assertIn("TOOL_NOT_AUTHORIZED", response["error"]["message"])
            self.assertEqual((run / task["calculation_ledger_ref"]).read_bytes(), before)

    def test_explicit_legacy_id_still_binds_exactly_and_empty_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepared(Path(directory))
            tools = StatelessFixtureTools(default_run_dir=run)
            args = self.arguments(task, packet)
            output = tools.calculate(**args, calculation_id="legacy-explicit")
            self.assertEqual(output["calculation_id"], "legacy-explicit")
            before = (run / output["artifact_ref"]).read_bytes()
            with self.assertRaisesRegex(ToolAccessError, "INVALID_CALCULATION_ID"):
                tools.calculate(**args, calculation_id="")
            self.assertEqual((run / output["artifact_ref"]).read_bytes(), before)
            old_schema = next(t["inputSchema"] for t in GateScopedFixtureTools.tool_manifest() if t["name"] == "calculate")
            self.assertIn("calculation_id", old_schema["required"])

    def test_unbound_legacy_task_still_requires_id_and_original_call_remains_usable(self):
        from product.runtime.run_package import prepare_run
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "legacy-run"
            prepare_run(fixtures.ROOT, fixture_path=fixtures.ROOT / "evals/fixtures/codex-native/normal-research.json",
                        run_dir=run, run_id="legacy-id-contract", model="gpt-6-luna",
                        research_question="仅验证旧协议确定性参数。")
            invocation = json.loads((run / "invocations/runtime_company_analyst.json").read_text())
            args = {"run_dir": str(run), "run_id": "legacy-id-contract", "agent": "runtime_company_analyst",
                    "invocation_id": invocation["invocation_id"], "operation": "ratio",
                    "evidence_ids": ["ev-normal-debt", "ev-normal-revenue"]}
            tools = StatelessFixtureTools()
            with self.assertRaisesRegex(ToolAccessError, "CALCULATION_ID_REQUIRED_FOR_LEGACY_PROTOCOL"):
                tools.calculate(**args)
            self.assertEqual(tools.events, [])
            output = tools.calculate(**args, calculation_id="legacy-ratio")
            self.assertEqual(output["calculation_id"], "legacy-ratio")
            self.assertNotIn("calculation_ref", output)

    def test_server_ids_do_not_grant_an_unauthorized_task_math_access(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, _ = self.prepared(Path(directory))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "OPTIONS_FLOW")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            before = {str(path.relative_to(run)): path.read_bytes()
                      for path in (run / "research/calculations").rglob("tool-results.jsonl")}
            with self.assertRaisesRegex(ToolAccessError, "TOOL_NOT_AUTHORIZED"):
                StatelessFixtureTools(default_run_dir=run).calculate(**self.arguments(task, packet))
            after = {str(path.relative_to(run)): path.read_bytes()
                     for path in (run / "research/calculations").rglob("tool-results.jsonl")}
            self.assertEqual(after, before)
