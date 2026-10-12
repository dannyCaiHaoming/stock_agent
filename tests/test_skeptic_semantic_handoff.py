"""反证语义草稿的真实业务/MCP与显式历史归集；不模拟正常Hook或作者执行。"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime import independent_skeptic_stage as stage
from product.runtime.local_revision import _apply, located_paths
from product.runtime.fixture_mcp import serve_stdio
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.multidimensional_references import translate_references
from product.runtime.invocation import SPECIALIST_SEMANTIC_DRAFT, SPECIALIST_TECHNICAL_FIELDS
from product.runtime.schema_validation import validate_schema_instance, schema_issue_locations
from product.runtime.validation import validate_skeptic_report
from tests import test_independent_skeptic_stage as fixtures


class SkepticSemanticHandoffTests(unittest.TestCase):
    def prepare(self, directory, *, count=1):
        run = fixtures.prepare_complete_forward(Path(directory), count=count)
        stage.prepare_skeptic_phase(fixtures.ROOT, run)
        task = stage.read_dispatch_index(run)["tasks"][0]
        packet = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
        view = json.loads(stage.serialize_skeptic_dispatch_context(packet))
        self.assertFalse((run / "invocation/skeptic").exists())
        return run, task, view

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

    def capture(self, run, task, draft):
        return stage.capture_skeptic_report(fixtures.ROOT, run, task_name=task["task_name"],
            raw_message=json.dumps(draft, ensure_ascii=False), model="gpt-5.6-terra")

    def write_historical_execution_fixture(self, run, task, capture, *, index_ref=None):
        """只为历史归集消费者写明示向量；真实query另行调用，不是宿主执行证明。"""
        packet = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"], index_ref=index_ref)
        index = stage.read_dispatch_index(run, index_ref)
        identity = {"parent_session_id": "synthetic-parent", "child_session_id": "synthetic-" + task["task_name"],
                    "agent_type": "runtime_skeptic", "model": packet["invocation"]["model"]}
        binding = {"status": "DELIVERED", "run_id": index["run_id"], "task_name": task["task_name"],
                   "invocation_id": task["invocation_id"], "packet_hash": canonical_hash(packet)}
        dispatch = {"decision": "ALLOW", "task_name": task["task_name"], "parent_session_id": identity["parent_session_id"],
                    "agent_type": "runtime_skeptic", "fork_turns": "none",
                    "dispatch_binding": {"matched": True, "packet_hash": canonical_hash(packet)}}
        events = [{**identity, "hook_event_name": "SubagentStart", "context_binding": binding},
                  {**identity, "hook_event_name": "SubagentStop", "output_binding": {"invocation_id": task["invocation_id"]},
                   "trusted_task_binding": {"task_name": task["task_name"], "task_id": task["task_id"],
                       "run_id": index["run_id"], "invocation_id": task["invocation_id"], "agent": "runtime_skeptic"},
                   "identity_binding": {"status": "BOUND"}, "output_capture": capture}]
        root = run / "invocation/skeptic"
        if task.get("attempt", 1) > 1:
            root = root / f"attempt-{task['attempt']}"
        root.mkdir(parents=True, exist_ok=True)
        for name, rows in (("subagent-dispatches.jsonl", [dispatch]), ("subagent-events.jsonl", events)):
            path = root / name
            path.with_suffix(path.suffix + ".lock").touch(exist_ok=True)
            with path.open("a") as stream:
                for row in rows:
                    row["event_hash"] = legacy_envelope_hash(row, hash_field="event_hash")
                    stream.write(json.dumps(row) + "\n")

    def test_business_query_report_and_historical_package_preserve_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepare(directory)
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
            capture = self.capture(run, task, draft)
            self.assertEqual(capture["status"], "SAVED", capture)
            self.assertFalse((run / "invocation/skeptic").exists())
            report_path = run / task["report_ref"]
            before_hash = file_hash(report_path)
            report = json.loads(report_path.read_text())
            for key, value in canonical.items():
                self.assertEqual(report[key], value)
            self.assertEqual(report["invocation_id"], task["invocation_id"])
            self.assertEqual(report["agent"], "runtime_skeptic")
            self.assertEqual(report["artifact_refs"], [])
            self.write_historical_execution_fixture(run, task, capture)
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
            run, task, view = self.prepare(directory)
            packet = stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            aliases = list(packet["reference_map"]["evidence"])
            self.assertEqual(view["allowed_evidence_ids"], aliases)
            self.assertNotIn("allowed_evidence_ids", view["agent_input"])
            self.assertEqual(view["output_schema"]["$defs"]["start_context_evidence_id"]["enum"], aliases)
            for field in ("evidence_refs", "counter_evidence_refs"):
                self.assertEqual(view["output_schema"]["properties"][field]["items"], {"$ref": "#/$defs/start_context_evidence_id"})
            challenge_schema = view["output_schema"]["properties"]["challenges"]["items"]
            self.assertEqual(challenge_schema["properties"]["evidence_refs"]["items"], {"$ref": "#/$defs/start_context_evidence_id"})
            result = self.query(run, task, aliases)
            self.assertNotIn("error", result)
            facts = result["result"]["structuredContent"]["evidence"]
            gate = json.loads((run / "evidence/gate.json").read_text())
            original = {fact["evidence_id"]: fact for fact in gate["allowed_evidence"]}
            for fact in facts:
                restored = translate_references(fact, packet["reference_map"])
                self.assertEqual(restored, original[restored["evidence_id"]])
            capture = self.capture(run, task, self.draft(task, run=run))
            self.assertEqual(capture["reference_map_hash"], packet["reference_map"]["map_hash"])
            events = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
            query_event = next(event for event in events if event.get("tool") == "fixture_evidence.query")
            self.assertEqual(query_event["evidence_ids"], task["allowed_evidence_ids"])

    def test_raw_decorated_unknown_and_cross_type_ids_fail_before_save(self):
        for kind in ("raw", "source", "time", "unknown", "type"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                run, task, view = self.prepare(directory)
                short = view["allowed_evidence_ids"][0]
                bad = {"raw": task["allowed_evidence_ids"][0], "source": short + "|source",
                       "time": short + "|as_of=2026-09-30", "unknown": "e.unknown.1",
                       "type": "d." + short[2:]}[kind]
                draft = self.draft(task, run=run)
                draft["evidence_refs"] = [bad]
                with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                    self.capture(run, task, draft)
                self.assertFalse((run / task["report_ref"]).exists())

    def test_multiple_selected_short_refs_preserve_order_and_research_text(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, view = self.prepare(directory)
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
            run, task, _ = self.prepare(directory, count=2)
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
                run, task, _ = self.prepare(directory)
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
                run, task, _ = self.prepare(directory)
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
            run, task, _ = self.prepare(directory)
            self.assertGreater(len(task["allowed_evidence_ids"]), 1)
            queried = task["allowed_evidence_ids"][1:]
            self.assertNotIn("error", self.query(run, task, queried))
            capture = self.capture(run, task, self.draft(task, run=run))
            self.assertEqual(capture["status"], "SAVED", capture)
            self.write_historical_execution_fixture(run, task, capture)
            result = stage.finalize_skeptic_phase(fixtures.ROOT, run)
            self.assertNotEqual(result["status"], "PASSED", result)
            package = json.loads((run / "research/skeptic/pre-decision-research-package.json").read_text())
            self.assertEqual(package["consumability"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(package["counter_theses"][0]["validation_status"], "FAILED")
            proof = json.loads((run / "research/skeptic/execution-proof.json").read_text())
            self.assertNotIn(task["allowed_evidence_ids"][0], proof["tasks"][0]["queried_evidence_ids"])
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_REPORT_EVIDENCE_NOT_QUERIED"):
                stage.validate_report_query_closure(self.draft(task), [{"evidence_ids": queried}])

    def test_schema_diagnostics_use_semantic_fields_not_authored_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, view = self.prepare(directory)
            draft = self.draft(task, run=run)
            draft.pop("scope")
            paths = located_paths(schema_issue_locations(draft, view["output_schema"]), exact_fields=True)
            self.assertEqual(paths, ["/scope"])
            with self.assertRaisesRegex(ValueError, "SCHEMA_REQUIRED_MISSING"):
                self.capture(run, task, draft)
            self.assertFalse((run / task["report_ref"]).exists())
            self.assertFalse((run / "invocation/skeptic").exists())
            self.assertNotIn("invocation_id", view["output_schema"]["properties"])
            self.assertNotIn("error", self.query(run, task, task["allowed_evidence_ids"]))
            fixed = _apply(draft, [{"op": "add", "path": "/scope", "value": self.draft(task)["scope"]}], paths)
            self.assertEqual(self.capture(run, task, fixed)["status"], "SAVED")

    def test_explicit_revision_reaches_business_save_and_historical_finalizer(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, view = self.prepare(directory)
            complete = self.draft(task, run=run)
            incomplete = {k: v for k, v in complete.items() if k != "confidence"}
            original = copy.deepcopy(incomplete)
            with self.assertRaisesRegex(ValueError, "SCHEMA_REQUIRED_MISSING"):
                self.capture(run, task, incomplete)
            paths = located_paths(schema_issue_locations(incomplete, view["output_schema"]), exact_fields=True)
            self.assertEqual(paths, ["/confidence"])
            self.assertNotIn("error", self.query(run, task, task["allowed_evidence_ids"]))
            # 诊断路径仅为补丁算法输入，不代表运行权限或服务端额度。
            corrected = _apply(incomplete, [{"op": "add", "path": "/confidence", "value": complete["confidence"]}], paths)
            capture = self.capture(run, task, corrected)
            report = json.loads((run / task["report_ref"]).read_text())
            expected = translate_references(complete, stage.build_skeptic_dispatch_packet(
                fixtures.ROOT, run, task["task_name"])["reference_map"])
            for key in expected:
                self.assertEqual(report[key], expected[key])
            self.assertEqual(incomplete, original)
            self.assertFalse((run / "invocation/skeptic").exists())
            self.write_historical_execution_fixture(run, task, capture)
            result = stage.finalize_skeptic_phase(fixtures.ROOT, run)
            self.assertEqual(result["status"], "PASSED", result)

    def test_explicit_revision_cannot_change_judgment_outside_schema_error(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, view = self.prepare(directory)
            draft = self.draft(task, run=run)
            draft.pop("scope")
            original = copy.deepcopy(draft)
            paths = located_paths(schema_issue_locations(draft, view["output_schema"]), exact_fields=True)
            self.assertEqual(paths, ["/scope"])
            with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_OUT_OF_SCOPE"):
                _apply(draft, [{"op": "replace", "path": "/confidence", "value": 0.99}], paths)
            self.assertEqual(draft, original)
            self.assertFalse((run / task["report_ref"]).exists())
            self.assertFalse((run / "invocation/skeptic").exists())

    def test_conflicting_identity_unknown_reference_and_technical_echo_are_rejected(self):
        for extra in ({"run_id": "foreign"}, {"invocation_id": "foreign"}, {"agent": "runtime_company_analyst"},
                      {"artifact_refs": []}, {"evidence_refs": ["not-an-evidence-id"]}):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                run, task, _ = self.prepare(directory)
                with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                    self.capture(run, task, {**self.draft(task, run=run), **extra})
                self.assertFalse((run / task["report_ref"]).exists())

    def test_other_security_evidence_is_rejected_by_real_tool_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _ = self.prepare(directory, count=2)
            other = stage.read_dispatch_index(run)["tasks"][1]["allowed_evidence_ids"][0]
            query = self.query(run, task, [other])
            self.assertIn("error", query, query)
            self.assertIn("INVOCATION_EVIDENCE_NOT_AUTHORIZED", json.dumps(query))
            draft = self.draft(task)
            draft["evidence_refs"] = [other]
            with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                self.capture(run, task, draft)
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
                run, task, _ = self.prepare(directory)
                self.rewrite_packet(run, task, lambda packet: packet[target].update({"unexpected": "tampered"}))
                with self.assertRaisesRegex(stage.IndependentSkepticStageError, code):
                    stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_resigned_packet_cannot_replace_frozen_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _ = self.prepare(directory)
            self.rewrite_packet(run, task, lambda packet: packet.update(task_prompt="读取正向结论后反证"))
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_PACKET_CONTEXT_BINDING_INVALID"):
                stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_task_protocol_downgrade_is_rejected_after_resigning_index(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, _ = self.prepare(directory)
            path = run / "research/skeptic/dispatch-index.json"
            index = json.loads(path.read_text())
            index["tasks"][0].pop("semantic_output_version")
            index["index_hash"] = canonical_hash({key: value for key, value in index.items() if key != "index_hash"})
            path.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_OUTPUT_PROTOCOL_BINDING_INVALID"):
                stage.read_dispatch_index(run)

    def test_synthetic_legacy_packet_is_readable_but_write_and_launch_are_retired(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _ = self.prepare(directory)
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
            with patch("subprocess.Popen") as process:
                with self.assertRaisesRegex(stage.IndependentSkepticStageError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    stage.launch_skeptic_phase(fixtures.ROOT, run_dir=run)
                process.assert_not_called()
            self.assertEqual({path: file_hash(path) for path in before}, before)

    def test_synthetic_previous_native_packet_stays_read_only_and_byte_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _ = self.prepare(directory)
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
            self.assertEqual(json.loads(stage.serialize_skeptic_dispatch_context(loaded)), packet)
            with self.assertRaisesRegex(ValueError, "COUNTER_LEGACY_REFERENCE_WRITE_RETIRED"):
                stage.capture_skeptic_report(fixtures.ROOT, run, task_name=task["task_name"],
                    raw_message=json.dumps(self.draft(task)), model="gpt-5.6-terra")
            with self.assertRaisesRegex(ValueError, "COUNTER_LEGACY_REFERENCE_RESUME_RETIRED"):
                stage.prepare_skeptic_resume(fixtures.ROOT, run)
            with patch("subprocess.Popen") as process:
                with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    stage.launch_skeptic_phase(fixtures.ROOT, run_dir=run)
                process.assert_not_called()
            self.assertEqual({path: file_hash(path) for path in before}, before)

    def test_invocation_protocol_drift_rejected_even_with_valid_manifest_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _ = self.prepare(directory)
            path = run / task["invocation_ref"]
            invocation = json.loads(path.read_text())
            invocation.pop("semantic_output_version")
            invocation["manifest_hash"] = canonical_hash({k: v for k, v in invocation.items() if k != "manifest_hash"})
            path.write_text(json.dumps(invocation), encoding="utf-8")
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "COUNTER_OUTPUT_PROTOCOL_BINDING_INVALID"):
                stage.build_skeptic_dispatch_packet(fixtures.ROOT, run, task["task_name"])

    def test_existing_formal_business_schema_and_validator_remain_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, _ = self.prepare(directory)
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
