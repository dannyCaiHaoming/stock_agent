"""独立反证语义草稿：真实 Hook/MCP/归集接缝，零模型调用。"""
from __future__ import annotations

import copy
import io
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime import independent_skeptic_stage as stage
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.fixture_mcp import serve_stdio
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.multidimensional_references import translate_references
from product.runtime.invocation import SPECIALIST_SEMANTIC_DRAFT, SPECIALIST_TECHNICAL_FIELDS
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.validation import validate_skeptic_report
from tests import test_independent_skeptic_stage as fixtures


class SkepticSemanticHandoffTests(unittest.TestCase):
    def prepare(self, directory, *, count=1):
        run = fixtures.prepare_complete_forward(Path(directory), count=count)
        stage.prepare_skeptic_phase(fixtures.ROOT, run)
        task = stage.read_dispatch_index(run)["tasks"][0]
        env = {
            "STOCK_AGENT_RUN_DIR": str(run),
            "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(run / "invocation/skeptic/subagent-events.jsonl"),
            "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(run / "invocation/skeptic/subagent-dispatches.jsonl"),
            "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_skeptic",
            "STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE": "independent-skeptic-runtime/1.0.0",
            "STOCK_AGENT_RESEARCH_TASK_NAME": task["task_name"],
        }
        dispatch = {
            "hook_event_name": "PreToolUse", "session_id": "semantic-parent",
            "turn_id": "semantic-turn", "tool_name": "spawn_agent", "tool_use_id": "semantic-tool",
            "cwd": str(fixtures.ROOT / "product"), "model": "gpt-5.6-terra",
            "permission_mode": "workspace-write", "tool_input": {
                "agent_type": "runtime_skeptic", "task_name": task["task_name"], "fork_turns": "none",
                "message": "启动本次冻结的独立反证研究；完整上下文由 SubagentStart Hook 交付。",
            },
        }
        allowed, _ = handle_hook_event(dispatch, environ=env)
        self.assertEqual(allowed["decision"], "ALLOW", allowed)
        start = {
            "hook_event_name": "SubagentStart", "session_id": "semantic-parent",
            "turn_id": "semantic-turn", "agent_id": "semantic-child", "agent_type": "runtime_skeptic",
            "model": "gpt-5.6-terra", "cwd": str(fixtures.ROOT / "product"), "permission_mode": "read-only",
        }
        record, response = handle_hook_event(start, environ=env)
        self.assertEqual(record["context_binding"]["status"], "DELIVERED", record)
        context = response["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(record["context_binding"]["model_context_bytes"], len(context.encode("utf-8")))
        self.assertEqual(record["context_binding"]["model_context_sha256"], hashlib.sha256(context.encode("utf-8")).hexdigest())
        packet = json.loads(context)
        return run, task, env, start, packet

    def draft(self, task, *, run=None):
        evidence_id = task["allowed_evidence_ids"][0]
        result = {
            "status": "LOW_CONFIDENCE", "mode": "INDEPENDENT_FIRST_PASS",
            "scope": f"{task['security_id']} 的独立反证",
            "challenges": [{
                "challenge_id": "cash-pressure", "statement": "现金流压力可能限制投资弹性；尚不能判定必然发生。",
                "evidence_refs": [evidence_id], "assumption_ids": ["financing-cost"],
                "resolution_evidence_needed": ["后续债务到期及融资条件"],
            }],
            "assumptions": [{"assumption_id": "financing-cost", "statement": "假设融资成本上行，非当前已知事实。"}],
            "evidence_refs": [evidence_id], "counter_evidence_refs": [],
            "uncertainties": ["缺乏长期融资路径"], "data_gaps": ["缺债务明细"],
            "invalidation_conditions": ["融资成本下降且现金流改善"],
            "confidence": 0.35, "confidence_rationale": "仅有当前有限资料，不能外推投资动作。",
        }
        if run is not None:
            packet = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            result = translate_references(result, packet["reference_map"], to_model=True)
        return result

    def query(self, run, task, ids):
        request = {"id": 1, "method": "tools/call", "params": {"name": "query", "arguments": {
            "run_id": stage.read_dispatch_index(run)["run_id"], "agent": "runtime_skeptic",
            "invocation_id": task["invocation_id"], "evidence_ids": ids,
        }}}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
            serve_stdio(stateless=True, default_run_dir=run)
        return json.loads(output.getvalue())

    def stop(self, env, start, draft):
        return handle_hook_event({**start, "hook_event_name": "SubagentStop",
            "last_assistant_message": json.dumps(draft, ensure_ascii=False), "stop_hook_active": False}, environ=env)

    def test_actual_hooks_query_formal_report_package_and_reader_preserve_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, packet = self.prepare(directory)
            self.assertEqual(packet["output_schema"]["$id"], SPECIALIST_SEMANTIC_DRAFT)
            self.assertTrue(SPECIALIST_TECHNICAL_FIELDS.isdisjoint(packet["output_schema"]["properties"]))
            self.assertNotIn("invocation", packet)
            self.assertNotIn("reference_map", packet)
            for forbidden in ("forward_bundle_hash", "unresolved_cross_dimension_questions", "forward_reports"):
                self.assertNotIn(forbidden, packet["agent_input"])
            query = self.query(run, task, task["allowed_evidence_ids"])
            self.assertNotIn("error", query, query)
            self.assertEqual({item["evidence_id"] for item in query["result"]["structuredContent"]["evidence"]},
                             set(packet["allowed_evidence_ids"]))
            draft = self.draft(task, run=run)
            canonical = self.draft(task)
            original = copy.deepcopy(draft)
            record, _ = self.stop(env, start, draft)
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            report_path = run / task["report_ref"]
            before_hash = file_hash(report_path)
            report = json.loads(report_path.read_text())
            for key, value in canonical.items():
                self.assertEqual(report[key], value)
            self.assertEqual(report["invocation_id"], task["invocation_id"])
            self.assertEqual(report["agent"], "runtime_skeptic")
            self.assertEqual(report["artifact_refs"], [])
            result = stage.finalize_skeptic_phase(fixtures.ROOT, run)
            self.assertEqual(result["status"], "PASSED", result)
            package = json.loads((run / "research/skeptic/pre-decision-research-package.json").read_text())
            self.assertEqual(package["consumability"], "DOWNSTREAM_READY")
            stage.validate_predecision_package(fixtures.ROOT, run, package)
            self.assertEqual(file_hash(report_path), before_hash)
            self.assertEqual(draft, original)
            markdown = (run / task["markdown_ref"]).read_text()
            self.assertIn(draft["challenges"][0]["statement"], markdown)
            self.assertIn("retrieved_at", markdown)

    def test_model_context_schema_and_tool_results_share_exact_short_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, view = self.prepare(directory)
            packet = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            aliases = list(packet["reference_map"]["evidence"])
            self.assertEqual(view["allowed_evidence_ids"], aliases)
            self.assertEqual(view["agent_input"]["allowed_evidence_ids"], aliases)
            for field in ("evidence_refs", "counter_evidence_refs"):
                self.assertEqual(view["output_schema"]["properties"][field]["items"]["enum"], aliases)
            challenge_schema = view["output_schema"]["properties"]["challenges"]["items"]
            self.assertEqual(challenge_schema["properties"]["evidence_refs"]["items"]["enum"], aliases)
            result = self.query(run, task, aliases)
            self.assertNotIn("error", result)
            facts = result["result"]["structuredContent"]["evidence"]
            gate = json.loads((run / "evidence/gate.json").read_text())
            original = {fact["evidence_id"]: fact for fact in gate["allowed_evidence"]}
            for fact in facts:
                restored = translate_references(fact, packet["reference_map"])
                self.assertEqual(restored, original[restored["evidence_id"]])
            record, _ = self.stop(env, start, self.draft(task, run=run))
            self.assertEqual(record["output_capture"]["reference_map_hash"], packet["reference_map"]["map_hash"])
            events = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
            query_event = next(event for event in events if event.get("tool") == "fixture_evidence.query")
            self.assertEqual(query_event["evidence_ids"], task["allowed_evidence_ids"])

    def test_raw_decorated_unknown_and_cross_type_ids_fail_before_save(self):
        for kind in ("raw", "source", "time", "unknown", "type"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                run, task, env, start, view = self.prepare(directory)
                short = view["allowed_evidence_ids"][0]
                bad = {"raw": task["allowed_evidence_ids"][0], "source": short + "|source",
                       "time": short + "|as_of=2026-09-30", "unknown": "e.unknown.1",
                       "type": "d." + short[2:]}[kind]
                draft = self.draft(task, run=run)
                draft["evidence_refs"] = [bad]
                record, _ = self.stop(env, start, draft)
                self.assertEqual(record["output_capture"]["status"], "FAILED")
                self.assertIn("SCHEMA_", record["output_capture"]["failure_code"])
                self.assertFalse((run / task["report_ref"]).exists())

    def test_multiple_selected_short_refs_preserve_order_and_research_text(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, _, view = self.prepare(directory)
            selected = list(reversed(view["allowed_evidence_ids"]))
            draft = self.draft(task, run=run)
            draft["evidence_refs"] = selected
            draft["counter_evidence_refs"] = selected[:1]
            draft["challenges"][0]["evidence_refs"] = selected
            draft["challenges"][0]["statement"] = "不推断现金压力必然发生；脚注限制与反向情景仍需核验。"
            original = copy.deepcopy(draft)
            capture = stage.capture_skeptic_report(fixtures.ROOT, run, task_name=task["task_name"],
                raw_message=json.dumps(draft, ensure_ascii=False), model="gpt-5.6-terra")
            packet = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            report = json.loads((run / capture["path"]).read_text())
            canonical = translate_references(draft, packet["reference_map"])
            for key in draft:
                self.assertEqual(report[key], canonical[key])
            self.assertEqual(report["evidence_refs"], list(reversed(task["allowed_evidence_ids"])))
            self.assertEqual(draft, original)

    def test_cross_run_role_and_security_aliases_are_not_guessed(self):
        from product.runtime.multidimensional_references import build_reference_map
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, _ = self.prepare(directory, count=2)
            packet = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            base = {key: value for key, value in packet.items() if key != "reference_map"}
            for field, value in (("run_id", "another-run"), ("agent", "runtime_company_analyst"),
                                 ("security_id", "US:OTHER")):
                foreign = copy.deepcopy(base)
                foreign["identity"][field] = value
                mapping = build_reference_map(foreign, packet["reference_map"]["binding"]["gate_hash"], str(run))
                alias = next(iter(mapping["evidence"]))
                self.assertIn("error", self.query(run, task, [alias]))
                bad = {**self.draft(task, run=run), "evidence_refs": [alias]}
                with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                    stage.capture_skeptic_report(fixtures.ROOT, run, task_name=task["task_name"],
                        raw_message=json.dumps(bad), model="gpt-5.6-terra")
            self.assertFalse((run / task["report_ref"]).exists())

    def test_resigned_reference_map_and_tool_context_are_rejected_at_actual_boundary(self):
        for target in ("reference_map", "tool_context", "allowed_evidence_ids"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                run, task, _, _, _ = self.prepare(directory)
                def corrupt(packet):
                    if target == "reference_map":
                        mapping = packet[target]
                        mapping["evidence"][next(iter(mapping["evidence"]))] = "wrong-canonical-id"
                        mapping["map_hash"] = canonical_hash({k: v for k, v in mapping.items() if k != "map_hash"})
                    elif target == "tool_context":
                        packet[target]["required_identity_arguments"]["agent"] = "runtime_company_analyst"
                    else:
                        packet[target] = ["wrong-canonical-id"]
                self.rewrite_packet(run, task, corrupt)
                with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_REFERENCE_MAP_BINDING_INVALID"):
                    stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                result = self.query(run, task, task["allowed_evidence_ids"])
                self.assertIn("error", result)
                self.assertIn("COUNTER_REFERENCE_MAP_BINDING_INVALID", json.dumps(result))

    def test_reference_protocol_drift_is_rejected_even_after_resigning(self):
        for target in ("index", "task", "invocation"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                run, task, _, _, _ = self.prepare(directory)
                path = run / "research/skeptic/dispatch-index.json"
                index = json.loads(path.read_text())
                if target == "invocation":
                    inv_path = run / task["invocation_ref"]
                    invocation = json.loads(inv_path.read_text())
                    invocation.pop("reference_transport_version")
                    invocation["manifest_hash"] = canonical_hash({k: v for k, v in invocation.items() if k != "manifest_hash"})
                    inv_path.write_text(json.dumps(invocation))
                else:
                    (index if target == "index" else index["tasks"][0]).pop("reference_transport_version")
                    index["index_hash"] = canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
                    path.write_text(json.dumps(index))
                with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_REFERENCE_PROTOCOL_BINDING_INVALID"):
                    stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_unqueried_allowed_evidence_does_not_become_downstream_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, _ = self.prepare(directory)
            self.assertGreater(len(task["allowed_evidence_ids"]), 1)
            queried = task["allowed_evidence_ids"][1:]
            self.assertNotIn("error", self.query(run, task, queried))
            record, _ = self.stop(env, start, self.draft(task, run=run))
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            result = stage.finalize_skeptic_phase(fixtures.ROOT, run)
            self.assertNotEqual(result["status"], "PASSED", result)
            package = json.loads((run / "research/skeptic/pre-decision-research-package.json").read_text())
            self.assertEqual(package["consumability"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(package["counter_theses"][0]["validation_status"], "FAILED")
            proof = json.loads((run / "research/skeptic/execution-proof.json").read_text())
            self.assertNotIn(task["allowed_evidence_ids"][0], proof["tasks"][0]["queried_evidence_ids"])
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_REPORT_EVIDENCE_NOT_QUERIED"):
                stage.validate_report_query_closure(self.draft(task), [{"evidence_ids": queried}])

    def test_native_format_feedback_uses_trusted_identity_not_authored_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, _ = self.prepare(directory)
            draft = self.draft(task, run=run)
            draft.pop("scope")
            record, response = self.stop(env, start, draft)
            self.assertEqual(record["output_capture"]["repair_state"], "REPAIR_REQUESTED", record)
            self.assertEqual(response["decision"], "block")
            feedback = json.loads(response["reason"])
            self.assertEqual(feedback["repair_contract"], "research-local-revision/1.0.0")
            self.assertEqual(feedback["allowed_paths"], ["/scope"])
            self.assertNotIn("invocation_id", feedback)
            self.assertNotIn("original_draft", feedback)
            self.assertNotIn("output_schema", feedback)
            self.assertNotIn("error", self.query(run, task, task["allowed_evidence_ids"]))
            record, _ = self.stop(env, start, self.draft(task, run=run))
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            self.assertEqual(record["output_capture"]["attempt"], 2)

    def test_native_revision_patch_reaches_real_skeptic_finalizer_without_semantic_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, _ = self.prepare(directory)
            complete = self.draft(task, run=run)
            incomplete = {k: v for k, v in complete.items() if k != "confidence"}
            first, response = self.stop(env, start, incomplete)
            repair = json.loads(response["reason"])
            self.assertEqual(repair["allowed_paths"], ["/confidence"])
            self.assertNotIn("error", self.query(run, task, task["allowed_evidence_ids"]))
            record, _ = self.stop(env, start, {"base_draft_ref": repair["base_draft_ref"], "changes": [
                {"op": "add", "path": "/confidence", "value": complete["confidence"]}]})
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            report = json.loads((run / task["report_ref"]).read_text())
            expected = translate_references(complete, stage.build_skeptic_dispatch_packet(
                fixtures.ROOT, run, task["task_name"])["reference_map"])
            for key in expected:
                self.assertEqual(report[key], expected[key])
            result = stage.finalize_skeptic_phase(fixtures.ROOT, run)
            self.assertEqual(result["status"], "PASSED", result)
            self.assertEqual(record["local_revision"]["transport"], "NATIVE_PATCH")
            self.assertTrue((run / first["output_capture"]["raw_path"]).is_file())

    def test_revision_cannot_change_skeptic_judgment_outside_schema_error(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, _ = self.prepare(directory)
            draft = self.draft(task, run=run)
            draft.pop("scope")
            _, response = self.stop(env, start, draft)
            repair = json.loads(response["reason"])
            record, response = self.stop(env, start, {"base_draft_ref": repair["base_draft_ref"], "changes": [
                {"op": "replace", "path": "/confidence", "value": 0.99}]})
            self.assertEqual(record["output_capture"]["failure_code"], "LOCAL_REVISION_OUT_OF_SCOPE")
            self.assertEqual(record["output_capture"]["repair_state"], "EXHAUSTED")
            self.assertEqual(response, {})
            self.assertFalse((run / task["report_ref"]).exists())

    def test_conflicting_identity_unknown_reference_and_technical_echo_are_rejected(self):
        for extra in ({"run_id": "foreign"}, {"invocation_id": "foreign"}, {"agent": "runtime_company_analyst"},
                      {"artifact_refs": []}, {"evidence_refs": ["not-an-evidence-id"]}):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                run, task, env, start, _ = self.prepare(directory)
                record, _ = self.stop(env, start, {**self.draft(task, run=run), **extra})
                self.assertEqual(record["output_capture"]["status"], "FAILED", record)
                self.assertFalse((run / task["report_ref"]).exists())

    def test_other_security_evidence_is_rejected_by_real_tool_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, env, start, _ = self.prepare(directory, count=2)
            other = stage.read_dispatch_index(run)["tasks"][1]["allowed_evidence_ids"][0]
            query = self.query(run, task, [other])
            self.assertIn("error", query, query)
            self.assertIn("INVOCATION_EVIDENCE_NOT_AUTHORIZED", json.dumps(query))
            draft = self.draft(task)
            draft["evidence_refs"] = [other]
            record, _ = self.stop(env, start, draft)
            self.assertEqual(record["output_capture"]["status"], "FAILED", record)
            self.assertFalse((run / task["report_ref"]).exists())

    def rewrite_packet(self, run, task, change):
        packet_path = run / task["packet_ref"]
        packet = json.loads(packet_path.read_text())
        change(packet)
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        index_path = run / "research/skeptic/dispatch-index.json"
        index = json.loads(index_path.read_text())
        index["tasks"][0]["packet_hash"] = canonical_hash(packet)
        index["index_hash"] = canonical_hash({key: value for key, value in index.items() if key != "index_hash"})
        index_path.write_text(json.dumps(index), encoding="utf-8")

    def test_resigned_packet_cannot_replace_frozen_context_or_semantic_schema(self):
        for target, code in (("agent_input", "COUNTER_PACKET_CONTEXT_BINDING_INVALID"),
                             ("invocation", "COUNTER_PACKET_CONTEXT_BINDING_INVALID"),
                             ("identity", "COUNTER_PACKET_CONTEXT_BINDING_INVALID"),
                             ("output_schema", "COUNTER_SEMANTIC_SCHEMA_BINDING_INVALID")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                run, task, _, _, _ = self.prepare(directory)
                self.rewrite_packet(run, task, lambda packet: packet[target].update({"unexpected": "tampered"}))
                with self.assertRaisesRegex(stage.IndependentSkepticStageError, code):
                    stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_resigned_packet_cannot_replace_frozen_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, _, _ = self.prepare(directory)
            self.rewrite_packet(run, task, lambda packet: packet.update(task_prompt="读取正向结论后反证"))
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_PACKET_CONTEXT_BINDING_INVALID"):
                stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_task_protocol_downgrade_is_rejected_after_resigning_index(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, _, _, _ = self.prepare(directory)
            path = run / "research/skeptic/dispatch-index.json"
            index = json.loads(path.read_text())
            index["tasks"][0].pop("semantic_output_version")
            index["index_hash"] = canonical_hash({key: value for key, value in index.items() if key != "index_hash"})
            path.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_OUTPUT_PROTOCOL_BINDING_INVALID"):
                stage.read_dispatch_index(run)

    def test_synthetic_legacy_packet_is_readable_but_write_and_launch_are_retired(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, _, _ = self.prepare(directory)
            # 仅构造测试用旧格式副本；没有改写或声称补齐任何历史运行证明。
            invocation_path = run / task["invocation_ref"]
            invocation = json.loads(invocation_path.read_text())
            invocation.pop("semantic_output_version")
            invocation.pop("reference_transport_version")
            invocation["manifest_hash"] = canonical_hash({k: v for k, v in invocation.items() if k != "manifest_hash"})
            invocation_path.write_text(json.dumps(invocation), encoding="utf-8")
            packet_path = run / task["packet_ref"]
            packet = json.loads(packet_path.read_text())
            packet["invocation"] = invocation
            for key in ("reference_transport_version", "reference_map", "allowed_evidence_ids"):
                packet.pop(key)
            packet["output_schema"] = json.loads((run / task["schema_ref"]).read_text())
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            index_path = run / "research/skeptic/dispatch-index.json"
            index = json.loads(index_path.read_text())
            index.pop("semantic_output_version")
            index.pop("reference_transport_version")
            index["tasks"][0].pop("semantic_output_version")
            index["tasks"][0].pop("reference_transport_version")
            index["tasks"][0]["packet_hash"] = canonical_hash(packet)
            index["index_hash"] = canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
            index_path.write_text(json.dumps(index), encoding="utf-8")
            before = {path: file_hash(path) for path in (invocation_path, packet_path, index_path)}
            self.assertEqual(stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"]), packet)
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_LEGACY_OUTPUT_WRITE_RETIRED"):
                stage.capture_skeptic_report(fixtures.ROOT, run, task_name=task["task_name"],
                    raw_message=json.dumps(self.draft(task)), model="gpt-5.6-terra")
            with patch.object(stage.subprocess, "Popen") as process:
                with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_LEGACY_EXECUTION_RETIRED"):
                    stage.launch_skeptic_phase(fixtures.ROOT, run_dir=run)
                process.assert_not_called()
            self.assertEqual({path: file_hash(path) for path in before}, before)

    def test_synthetic_previous_native_packet_stays_read_only_and_byte_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, _, _ = self.prepare(directory)
            inv_path = run / task["invocation_ref"]
            invocation = json.loads(inv_path.read_text())
            invocation.pop("reference_transport_version")
            invocation["manifest_hash"] = canonical_hash({k: v for k, v in invocation.items() if k != "manifest_hash"})
            inv_path.write_text(json.dumps(invocation))
            packet_path = run / task["packet_ref"]
            packet = json.loads(packet_path.read_text())
            packet["invocation"] = invocation
            for key in ("reference_transport_version", "reference_map", "allowed_evidence_ids"):
                packet.pop(key)
            packet_path.write_text(json.dumps(packet))
            index_path = run / "research/skeptic/dispatch-index.json"
            index = json.loads(index_path.read_text())
            index.pop("reference_transport_version")
            index["tasks"][0].pop("reference_transport_version")
            index["tasks"][0]["packet_hash"] = canonical_hash(packet)
            index["index_hash"] = canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
            index_path.write_text(json.dumps(index))
            before = {path: file_hash(path) for path in (inv_path, packet_path, index_path)}
            loaded = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            self.assertEqual(loaded, packet)
            self.assertEqual(stage.serialize_skeptic_dispatch_context(loaded),
                             json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            with self.assertRaisesRegex(ValueError, "COUNTER_LEGACY_REFERENCE_WRITE_RETIRED"):
                stage.capture_skeptic_report(fixtures.ROOT, run, task_name=task["task_name"],
                    raw_message=json.dumps(self.draft(task)), model="gpt-5.6-terra")
            with self.assertRaisesRegex(ValueError, "COUNTER_LEGACY_REFERENCE_RESUME_RETIRED"):
                stage.prepare_skeptic_resume(fixtures.ROOT, run)
            with patch.object(stage.subprocess, "Popen") as process:
                with self.assertRaisesRegex(ValueError, "COUNTER_LEGACY_REFERENCE_EXECUTION_RETIRED"):
                    stage.launch_skeptic_phase(fixtures.ROOT, run_dir=run)
                process.assert_not_called()
            self.assertEqual({path: file_hash(path) for path in before}, before)

    def test_invocation_protocol_drift_rejected_even_with_valid_manifest_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, _, _ = self.prepare(directory)
            path = run / task["invocation_ref"]
            invocation = json.loads(path.read_text())
            invocation.pop("semantic_output_version")
            invocation["manifest_hash"] = canonical_hash({k: v for k, v in invocation.items() if k != "manifest_hash"})
            path.write_text(json.dumps(invocation), encoding="utf-8")
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_OUTPUT_PROTOCOL_BINDING_INVALID"):
                stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_existing_formal_business_schema_and_validator_remain_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _, _, _ = self.prepare(directory)
            invocation = json.loads((run / task["invocation_ref"]).read_text())
            report = {**self.draft(task), "schema_version": "counter-thesis-report/2.1.0",
                "run_id": invocation["run_id"], "invocation_id": task["invocation_id"], "agent": "runtime_skeptic",
                "skill_execution": invocation["skill_execution"], "artifact_refs": []}
            original = json.dumps(report, ensure_ascii=False)
            schema = json.loads((run / task["schema_ref"]).read_text())
            validate_schema_instance(report, schema)
            validate_skeptic_report(report, run_id=invocation["run_id"], manifest=invocation)
            self.assertEqual(json.dumps(report, ensure_ascii=False), original)
            with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                stage.capture_skeptic_report(fixtures.ROOT, run, task_name=task["task_name"],
                    raw_message=original, model="gpt-5.6-terra")
            self.assertFalse((run / task["report_ref"]).exists())
