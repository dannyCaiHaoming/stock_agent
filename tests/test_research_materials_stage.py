from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from product.mcp.live.peer_candidates import build_peer_candidate_pool
from product.mcp.provenance import content_hash
from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError
from product.runtime.research_materials_stage import (
    STAGE_VERSION,
    _output_schema,
    _parent_output_schema,
    build_research_materials_dispatch_packet,
    build_research_materials_dispatch_message,
    finalize_research_materials_stage,
    materialize_selected_peers,
    prepare_research_materials_stage,
    validate_material_preparation_output,
)
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.multidimensional_stage import (
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
    def test_launcher_bound_fixture_mcp_exposes_research_tools_without_run_dir(self):
        tools = StatelessFixtureTools(default_run_dir=Path("/tmp/bound-research-run"))
        manifest = {item["name"]: item for item in tools.available_tools()}

        self.assertEqual(
            set(manifest),
            {"query", "calculate", "research_search", "research_fetch"},
        )
        for name in ("research_search", "research_fetch"):
            schema = manifest[name]["inputSchema"]
            self.assertNotIn("run_dir", schema["properties"])
            self.assertNotIn("run_dir", schema["required"])
            self.assertIn("run_id", schema["required"])
            self.assertIn("invocation_id", schema["required"])

    def test_parent_and_child_structured_output_properties_have_types(self) -> None:
        assert_explicit_property_types(self, _parent_output_schema("run", 6))
        self.assertEqual(
            ["stage", "run_id", "dispatched", "completed"],
            _parent_output_schema("run", 6)["required"],
        )
        assert_explicit_property_types(self, _output_schema(
            run_id="run", invocation_id="inv", agent="runtime_company_analyst",
            kind="RESEARCH_REPORT_DISCOVERY",
        ))

    def prepare(self, root: Path, count: int = 2):
        handoff = stock_handoff(count)
        gate = gate_for(handoff)
        holdings = [
            {"security_id": item["security_id"], "ticker": item["display_symbol"]}
            for item in handoff["portfolio"]["positions"]
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
            ROOT, handoff_path=handoff_path, gate_path=gate_path,
            peer_candidate_pool_path=pool_path, run_dir=run,
            run_id="materials-run", model="gpt-5.6-terra",
        )
        return run

    def execute_with_hooks(self, run: Path) -> dict:
        invocation = run / "invocation"
        invocation.mkdir(exist_ok=True)
        environment = {
            "STOCK_AGENT_RUN_DIR": str(run),
            "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation / "subagent-events.jsonl"),
            "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation / "subagent-dispatches.jsonl"),
            "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst,runtime_market_catalyst",
            "STOCK_AGENT_RESEARCH_MATERIALS_STAGE": STAGE_VERSION,
        }
        index = json.loads((run / "research/dispatch-index.json").read_text())
        tools = StatelessFixtureTools(default_run_dir=run)
        started = []
        for ordinal, task in enumerate(index["tasks"], 1):
            parent, child, turn = "materials-parent", f"child-{ordinal}", f"turn-{ordinal}"
            pre = {
                "hook_event_name": "PreToolUse", "session_id": parent, "turn_id": turn,
                "tool_name": "spawn_agent", "tool_use_id": f"tool-{ordinal}",
                "cwd": str(ROOT / "product"), "model": "gpt-5.6-terra",
                "permission_mode": "workspace-write",
                "tool_input": {
                    "agent_type": task["agent"], "task_name": task["task_name"],
                    "fork_turns": "none",
                    "message": build_research_materials_dispatch_message(ROOT, run, task["task_name"]),
                },
            }
            dispatch_record, _ = handle_hook_event(pre, environ=environment)
            self.assertEqual(dispatch_record["decision"], "ALLOW")
            start = {
                "hook_event_name": "SubagentStart", "session_id": parent, "turn_id": turn,
                "agent_id": child, "agent_type": task["agent"], "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"), "permission_mode": "read-only",
            }
            start_record, start_response = handle_hook_event(start, environ=environment)
            packet = json.loads(start_response["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(start_record["context_binding"]["task_name"], task["task_name"])
            started.append((task, packet, start))
        for task, packet, start in started:
            identity = {
                "run_id": task["run_id"], "invocation_id": task["invocation_id"],
                "agent": task["agent"], "security_id": task["security_id"],
            }
            if task["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY":
                query = f"{task['security']['display_symbol']} public research"
                search = tools.research_search(
                    **identity, decision_cutoff=task["decision_cutoff"], query=query
                )
                fetched = tools.research_fetch(**identity, candidate_id="research-lead-1")
                output = {
                    **identity, "preparation_kind": task["preparation_kind"], "status": "READY",
                    "summary": "已取得一份正文。",
                    "queries": [{"query": query, "purpose": "核对公司问题"}],
                    "selections": [{"candidate_id": "research-lead-1", "document_id": "research-document-1", "rationale": "正文相关。"}],
                    "gaps": [], "artifact_refs": [search["artifact_ref"], fetched["artifact_ref"]],
                }
            else:
                candidate = packet["peer_candidate_group"]["candidates"][0]
                output = {
                    **identity, "preparation_kind": task["preparation_kind"], "status": "READY",
                    "summary": "选择一个待核实同行。", "queries": [],
                    "selections": [{"candidate_id": candidate["candidate_id"], "document_id": None, "rationale": "行业分类与规模接近。"}],
                    "gaps": [], "artifact_refs": [],
                }
            stop = {
                **start, "hook_event_name": "SubagentStop",
                "last_assistant_message": json.dumps(output, ensure_ascii=False),
                "stop_hook_active": False,
            }
            stop_record, _ = handle_hook_event(stop, environ=environment)
            self.assertEqual(stop_record["output_capture"]["status"], "SAVED")
        return finalize_research_materials_stage(ROOT, run)

    def test_preparation_permissions_are_separate_by_task_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertEqual(len(index["tasks"]), 4)
            research = next(item for item in index["tasks"] if item["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY")
            peer = next(item for item in index["tasks"] if item["preparation_kind"] == "PEER_SELECTION")
            research_invocation = json.loads((run / research["invocation_path"]).read_text())
            peer_invocation = json.loads((run / peer["invocation_path"]).read_text())
            self.assertEqual(research_invocation["tool_permissions"], ["public_research.search", "public_research.fetch"])
            self.assertEqual(peer_invocation["tool_permissions"], [])
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

    def test_hook_dispatch_capture_and_finalizer_form_complete_material_manifest(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run = self.prepare(Path(temp), count=1)
            result = self.execute_with_hooks(run)
            self.assertEqual(result["status"], "PASSED")
            manifest = json.loads((run / "research/material-preparation-manifest.json").read_text())
            self.assertEqual(len(manifest["outputs"]), 2)
            self.assertEqual(
                {item["preparation_kind"] for item in manifest["outputs"]},
                {"RESEARCH_REPORT_DISCOVERY", "PEER_SELECTION"},
            )

    def test_finalizer_preserves_one_failed_preparation_as_explicit_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            run = self.prepare(Path(temp), count=1)
            invocation = run / "invocation"
            invocation.mkdir()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            dispatches = [
                {"task_name": task["task_name"], "decision": "ALLOW"}
                for task in index["tasks"]
            ]
            (invocation / "subagent-dispatches.jsonl").write_text(
                "\n".join(json.dumps(item) for item in dispatches) + "\n",
                encoding="utf-8",
            )
            events = []
            for task in index["tasks"]:
                if task["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY":
                    events.append({
                        "hook_event_name": "SubagentStop",
                        "output_binding": {"invocation_id": task["invocation_id"]},
                        "output_capture": {
                            "status": "FAILED",
                            "failure_code": "RESEARCH_MATERIALS_SEARCH_PROOF_MISSING",
                        },
                    })
                    continue
                packet = build_research_materials_dispatch_packet(
                    ROOT, run, task["task_name"]
                )
                candidate = packet["peer_candidate_group"]["candidates"][0]
                output = {
                    "run_id": task["run_id"],
                    "invocation_id": task["invocation_id"],
                    "agent": task["agent"],
                    "preparation_kind": task["preparation_kind"],
                    "security_id": task["security_id"],
                    "status": "READY",
                    "summary": "选择一个待核实同行。",
                    "queries": [],
                    "selections": [{
                        "candidate_id": candidate["candidate_id"],
                        "document_id": None,
                        "rationale": "行业分类与规模接近。",
                    }],
                    "gaps": [],
                    "artifact_refs": [],
                }
                result_dir = run / "research/material-results/saved-peer"
                result_dir.mkdir(parents=True)
                result_path = result_dir / "preparation-result.json"
                result_path.write_text(json.dumps(output), encoding="utf-8")
                events.append({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED", "task_id": task["task_id"],
                        "path": str(result_path.relative_to(run)),
                    },
                })
            (invocation / "subagent-events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n",
                encoding="utf-8",
            )
            result = finalize_research_materials_stage(ROOT, run)
            self.assertEqual(result["status"], "PASSED")
            self.assertTrue(result["coverage_complete"])
            self.assertEqual(len(result["failed"]), 1)
            manifest = json.loads(
                (run / "research/material-preparation-manifest.json").read_text()
            )
            failed = next(item for item in manifest["outputs"] if item["status"] == "FAILED")
            self.assertIsNone(failed["output_ref"])
            self.assertEqual(failed["selections"], [])
            self.assertEqual(
                failed["failure_code"], "RESEARCH_MATERIALS_SEARCH_PROOF_MISSING"
            )

    def test_selected_peer_is_materialized_and_merged_only_after_collection_gate(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            root = Path(temp)
            run = self.prepare(root, count=1)
            self.execute_with_hooks(run)

            def fake_collector(portfolio_path, *, access_path, output_dir, cache_root, sec_user_agent):
                del access_path, cache_root, sec_user_agent
                portfolio = json.loads(Path(portfolio_path).read_text())
                output_dir.mkdir(parents=True)
                snapshot = {"snapshot_hash": "s" * 64, "gaps": [], "portfolio": portfolio}
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
                )
            self.assertEqual(output["status"], "FROZEN")
            self.assertEqual(output["evidence_ids"], ["peer-price"])
            merged = json.loads((run / "research/peer-materialization/gate.json").read_text())
            self.assertIn("peer-price", merged["allowed_evidence_ids"])
            self.assertEqual(output["base_gate_content_hash"], merged["base_gate_content_hash"])
            formal = root / "formal-with-peer"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=run / "audit/portfolio-handoff.json",
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
            self.execute_with_hooks(run)
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
            self.execute_with_hooks(materials)
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


if __name__ == "__main__":
    unittest.main()
