from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run
from product.runtime.common_stock_stage import prepare_common_stock_stage_run
from product.council.research_output import persist_equity_research_report
from tests.test_common_stock_research_contracts import (
    gate_for, stock_handoff, valid_report,
)
from tests.test_multidimensional_stage import MultidimensionalStageTests

from product.runtime.independent_skeptic_stage import (
    DISPATCH_VERSION,
    IndependentSkepticStageError,
    build_first_pass_input,
    capture_skeptic_report,
    finalize_skeptic_phase,
    prepare_skeptic_phase,
    prepare_skeptic_resume,
    read_dispatch_index,
    scope_evidence_ids,
    validate_core_coverage,
    validate_first_pass_input,
    validate_forward_gate,
    validate_report_query_closure,
)
from product.runtime.hashing import canonical_hash, file_hash

ROOT = Path(__file__).resolve().parents[1]


class IndependentSkepticContractTests(unittest.TestCase):
    def test_report_requires_actual_same_invocation_query_and_attempt_10_is_valid(self):
        with self.assertRaisesRegex(
            IndependentSkepticStageError, "COUNTER_REPORT_EVIDENCE_NOT_QUERIED:ev-2"
        ):
            validate_report_query_closure(
                {"evidence_refs": ["ev-1", "ev-2"]},
                [{"evidence_ids": ["ev-1"]}],
            )
        self.assertEqual(
            {"ev-1", "ev-2"},
            validate_report_query_closure(
                {"evidence_refs": ["ev-1"], "counter_evidence_refs": ["ev-2"]},
                [{"evidence_ids": ["ev-1", "ev-2"]}],
            ),
        )
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            relative = "research/skeptic/attempts/10/dispatch-index.json"
            index = {
                "schema_version": DISPATCH_VERSION,
                "run_id": "attempt-10-run",
                "attempt": 10,
                "tasks": [],
            }
            index["index_hash"] = canonical_hash(index)
            path = run / relative
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(index), encoding="utf-8")
            self.assertEqual(10, read_dispatch_index(run, relative)["attempt"])

    def test_real_forward_gate_prepares_skeptic_without_mocking_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id = "counter-real-forward-run"
            handoff = stock_handoff(1)
            gate = gate_for(handoff, run_id)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")

            company = root / "company"
            prepare_common_stock_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=company, run_id=run_id, model="gpt-5.6-terra",
            )
            company_gate = json.loads((company / "evidence/gate.json").read_text())
            company_index = json.loads((company / "research/dispatch-index.json").read_text())
            for task in company_index["tasks"]:
                request = json.loads((company / task["request_path"]).read_text())
                report = valid_report(request)
                report["report_id"] = f"equity:{task['security_id']}"
                evidence = {
                    item["evidence_id"]: item for item in company_gate["allowed_evidence"]
                }
                persist_equity_research_report(
                    company / "research/reports", report=report, request=request,
                    evidence=[evidence[item] for item in request["allowed_evidence_ids"]],
                )
            company_proof = {
                "schema_version": "common-stock-research-execution-proof/1.0.0",
                "run_id": run_id,
                "expected_tasks": sorted(item["task_name"] for item in company_index["tasks"]),
                "completed_security_ids": sorted(item["security_id"] for item in company_index["tasks"]),
                "intervals": [], "parallel_overlap": False, "all_reports_valid": True,
                "agent": {}, "skills": [], "gate_hash": company_gate["bundle_hash"],
                "complete_portfolio_decision": False,
            }
            company_proof["proof_hash"] = canonical_hash(company_proof)
            (company / "research/execution-proof.json").write_text(
                json.dumps(company_proof), encoding="utf-8"
            )

            base = root / "base"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=base, run_id=run_id, model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
                company_research_run_path=company,
            )
            MultidimensionalStageTests().complete_with_explicit_gaps(base)
            run = base

            forward = validate_forward_gate(ROOT, run)
            self.assertEqual(run_id, forward["run_id"])
            prepared = prepare_skeptic_phase(ROOT, run)
            self.assertEqual("PREPARED", prepared["status"])
            self.assertEqual(1, prepared["task_count"])
            agent_input = json.loads(next(
                (run / "research/skeptic/inputs").glob("*.json")
            ).read_text())
            self.assertNotIn("forward_bundle_hash", agent_input)
            self.assertNotIn("unresolved_cross_dimension_questions", agent_input)

    def test_resume_keeps_first_attempt_and_retries_only_unready_security(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            (root / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            (root / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                run_dir=run, run_id="counter-resume-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            security_ids = [item["security_id"] for item in handoff["portfolio"]["positions"]]
            bundle = {"run_id": "counter-resume-run", "common_stock_security_ids": security_ids,
                      "bundle_hash": "b" * 64}
            bundle_path = run / "research/holding-research-bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            (run / "research/holding-research-bundle.md").write_text("正向样例", encoding="utf-8")
            fake_forward = {
                "run_id": "counter-resume-run", "decision_cutoff": gate["decision_cutoff"],
                "gate_hash": json.loads((run / "evidence/gate.json").read_text())["bundle_hash"],
                "bundle_hash": bundle["bundle_hash"], "bundle_file_hash": file_hash(bundle_path),
                "common_stock_security_ids": security_ids,
            }
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                prepare_skeptic_phase(ROOT, run)
            original_index = json.loads((run / "research/skeptic/dispatch-index.json").read_text())
            first = original_index["tasks"][0]
            invocation = json.loads((run / first["invocation_ref"]).read_text())
            evidence_id = first["allowed_evidence_ids"][0]
            report = {
                "schema_version": "counter-thesis-report/2.1.0", "run_id": "counter-resume-run",
                "invocation_id": first["invocation_id"], "status": "COMPLETE",
                "agent": "runtime_skeptic", "mode": "INDEPENDENT_FIRST_PASS",
                "scope": first["security_id"], "challenges": [], "assumptions": [],
                "evidence_refs": [evidence_id], "counter_evidence_refs": [],
                "uncertainties": [], "data_gaps": [], "invalidation_conditions": [],
                "confidence": 0.5, "confidence_rationale": "测试引用当前证据。",
                "skill_execution": invocation["skill_execution"], "artifact_refs": [],
            }
            capture_skeptic_report(
                ROOT, run, task_name=first["task_name"], raw_message=json.dumps(report),
                model="gpt-5.6-terra",
            )
            event_dir = run / "invocation/skeptic"
            event_dir.mkdir(parents=True)
            (event_dir / "subagent-dispatches.jsonl").write_text(
                json.dumps({"decision": "ALLOW", "task_name": first["task_name"]}) + "\n", encoding="utf-8"
            )
            (event_dir / "subagent-events.jsonl").write_text("\n".join(json.dumps(item) for item in [{
                "hook_event_name": "SubagentStart", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic", "context_binding": {
                    "status": "DELIVERED", "invocation_id": first["invocation_id"],
                },
            }, {
                "hook_event_name": "SubagentStop", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic", "output_binding": {"invocation_id": first["invocation_id"]},
                "output_capture": {"status": "SAVED", "output_hash": canonical_hash(report)},
            }]) + "\n", encoding="utf-8")
            tool_event = {
                "adapter_version": "fixture-gate-scoped/2.3.0", "run_id": "counter-resume-run",
                "agent": "runtime_skeptic", "invocation_id": first["invocation_id"],
                "tool": "fixture_evidence.query", "evidence_ids": [evidence_id],
                "access_mode": "read", "input_hash": "a" * 64, "output_hash": "b" * 64,
            }
            tool_event["event_hash"] = canonical_hash(tool_event)
            (run / "events/mcp").mkdir(parents=True)
            (run / "events/mcp/events.jsonl").write_text(json.dumps(tool_event) + "\n", encoding="utf-8")
            successful_report_hash = file_hash(run / first["report_ref"])
            successful_invocation_hash = file_hash(run / first["invocation_ref"])
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                partial = finalize_skeptic_phase(ROOT, run)
            self.assertEqual("PARTIAL", partial["status"])
            (run / "invocation/skeptic").mkdir(parents=True, exist_ok=True)
            (run / "invocation/skeptic/process-result.json").write_text(json.dumps({
                "run_id": "counter-resume-run", "source_integrity_unchanged": True,
                "stage_status": "PARTIAL",
            }), encoding="utf-8")
            original_package_hash = file_hash(run / "research/skeptic/pre-decision-research-package.json")
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                resumed = prepare_skeptic_resume(ROOT, run)
            self.assertEqual(2, resumed["attempt"])
            self.assertEqual([original_index["tasks"][1]["task_name"]], resumed["retry_task_names"])
            latest = json.loads((run / resumed["dispatch_index"]).read_text())
            self.assertEqual(2, latest["attempt"])
            self.assertEqual(first, latest["tasks"][0])
            self.assertEqual(2, latest["tasks"][1]["attempt"])
            self.assertEqual(successful_report_hash, file_hash(run / first["report_ref"]))
            self.assertEqual(successful_invocation_hash, file_hash(run / first["invocation_ref"]))
            self.assertEqual(original_package_hash, file_hash(run / "research/skeptic/pre-decision-research-package.json"))
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                with self.assertRaisesRegex(IndependentSkepticStageError, "COUNTER_INPUT_INVALID"):
                    prepare_skeptic_resume(ROOT, run)
            second = latest["tasks"][1]
            retry_invocation = json.loads((run / second["invocation_ref"]).read_text())
            retry_evidence_id = second["allowed_evidence_ids"][0]
            retry_report = {
                **report, "invocation_id": second["invocation_id"],
                "scope": second["security_id"], "evidence_refs": [retry_evidence_id],
                "skill_execution": retry_invocation["skill_execution"],
            }
            capture_skeptic_report(
                ROOT, run, task_name=second["task_name"], raw_message=json.dumps(retry_report),
                model="gpt-5.6-terra", index_ref=resumed["dispatch_index"],
            )
            retry_events = run / "invocation/skeptic/attempt-2"
            retry_events.mkdir(parents=True)
            (retry_events / "subagent-dispatches.jsonl").write_text(
                json.dumps({"decision": "ALLOW", "task_name": second["task_name"]}) + "\n", encoding="utf-8"
            )
            (retry_events / "subagent-events.jsonl").write_text("\n".join(json.dumps(item) for item in [{
                "hook_event_name": "SubagentStart", "child_session_id": "child-2",
                "agent_type": "runtime_skeptic", "context_binding": {
                    "status": "DELIVERED", "invocation_id": second["invocation_id"],
                },
            }, {
                "hook_event_name": "SubagentStop", "child_session_id": "child-2",
                "agent_type": "runtime_skeptic", "output_binding": {"invocation_id": second["invocation_id"]},
                "output_capture": {"status": "SAVED", "output_hash": canonical_hash(retry_report)},
            }]) + "\n", encoding="utf-8")
            retry_event = {
                **tool_event, "invocation_id": second["invocation_id"],
                "evidence_ids": [retry_evidence_id],
            }
            retry_event.pop("event_hash")
            retry_event["event_hash"] = canonical_hash(retry_event)
            with (run / "events/mcp/events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(retry_event) + "\n")
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                completed = finalize_skeptic_phase(ROOT, run, index_ref=resumed["dispatch_index"])
            self.assertEqual("PASSED", completed["status"])
            self.assertEqual(successful_report_hash, file_hash(run / first["report_ref"]))
            self.assertEqual(original_package_hash, file_hash(run / "research/skeptic/pre-decision-research-package.json"))

    def test_finalizer_builds_reference_only_package_and_blocks_hash_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            (root / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            (root / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                run_dir=run, run_id="counter-package-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            security_id = handoff["portfolio"]["positions"][0]["security_id"]
            bundle = {
                "run_id": "counter-package-run", "common_stock_security_ids": [security_id],
                "bundle_hash": "b" * 64,
            }
            bundle_path = run / "research/holding-research-bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            (run / "research/holding-research-bundle.md").write_text("正向测试报告", encoding="utf-8")
            frozen_gate = json.loads((run / "evidence/gate.json").read_text())
            fake_forward = {
                "run_id": "counter-package-run", "decision_cutoff": gate["decision_cutoff"],
                "gate_hash": frozen_gate["bundle_hash"], "bundle_hash": bundle["bundle_hash"],
                "bundle_file_hash": file_hash(bundle_path),
                "common_stock_security_ids": [security_id],
            }
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                prepare_skeptic_phase(ROOT, run)
            index = json.loads((run / "research/skeptic/dispatch-index.json").read_text())
            task = index["tasks"][0]
            invocation = json.loads((run / task["invocation_ref"]).read_text())
            evidence_id = task["allowed_evidence_ids"][0]
            report = {
                "schema_version": "counter-thesis-report/2.1.0", "run_id": "counter-package-run",
                "invocation_id": task["invocation_id"], "status": "COMPLETE",
                "agent": "runtime_skeptic", "mode": "INDEPENDENT_FIRST_PASS",
                "scope": security_id, "challenges": [{
                    "challenge_id": "challenge-1", "statement": "测试中的可观察风险。",
                    "evidence_refs": [evidence_id], "assumption_ids": [],
                    "resolution_evidence_needed": ["后续正式披露"],
                }],
                "assumptions": [], "evidence_refs": [evidence_id],
                "counter_evidence_refs": [], "uncertainties": [], "data_gaps": [],
                "invalidation_conditions": ["正式披露否定风险"], "confidence": 0.6,
                "confidence_rationale": "已核验当前事实。",
                "skill_execution": invocation["skill_execution"], "artifact_refs": [],
            }
            capture_skeptic_report(
                ROOT, run, task_name=task["task_name"],
                raw_message=json.dumps(report), model="gpt-5.6-terra",
            )
            event_dir = run / "invocation/skeptic"
            event_dir.mkdir(parents=True)
            (event_dir / "subagent-dispatches.jsonl").write_text(json.dumps({
                "decision": "ALLOW", "task_name": task["task_name"],
            }) + "\n", encoding="utf-8")
            events = [{
                "hook_event_name": "SubagentStart", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic",
                "context_binding": {"status": "DELIVERED", "invocation_id": task["invocation_id"]},
            }, {
                "hook_event_name": "SubagentStop", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic",
                "output_binding": {"invocation_id": task["invocation_id"]},
                "output_capture": {"status": "SAVED", "output_hash": canonical_hash(report)},
            }]
            (event_dir / "subagent-events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8"
            )
            event_path = run / "events/mcp/events.jsonl"
            event_path.parent.mkdir(parents=True)
            tool_event = {
                "event_type": "mcp_tool_result", "adapter_version": "fixture-gate-scoped/2.3.0",
                "run_id": "counter-package-run", "agent": "runtime_skeptic",
                "invocation_id": task["invocation_id"], "tool": "fixture_evidence.query",
                "evidence_ids": [evidence_id], "access_mode": "read",
                "input_hash": "a" * 64, "output_hash": "b" * 64,
            }
            tool_event["event_hash"] = canonical_hash(tool_event)
            event_path.write_text(json.dumps(tool_event) + "\n", encoding="utf-8")
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                result = finalize_skeptic_phase(ROOT, run)
            self.assertEqual("PASSED", result["status"])
            package = json.loads((run / "research/skeptic/pre-decision-research-package.json").read_text())
            self.assertEqual("DOWNSTREAM_READY", package["consumability"])
            self.assertNotIn("challenges", package)
            bundle_path.write_text(json.dumps({**bundle, "bundle_hash": "c" * 64}), encoding="utf-8")
            from product.runtime.independent_skeptic_stage import validate_predecision_package
            with self.assertRaisesRegex(IndependentSkepticStageError, "PACKAGE_BINDING_INVALID"):
                validate_predecision_package(ROOT, run, package)

    def test_two_securities_have_distinct_server_side_query_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            (root / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            (root / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                run_dir=run, run_id="counter-scope-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            fake_forward = {
                "run_id": "counter-scope-run", "decision_cutoff": gate["decision_cutoff"],
                "gate_hash": json.loads((run / "evidence/gate.json").read_text())["bundle_hash"],
                "bundle_hash": "b" * 64, "bundle_file_hash": "c" * 64,
                "common_stock_security_ids": [
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                ],
            }
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                prepare_skeptic_phase(ROOT, run)
            index = json.loads((run / "research/skeptic/dispatch-index.json").read_text())
            first, second = index["tasks"]
            self.assertEqual(2, len(index["tasks"]))
            own_id = first["allowed_evidence_ids"][0]
            other_id = second["allowed_evidence_ids"][0]
            tool = StatelessFixtureTools(default_run_dir=run)
            identity = {
                "run_id": "counter-scope-run", "agent": "runtime_skeptic",
                "invocation_id": first["invocation_id"],
            }
            self.assertEqual(
                own_id, tool.query(**identity, evidence_ids=[own_id])["evidence"][0]["evidence_id"]
            )
            self.assertEqual(
                "ratio", tool.calculate(
                    **identity, calculation_id="own-ratio", operation="ratio",
                    evidence_ids=first["allowed_evidence_ids"],
                )["operation"]
            )
            with self.assertRaisesRegex(ToolAccessError, "INVOCATION_EVIDENCE_NOT_AUTHORIZED"):
                tool.query(**identity, evidence_ids=[other_id])
            with self.assertRaisesRegex(ToolAccessError, "INVOCATION_EVIDENCE_NOT_AUTHORIZED"):
                tool.calculate(
                    **identity, calculation_id="cross-ratio", operation="ratio",
                    evidence_ids=[own_id, other_id],
                )
            with self.assertRaisesRegex(ToolAccessError, "INVOCATION_EVIDENCE_NOT_AUTHORIZED"):
                tool.query(**{**identity, "invocation_id": second["invocation_id"]}, evidence_ids=[own_id])
            with self.assertRaises((ToolAccessError, ValueError)):
                tool.query(**{**identity, "invocation_id": "invented"}, evidence_ids=[own_id])
            with self.assertRaisesRegex(ToolAccessError, "RUN_DIRECTORY_OVERRIDE_REJECTED"):
                tool.query(**identity, run_dir=str(root), evidence_ids=[own_id])

            invocation = json.loads((run / first["invocation_ref"]).read_text())
            report = {
                "schema_version": "counter-thesis-report/2.1.0",
                "run_id": "counter-scope-run", "invocation_id": first["invocation_id"],
                "status": "LOW_CONFIDENCE", "agent": "runtime_skeptic",
                "mode": "INDEPENDENT_FIRST_PASS",
                "scope": f"{first['security_id']} 的独立反证",
                "challenges": [{
                    "challenge_id": "challenge-1", "statement": "现金流压力可能限制投资弹性。",
                    "evidence_refs": [own_id], "assumption_ids": ["future-cost"],
                    "resolution_evidence_needed": ["未来债务到期明细"],
                }],
                "assumptions": [{"assumption_id": "future-cost", "statement": "假设未来融资成本上行。"}],
                "evidence_refs": [own_id], "counter_evidence_refs": [],
                "uncertainties": ["融资路径尚不确定"], "data_gaps": ["缺债务明细"],
                "invalidation_conditions": ["融资成本下降"],
                "confidence": 0.35, "confidence_rationale": "仅有一项当前事实。",
                "skill_execution": invocation["skill_execution"], "artifact_refs": [],
            }
            captured = capture_skeptic_report(
                ROOT, run, task_name=first["task_name"],
                raw_message=json.dumps(report), model="gpt-5.6-terra",
            )
            self.assertEqual("SAVED", captured["status"])
            markdown = (run / captured["markdown_path"]).read_text()
            self.assertIn("现金流压力", markdown)
            self.assertIn("假设未来融资成本上行", markdown)
            self.assertIn(own_id, markdown)

            hook_env = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(run / "invocation/skeptic/subagent-events.jsonl"),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(run / "invocation/skeptic/subagent-dispatches.jsonl"),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_skeptic",
                "STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE": "independent-skeptic-runtime/1.0.0",
                "STOCK_AGENT_RESEARCH_TASK_NAME": first["task_name"],
            }
            dispatch_payload = {
                "hook_event_name": "PreToolUse", "session_id": "parent-1",
                "turn_id": "turn-1", "tool_name": "spawn_agent", "tool_use_id": "tool-1",
                "cwd": str(ROOT / "product"), "model": "gpt-5.6-terra",
                "permission_mode": "workspace-write",
                "tool_input": {
                    "agent_type": "runtime_skeptic", "task_name": first["task_name"],
                    "fork_turns": "none",
                    "message": "启动本次冻结的独立反证研究；完整上下文由 SubagentStart Hook 交付。",
                },
            }
            decision, _ = handle_hook_event(dispatch_payload, environ=hook_env)
            self.assertEqual("ALLOW", decision["decision"])
            start_payload = {
                "hook_event_name": "SubagentStart", "session_id": "parent-1",
                "turn_id": "turn-1", "agent_id": "child-1",
                "agent_type": "runtime_skeptic", "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"), "permission_mode": "read-only",
            }
            start, context = handle_hook_event(start_payload, environ=hook_env)
            self.assertEqual("DELIVERED", start["context_binding"]["status"])
            delivered = context["hookSpecificOutput"]["additionalContext"]
            self.assertIn(first["invocation_id"], delivered)
            self.assertNotIn("forward_bundle_hash", delivered)

            second_invocation = json.loads((run / second["invocation_ref"]).read_text())
            second_report = copy.deepcopy(report)
            second_report["invocation_id"] = second["invocation_id"]
            second_report["scope"] = f"{second['security_id']} 的独立反证"
            second_report["evidence_refs"] = [other_id]
            second_report["challenges"][0]["evidence_refs"] = [other_id]
            second_report["skill_execution"] = second_invocation["skill_execution"]
            second_env = {**hook_env, "STOCK_AGENT_RESEARCH_TASK_NAME": second["task_name"]}
            second_dispatch = copy.deepcopy(dispatch_payload)
            second_dispatch["session_id"] = "parent-2"
            second_dispatch["tool_input"]["task_name"] = second["task_name"]
            allowed_dispatch, _ = handle_hook_event(second_dispatch, environ=second_env)
            self.assertEqual("ALLOW", allowed_dispatch["decision"])
            second_start = {**start_payload, "session_id": "parent-2", "agent_id": "child-2"}
            handle_hook_event(second_start, environ=second_env)
            second_stop = {
                **second_start, "hook_event_name": "SubagentStop",
                "last_assistant_message": json.dumps(second_report),
                "stop_hook_active": False,
            }
            stopped, _ = handle_hook_event(second_stop, environ=second_env)
            self.assertEqual("SAVED", stopped["output_capture"]["status"])
            self.assertTrue((run / second["report_ref"]).is_file())

    def test_core_coverage_blocks_failed_core_but_allows_specialist_source_limit(self):
        core = [
            "COMPANY_RESEARCH", "TECHNICAL_STRUCTURE", "FUNDAMENTAL_EVENT",
            "INDUSTRY_COMPARISON", "MACRO_CONTEXT", "MARKET_STATE",
        ]
        bundle = {
            "consumability": "DOWNSTREAM_READY", "common_stock_security_ids": ["US:COMMON_STOCK:MRVL"],
            "coverage": [
                {"security_id": "US:COMMON_STOCK:MRVL", "capability": capability,
                 "status": "COMPLETE", "report_id": f"report:{capability}"}
                for capability in core
            ] + [{
                "security_id": "US:COMMON_STOCK:MRVL", "capability": "RESEARCH_REPORT",
                "status": "SOURCE_LIMITED", "report_id": "report:research",
            }],
        }
        validate_core_coverage(bundle)
        source_limited_core = copy.deepcopy(bundle)
        source_limited_core["coverage"][2]["status"] = "SOURCE_LIMITED"
        validate_core_coverage(source_limited_core)
        for status in ("FAILED", "TIMEOUT", "NOT_RESEARCHED"):
            broken = copy.deepcopy(bundle)
            broken["coverage"][2]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(
                IndependentSkepticStageError, "COUNTER_FORWARD_CORE_NOT_READY"
            ):
                validate_core_coverage(broken)
        missing = copy.deepcopy(bundle)
        missing["coverage"].pop(0)
        with self.assertRaisesRegex(IndependentSkepticStageError, "CORE_COVERAGE_INCOMPLETE"):
            validate_core_coverage(missing)

    def test_gate_scoping_keeps_target_shared_and_frozen_peer_not_other_holding(self):
        gate = {
            "allowed_evidence_ids": ["target", "other", "peer", "macro", "market"],
            "allowed_evidence": [
                {"evidence_id": "target", "security_id": "US:COMMON_STOCK:MRVL"},
                {"evidence_id": "other", "security_id": "US:COMMON_STOCK:MSFT"},
                {"evidence_id": "peer", "security_id": "US:COMMON_STOCK:NVDA"},
                {"evidence_id": "macro", "security_id": "US:MACRO"},
                {"evidence_id": "market", "security_id": "US:MARKET"},
            ],
        }
        self.assertEqual(
            ["macro", "market", "peer", "target"],
            scope_evidence_ids(
                gate, security_id="US:COMMON_STOCK:MRVL",
                shared_evidence_ids=["macro", "market", "other"],
                peer_security_ids=["US:COMMON_STOCK:NVDA"],
            ),
        )
        with self.assertRaisesRegex(IndependentSkepticStageError, "OUTSIDE_GATE"):
            scope_evidence_ids(gate, security_id="US:COMMON_STOCK:MRVL", shared_evidence_ids=["unknown"])

    def test_first_pass_is_exact_allowlist_not_recursive_denylist(self):
        request = {"request_id": "request-1", "research_question": "分析风险。", "holding_horizon": None}
        gate = {"decision_cutoff": "2026-09-01T00:00:00Z", "bundle_hash": "a" * 64}
        value = build_first_pass_input(
            run_id="run-1", security_id="US:COMMON_STOCK:MRVL", request=request,
            gate=gate, allowed_ids=["ev-1"],
        )
        self.assertNotIn("portfolio_summary", value)
        for key in ("bundle_hash", "unresolved_cross_dimension_questions", "artifact_refs", "analyst_summary"):
            broken = {**value, key: {"nested": "polluted"}}
            with self.subTest(key=key), self.assertRaisesRegex(
                IndependentSkepticStageError, "CONTEXT_ISOLATION_VIOLATION"
            ):
                validate_first_pass_input(broken, allowed_ids=["ev-1"])


if __name__ == "__main__":
    unittest.main()
