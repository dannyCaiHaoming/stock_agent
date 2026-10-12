"""原生用户门禁契约与本地授权接缝；合成宿主/资料，无真人UI或模型质量证明。"""
import json
import os
import select
import subprocess
import sys
import unittest
from unittest.mock import patch

from product.mcp.research import dispatch, company_entry_tool_manifest
from product.tools.single_stock_approval import CONFIG_KEY, NativeSingleStockApproval
from product.tools.single_stock_preparation import KEY, authorize_single_stock_preparation
from product.tools.research_connection import ResearchConnection, prepare_connection, bind_connection_file
from tests import test_native_single_stock_preparation as preparation_fixture
from tests.test_native_single_stock_preparation import SyntheticSources, ROOT, PREFIX, CONTACT, FUTURE
from tests.test_native_dynamic_task_binding import synthetic_request
from tests.test_native_research_tools import frozen_gate
from tests.test_native_research_submission import company_draft


class NativeSingleStockApprovalTests(unittest.TestCase):
    setUp = preparation_fixture.NativeSingleStockPreparationTests.setUp
    tearDown = preparation_fixture.NativeSingleStockPreparationTests.tearDown

    def configure(self):
        values = json.loads(self.path.read_text())
        values[CONFIG_KEY] = {
            "source_access_path": str(self.access), "output_root": str(self.root / "output"),
            "memory_root": str(self.root / "memory"), "cache_root": str(self.root / "cache"),
            "sec_user_agent": CONTACT, "authorization_seconds": 900,
        }
        self.path.write_text(json.dumps(values))
        self.path.chmod(0o600)

    def session(self, name="claude-code", version="2.1.295"):
        session = NativeSingleStockApproval()
        dispatch(self.service, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "clientInfo": {"name": name, "version": version}, "capabilities": {},
        }}, approval=session)
        return session

    def rpc(self, session, name, **arguments):
        return dispatch(self.service, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": name, "arguments": arguments}}, approval=session)["result"]

    def offer(self, session, **arguments):
        result = self.rpc(session, "research_prepare_single_stock", symbol="LITE", **arguments)
        self.assertFalse(result["isError"], result)
        action = json.loads(result["content"][0]["text"])["authorization_action"]
        self.assertNotIn("operator_command", action)
        return action["tool"]

    def test_native_flag_is_boolean_true_and_no_model_approval_or_secret_fields(self):
        manifest = company_entry_tool_manifest()
        flagged = [item for item in manifest if item.get("_meta", {}).get("anthropic/requiresUserInteraction") is True]
        self.assertEqual([item["name"] for item in flagged], ["research_authorize_single_stock"])
        schema = flagged[0]["inputSchema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertFalse(set(schema["properties"]) & {"approved", "consent", "token", "connection_token", "source_access_path"})
        from tests.test_native_host_templates import frontmatter
        for base in ("hosts/claude-code", ".claude"):
            for role in ("runtime_company_analyst", "runtime_market_catalyst", "runtime_skeptic"):
                _, lists, _ = frontmatter(ROOT / f"product/{base}/agents/{role}.md")
                self.assertNotIn("mcp__company__research_authorize_single_stock", lists["tools"])

    def test_accept_calls_original_authorizer_then_prepares_and_returns_company_continuation(self):
        self.configure()
        session = self.session()
        before = self.path.read_bytes()
        action = self.offer(session, question="分析合成公司的经营质量")
        self.assertEqual(self.path.read_bytes(), before)
        with SyntheticSources() as sources, patch("product.tools.single_stock_approval.authorize_single_stock_preparation",
                wraps=authorize_single_stock_preparation) as authorize:
            result = self.rpc(session, action["name"], **action["arguments"])
        self.assertFalse(result["isError"], result)
        self.assertEqual(authorize.call_count, 1)
        self.assertEqual(sources.collect.call_count, 1)
        value = json.loads(result["content"][0]["text"])
        self.assertEqual(value["status"], "FROZEN_COMPANY_BOUND")
        self.assertEqual(value["company_authorization"]["max_native_invocations"], 1)
        self.assertEqual(value["company_authorization"]["expires_at"], action["arguments"]["expires_at"])
        self.assertEqual(value["company_authorization"]["model"], "inherit")
        grant = self.rpc(session, value["next_tool"]["name"], **value["next_tool"]["arguments"])
        self.assertFalse(grant["isError"], grant)
        task = json.loads(grant["content"][0]["text"])
        self.assertEqual(task["task"]["research_question"], action["arguments"]["question"])
        self.assertEqual(task["task"]["capability"], "COMPANY_RESEARCH")
        self.assertNotIn(CONTACT, json.dumps([action, value, grant]))
        self.assertNotIn(str(self.root), json.dumps([action, value, grant]))
        self.assertNotIn(self.service.connection().connection_token, json.dumps([action, value, grant]))
        replay = self.rpc(session, action["name"], **action["arguments"])
        self.assertTrue(replay["isError"])

    def test_decline_host_does_not_execute_flagged_tool_or_continue(self):
        self.configure()
        session = self.session()
        before = self.path.read_bytes()
        with patch("product.tools.single_stock_approval.authorize_single_stock_preparation") as authorize, \
                patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            self.offer(session)
            # 官方原生门禁拒绝时不投递tools/call；不向服务器伪造一个accept/decline参数。
            host_permission_result = {"behavior": "deny"}
            self.assertEqual(host_permission_result["behavior"], "deny")
        authorize.assert_not_called()
        collect.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_unknown_old_uninitialized_or_custom_host_stops_before_grant(self):
        self.configure()
        before = self.path.read_bytes()
        sessions = [NativeSingleStockApproval(), self.session(version="2.1.213"), self.session(name="custom-sdk"),
                    self.session(version="bad"), self.session(version="2.1.214")]
        with patch("product.tools.single_stock_approval.authorize_single_stock_preparation") as authorize:
            for session in sessions[:-1]:
                result = self.rpc(session, "research_prepare_single_stock", symbol="LITE")
                self.assertTrue(result["isError"])
                self.assertEqual(result["content"][0]["text"], "NATIVE_SINGLE_STOCK_HOST_APPROVAL_UNSUPPORTED")
            self.offer(sessions[-1])
        authorize.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "ALREADY_INITIALIZED"):
            sessions[1].initialize({})

    def test_model_approved_text_and_unissued_ref_do_not_authorize(self):
        self.configure()
        session = self.session()
        action = self.offer(session)
        before = self.path.read_bytes()
        with patch("product.tools.single_stock_approval.authorize_single_stock_preparation") as authorize:
            for fields in ({"approved": True}, {"consent": "用户已批准"}, {"connection_token": "x" * 43},
                           {"approval_ref": "a." + "0" * 32}):
                result = self.rpc(session, action["name"], **{**action["arguments"], **fields})
                self.assertTrue(result["isError"])
        authorize.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_scope_mismatch_expiry_and_replaced_prompt_stop_without_grant(self):
        self.configure()
        before = self.path.read_bytes()
        with patch("product.tools.single_stock_approval.authorize_single_stock_preparation") as authorize:
            for fields in ({"symbol": "MRVL"}, {"question": "不同问题"}, {"expires_at": FUTURE},
                           {"source_budgets": "sec=9999"}):
                session = self.session()
                action = self.offer(session)
                self.assertTrue(self.rpc(session, action["name"], **{**action["arguments"], **fields})["isError"])
                self.assertTrue(self.rpc(session, action["name"], **action["arguments"])["isError"])
            session = self.session()
            action = self.offer(session)
            with patch("product.tools.single_stock_approval._utc_now", return_value=action["arguments"]["expires_at"]):
                result = self.rpc(session, action["name"], **action["arguments"])
            self.assertEqual(result["content"][0]["text"], "NATIVE_SINGLE_STOCK_AUTHORIZATION_EXPIRED")
            old = self.offer(session)
            self.offer(session)
            self.assertTrue(self.rpc(session, old["name"], **old["arguments"])["isError"])
        authorize.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_configuration_source_or_connection_drift_is_not_new_approval(self):
        self.configure()
        initial = self.path.read_bytes()
        sources = self.access.read_bytes()
        with patch("product.tools.single_stock_approval.authorize_single_stock_preparation") as authorize:
            for mutate in ("profile", "source", "paused", "connection", "permissions"):
                session = self.session()
                action = self.offer(session)
                values = json.loads(initial)
                if mutate == "profile":
                    values[CONFIG_KEY]["authorization_seconds"] += 1
                    self.path.write_text(json.dumps(values))
                elif mutate in {"source", "paused"}:
                    access = json.loads(sources)
                    if mutate == "source":
                        access[0]["request_budget"] += 1
                    else:
                        access[0]["operator_approval"]["status"] = "PAUSED"
                    self.access.write_text(json.dumps(access))
                elif mutate == "connection":
                    values[PREFIX + "_TOKEN"] = "x" * 43
                    self.path.write_text(json.dumps(values))
                else:
                    self.path.chmod(0o644)
                self.assertTrue(self.rpc(session, action["name"], **action["arguments"])["isError"])
                self.path.chmod(0o600)
                self.path.write_bytes(initial)
                self.access.write_bytes(sources)
        authorize.assert_not_called()
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_missing_local_configuration_is_specific_and_never_requests_cli_or_secrets(self):
        result = self.rpc(self.session(), "research_prepare_single_stock", symbol="LITE")
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], "NATIVE_SINGLE_STOCK_APPROVAL_CONFIGURATION_REQUIRED")
        for secret in (str(self.root), CONTACT, "--source-access"):
            self.assertNotIn(secret, json.dumps(result))

    def test_binding_uses_server_verified_old_hash_and_preserves_other_roles(self):
        self.configure()
        request = synthetic_request("MRVL")
        prepared = prepare_connection(self.root / "old", research_input=request, gate=frozen_gate(), role="runtime_company_analyst")
        connection = ResearchConnection(self.root / "old", connection_token=prepared["connection_token"])
        bind_connection_file(self.path, connection, expires_at=FUTURE)
        values = json.loads(self.path.read_text())
        values["STOCK_AGENT_MARKET_TOKEN"] = "unrelated-private-token"
        self.path.write_text(json.dumps(values))
        session = self.session()
        action = self.offer(session)
        with SyntheticSources(), patch("product.tools.single_stock_approval.authorize_single_stock_preparation",
                wraps=authorize_single_stock_preparation) as authorize:
            result = self.rpc(session, action["name"], **action["arguments"])
        self.assertFalse(result["isError"], result)
        self.assertEqual(authorize.call_args.kwargs["expected_connection_hash"], connection.context()["connection_hash"])
        self.assertEqual(json.loads(self.path.read_text())["STOCK_AGENT_MARKET_TOKEN"], "unrelated-private-token")
        self.assertEqual(json.loads((connection.root / "input.json").read_text()), request)

    def test_atomic_environment_and_source_checks_close_authorizer_race(self):
        self.configure()
        initial = self.path.read_bytes()
        access = self.access.read_bytes()
        for change in ("environment", "source"):
            session = self.session()
            action = self.offer(session)
            def raced(*args, **kwargs):
                if change == "environment":
                    values = json.loads(self.path.read_text())
                    values[CONFIG_KEY]["authorization_seconds"] += 1
                    self.path.write_text(json.dumps(values))
                else:
                    values = json.loads(self.access.read_text())
                    values[0]["request_budget"] += 1
                    self.access.write_text(json.dumps(values))
                return authorize_single_stock_preparation(*args, **kwargs)
            with patch("product.tools.single_stock_approval.authorize_single_stock_preparation", side_effect=raced):
                self.assertTrue(self.rpc(session, action["name"], **action["arguments"])["isError"])
            self.assertNotIn(KEY, json.loads(self.path.read_text()))
            self.path.write_bytes(initial)
            self.access.write_bytes(access)
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_cross_session_ref_is_not_an_approval_credential(self):
        self.configure()
        action = self.offer(self.session())
        before = self.path.read_bytes()
        with patch("product.tools.single_stock_approval.authorize_single_stock_preparation") as authorize:
            result = self.rpc(self.session(), action["name"], **action["arguments"])
        self.assertTrue(result["isError"])
        authorize.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_revocation_during_collection_preserves_data_but_never_binds_or_creates_task(self):
        self.configure()
        session = self.session()
        action = self.offer(session)
        from product.runtime.common_stock_data import collect_single_stock_research_data
        def revoke(*args, **kwargs):
            result = collect_single_stock_research_data(*args, **kwargs)
            values = json.loads(self.path.read_text())
            values.pop(CONFIG_KEY)
            self.path.write_text(json.dumps(values))
            return result
        with SyntheticSources(), patch("product.runtime.common_stock_data.collect_single_stock_research_data", side_effect=revoke):
            result = self.rpc(session, action["name"], **action["arguments"])
        self.assertTrue(result["isError"])
        self.assertNotIn(PREFIX + "_CONNECTION", json.loads(self.path.read_text()))
        self.assertTrue(list((self.root / "output").rglob("gate.json")))
        self.assertFalse(list((self.root / "output").rglob("tasks")))

    def test_approved_question_cannot_be_replaced_before_preparation(self):
        self.configure()
        session = self.session()
        action = self.offer(session)
        from product.tools.single_stock_preparation import prepare_single_stock_from_file
        def changed(service, **arguments):
            return prepare_single_stock_from_file(service, **{**arguments, "question": "not the approved question"})
        with patch("product.tools.single_stock_approval.prepare_single_stock_from_file", side_effect=changed), \
                patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            result = self.rpc(session, action["name"], **action["arguments"])
        self.assertTrue(result["isError"])
        collect.assert_not_called()
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_collection_failure_does_not_retry_or_create_task(self):
        self.configure()
        session = self.session()
        action = self.offer(session)
        with SyntheticSources(wrong_exchange=True) as sources:
            self.assertTrue(self.rpc(session, action["name"], **action["arguments"])["isError"])
            self.assertTrue(self.rpc(session, action["name"], **action["arguments"])["isError"])
        self.assertEqual(sources.collect.call_count, 1)
        self.assertTrue(json.loads(self.path.read_text())[KEY]["used"])
        self.assertFalse(list((self.root / "output").rglob("tasks")))

    def test_same_stdio_session_native_approval_to_company_query_submit_and_read_without_cli(self):
        self.configure()
        configs = {path: path.read_bytes() for path in (ROOT / "product/.mcp.json", ROOT / "product/hosts/claude-code/mcp.json")}
        code = "from tests.test_native_single_stock_preparation import SyntheticSources; from product.mcp.research import main; "
        code += "sources = SyntheticSources(); sources.__enter__(); raise SystemExit(main())"
        process = subprocess.Popen([sys.executable, "-B", "-c", code, "--connection-env-prefix", PREFIX,
            "--connection-env-file", str(self.path)], cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        def rpc(method, **params):
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            self.assertTrue(select.select([process.stdout], [], [], 30)[0], "stdio response timeout")
            return json.loads(process.stdout.readline())["result"]
        def call(name, **arguments):
            result = rpc("tools/call", name=name, arguments=arguments)
            self.assertFalse(result["isError"], result)
            return json.loads(result["content"][0]["text"])
        try:
            pid = process.pid
            rpc("initialize", protocolVersion="2025-11-25", clientInfo={"name": "claude-code", "version": "2.1.295"})
            manifest = rpc("tools/list")["tools"]
            operation = call("research_prepare_single_stock", symbol="LITE")["authorization_action"]["tool"]
            selected = next(item for item in manifest if item["name"] == operation["name"])
            self.assertIs(selected["_meta"]["anthropic/requiresUserInteraction"], True)
            self.assertNotIn(KEY, json.loads(self.path.read_text()))
            # 合成宿主模拟真人批准后的投递；不宣称本测试显示了真实Claude UI。
            frozen = call(operation["name"], **operation["arguments"])
            task = call(frozen["next_tool"]["name"], **frozen["next_tool"]["arguments"])
            auth = {key: task[key] for key in ("task_ref", "task_token")}
            context = call("research_context", **auth)
            evidence = call("research_query", **auth, evidence_ids=context["allowed_evidence_ids"][:1])
            self.assertTrue(evidence)
            # 实际研究仍由Company原生角色；这里只提交合成语义以验证原工具接缝。
            evidence_id = context["allowed_evidence_ids"][0]
            draft = json.loads(json.dumps(company_draft()).replace("ev-revenue", evidence_id))
            receipt = call("research_submit", **auth, draft=draft)
            self.assertTrue(receipt["accepted"], receipt)
            report = call("research_read_submission", **auth, draft_ref=receipt["draft_ref"])
            self.assertEqual(report["security"]["display_symbol"], "LITE")
            self.assertEqual(process.pid, pid)
            self.assertEqual({path: path.read_bytes() for path in configs}, configs)
            process.stdin.close()
            process.wait(timeout=10)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(process.stderr.read(), "")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


if __name__ == "__main__":
    unittest.main()
