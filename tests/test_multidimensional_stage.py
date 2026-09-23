from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from product.runtime.codex_hook_recorder import handle_hook_event, _terminal_research_tasks
from product.runtime.fixture_mcp import StatelessFixtureTools
from product.council.multidimensional_research import envelope_research_dimension_draft
from product.runtime.multidimensional_stage import (
    DISPATCH_VERSION,
    STAGE_VERSION,
    _bounded_latest_facts,
    _facts_for_capability,
    _capability_routing_coverage,
    _dynamic_draft_schema,
    _adopt_multidimensional_retry,
    _parent_output_schema,
    build_multidimensional_dispatch_packet,
    build_multidimensional_stage_prompt,
    build_multidimensional_task_prompt,
    assemble_canonical_holding_research_package,
    check_multidimensional_bundle_consumable,
    finalize_multidimensional_task_evidence,
    finalize_multidimensional_stage_run,
    prepare_multidimensional_stage_run,
)
from product.runtime.multidimensional_stage import _frozen_peer_candidates
from product.runtime.common_stock_stage import prepare_common_stock_stage_run
from product.council.research_output import persist_equity_research_report
from product.council.multidimensional_output import persist_dimension_report
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.validation import ArtifactValidationError, validate_evidence_closure
from product.mcp.live.peer_candidates import build_peer_candidate_pool
from product.mcp.provenance import content_hash
from tests.test_common_stock_research_contracts import gate_for, stock_handoff, valid_report


ROOT = Path(__file__).resolve().parents[1]


