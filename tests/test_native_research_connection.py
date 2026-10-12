"""同一请求/角色连接的多任务业务路由；不启动Agent或模型。"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from product.council.intake_planning import build_common_stock_council_request
from product.mcp.research import dispatch, routed_tool_manifest
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.tools.research_connection import prepare_connection, ResearchConnection
from tests.test_common_stock_research_contracts import stock_handoff, gate_for
from tests.test_native_research_submission import company_draft

ROOT = Path(__file__).resolve().parents[1]


class NativeResearchConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.input = stock_handoff(2)
        self.gate = gate_for(self.input, run_id="native-connection-test")
        self.request = build_common_stock_council_request(self.input, request_id="connection-request", research_question="研究全部确认普通股的经营质量。")
        prepared = prepare_connection(self.root/"company", research_input=self.input, gate=self.gate,
                                      role="runtime_company_analyst", research_request=self.request)
        self.token = prepared["connection_token"]
        self.connection = ResearchConnection(self.root/"company", connection_token=self.token)
        self.tasks = [self.connection.prepare_task(security_id=position["security_id"], capability="COMPANY_RESEARCH")
                      for position in self.input["portfolio"]["positions"]]

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, task, name, **arguments):
        response = dispatch(self.connection, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": name, "arguments": {"task_ref": task["task_ref"], "task_token": task["task_token"], **arguments}}})
        return response["result"]

    def snapshot(self):
        result = {}
        for path in (self.root, *self.root.rglob("*")):
            value = {"mode": path.lstat().st_mode}
            if path.is_symlink():
                value["link"] = os.readlink(path)
            elif path.is_file():
                value["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            result[str(path.relative_to(self.root))] = value
        return result

    def observe(self, connection=None, **arguments):
        return dispatch(connection or self.connection, {"jsonrpc": "2.0", "id": 1,
            "method": "tools/call", "params": {"name": "research_connection_context", "arguments": arguments}})["result"]

    def test_binding_observation_four_roles_without_tasks_has_exact_fields_and_current_time(self):
        fields = {"source_id", "as_of", "retrieved_at", "role", "connection_hash", "request_hash",
                  "input_hash", "gate_hash", "decision_cutoff", "caller_authentication"}
        stamp = "2026-10-09T09:20:00Z"
        for role in ("runtime_company_analyst", "runtime_market_catalyst", "runtime_skeptic", "runtime_cio"):
            with self.subTest(role=role):
                root = self.root/role
                prepared = prepare_connection(root, research_input=self.input, gate=self.gate,
                    role=role, research_request=self.request)
                connection = ResearchConnection(root, connection_token=prepared["connection_token"])
                before = self.snapshot()
                with patch("product.tools.research_connection._utc_now", return_value=stamp) as clock:
                    response = self.observe(connection, expected_connection_hash=prepared["connection"]["connection_hash"])
                self.assertFalse(response["isError"], response)
                value = json.loads(response["content"][0]["text"])
                self.assertEqual(set(value), fields)
                for key in ("role", "connection_hash", "request_hash", "input_hash", "gate_hash", "decision_cutoff"):
                    self.assertEqual(value[key], prepared["connection"][key])
                self.assertEqual(value["source_id"], "native-research-connection-observation:"+role)
                self.assertEqual(value["as_of"], stamp)
                self.assertEqual(value["retrieved_at"], stamp)
                self.assertNotEqual(value["as_of"], value["decision_cutoff"])
                self.assertEqual(value["caller_authentication"], "UNVERIFIED")
                clock.assert_called_once_with()
                self.assertNotIn(prepared["connection_token"], json.dumps(response))
                self.assertFalse((root/"tasks").exists())
                self.assertEqual(self.snapshot(), before)

    def test_binding_projection_excludes_private_future_fields_and_untrusted_caller_claim(self):
        root = self.root/"company"
        path = root/"connection.json"
        connection = json.loads(path.read_text())
        connection.update(caller_authentication="VERIFIED", future_private={"token": "private-future-token",
            "path": str(root), "report": "private-positive-report"},
            precomputed={"private-metric": 987654321}, allowed_evidence_ids=["private-fact-id"])
        connection["dependency_connections"] = {"runtime_market_catalyst": str(self.root/"private-dependency")}
        connection["preparation_inputs"]["future_secret"] = "private-preparation-secret"
        connection["connection_hash"] = canonical_hash({k: v for k, v in connection.items() if k != "connection_hash"})
        path.write_text(json.dumps(connection), encoding="utf-8")
        access_path = root/"access.json"
        access = json.loads(access_path.read_text())
        access["connection_hash"] = connection["connection_hash"]
        access_path.write_text(json.dumps(access), encoding="utf-8")
        before = self.snapshot()
        response = self.observe(expected_connection_hash=connection["connection_hash"])
        self.assertFalse(response["isError"], response)
        value = json.loads(response["content"][0]["text"])
        self.assertEqual(len(value), 10)
        self.assertEqual(value["caller_authentication"], "UNVERIFIED")
        for secret in (self.token, str(self.root), self.request["research_question"], "private-future-token",
                       "private-positive-report", "private-metric", "private-fact-id", "private-preparation-secret",
                       "input_binding", "preparation_inputs", "dependency_connections", "987654321"):
            self.assertNotIn(secret, json.dumps(response, ensure_ascii=False))
        self.assertEqual(self.snapshot(), before)

    def test_binding_observation_rejects_missing_wrong_connection_tokens_without_writes(self):
        expected = self.connection.context()["connection_hash"]
        before = self.snapshot()
        for token in (None, "bad", self.tasks[0]["task_token"]):
            with self.subTest(token_kind="missing" if token is None else "wrong"):
                response = self.observe(ResearchConnection(self.root/"company", connection_token=token),
                    expected_connection_hash=expected)
                self.assertTrue(response["isError"], response)
                self.assertEqual(response["content"][0]["text"], "NATIVE_RESEARCH_CONNECTION_ACCESS_INVALID")
                self.assertNotIn(self.token, json.dumps(response))
                self.assertEqual(self.snapshot(), before)

    def test_binding_observation_reauthorizes_files_sources_and_permissions_each_call(self):
        root = self.root/"company"
        expected = self.connection.context()["connection_hash"]
        mutations = {
            "access.json": lambda value: value.update(token="replaced-server-token"+"x"*32),
            "connection.json": lambda value: value.update(research_question="changed connection question"),
            "request.json": lambda value: value.update(research_question="changed request question"),
            "input.json": lambda value: value.update(source_id="changed-input-source"),
            "gate.json": lambda value: value["allowed_evidence"][0].update(value="changed-fact"),
        }
        for name, mutate in mutations.items():
            with self.subTest(file=name):
                self.assertFalse(self.observe(expected_connection_hash=expected)["isError"])
                path = root/name
                original = path.read_bytes()
                value = json.loads(original)
                mutate(value)
                path.write_text(json.dumps(value), encoding="utf-8")
                before = self.snapshot()
                try:
                    response = self.observe(expected_connection_hash=expected)
                    self.assertTrue(response["isError"], response)
                    self.assertRegex(response["content"][0]["text"], r"^[A-Z0-9_]+$")
                    self.assertNotIn(self.token, json.dumps(response))
                    self.assertNotIn(str(root), json.dumps(response))
                    self.assertEqual(self.snapshot(), before)
                finally:
                    path.write_bytes(original)
                self.assertFalse(self.observe(expected_connection_hash=expected)["isError"])
        for path in (root, root/"connection.json", root/"access.json", root/"request.json", root/"input.json", root/"gate.json"):
            with self.subTest(permissions=path.name):
                mode = path.stat().st_mode & 0o777
                path.chmod(mode | 0o044)
                before = self.snapshot()
                try:
                    response = self.observe(expected_connection_hash=expected)
                    self.assertTrue(response["isError"], response)
                    self.assertEqual(self.snapshot(), before)
                finally:
                    path.chmod(mode)
        path = root/"connection.json"
        original = path.read_bytes()
        path.rename(root/"original-connection.json")
        path.symlink_to(root/"original-connection.json")
        before = self.snapshot()
        self.assertTrue(self.observe(expected_connection_hash=expected)["isError"])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((root/"original-connection.json").read_bytes(), original)

    def test_binding_observation_rejects_valid_rehashed_gate_cutoff_drift(self):
        from product.tools.research import validate_gate
        expected = self.connection.context()["connection_hash"]
        path = self.root/"company/gate.json"
        gate = json.loads(path.read_text())
        gate["decision_cutoff"] = "2026-09-12T12:00:00Z"
        gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
        validate_gate(gate)
        path.write_text(json.dumps(gate), encoding="utf-8")
        before = self.snapshot()
        response = self.observe(expected_connection_hash=expected)
        self.assertTrue(response["isError"], response)
        self.assertEqual(response["content"][0]["text"], "NATIVE_RESEARCH_CONNECTION_SOURCE_INVALID")
        self.assertEqual(self.snapshot(), before)

    def test_binding_observation_rejects_wrong_hash_format_type_and_extra_arguments(self):
        expected = self.connection.context()["connection_hash"]
        before = self.snapshot()
        arguments = [{}, *[{"expected_connection_hash": value} for value in ("0"*64, "A"*64, "0"*63, None, 1, [], True)],
                     *[{"expected_connection_hash": expected, key: value} for key, value in (
                         ("role", "runtime_cio"), ("run_dir", str(self.root)), ("task_ref", self.tasks[0]["task_ref"]),
                         ("task_token", self.tasks[0]["task_token"]), ("connection_token", self.token))]]
        for supplied in arguments:
            with self.subTest(keys=sorted(supplied)):
                response = self.observe(**supplied)
                self.assertTrue(response["isError"], response)
                self.assertRegex(response["content"][0]["text"], r"^[A-Z0-9_]+$")
                for secret in (self.token, self.tasks[0]["task_token"], str(self.root)):
                    self.assertNotIn(secret, json.dumps(response))
                self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.observe(expected_connection_hash=expected)["isError"])
        self.assertEqual(self.snapshot(), before)

    def test_valid_old_connection_cannot_match_new_preparation_hash(self):
        changed = build_common_stock_council_request(self.input, request_id="new-window-request",
            research_question=self.request["research_question"])
        prepared = prepare_connection(self.root/"new-window", research_input=self.input, gate=self.gate,
            role="runtime_company_analyst", research_request=changed)
        before = self.snapshot()
        response = self.observe(expected_connection_hash=prepared["connection"]["connection_hash"])
        self.assertTrue(response["isError"], response)
        self.assertEqual(response["content"][0]["text"], "NATIVE_RESEARCH_CONNECTION_EXPECTATION_MISMATCH")
        self.assertEqual(self.snapshot(), before)

    def test_observation_does_not_authorize_business_and_original_submit_path_recovers(self):
        expected = self.connection.context()["connection_hash"]
        before = self.snapshot()
        self.assertFalse(self.observe(expected_connection_hash=expected)["isError"])
        task = self.tasks[0]
        for name, arguments in (("research_context", {}), ("research_query", {"evidence_ids": ["not-authorized"]}),
                                ("research_submit", {"draft": company_draft()})):
            response = dispatch(self.connection, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}})["result"]
            self.assertTrue(response["isError"], response)
        self.assertTrue(self.call(task, "research_context", task_token=self.tasks[1]["task_token"])["isError"])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.call(task, "research_context")["isError"])
        ref = task["task"]["allowed_evidence_ids"][0]
        self.assertFalse(self.call(task, "research_query", evidence_ids=[ref])["isError"])
        draft = json.loads(json.dumps(company_draft()).replace("ev-revenue", ref))
        response = self.call(task, "research_submit", draft=draft)
        self.assertFalse(response["isError"], response)
        receipt = json.loads(response["content"][0]["text"])
        self.assertTrue(receipt["accepted"], receipt)
        report = self.call(task, "research_read_submission", draft_ref=receipt["draft_ref"])
        self.assertFalse(report["isError"], report)
        self.assertEqual(json.loads(report["content"][0]["text"])["security"], task["task"]["security"])

    def test_legacy_single_task_interface_does_not_expose_or_accept_connection_observation(self):
        task = self.tasks[0]
        tools = self.connection.task_tools(task_ref=task["task_ref"], task_token=task["task_token"])
        before = self.snapshot()
        listed = dispatch(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertNotIn("research_connection_context", {item["name"] for item in listed["result"]["tools"]})
        response = self.observe(tools, expected_connection_hash=self.connection.context()["connection_hash"])
        self.assertTrue(response["isError"], response)
        self.assertEqual(response["content"][0]["text"], "NATIVE_RESEARCH_TOOL_UNSUPPORTED")
        self.assertFalse(dispatch(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "research_context", "arguments": {}}})["result"]["isError"])
        self.assertEqual(self.snapshot(), before)

    def test_same_connection_queries_two_securities_without_identity_or_data_mix(self):
        for task in [self.tasks[0], self.tasks[1], self.tasks[0]]:
            ref = task["task"]["allowed_evidence_ids"][0]
            response = self.call(task, "research_query", evidence_ids=[ref])
            self.assertFalse(response["isError"], response)
            result = json.loads(response["content"][0]["text"])
            self.assertEqual(result["evidence"][0]["security_id"], task["task"]["security"]["security_id"])
            self.assertNotIn(task["task_token"], json.dumps(result))
        context = self.connection.context()
        self.assertNotIn("portfolio", context)
        self.assertNotIn("token", context)
        self.assertEqual(context["caller_authentication"], "UNVERIFIED")

    def test_context_paging_uses_exact_task_route_and_rejects_mixed_credentials(self):
        first, second = self.tasks
        response = self.call(first, "research_context", evidence_offset=1, evidence_limit=1)
        self.assertFalse(response["isError"], response)
        page = json.loads(response["content"][0]["text"])
        self.assertEqual(page["allowed_evidence_ids"], first["task"]["allowed_evidence_ids"][1:2])
        self.assertEqual(page["security"], first["task"]["security"])
        wrong = self.call(second, "research_context", task_token=first["task_token"], evidence_offset=1)
        self.assertTrue(wrong["isError"], wrong)
        bad = self.call(first, "research_context", evidence_limit=True)
        self.assertTrue(bad["isError"], bad)
        recovered = self.call(first, "research_context", evidence_limit=1)
        self.assertFalse(recovered["isError"], recovered)
        for task in self.tasks:
            root = self.root/"company/tasks"/task["task_ref"]
            self.assertFalse((root/"tools").exists())
            self.assertFalse((root/"submissions").exists())

    def test_mixed_task_token_unknown_ref_and_path_override_reject_before_slot(self):
        first, second = self.tasks
        for override in ({"task_token": first["task_token"]}, {"task_ref": "t."+"0"*24}, {"task_ref": "../../private"}, {"run_dir": "/private/tmp"}):
            response = self.call(second, "research_submit", draft=company_draft(), **override)
            self.assertTrue(response["isError"])
        self.assertFalse((self.root/"company/tasks"/second["task_ref"]/"submissions").exists())
        response = self.call(second, "research_query", evidence_ids=[second["task"]["allowed_evidence_ids"][0]])
        self.assertFalse(response["isError"])

    def test_concurrent_business_calls_preserve_per_task_receipts(self):
        def query(task):
            return self.call(task, "research_query", evidence_ids=[task["task"]["allowed_evidence_ids"][0]])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(query, self.tasks))
        self.assertTrue(all(not result["isError"] for result in results))
        for task in self.tasks:
            events = list((self.root/"company/tasks"/task["task_ref"]/"tools").glob("*.json"))
            self.assertEqual(len(events), 1)
            self.assertEqual(json.loads(events[0].read_text())["task_id"], task["task"]["task_id"])

    def test_two_reports_and_draft_slots_remain_independent(self):
        receipts = []
        for task in self.tasks:
            ref = task["task"]["allowed_evidence_ids"][0]
            self.call(task,"research_query",evidence_ids=[ref])
            text = json.dumps(company_draft()).replace("ev-revenue", ref)
            response = self.call(task,"research_submit",draft=json.loads(text))
            self.assertFalse(response["isError"], response)
            result = json.loads(response["content"][0]["text"])
            self.assertTrue(result["accepted"], result)
            receipts.append(result["draft_ref"])
        self.assertNotEqual(*receipts)
        for task, receipt in zip(self.tasks, receipts):
            response=self.call(task,"research_read_submission",draft_ref=receipt)
            self.assertFalse(response["isError"])
            report=json.loads(response["content"][0]["text"])
            self.assertEqual(report["security"],task["task"]["security"])
        self.assertTrue(self.call(self.tasks[1],"research_read_submission",draft_ref=receipts[0])["isError"])

    def test_normal_business_needs_no_observation_and_old_connection_rejects_new_task(self):
        changed = build_common_stock_council_request(self.input, request_id="new-request",
                                                   research_question=self.request["research_question"])
        prepared = prepare_connection(self.root/"new-company", research_input=self.input, gate=self.gate,
                                      role="runtime_company_analyst", research_request=changed)
        current = ResearchConnection(self.root/"new-company", connection_token=prepared["connection_token"])
        grant = current.prepare_task(security_id=self.tasks[0]["task"]["security"]["security_id"],
                                     capability="COMPANY_RESEARCH")
        shutil.copytree(current.root/"tasks"/grant["task_ref"], self.connection.root/"tasks"/grant["task_ref"])
        before = self.snapshot()
        with patch.object(ResearchConnection, "binding_context", side_effect=AssertionError("not required")):
            for name, arguments in (("research_context", {}),
                                    ("research_query", {"evidence_ids": [grant["task"]["allowed_evidence_ids"][0]]}),
                                    ("research_submit", {"draft": company_draft()})):
                response = self.call(grant, name, **arguments)
                self.assertTrue(response["isError"], response)
                self.assertEqual(response["content"][0]["text"], "NATIVE_RESEARCH_TASK_CONNECTION_MISMATCH")
                self.assertEqual(self.snapshot(), before)
            ref = self.tasks[0]["task"]["allowed_evidence_ids"][0]
            self.assertFalse(self.call(self.tasks[0], "research_query", evidence_ids=[ref])["isError"])
            self.assertFalse(self.call(self.tasks[0], "research_context")["isError"])

    def test_other_request_task_copied_into_connection_still_rejects(self):
        changed = build_common_stock_council_request(self.input, request_id="another-request",research_question=self.request["research_question"])
        other = prepare_connection(self.root/"another",research_input=self.input,gate=self.gate,
                                   role="runtime_company_analyst",research_request=changed)
        connection=ResearchConnection(self.root/"another",connection_token=other["connection_token"])
        grant=connection.prepare_task(security_id=self.tasks[0]["task"]["security"]["security_id"],capability="COMPANY_RESEARCH")
        shutil.copytree(self.root/"another/tasks"/grant["task_ref"],self.root/"company/tasks"/grant["task_ref"])
        with self.assertRaisesRegex(ValueError,"TASK_CONNECTION_MISMATCH"):
            self.connection.task_tools(task_ref=grant["task_ref"],task_token=grant["task_token"])

    def test_role_wrong_capability_and_question_change_do_not_create_tasks(self):
        before = {p.name for p in (self.root/"company/tasks").iterdir()}
        with self.assertRaisesRegex(ValueError,"CAPABILITY_ROLE_MISMATCH"):
            self.connection.prepare_task(security_id=self.tasks[0]["task"]["security"]["security_id"],capability="INDEPENDENT_FIRST_PASS")
        with self.assertRaisesRegex(ValueError,"QUESTION_OUTSIDE_REQUEST"):
            self.connection.prepare_task(security_id=self.tasks[0]["task"]["security"]["security_id"],capability="COMPANY_RESEARCH",research_question="other question")
        self.assertEqual({p.name for p in (self.root/"company/tasks").iterdir()},before)

    def test_skeptic_manifest_and_server_do_not_allow_positive_report_reads(self):
        prepared=prepare_connection(self.root/"skeptic",research_input=self.input,gate=self.gate,
                                    role="runtime_skeptic",research_request=self.request)
        connection=ResearchConnection(self.root/"skeptic",connection_token=prepared["connection_token"])
        task=connection.prepare_task(security_id=self.tasks[0]["task"]["security"]["security_id"],capability="INDEPENDENT_FIRST_PASS")
        listed=dispatch(connection,{"jsonrpc":"2.0","id":1,"method":"tools/list"})
        self.assertNotIn("research_read_reports",{t["name"] for t in listed["result"]["tools"]})
        response=dispatch(connection,{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
            "name":"research_read_reports","arguments":{"task_ref":task["task_ref"],"task_token":task["task_token"],"report_ids":["positive-report"]}}})
        self.assertTrue(response["result"]["isError"])

    def test_actual_stdio_observation_without_cio_task_is_read_only_and_redacted(self):
        from product.tools.research import _write_json
        root = self.root/"stdio-cio"
        prepared = prepare_connection(root, research_input=self.input, gate=self.gate,
            role="runtime_cio", research_request=self.request)
        path = self.root/"cio-environment.json"
        _write_json(path, {"STOCK_AGENT_CIO_CONNECTION": str(root), "STOCK_AGENT_CIO_TOKEN": prepared["connection_token"]})
        def observation(number, expected):
            return {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": {
                "name": "research_connection_context", "arguments": {"expected_connection_hash": expected}}}
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, observation(2, "0"*64),
                    observation(3, prepared["connection"]["connection_hash"]),
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "research_context", "arguments": {}}}]
        env = {k: v for k, v in os.environ.items() if not k.startswith("STOCK_AGENT_")}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
        before = self.snapshot()
        run = subprocess.run([sys.executable, "-B", "-m", "product.mcp.research", "--connection-env-prefix",
            "STOCK_AGENT_CIO", "--connection-env-file", str(path)], cwd=ROOT, env=env,
            input='\n'.join(json.dumps(message) for message in messages)+'\n', text=True,
            capture_output=True, timeout=10, check=True)
        replies = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(len(replies), 4)
        manifest = next(item for item in replies[0]["result"]["tools"] if item["name"] == "research_connection_context")
        self.assertEqual(manifest["inputSchema"], {"type": "object", "additionalProperties": False,
            "required": ["expected_connection_hash"],
            "properties": {"expected_connection_hash": {"type": "string", "pattern": r"^[0-9a-f]{64}$"}}})
        self.assertEqual(manifest["annotations"], {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False})
        self.assertTrue(replies[1]["result"]["isError"])
        self.assertEqual(replies[1]["result"]["content"][0]["text"], "NATIVE_RESEARCH_CONNECTION_EXPECTATION_MISMATCH")
        self.assertFalse(replies[2]["result"]["isError"])
        value = json.loads(replies[2]["result"]["content"][0]["text"])
        self.assertEqual(value["connection_hash"], prepared["connection"]["connection_hash"])
        self.assertEqual(value["role"], "runtime_cio")
        self.assertEqual(value["caller_authentication"], "UNVERIFIED")
        self.assertEqual(len(value), 10)
        self.assertTrue(replies[3]["result"]["isError"])
        for secret in (prepared["connection_token"], str(self.root), self.request["research_question"]):
            self.assertNotIn(secret, run.stdout+run.stderr)
        self.assertEqual(run.stderr, "")
        self.assertFalse((root/"tasks").exists())
        self.assertEqual(self.snapshot(), before)

    def test_actual_stdio_uses_routed_schema_and_rejects_then_recovers(self):
        first,second=self.tasks
        def message(number,task,token):
            return {"jsonrpc":"2.0","id":number,"method":"tools/call","params":{"name":"research_query","arguments":{
                "task_ref":task["task_ref"],"task_token":token,"evidence_ids":[task["task"]["allowed_evidence_ids"][0]]}}}
        messages=[{"jsonrpc":"2.0","id":1,"method":"tools/list"},message(2,second,first["task_token"]),
                  message(3,first,first["task_token"]),message(4,second,second["task_token"])]
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",STOCK_AGENT_COMPANY_CONNECTION=str(self.root/"company"),STOCK_AGENT_COMPANY_TOKEN=self.token)
        run=subprocess.run([sys.executable,"-B","-m","product.mcp.research","--connection-env-prefix","STOCK_AGENT_COMPANY"],
                           cwd=ROOT,env=env,input='\n'.join(json.dumps(m) for m in messages)+'\n',text=True,capture_output=True,timeout=10,check=True)
        replies=[json.loads(line) for line in run.stdout.splitlines()]
        self.assertTrue(replies[1]["result"]["isError"])
        self.assertTrue(all(not reply["result"]["isError"] for reply in replies[2:]))
        for item in replies[0]["result"]["tools"]:
            if item["name"] == "research_prepare_task":
                self.assertEqual(item["inputSchema"]["required"], ["security_id", "capability"])
                self.assertNotIn("preparation_token", item["inputSchema"]["properties"])
                continue
            if item["name"] == "research_connection_context":
                self.assertEqual(item["inputSchema"]["required"], ["expected_connection_hash"])
                self.assertEqual(set(item["inputSchema"]["properties"]), {"expected_connection_hash"})
                self.assertFalse(item["inputSchema"]["additionalProperties"])
                continue
            self.assertIn("task_ref",item["inputSchema"]["required"])
            self.assertIn("task_token",item["inputSchema"]["required"])
        self.assertNotIn(self.token,run.stdout+run.stderr)
        self.assertNotIn(first["task_token"],run.stdout+run.stderr)

    def file_stdio(self, path, *, prefix="STOCK_AGENT_COMPANY", environment=None, binding=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("STOCK_AGENT_")}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
        env.update(environment or {})
        task = self.tasks[0]
        message = {"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{
            "name":"research_context", "arguments":{"task_ref":task["task_ref"], "task_token":task["task_token"]}}}
        return subprocess.run([sys.executable,"-B","-m","product.mcp.research",
            *(binding or ["--connection-env-prefix",prefix]),"--connection-env-file",str(path)],
            cwd=ROOT,env=env,input=json.dumps(message)+"\n",text=True,capture_output=True,timeout=10)

    def connection_file(self, **extra):
        from product.tools.research import _write_json
        path = self.root/"connection-environment.json"
        _write_json(path, {"STOCK_AGENT_COMPANY_CONNECTION":str(self.root/"company"),
                           "STOCK_AGENT_COMPANY_TOKEN":self.token, **extra})
        return path

    def test_private_connection_file_works_without_inherited_credentials_and_ignores_other_keys(self):
        path = self.connection_file(PYTHONPATH="/not-an-import-path", STOCK_AGENT_MARKET_TOKEN="unrelated-private-value")
        before = path.read_bytes()
        result = self.file_stdio(path, environment={"STOCK_AGENT_COMPANY_CONNECTION":"/wrong-connection",
                                                   "STOCK_AGENT_COMPANY_TOKEN":"wrong-inherited-token"})
        self.assertEqual(result.returncode,0,result.stderr)
        reply = json.loads(result.stdout)["result"]
        self.assertFalse(reply["isError"],reply)
        context = json.loads(reply["content"][0]["text"])
        self.assertEqual(context["role"],"runtime_company_analyst")
        self.assertEqual(path.read_bytes(),before)
        self.assertNotIn(self.token,result.stdout+result.stderr)
        self.assertNotIn("unrelated-private-value",result.stdout+result.stderr)
        self.assertFalse((self.root/"company/tasks"/self.tasks[0]["task_ref"]/"tools").exists())

    def test_private_file_rejects_permissions_symlinks_missing_and_malformed_without_environment_fallback(self):
        from product.tools.research import _write_json
        good = self.connection_file()
        insecure = self.root/"insecure.json"
        _write_json(insecure,json.loads(good.read_text()))
        insecure.chmod(0o644)
        link = self.root/"link.json"; link.symlink_to(good)
        parent_link = self.root/"linked-parent"; parent_link.symlink_to(self.root,target_is_directory=True)
        public_parent = self.root/"public-parent"; public_parent.mkdir(mode=0o755); public_parent.chmod(0o755)
        _write_json(public_parent/"env.json",json.loads(good.read_text()))
        invalid = self.root/"invalid.json"; invalid.write_text("{not-json"); invalid.chmod(0o600)
        missing_token = self.root/"missing-token.json"
        _write_json(missing_token,{"STOCK_AGENT_COMPANY_CONNECTION":str(self.root/"company")})
        wrong_token = self.root/"wrong-token.json"
        _write_json(wrong_token,{"STOCK_AGENT_COMPANY_CONNECTION":str(self.root/"company"),
                                 "STOCK_AGENT_COMPANY_TOKEN":"x"*43})
        relative_root = self.root/"relative-root.json"
        _write_json(relative_root,{"STOCK_AGENT_COMPANY_CONNECTION":"company","STOCK_AGENT_COMPANY_TOKEN":self.token})
        env = {"STOCK_AGENT_COMPANY_CONNECTION":str(self.root/"company"),"STOCK_AGENT_COMPANY_TOKEN":self.token}
        before = {str(p.relative_to(self.root)) for p in self.root.rglob("*")}
        for path in (insecure,link,parent_link/good.name,public_parent/"env.json",invalid,
                     self.root/"missing.json",missing_token,wrong_token,relative_root,Path("relative.json"),""):
            with self.subTest(path=str(path)):
                result = self.file_stdio(path,environment=env)
                self.assertEqual(result.returncode,2)
                self.assertEqual(result.stdout,"")
                self.assertEqual(result.stderr,"NATIVE_RESEARCH_CONNECTION_REJECTED\n")
                self.assertNotIn(self.token,result.stderr)
                if str(path):
                    self.assertNotIn(str(path),result.stderr)
        self.assertEqual({str(p.relative_to(self.root)) for p in self.root.rglob("*")},before)

    def test_private_connection_file_rejects_role_mismatch_and_legacy_binding(self):
        path = self.connection_file(STOCK_AGENT_SKEPTIC_CONNECTION=str(self.root/"company"),
                                    STOCK_AGENT_SKEPTIC_TOKEN=self.token)
        mismatch = self.file_stdio(path,prefix="STOCK_AGENT_SKEPTIC")
        self.assertEqual(mismatch.returncode,2)
        self.assertEqual(mismatch.stderr,"NATIVE_RESEARCH_CONNECTION_REJECTED\n")
        for binding in (["--connection-root",str(self.root/"company")],
                        ["--task-env-prefix","STOCK_AGENT_COMPANY"]):
            result = self.file_stdio(path,binding=binding)
            self.assertEqual(result.returncode,2)
            self.assertIn("--connection-env-file requires --connection-env-prefix",result.stderr)
        self.assertFalse((self.root/"company/tasks"/self.tasks[0]["task_ref"]/"tools").exists())

    def test_main_thread_prepares_task_through_private_connection_without_manual_secret(self):
        before = {p.name for p in (self.root / "company/tasks").iterdir()}
        arguments = {"security_id": self.tasks[0]["task"]["security"]["security_id"],
                     "capability": "COMPANY_RESEARCH"}
        invalid_connection = ResearchConnection(self.root / "company", connection_token=self.tasks[0]["task_token"])
        rejected = dispatch(invalid_connection, {"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{
            "name":"research_prepare_task", "arguments":arguments}})
        self.assertTrue(rejected["result"]["isError"])
        self.assertEqual({p.name for p in (self.root / "company/tasks").iterdir()}, before)

        secret_argument = dispatch(self.connection, {"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{
            "name":"research_prepare_task", "arguments":{**arguments, "preparation_token":self.token}}})
        self.assertTrue(secret_argument["result"]["isError"])
        self.assertEqual({p.name for p in (self.root / "company/tasks").iterdir()}, before)

        good = dispatch(self.connection, {"jsonrpc":"2.0", "id":1, "method":"tools/call", "params":{
            "name":"research_prepare_task", "arguments":arguments}})
        self.assertFalse(good["result"]["isError"])
        grant = json.loads(good["result"]["content"][0]["text"])
        self.assertEqual(grant["task"]["role"], "runtime_company_analyst")
        self.assertEqual(len({p.name for p in (self.root / "company/tasks").iterdir()}),len(before)+1)
        self.assertNotIn(self.token, json.dumps(grant))

    def test_no_connection_token_rejects_without_task_side_effect(self):
        for token in (None,"bad"):
            with self.assertRaisesRegex(ValueError,"CONNECTION_ACCESS_INVALID"):
                ResearchConnection(self.root/"company",connection_token=token).task_tools(**{k:self.tasks[0][k] for k in ["task_ref","task_token"]})
        self.assertTrue(all(not (self.root/"company/tasks"/task["task_ref"]/"tools").exists() for task in self.tasks))
