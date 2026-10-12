"""全新单股入口：合成Provider响应及真实stdio/CLI，不联网、不运行模型。"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, UTC
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from product.mcp.research import dispatch, single_stock_preparation_tool_manifest
from product.runtime.hashing import canonical_hash
from product.tools.research import _write_json
from product.tools.research_connection import ResearchConnectionFile, ResearchConnection, prepare_connection, bind_connection_file
from product.tools.single_stock_preparation import KEY, authorize_single_stock_preparation
from tests.test_native_dynamic_task_binding import synthetic_request
from tests.test_native_research_tools import frozen_gate

ROOT = Path(__file__).resolve().parents[1]
AT = "2026-10-12T00:00:00Z"
NOW = datetime(2026, 10, 12, tzinfo=UTC)
FUTURE = "2099-01-01T00:00:00Z"
PREFIX = "STOCK_AGENT_COMPANY"
CONTACT = "synthetic contact@example.invalid"


def source_access():
    from tests.test_live_admission import approved_access
    from tests.test_live_yahoo_transport import access
    from tests.test_live_nasdaq import access as nasdaq_access
    from product.mcp.live.sec_client import CLIENT_VERSION, ADAPTER_VERSION
    from product.mcp.live.eastmoney_transport import ADAPTER_VERSION as EM_VERSION, AKSHARE_VERSION
    return [approved_access(row) for row in (
        access(), dict(access(), provider="sec", client_version=CLIENT_VERSION,
            adapter_version=ADAPTER_VERSION, domains=["data.sec.gov", "www.sec.gov"], request_budget=20),
        nasdaq_access(), dict(access(), provider="eastmoney", client_version=f"akshare/{AKSHARE_VERSION}",
            adapter_version=EM_VERSION, domains=["63.push2his.eastmoney.com"]),
    )]


class SyntheticSources:
    """仅在测试进程替换传输；身份/解析/Gate/冻结/Memory均执行真实实现。"""
    def __init__(self, symbol="LITE", *, wrong_exchange=False):
        self.symbol, self.wrong_exchange, self.calls = symbol, wrong_exchange, []

    def __enter__(self):
        from product.mcp.live.collection import collect_single_stock_snapshot
        from product.mcp.live.sec_client import SecClient, Response
        from product.mcp.live.nasdaq import NasdaqClient
        from product.mcp.live.market import ExchangeCalendar, normalize_daily_rows
        from product.mcp.live.yahoo_transport import RequestBoundary
        from product.mcp.live.research_supplement_collection import _failure
        from tests.test_live_nasdaq import page
        symbol = self.symbol
        mapping = {"fields": ["cik", "name", "ticker", "exchange"],
                   "data": [[1, "Synthetic test issuer", symbol, "NYSE"]]}
        submissions = {"cik": 1, "filings": {"files": [], "recent": {
            "accessionNumber": ["0000000001-26-000001"], "acceptanceDateTime": ["2026-02-01T12:00:00Z"],
            "form": ["10-K"], "primaryDocument": ["test.htm"], "reportDate": ["2025-12-31"]}}}
        financials = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"val": 120, "start": "2025-01-01", "end": "2025-12-31", "accn": "0000000001-26-000001", "form": "10-K"},
            {"val": 100, "start": "2024-01-01", "end": "2024-12-31", "accn": "0000000001-26-000001", "form": "10-K"}]}}}}}
        html = ('<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">Common Stock</ix:nonNumeric>'
                f'<ix:nonNumeric name="dei:TradingSymbol" contextRef="C">{symbol}</ix:nonNumeric>'
                '<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">NYSE</ix:nonNumeric>'
                '<p>Item 1. Business Synthetic manufacturing.</p><p>Item 1A. Risk Factors Synthetic supplier risk.</p>'
                '<p>Item 7. Management Discussion Synthetic expansion.</p>').encode()
        def transport(url, contact):
            self.calls.append(url)
            body = mapping if "/files/" in url else submissions if "/submissions/" in url else financials if "/companyfacts/" in url else None
            return Response(200, json.dumps(body).encode() if body is not None else html)
        def sec_factory(cache, **kwargs):
            return SecClient(cache, **kwargs, transport=transport, now=lambda: NOW, sleep=lambda _: None, monotonic=lambda: 0)
        def session_factory(policy, *, tickers, state_dir, cache):
            return SimpleNamespace(live_boundary=RequestBoundary(policy, tickers=tickers, cache=cache,
                now=lambda: NOW, sleep=lambda _: None), close=lambda: None)
        def market(securities, *, cache, calendar, session, **kwargs):
            raw = json.dumps({"chart": {"error": None, "result": [{"meta": {
                "symbol": symbol, "instrumentType": "EQUITY", "currency": "USD",
                "exchangeName": "NMS" if self.wrong_exchange else "NYQ", "exchangeTimezoneName": "America/New_York"}}]}}).encode()
            session.live_boundary.request(Mock(return_value=SimpleNamespace(status_code=200, content=raw, headers={})),
                "GET", f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}")
            record = cache.store({"synthetic": "price", "provider": "yahoo"}, b"synthetic price", retrieved_at=AT)
            prices = normalize_daily_rows([{"date": "2026-10-09", "close": 20}],
                security_id=securities[0]["security_id"], ticker=symbol, retrieved_at=AT,
                calendar=calendar, raw_content_hash=record["raw_content_hash"], currency="USD")
            return dict(prices, records={symbol: record})
        def collect(*args, **kwargs):
            return collect_single_stock_snapshot(*args, **kwargs, now=lambda: NOW,
                sec_factory=sec_factory, session_factory=session_factory, market_collector=market,
                calendar_factory=ExchangeCalendar, universe_factory=lambda a, c: NasdaqClient(a, c,
                    transport=lambda *args, **kw: page([symbol], 1, asof="Last price as of Oct 9, 2026"),
                    now=lambda: NOW, sleep=lambda _: None),
                backup_factory=lambda *args: SimpleNamespace(events=[]))
        self.stack = ExitStack()
        self.collect = self.stack.enter_context(patch("product.mcp.live.collection.collect_single_stock_snapshot", side_effect=collect))
        self.stack.enter_context(patch("product.runtime.common_stock_data._utc_now", return_value=AT))
        self.stack.enter_context(patch("product.mcp.live.research_supplement_collection.capture_external_research_results",
                                     return_value={"US:COMMON_STOCK:" + symbol: []}))
        self.stack.enter_context(patch("product.mcp.live.research_supplement_collection.capture_shared_research_results", return_value=[]))
        self.stack.enter_context(patch("product.mcp.live.research_supplement_collection.capture_public_company_news_result",
                                     return_value=_failure("moomoo_sg", "event_context", "SYNTHETIC_SOURCE_LIMITED")))
        for target in ("product.mcp.live.macro.collect_official_macro_snapshot",
                       "product.mcp.live.market_context.collect_market_context_snapshot",
                       "product.mcp.live.options.collect_portfolio_option_snapshots"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("Company入口不得扩大到Market资料采集")))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


class NativeSingleStockPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.path = self.root / "company-connections.json"
        _write_json(self.path, {})
        self.access = self.root / "source-access.json"
        self.access.write_text(json.dumps(source_access()))
        self.access.chmod(0o600)
        for name in ("output", "memory", "cache"):
            (self.root / name).mkdir(mode=0o700)
        self.service = ResearchConnectionFile(self.path, prefix=PREFIX)

    def tearDown(self):
        self.tmp.cleanup()

    def authorize(self, **kwargs):
        return authorize_single_stock_preparation(self.path, symbol="LITE", source_access_path=self.access,
            output_root=self.root / "output", memory_root=self.root / "memory", cache_root=self.root / "cache",
            sec_user_agent=CONTACT, expires_at=kwargs.pop("expires_at", FUTURE), **kwargs)

    def rpc(self, name, **arguments):
        return dispatch(self.service, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}})["result"]

    def prepare(self, **kwargs):
        result = self.rpc("research_prepare_single_stock", symbol="LITE", **kwargs)
        self.assertFalse(result["isError"], result)
        return json.loads(result["content"][0]["text"])

    def test_fresh_request_actually_collects_freezes_binds_and_uses_existing_task_tool(self):
        self.assertEqual(list((self.root / "output").iterdir()), [])
        self.authorize()
        from product.runtime.single_stock_input import resolve_single_stock_identity, freeze_latest_research_request
        with SyntheticSources() as sources, patch("product.runtime.single_stock_input.resolve_single_stock_identity",
                wraps=resolve_single_stock_identity) as identity, patch("product.runtime.single_stock_input.freeze_latest_research_request",
                wraps=freeze_latest_research_request) as freeze:
            prepared = self.prepare()
        self.assertEqual(prepared["status"], "FROZEN_COMPANY_BOUND")
        self.assertTrue(sources.calls)
        self.assertEqual(sources.collect.call_count, 1)
        self.assertGreater(identity.call_count, 0)
        self.assertGreater(freeze.call_count, 0)
        self.assertEqual(prepared["security"]["ticker"], "LITE")
        self.assertEqual(prepared["decision_cutoff"], AT)
        self.assertFalse(prepared["research_started"])
        connection = self.service.connection()
        self.assertEqual(connection.context()["request_hash"],
                         canonical_hash(json.loads((connection.root / "input.json").read_text())))
        self.assertFalse((connection.root / "tasks").exists())
        grant = self.rpc(prepared["next_tool"]["name"], **prepared["next_tool"]["arguments"])
        self.assertFalse(grant["isError"], grant)
        task = json.loads(grant["content"][0]["text"])
        self.assertEqual(task["task"]["security"]["security_id"], "US:COMMON_STOCK:LITE")
        context = self.rpc("research_context", task_ref=task["task_ref"], task_token=task["task_token"])
        self.assertFalse(context["isError"], context)
        self.assertTrue(json.loads(context["content"][0]["text"])["allowed_evidence_ids"])
        for secret in (CONTACT, str(self.root), connection.connection_token):
            self.assertNotIn(secret, json.dumps([prepared, grant]))
        repeated = self.prepare()
        self.assertEqual(repeated["status"], "AUTHORIZATION_REQUIRED")
        self.assertEqual(repeated["reason"], "NATIVE_SINGLE_STOCK_PREPARATION_ALREADY_ATTEMPTED")

    def test_no_authorization_returns_concrete_action_not_missing_materials(self):
        before = self.path.read_bytes()
        with patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            result = self.prepare()
        collect.assert_not_called()
        self.assertEqual(result["status"], "AUTHORIZATION_REQUIRED")
        action = result["authorization_action"]
        self.assertIn("原生逐次用户审批", action["user_message"])
        self.assertNotIn("operator_command", action)
        self.assertIn("requiresUserInteraction", action["required_host"])
        self.assertIn("research_prepare_single_stock", action["resume"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_invalid_or_private_model_arguments_reject_before_attempt(self):
        self.authorize()
        before = self.path.read_bytes()
        with patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            for extra in ({"symbol": "../LITE"}, {"symbol": "US:COMMON_STOCK:LITE"},
                          {"connection_token": "x" * 43}, {"output_dir": str(self.root)},
                          {"source_access": str(self.access)}, {"role": "runtime_company_analyst"}):
                arguments = {"symbol": "LITE", **extra}
                result = self.rpc("research_prepare_single_stock", **arguments)
                self.assertTrue(result["isError"], result)
                self.assertEqual(self.path.read_bytes(), before)
            historical = self.rpc("research_prepare_single_stock", symbol="LITE", cutoff="2026-09-01T00:00:00Z")
            self.assertTrue(historical["isError"])
        collect.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_ticker_expiry_source_pause_and_drift_do_not_collect_or_consume(self):
        self.authorize()
        original = self.path.read_bytes()
        with patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            wrong = self.rpc("research_prepare_single_stock", symbol="MRVL")
            self.assertEqual(json.loads(wrong["content"][0]["text"])["status"], "AUTHORIZATION_REQUIRED")
            with patch("product.tools.single_stock_preparation._utc_now", return_value=FUTURE):
                self.assertEqual(self.prepare()["reason"], "NATIVE_SINGLE_STOCK_AUTHORIZATION_EXPIRED")
            policies = json.loads(self.access.read_text())
            policies[0]["operator_approval"]["status"] = "PAUSED"
            self.access.write_text(json.dumps(policies))
            self.assertEqual(self.prepare()["status"], "AUTHORIZATION_REQUIRED")
            policies[0]["operator_approval"]["status"] = "APPROVED"
            policies[0]["request_budget"] += 1
            self.access.write_text(json.dumps(policies))
            self.assertEqual(self.prepare()["reason"], "NATIVE_SINGLE_STOCK_SOURCE_AUTHORIZATION_CHANGED")
        collect.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_collection_failure_preserves_attempt_does_not_bind_or_retry(self):
        self.authorize()
        with SyntheticSources(wrong_exchange=True) as sources:
            result = self.rpc("research_prepare_single_stock", symbol="LITE")
        self.assertTrue(result["isError"], result)
        self.assertEqual(sources.collect.call_count, 1)
        self.assertTrue(list((self.root / "output").rglob("collection-error.json")))
        values = json.loads(self.path.read_text())
        self.assertTrue(values[KEY]["used"])
        self.assertNotIn(PREFIX + "_CONNECTION", values)
        self.assertFalse(list((self.root / "output").rglob("tasks")))
        with patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            self.assertEqual(self.prepare()["status"], "AUTHORIZATION_REQUIRED")
        collect.assert_not_called()

    def test_specialists_have_no_preparation_tools_and_task_or_other_roles_reject(self):
        from tests.test_native_host_templates import frontmatter
        for base in ("hosts/claude-code", ".claude"):
            for role in ("runtime_company_analyst", "runtime_market_catalyst", "runtime_skeptic"):
                _, fields, _ = frontmatter(ROOT / f"product/{base}/agents/{role}.md")
                self.assertFalse({tool.split("__")[-1] for tool in fields["tools"]}
                    & {"research_prepare_single_stock", "research_prepare_task"})
        other = ResearchConnectionFile(self.path, prefix="STOCK_AGENT_SKEPTIC")
        with patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            rejected = dispatch(other, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "research_prepare_single_stock", "arguments": {"symbol": "LITE"}}})
        self.assertTrue(rejected["result"]["isError"])
        collect.assert_not_called()
        properties = single_stock_preparation_tool_manifest()["inputSchema"]["properties"]
        self.assertEqual(set(properties), {"symbol", "question", "cutoff"})

    def test_expected_freeze_hashes_reject_before_task_creation(self):
        self.authorize()
        with SyntheticSources():
            prepared = self.prepare()
        good = prepared["next_tool"]["arguments"]
        root = self.service.connection().root
        for changed in ({"expected_request_hash": "0" * 64}, {"expected_gate_hash": "0" * 64},
                        {"expected_gate_hash": None}):
            result = self.rpc("research_prepare_task", **{**good, **changed})
            self.assertTrue(result["isError"])
            self.assertFalse((root / "tasks").exists())
        partial = {key: value for key, value in good.items() if key != "expected_gate_hash"}
        self.assertTrue(self.rpc("research_prepare_task", **partial)["isError"])
        self.assertFalse((root / "tasks").exists())
        self.assertFalse(self.rpc("research_prepare_task", **good)["isError"])

    def test_operator_requires_exact_old_binding_and_keeps_other_role(self):
        request = synthetic_request("MRVL")
        gate = frozen_gate()
        # 使用相同合成ALB Gate只作连接授权；本测试不查询或创建业务任务。
        prepared = prepare_connection(self.root / "old", research_input=request, gate=gate, role="runtime_company_analyst")
        connection = ResearchConnection(self.root / "old", connection_token=prepared["connection_token"])
        bind_connection_file(self.path, connection, expires_at=FUTURE)
        values = json.loads(self.path.read_text())
        values["STOCK_AGENT_MARKET_TOKEN"] = "unrelated-private-token"
        self.path.write_text(json.dumps(values))
        before = self.path.read_bytes()
        for expected in (None, "0" * 64):
            with self.assertRaises(ValueError):
                self.authorize(expected_connection_hash=expected)
            self.assertEqual(self.path.read_bytes(), before)
        self.authorize(expected_connection_hash=connection.context()["connection_hash"])
        with SyntheticSources():
            self.assertEqual(self.prepare()["status"], "FROZEN_COMPANY_BOUND")
        self.assertEqual(json.loads(self.path.read_text())["STOCK_AGENT_MARKET_TOKEN"], "unrelated-private-token")
        self.assertEqual(json.loads((connection.root / "input.json").read_text()), request)

    def test_revoked_authorization_after_collection_does_not_bind(self):
        self.authorize()
        from product.runtime.common_stock_data import collect_single_stock_research_data
        def revoke(*args, **kwargs):
            result = collect_single_stock_research_data(*args, **kwargs)
            values = json.loads(self.path.read_text())
            values.pop(KEY)
            self.path.write_text(json.dumps(values))
            return result
        with SyntheticSources(), patch("product.runtime.common_stock_data.collect_single_stock_research_data", side_effect=revoke):
            result = self.rpc("research_prepare_single_stock", symbol="LITE")
        self.assertTrue(result["isError"])
        self.assertNotIn(PREFIX + "_CONNECTION", json.loads(self.path.read_text()))
        self.assertTrue(list((self.root / "output").rglob("gate.json")))
        self.assertFalse(list((self.root / "output").rglob("tasks")))

    def test_private_permissions_symlinks_and_bad_grant_reject_before_collection(self):
        self.authorize()
        original = self.path.read_bytes()
        with patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            self.path.chmod(0o644)
            self.assertTrue(self.rpc("research_prepare_single_stock", symbol="LITE")["isError"])
            self.path.chmod(0o600)
            self.access.chmod(0o644)
            self.assertEqual(self.prepare()["status"], "AUTHORIZATION_REQUIRED")
            self.access.chmod(0o600)
            values = json.loads(original)
            values[KEY]["authorization_hash"] = "0" * 64
            self.path.write_text(json.dumps(values))
            self.assertEqual(self.prepare()["reason"], "NATIVE_SINGLE_STOCK_AUTHORIZATION_INVALID")
            self.path.write_bytes(original)
            link = self.root / "source-link.json"
            link.symlink_to(self.access)
            with self.assertRaises(ValueError):
                authorize_single_stock_preparation(self.path, symbol="LITE", source_access_path=link,
                    output_root=self.root / "output", memory_root=self.root / "memory", cache_root=self.root / "cache",
                    sec_user_agent=CONTACT, expires_at=FUTURE)
        collect.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_expiry_after_collection_retains_frozen_data_but_does_not_bind(self):
        self.authorize()
        from product.runtime.common_stock_data import collect_single_stock_research_data
        with ExitStack() as stack:
            def expire(*args, **kwargs):
                result = collect_single_stock_research_data(*args, **kwargs)
                stack.enter_context(patch("product.tools.single_stock_preparation._utc_now", return_value=FUTURE))
                return result
            with SyntheticSources(), patch("product.runtime.common_stock_data.collect_single_stock_research_data", side_effect=expire):
                result = self.rpc("research_prepare_single_stock", symbol="LITE")
        self.assertTrue(result["isError"])
        self.assertNotIn(PREFIX + "_CONNECTION", json.loads(self.path.read_text()))
        self.assertTrue(list((self.root / "output").rglob("gate.json")))
        self.assertFalse(list((self.root / "output").rglob("operator-grant.json")))

    def test_authorization_content_is_not_forwarded_as_specialist_permission(self):
        self.authorize()
        with SyntheticSources():
            prepared = self.prepare()
        connection = self.service.connection()
        result = self.rpc("research_prepare_task", **prepared["next_tool"]["arguments"])
        grant = json.loads(result["content"][0]["text"])
        task_tools = connection.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "research_prepare_single_stock", "arguments": {"symbol": "LITE"}}}
        with patch("product.runtime.common_stock_data.collect_single_stock_research_data") as collect:
            for tools in (task_tools, connection):
                self.assertTrue(dispatch(tools, request)["result"]["isError"])
        collect.assert_not_called()
        for tools in (task_tools, connection):
            names = {item["name"] for item in dispatch(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}
            self.assertNotIn("research_prepare_single_stock", names)
        self.assertNotIn(KEY, json.dumps(grant))
        self.assertNotIn("source_access_path", json.dumps(grant))
        self.assertNotIn(CONTACT, json.dumps(grant))
        self.assertNotIn(connection.connection_token, json.dumps(grant))

    def test_market_skeptic_and_cio_manifests_are_unchanged(self):
        from product.mcp.research import preparation_tool_manifest
        self.assertEqual(set(preparation_tool_manifest()["inputSchema"]["properties"]),
                         {"security_id", "capability", "benchmark_id", "dependency_grants"})
        request = synthetic_request("MRVL")
        for role, prefix in (("runtime_market_catalyst", "STOCK_AGENT_MARKET"),
                             ("runtime_skeptic", "STOCK_AGENT_SKEPTIC"), ("runtime_cio", "STOCK_AGENT_CIO")):
            root = self.root / role
            prepared = prepare_connection(root, research_input=request, gate=frozen_gate(), role=role)
            connection = ResearchConnection(root, connection_token=prepared["connection_token"])
            values = json.loads(self.path.read_text())
            values.update({prefix + "_CONNECTION": str(root), prefix + "_TOKEN": prepared["connection_token"]})
            self.path.write_text(json.dumps(values))
            service = ResearchConnectionFile(self.path, prefix=prefix)
            message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            self.assertEqual(dispatch(service, message), dispatch(connection, message))
            self.assertNotIn("research_prepare_single_stock", json.dumps(dispatch(service, message)))

    def test_operator_cli_is_private_and_does_not_collect(self):
        command = [sys.executable, "-B", "-m", "product.tools.prepare", "authorize-single-stock", "--symbol", "LITE",
            "--connection-env-file", str(self.path), "--source-access", str(self.access), "--output-root", str(self.root / "output"),
            "--memory-root", str(self.root / "memory"), "--cache-root", str(self.root / "cache"), "--expires-at", FUTURE]
        env = dict(os.environ, SEC_USER_AGENT=CONTACT, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "AUTHORIZED_NOT_COLLECTED")
        self.assertNotIn(CONTACT, result.stdout + result.stderr)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list((self.root / "output").iterdir()), [])
        saved = self.path.read_bytes()
        env["SEC_USER_AGENT"] = ""
        result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "NATIVE_SINGLE_STOCK_AUTHORIZATION_REJECTED\n")
        self.assertEqual(self.path.read_bytes(), saved)

    def test_live_stdio_starts_without_frozen_materials_then_prepares_on_same_pid(self):
        config_paths = (ROOT / "product/.mcp.json", ROOT / "product/hosts/claude-code/mcp.json")
        configs = {path: path.read_bytes() for path in config_paths}
        code = "from tests.test_native_single_stock_preparation import SyntheticSources; from product.mcp.research import main; "
        code += "sources = SyntheticSources(); sources.__enter__(); raise SystemExit(main())"
        command = [sys.executable, "-B", "-c", code, "--connection-env-prefix", PREFIX, "--connection-env-file", str(self.path)]
        process = subprocess.Popen(command, cwd=ROOT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        def rpc(name=None, **arguments):
            message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list" if name is None else "tools/call"}
            if name:
                message["params"] = {"name": name, "arguments": arguments}
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            self.assertTrue(select.select([process.stdout], [], [], 30)[0], "stdio response timeout")
            return json.loads(process.stdout.readline())["result"]
        try:
            pid = process.pid
            manifest = rpc()
            self.assertIn("research_prepare_single_stock", {tool["name"] for tool in manifest["tools"]})
            first = rpc("research_prepare_single_stock", symbol="LITE")
            self.assertTrue(first["isError"])
            self.assertEqual(first["content"][0]["text"], "NATIVE_SINGLE_STOCK_HOST_APPROVAL_UNSUPPORTED")
            self.authorize()
            prepared = rpc("research_prepare_single_stock", symbol="LITE")
            self.assertFalse(prepared["isError"], prepared)
            frozen = json.loads(prepared["content"][0]["text"])
            self.assertEqual(frozen["status"], "FROZEN_COMPANY_BOUND")
            self.assertEqual(rpc(), manifest)
            grant = rpc(frozen["next_tool"]["name"], **frozen["next_tool"]["arguments"])
            self.assertFalse(grant["isError"], grant)
            task = json.loads(grant["content"][0]["text"])
            self.assertFalse(rpc("research_context", task_ref=task["task_ref"], task_token=task["task_token"])["isError"])
            self.assertEqual(process.pid, pid)
            self.assertIsNone(process.poll())
            self.assertEqual({path: path.read_bytes() for path in config_paths}, configs)
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