class MultidimensionalStageTests(unittest.TestCase):
    def test_selected_but_unmaterialized_peers_still_forbid_comparison_claims(self) -> None:
        task = {
            "selected_peer_candidates": [{
                "candidate_id": "candidate-amd",
                "materialization_status": "NOT_MATERIALIZED",
                "materialized_security_id": None,
            }],
        }
        self.assertEqual([], _frozen_peer_candidates(task))
        task["selected_peer_candidates"].append({
            "candidate_id": "candidate-intc",
            "materialization_status": "FROZEN",
            "materialized_security_id": "US:COMMON_STOCK:INTC",
        })
        self.assertEqual(
            ["US:COMMON_STOCK:INTC"],
            [item["materialized_security_id"] for item in _frozen_peer_candidates(task)],
        )

    def test_evidence_closure_requires_exact_full_identifier(self) -> None:
        full_id = "ev-official-macro-f4c54045b82c4676c50556b5c53d6e024bb95adaa770be97e8b5c01b68902216"
        value = {"claims": [{"evidence_refs": [full_id]}]}
        self.assertEqual(
            {full_id}, validate_evidence_closure(value, allowed_evidence_ids=[full_id])
        )
        for invalid in (full_id[:-12], full_id.replace("c53d6e", "c01b68"), "ev-unknown"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                ArtifactValidationError, "EVIDENCE_CLOSURE_FAILED"
            ):
                validate_evidence_closure(
                    {"claims": [{"evidence_refs": [invalid]}]},
                    allowed_evidence_ids=[full_id],
                )

    def test_prepare_independent_stage_reuses_forward_plan_without_skeptic_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="counter-stage-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            manifest = json.loads((run / "run_manifest.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertEqual("INDEPENDENT_COUNTER_THESIS_RESEARCH", manifest["stage"])
            self.assertEqual(manifest["stage"], request["stage"])
            self.assertFalse(manifest["complete_portfolio_decision"])
            self.assertNotIn("runtime_skeptic", {task["agent"] for task in index["tasks"]})
            macro = next(task for task in index["tasks"] if task["capability"] == "MACRO_CONTEXT")
            packet = json.loads((run / macro["packet_path"]).read_text())
            self.assertIn("先通过非空 fixture_runtime.query 实际读取", packet["instruction"])
            self.assertIn("当前只有一只普通股持仓", packet["instruction"])
            self.assertIn("不得因缺少第二只持仓", packet["instruction"])
            self.assertEqual(
                packet["citation_contract"]["required_form"],
                "FULL_EVIDENCE_ID_FROM_TOOL_RESULT",
            )
            self.assertEqual(packet["citation_contract"]["aliases"], {})
            old_run = root / "old-run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=old_run, run_id="old-stage-run", model="gpt-5.6-terra",
            )
            old_index = json.loads((old_run / "research/dispatch-index.json").read_text())
            old_macro = next(task for task in old_index["tasks"] if task["capability"] == "MACRO_CONTEXT")
            old_packet = json.loads((old_run / old_macro["packet_path"]).read_text())
            self.assertNotIn("先通过非空 fixture_runtime.query 实际读取", old_packet["instruction"])

    def test_moomoo_datasets_route_to_existing_capabilities_without_new_domain(self):
        def fact(evidence_id, security_id, dataset, field):
            return {
                "evidence_id": evidence_id, "security_id": security_id,
                "dataset": dataset, "semantic_field": field,
                "source_family": "moomoo_sg", "source_type": "SECONDARY_VENDOR",
            }
        evidence = [
            fact("rating", "US:COMMON_STOCK:AAPL", "research_discovery", "moomoo_rating_item:x"),
            fact("owner", "US:COMMON_STOCK:AAPL", "institutional_ownership", "moomoo_institutional_aggregate:x"),
            fact("option", "US:COMMON_STOCK:AAPL", "options_snapshot", "moomoo_option_quote:x"),
            fact("macro", "US:MARKET", "macro_history", "moomoo_us_cpi_yoy:x"),
            fact("market", "US:MARKET", "fedwatch_expectations", "moomoo_fedwatch:x"),
        ]
        expected = {
            "RESEARCH_REPORT": {"rating"}, "OWNERSHIP_DISCLOSURE": {"owner"},
            "OPTIONS_FLOW": {"option"}, "MACRO_CONTEXT": {"macro"},
            "MARKET_STATE": {"market"},
        }
        for capability, ids in expected.items():
            selected = _facts_for_capability(
                evidence, capability=capability,
                security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
            )
            self.assertEqual(ids, {item["evidence_id"] for item in selected})

    def test_provider_neutral_routing_coverage_separates_delivery_from_actual_use(self):
        evidence = [{
            "evidence_id": "ev-option", "security_id": "US:COMMON_STOCK:AAPL",
            "dataset": "options_snapshot", "semantic_field": "moomoo_option_quote:x",
            "source_family": "moomoo_sg", "source_type": "SECONDARY_VENDOR",
        }]
        coverage = _capability_routing_coverage(
            evidence, capture_batches=[{"capabilities": [{
                "source": "moomoo_sg", "dataset": "options_snapshot",
                "evidence_ids": ["ev-option"],
            }]}], security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
        )
        option = next(
            item for item in coverage["dataset_observations"]
            if item["dataset"] == "options_snapshot"
        )
        self.assertEqual("CLOSED", coverage["status"])
        self.assertEqual(1, option["capture_evidence_count"])
        self.assertEqual(1, option["gate_eligible_evidence_count"])
        self.assertEqual(1, option["delivered_evidence_count"])
        self.assertEqual("NOT_EVALUATED_AT_PREPARATION", option["actual_research_use_status"])

        wrong_scope = [dict(evidence[0], security_id="US:COMMON_STOCK:MSFT")]
        failed = _capability_routing_coverage(
            wrong_scope, capture_batches=[],
            security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
        )
        self.assertEqual("FAILED", failed["status"])
        self.assertTrue(failed["failure_codes"][0].startswith(
            "CAPABILITY_EVIDENCE_NOT_ROUTED:OPTIONS_FLOW:"
        ))

    def test_provider_neutral_routing_counts_yahoo_primary_options(self):
        evidence = [{
            "evidence_id": "ev-yahoo-option", "security_id": "US:COMMON_STOCK:AAPL",
            "dataset": "options_snapshot", "semantic_field": "option_chain_contract:AAPL",
            "source_family": "yahoo", "source_type": "options",
        }]
        coverage = _capability_routing_coverage(
            evidence, capture_batches=[{"capabilities": [{
                "source": "yahoo", "dataset": "options_snapshot",
                "evidence_ids": ["ev-yahoo-option"],
            }]}], security_ids=["US:COMMON_STOCK:AAPL"], benchmark_id="US:SPY",
        )
        option = next(
            item for item in coverage["dataset_observations"]
            if item["dataset"] == "options_snapshot"
        )
        self.assertEqual("CLOSED", coverage["status"])
        self.assertEqual("DELIVERED", option["delivery_status"])
        self.assertEqual(1, option["capture_evidence_count"])
        self.assertEqual(1, option["gate_eligible_evidence_count"])
        self.assertEqual(1, option["delivered_evidence_count"])

    @staticmethod
    def dimension_draft(task: dict, *, include_impact: bool = True) -> dict:
        gap = {
            "gap_id": f"gap:{task['task_id']}",
            "reason_code": "UNKNOWN",
            "description": "测试资料不足。",
        }
        if include_impact:
            gap["impact"] = "不形成研究主张。"
        return {
            "run_id": task["run_id"],
            "invocation_id": task["invocation_id"],
            "agent": task["agent"],
            "status": "INSUFFICIENT_EVIDENCE",
            "sufficiency": "INSUFFICIENT",
            "evaluation_status": "NOT_EVALUATED",
            "summary": "测试报告明确保留资料缺口。",
            "claims": [],
            "assumptions": [],
            "calculations": [],
            "documents": [],
            "research_relationships": [],
            "limitations": ["测试资料不足。"],
            "observation_conditions": [],
            "data_gaps": [gap],
            "artifact_refs": [],
        }

    @staticmethod
    def targeted_environment(run: Path, task: dict) -> dict[str, str]:
        invocation_dir = run / "invocation"
        invocation_dir.mkdir(exist_ok=True)
        return {
            "STOCK_AGENT_RUN_DIR": str(run),
            "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(
                invocation_dir / "subagent-events.jsonl"
            ),
            "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(
                invocation_dir / "subagent-dispatches.jsonl"
            ),
            "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": task["agent"],
            "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
            "STOCK_AGENT_RESEARCH_TASK_NAME": task["task_name"],
        }

    @staticmethod
    def dispatch_payload(task: dict, *, parent: str) -> dict:
        return {
            "hook_event_name": "PreToolUse",
            "session_id": parent,
            "turn_id": f"turn:{parent}",
            "tool_name": "spawn_agent",
            "tool_use_id": f"tool:{parent}",
            "cwd": str(ROOT / "product"),
            "model": "gpt-5.6-terra",
            "permission_mode": "workspace-write",
            "tool_input": {
                "agent_type": task["agent"],
                "task_name": task["task_name"],
                "fork_turns": "none",
                "message": "启动冻结多维研究任务。",
            },
        }

    @staticmethod
    def stop_payload(task: dict, draft: dict, *, parent: str, child: str) -> dict:
        return {
            "hook_event_name": "SubagentStop",
            "session_id": parent,
            "turn_id": f"turn:{parent}",
            "agent_id": child,
            "agent_type": task["agent"],
            "model": "gpt-5.6-terra",
            "cwd": str(ROOT / "product"),
            "permission_mode": "read-only",
            "stop_hook_active": False,
            "last_assistant_message": json.dumps(draft),
        }

    @staticmethod
    def start_payload(task: dict, *, parent: str, child: str) -> dict:
        return {
            "hook_event_name": "SubagentStart",
            "session_id": parent,
            "turn_id": f"turn:{parent}",
            "agent_id": child,
            "agent_type": task["agent"],
            "model": "gpt-5.6-terra",
            "cwd": str(ROOT / "product"),
            "permission_mode": "read-only",
        }

    def complete_with_explicit_gaps(self, run: Path) -> None:
        invocation_dir = run / "invocation"
        invocation_dir.mkdir()
        index = json.loads((run / "research/dispatch-index.json").read_text())
        handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
        request = json.loads((run / "council-request.json").read_text())
        gate = json.loads((run / "evidence/gate.json").read_text())
        bindings = {
            "handoff_id": handoff["handoff_id"],
            "handoff_hash": handoff["handoff_hash"],
            "portfolio_hash": handoff["portfolio_hash"],
            "council_request_id": request["request_id"],
            "council_request_hash": request["request_hash"],
            "decision_cutoff": gate["decision_cutoff"],
        }
        events = []
        for task in index["tasks"]:
            invocation = json.loads((run / task["invocation_path"]).read_text())
            report = envelope_research_dimension_draft(
                {
                    "run_id": task["run_id"],
                    "invocation_id": task["invocation_id"],
                    "agent": task["agent"],
                    "status": "INSUFFICIENT_EVIDENCE",
                    "sufficiency": "INSUFFICIENT",
                    "evaluation_status": "NOT_EVALUATED",
                    "summary": "测试报告明确保留资料缺口。",
                    "claims": [], "assumptions": [], "calculations": [],
                    "documents": [], "research_relationships": [],
                    "limitations": ["测试不形成投资判断。"],
                    "observation_conditions": [],
                    "data_gaps": [{
                        "gap_id": f"gap:{task['task_id']}",
                        "reason_code": "UNKNOWN",
                        "description": "测试资料不足。",
                        "impact": "仅验证交接结构。",
                    }],
                    "artifact_refs": [],
                },
                task=task,
                invocation=invocation,
                expected_bindings=bindings,
                allowed_security_ids=[
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                    if item["asset_type"] == "COMMON_STOCK"
                ],
                allowed_evidence_ids=task["allowed_evidence_ids"],
                allowed_documents=task.get("allowed_documents", []),
            )
            output = persist_dimension_report(
                run / "research/reports" / task["task_id"],
                report=report,
                evidence=[],
            )
            events.append({
                "hook_event_name": "SubagentStop",
                "output_capture": {
                    "status": "SAVED", "task_id": task["task_id"],
                    "path": str(Path(output["json"]).relative_to(run)),
                },
            })
        (invocation_dir / "subagent-dispatches.jsonl").write_text(
            "\n".join(json.dumps({
                "task_name": task["task_name"], "decision": "ALLOW"
            }) for task in index["tasks"]) + "\n",
            encoding="utf-8",
        )
        (invocation_dir / "subagent-events.jsonl").write_text(
            "\n".join(json.dumps(item) for item in events) + "\n",
            encoding="utf-8",
        )
        finalize_multidimensional_stage_run(ROOT, run)

    def test_parent_and_dimension_structured_output_properties_have_types(self) -> None:
        def walk(value, path="$"):
            if isinstance(value, dict):
                for name, child in value.get("properties", {}).items():
                    self.assertTrue(
                        "type" in child or any(key in child for key in ("$ref", "anyOf", "oneOf", "allOf")),
                        f"{path}.properties.{name} 缺少显式类型",
                    )
                for name, child in value.items():
                    walk(child, f"{path}.{name}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]")
        walk(_parent_output_schema("run", 19))
        self.assertEqual(
            ["stage", "run_id", "dispatched", "completed"],
            _parent_output_schema("run", 19)["required"],
        )
        walk(_dynamic_draft_schema(
            ROOT, run_id="run", invocation_id="inv",
            agent="runtime_market_catalyst", allowed_evidence_ids=["ev-1"],
            allowed_artifact_refs=["artifact.json"], allowed_documents=[],
        ))

    def prepare(self, root: Path, count: int = 2):
        handoff = stock_handoff(count)
        gate = gate_for(handoff)
        handoff_path, gate_path = root / "handoff.json", root / "gate.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        gate_path.write_text(json.dumps(gate), encoding="utf-8")
        run = root / "run"
        result = prepare_multidimensional_stage_run(
            ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
            run_id="multi-stage-run", model="gpt-5.6-terra",
        )
        return run, result

    def test_prepare_creates_explicit_all_holding_dimension_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, result = self.prepare(Path(temp))
            self.assertEqual(result["status"], "PREPARED")
            manifest = json.loads((run / "run_manifest.json").read_text())
            self.assertEqual(manifest["schema_version"], STAGE_VERSION)
            self.assertEqual(manifest["stage"], "MULTI_DIMENSIONAL_HOLDING_RESEARCH")
            self.assertFalse(manifest["complete_portfolio_decision"])
            self.assertEqual(manifest["downstream_stages_started"], [])
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertEqual(index["schema_version"], DISPATCH_VERSION)
            self.assertEqual(len(index["tasks"]), 14)  # 六个逐股维度 + Macro/Market 两项共享研究
            self.assertEqual(
                {item["agent"] for item in index["tasks"]},
                {"runtime_company_analyst", "runtime_market_catalyst"},
            )
            macro = [item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT"]
            market = [item for item in index["tasks"] if item["capability"] == "MARKET_STATE"]
            self.assertEqual(len(macro), 1)
            self.assertEqual(len(market), 1)
            self.assertEqual(
                macro[0]["security_ids"],
                ["US:COMMON_STOCK:AAPL", "US:COMMON_STOCK:MSFT"],
            )
            self.assertEqual(macro[0]["depends_on"], [])
            self.assertEqual(market[0]["depends_on"], [])
            self.assertEqual(
                manifest["research_input_topology"]["domains"]["MACRO"],
                ["MACRO_CONTEXT"],
            )
            self.assertEqual(macro[0]["agent"], market[0]["agent"])
            macro_packet = json.loads((run / macro[0]["packet_path"]).read_text())
            market_packet = json.loads((run / market[0]["packet_path"]).read_text())
            self.assertIn("当前有多只普通股持仓", macro_packet["instruction"])
            self.assertIn("当前有多只普通股持仓", market_packet["instruction"])
            self.assertNotIn("当前只有一只普通股持仓", macro_packet["instruction"])
            task = index["tasks"][0]
            packet = json.loads((run / task["packet_path"]).read_text())
            invocation = json.loads((run / task["invocation_path"]).read_text())
            self.assertEqual(packet["output_schema"]["$id"], "research-dimension-draft/2.0.0")
            self.assertEqual(packet["output_schema_hash"], canonical_hash(packet["output_schema"]))
            self.assertEqual(
                invocation["output_contract"]["draft_schema_hash"],
                packet["output_schema_hash"],
            )
            self.assertEqual(
                invocation["output_contract"]["sha256"],
                manifest["research_input_topology"]["default_output_contract"]["sha256"],
            )

    def test_company_report_routes_issuer_body_guidance_and_expectations_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            security_id = handoff["portfolio"]["positions"][0]["security_id"]
            issuer = {
                "evidence_id": "ev-issuer-body", "security_id": security_id,
                "semantic_field": "earnings_release", "value": (
                    "Issuer earnings release discussion provides a verified operating update. " * 30
                ),
                "source_id": "sec-filing:test", "source_type": "sec",
                "source_locator": "https://www.sec.gov/Archives/example.htm",
                "as_of": "2026-09-10T20:00:00Z", "published_at": "2026-09-10T20:00:00Z",
                "retrieved_at": "2026-09-11T11:00:00Z", "raw_content_hash": "a" * 64,
                "section": "earnings_release", "metadata": {"description": "Issuer earnings release"},
            }
            issuer_toc = {
                **issuer, "evidence_id": "ev-issuer-toc",
                "value": "Item 2. Management Discussion and Analysis 28",
                "semantic_field": "management_discussion",
            }
            guidance = {
                **issuer, "evidence_id": "ev-guidance", "semantic_field": "sec_issuer_guidance_candidate_text",
                "source_id": "sec-guidance:test", "source_family": "sec",
            }
            expectation = {
                **issuer, "evidence_id": "ev-expectation", "semantic_field": "yahoo_earnings_trend",
                "source_id": "yahoo-quote-summary:AAPL", "source_type": "yahoo",
                "source_family": "yahoo",
            }
            gate["allowed_evidence"].extend([issuer, issuer_toc, guidance, expectation])
            gate["allowed_evidence_ids"] = sorted(
                item["evidence_id"] for item in gate["allowed_evidence"]
            )
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                run_id="issuer-material-routing", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, task["task_name"], include_dependency_reports=False
            )
            self.assertEqual(packet["company_material_coverage"]["issuer_body_count"], 1)
            self.assertEqual(packet["company_material_coverage"]["guidance_evidence_ids"], ["ev-guidance"])
            self.assertEqual(packet["company_material_coverage"]["expectation_evidence_ids"], ["ev-expectation"])
            self.assertEqual(packet["task"]["allowed_documents"][0]["material_type"], "ISSUER_MATERIAL")
            self.assertNotEqual(
                packet["task"]["allowed_documents"][0]["body_hash"],
                issuer["raw_content_hash"],
            )
            self.assertEqual(
                packet["task"]["allowed_documents"][0]["body_hash"],
                packet["verified_documents"][0]["content"]["body_hash"],
            )
            self.assertEqual(
                packet["verified_documents"][0]["content"]["evidence_id"],
                "ev-issuer-body",
            )
            self.assertEqual(
                packet["task"]["allowed_documents"][0]["retrieved_at"],
                issuer["retrieved_at"],
            )
            self.assertEqual(
                packet["task"]["allowed_documents"][0]["interest_disclosure"]["status"],
                "DECLARED",
            )
            self.assertIn("不得省略问题字段", packet["instruction"])
            self.assertIn("limitations 必须是纯字符串数组", packet["instruction"])
            self.assertIn("gap_id、reason_code、description、impact", packet["instruction"])
            self.assertEqual(packet["verified_documents"][0]["content"]["classification"], "ISSUER_IR_OR_ANNOUNCEMENT_BODY")
            self.assertIn("ev-guidance", packet["allowed_evidence_ids"])
            self.assertIn("ev-expectation", packet["allowed_evidence_ids"])
            macro = [item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT"]
            market = [item for item in index["tasks"] if item["capability"] == "MARKET_STATE"]
            self.assertEqual(macro[0]["skill_name"], market[0]["skill_name"])
            self.assertNotEqual(macro[0]["invocation_id"], market[0]["invocation_id"])
            macro_packet = json.loads((run / macro[0]["packet_path"]).read_text())
            market_packet = json.loads((run / market[0]["packet_path"]).read_text())
            self.assertNotEqual(
                macro_packet["minimum_questions"], market_packet["minimum_questions"]
            )
            self.assertEqual(
                macro_packet["research_input_topology"],
                market_packet["research_input_topology"],
            )
            macro_invocation = json.loads((run / macro[0]["invocation_path"]).read_text())
            self.assertEqual(
                macro_invocation["research_input_topology"],
                macro_packet["research_input_topology"],
            )
            industry = [
                item for item in index["tasks"]
                if item["capability"] == "INDUSTRY_COMPARISON"
            ]
            self.assertTrue(all(item["depends_on"] == [] for item in industry))
            self.assertTrue(all(item["model"] == "gpt-5.6-terra" for item in [
                json.loads((run / task["invocation_path"]).read_text()) for task in index["tasks"]
            ]))

    def test_dispatch_packet_has_dynamic_evidence_ids_and_no_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            fundamental = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            packet = build_multidimensional_dispatch_packet(ROOT, run, fundamental["task_name"])
            self.assertTrue(packet["allowed_evidence_ids"])
            self.assertEqual(
                packet["output_schema"]["$defs"]["evidence_id"]["enum"],
                packet["allowed_evidence_ids"],
            )
            self.assertNotIn("action", packet["output_schema"]["properties"])
            prompt = build_multidimensional_stage_prompt(ROOT, run)
            self.assertIn("runtime_company_analyst", prompt)
            self.assertIn("runtime_market_catalyst", prompt)
            self.assertIn("不得启动 runtime_skeptic", prompt)

    def test_targeted_prompt_dispatches_only_one_independent_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            macro = next(item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT")
            prompt = build_multidimensional_task_prompt(ROOT, run, macro["task_name"])
            self.assertIn(f"task_name={macro['task_name']}", prompt)
            self.assertIn("只派发一次", prompt)
            other_names = {
                item["task_name"] for item in index["tasks"] if item is not macro
            }
            self.assertTrue(all(name not in prompt for name in other_names))
            dependent = next(item for item in index["tasks"] if item["depends_on"])
            dependency = next(
                item for item in index["tasks"]
                if item["task_id"] == dependent["depends_on"][0]
            )
            chain_prompt = build_multidimensional_task_prompt(
                ROOT, run, dependent["task_name"]
            )
            self.assertIn(dependent["task_name"], chain_prompt)
            self.assertIn(dependency["task_name"], chain_prompt)
            self.assertIn("最小依赖闭包", chain_prompt)
            self.assertNotIn("跨批次复制或注入报告", prompt)
            self.assertIn("不得跨批次复制或注入报告", chain_prompt)

    def test_targeted_hook_scopes_dispatch_and_stop_barrier_to_one_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            target = next(
                item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT"
            )
            other = next(item for item in index["tasks"] if item is not target)
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(
                    invocation_dir / "subagent-events.jsonl"
                ),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(
                    invocation_dir / "subagent-dispatches.jsonl"
                ),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": target["agent"],
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
                "STOCK_AGENT_RESEARCH_TASK_NAME": target["task_name"],
            }

            def pre(task, tool_id):
                return {
                    "hook_event_name": "PreToolUse",
                    "session_id": "parent-targeted",
                    "turn_id": "turn-targeted",
                    "tool_name": "spawn_agent",
                    "tool_use_id": tool_id,
                    "cwd": str(ROOT / "product"),
                    "model": "gpt-5.6-terra",
                    "permission_mode": "workspace-write",
                    "tool_input": {
                        "agent_type": task["agent"],
                        "task_name": task["task_name"],
                        "fork_turns": "none",
                        "message": "启动冻结多维研究任务。",
                    },
                }

            denied, _ = handle_hook_event(pre(other, "wrong-task"), environ=environment)
            self.assertEqual(denied["decision"], "DENY_DISPATCH_CONTRACT")
            allowed, _ = handle_hook_event(pre(target, "target-task"), environ=environment)
            self.assertEqual(allowed["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(
                    target, parent="parent-targeted", child="child-targeted"
                ),
                environ=environment,
            )

            stop = {
                "hook_event_name": "SubagentStop",
                "session_id": "parent-targeted",
                "turn_id": "turn-targeted",
                "agent_id": "child-targeted",
                "agent_type": target["agent"],
                "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"),
                "permission_mode": "read-only",
                "stop_hook_active": False,
                "last_assistant_message": json.dumps({
                    "run_id": target["run_id"],
                    "invocation_id": target["invocation_id"],
                    "agent": target["agent"],
                    "status": "INSUFFICIENT_EVIDENCE",
                    "sufficiency": "INSUFFICIENT",
                    "evaluation_status": "NOT_EVALUATED",
                    "summary": "定点 Hook 屏障测试。",
                    "claims": [],
                    "assumptions": [],
                    "calculations": [],
                    "documents": [],
                    "research_relationships": [],
                    "limitations": ["测试资料不足。"],
                    "observation_conditions": [],
                    "data_gaps": [{
                        "gap_id": "gap-targeted-hook",
                        "reason_code": "UNKNOWN",
                        "description": "测试资料不足。",
                        "impact": "不形成宏观主张。",
                    }],
                    "artifact_refs": [],
                }),
            }
            stopped, response = handle_hook_event(stop, environ=environment)
            self.assertEqual(stopped["hook_event_name"], "SubagentStop")
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")
            self.assertEqual(stopped["output_capture"]["task_id"], target["task_id"])
            self.assertEqual(response, {})

    def test_structural_failure_blocks_once_then_original_agent_repair_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            parent, child = "parent-repair", "child-repair"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(task, parent=parent), environ=environment
            )
            self.assertEqual(allowed["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(task, parent=parent, child=child),
                environ=environment,
            )

            first, response = handle_hook_event(
                self.stop_payload(
                    task,
                    self.dimension_draft(task, include_impact=False),
                    parent=parent,
                    child=child,
                ),
                environ=environment,
            )
            self.assertEqual(first["hook_event_name"], "SubagentStopBlocked")
            self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED")
            self.assertEqual(response["decision"], "block")
            repair = json.loads(response["reason"])
            self.assertIn("$.data_gaps[0]:impact", repair["validation_error"])
            self.assertEqual(
                repair["output_schema_hash"], canonical_hash(repair["output_schema"])
            )
            self.assertNotIn("impact", repair["original_draft"]["data_gaps"][0])
            self.assertTrue((run / first["output_capture"]["raw_path"]).is_file())
            self.assertNotIn(
                task["task_name"],
                _terminal_research_tasks(
                    Path(environment["STOCK_AGENT_SUBAGENT_EVENT_LOG"]),
                    parent_session_id=parent,
                    environment=environment,
                ),
            )
            redispatch = self.dispatch_payload(task, parent=parent)
            redispatch["tool_use_id"] = "tool:repair-redispatch"
            redispatch_record, _ = handle_hook_event(
                redispatch, environ=environment
            )
            self.assertEqual(
                redispatch_record["decision"], "DENY_DUPLICATE_AGENT"
            )

            second, response = handle_hook_event(
                self.stop_payload(
                    task,
                    self.dimension_draft(task, include_impact=True),
                    parent=parent,
                    child=child,
                ),
                environ=environment,
            )
            self.assertEqual(second["hook_event_name"], "SubagentStop")
            self.assertEqual(second["output_capture"]["status"], "SAVED")
            self.assertEqual(second["output_capture"]["attempt"], 2)
            self.assertEqual(second["output_capture"]["repair_state"], "REPAIRED")
            self.assertEqual(response, {})
            self.assertIn(
                task["task_name"],
                _terminal_research_tasks(
                    Path(environment["STOCK_AGENT_SUBAGENT_EVENT_LOG"]),
                    parent_session_id=parent,
                    environment=environment,
                ),
            )
            self.assertTrue((run / second["output_capture"]["raw_path"]).is_file())
            self.assertNotEqual(
                first["output_capture"]["raw_path"],
                second["output_capture"]["raw_path"],
            )

    def test_trusted_start_envelopes_missing_identity_without_changing_raw_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "MARKET_STATE")
            environment = self.targeted_environment(run, task)
            parent, child = "parent-missing-identity", "child-missing-identity"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(task, parent=parent), environ=environment
            )
            self.assertEqual("ALLOW", allowed["decision"])
            handle_hook_event(
                self.start_payload(task, parent=parent, child=child),
                environ=environment,
            )
            raw = self.dimension_draft(task)
            for key in ("run_id", "invocation_id", "agent"):
                raw.pop(key)
            stopped, response = handle_hook_event(
                self.stop_payload(task, raw, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual("SAVED", stopped["output_capture"]["status"])
            self.assertEqual(
                ["agent", "invocation_id", "run_id"],
                sorted(stopped["identity_binding"]["filled_fields"]),
            )
            self.assertEqual(task["invocation_id"], stopped["output_binding"]["invocation_id"])
            self.assertEqual({}, response)
            persisted_raw = json.loads(
                (run / stopped["output_capture"]["raw_path"]).read_text()
            )
            self.assertNotIn("run_id", persisted_raw)
            self.assertNotIn("invocation_id", persisted_raw)
            self.assertNotIn("agent", persisted_raw)

    def test_targeted_company_dependency_chain_is_scoped_and_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            target = next(
                item for item in index["tasks"]
                if item["capability"] == "RESEARCH_REPORT"
            )
            dependency = next(
                item for item in index["tasks"]
                if item["task_id"] == target["depends_on"][0]
            )
            outside = next(
                item for item in index["tasks"]
                if item["task_id"] not in {dependency["task_id"], target["task_id"]}
            )
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(
                    invocation_dir / "subagent-events.jsonl"
                ),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(
                    invocation_dir / "subagent-dispatches.jsonl"
                ),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": target["agent"],
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
                "STOCK_AGENT_RESEARCH_TASK_NAMES": json.dumps(
                    [dependency["task_name"], target["task_name"]]
                ),
            }
            parent = "parent-company-chain"

            outside_record, _ = handle_hook_event(
                self.dispatch_payload(outside, parent=parent), environ=environment
            )
            self.assertEqual(outside_record["decision"], "DENY_UNAPPROVED_AGENT")
            early_record, _ = handle_hook_event(
                self.dispatch_payload(target, parent=parent), environ=environment
            )
            self.assertEqual(early_record["decision"], "DENY_DISPATCH_CONTRACT")
            self.assertEqual(
                early_record["dispatch_binding"]["failure_code"],
                "RESEARCH_DEPENDENCY_NOT_READY",
            )

            dependency_record, _ = handle_hook_event(
                self.dispatch_payload(dependency, parent=parent), environ=environment
            )
            self.assertEqual(dependency_record["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(
                    dependency, parent=parent, child="child-company-foundation"
                ),
                environ=environment,
            )
            stopped, _ = handle_hook_event(
                self.stop_payload(
                    dependency, self.dimension_draft(dependency),
                    parent=parent, child="child-company-foundation",
                ),
                environ=environment,
            )
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")

            target_record, _ = handle_hook_event(
                self.dispatch_payload(target, parent=parent), environ=environment
            )
            self.assertEqual(target_record["decision"], "ALLOW")
            handle_hook_event(
                self.start_payload(
                    target, parent=parent, child="child-company-report"
                ),
                environ=environment,
            )
            stopped, _ = handle_hook_event(
                self.stop_payload(
                    target, self.dimension_draft(target),
                    parent=parent, child="child-company-report",
                ),
                environ=environment,
            )
            self.assertEqual(stopped["output_capture"]["status"], "SAVED")

            proof = finalize_multidimensional_task_evidence(
                ROOT, run, target["task_name"]
            )
            self.assertEqual(proof["status"], "PASSED")
            self.assertEqual(proof["scope"], "DEPENDENCY_CHAIN_EVIDENCE")
            self.assertEqual(
                proof["task_names"],
                [dependency["task_name"], target["task_name"]],
            )
            self.assertEqual(len(proof["report_inventory"]), 2)
            self.assertTrue(proof["dependency_chain_complete"])

    def test_repair_budget_exhausts_and_identity_failure_is_not_repairable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            parent, child = "parent-exhausted", "child-exhausted"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(
                self.start_payload(task, parent=parent, child=child),
                environ=environment,
            )
            invalid = self.dimension_draft(task, include_impact=False)
            first, first_response = handle_hook_event(
                self.stop_payload(task, invalid, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual(first_response["decision"], "block")
            second, second_response = handle_hook_event(
                self.stop_payload(task, invalid, parent=parent, child=child),
                environ=environment,
            )
            self.assertEqual(second["hook_event_name"], "SubagentStop")
            self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
            self.assertEqual(second["output_capture"]["attempt"], 2)
            self.assertEqual(second_response, {})

        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            environment = self.targeted_environment(run, task)
            parent = "parent-binding"
            handle_hook_event(self.dispatch_payload(task, parent=parent), environ=environment)
            handle_hook_event(
                self.start_payload(
                    task, parent=parent, child="child-binding"
                ),
                environ=environment,
            )
            wrong_identity = self.dimension_draft(task)
            wrong_identity["agent"] = "runtime_market_catalyst"
            stopped, response = handle_hook_event(
                self.stop_payload(
                    task, wrong_identity, parent=parent, child="child-binding"
                ),
                environ=environment,
            )
            self.assertEqual(stopped["hook_event_name"], "SubagentStop")
            self.assertEqual(stopped["output_capture"]["repair_state"], "NOT_ALLOWED")
            self.assertIn(
                "RESEARCH_OUTPUT_IDENTITY_CONFLICT",
                stopped["output_capture"]["failure_code"],
            )
            self.assertEqual(response, {})

    def test_targeted_finalizer_proves_only_requested_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "MACRO_CONTEXT")
            invocation = json.loads((run / task["invocation_path"]).read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            report = envelope_research_dimension_draft(
                {
                    "run_id": task["run_id"],
                    "invocation_id": task["invocation_id"],
                    "agent": task["agent"],
                    "status": "INSUFFICIENT_EVIDENCE",
                    "sufficiency": "INSUFFICIENT",
                    "evaluation_status": "NOT_EVALUATED",
                    "summary": "定点执行证明测试。",
                    "claims": [], "assumptions": [], "calculations": [],
                    "documents": [], "research_relationships": [],
                    "limitations": ["测试资料不足。"],
                    "observation_conditions": [],
                    "data_gaps": [{
                        "gap_id": "gap-targeted",
                        "reason_code": "UNKNOWN",
                        "description": "测试资料不足。",
                        "impact": "不形成宏观主张。",
                    }],
                    "artifact_refs": [],
                },
                task=task,
                invocation=invocation,
                expected_bindings={
                    "handoff_id": handoff["handoff_id"],
                    "handoff_hash": handoff["handoff_hash"],
                    "portfolio_hash": handoff["portfolio_hash"],
                    "council_request_id": request["request_id"],
                    "council_request_hash": request["request_hash"],
                    "decision_cutoff": gate["decision_cutoff"],
                },
                allowed_security_ids=[
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                ],
                allowed_evidence_ids=task["allowed_evidence_ids"],
            )
            output = persist_dimension_report(
                run / "research/reports/targeted", report=report, evidence=[]
            )
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            (invocation_dir / "subagent-dispatches.jsonl").write_text(
                json.dumps({"task_name": task["task_name"], "decision": "ALLOW"}) + "\n",
                encoding="utf-8",
            )
            (invocation_dir / "subagent-events.jsonl").write_text(
                json.dumps({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED",
                        "task_id": task["task_id"],
                        "path": str(Path(output["json"]).relative_to(run)),
                    },
                }) + "\n",
                encoding="utf-8",
            )
            proof = finalize_multidimensional_task_evidence(
                ROOT, run, task["task_name"]
            )
            self.assertEqual(proof["status"], "PASSED")
            self.assertEqual(proof["scope"], "SINGLE_TASK_EVIDENCE")
            self.assertFalse(proof["complete_holding_research_bundle"])
            self.assertTrue((run / "research/task-execution-proof.json").is_file())

    def test_successful_targeted_retry_archives_bundle_and_records_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            self.complete_with_explicit_gaps(run)
            old_bundle_hash = file_hash(run / "research/holding-research-bundle.json")
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(
                item for item in index["tasks"]
                if item["capability"] == "INDUSTRY_COMPARISON"
            )
            invocation = json.loads((run / task["invocation_path"]).read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            report = envelope_research_dimension_draft(
                self.dimension_draft(task), task=task, invocation=invocation,
                expected_bindings={
                    "handoff_id": handoff["handoff_id"],
                    "handoff_hash": handoff["handoff_hash"],
                    "portfolio_hash": handoff["portfolio_hash"],
                    "council_request_id": request["request_id"],
                    "council_request_hash": request["request_hash"],
                    "decision_cutoff": gate["decision_cutoff"],
                },
                allowed_security_ids=[
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                    if item["asset_type"] == "COMMON_STOCK"
                ],
                allowed_evidence_ids=task["allowed_evidence_ids"],
                allowed_documents=task.get("allowed_documents", []),
            )
            retry_output = persist_dimension_report(
                run / "research/reports/retry-industry", report=report, evidence=[],
            )
            retry_dir = run / "invocation/retries/retry-industry/attempt-1"
            retry_dir.mkdir(parents=True)
            (retry_dir / "subagent-dispatches.jsonl").write_text(
                json.dumps({"task_name": task["task_name"], "decision": "ALLOW"}) + "\n",
                encoding="utf-8",
            )
            (retry_dir / "subagent-events.jsonl").write_text(
                json.dumps({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED", "task_id": task["task_id"],
                        "path": str(Path(retry_output["json"]).relative_to(run)),
                    },
                }) + "\n",
                encoding="utf-8",
            )
            finalize_multidimensional_task_evidence(
                ROOT, run, task["task_name"], invocation_dir=retry_dir,
            )
            result = _adopt_multidimensional_retry(
                ROOT, run, invocation_dir=retry_dir,
            )
            self.assertEqual("PASSED", result["status"])
            self.assertEqual(
                old_bundle_hash,
                file_hash(run / "research/revisions/1/holding-research-bundle.json"),
            )
            adoption = json.loads(
                (run / "research/retry-adoptions.jsonl").read_text().strip()
            )
            self.assertEqual(task["task_name"], adoption["task_name"])
            self.assertEqual(
                str(retry_dir.relative_to(run)), adoption["invocation_ref"]
            )

    def test_macro_packet_includes_scoped_company_context_without_report_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            for security_id in ("US:COMMON_STOCK:AAPL", "US:COMMON_STOCK:MSFT"):
                evidence_id = f"ev-business-{security_id.rsplit(':', 1)[-1].lower()}"
                gate["allowed_evidence"].append({
                    "evidence_id": evidence_id,
                    "security_id": security_id,
                    "semantic_field": "business",
                    "value": "可核对的公司业务暴露。",
                    "unit": "text",
                    "source_id": "sec-companyfacts",
                    "source_type": "sec",
                    "as_of": "2026-09-10T00:00:00Z",
                    "published_at": "2026-09-10T00:00:00Z",
                    "retrieved_at": "2026-09-11T00:00:00Z",
                })
                gate["allowed_evidence_ids"].append(evidence_id)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="macro-company-context", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            macro = next(
                item for item in index["tasks"]
                if item["capability"] == "MACRO_CONTEXT"
            )
            self.assertEqual(macro["depends_on"], [])
            self.assertTrue(
                {"ev-business-aapl", "ev-business-msft"}
                <= set(macro["allowed_evidence_ids"])
            )
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, macro["task_name"]
            )
            self.assertIn("必须读取至少两只持仓", packet["instruction"])

    def test_macro_packet_includes_deterministic_benchmark_market_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            for index in range(21):
                day = f"2026-08-{index + 1:02d}"
                for field, value in (
                    ("historical_close_price", 500 + index),
                    ("adjusted_close_price", 500 + index),
                    ("share_volume", 1_000_000 + index * 1_000),
                ):
                    evidence_id = f"ev-spy-{field}-{index}"
                    gate["allowed_evidence"].append({
                        "evidence_id": evidence_id,
                        "security_id": "US:SPY",
                        "semantic_field": field,
                        "value": value,
                        "unit": "USD" if field != "share_volume" else "shares",
                        "source_id": "yahoo-daily",
                        "source_type": "yahoo",
                        "as_of": f"{day}T20:00:00Z",
                        "published_at": f"{day}T20:00:00Z",
                        "retrieved_at": "2026-09-11T00:00:00Z",
                        "metadata": {"trading_date": day},
                    })
                    gate["allowed_evidence_ids"].append(evidence_id)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="macro-market-state", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            market = next(item for item in index["tasks"] if item["capability"] == "MARKET_STATE")
            packet = build_multidimensional_dispatch_packet(ROOT, run, market["task_name"])
            prepared = packet["prepared_analysis"]
            self.assertEqual(
                prepared["calculation"]["schema_version"],
                "market-state-calculation/1.0.0",
            )
            self.assertEqual(
                prepared["calculation"]["windows"][0]["status"], "COMPLETE"
            )
            self.assertEqual(
                packet["allowed_artifact_refs"], [prepared["calculation_ref"]]
            )
            self.assertIn("共享市场状态报告", packet["instruction"])
            self.assertIn("不得把股票波动称为信用", packet["instruction"])

    def test_peer_candidate_pool_is_bound_but_not_promoted_to_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            holdings = [
                {"security_id": item["security_id"], "ticker": item["display_symbol"]}
                for item in handoff["portfolio"]["positions"]
                if item["asset_type"] == "COMMON_STOCK"
            ]
            observed = "2026-09-11T11:00:00Z"
            rows = []
            for symbol, name, cap in (
                (holdings[0]["ticker"], "Holding One", "100"),
                (holdings[1]["ticker"], "Holding Two", "200"),
                ("PEER1", "Peer One", "120"),
            ):
                rows.append({
                    "symbol": symbol, "name": name, "market_cap": cap,
                    "country": "United States", "ipo_year": 2000,
                    "sector": "Technology", "industry": "Synthetic Industry",
                    "source_id": "nasdaq-screener", "as_of": observed,
                    "retrieved_at": observed, "raw_content_hash": "a" * 64,
                })
            universe = {
                "schema_version": "live-universe/1.0.0", "provider": "nasdaq",
                "source_id": "nasdaq-screener",
                "source_locator": "https://api.nasdaq.com/api/screener/stocks",
                "request_started_at": "2026-09-11T10:59:00Z",
                "as_of": observed, "retrieved_at": observed,
                "completeness": "COMPLETE", "rows": rows,
                "snapshot_hash": content_hash({"rows": rows, "as_of": observed}),
            }
            pool = build_peer_candidate_pool(holdings, universe=universe)
            handoff_path, gate_path, pool_path = root / "handoff.json", root / "gate.json", root / "peers.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            pool_path.write_text(json.dumps(pool), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                run_id="peer-pool-stage-run", model="gpt-5.6-terra",
                peer_candidate_pool_path=pool_path,
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            industry = next(item for item in index["tasks"] if item["capability"] == "INDUSTRY_COMPARISON")
            packet = build_multidimensional_dispatch_packet(ROOT, run, industry["task_name"], include_dependency_reports=False)
            self.assertEqual(packet["peer_candidate_group"]["security_id"], industry["security_ids"][0])
            self.assertTrue(packet["peer_candidate_group"]["candidates"])
            self.assertFalse(
                set(item["candidate_id"] for item in packet["peer_candidate_group"]["candidates"])
                & set(packet["allowed_evidence_ids"])
            )
            self.assertIn("未核实候选池", packet["instruction"])
            self.assertIn("claims 必须为空", packet["instruction"])
            self.assertEqual(packet["output_schema"]["properties"]["claims"]["maxItems"], 0)

    def test_prepare_revalidates_and_freezes_existing_company_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff, "company-source-run")
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            source = root / "company-run"
            prepare_common_stock_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=source, run_id="company-source-run", model="gpt-5.6-terra",
            )
            source_gate = json.loads((source / "evidence/gate.json").read_text())
            index = json.loads((source / "research/dispatch-index.json").read_text())
            for task in index["tasks"]:
                request = json.loads((source / task["request_path"]).read_text())
                report = valid_report(request)
                report["report_id"] = f"equity:{task['security_id']}"
                evidence_by_id = {
                    item["evidence_id"]: item for item in source_gate["allowed_evidence"]
                }
                persist_equity_research_report(
                    source / "research/reports", report=report, request=request,
                    evidence=[evidence_by_id[item] for item in request["allowed_evidence_ids"]],
                )
            proof = {
                "schema_version": "common-stock-research-execution-proof/1.0.0",
                "run_id": "company-source-run",
                "expected_tasks": sorted(item["task_name"] for item in index["tasks"]),
                "completed_security_ids": sorted(item["security_id"] for item in index["tasks"]),
                "intervals": [], "parallel_overlap": False, "all_reports_valid": True,
                "agent": {}, "skills": [], "gate_hash": source_gate["bundle_hash"],
                "complete_portfolio_decision": False,
            }
            proof["proof_hash"] = canonical_hash(proof)
            (source / "research/execution-proof.json").write_text(
                json.dumps(proof), encoding="utf-8"
            )
            target = root / "multidimensional-run"
            gate_path.write_text(
                json.dumps(gate_for(handoff, "multidimensional-import-run")),
                encoding="utf-8",
            )
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=target, run_id="multidimensional-import-run",
                model="gpt-5.6-terra", company_research_run_path=source,
            )
            imported = json.loads(
                (target / "research/imported-company-research/import-manifest.json").read_text()
            )
            self.assertEqual(len(imported["reports"]), 2)
            self.assertEqual(
                {item["security_id"] for item in imported["reports"]},
                {item["security_id"] for item in index["tasks"]},
            )
            self.assertTrue(all((target / item["artifact_ref"]).is_file() for item in imported["reports"]))
            manifest = json.loads((target / "run_manifest.json").read_text())
            self.assertEqual(manifest["company_research_import_hash"], imported["import_hash"])

    def test_canonical_assembly_imports_company_reports_and_excludes_drifted_supplement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff, "company-source-run")
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")

            company = root / "company-run"
            prepare_common_stock_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=company, run_id="company-source-run", model="gpt-5.6-terra",
            )
            company_gate = json.loads((company / "evidence/gate.json").read_text())
            company_index = json.loads((company / "research/dispatch-index.json").read_text())
            for task in company_index["tasks"]:
                request = json.loads((company / task["request_path"]).read_text())
                report = valid_report(request)
                report["report_id"] = f"equity:{task['security_id']}"
                evidence_by_id = {
                    item["evidence_id"]: item for item in company_gate["allowed_evidence"]
                }
                persist_equity_research_report(
                    company / "research/reports", report=report, request=request,
                    evidence=[evidence_by_id[item] for item in request["allowed_evidence_ids"]],
                )
            company_proof = {
                "schema_version": "common-stock-research-execution-proof/1.0.0",
                "run_id": "company-source-run",
                "expected_tasks": sorted(item["task_name"] for item in company_index["tasks"]),
                "completed_security_ids": sorted(item["security_id"] for item in company_index["tasks"]),
                "intervals": [], "parallel_overlap": False, "all_reports_valid": True,
                "agent": {}, "skills": [], "gate_hash": company_gate["bundle_hash"],
                "complete_portfolio_decision": False,
            }
            company_proof["proof_hash"] = canonical_hash(company_proof)
            (company / "research/execution-proof.json").write_text(json.dumps(company_proof))

            base = root / "base-run"
            gate_path.write_text(
                json.dumps(gate_for(handoff, "canonical-base-run")),
                encoding="utf-8",
            )
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=base, run_id="canonical-base-run", model="gpt-5.6-terra",
            )
            self.complete_with_explicit_gaps(base)
            supplement = root / "supplement-run"
            (supplement / "research").mkdir(parents=True)
            shutil.copy2(base / "evidence/gate.json", supplement / "gate.json")
            supplement_report = next((base / "research/reports").glob("*/dimension-report.json"))
            shutil.copy2(supplement_report, supplement / "research/dimension-report.json")
            report = json.loads(supplement_report.read_text())
            (supplement / "run_manifest.json").write_text(json.dumps({
                "run_id": "different-run",
            }))
            shutil.move(str(supplement / "gate.json"), str(supplement / "evidence-gate.json"))
            (supplement / "evidence").mkdir()
            shutil.move(str(supplement / "evidence-gate.json"), str(supplement / "evidence/gate.json"))
            (supplement / "research/task-execution-proof.json").write_text(json.dumps({
                "report_ref": "research/dimension-report.json",
            }))

            target = root / "canonical"
            result = assemble_canonical_holding_research_package(
                ROOT,
                base_run_dir=base,
                company_research_run_dir=company,
                output_dir=target,
                supplement_run_dirs=[supplement],
            )
            self.assertEqual(result["consumability"], "DOWNSTREAM_READY")
            bundle = json.loads((target / "research/holding-research-bundle.json").read_text())
            self.assertTrue(all(
                item["report_id"]
                for item in bundle["coverage"]
                if item["capability"] == "COMPANY_RESEARCH"
            ))
            self.assertEqual(
                bundle["package_provenance"]["excluded_supplements"][0]["reason_codes"],
                ["RUN_ID_MISMATCH"],
            )
            package_proof = json.loads(
                (target / "research/canonical-package-proof.json").read_text()
            )
            self.assertEqual(len(package_proof["source_inputs"]["supplements"]), 1)
            self.assertEqual(
                set(package_proof["implementation_snapshot"]),
                {
                    "product/council/multidimensional_research.py",
                    "product/council/multidimensional_output.py",
                    "product/runtime/multidimensional_stage.py",
                    "product/runtime/cli.py",
                    "product/schemas/runtime/holding-research-bundle-v1.1.schema.json",
                    "product/skills/portfolio-council/SKILL.md",
                    "product/version-manifest.json",
                },
            )
            proof = check_multidimensional_bundle_consumable(ROOT, target)
            self.assertEqual(proof["downstream_status"], "DOWNSTREAM_READY")
            self.assertEqual(proof["downstream_models_started"], [])

    def test_multidimensional_invocation_can_query_its_frozen_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            tools = StatelessFixtureTools(default_run_dir=run)
            result = tools.query(
                run_id=task["run_id"], agent=task["agent"],
                invocation_id=task["invocation_id"],
                evidence_ids=[task["allowed_evidence_ids"][0]],
            )
            self.assertEqual(result["evidence"][0]["evidence_id"], task["allowed_evidence_ids"][0])
            self.assertEqual(tools.events[-1]["invocation_id"], task["invocation_id"])

    def test_hook_loads_correct_agent_packet_and_rejects_unready_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            invocation = run / "invocation"
            invocation.mkdir()
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation / "subagent-events.jsonl"),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation / "subagent-dispatches.jsonl"),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst,runtime_market_catalyst",
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
            }
            index = json.loads((run / "research/dispatch-index.json").read_text())
            first = index["tasks"][0]
            pre = {
                "hook_event_name": "PreToolUse", "session_id": "parent", "turn_id": "turn",
                "tool_name": "spawn_agent", "tool_use_id": "tool-1", "cwd": str(ROOT / "product"),
                "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                "tool_input": {
                    "agent_type": first["agent"], "task_name": first["task_name"],
                    "fork_turns": "none", "message": "启动冻结多维研究任务。",
                },
            }
            record, response = handle_hook_event(pre, environ=environment)
            self.assertEqual(record["decision"], "ALLOW")
            self.assertEqual(response, {})
            start = {
                "hook_event_name": "SubagentStart", "session_id": "parent", "turn_id": "turn",
                "agent_id": "child", "agent_type": first["agent"], "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"), "permission_mode": "read-only",
            }
            start_record, start_response = handle_hook_event(start, environ=environment)
            context = json.loads(start_response["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(context["identity"]["task_id"], first["task_id"])
            self.assertEqual(start_record["context_binding"]["packet_hash"], first["packet_hash"])

            dependent = next(item for item in index["tasks"] if item["capability"] == "RESEARCH_REPORT")
            denied = dict(pre, tool_use_id="tool-2", tool_input={
                "agent_type": dependent["agent"], "task_name": dependent["task_name"],
                "fork_turns": "none", "message": "依赖尚未完成。",
            })
            denied_record, denied_response = handle_hook_event(denied, environ=environment)
            self.assertEqual(denied_record["decision"], "DENY_DISPATCH_CONTRACT")
            self.assertEqual(
                denied_record["dispatch_binding"]["failure_code"],
                "RESEARCH_DEPENDENCY_NOT_READY",
            )
            self.assertEqual(
                denied_response["hookSpecificOutput"]["permissionDecision"], "deny"
            )

    def test_failed_report_releases_slot_but_does_not_satisfy_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            index["target_concurrency"] = 1
            index["index_hash"] = canonical_hash({
                key: value for key, value in index.items() if key != "index_hash"
            })
            index_path.write_text(json.dumps(index), encoding="utf-8")
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation_dir / "subagent-events.jsonl"),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation_dir / "subagent-dispatches.jsonl"),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst,runtime_market_catalyst",
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
            }
            fundamental = next(
                item for item in index["tasks"]
                if item["capability"] == "FUNDAMENTAL_EVENT"
            )
            dependent = next(
                item for item in index["tasks"]
                if item["capability"] == "RESEARCH_REPORT"
                and item["security_ids"] == fundamental["security_ids"]
            )
            independent = next(
                item for item in index["tasks"]
                if item["capability"] == "INDUSTRY_COMPARISON"
                and item["security_ids"] == fundamental["security_ids"]
            )

            def pre(task, tool_id):
                return {
                    "hook_event_name": "PreToolUse", "session_id": "parent",
                    "turn_id": "turn", "tool_name": "spawn_agent",
                    "tool_use_id": tool_id, "cwd": str(ROOT / "product"),
                    "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                    "tool_input": {
                        "agent_type": task["agent"], "task_name": task["task_name"],
                        "fork_turns": "none", "message": "启动冻结多维研究任务。",
                    },
                }

            allowed, _ = handle_hook_event(
                pre(fundamental, "fundamental"), environ=environment
            )
            self.assertEqual(allowed["decision"], "ALLOW")
            (invocation_dir / "subagent-events.jsonl").write_text(
                json.dumps({
                    "hook_event_name": "SubagentStop",
                    "parent_session_id": "parent",
                    "output_binding": {"invocation_id": fundamental["invocation_id"]},
                    "output_capture": {
                        "status": "FAILED", "failure_code": "EVIDENCE_CLOSURE_FAILED"
                    },
                }) + "\n",
                encoding="utf-8",
            )
            blocked, _ = handle_hook_event(
                pre(dependent, "dependent"), environ=environment
            )
            self.assertEqual(blocked["decision"], "DENY_DISPATCH_CONTRACT")
            self.assertEqual(
                blocked["dispatch_binding"]["failure_code"],
                "RESEARCH_DEPENDENCY_NOT_READY",
            )
            released, _ = handle_hook_event(
                pre(independent, "independent"), environ=environment
            )
            self.assertEqual(released["decision"], "ALLOW")

    def test_prepare_binds_same_source_technical_calculation_and_chart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            for security_id, scale in (
                ("US:COMMON_STOCK:AAPL", 2), ("US:SPY", 1)
            ):
                for day_index, day in enumerate(("2026-09-08", "2026-09-09", "2026-09-10")):
                    for field, value, unit in (
                        ("historical_close_price", 100 + day_index * scale, "USD"),
                        ("adjusted_close_price", 100 + day_index * scale, "USD"),
                        ("share_volume", 1000 + day_index * 10, "shares"),
                    ):
                        evidence_id = f"ev-{security_id.split(':')[-1].lower()}-{day}-{field}"
                        gate["allowed_evidence"].append({
                            "evidence_id": evidence_id,
                            "security_id": security_id,
                            "semantic_field": field,
                            "value": str(value),
                            "unit": unit,
                            "source_id": "yahoo-daily",
                            "source_type": "yahoo",
                            "as_of": day + "T20:00:00Z",
                            "published_at": day + "T20:00:00Z",
                            "retrieved_at": "2026-09-11T11:00:00Z",
                            "metadata": {"trading_date": day},
                        })
                        gate["allowed_evidence_ids"].append(evidence_id)
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
                run_id="technical-stage-run", model="gpt-5.6-terra",
            )
            index = json.loads((run / "research/dispatch-index.json").read_text())
            technical = next(
                item for item in index["tasks"]
                if item["capability"] == "TECHNICAL_STRUCTURE"
                and item["security_ids"] == ["US:COMMON_STOCK:AAPL"]
            )
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, technical["task_name"]
            )
            prepared = packet["prepared_analysis"]
            self.assertIsNotNone(prepared["calculation"])
            self.assertNotIn("evidence_fact_ids", prepared["calculation"])
            calculation_artifact = json.loads(
                (run / prepared["calculation_ref"]).read_text()
            )
            self.assertEqual(
                prepared["calculation"]["evidence_fact_count"],
                len(calculation_artifact["evidence_fact_ids"]),
            )
            self.assertEqual(
                len(prepared["calculation"]["evidence_fact_ids_hash"]), 64
            )
            self.assertEqual(technical["allowed_evidence_ids"], [])
            self.assertIsNotNone(prepared["chart"])
            self.assertEqual(len(prepared["allowed_artifact_refs"]), 2)
            for relative in prepared["allowed_artifact_refs"]:
                self.assertTrue((run / relative).is_file())
            self.assertEqual(
                packet["output_schema"]["properties"]["artifact_refs"]["items"]["enum"],
                prepared["allowed_artifact_refs"],
            )

    def test_bounded_latest_facts_keeps_recent_values_per_reporting_series(self) -> None:
        facts = []
        for index, as_of in enumerate(("2024-12-31", "2025-12-31", "2026-06-30")):
            facts.append({
                "evidence_id": f"ev-revenue-{index}",
                "security_id": "US:COMMON_STOCK:TEST",
                "semantic_field": "us-gaap.Revenues",
                "unit": "USD",
                "as_of": f"{as_of}T00:00:00Z",
                "published_at": f"{as_of}T20:00:00Z",
                "retrieved_at": "2026-09-15T00:00:00Z",
                "metadata": {"form": "10-K", "period_start": "2024-01-01"},
            })
        selected = _bounded_latest_facts(facts)
        self.assertEqual(
            [item["evidence_id"] for item in selected],
            ["ev-revenue-1", "ev-revenue-2"],
        )

    def test_dependency_report_is_delivered_as_structured_agent_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            fundamental = next(
                item for item in index["tasks"]
                if item["capability"] == "FUNDAMENTAL_EVENT"
                and item["security_ids"] == ["US:COMMON_STOCK:AAPL"]
            )
            invocation = json.loads((run / fundamental["invocation_path"]).read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            report = envelope_research_dimension_draft(
                {
                    "run_id": fundamental["run_id"],
                    "invocation_id": fundamental["invocation_id"],
                    "agent": fundamental["agent"],
                    "status": "COMPLETE",
                    "sufficiency": "SUFFICIENT",
                    "evaluation_status": "PASS",
                    "summary": "公司资料支持一项有依据的核心判断。",
                    "claims": [{
                        "claim_id": "fundamental-claim-1",
                        "question": "核心经营驱动是什么？",
                        "statement": "收入事实为后续研报对比提供公司基线。",
                        "kind": "FACT",
                        "evidence_refs": [fundamental["allowed_evidence_ids"][0]],
                        "research_claim_refs": [], "assumption_ids": [],
                        "document_refs": [],
                        "calculation_refs": [],
                    }],
                    "assumptions": [], "calculations": [],
                    "documents": [], "research_relationships": [],
                    "limitations": [], "observation_conditions": [],
                    "data_gaps": [], "artifact_refs": [],
                },
                task=fundamental,
                invocation=invocation,
                expected_bindings={
                    "handoff_id": handoff["handoff_id"],
                    "handoff_hash": handoff["handoff_hash"],
                    "portfolio_hash": handoff["portfolio_hash"],
                    "council_request_id": request["request_id"],
                    "council_request_hash": request["request_hash"],
                    "decision_cutoff": gate["decision_cutoff"],
                },
                allowed_security_ids=[
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                    if item["asset_type"] == "COMMON_STOCK"
                ],
                allowed_evidence_ids=fundamental["allowed_evidence_ids"],
            )
            output = run / "research/reports/dependency"
            output.mkdir(parents=True)
            (output / "dimension-report.json").write_text(
                json.dumps(report), encoding="utf-8"
            )
            dependent = next(
                item for item in index["tasks"]
                if item["capability"] == "RESEARCH_REPORT"
                and item["security_ids"] == ["US:COMMON_STOCK:AAPL"]
            )
            packet = build_multidimensional_dispatch_packet(
                ROOT, run, dependent["task_name"]
            )
            self.assertEqual(
                packet["allowed_research_claim_ids"], ["fundamental-claim-1"]
            )
            self.assertEqual(
                packet["dependency_reports"][0]["report_hash"], report["report_hash"]
            )

    def test_finalizer_keeps_valid_reports_and_records_dependency_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            bindings = {
                "handoff_id": handoff["handoff_id"],
                "handoff_hash": handoff["handoff_hash"],
                "portfolio_hash": handoff["portfolio_hash"],
                "council_request_id": request["request_id"],
                "council_request_hash": request["request_hash"],
                "decision_cutoff": gate["decision_cutoff"],
            }
            failed_task = next(
                task for task in index["tasks"]
                if task["capability"] == "FUNDAMENTAL_EVENT"
            )
            blocked_task = next(
                task for task in index["tasks"]
                if task["capability"] == "RESEARCH_REPORT"
            )
            events = []
            for task in index["tasks"]:
                if task is failed_task:
                    events.append({
                        "hook_event_name": "SubagentStop",
                        "final_structured_output_hash": "f" * 64,
                        "output_binding": {"invocation_id": task["invocation_id"]},
                        "output_capture": {
                            "status": "FAILED",
                            "failure_code": "DIMENSION_REPORT_CLAIM_UNGROUNDED",
                        },
                    })
                    continue
                if task is blocked_task:
                    continue
                invocation = json.loads((run / task["invocation_path"]).read_text())
                report = envelope_research_dimension_draft(
                    {
                        "run_id": task["run_id"],
                        "invocation_id": task["invocation_id"],
                        "agent": task["agent"],
                        "status": "INSUFFICIENT_EVIDENCE",
                        "sufficiency": "INSUFFICIENT",
                        "evaluation_status": "NOT_EVALUATED",
                        "summary": "本测试仅验证失败隔离与覆盖交接。",
                        "claims": [], "assumptions": [], "calculations": [],
                        "documents": [], "research_relationships": [],
                        "limitations": ["资料不足。"],
                        "observation_conditions": [],
                        "data_gaps": [{
                            "gap_id": f"gap:{task['task_id']}",
                            "reason_code": "UNKNOWN",
                            "description": "测试资料不足。",
                            "impact": "不形成研究主张。",
                        }],
                        "artifact_refs": [],
                    },
                    task=task,
                    invocation=invocation,
                    expected_bindings=bindings,
                    allowed_security_ids=[
                        item["security_id"] for item in handoff["portfolio"]["positions"]
                    ],
                    allowed_evidence_ids=task["allowed_evidence_ids"],
                    allowed_documents=task.get("allowed_documents", []),
                )
                output = persist_dimension_report(
                    run / "research/reports" / task["task_id"],
                    report=report,
                    evidence=[],
                )
                events.append({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED", "task_id": task["task_id"],
                        "path": str(Path(output["json"]).relative_to(run)),
                    },
                })
            (invocation_dir / "subagent-dispatches.jsonl").write_text(
                "\n".join(json.dumps(
                    {
                        "task_name": task["task_name"],
                        "decision": "DENY_DISPATCH_CONTRACT",
                        "dispatch_binding": {
                            "failure_code": "RESEARCH_DEPENDENCY_NOT_READY"
                        },
                    }
                    if task is blocked_task else {
                        "task_name": task["task_name"], "decision": "ALLOW"
                    }
                ) for task in index["tasks"]) + "\n",
                encoding="utf-8",
            )
            (invocation_dir / "subagent-events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n",
                encoding="utf-8",
            )
            result = finalize_multidimensional_stage_run(ROOT, run)
            self.assertEqual(result["status"], "PASSED")
            bundle = json.loads(
                (run / "research/holding-research-bundle.json").read_text()
            )
            failed = next(
                item for item in bundle["coverage"]
                if item["capability"] == "FUNDAMENTAL_EVENT"
            )
            self.assertEqual(failed["status"], "FAILED")
            self.assertIsNone(failed["report_id"])
            self.assertIn("DIMENSION_REPORT_CLAIM_UNGROUNDED", failed["gap_reason"])
            blocked = next(
                item for item in bundle["coverage"]
                if item["capability"] == "RESEARCH_REPORT"
            )
            self.assertEqual(blocked["status"], "FAILED")
            self.assertIn(
                "MULTIDIMENSIONAL_UPSTREAM_DEPENDENCY_FAILED",
                blocked["gap_reason"],
            )
            proof = json.loads((run / "research/execution-proof.json").read_text())
            self.assertFalse(proof["all_reports_valid"])
            self.assertTrue(proof["coverage_complete"])
            self.assertEqual(
                {item["task_id"] for item in proof["failed_tasks"]},
                {failed_task["task_id"], blocked_task["task_id"]},
            )
            markdown = (run / "research/holding-research-bundle.md").read_text()
            self.assertIn("## 已验证报告摘要", markdown)
            self.assertIn("本测试仅验证失败隔离与覆盖交接。", markdown)
            self.assertIn("## 未形成有效报告的维度", markdown)
            self.assertIn("未执行额外语义综合", markdown)

    def test_finalizer_records_started_task_without_stop_as_explicit_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare(Path(temp), count=1)
            invocation_dir = run / "invocation"
            invocation_dir.mkdir()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            missing_task = next(
                task for task in index["tasks"]
                if task["capability"] == "INDUSTRY_COMPARISON"
            )
            handoff = json.loads((run / "audit/portfolio-handoff.json").read_text())
            request = json.loads((run / "council-request.json").read_text())
            gate = json.loads((run / "evidence/gate.json").read_text())
            bindings = {
                "handoff_id": handoff["handoff_id"],
                "handoff_hash": handoff["handoff_hash"],
                "portfolio_hash": handoff["portfolio_hash"],
                "council_request_id": request["request_id"],
                "council_request_hash": request["request_hash"],
                "decision_cutoff": gate["decision_cutoff"],
            }
            events = []
            for task in index["tasks"]:
                if task is missing_task:
                    events.append({
                        "hook_event_name": "SubagentStart",
                        "context_binding": {
                            "status": "DELIVERED",
                            "invocation_id": task["invocation_id"],
                        },
                    })
                    events.append({
                        "hook_event_name": "SubagentStopBlocked",
                        "child_session_id": "child-repair-unavailable",
                        "output_binding": {"invocation_id": task["invocation_id"]},
                        "repair_request": {
                            "task_id": task["task_id"],
                            "invocation_id": task["invocation_id"],
                            "validation_error": "DIMENSION_REPORT_SCHEMA_INVALID",
                            "output_schema_hash": "a" * 64,
                        },
                        "output_capture": {
                            "status": "FAILED",
                            "attempt": 1,
                            "repair_state": "REPAIR_REQUESTED",
                            "raw_output_hash": "b" * 64,
                            "raw_path": "research/raw-drafts/unavailable.json",
                        },
                    })
                    continue
                invocation = json.loads((run / task["invocation_path"]).read_text())
                report = envelope_research_dimension_draft(
                    {
                        "run_id": task["run_id"],
                        "invocation_id": task["invocation_id"],
                        "agent": task["agent"],
                        "status": "INSUFFICIENT_EVIDENCE",
                        "sufficiency": "INSUFFICIENT",
                        "evaluation_status": "NOT_EVALUATED",
                        "summary": "本测试验证缺失终态事件的失败隔离。",
                        "claims": [], "assumptions": [], "calculations": [],
                        "documents": [], "research_relationships": [],
                        "limitations": ["资料不足。"],
                        "observation_conditions": [],
                        "data_gaps": [{
                            "gap_id": f"gap:{task['task_id']}",
                            "reason_code": "UNKNOWN",
                            "description": "测试资料不足。",
                            "impact": "不形成研究主张。",
                        }],
                        "artifact_refs": [],
                    },
                    task=task, invocation=invocation,
                    expected_bindings=bindings,
                    allowed_security_ids=[
                        item["security_id"] for item in handoff["portfolio"]["positions"]
                    ],
                    allowed_evidence_ids=task["allowed_evidence_ids"],
                    allowed_documents=task.get("allowed_documents", []),
                )
                output = persist_dimension_report(
                    run / "research/reports" / task["task_id"],
                    report=report, evidence=[],
                )
                events.append({
                    "hook_event_name": "SubagentStop",
                    "output_capture": {
                        "status": "SAVED", "task_id": task["task_id"],
                        "path": str(Path(output["json"]).relative_to(run)),
                    },
                })
            (invocation_dir / "subagent-dispatches.jsonl").write_text(
                "\n".join(json.dumps({
                    "task_name": task["task_name"], "decision": "ALLOW"
                }) for task in index["tasks"]) + "\n",
                encoding="utf-8",
            )
            (invocation_dir / "subagent-events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n",
                encoding="utf-8",
            )
            result = finalize_multidimensional_stage_run(ROOT, run)
            self.assertEqual(result["status"], "PASSED")
            bundle = json.loads(
                (run / "research/holding-research-bundle.json").read_text()
            )
            failed = next(
                item for item in bundle["coverage"]
                if item["capability"] == "INDUSTRY_COMPARISON"
            )
            self.assertEqual(failed["status"], "FAILED")
            self.assertIn("TERMINAL_EVENT_MISSING", failed["gap_reason"])
            proof = json.loads((run / "research/execution-proof.json").read_text())
            self.assertEqual(
                proof["failed_tasks"][0]["failure_source"],
                "START_WITHOUT_STOP_AFTER_PARENT_EXIT",
            )
            self.assertIsNone(proof["failed_tasks"][0]["rejected_output_hash"])
            self.assertEqual(len(proof["repair_attempts"]), 1)
            self.assertEqual(
                proof["repair_attempts"][0]["task_id"], missing_task["task_id"]
            )
            self.assertIsNone(
                proof["repair_attempts"][0]["terminal_status"]
            )


if __name__ == "__main__":
    unittest.main()
