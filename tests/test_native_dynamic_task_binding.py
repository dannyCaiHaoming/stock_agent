"""稳定MCP实例的动态任务接入；仅合成资料、确定性CLI和真实stdio，无模型/网络。"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from product.mcp.live.identity import parse_sec_ticker_map
from product.mcp.live.security_metadata import parse_chart_identity, bind_disclosure_security
from product.mcp.research import dispatch
from product.runtime.hashing import legacy_envelope_hash
from product.runtime.single_stock_input import build_single_stock_request, normalize_single_stock_intent
from product.tools.research import _write_json
from product.tools.research_connection import (
    bind_connection_file, prepare_connection, ResearchConnection, ResearchConnectionFile,
)
from tests.test_native_research_submission import company_draft
from tests.test_single_stock_input import AT

ROOT = Path(__file__).resolve().parents[1]
FUTURE = "2099-01-01T00:00:00Z"
PREFIX = "STOCK_AGENT_COMPANY"


def synthetic_request(symbol):
    mapping = parse_sec_ticker_map(json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
        "data": [[915913, symbol + " synthetic issuer", symbol, "NYSE"]]}).encode(), retrieved_at=AT)
    raw = json.dumps({"chart": {"error": None, "result": [{"meta": {
        "symbol": symbol, "instrumentType": "EQUITY", "currency": "USD", "exchangeName": "NYQ",
        "exchangeTimezoneName": "America/New_York"}}]}}).encode()
    record = {"raw_content_hash": hashlib.sha256(raw).hexdigest(), "retrieved_at": AT,
              "key": {"endpoint": "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol}}
    quote = parse_chart_identity(raw, ticker=symbol, record=record)
    cover = ('<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">Common Stock</ix:nonNumeric>'
             '<ix:nonNumeric name="dei:TradingSymbol" contextRef="C">' + symbol + '</ix:nonNumeric>'
             '<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">NYSE</ix:nonNumeric>').encode()
    document = {"form": "10-K", "raw_content_hash": hashlib.sha256(cover).hexdigest(),
        "cik": "0000915913", "source_id": "sec-synthetic-cover", "source_locator": "https://www.sec.gov/synthetic/cover.htm",
        "retrieved_at": AT, "published_at": "2026-02-01T00:00:00Z", "accession": "0000915913-26-000001"}
    return build_single_stock_request(normalize_single_stock_intent(symbol, at=AT), sec_mapping=mapping,
        security_metadata=[bind_disclosure_security(cover, document, quote)], resolved_cutoff=AT,
        request_id="synthetic-dynamic-" + symbol)


class NativeDynamicTaskBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.connections, self.tasks = [], []
        for symbol in ("LITE", "MRVL"):
            original = synthetic_request(symbol)
            facts = [{"evidence_id": symbol + "-revenue", "security_id": original["security"]["security_id"],
                      "semantic_field": "revenue", "value": "100", "unit": "USD",
                      "source_id": "synthetic-sec-" + symbol, "as_of": AT, "retrieved_at": AT}]
            gate = {"run_id": "synthetic-dynamic-" + symbol, "decision_cutoff": AT,
                    "allowed_evidence": facts, "allowed_evidence_ids": [facts[0]["evidence_id"]],
                    "excluded_evidence_ids": []}
            gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
            path = self.root/symbol
            prepared = prepare_connection(path, research_input=original, gate=gate, role="runtime_company_analyst")
            _write_json(path/"operator-grant.json", prepared)
            connection = ResearchConnection(path, connection_token=prepared["connection_token"])
            self.connections.append(connection)
            self.tasks.append(connection.prepare_task(security_id=original["security"]["security_id"], capability="COMPANY_RESEARCH"))
        self.path = self.root/"stable-connections.json"
        bind_connection_file(self.path, self.connections[0], expires_at=FUTURE)
        self.service = ResearchConnectionFile(self.path, prefix=PREFIX)

    def tearDown(self):
        self.tmp.cleanup()

    def bind(self, index):
        return bind_connection_file(self.path, self.connections[index], expires_at=FUTURE,
            expected_connection_hash=self.service.connection().context()["connection_hash"])

    def message(self, task, name="research_context", **arguments):
        return {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": name, "arguments": {"task_ref": task["task_ref"], "task_token": task["task_token"], **arguments}}}

    def call(self, task, name="research_context", **arguments):
        return dispatch(self.service, self.message(task, name, **arguments))["result"]

    def task_snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for connection in self.connections
                for p in connection.root.rglob("*") if p.is_file()}

    def assert_rejected_without_task_writes(self, task, name="research_submit", **arguments):
        before = self.task_snapshot()
        response = self.call(task, name, **({"draft": company_draft()} if name == "research_submit" else {}), **arguments)
        self.assertTrue(response["isError"], response)
        self.assertRegex(response["content"][0]["text"], r"^[A-Z0-9_]+$")
        for secret in (task["task_token"], str(self.root), *[c.connection_token for c in self.connections]):
            self.assertNotIn(secret, json.dumps(response))
        self.assertEqual(self.task_snapshot(), before)
        return response

    def test_new_request_uses_same_service_and_old_task_is_not_reinterpreted(self):
        before = self.task_snapshot()
        first = json.loads(self.call(self.tasks[0])["content"][0]["text"])
        self.assertEqual(first["security"]["display_symbol"], "LITE")
        receipt = self.bind(1)
        self.assertEqual(receipt["status"], "BOUND_NOT_RESEARCHED")
        self.assertNotIn(self.connections[1].connection_token, json.dumps(receipt))
        second = json.loads(self.call(self.tasks[1])["content"][0]["text"])
        self.assertEqual(second["security"]["display_symbol"], "MRVL")
        self.assertNotEqual(first["input_hash"], second["input_hash"])
        self.assertNotEqual(first["gate_hash"], second["gate_hash"])
        self.assert_rejected_without_task_writes(self.tasks[0])
        self.assert_rejected_without_task_writes(self.tasks[1], task_token=self.tasks[0]["task_token"])
        self.assert_rejected_without_task_writes(self.tasks[1], task_token="x"*43)
        self.assert_rejected_without_task_writes(self.tasks[1], task_ref="../../private")
        self.assert_rejected_without_task_writes(self.tasks[1], "research_query", evidence_ids=["LITE-revenue"])
        self.assertEqual(self.task_snapshot(), before)
        self.assertFalse(self.call(self.tasks[1])["isError"])

    def test_bound_connection_prepares_company_task_without_manual_credentials(self):
        before = {path.name for path in (self.connections[0].root / "tasks").iterdir()}
        response = dispatch(self.service, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "research_prepare_task", "arguments": {
                "security_id": "US:COMMON_STOCK:LITE", "capability": "COMPANY_RESEARCH"}}})
        self.assertFalse(response["result"]["isError"], response)
        grant = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(grant["task"]["security"]["security_id"], "US:COMMON_STOCK:LITE")
        self.assertEqual(grant["task"]["role"], "runtime_company_analyst")
        self.assertNotIn(self.connections[0].connection_token, json.dumps(response))
        self.assertEqual(len({path.name for path in (self.connections[0].root / "tasks").iterdir()}), len(before) + 1)

        values = json.loads(self.path.read_text())
        values[PREFIX + "_EXPIRES_AT"] = "2026-10-12T01:00:00Z"
        self.path.write_text(json.dumps(values))
        for at, rejected in (("2026-10-12T00:59:59Z", False), ("2026-10-12T01:00:00Z", True),
                             ("2026-10-12T01:00:01Z", True)):
            with self.subTest(at=at), patch("product.tools.research_connection._utc_now", return_value=at):
                if rejected:
                    result = self.assert_rejected_without_task_writes(self.tasks[0])
                    self.assertEqual(result["content"][0]["text"], "NATIVE_RESEARCH_CONNECTION_EXPIRED")
                else:
                    self.assertFalse(self.call(self.tasks[0])["isError"])
        before = self.task_snapshot()
        with patch("product.tools.research_connection._utc_now", return_value="2026-10-12T01:00:00Z"):
            result = dispatch(self.service, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_prepare_task", "arguments": {
                "security_id": self.tasks[0]["task"]["security"]["security_id"], "capability": "COMPANY_RESEARCH"}}})
        self.assertTrue(result["result"]["isError"])
        self.assertEqual(self.task_snapshot(), before)

    def test_dynamic_file_revalidates_private_path_permissions_and_never_falls_back(self):
        original = self.path.read_bytes()
        for values in ({}, {PREFIX + "_CONNECTION": str(self.connections[0].root), PREFIX + "_TOKEN": "x"*43},
                       {PREFIX + "_CONNECTION": "relative", PREFIX + "_TOKEN": self.connections[0].connection_token},
                       *[{**json.loads(original), PREFIX + "_EXPIRES_AT": expiry}
                         for expiry in (None, True, 1, "bad", "2099-01-01T00:00:00")]):
            with self.subTest(keys=list(values)):
                self.path.write_text(json.dumps(values))
                self.assert_rejected_without_task_writes(self.tasks[0])
        self.path.write_bytes(original)
        self.path.chmod(0o644)
        self.assert_rejected_without_task_writes(self.tasks[0])
        self.path.chmod(0o600)
        self.path.rename(self.root/"saved.json")
        self.assert_rejected_without_task_writes(self.tasks[0])
        self.path.symlink_to(self.root/"saved.json")
        self.assert_rejected_without_task_writes(self.tasks[0])
        self.path.unlink()
        (self.root/"saved.json").rename(self.path)
        self.root.chmod(0o755)
        try:
            self.assert_rejected_without_task_writes(self.tasks[0])
        finally:
            self.root.chmod(0o700)
        self.assertFalse(self.call(self.tasks[0])["isError"])

    def test_changed_role_and_source_integrity_are_rejected_on_next_call(self):
        prepared = prepare_connection(self.root/"skeptic", research_input=synthetic_request("MRVL"),
            gate=json.loads((self.connections[1].root/"gate.json").read_text()), role="runtime_skeptic")
        original = self.path.read_bytes()
        values = json.loads(original)
        values.update({PREFIX + "_CONNECTION": str(self.root/"skeptic"), PREFIX + "_TOKEN": prepared["connection_token"]})
        self.path.write_text(json.dumps(values))
        result = self.assert_rejected_without_task_writes(self.tasks[0])
        self.assertEqual(result["content"][0]["text"], "NATIVE_RESEARCH_ROLE_BINDING_INVALID")
        self.path.write_bytes(original)
        for name in ("input.json", "request.json", "gate.json", "connection.json", "access.json"):
            with self.subTest(source=name):
                path = self.connections[0].root/name
                saved = path.read_bytes()
                value = json.loads(saved)
                value["source_id"] = "tampered"
                if name == "access.json":
                    value["token"] = "x"*43
                path.write_text(json.dumps(value))
                self.assert_rejected_without_task_writes(self.tasks[0])
                path.write_bytes(saved)
        self.assertFalse(self.call(self.tasks[0])["isError"])

    def test_bind_requires_exact_previous_hash_and_retains_other_role_fields(self):
        before = self.path.read_bytes()
        for expected in (None, "0"*64, "bad"):
            with self.assertRaisesRegex(ValueError, "EXPECTATION_MISMATCH"):
                bind_connection_file(self.path, self.connections[1], expires_at=FUTURE, expected_connection_hash=expected)
            self.assertEqual(self.path.read_bytes(), before)
        prepared = prepare_connection(self.root/"market", research_input=synthetic_request("MRVL"),
            gate=json.loads((self.connections[1].root/"gate.json").read_text()), role="runtime_market_catalyst")
        market = ResearchConnection(self.root/"market", connection_token=prepared["connection_token"])
        bind_connection_file(self.path, market, expires_at=FUTURE)
        saved = json.loads(self.path.read_text())
        self.bind(1)
        values = json.loads(self.path.read_text())
        for key in ("STOCK_AGENT_MARKET_CONNECTION", "STOCK_AGENT_MARKET_TOKEN", "STOCK_AGENT_MARKET_EXPIRES_AT"):
            self.assertEqual(values[key], saved[key])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.root.glob(".stable-connections.json.*")))

    def test_bind_rejects_expired_invalid_credentials_and_unsafe_targets(self):
        before = self.path.read_bytes()
        for expiry in (AT, "bad", None, "2099-01-01T00:00:00"):
            with self.assertRaises(ValueError):
                bind_connection_file(self.path, self.connections[1], expires_at=expiry)
            self.assertEqual(self.path.read_bytes(), before)
        bad = ResearchConnection(self.connections[1].root, connection_token=self.tasks[1]["task_token"])
        with self.assertRaisesRegex(ValueError, "CONNECTION_ACCESS_INVALID"):
            bind_connection_file(self.path, bad, expires_at=FUTURE)
        link = self.root/"link.json"
        link.symlink_to(self.path)
        public = self.root/"public"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        for path in (Path("relative.json"), link, public/"env.json", ROOT/"unapproved-env.json",
                     self.connections[1].root/"input.json"):
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                bind_connection_file(path, self.connections[1], expires_at=FUTURE)
        unrelated = self.root/"unrelated.json"
        _write_json(unrelated, {"private": "do-not-overwrite"})
        saved = unrelated.read_bytes()
        with self.assertRaisesRegex(ValueError, "CONNECTION_FILE_INVALID"):
            bind_connection_file(unrelated, self.connections[1], expires_at=FUTURE)
        self.assertEqual(unrelated.read_bytes(), saved)
        self.assertEqual(self.path.read_bytes(), before)

    def test_busy_binding_file_fails_closed_and_atomic_replace_keeps_old_snapshot(self):
        before = self.path.read_bytes()
        expected = self.connections[0].context()["connection_hash"]
        with open(str(self.path) + ".lock", "rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, "CONNECTION_FILE_BUSY"):
                bind_connection_file(self.path, self.connections[1], expires_at=FUTURE, expected_connection_hash=expected)
        self.assertEqual(self.path.read_bytes(), before)
        with patch("product.tools.research_connection.os.replace", side_effect=OSError("private-path-secret")):
            with self.assertRaises(OSError):
                bind_connection_file(self.path, self.connections[1], expires_at=FUTURE, expected_connection_hash=expected)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".stable-connections.json.*")))
        self.assertFalse(self.call(self.tasks[0])["isError"])
        self.bind(1)
        self.assertFalse(self.call(self.tasks[1])["isError"])

    def test_legacy_file_without_expiry_keeps_company_schema_and_task_credentials(self):
        values = json.loads(self.path.read_text())
        values.pop(PREFIX + "_EXPIRES_AT")
        self.path.write_text(json.dumps(values))
        listed = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        dynamic = dispatch(self.service, listed)
        added = {item["name"] for item in dynamic["result"]["tools"]
                 if item["name"] in {"research_prepare_single_stock", "research_authorize_single_stock"}}
        self.assertEqual(added, {"research_prepare_single_stock", "research_authorize_single_stock"})
        dynamic["result"]["tools"] = [item for item in dynamic["result"]["tools"] if item["name"] not in added]
        for item in dynamic["result"]["tools"]:
            if item["name"] == "research_prepare_task":
                fields = item["inputSchema"]["properties"]
                self.assertIn("expected_request_hash", fields)
                self.assertIn("expected_gate_hash", fields)
                fields.pop("expected_request_hash")
                fields.pop("expected_gate_hash")
        self.assertEqual(dynamic, dispatch(self.connections[0], listed))
        self.assertEqual(self.call(self.tasks[0]), dispatch(self.connections[0], self.message(self.tasks[0]))["result"])
        self.assert_rejected_without_task_writes(self.tasks[0], task_token="x"*43)

    def cli_bind(self, index, *, expected=None, access=None):
        command = [sys.executable, "-B", "-m", "product.tools.prepare", "bind",
            "--connection-root", str(self.connections[index].root), "--connection-access",
            str(access or self.connections[index].root/"operator-grant.json"),
            "--connection-env-file", str(self.path), "--expires-at", FUTURE]
        if expected is not None:
            command.extend(["--expected-connection-hash", expected])
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=10)

    def test_binding_cli_redacts_secrets_and_rejects_before_replace(self):
        before = self.path.read_bytes()
        invalid = self.root/"invalid-access.json"
        _write_json(invalid, {"connection_token": self.tasks[1]["task_token"]})
        expected = self.connections[0].context()["connection_hash"]
        for result in (self.cli_bind(1), self.cli_bind(1, expected="0"*64), self.cli_bind(1, expected=expected, access=invalid)):
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "NATIVE_RESEARCH_CONNECTION_BINDING_REJECTED\n")
            self.assertEqual(self.path.read_bytes(), before)
        result = self.cli_bind(1, expected=expected)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["connection_hash"], self.connections[1].context()["connection_hash"])
        for secret in (*[c.connection_token for c in self.connections], self.tasks[1]["task_token"], str(self.root)):
            self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertFalse(self.call(self.tasks[1])["isError"])

    def test_same_live_stdio_pid_handles_lite_then_new_mrvl_without_config_or_restart(self):
        config_paths = (ROOT/"product/.mcp.json", ROOT/"product/hosts/claude-code/mcp.json")
        config_before = {path: path.read_bytes() for path in config_paths}
        env = {key: value for key, value in os.environ.items() if not key.startswith("STOCK_AGENT_")}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT),
                   STOCK_AGENT_COMPANY_CONNECTION=str(self.connections[0].root), STOCK_AGENT_COMPANY_TOKEN="invalid-inherited-token")
        command = [sys.executable, "-B", "-m", "product.mcp.research", "--connection-env-prefix", PREFIX,
                   "--connection-env-file", str(self.path)]
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        def rpc(message):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            self.assertTrue(select.select([process.stdout], [], [], 10)[0], "stdio response timeout")
            return json.loads(process.stdout.readline())["result"]
        def call(task, name="research_context", **arguments):
            return rpc(self.message(task, name, **arguments))
        try:
            pid = process.pid
            listed = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            manifest = rpc(listed)
            for task in (self.tasks[0],):
                self.assertFalse(call(task)["isError"])
                self.assertFalse(call(task, "research_query", evidence_ids=["LITE-revenue"])["isError"])
                draft = json.loads(json.dumps(company_draft()).replace("ev-revenue", "LITE-revenue"))
                submitted = call(task, "research_submit", draft=draft)
                self.assertFalse(submitted["isError"], submitted)
                first_receipt = json.loads(submitted["content"][0]["text"])
                self.assertTrue(first_receipt["accepted"])
                self.assertFalse(call(task, "research_read_submission", draft_ref=first_receipt["draft_ref"])["isError"])
            # New request task and its operator binding are prepared after the server has started.
            second = self.connections[1].prepare_task(security_id="US:COMMON_STOCK:MRVL", capability="COMPANY_RESEARCH")
            result = self.cli_bind(1, expected=self.connections[0].context()["connection_hash"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(rpc(listed), manifest)
            self.assertTrue(call(self.tasks[0])["isError"])
            self.assertTrue(call(second, task_token=self.tasks[0]["task_token"])["isError"])
            self.assertTrue(call(second, "research_query", evidence_ids=["LITE-revenue"])["isError"])
            context = call(second)
            self.assertFalse(context["isError"], context)
            self.assertEqual(json.loads(context["content"][0]["text"])["security"]["display_symbol"], "MRVL")
            self.assertFalse(call(second, "research_query", evidence_ids=["MRVL-revenue"])["isError"])
            draft = json.loads(json.dumps(company_draft()).replace("ev-revenue", "MRVL-revenue"))
            submitted = call(second, "research_submit", draft=draft)
            self.assertFalse(submitted["isError"], submitted)
            receipt = json.loads(submitted["content"][0]["text"])
            self.assertTrue(receipt["accepted"], receipt)
            read = call(second, "research_read_submission", draft_ref=receipt["draft_ref"])
            self.assertFalse(read["isError"], read)
            self.assertEqual(json.loads(read["content"][0]["text"])["security"]["display_symbol"], "MRVL")
            self.assertTrue(call(second, "research_read_submission", draft_ref=first_receipt["draft_ref"])["isError"])
            self.assertIsNone(process.poll())
            self.assertEqual(process.pid, pid)
            self.assertEqual({path: path.read_bytes() for path in config_paths}, config_before)
            process.stdin.close()
            process.wait(timeout=10)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(process.stderr.read(), "")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


if __name__ == "__main__":
    unittest.main()
