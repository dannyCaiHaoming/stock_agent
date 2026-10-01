"""资料准备语义草稿与真实 MCP/Hook 接缝；零 LLM、无外部网络。"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime import research_materials_stage as stage
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.fixture_mcp import StatelessFixtureTools, serve_stdio
from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import SchemaValidationError
from tests import test_research_materials_stage as fixtures


class SearchUnavailable(fixtures.FakeOpenAlexClient):
    def search(self, **kwargs):
        raise ValueError("PUBLIC_RESEARCH_SEARCH_HTTP_503")


class MaterialSemanticHandoffTests(unittest.TestCase):
    def prepare(self, root, kind="RESEARCH_REPORT_DISCOVERY"):
        # 此接缝一次只模拟一个子任务；不绕过真实首波派发完成约束。
        run = fixtures.ResearchMaterialsStageTests().prepare(root, count=1, target_concurrency=1)
        index = json.loads((run / "research/dispatch-index.json").read_text())
        task = next(item for item in index["tasks"] if item["preparation_kind"] == kind)
        invocation = run / "invocation"
        invocation.mkdir(exist_ok=True)
        env = {
            "STOCK_AGENT_RUN_DIR": str(run),
            "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation / "subagent-events.jsonl"),
            "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation / "subagent-dispatches.jsonl"),
            "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst,runtime_market_catalyst",
            "STOCK_AGENT_RESEARCH_MATERIALS_STAGE": stage.STAGE_VERSION,
        }
        start = {"session_id": "parent", "turn_id": "turn", "agent_id": "child",
                 "agent_type": task["agent"], "model": "gpt-5.6-terra",
                 "cwd": str(fixtures.ROOT / "product"), "permission_mode": "read-only"}
        pre = {**start, "hook_event_name": "PreToolUse", "tool_name": "spawn_agent",
               "permission_mode": "workspace-write",
               "tool_use_id": "spawn", "tool_input": {"agent_type": task["agent"],
                   "task_name": task["task_name"], "fork_turns": "none",
                   "message": stage.build_research_materials_dispatch_message(fixtures.ROOT, run, task["task_name"])}}
        record, _ = handle_hook_event(pre, environ=env)
        self.assertEqual(record["decision"], "ALLOW")
        record, response = handle_hook_event({**start, "hook_event_name": "SubagentStart"}, environ=env)
        self.assertEqual(record["context_binding"]["status"], "DELIVERED")
        packet = json.loads(response["hookSpecificOutput"]["additionalContext"])
        return run, task, packet, env, start

    def call(self, run, task, name, **extra):
        args = {key: task[key] for key in ("run_id", "agent", "invocation_id", "security_id")}
        args.update(extra)
        request = {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", stdout):
            serve_stdio(stateless=True, default_run_dir=run)
        return json.loads(stdout.getvalue())

    def search(self, run, task):
        response = self.call(run, task, "research_search", decision_cutoff=task["decision_cutoff"], query="Company public research")
        self.assertNotIn("error", response)
        return response["result"]["structuredContent"]

    def fetch(self, run, task):
        response = self.call(run, task, "research_fetch", candidate_id="research-lead-1")
        self.assertNotIn("error", response)
        return response["result"]["structuredContent"]

    def draft(self, status="READY"):
        return {"status": status, "summary": "材料选择及来源限制说明。",
                "query_intents": [{"query": "Company public research", "purpose": "核对核心研究问题"}],
                "selections": ([{"candidate_id": "research-lead-1", "document_id": "research-document-1",
                                  "rationale": "正文与问题相关，需由研究阶段分析。"}] if status == "READY" else []),
                "gaps": ([] if status == "READY" else [{"reason_code": status,
                    "description": "当前未取得正文。", "impact": "不能形成正文支持的结论。"}])}

    def stop(self, env, start, draft):
        record, _ = handle_hook_event({**start, "hook_event_name": "SubagentStop", "stop_hook_active": False,
            "last_assistant_message": json.dumps(draft, ensure_ascii=False)}, environ=env)
        return record

    def test_actual_start_schema_and_stop_assemble_fixed_fields_and_tool_audit(self):
        for kind in sorted(stage.DISCOVERY_KINDS):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
            ):
                run, task, packet, env, start = self.prepare(Path(directory), kind)
                schema = packet["output_schema"]
                self.assertEqual(schema, stage.material_semantic_schema(task))
                for field in ("run_id", "invocation_id", "agent", "artifact_refs", "queries", "security_id"):
                    self.assertNotIn(field, schema["properties"])
                self.assertEqual(packet["submission_guidance"]["format"], "semantic-draft")
                self.search(run, task)
                self.fetch(run, task)
                record = self.stop(env, start, self.draft())
                capture = record["output_capture"]
                self.assertEqual(capture["status"], "SAVED", record)
                formal = json.loads((run / capture["path"]).read_text())
                stage.validate_material_preparation_output(formal, task=task, run_dir=run)
                binding = stage.verify_material_tool_audit(run, task, formal, capture)
                self.assertEqual(binding["tool_audit_hash"], capture["tool_audit_hash"])
                self.assertEqual(formal["summary"], self.draft()["summary"])
                self.assertEqual(len(formal["artifact_refs"]), 3)
                audit = json.loads((run / capture["tool_audit_ref"]).read_text())
                self.assertEqual([item["operation"] for item in audit["attempts"]], ["public_research.search", "public_research.fetch"])

    def test_fetch_failure_and_missing_configuration_keep_actual_attempt_status(self):
        for client, status in ((fixtures.UnavailableOpenAlexClient, "SOURCE_LIMITED"),
                               (fixtures.MissingKeyOpenAlexClient, "BLOCKED_CONFIGURATION")):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", client
            ):
                run, task, _, env, start = self.prepare(Path(directory))
                self.search(run, task)
                self.assertEqual(self.fetch(run, task)["status"], status)
                record = self.stop(env, start, self.draft(status))
                self.assertEqual(record["output_capture"]["status"], "SAVED", record)
                audit = stage.build_material_tool_audit(run, task)
                self.assertEqual(audit["attempts"][-1]["status"], status)
                self.assertIsNotNone(audit["attempts"][-1]["failure_code"])
                if status == "BLOCKED_CONFIGURATION":
                    with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "MASQUERADED"):
                        stage.assemble_material_semantic_draft(self.draft("SOURCE_LIMITED"), task=task, run_dir=run)

    def test_search_failure_is_preserved_not_promoted_to_body(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", SearchUnavailable
        ):
            run, task, _, env, start = self.prepare(Path(directory))
            self.assertEqual(self.search(run, task)["status"], "SOURCE_LIMITED")
            record = self.stop(env, start, self.draft("SOURCE_LIMITED"))
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "DOCUMENT_SELECTION_INVALID"):
                stage.assemble_material_semantic_draft(self.draft(), task=task, run_dir=run)

    def test_repeated_query_and_cached_fetch_are_separate_actual_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
        ):
            run, task, _, _, _ = self.prepare(Path(directory))
            self.search(run, task)
            self.fetch(run, task)
            self.assertTrue(self.fetch(run, task)["cache_hit"])
            self.search(run, task)
            formal, audit = stage.assemble_material_semantic_draft(self.draft(), task=task, run_dir=run)
            self.assertEqual(len(formal["queries"]), 1)
            self.assertEqual(len(audit["attempts"]), 4)
            self.assertEqual([item["ordinal"] for item in audit["attempts"]], [1, 2, 3, 4])
            self.assertTrue(audit["attempts"][2]["cache_hit"])

    def test_unexecuted_missing_and_duplicate_intents_fail_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
        ):
            run, task, _, _, _ = self.prepare(Path(directory))
            self.search(run, task)
            self.fetch(run, task)
            for intents in ([], [{"query": "never executed", "purpose": "说明"}],
                            self.draft()["query_intents"] * 2):
                draft = {**self.draft(), "query_intents": intents}
                before = copy.deepcopy(draft)
                with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "INTENT_NOT_EXECUTED"):
                    stage.assemble_material_semantic_draft(draft, task=task, run_dir=run)
                self.assertEqual(draft, before)

    def test_unknown_selection_and_claimed_foreign_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
        ):
            run, task, _, env, start = self.prepare(Path(directory))
            self.search(run, task)
            self.fetch(run, task)
            for field in ("candidate_id", "document_id"):
                draft = self.draft()
                draft["selections"][0][field] = "foreign-id"
                with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "DOCUMENT_SELECTION_INVALID"):
                    stage.assemble_material_semantic_draft(draft, task=task, run_dir=run)
            record = self.stop(env, start, {**self.draft(), "invocation_id": "foreign"})
            self.assertNotEqual(record.get("output_capture", {}).get("status"), "SAVED")
            self.assertFalse((run / "research/material-results").exists())

    def test_structure_is_validated_before_missing_tool_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, env, start = self.prepare(Path(directory))
            draft = self.draft()
            draft.pop("summary")
            record = self.stop(env, start, draft)
            self.assertEqual(record["output_capture"]["status"], "FAILED")
            self.assertIn("SCHEMA_REQUIRED_MISSING", record["output_capture"]["failure_code"])
            with self.assertRaises(SchemaValidationError):
                stage.assemble_material_semantic_draft({**self.draft(), "artifact_refs": []}, task=task, run_dir=run)

    def test_event_artifact_tampering_and_unproven_file_rejected(self):
        for mutation in ("artifact", "input_hash", "output_hash", "agent", "run_id", "missing_events", "orphan"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
            ):
                run, task, _, _, _ = self.prepare(Path(directory))
                search = self.search(run, task)
                self.fetch(run, task)
                events = run / "events/mcp/events.jsonl"
                if mutation == "artifact":
                    path = run / search["artifact_ref"]
                    path.write_text(path.read_text() + "\n")
                elif mutation == "missing_events":
                    events.unlink()
                elif mutation == "orphan":
                    (run / search["artifact_ref"]).with_name("search-unknown.json").write_text("{}")
                else:
                    records = [json.loads(line) for line in events.read_text().splitlines()]
                    records[0][mutation] = "foreign-value"
                    events.write_text("\n".join(json.dumps(item) for item in records) + "\n")
                with self.assertRaises(stage.ResearchMaterialsStageError):
                    stage.assemble_material_semantic_draft(self.draft(), task=task, run_dir=run)

    def test_consumer_recomputes_audit_instead_of_trusting_saved_hash(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
        ):
            run, task, _, env, start = self.prepare(Path(directory))
            self.search(run, task)
            self.fetch(run, task)
            record = self.stop(env, start, self.draft())
            capture = record["output_capture"]
            formal = json.loads((run / capture["path"]).read_text())
            audit_path = run / capture["tool_audit_ref"]
            audit = json.loads(audit_path.read_text())
            audit["attempts"][0]["query"] = "not-executed"
            audit["audit_hash"] = canonical_hash({key: value for key, value in audit.items() if key != "audit_hash"})
            audit_path.write_text(json.dumps(audit))
            capture["tool_audit_hash"] = audit["audit_hash"]
            with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "AUDIT_BINDING_INVALID"):
                stage.verify_material_tool_audit(run, task, formal, capture)

    def test_task_cannot_downgrade_current_invocation_to_legacy_full_output(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, env, start = self.prepare(Path(directory), "PEER_SELECTION")
            path = run / "research/dispatch-index.json"
            index = json.loads(path.read_text())
            selected = next(item for item in index["tasks"] if item["task_id"] == task["task_id"])
            selected.pop("semantic_output_version")
            index["index_hash"] = canonical_hash({key: value for key, value in index.items() if key != "index_hash"})
            path.write_text(json.dumps(index))
            record = self.stop(env, start, {**self.draft(), "query_intents": [], "selections": []})
            self.assertEqual(record["output_capture"]["status"], "FAILED", record)
            self.assertIn("SEMANTIC_PROTOCOL_INVALID", record["output_capture"]["failure_code"])
            self.assertFalse((run / "research/material-results").exists())

    def test_legacy_material_protocol_cannot_start_process_or_create_runtime_directories(self):
        for location in ("index", "packet", "invocation"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as directory:
                run = fixtures.ResearchMaterialsStageTests().prepare(Path(directory), count=1)
                index_path = run / "research/dispatch-index.json"
                index = json.loads(index_path.read_text())
                task = index["tasks"][0]
                if location == "index":
                    task.pop("semantic_output_version")
                elif location == "packet":
                    packet_path = run / task["packet_path"]
                    packet = json.loads(packet_path.read_text())
                    packet["task"].pop("semantic_output_version")
                    packet_path.write_text(json.dumps(packet))
                    task["packet_hash"] = canonical_hash(packet)
                else:
                    path = run / task["invocation_path"]
                    invocation = json.loads(path.read_text())
                    invocation.pop("semantic_output_version")
                    invocation["manifest_hash"] = canonical_hash({
                        key: value for key, value in invocation.items() if key != "manifest_hash"})
                    path.write_text(json.dumps(invocation))
                index["index_hash"] = canonical_hash({key: value for key, value in index.items() if key != "index_hash"})
                index_path.write_text(json.dumps(index))
                originals = {path: path.read_bytes() for path in run.rglob('*') if path.is_file()}
                with patch.object(stage.subprocess, "run") as process, self.assertRaisesRegex(
                    stage.ResearchMaterialsStageError, "RESEARCH_MATERIALS_LEGACY_OUTPUT_EXECUTION_RETIRED"
                ):
                    stage.launch_research_materials_stage(fixtures.ROOT, run_dir=run)
                process.assert_not_called()
                self.assertFalse((run / "invocation").exists())
                self.assertFalse((run / ".codex-runtime").exists())
                self.assertEqual({path: path.read_bytes() for path in run.rglob('*') if path.is_file()}, originals)

    def test_legacy_material_result_still_validates_but_stop_cannot_save_new_output(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, env, start = self.prepare(Path(directory), "PEER_SELECTION")
            draft = {**self.draft(), "query_intents": [], "selections": []}
            formal, _ = stage.assemble_material_semantic_draft(draft, task=task, run_dir=run)
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            selected = next(item for item in index["tasks"] if item["task_id"] == task["task_id"])
            selected.pop("semantic_output_version")
            index["index_hash"] = canonical_hash({key: value for key, value in index.items() if key != "index_hash"})
            index_path.write_text(json.dumps(index))
            invocation_path = run / task["invocation_path"]
            invocation = json.loads(invocation_path.read_text())
            invocation.pop("semantic_output_version")
            invocation["manifest_hash"] = canonical_hash({
                key: value for key, value in invocation.items() if key != "manifest_hash"})
            invocation_path.write_text(json.dumps(invocation))
            # 校验历史业务结构不重写旧对象；不以 Hook 捕获代替只读校验。
            before = json.dumps(formal, sort_keys=True)
            stage.validate_material_preparation_output(formal, task=selected, run_dir=run)
            self.assertEqual(json.dumps(formal, sort_keys=True), before)
            record = self.stop(env, start, formal)
            self.assertEqual(record["output_capture"]["status"], "FAILED", record)
            self.assertIn("RESEARCH_MATERIALS_LEGACY_OUTPUT_WRITE_RETIRED", record["output_capture"]["failure_code"])
            self.assertFalse((run / "research/material-results").exists())

    def test_peer_native_selection_has_no_queries_or_tool_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet, env, start = self.prepare(Path(directory), "PEER_SELECTION")
            self.assertEqual(packet["output_schema"]["properties"]["query_intents"]["maxItems"], 0)
            response = self.call(run, task, "research_search", decision_cutoff=task["decision_cutoff"], query="forbidden")
            self.assertIn("TOOL_NOT_AUTHORIZED", response["error"]["message"])
            self.assertFalse((run / "research/materials").exists())
            candidate = packet["peer_candidate_group"]["candidates"][0]
            draft = {**self.draft(), "query_intents": [], "selections": [{
                "candidate_id": candidate["candidate_id"], "document_id": None, "rationale": "可比性待核实。"}]}
            record = self.stop(env, start, draft)
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            audit = stage.build_material_tool_audit(run, task)
            self.assertEqual(audit["attempts"], [])
            self.assertEqual(audit["artifact_refs"], [])

    def test_formal_historical_shape_is_readable_but_not_current_native_write(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
        ):
            run, task, _, env, start = self.prepare(Path(directory))
            self.search(run, task)
            self.fetch(run, task)
            formal, _ = stage.assemble_material_semantic_draft(self.draft(), task=task, run_dir=run)
            before = json.dumps(formal, sort_keys=True)
            stage.validate_material_preparation_output(formal, task=task, run_dir=run)
            self.assertEqual(json.dumps(formal, sort_keys=True), before)
            record = self.stop(env, start, formal)
            self.assertEqual(record["output_capture"]["status"], "FAILED")
            self.assertIn("SCHEMA_REQUIRED_MISSING", record["output_capture"]["failure_code"])
            record = self.stop(env, start, {**formal, "query_intents": self.draft()["query_intents"]})
            self.assertEqual(record["output_capture"]["status"], "FAILED")
            self.assertIn("SCHEMA_EXTRA_PROPERTY", record["output_capture"]["failure_code"])

    def test_search_lead_or_missing_provenance_cannot_be_assembled_as_body(self):
        for change in ({"verification_status": "LEAD_ONLY"}, {"source_id": None}, {"security_id": "foreign"}):
            class InvalidDocument(fixtures.FakeOpenAlexClient):
                def fetch(self, candidate):
                    return {**super().fetch(candidate), **change}
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", InvalidDocument
            ):
                run, task, _, _, _ = self.prepare(Path(directory))
                self.search(run, task)
                self.fetch(run, task)
                with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "DOCUMENT_PROVENANCE_INVALID"):
                    stage.assemble_material_semantic_draft(self.draft(), task=task, run_dir=run)

    def test_finalizer_and_formal_import_reverify_audit_without_rewriting_original(self):
        from product.runtime.multidimensional_stage import _import_research_materials
        for tampered in (False, True):
            with self.subTest(tampered=tampered), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", fixtures.FakeOpenAlexClient
            ):
                root = Path(directory)
                helper = fixtures.ResearchMaterialsStageTests()
                run = helper.prepare(root, count=1)
                helper.execute_with_hooks(run)
                manifest = json.loads((run / "research/material-preparation-manifest.json").read_text())
                entry = next(item for item in manifest["outputs"] if item["preparation_kind"] == "RESEARCH_REPORT_DISCOVERY")
                original = (run / entry["output_ref"]).read_bytes()
                if tampered:
                    (run / entry["tool_audit_ref"]).write_text("{}")
                    with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "AUDIT_BINDING_INVALID"):
                        stage.finalize_research_materials_stage(fixtures.ROOT, run)
                handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
                args = {"source_run": run, "target_run": root / "consumer",
                        "expected_handoff": handoff,
                        "target_gate": json.loads((run / "evidence/gate.json").read_text()),
                        "expected_security_ids": [p["security_id"] for p in handoff["portfolio"]["positions"]]}
                if tampered:
                    with self.assertRaisesRegex(stage.ResearchMaterialsStageError, "AUDIT_BINDING_INVALID"):
                        _import_research_materials(**args)
                else:
                    _import_research_materials(**args)
                    audits = list((root / "consumer/research/imported-materials").glob("*/tool-audit.json"))
                    self.assertEqual(len(audits), 4)
                    self.assertTrue(any(path.read_bytes() == (run / entry["tool_audit_ref"]).read_bytes() for path in audits))
                self.assertEqual((run / entry["output_ref"]).read_bytes(), original)
