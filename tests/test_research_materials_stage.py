from __future__ import annotations

import json
import io
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from product.mcp.live.peer_candidates import build_peer_candidate_pool
from product.mcp.provenance import content_hash
from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError, serve_stdio
from product.runtime.research_materials_stage import (
    DISCOVERY_KINDS,
    ResearchMaterialsStageError,
    STAGE_VERSION,
    _output_schema,
    _verify_merged_peer_gate_time,
    build_research_materials_dispatch_packet,
    build_research_materials_dispatch_message,
    finalize_research_materials_stage,
    launch_research_materials_stage,
    materialize_selected_peers,
    prepare_research_materials_stage,
    require_complete_research_materials_stage,
    serialize_research_materials_dispatch_context,
    validate_material_preparation_output,
)
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash
from product.runtime.multidimensional_stage import (
    MultidimensionalStageError,
    build_multidimensional_dispatch_packet,
    prepare_multidimensional_stage_run,
)
from tests.test_common_stock_research_contracts import gate_for, stock_handoff


ROOT = Path(__file__).resolve().parents[1]


class FakeOpenAlexClient:
    def __init__(self, policy, cache, *, api_key=None):
        self.events = []

    def search(self, *, query, security_id, decision_cutoff):
        self.events.append({"operation": "search", "query_hash": content_hash({"query": query})})
        candidate = {
            "candidate_id": "research-lead-1", "security_id": security_id,
            "query": query, "work_id": "W123", "title": "Public paper",
            "authors": ["Author"], "institution": "Journal",
            "material_type": "SEARCH_LEAD", "publication_date": "2026-01-01",
            "published_at": "2026-01-01T00:00:00Z", "retrieved_at": "2026-09-11T11:00:00Z",
            "source_id": "openalex-work-W123", "source_url": "https://openalex.org/W123",
            "doi": None, "content_url": "https://content.openalex.org/works/W123.grobid-xml",
            "verification_status": "LEAD_ONLY", "raw_content_hash": "a" * 64,
        }
        return {"candidates": [candidate], "excluded": [], "raw_content_hash": "a" * 64}

    def fetch(self, candidate):
        self.events.append({"operation": "fetch_content", "work_id": candidate["work_id"]})
        return {
            "schema_version": "verified-research-document/1.0.0",
            "document_id": "research-document-1", "candidate_id": candidate["candidate_id"],
            "security_id": candidate["security_id"], "source_id": candidate["source_id"],
            "title": candidate["title"], "authors": candidate["authors"],
            "institution": candidate["institution"], "material_type": "INDEPENDENT_RESEARCH",
            "source_url": candidate["source_url"], "original_source_url": None,
            "published_at": candidate["published_at"], "as_of": candidate["published_at"],
            "retrieved_at": "2026-09-11T11:01:00Z", "body_hash": "b" * 64,
            "locations": ["Introduction"], "parse_scope": "GROBID_XML_SECTIONS",
            "duplicate_of": None, "revision_of": None,
            "interest_disclosure": "UNKNOWN", "verification_status": "BODY_VERIFIED",
            "sections": [{"section": "Introduction", "text": "Verified body."}],
            "untrusted_content": True, "record_hash": "c" * 64,
        }


