"""Preparation boundary for the independent predecision CIO run."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.cli import main as runtime_cli_main
from product.runtime.predecision_cio_stage import (
    PredecisionCioStageError,
    _decoding_schema,
    _output_schema,
    build_predecision_cio_prompt,
    check_predecision_cio_trace,
    finalize_predecision_cio_advice,
    finalize_predecision_cio_research,
    prepare_predecision_cio_run,
    validate_predecision_cio_run,
)


REPO = Path(__file__).resolve().parents[1]


def _write(root: Path, ref: str, value: dict) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class PredecisionCioPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.target = self.root / "cio"
        self.package_ref = "research/skeptic/pre-decision-research-package.json"
        self.package = {
            "run_id": "source-1", "package_hash": "a" * 64,
            "consumability": "DOWNSTREAM_READY", "decision_cutoff": "2026-09-20T00:00:00Z",
            "request_id": "source-request", "request_hash": "b" * 64,
            "handoff_id": "handoff-1", "handoff_hash": "c" * 64,
            "portfolio_hash": "d" * 64, "gate_hash": "e" * 64,
            "counter_theses": [{"security_id": "US:COMMON_STOCK:MRVL", "invocation_id": "skeptic-1", "report": {
                "artifact_ref": "research/skeptic/reports/mrvl/counter-thesis.json",
                "content_hash": "a" * 64,
            }}],
            "coverage": {},
            "execution_proof": {"artifact_ref": "research/skeptic/execution-proof.json"},
        }
        self.handoff = {
            "portfolio_hash": "d" * 64,
            "source_items": [{"source_id": "s1", "as_of": "2026-09-20T00:00:00Z",
                              "retrieved_at": "2026-09-20T00:00:00Z"}],
            "field_lineage": [{"field_path": "account_snapshot.cash_balance", "source_refs": ["s1"]},
                              {"field_path": "portfolio.positions.p1.quantity", "source_refs": ["s1"]}],
            "portfolio": {"base_currency": "USD", "as_of": "2026-09-20T00:00:00Z", "positions": [{
                "position_id": "p1", "security_id": "US:COMMON_STOCK:MRVL", "asset_type": "COMMON_STOCK", "quantity": 10,
                "quote_price": 80, "market_value": 800, "source_refs": ["s1"],
            }]},
            "account_snapshot": {"cash_balance": 200, "as_of": "2026-09-20T00:00:00Z"}, "unknown_fields": [],
        }
        self.bundle = {"common_stock_security_ids": ["US:COMMON_STOCK:MRVL"], "coverage": {}, "report_refs": [{
            "artifact_ref": "research/reports/mrvl.json", "report_id": "company:US:COMMON_STOCK:MRVL",
            "capability": "COMPANY_RESEARCH", "security_ids": ["US:COMMON_STOCK:MRVL"],
            "report_hash": "f" * 64,
        }]}
        self._create_files()

    def _create_files(self) -> None:
        gate = {"run_id": "source-1", "decision_cutoff": "2026-09-20T00:00:00Z",
                "source_mode": "fixture", "allowed_evidence_ids": ["ev-1"],
                "allowed_evidence": [{"evidence_id": "ev-1", "source_id": "sec",
                                      "as_of": "2026-09-20T00:00:00Z",
                                      "retrieved_at": "2026-09-20T00:00:00Z"},
                                     {"evidence_id": "price-1", "security_id": "US:COMMON_STOCK:MRVL",
                                      "semantic_field": "close_price", "currency": "USD",
                                      "value": "80", "source_id": "yahoo-daily",
                                      "as_of": "2026-09-20T00:00:00Z",
                                      "retrieved_at": "2026-09-20T00:00:00Z"}]}
        gate["allowed_evidence_ids"].append("price-1")
        gate["bundle_hash"] = canonical_hash(gate)
        self.package["gate_hash"] = gate["bundle_hash"]
        for ref, value in {
            self.package_ref: self.package,
            "run_manifest.json": {"run_id": "source-1"},
            "audit/portfolio-handoff.json": self.handoff,
            "council-request.json": {"request_id": "source-request"},
            "evidence/gate.json": gate,
            "research/holding-research-bundle.json": self.bundle,
            "research/skeptic/execution-proof.json": {"status": "PASSED"},
            "research/skeptic/reports/mrvl/counter-thesis.json": {"challenges": []},
            "research/reports/mrvl.json": {"claims": []},
        }.items():
            _write(self.source, ref, value)

    def _prepare(self, **kwargs):
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package"
        ):
            return prepare_predecision_cio_run(
                REPO, source_run_dir=self.source, run_dir=self.target,
                run_id="cio-1", target_security_id="US:COMMON_STOCK:MRVL", **kwargs,
            )

    def _write_model_proof(self, output: dict) -> None:
        invocation = self.target / "invocation"
        invocation.mkdir(exist_ok=True)
        text = json.dumps(output)
        (invocation / "final-message.json").write_text(text, encoding="utf-8")
        (invocation / "prompt.txt").write_text(
            build_predecision_cio_prompt(REPO, self.target), encoding="utf-8"
        )
        (invocation / "cio-output.schema.json").write_text("{}", encoding="utf-8")
        (invocation / "environment-manifest.json").write_text(json.dumps({
            "command": ["codex", "exec", "--skip-git-repo-check", "--sandbox",
                        "workspace-write", "--add-dir", str(self.target.resolve()), "-C",
                        str(self.target.resolve()), "--model", "gpt-6-luna"],
            "run_id": "cio-1", "model": "gpt-6-luna",
            "started_at": "2026-09-20T00:00:00Z",
            "prompt_hash": file_hash(invocation / "prompt.txt"),
            "output_schema_hash": file_hash(invocation / "cio-output.schema.json"),
            "product_instructions_file_hash": file_hash(REPO / "product/AGENTS.md"),
            "skill_file_hash": file_hash(REPO / "product/skills/portfolio-council/SKILL.md"),
            "agent_file_hash": file_hash(REPO / "product/.codex/agents/runtime_cio.toml"),
        }), encoding="utf-8")
        (invocation / "codex-events.jsonl").write_text("\n".join(json.dumps(item) for item in (
            {"type": "thread.started", "thread_id": "test"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
            {"type": "turn.completed"},
        )) + "\n", encoding="utf-8")

    def test_research_prepare_keeps_source_and_no_risk_context(self) -> None:
        before = file_hash(self.source / self.package_ref)
        result = self._prepare()
        self.assertEqual(result["actual_level"], "RESEARCH_SYNTHESIS")
        self.assertEqual(file_hash(self.source / self.package_ref), before)
        self.assertEqual(file_hash(self.target / "source-inputs" / self.package_ref), before)
        self.assertFalse((self.target / "risk-context.json").exists())
        self.assertFalse((self.target / "decision.json").exists())
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        self.assertEqual(request["request_hash"], canonical_hash({
            key: value for key, value in request.items() if key != "request_hash"
        }))

    def test_advice_and_mandate_are_rejected_before_writes(self) -> None:
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            self._prepare(requested_level="PORTFOLIO_ADVICE")
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_MANDATE_NOT_APPLICABLE_TO_RESEARCH"):
            self._prepare(mandate_path=self.root / "mandate.json")
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            finalize_predecision_cio_advice(REPO, self.target)

    def test_direct_cli_advice_paths_reject_before_model_or_output(self) -> None:
        common = ["--repo", str(REPO), "--run-dir", str(self.target)]
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            runtime_cli_main([
                "prepare-predecision-cio", *common, "--source-run", str(self.source),
                "--run-id", "cio-1", "--target-security-id", "US:COMMON_STOCK:MRVL",
                "--requested-level", "PORTFOLIO_ADVICE",
            ])
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            runtime_cli_main(["finalize-predecision-cio-advice", *common])
        self.assertFalse(self.target.exists())

    def test_prepared_advice_request_cannot_reenter_model_path(self) -> None:
        self._prepare()
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        manifest = json.loads((self.target / "run_manifest.json").read_text())
        request["requested_level"] = request["actual_level"] = "PORTFOLIO_ADVICE"
        request["request_hash"] = canonical_hash({
            key: value for key, value in request.items() if key != "request_hash"
        })
        manifest["request_hash"] = request["request_hash"]
        manifest["manifest_hash"] = canonical_hash({
            key: value for key, value in manifest.items() if key != "manifest_hash"
        })
        _write(self.target, "predecision-cio-request.json", request)
        _write(self.target, "run_manifest.json", manifest)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            validate_predecision_cio_run(REPO, self.target)
        self.assertFalse((self.target / "invocation").exists())

    def test_model_decoder_schema_keeps_types_and_finalizer_exact_contract(self) -> None:
        self._prepare()
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        catalog = json.loads((self.target / "report-catalog.json").read_text())["reports"]
        authoritative = _output_schema(REPO, request, catalog, run_dir=self.target)
        decoder = _decoding_schema(authoritative)
        self.assertEqual(authoritative["properties"]["consumed_reports"]["const"], [
            {key: item[key] for key in (
                "report_id", "role", "security_ids", "invocation_id", "content_hash"
            )} for item in catalog
        ])
        self.assertEqual(decoder["properties"]["consumed_reports"]["type"], "array")
        self.assertNotIn("const", decoder["properties"]["consumed_reports"])
        self.assertEqual(decoder["properties"]["actual_level"], {
            "type": "string", "enum": ["RESEARCH_SYNTHESIS"]
        })
        allowed_ids = [item["report_id"] for item in catalog]
        for field in ("key_facts", "macro_market_transmission"):
            self.assertEqual(
                decoder["properties"][field]["items"]["properties"]["report_ids"]["items"]["enum"],
                allowed_ids,
            )

        def inspect(node: dict) -> None:
            self.assertNotIn("const", node)
            self.assertNotIn("uniqueItems", node)
            if "enum" in node:
                self.assertIn("type", node)
            for child in node.get("properties", {}).values():
                inspect(child)
            if isinstance(node.get("items"), dict):
                inspect(node["items"])

        inspect(decoder)

    def test_prompt_requires_every_final_evidence_reference_to_be_queried(self) -> None:
        self._prepare()
        prompt = build_predecision_cio_prompt(REPO, self.target)
        self.assertIn("所有最终输出中的 Evidence ID", prompt)
        self.assertIn("不能只查一个却引用多个", prompt)
        self.assertIn("必须查询并引用两个科目各自的 Evidence ID", prompt)
        self.assertIn("MD&A 文本冲突未消解", prompt)
        self.assertIn("MRVL 对基准的相对表现", prompt)
        self.assertIn((REPO / "product/AGENTS.md").read_text(), prompt)
        self.assertIn((REPO / "product/skills/portfolio-council/SKILL.md").read_text(), prompt)
        self.assertIn((REPO / "product/.codex/agents/runtime_cio.toml").read_text(), prompt)

    def test_structurally_consumable_source_stops_before_writes(self) -> None:
        self.package["consumability"] = "STRUCTURALLY_CONSUMABLE"
        _write(self.source, self.package_ref, self.package)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_SOURCE_PACKAGE_NOT_READY"):
            self._prepare()
        self.assertFalse(self.target.exists())

    def test_source_validator_failure_stops_before_writes(self) -> None:
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package",
            side_effect=ValueError("COUNTER_PACKAGE_HASH_MISMATCH"),
        ):
            with self.assertRaisesRegex(ValueError, "COUNTER_PACKAGE_HASH_MISMATCH"):
                prepare_predecision_cio_run(
                    REPO, source_run_dir=self.source, run_dir=self.target,
                    run_id="cio-1", target_security_id="US:COMMON_STOCK:MRVL",
                )
        self.assertFalse(self.target.exists())

    def test_destination_cannot_be_nested_in_source_run(self) -> None:
        nested_target = self.source / "new-cio-run"
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package"
        ):
            with self.assertRaisesRegex(PredecisionCioStageError, "CIO_SOURCE_RUN_INVALID"):
                prepare_predecision_cio_run(
                    REPO, source_run_dir=self.source, run_dir=nested_target,
                    run_id="cio-1", target_security_id="US:COMMON_STOCK:MRVL",
                )
        self.assertFalse(nested_target.exists())

    def test_current_mode_requires_new_source(self) -> None:
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_CURRENT_RESEARCH_REQUIRES_NEW_SOURCE"):
            self._prepare(time_mode="CURRENT")
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_CURRENT_RESEARCH_REQUIRES_NEW_SOURCE"):
            self._prepare(time_mode="CURRENT", max_research_age_days=0)
        self.assertFalse(self.target.exists())

    def test_other_security_cannot_inherit_mrvl_nonholding_context(self) -> None:
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package"
        ):
            with self.assertRaisesRegex(PredecisionCioStageError, "CIO_RESEARCH_TARGET_NOT_IN_SCOPE"):
                prepare_predecision_cio_run(
                    REPO, source_run_dir=self.source, run_dir=self.target,
                    run_id="cio-1", target_security_id="US:COMMON_STOCK:ALB",
                )
        self.assertFalse(self.target.exists())

    def test_mixed_assets_are_preserved_without_account_advice(self) -> None:
        self.handoff["portfolio"]["positions"].append({
            "position_id": "p2", "security_id": "US:QQQ", "asset_type": "ETF",
            "quantity": 2, "source_refs": ["s2"],
        })
        _write(self.source, "audit/portfolio-handoff.json", self.handoff)
        self._prepare()
        frozen = json.loads((self.target / "source-inputs/audit/portfolio-handoff.json").read_text())
        self.assertEqual(len(frozen["portfolio"]["positions"]), 2)
        self.assertFalse((self.target / "risk-context.json").exists())

    def test_cio_query_is_bound_to_frozen_gate_and_run(self) -> None:
        self._prepare()
        validate_predecision_cio_run(REPO, self.target)
        tools = StatelessFixtureTools(default_run_dir=self.target)
        identity = {"run_id": "cio-1", "agent": "runtime_cio", "invocation_id": "cio:cio-1"}
        self.assertEqual(["ev-1"], [
            fact["evidence_id"] for fact in tools.query(**identity, evidence_ids=["ev-1"])["evidence"]
        ])
        with self.assertRaisesRegex(ToolAccessError, "UNKNOWN_EVIDENCE"):
            tools.query(**identity, evidence_ids=["outside-gate"])
        with self.assertRaisesRegex(ToolAccessError, "INVOCATION_IDENTITY_MISMATCH"):
            tools.query(**{**identity, "run_id": "another-run"}, evidence_ids=["ev-1"])

    def test_materialized_report_tampering_blocks_query(self) -> None:
        self._prepare()
        (self.target / "source-inputs/research/reports/mrvl.json").write_text("{}", encoding="utf-8")
        tools = StatelessFixtureTools(default_run_dir=self.target)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_FROZEN_INPUT_DRIFT"):
            tools.query(run_id="cio-1", agent="runtime_cio", invocation_id="cio:cio-1",
                        evidence_ids=["ev-1"])

    def test_research_finalizer_is_non_action_and_query_backed(self) -> None:
        self.handoff["account_snapshot"]["cash_balance"] = None
        _write(self.source, "audit/portfolio-handoff.json", self.handoff)
        self._prepare()
        tools = StatelessFixtureTools(default_run_dir=self.target)
        tools.query(run_id="cio-1", agent="runtime_cio", invocation_id="cio:cio-1",
                    evidence_ids=["ev-1"])
        events = self.target / "events/mcp/events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        events.write_text(json.dumps(tools.events[-1]) + "\n", encoding="utf-8")
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        catalog = json.loads((self.target / "report-catalog.json").read_text())["reports"]
        consumed = [{key: item[key] for key in (
            "report_id", "role", "security_ids", "invocation_id", "content_hash"
        )} for item in catalog]
        output = {
            "schema_version": "predecision-cio-synthesis/1.0.0", "run_id": "cio-1",
            "invocation_id": "cio:cio-1", "source_run_id": "source-1",
            "source_package_hash": request["source_package_hash"],
            "target_security_id": "US:COMMON_STOCK:MRVL", "requested_level": "RESEARCH_SYNTHESIS",
            "actual_level": "RESEARCH_SYNTHESIS", "decision_cutoff": request["decision_cutoff"],
            "generated_at": "2026-09-24T00:00:00Z", "status": "LOW_CONFIDENCE",
            "advisory_only": True, "complete_portfolio_decision": False,
            "risk_status": "NOT_RUN",
            "consumed_reports": consumed, "analysis_horizon": "未来两个季度，仅为分析假设",
            "judgment": "公司经营判断暂不确定。", "reasoning": "资料不足，保留分歧。",
            "thesis": "增长有待验证", "counter_thesis": "证据时点仍有缺口",
            "consensus": [], "conflicts": ["增长证据不足"],
            "business_outlook": "待核实", "price_attractiveness": "无法判断",
            "account_fit": "当前账户适配未评估", "key_facts": [{
                "fact": "测试事实", "report_ids": [catalog[0]["report_id"]],
                "evidence_refs": ["ev-1"], "reasoning": "仅测试结构",
            }], "challenge_dispositions": [], "macro_market_transmission": [{
                "channel": "利率", "report_ids": [catalog[0]["report_id"]],
                "mechanism": "贴现率", "assessment": "影响未知", "limitations": "缺估值输入",
            }], "unresolved_questions": [], "invalidation_conditions": ["新披露"],
            "watch_plan": [{"item": "季度披露", "trigger": "披露发布", "reassess_on": "发布后"}],
            "reevaluation_conditions": ["新披露"],
            "confidence_rationale": "资料不足", "limitations": ["非组合建议"],
            "evidence_refs": ["ev-1"],
        }
        message = self.target / "invocation/final-message.json"
        self._write_model_proof(output)
        output["action"] = "BUY"
        self._write_model_proof(output)
        with self.assertRaises(ValueError):
            finalize_predecision_cio_research(REPO, self.target)
        self.assertFalse((self.target / "report.md").exists())
        del output["action"]
        output["account_fit"] = "当前账户适配良好"
        self._write_model_proof(output)
        with self.assertRaises(ValueError):
            finalize_predecision_cio_research(REPO, self.target)
        output["account_fit"] = "当前账户适配未评估"
        self._write_model_proof(output)
        environment_ref = "invocation/environment-manifest.json"
        environment = json.loads((self.target / environment_ref).read_text())
        command = environment["command"]
        command[command.index("-C") + 1] = str(REPO / "product")
        _write(self.target, environment_ref, environment)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_SOURCE_READONLY_COMMAND_INVALID"):
            finalize_predecision_cio_research(REPO, self.target)
        self._write_model_proof(output)
        result = finalize_predecision_cio_research(REPO, self.target)
        self.assertEqual(result["status"], "COMPLETED_RESEARCH_SYNTHESIS")
        process_ref = "invocation/process-result.json"
        with self.assertRaises(PredecisionCioStageError):
            check_predecision_cio_trace(REPO, self.target)
        process = {
            "run_id": "cio-1", "process_exit_code": 0, "timed_out": False,
            "failure_code": None, "stage_status": "COMPLETED_RESEARCH_SYNTHESIS",
            "source_integrity_unchanged": True,
        }
        _write(self.target, process_ref, process)
        self.assertEqual(check_predecision_cio_trace(REPO, self.target)["status"], "PASSED")
        invalid_results = (
            {"run_id": "different-run"}, {"process_exit_code": 1},
            {"process_exit_code": True}, {"timed_out": True},
            {"timed_out": "false"}, {"failure_code": "CIO_CODEX_PROCESS_FAILED"},
            {"stage_status": "FAILED_VALIDATION"},
            {"source_integrity_unchanged": False},
            {"source_integrity_unchanged": 1},
        )
        for invalid in invalid_results:
            with self.subTest(invalid=invalid):
                _write(self.target, process_ref, {**process, **invalid})
                with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PROCESS_RESULT_INVALID"):
                    check_predecision_cio_trace(REPO, self.target)
        for missing in process:
            with self.subTest(missing=missing):
                _write(self.target, process_ref, {
                    key: value for key, value in process.items() if key != missing
                })
                with self.assertRaises(PredecisionCioStageError):
                    check_predecision_cio_trace(REPO, self.target)
        _write(self.target, process_ref, process)
        published = json.loads((self.target / "cio-research-synthesis.json").read_text())
        self.assertNotEqual(published["generated_at"], output["generated_at"])
        self.assertEqual(
            json.loads((self.target / "decision_trace.json").read_text())["generated_at"],
            published["generated_at"],
        )
        self.assertFalse((self.target / "decision.json").exists())
        self.assertIn("Risk：未运行", (self.target / "report.md").read_text())
        published["generated_at"] = output["generated_at"]
        _write(self.target, "cio-research-synthesis.json", published)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_RESEARCH_TRACE_INVALID"):
            check_predecision_cio_trace(REPO, self.target)

if __name__ == "__main__":
    unittest.main()
