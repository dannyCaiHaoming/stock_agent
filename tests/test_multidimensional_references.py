from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tests import test_multidimensional_stage as fixtures
from product.runtime.codex_hook_recorder import handle_hook_event, _multidimensional_repair_packet, _multidimensional_draft_diagnostics
from product.runtime.fixture_mcp import StatelessFixtureTools, _write_event
from product.runtime.multidimensional_references import translate_references
from product.runtime.multidimensional_stage import build_multidimensional_dispatch_packet, _text_locator
from product.runtime.multidimensional_stage import (
    serialize_multidimensional_model_context, serialize_multidimensional_initial_context,
    _verified_retry_dependencies, read_retry_dependencies, build_multidimensional_task_prompt,
    finalize_multidimensional_task_evidence,
    launch_multidimensional_stage,
)


class ReferenceBoundaryTests(unittest.TestCase):
    def test_unparseable_json_preserves_diagnostics_but_cannot_authorize_full_regeneration(self):
        for defect in ("empty_key", "truncated", "fenced"):
            for second in ("valid", "syntax", "reference", "identity"):
                with self.subTest(defect=defect, second=second), tempfile.TemporaryDirectory() as directory:
                    f, run, task = self.prepare_with_document(Path(directory))
                    env = f.targeted_environment(run, task)
                    handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=env)
                    handle_hook_event(f.start_payload(task, parent="dependency-parent", child="r"), environ=env)
                    draft = f.dimension_draft(task)
                    payload = f.stop_payload(task, draft, parent="dependency-parent", child="r")
                    original = payload["last_assistant_message"]
                    malformed = (original[:-1] + ',""}' if defect == "empty_key" else
                                 original[:-1] if defect == "truncated" else '```json\n' + original + '\n```')
                    payload["last_assistant_message"] = malformed
                    first, response = handle_hook_event(payload, environ=env)
                    self.assertEqual(first["output_capture"]["repair_state"], "NOT_ALLOWED", first)
                    self.assertNotEqual(response.get("decision"), "block")
                    self.assertNotIn("repair_request", first)
                    finding = first["output_capture"]["diagnostics"]["findings"][0]
                    self.assertEqual(finding["code"], "RESEARCH_OUTPUT_JSON_INVALID")
                    self.assertGreaterEqual(finding["line"], 1)
                    self.assertNotIn("original_draft", first["output_capture"]["diagnostics"])
                    self.assertEqual((run / first["output_capture"]["raw_path"]).read_text().rstrip('\n'), malformed)
                    if second == "reference":
                        draft["artifact_refs"] = ["forged.json"]
                    if second == "identity":
                        draft["run_id"] = "forged-run"
                    payload = f.stop_payload(task, draft, parent="dependency-parent", child="r")
                    if second == "syntax":
                        payload["last_assistant_message"] = malformed
                    final, response = handle_hook_event(payload, environ=env)
                    self.assertEqual(final["output_capture"]["status"], "FAILED", final)
                    self.assertEqual(final["output_capture"]["failure_code"],
                                     "RESEARCH_OUTPUT_IDENTITY_CONFLICT" if second == "identity" else "LOCAL_REVISION_NOT_AUTHORIZED")
                    if second != "identity":
                        self.assertEqual(final["output_capture"]["repair_state"], "EXHAUSTED")
                    self.assertNotEqual(response.get("decision"), "block")

    def test_json_syntax_feedback_rejects_missing_binding_oversize_and_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = self.prepare_with_document(Path(directory))
            env = f.targeted_environment(run, task)
            handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=env)
            handle_hook_event(f.start_payload(task, parent="dependency-parent", child="r"), environ=env)
            payload = f.stop_payload(task, f.dimension_draft(task), parent="dependency-parent", child="r")
            payload["last_assistant_message"] = '{"secret":"never-copy-this", ""}'
            args = {"failure_code": "RESEARCH_OUTPUT_JSON_INVALID", "attempt": 1}
            self.assertIsNone(_multidimensional_repair_packet(payload, env, **args))
            for message in (None, "{}", "[]", "中" * (256 * 1024 // 3 + 1)):
                changed = dict(payload, last_assistant_message=message)
                self.assertEqual(_multidimensional_draft_diagnostics(changed, env, failure_code=args["failure_code"])["status"], "UNAVAILABLE")
            record, _ = handle_hook_event(payload, environ=env)
            self.assertNotIn("never-copy-this", json.dumps(record["output_capture"]["diagnostics"]))
            trusted = copy.deepcopy(record)
            trusted["identity_binding"]["status"] = "CONFLICT"
            self.assertIsNone(_multidimensional_repair_packet(payload, env, trusted_record=trusted, **args))
            path = run / task["packet_path"]
            packet = json.loads(path.read_text())
            packet["instruction"] += " tampered"
            path.write_text(json.dumps(packet))
            self.assertIsNone(_multidimensional_repair_packet(payload, env, trusted_record=record, **args))

    def test_retry_launcher_selects_only_research_and_counts_one(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = self.prepare_with_document(Path(directory))

            def simulated(command, *, input, cwd, env, **kwargs):
                self.assertEqual(json.loads(env["STOCK_AGENT_RESEARCH_TASK_NAMES"]), [task["task_name"]])
                self.assertIn('"dispatched":1', input)
                record, _ = handle_hook_event(f.dispatch_payload(task, parent="retry"), environ=env)
                self.assertEqual(record["decision"], "ALLOW")
                handle_hook_event(f.start_payload(task, parent="retry", child="r"), environ=env)
                record, _ = handle_hook_event(f.stop_payload(task, f.dimension_draft(task), parent="retry", child="r"), environ=env)
                self.assertEqual(record["output_capture"]["status"], "SAVED")
                (Path(env["TMPDIR"]) / "final-message.json").write_text(json.dumps({
                    "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH", "run_id": task["run_id"],
                    "dispatched": 1, "completed": 1,
                }))
                return subprocess.CompletedProcess([], 0, "", "")

            with patch("product.runtime.multidimensional_stage.subprocess.run", side_effect=simulated), patch(
                "product.runtime.multidimensional_stage._adopt_multidimensional_retry", return_value={"status": "PASSED"}
            ):
                result, code = launch_multidimensional_stage(fixtures.ROOT, run_dir=run, task_name=task["task_name"])
            self.assertEqual(code, 0)
            proof_path = next((run / "invocation/retries").glob("*/attempt-1/task-execution-proof.json"))
            proof = json.loads(proof_path.read_text())
            self.assertEqual(proof["task_names"], [task["task_name"]])
            self.assertEqual(len(proof["reused_dependencies"]), 1)

    def test_report_retry_reuses_dependency_without_dispatch_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = self.prepare_with_document(Path(directory))
            reused = _verified_retry_dependencies(run, task["task_name"])
            self.assertEqual(len(reused), 1)
            dependency_path = run / reused[0]["report_ref"]
            original = dependency_path.read_bytes()
            attempt = run / "invocation/retries/research/attempt-1"
            attempt.mkdir(parents=True)
            (attempt / "reused-dependencies.json").write_text(json.dumps({
                "target_task_name": task["task_name"], "dependencies": reused,
            }))
            prompt = build_multidimensional_task_prompt(fixtures.ROOT, run, task["task_name"], reused_dependencies=reused)
            self.assertIn('"dispatched":1', prompt)
            environment = f.targeted_environment(run, task)
            environment["STOCK_AGENT_SUBAGENT_EVENT_LOG"] = str(attempt / "subagent-events.jsonl")
            environment["STOCK_AGENT_SUBAGENT_DISPATCH_LOG"] = str(attempt / "subagent-dispatches.jsonl")
            dispatch, _ = handle_hook_event(f.dispatch_payload(task, parent="retry"), environ=environment)
            self.assertEqual(dispatch["decision"], "ALLOW", dispatch)
            handle_hook_event(f.start_payload(task, parent="retry", child="r"), environ=environment)
            saved, _ = handle_hook_event(f.stop_payload(task, f.dimension_draft(task), parent="retry", child="r"), environ=environment)
            self.assertEqual(saved["output_capture"]["status"], "SAVED")
            proof = finalize_multidimensional_task_evidence(fixtures.ROOT, run, task["task_name"], invocation_dir=attempt)
            self.assertEqual(proof["task_names"], [task["task_name"]])
            self.assertEqual(len(proof["report_inventory"]), 2)
            self.assertEqual(len(proof["reused_dependencies"]), 1)
            self.assertEqual(dependency_path.read_bytes(), original)
            dependency_path.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "REUSE_CHANGED"):
                read_retry_dependencies(run, attempt, task["task_name"])
            dependency_path.write_bytes(original)
            log = run / "invocation/subagent-events.jsonl"
            original_log = log.read_text()
            log.write_text(original_log.replace('"SAVED"', '"FAILED"'))
            with self.assertRaisesRegex(ValueError, "REUSE_EVENT_INVALID"):
                read_retry_dependencies(run, attempt, task["task_name"])

    def prepare_with_document(self, root):
        original = fixtures.gate_for

        def gate_with_document(handoff):
            gate = original(handoff)
            gate["allowed_evidence"].append({
                "evidence_id": "ev-issuer-body", "security_id": handoff["portfolio"]["positions"][0]["security_id"],
                "semantic_field": "earnings_release", "value": "Issuer verified earnings discussion. " * 30,
                "source_id": "sec-filing:test", "source_type": "sec",
                "source_locator": "https://www.sec.gov/Archives/example.htm",
                "as_of": "2026-09-10T20:00:00Z", "published_at": "2026-09-10T20:00:00Z",
                "retrieved_at": "2026-09-11T11:00:00Z", "raw_content_hash": "a" * 64,
                "section": "earnings_release", "metadata": {"description": "Issuer earnings release"},
            })
            gate["allowed_evidence_ids"] = sorted(x["evidence_id"] for x in gate["allowed_evidence"])
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = fixtures.canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            return gate

        f = fixtures.MultidimensionalStageTests()
        with patch.object(fixtures, "gate_for", gate_with_document):
            run, _ = f.prepare(root, count=1)
        index = json.loads((run / "research/dispatch-index.json").read_text())
        f.save_fundamental_dependency(run, index)
        (run / "invocation/process-result.json").write_text(json.dumps({
            "source_integrity_unchanged": True, "timed_out": False, "process_exit_code": 0,
        }))
        task = next(x for x in index["tasks"] if x["capability"] == "RESEARCH_REPORT")
        return f, run, task

    def test_contract_rules_delivered_without_changing_frozen_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task = self.prepare_with_document(Path(directory))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            frozen = copy.deepcopy(packet)
            for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                context = json.loads(serialize(packet))
                self.assertIn("evaluation_status 必须为 SOURCE_LIMITED", context["output_contract_rules"]["status"])
                self.assertEqual(context["task"]["allowed_documents"], translate_references(
                    {"documents": task["allowed_documents"]}, packet["reference_map"], to_model=True,
                )["documents"])
                self.assertIn("不得重写", context["output_contract_rules"]["documents"])
            self.assertEqual(packet, frozen)

    def test_attribution_guidance_delivered_only_to_research_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task = self.prepare_with_document(Path(directory))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            frozen = copy.deepcopy(packet)
            # Verify the same task locks the actual, aligned Skill, not only
            # dynamically injected guidance. This proves the configured binding,
            # not runtime loading or semantic quality of a generated report.
            import hashlib
            skill_path = fixtures.ROOT / "product/skills/research-report-analysis/SKILL.md"
            index = json.loads((run / "research/dispatch-index.json").read_text())
            indexed = next(t for t in index["tasks"] if t["task_name"] == task["task_name"])
            invocation = json.loads((run / indexed["invocation_path"]).read_text())
            self.assertEqual(invocation["skill"]["version"], "1.4.2")
            self.assertEqual(invocation["skill"]["content_hash"], hashlib.sha256(skill_path.read_bytes()).hexdigest())
            agent_path = fixtures.ROOT / "product/.codex/agents/runtime_company_analyst.toml"
            self.assertEqual(invocation["agent_binding"]["content_hash"], hashlib.sha256(agent_path.read_bytes()).hexdigest())
            # 角色只绑定方法 Skill；当前草稿/归属规则来自实际任务契约。
            # 配置和交付一致性不冒充真实 Skill 加载或研究语义质量。
            import tomllib
            config = tomllib.loads(agent_path.read_text())
            self.assertEqual(config["sandbox_mode"], "read-only")
            self.assertTrue(any(entry["enabled"] and entry["path"] == "skills/research-report-analysis"
                                for entry in config["skills"]["config"]))
            for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                context = json.loads(serialize(packet))
                guide = context["research_attribution_guidance"]
                from product.runtime.multidimensional_stage import RESEARCH_ATTRIBUTION_GUIDANCE
                self.assertEqual(guide, RESEARCH_ATTRIBUTION_GUIDANCE)
                self.assertEqual(guide["version"], "research-report-attribution/1.3.1")
                self.assertIn("独立陈述供应商观点可只引许可 Evidence", guide["source"])
                self.assertIn("最后填写引用", guide["self_check"])
                self.assertIn("完全没有估值观点", guide["upstream_scope"])
                for field in ("evidence_refs", "document_refs", "research_claim_refs"):
                    self.assertIn(field, guide["self_check"])
                self.assertIn("不要求覆盖全部上游", guide["self_check"])
                self.assertIn("claims[].evidence_refs", guide["source"])
                self.assertIn("research_claim_refs", guide["source"])
                self.assertIn("research_relationships 可以为空", guide["source"])
                self.assertIn("不得借用 SEC/发行人 document_id", guide["source"])
                self.assertIn("不等于完全没有估值信息", guide["upstream_scope"])
                self.assertIn("不自动推翻上游缺口", guide["upstream_scope"])
                self.assertIn("ID 合法不代表语义支持已验证", guide["self_check"])
                self.assertIn("每一个 resulting_claim_ref", guide["self_check"])
                self.assertIn("收购事实不支持独立研报覆盖不足", guide["self_check"])
            self.assertEqual(packet, frozen)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            for other in index["tasks"]:
                if other["capability"] == "RESEARCH_REPORT":
                    continue
                other_packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, other["task_name"])
                self.assertNotIn("research_attribution_guidance", json.loads(serialize_multidimensional_model_context(other_packet)))
                if other["capability"] == "FUNDAMENTAL_EVENT":
                    self.assertNotIn("research_attribution_guidance", json.loads(serialize_multidimensional_initial_context(other_packet)))

    def test_evidence_only_and_issuer_document_relationship_remain_valid(self):
        # Synthetic contract checks, not a claim that either wording is LLM-verified.
        for with_document in (False, True):
            with self.subTest(with_document=with_document), tempfile.TemporaryDirectory() as directory:
                f, run, task = self.prepare_with_document(Path(directory))
                packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                upstream = next(iter(packet["reference_map"]["claims"]))
                draft = f.dimension_draft(task)
                document = task["allowed_documents"][0]
                document_ref = next(ref for ref, full in packet["reference_map"]["documents"].items()
                                    if full == document["document_id"])
                draft["claims"] = [{
                    "claim_id": "comparison", "question": "与上游何种关系？",
                    "statement": "模拟：披露为上游经营分析补充依据，不推翻其限定缺口。",
                    "kind": "COMPARISON", "evidence_refs": ["ev-issuer-body"],
                    "research_claim_refs": [upstream],
                    "document_refs": [document["document_id"]] if with_document else [],
                    "assumption_ids": [],
                }]
                if with_document:
                    draft["document_selections"] = [document_ref]
                    draft["research_relationships"] = [{
                        "relationship_id": "issuer-support", "document_id": document["document_id"],
                        "target_claim_refs": [upstream], "effect": "SUPPORT",
                        "rationale": "模拟：该发行人披露自身提供经营依据。",
                        "resulting_claim_refs": ["comparison"],
                    }]
                environment = f.targeted_environment(run, task)
                handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=environment)
                handle_hook_event(f.start_payload(task, parent="dependency-parent", child="r"), environ=environment)
                result, _ = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="r"), environ=environment)
                self.assertEqual(result["output_capture"]["status"], "SAVED", result)
                report = json.loads((run / result["output_capture"]["path"]).read_text())
                self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
                self.assertEqual(len(report["research_relationships"]), int(with_document))

    def test_metadata_and_state_same_session_repair_or_exhaustion(self):
        for defect in ("state", "document", "failed_evaluation"):
            for corrected in (True, False):
                with self.subTest(defect=defect, corrected=corrected), tempfile.TemporaryDirectory() as directory:
                    f, run, task = self.prepare_with_document(Path(directory))
                    environment = f.targeted_environment(run, task)
                    handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=environment)
                    handle_hook_event(f.start_payload(task, parent="dependency-parent", child="r"), environ=environment)
                    draft = f.dimension_draft(task)
                    if defect == "document":
                        draft["document_selections"] = ["d.not-authorized.1"]
                    else:
                        draft["status"] = "SOURCE_LIMITED" if defect == "state" else "FAILED"
                        draft["evaluation_status"] = "NOT_EVALUATED" if defect == "state" else "PASS"
                    original = copy.deepcopy(draft)
                    first, response = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="r"), environ=environment)
                    self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED", first)
                    repair = json.loads(response["reason"])
                    self.assertNotIn("original_draft", repair)
                    if defect != "document":
                        self.assertIn("output_contract_rules", repair["validation_details"])
                    else:
                        self.assertTrue(any(f["path"].startswith("/document_selections")
                                            for f in repair["validation_details"]["findings"]))
                    self.assertEqual(json.loads((run / first["output_capture"]["raw_path"]).read_text()), original)
                    if corrected:
                        if defect == "document":
                            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                            draft["document_selections"] = list(packet["reference_map"]["documents"])
                        else:
                            draft["evaluation_status"] = "SOURCE_LIMITED" if defect == "state" else "FAIL"
                    second, _ = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="r"), environ=environment)
                    self.assertEqual(second["output_capture"]["repair_state"], "REPAIRED" if corrected else "EXHAUSTED")
                    self.assertEqual(second["output_capture"]["status"], "SAVED" if corrected else "FAILED")

    def test_compound_diagnostics_unknown_document_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = self.prepare_with_document(Path(directory))
            environment = f.targeted_environment(run, task)
            # 历史完整稿只读诊断；不经当前 Stop 写入入口。
            draft = f.formal_dimension_draft(task)
            draft["status"] = "SOURCE_LIMITED"
            draft["documents"] = copy.deepcopy(task["allowed_documents"])
            draft["documents"][0]["as_of"] = "2026-09-11T20:00:00Z"
            draft["claims"] = [{"claim_id": "local", "research_claim_refs": ["invented"]}]
            def repair(value):
                return _multidimensional_repair_packet(
                    f.stop_payload(task, value, parent="p", child="c"), environment,
                    failure_code="DIMENSION_REPORT_SOURCE_LIMITED_STATE_INVALID", attempt=1)
            result = repair(draft)
            self.assertEqual({x["path"] for x in result["validation_details"]["findings"]},
                             {"evaluation_status", "documents[0].as_of", "claims[0].research_claim_refs[0]"})
            self.assertIn("valid_upstream_claims", result["validation_details"])
            self.assertEqual(len(json.dumps(result).encode()) < 16 * 1024, True)
            unknown = copy.deepcopy(draft)
            unknown["documents"][0]["document_id"] = "foreign-document"
            self.assertIsNone(repair(unknown))
            many = copy.deepcopy(draft)
            many["documents"] *= 33
            self.assertIsNone(repair(many))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            oversized = copy.deepcopy(packet)
            oversized["task"]["allowed_documents"][0]["title"] = "large " * 4000
            with patch("product.runtime.multidimensional_references.load_reference_packet", return_value=oversized):
                self.assertIsNone(repair(draft))
            # Frozen packet tampering prevents diagnostic feedback, not just saving.
            path = run / task["packet_path"]
            frozen = json.loads(path.read_text())
            frozen["instruction"] = "tampered"
            path.write_text(json.dumps(frozen))
            self.assertIsNone(repair(draft))

    def test_short_query_calculate_and_stop_preserve_canonical_report(self):
        f = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = f.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            mapping = packet["reference_map"]
            short, full = next(iter(mapping["evidence"].items()))
            args = {"run_id": task["run_id"], "agent": task["agent"], "invocation_id": task["invocation_id"]}
            tools = StatelessFixtureTools(default_run_dir=run)
            result = tools.query(**args, evidence_ids=[short])
            self.assertEqual(result["evidence"][0]["evidence_id"], short)
            self.assertEqual(tools.events[-1]["evidence_ids"], [full])
            self.assertEqual(result["reference_map_hash"], mapping["map_hash"])
            short_ids = list(mapping["evidence"])[:2]
            calculated = tools.calculate(**args, evidence_ids=short_ids, calculation_id="ratio-test", operation="ratio")
            _write_event(run / "events/mcp/events.jsonl", tools.events[-1])
            self.assertEqual(calculated["evidence_ids"], short_ids)
            ledger = json.loads((run / calculated["artifact_ref"]).read_text().splitlines()[0])
            self.assertEqual(ledger["evidence_ids"], [mapping["evidence"][s] for s in short_ids])
            self.assertEqual(ledger["output"]["value"], calculated["value"])
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                tools.query(**args, evidence_ids=["e.other-task.1"])
            environment = f.targeted_environment(run, task)
            handle_hook_event(f.dispatch_payload(task, parent="p"), environ=environment)
            handle_hook_event(f.start_payload(task, parent="p", child="c"), environ=environment)
            draft = f.dimension_draft(task)
            draft["claims"] = [{
                "claim_id": "local-1", "question": "事实？", "statement": f"模拟文本保留 {short}",
                "kind": "FACT", "evidence_refs": [short], "research_claim_refs": [],
                "document_refs": [], "assumption_ids": [],
            }]
            stopped, _ = handle_hook_event(f.stop_payload(task, draft, parent="p", child="c"), environ=environment)
            self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
            report = json.loads((run / stopped["output_capture"]["path"]).read_text())
            self.assertEqual(report["claims"][0]["evidence_refs"], [full])
            self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
            raw = json.loads((run / stopped["output_capture"]["raw_path"]).read_text())
            self.assertEqual(raw, draft)
            broken = copy.deepcopy(mapping)
            broken["evidence"][short] = "ev-forged"
            with self.assertRaisesRegex(ValueError, "MAP_INVALID"):
                translate_references(draft, broken)

    def test_legacy_packet_keeps_full_id_tool_protocol(self):
        f = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = f.prepare(Path(directory), count=1)
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            path = run / task["packet_path"]
            packet = json.loads(path.read_text())
            packet.pop("reference_transport_version")
            path.write_text(json.dumps(packet))
            task["packet_hash"] = fixtures.canonical_hash(packet)
            index_path.write_text(json.dumps(index))
            built = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            self.assertNotIn("reference_map", built)
            full = task["allowed_evidence_ids"][0]
            output = StatelessFixtureTools(default_run_dir=run).query(
                run_id=task["run_id"], agent=task["agent"], invocation_id=task["invocation_id"], evidence_ids=[full])
            self.assertEqual(output["evidence"][0]["evidence_id"], full)

    def test_upstream_claim_repair_and_unknown_reference_are_bounded(self):
        f = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = f.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            f.save_fundamental_dependency(run, index)
            task = next(t for t in index["tasks"] if t["capability"] == "RESEARCH_REPORT")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            mapping = packet["reference_map"]
            claim_short = next(iter(mapping["claims"]))
            # 直接辅助函数测试使用带身份的历史稿；当前新稿身份来自 Start。
            draft = f.formal_dimension_draft(task)
            draft["claims"] = [{"claim_id": "local", "research_claim_refs": ["mrvl_growth_continuity"]}]
            draft["research_relationships"] = [{"target_claim_refs": ["mrvl_growth_continuity"]}]
            environment = f.targeted_environment(run, task)
            payload = f.stop_payload(task, draft, parent="p", child="c")
            repair = _multidimensional_repair_packet(payload, environment, failure_code="DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING", attempt=1)
            self.assertEqual(len(repair["validation_details"]["findings"]), 2)
            self.assertEqual(repair["validation_details"]["valid_upstream_claims"][0]["claim_id"], "mrvl_core_drivers")
            self.assertIsNone(_multidimensional_repair_packet(payload, environment, failure_code="DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING", attempt=2))
            draft["claims"][0]["research_claim_refs"] = [claim_short]
            resolved = translate_references(draft, mapping)
            self.assertEqual(resolved["claims"][0]["research_claim_refs"],
                             [mapping["claims"][claim_short]["canonical_ref"]])
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                translate_references({"evidence_refs": [claim_short]}, mapping)
            unknown = f.formal_dimension_draft(task)
            unknown["claims"] = [{"claim_id": "local", "evidence_refs": ["e.wrong.1"]}]
            repair = _multidimensional_repair_packet(f.stop_payload(task, unknown, parent="p", child="c"), environment,
                failure_code="MULTIDIMENSIONAL_REFERENCE_UNKNOWN:claims[0].evidence_refs[0]:e.wrong.1", attempt=1)
            self.assertIsNotNone(repair)

    def test_heading_not_confused_with_short_substantive_text(self):
        heading = {"value": "Item 1. Business 3 ", "metadata": {"section": "business", "truncated": False}}
        self.assertEqual(_text_locator(heading)["content_kind"], "HEADING_ONLY")
        body = {"value": "We sell chips.", "metadata": {"section": "business", "truncated": False}}
        self.assertEqual(_text_locator(body)["content_kind"], "SECTION_TEXT")
        self.assertEqual(_text_locator({"value": "We sell chips."})["content_kind"], "UNKNOWN")
        self.assertEqual(_text_locator({"value": "We sell chips.", "metadata": {"section": "business", "truncated": True}})["content_kind"], "SECTION_EXCERPT")

    def test_upstream_same_session_correction_saves_or_exhausts(self):
        f = fixtures.MultidimensionalStageTests()
        for corrected in (True, False):
            with self.subTest(corrected=corrected), tempfile.TemporaryDirectory() as directory:
                run, _ = f.prepare(Path(directory), count=1)
                index = json.loads((run / "research/dispatch-index.json").read_text())
                f.save_fundamental_dependency(run, index)
                task = next(t for t in index["tasks"] if t["capability"] == "RESEARCH_REPORT")
                environment = f.targeted_environment(run, task)
                handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=environment)
                handle_hook_event(f.start_payload(task, parent="dependency-parent", child="research-c"), environ=environment)
                draft = f.dimension_draft(task)
                draft["claims"] = [{
                    "claim_id": "local", "question": "对照？", "statement": "模拟研究主张关系。",
                    "kind": "INTERPRETATION", "evidence_refs": [],
                    "research_claim_refs": ["mrvl_growth_continuity"],
                    "document_refs": [], "assumption_ids": [],
                }]
                first, response = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="research-c"), environ=environment)
                self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED", first["output_capture"])
                repair = json.loads(response["reason"])
                if corrected:
                    draft["claims"][0]["research_claim_refs"] = [next(iter(repair["validation_details"]["upstream_short_references"]))]
                second, _ = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="research-c"), environ=environment)
                self.assertEqual(second["output_capture"]["status"], "SAVED" if corrected else "FAILED")
                self.assertEqual(second["output_capture"]["repair_state"], "REPAIRED" if corrected else "EXHAUSTED")