def assert_explicit_property_types(test: unittest.TestCase, schema: dict) -> None:
    def walk(value, path="$"):
        if isinstance(value, dict):
            for name, child in value.get("properties", {}).items():
                test.assertTrue(
                    "type" in child or any(key in child for key in ("$ref", "anyOf", "oneOf", "allOf")),
                    f"{path}.properties.{name} 缺少显式类型",
                )
            for name, child in value.items():
                walk(child, f"{path}.{name}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
    walk(schema)


class MissingKeyOpenAlexClient(FakeOpenAlexClient):
    def fetch(self, candidate):
        raise ValueError("PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED")


class UnavailableOpenAlexClient(FakeOpenAlexClient):
    def fetch(self, candidate):
        raise ValueError("PUBLIC_RESEARCH_CONTENT_HTTP_404")


class ResearchMaterialsStageTests(unittest.TestCase):
    @staticmethod
    def mark_material_process_success(run: Path) -> None:
        manifest = json.loads((run / "run_manifest.json").read_text())
        (run / "invocation/process-result.json").write_text(json.dumps({
            "run_id": manifest["run_id"], "process_exit_code": 0,
            "timed_out": False, "stage_status": "PASSED",
            "source_integrity_unchanged": True,
        }))

    def test_required_materials_accepts_complete_source_limited_results(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run = self.prepare(Path(temp), count=1)
            self.write_historical_fixture(run)
            self.mark_material_process_success(run)
            require_complete_research_materials_stage(run)
            manifest_path = run / "research/material-preparation-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["outputs"].pop()
            manifest["manifest_hash"] = canonical_hash({
                key: value for key, value in manifest.items() if key != "manifest_hash"
            })
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ResearchMaterialsStageError, "TASKS_INCOMPLETE"):
                require_complete_research_materials_stage(run)

    def test_required_materials_rejects_failed_result_despite_stage_pass(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run = self.prepare(Path(temp), count=1)
            self.write_historical_fixture(run)
            self.mark_material_process_success(run)
            manifest_path = run / "research/material-preparation-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["outputs"][0]["status"] = "FAILED"
            manifest["manifest_hash"] = canonical_hash({
                key: value for key, value in manifest.items() if key != "manifest_hash"
            })
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ResearchMaterialsStageError, "TASK_FAILED"):
                require_complete_research_materials_stage(run)

    def test_market_discovery_bounds_daily_catalog_without_truncating_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare(root, count=1)
            gate_path = root / "gate.json"
            gate = json.loads(gate_path.read_text())
            daily = [{
                "evidence_id": f"market-daily-{i:05d}", "security_id": "US:MARKET:SPY",
                "semantic_field": "market_context_close", "source_type": "yahoo",
                "source_id": "yahoo-spy", "as_of": "2026-09-10T20:00:00Z",
                "retrieved_at": "2026-09-11T10:00:00Z", "value": "100", "unit": "USD",
            } for i in range(6000)]
            gate["allowed_evidence"].extend(daily)
            gate_path.write_text(json.dumps(gate))
            run = root / "bounded-run"
            prepare_research_materials_stage(
                ROOT, handoff_path=root / "handoff.json", gate_path=gate_path,
                peer_candidate_pool_path=root / "pool.json", run_dir=run,
                run_id="materials-run", model="gpt-5.6-terra", target_concurrency=2,
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(t for t in index["tasks"] if t["preparation_kind"] == "MARKET_RESEARCH_DISCOVERY")
            packet = build_research_materials_dispatch_packet(ROOT, run, task["task_name"])
            selected = [x for x in packet["evidence_catalog"] if x["source_id"] == "yahoo-spy"]
            self.assertEqual(len(selected), 2)
            self.assertLess(len(serialize_research_materials_dispatch_context(packet).encode()), 256 * 1024)
            frozen = json.loads((run / "evidence/gate.json").read_text())
            self.assertEqual(frozen["allowed_evidence"], gate["allowed_evidence"])

    def test_historical_material_context_utf8_limit_and_retired_model_start(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare(Path(temp), count=1)
            task_name = json.loads((run/'research/dispatch-index.json').read_text())['tasks'][0]['task_name']
            packet = build_research_materials_dispatch_packet(ROOT, run, task_name)
            with self.assertRaisesRegex(ResearchMaterialsStageError, 'START_CONTEXT_TOO_LARGE'):
                serialize_research_materials_dispatch_context({**packet, 'instruction': '研'*100000})
            with patch('subprocess.run') as process:
                with self.assertRaisesRegex(ResearchMaterialsStageError, 'NATIVE_HOST_EXECUTION_REQUIRED'):
                    launch_research_materials_stage(ROOT, run_dir=run)
                process.assert_not_called()
            self.assertFalse((run/'invocation').exists())

    def test_company_material_catalog_bounds_history_without_changing_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.prepare(root, count=1)
            gate_path = root / "gate.json"
            gate = json.loads(gate_path.read_text())
            security_id = json.loads((root / "pool.json").read_text())["groups"][0]["security_id"]
            history = [{
                "evidence_id": f"financial-history-{i:05d}", "security_id": security_id,
                "semantic_field": "us-gaap.Revenues", "source_id": "sec-test",
                "as_of": "2026-09-10T20:00:00Z", "retrieved_at": "2026-09-11T10:00:00Z",
                "kind": "financial", "unit": "USD", "value": "100",
                "metadata": {"form": "10-Q", "period_start": "2026-01-01"},
            } for i in range(6000)]
            gate["allowed_evidence"].extend(history)
            gate_path.write_text(json.dumps(gate))
            run = root / "bounded-company-run"
            prepare_research_materials_stage(
                ROOT, handoff_path=root / "handoff.json", gate_path=gate_path,
                peer_candidate_pool_path=root / "pool.json", run_dir=run,
                run_id="materials-run", model="gpt-5.6-terra", target_concurrency=2,
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            for task in index["tasks"]:
                packet = build_research_materials_dispatch_packet(ROOT, run, task["task_name"])
                self.assertLess(len(serialize_research_materials_dispatch_context(packet).encode()), 256 * 1024)
                if task["preparation_kind"] in {"RESEARCH_REPORT_DISCOVERY", "PEER_SELECTION"}:
                    self.assertEqual(sum(f["source_id"] == "sec-test" for f in packet["evidence_catalog"]), 2)
            frozen = json.loads((run / "evidence/gate.json").read_text())
            self.assertEqual(frozen["allowed_evidence"], gate["allowed_evidence"])

    def test_retired_material_hook_cannot_dispatch_or_write_state(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare(Path(temp), count=1, target_concurrency=2)
            before = {path: path.read_bytes() for path in run.rglob("*") if path.is_file()}
            for event in ("PreToolUse", "SubagentStart", "SubagentStop", "Stop"):
                with self.subTest(event=event), self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    handle_hook_event({"hook_event_name": event, "last_assistant_message": "{}"}, environ={
                        "STOCK_AGENT_RUN_DIR": str(run),
                        "STOCK_AGENT_RESEARCH_MATERIALS_STAGE": STAGE_VERSION,
                    })
            self.assertFalse((run / "invocation").exists())
            self.assertFalse((run / "research/material-results").exists())
            self.assertEqual({path: path.read_bytes() for path in run.rglob("*") if path.is_file()}, before)

    def test_launcher_bound_fixture_mcp_exposes_research_tools_without_run_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare(Path(temp), count=1)
            tools = StatelessFixtureTools(default_run_dir=run)
            manifest = {item["name"]: item for item in tools.available_tools()}

        self.assertEqual(
            set(manifest),
            {
                "query", "calculate", "equity_research_attachments.query",
                "research_search", "research_fetch",
            },
        )
        for name in (
            "equity_research_attachments.query", "research_search", "research_fetch",
        ):
            schema = manifest[name]["inputSchema"]
            self.assertNotIn("run_dir", schema["properties"])
            self.assertNotIn("run_dir", schema["required"])
            self.assertIn("run_id", schema["required"])
            self.assertIn("invocation_id", schema["required"])

    def test_material_structured_output_properties_have_types(self) -> None:
        assert_explicit_property_types(self, _output_schema(
            run_id="run", invocation_id="inv", agent="runtime_company_analyst",
            kind="RESEARCH_REPORT_DISCOVERY",
        ))

    def prepare(self, root: Path, count: int = 2, target_concurrency: int = 8, single_stock=False):
        if single_stock:
            from tests.test_single_stock_input import SingleStockCompanyTests
            from product.runtime.hashing import canonical_hash
            handoff, _, gate, _ = SingleStockCompanyTests().prepare_values()
            gate['run_id'] = 'materials-run'
            gate['bundle_hash'] = canonical_hash({k: v for k, v in gate.items() if k != 'bundle_hash'})
        else:
            handoff = stock_handoff(count)
            gate = gate_for(handoff)
        from product.runtime.research_input import research_subjects
        holdings = [
            {"security_id": item["security_id"], "ticker": item["display_symbol"]}
            for item in research_subjects(handoff)
        ]
        observed = "2026-09-11T11:00:00Z"
        rows = []
        for item in holdings:
            rows.append({
                "symbol": item["ticker"], "name": item["ticker"], "market_cap": "100",
                "country": "United States", "ipo_year": 2000, "sector": "Technology",
                "industry": "Semiconductors", "source_id": "nasdaq-screener",
                "as_of": observed, "retrieved_at": observed, "raw_content_hash": "a" * 64,
            })
        rows.append({
            "symbol": "PEER1", "name": "Peer One", "market_cap": "120",
            "country": "United States", "ipo_year": 2001, "sector": "Technology",
            "industry": "Semiconductors", "source_id": "nasdaq-screener",
            "as_of": observed, "retrieved_at": observed, "raw_content_hash": "a" * 64,
        })
        universe = {
            "schema_version": "live-universe/1.0.0", "provider": "nasdaq",
            "source_id": "nasdaq-screener", "source_locator": "https://api.nasdaq.com/api/screener/stocks",
            "request_started_at": observed, "as_of": observed, "retrieved_at": observed,
            "completeness": "COMPLETE", "rows": rows,
            "snapshot_hash": content_hash({"rows": rows, "as_of": observed}),
        }
        pool = build_peer_candidate_pool(holdings, universe=universe)
        handoff_path, gate_path, pool_path = root / "handoff.json", root / "gate.json", root / "pool.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        gate_path.write_text(json.dumps(gate), encoding="utf-8")
        pool_path.write_text(json.dumps(pool), encoding="utf-8")
        run = root / "run"
        prepare_research_materials_stage(
            ROOT, **({'research_input_path': handoff_path} if single_stock else {'handoff_path': handoff_path}), gate_path=gate_path,
            peer_candidate_pool_path=pool_path, run_dir=run,
            run_id="materials-run", model="gpt-5.6-terra",
            target_concurrency=target_concurrency,
        )
        return run.resolve()

    def write_historical_fixture(self, run: Path, *, transform=None) -> dict:
        """真实本地工具产物加显式历史归集向量；不是当前宿主执行证明。"""
        from tests.test_material_semantic_handoff import MaterialSemanticHandoffTests
        helper = MaterialSemanticHandoffTests()
        index = json.loads((run / "research/dispatch-index.json").read_text())
        tools = StatelessFixtureTools(default_run_dir=run)

        def call(name, arguments):
            request = {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
            stdout = io.StringIO()
            with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", stdout):
                serve_stdio(tools_override=tools)
            response = json.loads(stdout.getvalue())
            self.assertNotIn("error", response)
            return response["result"]["structuredContent"]

        events = []
        for task in index["tasks"]:
            packet = build_research_materials_dispatch_packet(ROOT, run, task["task_name"])
            identity = {key: task[key] for key in ("run_id", "invocation_id", "agent", "security_id")}
            if task["preparation_kind"] in DISCOVERY_KINDS:
                subject = task["security"]["display_symbol"] or task["security"]["display_name"]
                query = f"{subject} public research"
                call("research_search", {**identity, "decision_cutoff": task["decision_cutoff"], "query": query})
                call("research_fetch", {**identity, "candidate_id": "research-lead-1"})
                output = {
                    "status": "READY", "summary": "已取得一份正文。",
                    "query_intents": [{"query": query, "purpose": "核对公司问题"}],
                    "selections": [{"candidate_id": "research-lead-1", "document_id": "research-document-1", "rationale": "正文相关。"}],
                    "gaps": [],
                }
            else:
                candidates = packet["peer_candidate_group"]["candidates"]
                output = {
                    "status": "READY" if candidates else "SOURCE_LIMITED",
                    "summary": "选择待核实同行，或保留候选目录缺口。", "query_intents": [],
                    "selections": [{"candidate_id": candidates[0]["candidate_id"], "document_id": None, "rationale": "行业分类与规模接近。"}] if candidates else [],
                    "gaps": [] if candidates else [{"reason_code": "NO_PEER_CANDIDATES", "description": "测试目录无同行候选", "impact": "无法做同行研究"}],
                }
            if transform is not None:
                output = transform(task, output)
            try:
                _, binding = helper.save_material_fixture(run, task, output)
            except ResearchMaterialsStageError as exc:
                if transform is None:
                    raise
                capture = {"status": "FAILED", "failure_code": str(exc), "rejected_output_hash": canonical_hash(output)}
            else:
                capture = {"status": "SAVED", "task_id": task["task_id"], **binding}
            events.append({"hook_event_name": "SubagentStop", "output_binding": {"invocation_id": task["invocation_id"]},
                           "output_capture": capture})
        invocation = run / "invocation"
        invocation.mkdir(exist_ok=True)
        (invocation / "subagent-events.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")
        (invocation / "subagent-dispatches.jsonl").write_text("\n".join(
            json.dumps({"task_name": task["task_name"], "decision": "ALLOW"}) for task in index["tasks"]) + "\n")
        return finalize_research_materials_stage(ROOT, run)

    def test_preparation_permissions_are_separate_by_task_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertEqual(len(index["tasks"]), 6)
            research = next(item for item in index["tasks"] if item["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY")
            peer = next(item for item in index["tasks"] if item["preparation_kind"] == "PEER_SELECTION")
            macro = next(item for item in index["tasks"] if item["preparation_kind"] == "MACRO_RESEARCH_DISCOVERY")
            market = next(item for item in index["tasks"] if item["preparation_kind"] == "MARKET_RESEARCH_DISCOVERY")
            research_invocation = json.loads((run / research["invocation_path"]).read_text())
            peer_invocation = json.loads((run / peer["invocation_path"]).read_text())
            self.assertEqual(research_invocation["tool_permissions"], ["public_research.search", "public_research.fetch"])
            self.assertEqual(peer_invocation["tool_permissions"], [])
            for task, capability in ((macro, "MACRO_CONTEXT"), (market, "MARKET_STATE")):
                invocation = json.loads((run / task["invocation_path"]).read_text())
                self.assertEqual(task["agent"], "runtime_market_catalyst")
                self.assertEqual(task["target_capabilities"], [capability])
                self.assertEqual(
                    invocation["tool_permissions"],
                    ["public_research.search", "public_research.fetch"],
                )
                self.assertEqual(invocation["skill"]["name"], "macro-market-analysis")
            self.assertEqual(json.loads((run / "run_manifest.json").read_text())["schema_version"], STAGE_VERSION)
            self.assertIsNotNone(build_research_materials_dispatch_packet(ROOT, run, research["task_name"]))
            packet = build_research_materials_dispatch_packet(ROOT, run, research["task_name"])
            identity = packet["tool_context"]["required_identity_arguments"]
            self.assertEqual(
                identity,
                {
                    "run_id": research["run_id"],
                    "agent": research["agent"],
                    "invocation_id": research["invocation_id"],
                },
            )
            self.assertNotIn("run_dir", identity)

    def test_search_and_fetch_are_bound_to_the_preparation_invocation(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY")
            tools = StatelessFixtureTools(default_run_dir=run)
            identity = {
                "run_id": task["run_id"], "agent": task["agent"],
                "invocation_id": task["invocation_id"], "security_id": task["security_id"],
            }
            search = tools.research_search(
                **identity, decision_cutoff=task["decision_cutoff"], query="AAPL semiconductor demand research"
            )
            fetched = tools.research_fetch(**identity, candidate_id="research-lead-1")
            output = {
                **identity, "preparation_kind": task["preparation_kind"], "status": "READY",
                "summary": "自动搜索并取得一份可定位正文。",
                "queries": [{"query": "AAPL semiconductor demand research", "purpose": "核对需求假设"}],
                "selections": [{"candidate_id": "research-lead-1", "document_id": "research-document-1", "rationale": "正文与核心问题相关。"}],
                "gaps": [], "artifact_refs": [search["artifact_ref"], fetched["artifact_ref"]],
            }
            validate_material_preparation_output(output, task=task, run_dir=run)
            event_log = run / "events/mcp/events.jsonl"
            event_log.parent.mkdir(parents=True, exist_ok=True)
            event_log.write_text("\n".join(json.dumps(event) for event in tools.events) + "\n")
            validate_material_preparation_output(output, task=task, run_dir=run)
            for bad_ref in (
                "research/materials/another-invocation/search-1.json",
                "../outside/search-1.json", "/private/tmp/search-1.json",
            ):
                with self.subTest(bad_ref=bad_ref), self.assertRaisesRegex(
                    ResearchMaterialsStageError, "RESEARCH_MATERIALS_ARTIFACT_REF_INVALID",
                ):
                    validate_material_preparation_output(
                        {**output, "artifact_refs": [*output["artifact_refs"], bad_ref]},
                        task=task, run_dir=run,
                    )
            search_path = run / search["artifact_ref"]
            search_path.write_text(search_path.read_text() + "\n")
            with self.assertRaisesRegex(
                ResearchMaterialsStageError, "RESEARCH_MATERIALS_ARTIFACT_HASH_MISMATCH",
            ):
                validate_material_preparation_output(output, task=task, run_dir=run)
            peer = next(item for item in index["tasks"] if item["preparation_kind"] == "PEER_SELECTION")
            with self.assertRaisesRegex(ToolAccessError, "TOOL_NOT_AUTHORIZED"):
                tools.research_search(
                    run_id=peer["run_id"], agent=peer["agent"], invocation_id=peer["invocation_id"],
                    security_id=peer["security_id"], decision_cutoff=peer["decision_cutoff"], query="forbidden",
                )

    def test_peer_selection_rejects_unknown_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["preparation_kind"] == "PEER_SELECTION")
            output = {
                "run_id": task["run_id"], "invocation_id": task["invocation_id"],
                "agent": task["agent"], "preparation_kind": task["preparation_kind"],
                "security_id": task["security_id"], "status": "READY", "summary": "选择同行。",
                "queries": [], "selections": [{"candidate_id": "missing", "document_id": None, "rationale": "错误候选"}],
                "gaps": [], "artifact_refs": [],
            }
            with self.assertRaisesRegex(Exception, "PEER_SELECTION_INVALID"):
                validate_material_preparation_output(output, task=task, run_dir=run)

    def test_missing_content_key_is_configuration_block_not_source_limit(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", MissingKeyOpenAlexClient
        ):
            run = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY")
            tools = StatelessFixtureTools(default_run_dir=run)
            identity = {
                "run_id": task["run_id"], "agent": task["agent"],
                "invocation_id": task["invocation_id"], "security_id": task["security_id"],
            }
            query = "AAPL demand research"
            search = tools.research_search(
                **identity, decision_cutoff=task["decision_cutoff"], query=query
            )
            failed = tools.research_fetch(**identity, candidate_id="research-lead-1")
            self.assertEqual(failed["status"], "BLOCKED_CONFIGURATION")
            blocked = {
                **identity, "preparation_kind": task["preparation_kind"],
                "status": "BLOCKED_CONFIGURATION", "summary": "正文读取缺少外置凭证。",
                "queries": [{"query": query, "purpose": "核对需求假设"}],
                "selections": [],
                "gaps": [{"reason_code": failed["failure_code"], "description": "正文配置未就绪。", "impact": "不能声称已读研报。"}],
                "artifact_refs": [search["artifact_ref"], failed["artifact_ref"]],
            }
            validate_material_preparation_output(blocked, task=task, run_dir=run)
            masqueraded = dict(blocked, status="SOURCE_LIMITED")
            with self.assertRaisesRegex(Exception, "MASQUERADED"):
                validate_material_preparation_output(masqueraded, task=task, run_dir=run)

    def test_source_failure_requires_actual_attempt_and_gap(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", UnavailableOpenAlexClient
        ):
            run = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY")
            tools = StatelessFixtureTools(default_run_dir=run)
            identity = {
                "run_id": task["run_id"], "agent": task["agent"],
                "invocation_id": task["invocation_id"], "security_id": task["security_id"],
            }
            query = "AAPL demand research"
            search = tools.research_search(
                **identity, decision_cutoff=task["decision_cutoff"], query=query
            )
            failed = tools.research_fetch(**identity, candidate_id="research-lead-1")
            limited = {
                **identity, "preparation_kind": task["preparation_kind"],
                "status": "SOURCE_LIMITED", "summary": "候选正文不可取得。",
                "queries": [{"query": query, "purpose": "核对需求假设"}],
                "selections": [],
                "gaps": [{"reason_code": failed["failure_code"], "description": "正文不可取得。", "impact": "无法进行研报比较。"}],
                "artifact_refs": [search["artifact_ref"], failed["artifact_ref"]],
            }
            validate_material_preparation_output(limited, task=task, run_dir=run)
            without_search = dict(limited, queries=[])
            with self.assertRaisesRegex(Exception, "QUERY_PROOF_MISMATCH"):
                validate_material_preparation_output(without_search, task=task, run_dir=run)

    def test_selected_document_artifact_must_be_declared(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY")
            tools = StatelessFixtureTools(default_run_dir=run)
            identity = {
                "run_id": task["run_id"], "agent": task["agent"],
                "invocation_id": task["invocation_id"], "security_id": task["security_id"],
            }
            query = "AAPL demand research"
            search = tools.research_search(
                **identity, decision_cutoff=task["decision_cutoff"], query=query
            )
            tools.research_fetch(**identity, candidate_id="research-lead-1")
            value = {
                **identity, "preparation_kind": task["preparation_kind"], "status": "READY",
                "summary": "已取得正文。", "queries": [{"query": query, "purpose": "核对需求"}],
                "selections": [{"candidate_id": "research-lead-1", "document_id": "research-document-1", "rationale": "相关"}],
                "gaps": [], "artifact_refs": [search["artifact_ref"]],
            }
            with self.assertRaisesRegex(Exception, "SELECTED_DOCUMENT_REF_MISSING"):
                validate_material_preparation_output(value, task=task, run_dir=run)

    def test_historical_finalizer_forms_complete_material_manifest(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run = self.prepare(Path(temp), count=1)
            result = self.write_historical_fixture(run)
            self.assertEqual(result["status"], "PASSED")
            manifest = json.loads((run / "research/material-preparation-manifest.json").read_text())
            self.assertEqual(len(manifest["outputs"]), 4)
            self.assertEqual(
                {item["preparation_kind"] for item in manifest["outputs"]},
                {
                    "RESEARCH_REPORT_DISCOVERY", "PEER_SELECTION",
                    "MACRO_RESEARCH_DISCOVERY", "MARKET_RESEARCH_DISCOVERY",
                },
            )

    def test_finalizer_preserves_one_failed_preparation_as_explicit_gap(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run = self.prepare(Path(temp), count=1)
            def reject_one(task, draft):
                if task["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY":
                    draft["selections"][0]["document_id"] = "unknown-document"
                return draft
            result = self.write_historical_fixture(run, transform=reject_one)
            self.assertEqual(result["status"], "PASSED")
            self.assertTrue(result["coverage_complete"])
            self.assertEqual(len(result["failed"]), 1)
            manifest = json.loads((run / "research/material-preparation-manifest.json").read_text())
            failed = next(item for item in manifest["outputs"] if item["status"] == "FAILED")
            self.assertIsNone(failed["output_ref"])
            self.assertEqual(failed["selections"], [])
            self.assertEqual(failed["failure_code"], "RESEARCH_MATERIALS_DOCUMENT_SELECTION_INVALID:selections[0]")
            self.mark_material_process_success(run)
            with self.assertRaisesRegex(ResearchMaterialsStageError, "TASK_FAILED"):
                require_complete_research_materials_stage(run)

    def test_selected_peer_is_materialized_and_merged_only_after_collection_gate(self):
        self.selected_peer_case()

    def test_single_stock_selected_peer_reaches_actual_industry_consumer(self):
        self.selected_peer_case(single_stock=True)

    def test_selected_peer_memory_keeps_view_labels_out_of_source_facts(self):
        self.selected_peer_case(with_memory=True)

    def test_single_stock_peer_memory_keeps_view_labels_out_of_source_facts(self):
        self.selected_peer_case(single_stock=True, with_memory=True)

    def selected_peer_case(self, single_stock=False, with_memory=False):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            root = Path(temp)
            run = self.prepare(root, count=1, single_stock=single_stock)
            self.write_historical_fixture(run)
            if single_stock:
                self.mark_material_process_success(run)

            def fake_collector(portfolio_path, *, access_path, output_dir, cache_root, sec_user_agent):
                del access_path, cache_root, sec_user_agent
                portfolio = json.loads(Path(portfolio_path).read_text())
                output_dir.mkdir(parents=True)
                snapshot = {"snapshot_hash": "s" * 64, "gaps": [], "portfolio": portfolio,
                            "decision_cutoff": "2026-09-11T11:00:00Z"}
                (output_dir / "snapshot.json").write_text(json.dumps(snapshot))
                (output_dir / "calendar.json").write_text("{}")
                return {
                    "snapshot_path": str(output_dir / "snapshot.json"),
                    "calendar_lock": str(output_dir / "calendar.json"),
                }

            peer_fact = {
                "evidence_id": "peer-price", "security_id": "US:COMMON_STOCK:PEER1",
                "semantic_field": "historical_close_price", "value": "100", "unit": "USD",
                "source_id": "synthetic-peer", "source_type": "yahoo",
                "as_of": "2026-09-11T11:00:00Z", "published_at": "2026-09-11T11:00:00Z",
                "retrieved_at": "2026-09-11T11:00:00Z",
            }
            if with_memory:
                peer_fact.update(freshness_status="FRESH", freshness_policy_version="test/1.0.0")
            peer_gate = {
                "bundle_hash": "p" * 64, "decision_cutoff": "2026-09-11T11:00:00Z",
                "input_evidence_ids": ["peer-price"], "allowed_evidence": [peer_fact],
                "allowed_evidence_ids": ["peer-price"], "excluded": [],
                "excluded_evidence_ids": [],
            }
            access_path = root / "access.json"
            access_path.write_text(json.dumps([{
                "operator_approval": {
                    "record": {"scope": {"max_positions": 3}}
                }
            }]), encoding="utf-8")
            with patch(
                "product.runtime.evidence_gate.run_live_evidence_gate",
                return_value=SimpleNamespace(artifact=peer_gate),
            ), patch("product.mcp.live.market.load_locked_calendar", return_value=object()):
                output = materialize_selected_peers(
                    run, source_access_path=access_path, cache_root=root / "cache",
                    sec_user_agent="test", output_dir=run / "research/peer-materialization",
                    collector=fake_collector,
                    memory_root=root / "memory" if with_memory else None,
                )
            self.assertEqual(output["status"], "FROZEN")
            self.assertEqual(output["evidence_ids"], ["peer-price"])
            merged = json.loads((run / "research/peer-materialization/gate.json").read_text())
            self.assertIn("peer-price", merged["allowed_evidence_ids"])
            self.assertEqual(output["base_gate_content_hash"], merged["base_gate_content_hash"])
            if with_memory:
                from product.runtime.research_memory import ResearchMemory, VIEW_CONTEXT_FIELDS, fact_content_hash
                memory = ResearchMemory(root / "memory")
                persisted = memory.current_facts("US:COMMON_STOCK:PEER1", peer_gate["decision_cutoff"])
                self.assertEqual(len(persisted), 1)
                self.assertFalse(VIEW_CONTEXT_FIELDS.intersection(persisted[0]))
                for key, value in peer_fact.items():
                    if key not in VIEW_CONTEXT_FIELDS:
                        self.assertEqual(persisted[0][key], value)
                self.assertEqual(next(item for item in merged['allowed_evidence']
                                      if item['evidence_id'] == 'peer-price'), peer_fact)
                view = json.loads((run / 'research/peer-materialization/peer-views/PEER1.json').read_text())
                self.assertEqual(len(view['selected_fact_versions']), 1)
                self.assertEqual(view['selected_fact_versions'], [fact_content_hash(persisted[0])])
            formal = root / "formal-with-peer"
            input_args = {'handoff_path': run / 'audit/portfolio-handoff.json'}
            if single_stock:
                from product.runtime.single_stock_input import freeze_latest_research_request
                original = json.loads((run / 'audit/single-stock-request.json').read_text())
                final = freeze_latest_research_request(original, resolved_cutoff=merged['decision_cutoff'])
                (root / 'final-request.json').write_text(json.dumps(final))
                input_args = {'research_input_path': root / 'final-request.json'}
            prepare_multidimensional_stage_run(
                ROOT, **input_args,
                gate_path=run / "research/peer-materialization/gate.json",
                run_dir=formal, run_id="materials-run", model="gpt-5.6-terra",
                research_materials_run_path=run,
            )
            index = json.loads((formal / "research/dispatch-index.json").read_text())
            industry = next(item for item in index["tasks"] if item["capability"] == "INDUSTRY_COMPARISON")
            packet = build_multidimensional_dispatch_packet(
                ROOT, formal, industry["task_name"], include_dependency_reports=False
            )
            self.assertIn("peer-price", packet["allowed_evidence_ids"])
            self.assertEqual(packet["selected_peer_candidates"][0]["materialization_status"], "FROZEN")
            self.assertIn("同一指标、相近期间长度", packet["instruction"])
            self.assertIn("不同公司的收入与毛利", packet["instruction"])
            if single_stock:
                self.assertNotIn('半导体', packet['instruction'])
            else:
                self.assertIn("仅写半导体供应商、电子系统需求等行业共性不算回答", packet["instruction"])
            self.assertIn("无可核实交集或资料不足时说明依据与具体gap", packet["instruction"])
            self.assertIn("不得为满足格式虚构交集", packet["instruction"])
            self.assertIn("不得用当前财年标签替代历史变更的发生财年", packet["instruction"])
            view_path = run / "research/peer-materialization/final-view.json"
            final_view = json.loads(view_path.read_text())
            self.assertEqual(final_view["gate_hash"], merged["bundle_hash"])
            if single_stock:
                self.assertEqual(packet['identity']['input_kind'], 'SINGLE_STOCK_RESEARCH')
                self.assertFalse((formal / 'audit/portfolio-handoff.json').exists())
                return
            # 冻结资料用新执行身份复用时，真正的材料/同行导入不打桩。
            source_paths = [
                run / "research/peer-materialization/gate.json", view_path,
                run / "research/peer-materialization/peer-materialization-manifest.json",
            ]
            original_bytes = {path: path.read_bytes() for path in source_paths}
            rebound_run = root / "formal-new-identity"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=run / "audit/portfolio-handoff.json",
                gate_path=source_paths[0], run_dir=rebound_run,
                run_id="new-frozen-input-consumer", model="gpt-5.6-terra",
                research_materials_run_path=run, reuse_frozen_gate=True,
            )
            rebound_gate = json.loads((rebound_run / "evidence/gate.json").read_text())
            rebound_manifest = json.loads((rebound_run / "run_manifest.json").read_text())
            self.assertEqual(rebound_gate["run_id"], "new-frozen-input-consumer")
            self.assertNotEqual(rebound_gate["bundle_hash"], merged["bundle_hash"])
            self.assertEqual(rebound_gate["allowed_evidence"], merged["allowed_evidence"])
            self.assertEqual(rebound_gate["decision_cutoff"], merged["decision_cutoff"])
            self.assertEqual(rebound_manifest["gate_input_binding"]["source_gate_hash"], merged["bundle_hash"])
            from product.runtime.evidence_gate import validate_frozen_gate_binding, FixtureValidationError
            validate_frozen_gate_binding(rebound_run, rebound_manifest, rebound_gate)
            rebound_gate["decision_cutoff"] = "2026-09-12T00:00:00Z"
            from product.runtime.hashing import legacy_envelope_hash
            rebound_gate["bundle_hash"] = legacy_envelope_hash(rebound_gate, hash_field="bundle_hash")
            with self.assertRaisesRegex(FixtureValidationError, "FROZEN_GATE_BINDING_INVALID"):
                validate_frozen_gate_binding(rebound_run, rebound_manifest, rebound_gate)
            self.assertEqual({path: path.read_bytes() for path in source_paths}, original_bytes)
            with self.assertRaisesRegex(MultidimensionalStageError, "GATE_RUN_MISMATCH"):
                prepare_multidimensional_stage_run(
                    ROOT, handoff_path=run / "audit/portfolio-handoff.json",
                    gate_path=source_paths[0], run_dir=root / "implicit-rebind",
                    run_id="unapproved-new-identity", model="gpt-5.6-terra",
                    research_materials_run_path=run,
                )
            for field in ("gate_hash", "allowed_evidence_ids"):
                with self.subTest(rebound_source_tamper=field):
                    tampered_view = {**final_view, field: "wrong-gate" if field == "gate_hash" else []}
                    tampered_view["view_hash"] = legacy_envelope_hash(tampered_view, hash_field="view_hash")
                    materialization = json.loads(original_bytes[source_paths[2]])
                    materialization["final_view_hash"] = tampered_view["view_hash"]
                    materialization["materialization_hash"] = legacy_envelope_hash(materialization, hash_field="materialization_hash")
                    view_path.write_text(json.dumps(tampered_view))
                    source_paths[2].write_text(json.dumps(materialization))
                    with self.assertRaisesRegex(MultidimensionalStageError, "PEER_FINAL_VIEW_INVALID"):
                        prepare_multidimensional_stage_run(
                            ROOT, handoff_path=run / "audit/portfolio-handoff.json",
                            gate_path=source_paths[0], run_dir=root / ("tampered-new-" + field),
                            run_id="tampered-new-identity", model="gpt-5.6-terra",
                            research_materials_run_path=run, reuse_frozen_gate=True,
                        )
                    for path in source_paths:
                        path.write_bytes(original_bytes[path])
            final_view["decision_cutoff"] = "2026-09-12T00:00:00Z"
            view_path.write_text(json.dumps(final_view), encoding="utf-8")
            with self.assertRaisesRegex(MultidimensionalStageError,
                                        "MULTIDIMENSIONAL_PEER_FINAL_VIEW_INVALID"):
                prepare_multidimensional_stage_run(
                    ROOT, handoff_path=run / "audit/portfolio-handoff.json",
                    gate_path=run / "research/peer-materialization/gate.json",
                    run_dir=root / "formal-tampered", run_id="materials-run",
                    model="gpt-5.6-terra", research_materials_run_path=run,
                )

    def test_final_peer_gate_rejects_future_fact_even_if_both_source_gates_claim_allowed(self):
        base = {"decision_cutoff": "2026-09-11T11:00:00Z"}
        peer = {"decision_cutoff": "2026-09-11T11:01:00Z"}
        fact = {
            "evidence_id": "future", "source_id": "peer", "as_of": "2026-09-11T11:02:00Z",
            "published_at": "2026-09-11T11:02:00Z", "retrieved_at": "2026-09-11T11:02:00Z",
        }
        with self.assertRaisesRegex(ResearchMaterialsStageError,
                                    "PEER_MATERIALIZATION_FINAL_PIT_LEAKAGE"):
            _verify_merged_peer_gate_time(
                base, peer, [fact], [], observed_at="2026-09-11T11:03:00Z",
            )
        stale = {**fact, "evidence_id": "stale", "as_of": "2026-01-01T00:00:00Z",
                 "published_at": "2026-01-01T00:00:00Z",
                 "retrieved_at": "2026-01-01T01:00:00Z", "freshness_status": "FRESH",
                 "source_type": "sec", "kind": "filing", "usage": "current",
                 "metadata": {"form": "10-Q"}}
        with self.assertRaisesRegex(ResearchMaterialsStageError,
                                    "PEER_MATERIALIZATION_FINAL_FACT_STALE"):
            _verify_merged_peer_gate_time(
                base, peer, [stale], [], observed_at="2026-09-11T11:03:00Z",
            )

    def test_peer_supplement_enters_industry_gate_without_becoming_holding(self):
        from product.mcp.live.research_supplement import build_supplement_fact
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            root = Path(temp)
            run = self.prepare(root, count=1)
            self.write_historical_fixture(run)
            access_path = root / "access.json"
            access_path.write_text(json.dumps([{
                "operator_approval": {"record": {"scope": {"max_positions": 1}}}
            }]), encoding="utf-8")

            def fake_collector(portfolio_path, *, access_path, output_dir, cache_root, sec_user_agent):
                del access_path, cache_root, sec_user_agent
                output_dir.mkdir(parents=True)
                portfolio = json.loads(Path(portfolio_path).read_text())
                (output_dir / "snapshot.json").write_text(json.dumps({
                    "snapshot_hash": "s" * 64, "gaps": [], "portfolio": portfolio,
                    "decision_cutoff": "2026-09-11T11:00:00Z",
                }))
                (output_dir / "calendar.json").write_text("{}")
                return {"snapshot_path": str(output_dir / "snapshot.json"),
                        "calendar_lock": str(output_dir / "calendar.json")}

            peer_gate = {
                "bundle_hash": "p" * 64, "decision_cutoff": "2026-09-11T11:00:00Z",
                "input_evidence_ids": [], "allowed_evidence": [],
                "allowed_evidence_ids": [], "excluded": [], "excluded_evidence_ids": [],
            }
            fact = build_supplement_fact(
                security_id="US:COMMON_STOCK:PEER1", dataset="business_segments",
                semantic_field="moomoo_segment_revenue", value={"segment": "Data Center", "revenue": "42"},
                source_id="moomoo_sg-test", source_family="moomoo_sg",
                source_locator="test:peer1:segment", source_version="test/1.0.0",
                as_of="2026-09-11T10:00:00Z", published_at="2026-09-11T10:00:00Z",
                retrieved_at="2026-09-11T10:30:00Z", raw_content_hash="a" * 64,
            )
            def fake_supplements(positions, **kwargs):
                self.assertTrue(kwargs["peer_scope"])
                self.assertEqual([item["security_id"] for item in positions],
                                 ["US:COMMON_STOCK:PEER1"])
                return {"US:COMMON_STOCK:PEER1": [{
                    "source": "moomoo_sg", "dataset": "business_segments",
                    "status": "AVAILABLE", "failure_code": None, "evidence": [fact],
                    "gaps": [], "limitations": [],
                }]}

            with patch(
                "product.mcp.live.collection.validate_live_collection_configuration",
                return_value=[{"provider": "yahoo"}],
            ), patch(
                "product.mcp.live.research_supplement_collection.capture_public_company_news_result",
                return_value={"source": "moomoo_public_news", "dataset": "research_discovery",
                              "status": "SOURCE_LIMITED", "failure_code": "NO_LEADS",
                              "evidence": [], "gaps": ["NO_LEADS"], "limitations": ["none"]},
            ), patch(
                "product.runtime.evidence_gate.run_live_evidence_gate",
                return_value=SimpleNamespace(artifact=peer_gate),
            ), patch("product.mcp.live.market.load_locked_calendar", return_value=object()):
                materialize_selected_peers(
                    run, source_access_path=access_path, cache_root=root / "cache",
                    sec_user_agent="test", output_dir=run / "research/peer-materialization",
                    collector=fake_collector, peer_supplement_collector=fake_supplements,
                    memory_root=root / "memory",
                )
            merged = json.loads((run / "research/peer-materialization/gate.json").read_text())
            self.assertTrue(any(
                item["security_id"] == "US:COMMON_STOCK:PEER1"
                and item["semantic_field"] == "moomoo_segment_revenue"
                for item in merged["allowed_evidence"]
            ))
            self.assertTrue((run / "research/peer-materialization/peer-views/PEER1.json").is_file())
            self.assertNotIn("US:COMMON_STOCK:PEER1", {
                position["security_id"] for position in json.loads(
                    (run / "audit/portfolio-handoff.json").read_text()
                )["portfolio"]["positions"]
            })

    def test_already_frozen_selected_peer_is_reused_without_duplicate_collection(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            root = Path(temp)
            run = self.prepare(root, count=1)
            gate_path = run / "evidence/gate.json"
            gate = json.loads(gate_path.read_text())
            peer_fact = {
                "evidence_id": "peer-price", "security_id": "US:COMMON_STOCK:PEER1",
                "semantic_field": "historical_close_price", "value": "100", "unit": "USD",
                "source_id": "synthetic-peer", "source_type": "yahoo",
                "as_of": "2026-09-11T11:00:00Z", "published_at": "2026-09-11T11:00:00Z",
                "retrieved_at": "2026-09-11T11:00:00Z",
            }
            gate["allowed_evidence"].append(peer_fact)
            gate["allowed_evidence_ids"].append("peer-price")
            gate.setdefault("input_evidence_ids", list(gate["allowed_evidence_ids"][:-1]))
            gate["input_evidence_ids"].append("peer-price")
            gate["bundle_hash"] = content_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            self.write_historical_fixture(run)
            access_path = root / "access.json"
            access_path.write_text(json.dumps([{
                "operator_approval": {"record": {"scope": {"max_positions": 1}}}
            }]), encoding="utf-8")

            def unexpected_collector(*args, **kwargs):
                self.fail("已冻结同行不应再次采集")

            output = materialize_selected_peers(
                run, source_access_path=access_path, cache_root=root / "cache",
                sec_user_agent="test", output_dir=run / "research/peer-materialization",
                collector=unexpected_collector,
            )
            self.assertEqual(output["status"], "FROZEN")
            self.assertEqual(output["evidence_ids"], ["peer-price"])
            self.assertIsNone(output["snapshot_hash"])
            self.assertEqual(
                output["selected"][0]["materialization_source"], "REUSED_FROZEN_GATE"
            )
            merged = json.loads((run / "research/peer-materialization/gate.json").read_text())
            self.assertEqual(merged["allowed_evidence_ids"].count("peer-price"), 1)

    def test_formal_stage_imports_verified_documents_but_not_unfrozen_peer_facts(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            root = Path(temp)
            materials = self.prepare(root, count=1)
            self.write_historical_fixture(materials)
            formal = root / "formal"
            prepare_multidimensional_stage_run(
                ROOT,
                handoff_path=materials / "audit/portfolio-handoff.json",
                gate_path=materials / "evidence/gate.json",
                run_dir=formal, run_id="materials-run", model="gpt-5.6-terra",
                research_materials_run_path=materials,
            )
            index = json.loads((formal / "research/dispatch-index.json").read_text())
            report_task = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            report_packet = build_multidimensional_dispatch_packet(
                ROOT, formal, report_task["task_name"], include_dependency_reports=False
            )
            self.assertEqual(
                [item["document_id"] for item in report_packet["task"]["allowed_documents"]],
                ["research-document-1"],
            )
            self.assertEqual(
                report_packet["verified_documents"][0]["content"]["document_id"],
                "research-document-1",
            )
            self.assertEqual(report_packet["material_preparation"]["status"], "READY")
            self.assertEqual(
                report_packet["output_schema"]["properties"]["documents"]["items"]["enum"],
                report_packet["task"]["allowed_documents"],
            )
            industry_task = next(item for item in index["tasks"] if item["capability"] == "INDUSTRY_COMPARISON")
            industry_packet = build_multidimensional_dispatch_packet(
                ROOT, formal, industry_task["task_name"], include_dependency_reports=False
            )
            self.assertTrue(industry_packet["selected_peer_candidates"])
            self.assertTrue(all(
                item["materialization_status"] == "NOT_MATERIALIZED"
                for item in industry_packet["selected_peer_candidates"]
            ))
            self.assertFalse(any(
                evidence_id.startswith("candidate:")
                for evidence_id in industry_packet["allowed_evidence_ids"]
            ))
            macro_task = next(item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT")
            market_task = next(item for item in index["tasks"] if item["capability"] == "MARKET_STATE")
            macro_packet = build_multidimensional_dispatch_packet(
                ROOT, formal, macro_task["task_name"], include_dependency_reports=False
            )
            market_packet = build_multidimensional_dispatch_packet(
                ROOT, formal, market_task["task_name"], include_dependency_reports=False
            )
            self.assertEqual(
                macro_packet["verified_documents"][0]["content"]["security_id"],
                "US:MACRO",
            )
            self.assertEqual(
                market_packet["verified_documents"][0]["content"]["security_id"],
                "US:MARKET",
            )
            self.assertEqual(macro_packet["material_preparation"]["status"], "READY")
            self.assertEqual(market_packet["material_preparation"]["status"], "READY")
            self.assertIn("外部观点", macro_packet["instruction"])


if __name__ == "__main__":
    unittest.main()
