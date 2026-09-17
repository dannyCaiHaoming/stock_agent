from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from product.runtime.hashing import canonical_hash

from product.council.multidimensional_research import (
    BUNDLE_CAPABILITIES,
    MultiDimensionalResearchError,
    finalize_holding_research_bundle,
    finalize_research_dimension_report,
    validate_holding_research_bundle,
    validate_research_dimension_report,
)
from product.runtime.multidimensional_stage import check_multidimensional_bundle_consumable


HASH_A = "a" * 64
HASH_B = "b" * 64
SECURITIES = ["US:AAPL", "US:MSFT"]
BINDINGS = {
    "handoff_id": "handoff-1",
    "handoff_hash": HASH_A,
    "portfolio_hash": HASH_B,
    "council_request_id": "request-1",
    "council_request_hash": "c" * 64,
    "decision_cutoff": "2026-09-14T20:00:00Z",
}
BUNDLE_BINDINGS = {key: value for key, value in BINDINGS.items() if key != "decision_cutoff"}


def _report(
    *,
    capability: str = "TECHNICAL_STRUCTURE",
    security_ids: list[str] | None = None,
    scope: str = "PER_SECURITY",
    status: str = "COMPLETE",
    evaluation_status: str = "PASS",
) -> dict:
    ids = list(security_ids or ["US:AAPL"])
    report = {
        "schema_version": "research-dimension-report/1.1.0",
        "report_id": f"report:{capability.lower()}:1",
        "run_id": "run-1",
        "invocation_id": "invocation-1",
        "capability": capability,
        "scope": scope,
        "security_ids": ids,
        "status": status,
        "sufficiency": "SUFFICIENT" if status == "COMPLETE" else "PARTIAL",
        "evaluation_status": evaluation_status,
        "bindings": copy.deepcopy(BINDINGS),
        "time_context": {
            "window_start": "2025-09-14T00:00:00Z",
            "window_end": "2026-09-14T00:00:00Z",
            "benchmark_id": "US:SPY",
            "price_adjustment": "ADJUSTED_CLOSE",
            "timezone": "America/New_York",
        },
        "execution": {
            "agent_name": (
                "runtime_company_analyst"
                if capability in {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT"}
                else "runtime_market_catalyst"
            ),
            "agent_version": "1.0.0",
            "skill_name": "technical-structure",
            "skill_version": "1.0.0",
            "skill_hash": "d" * 64,
            "model": "gpt-5.6-terra",
            "prompt_hash": "e" * 64,
            "input_refs": ["evidence:bundle:1"],
            "raw_output_hash": "f" * 64,
        },
        "summary": "相对基准和量价结构均已按冻结窗口分析。",
        "claims": [{
            "claim_id": "claim-1",
            "question": "相对基准表现如何？",
            "statement": "样本期内该证券相对基准表现较弱。",
            "kind": "INTERPRETATION",
            "evidence_refs": ["ev-price-1"],
            "research_claim_refs": [],
            "document_refs": [],
            "assumption_ids": [],
            "calculation_refs": ["calc-1"],
        }],
        "assumptions": [],
        "calculations": [{
            "calculation_id": "calc-1",
            "method": "total_return",
            "value": -0.12,
            "unit": "ratio",
            "input_evidence_refs": ["ev-price-1"],
            "artifact_ref": "calculations/technical.json",
        }],
        "documents": [],
        "research_relationships": [],
        "limitations": ["日线资料不能解释日内资金方向。"],
        "observation_conditions": [{
            "condition_id": "condition-1",
            "description": "后续相对强弱持续转正将推翻当前解释。",
            "claim_refs": ["claim-1"],
            "evidence_refs": ["ev-price-1"],
        }],
        "data_gaps": [],
        "artifact_refs": ["calculations/technical.json", "charts/technical.svg"],
    }
    return finalize_research_dimension_report(report)


def _bundle(report: dict) -> dict:
    coverage = []
    for security_id in SECURITIES:
        for capability in BUNDLE_CAPABILITIES:
            linked = capability == report["capability"] and security_id in report["security_ids"]
            coverage.append({
                "security_id": security_id,
                "capability": capability,
                "status": report["status"] if linked else "NOT_RESEARCHED",
                "report_id": report["report_id"] if linked else None,
                "gap_reason": None if linked else "该维度尚未执行。",
            })
    value = {
        "schema_version": "holding-research-bundle/1.1.0",
        "bundle_id": "bundle-1",
        "run_id": "run-1",
        "bindings": copy.deepcopy(BUNDLE_BINDINGS),
        "decision_cutoff": BINDINGS["decision_cutoff"],
        "common_stock_security_ids": list(SECURITIES),
        "report_refs": [{
            "report_id": report["report_id"],
            "report_hash": report["report_hash"],
            "report_type": "RESEARCH_DIMENSION_REPORT",
            "capability": report["capability"],
            "security_ids": list(report["security_ids"]),
            "artifact_ref": "reports/macro.json",
        }],
        "coverage": coverage,
        "consumability": "STRUCTURALLY_CONSUMABLE",
        "package_provenance": {
            "base_run_id": "run-1",
            "base_bundle_hash": None,
            "base_gate_hash": "9" * 64,
            "company_research_imports": [],
            "incorporated_supplements": [],
            "excluded_supplements": [],
        },
        "unresolved_cross_dimension_questions": [],
        "no_unresolved_reason": "测试包没有额外待反证问题。",
        "summary": "当前研究包保留已完成维度及其他维度缺口。",
        "artifact_refs": ["reports/macro.json"],
    }
    return finalize_holding_research_bundle(value)


def _equity_report() -> dict:
    return {
        "report_id": "equity-report-1",
        "status": "COMPLETE",
        "security": {"security_id": "US:AAPL"},
        "claims": [{"claim_id": "equity-claim-1"}],
    }


class ResearchDimensionContractTests(unittest.TestCase):
    def test_valid_report_passes(self) -> None:
        report = _report()
        refs = validate_research_dimension_report(
            report,
            expected_bindings=BINDINGS,
            allowed_security_ids=SECURITIES,
            allowed_evidence_ids=["ev-price-1"],
        )
        self.assertEqual(refs, {"ev-price-1"})

    def test_dangling_evidence_fails_closed(self) -> None:
        report = _report()
        report["claims"][0]["evidence_refs"] = ["ev-missing"]
        report = finalize_research_dimension_report(report)
        with self.assertRaisesRegex(MultiDimensionalResearchError, "EVIDENCE_CLOSURE_FAILED"):
            validate_research_dimension_report(
                report,
                expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES,
                allowed_evidence_ids=["ev-price-1"],
            )

    def test_wrong_holding_binding_fails(self) -> None:
        report = _report(security_ids=["US:NVDA"])
        with self.assertRaisesRegex(MultiDimensionalResearchError, "SECURITY_BINDING_INVALID"):
            validate_research_dimension_report(
                report,
                expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES,
                allowed_evidence_ids=["ev-price-1"],
            )

    def test_investment_action_is_forbidden(self) -> None:
        report = _report()
        report["claims"][0]["action"] = "BUY"
        report = finalize_research_dimension_report(report)
        with self.assertRaisesRegex(MultiDimensionalResearchError, "ACTION_FIELD_FORBIDDEN"):
            validate_research_dimension_report(
                report,
                expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES,
                allowed_evidence_ids=["ev-price-1"],
            )

    def test_source_limited_requires_matching_evaluation_state(self) -> None:
        report = _report(status="SOURCE_LIMITED", evaluation_status="PASS")
        with self.assertRaisesRegex(MultiDimensionalResearchError, "SOURCE_LIMITED_STATE_INVALID"):
            validate_research_dimension_report(
                report,
                expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES,
                allowed_evidence_ids=["ev-price-1"],
            )

    def test_research_report_requires_verified_document_and_closed_relationships(self) -> None:
        report = _report(capability="RESEARCH_REPORT")
        report["documents"] = [{
            "document_id": "document-1",
            "source_id": "issuer.example.com",
            "title": "季度股东信",
            "authors": ["Issuer"],
            "institution": "Example Inc.",
            "material_type": "ISSUER_MATERIAL",
            "source_url": "https://issuer.example.com/letter",
            "original_source_url": None,
            "published_at": "2026-09-10T20:00:00Z",
            "as_of": "2026-09-10T20:00:00Z",
            "retrieved_at": "2026-09-11T01:00:00Z",
            "body_hash": "1" * 64,
            "locations": ["第 2 页"],
            "parse_scope": "正文第 1-3 页",
            "duplicate_of": None,
            "revision_of": None,
            "interest_disclosure": {
                "status": "DECLARED",
                "statement": "公司自行发布。",
                "location": "封面",
            },
            "verification_status": "BODY_VERIFIED",
        }]
        report["claims"][0]["document_refs"] = ["document-1"]
        report["research_relationships"] = [{
            "relationship_id": "relationship-1",
            "document_id": "document-1",
            "target_claim_refs": ["upstream-claim-1"],
            "effect": "SUPPORT",
            "rationale": "股东信中的分部说明支持上游经营驱动主张。",
            "resulting_claim_refs": ["claim-1"],
        }]
        report = finalize_research_dimension_report(report)
        validate_research_dimension_report(
            report,
            expected_bindings=BINDINGS,
            allowed_security_ids=SECURITIES,
            allowed_evidence_ids=["ev-price-1"],
            known_research_claim_ids=["upstream-claim-1"],
        )

        invalid = copy.deepcopy(report)
        invalid["research_relationships"][0]["target_claim_refs"] = ["missing-claim"]
        invalid = finalize_research_dimension_report(invalid)
        with self.assertRaisesRegex(MultiDimensionalResearchError, "RELATIONSHIP_TARGET_DANGLING"):
            validate_research_dimension_report(
                invalid,
                expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES,
                allowed_evidence_ids=["ev-price-1"],
                known_research_claim_ids=["upstream-claim-1"],
            )

    def test_research_report_complete_rejects_lead_only_document(self) -> None:
        report = _report(capability="RESEARCH_REPORT")
        report["documents"] = [{
            "document_id": "lead-1", "source_id": "search.example.com",
            "title": "搜索线索", "authors": [], "institution": None,
            "material_type": "SEARCH_LEAD", "source_url": "https://search.example.com/lead",
            "original_source_url": None, "published_at": "2026-09-10T20:00:00Z",
            "as_of": "2026-09-10T20:00:00Z", "retrieved_at": "2026-09-11T01:00:00Z",
            "body_hash": None, "locations": [], "parse_scope": "仅搜索摘要",
            "duplicate_of": None, "revision_of": None,
            "interest_disclosure": {"status": "UNKNOWN", "statement": None, "location": None},
            "verification_status": "LEAD_ONLY",
        }]
        report["claims"][0]["document_refs"] = ["lead-1"]
        report = finalize_research_dimension_report(report)
        with self.assertRaisesRegex(MultiDimensionalResearchError, "VERIFIED_DOCUMENT_REQUIRED"):
            validate_research_dimension_report(
                report,
                expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES,
                allowed_evidence_ids=["ev-price-1"],
            )

    def test_research_report_rejects_document_not_in_frozen_allowed_set(self) -> None:
        report = _report(capability="RESEARCH_REPORT")
        document = {
            "document_id": "document-invented", "source_id": "example.com",
            "title": "未冻结材料", "authors": ["Author"], "institution": None,
            "material_type": "INDEPENDENT_RESEARCH", "source_url": "https://example.com/report",
            "original_source_url": None, "published_at": "2026-09-10T20:00:00Z",
            "as_of": "2026-09-10T20:00:00Z", "retrieved_at": "2026-09-11T01:00:00Z",
            "body_hash": "1" * 64, "locations": ["Results"], "parse_scope": "正文",
            "duplicate_of": None, "revision_of": None,
            "interest_disclosure": {"status": "UNKNOWN", "statement": None, "location": None},
            "verification_status": "BODY_VERIFIED",
        }
        report["documents"] = [document]
        report["claims"][0]["document_refs"] = [document["document_id"]]
        report = finalize_research_dimension_report(report)
        with self.assertRaisesRegex(MultiDimensionalResearchError, "DOCUMENT_NOT_ALLOWED"):
            validate_research_dimension_report(
                report,
                expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES,
                allowed_evidence_ids=["ev-price-1"],
                allowed_documents=[],
            )

    def test_shared_report_can_cover_multiple_holdings(self) -> None:
        report = _report(
            capability="MACRO_MARKET", security_ids=SECURITIES, scope="SHARED_MARKET"
        )
        validate_research_dimension_report(
            report,
            expected_bindings=BINDINGS,
            allowed_security_ids=SECURITIES,
            allowed_evidence_ids=["ev-price-1"],
        )
        bundle = _bundle(report)
        validate_holding_research_bundle(
            bundle,
            expected_bindings=BUNDLE_BINDINGS,
            expected_common_stock_ids=SECURITIES,
            dimension_reports=[report],
        )

    def test_bundle_accepts_a_bound_equity_research_report(self) -> None:
        report = _report()
        equity = _equity_report()
        bundle = _bundle(report)
        bundle["report_refs"].append({
            "report_id": equity["report_id"],
            "report_hash": canonical_hash(equity),
            "report_type": "EQUITY_RESEARCH_REPORT",
            "capability": "COMPANY_RESEARCH",
            "security_ids": ["US:AAPL"],
            "artifact_ref": "reports/equity.json",
        })
        company = next(
            item for item in bundle["coverage"]
            if item["security_id"] == "US:AAPL" and item["capability"] == "COMPANY_RESEARCH"
        )
        company.update(status="COMPLETE", report_id=equity["report_id"], gap_reason=None)
        bundle["package_provenance"]["company_research_imports"].append({
            "source_run_id": "company-run",
            "source_decision_cutoff": BINDINGS["decision_cutoff"],
            "report_id": equity["report_id"],
            "report_hash": canonical_hash(equity),
            "compatibility_status": "REVALIDATED",
        })
        bundle["artifact_refs"].append("reports/equity.json")
        bundle = finalize_holding_research_bundle(bundle)
        validate_holding_research_bundle(
            bundle,
            expected_bindings=BUNDLE_BINDINGS,
            expected_common_stock_ids=SECURITIES,
            dimension_reports=[report],
            equity_reports=[equity],
        )

    def test_consumer_check_parses_structured_bundle_without_downstream_model(self) -> None:
        report = _report()
        bundle = _bundle(report)
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            (run / "research").mkdir()
            (run / "evidence").mkdir()
            (run / "reports").mkdir()
            (run / "run_manifest.json").write_text(json.dumps({
                "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
                "run_id": "run-1",
            }))
            (run / "research/holding-research-bundle.json").write_text(json.dumps(bundle))
            (run / "reports/macro.json").write_text(json.dumps(report))
            (run / "evidence/gate.json").write_text(json.dumps({
                "bundle_hash": "a" * 64,
                "allowed_evidence_ids": ["ev-price-1"],
            }))
            proof = check_multidimensional_bundle_consumable(Path(temp), run)
            self.assertEqual(proof["status"], "PASSED")
            self.assertEqual(proof["structural_status"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(proof["downstream_status"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(proof["report_inventory"][0]["claim_ids"], ["claim-1"])
            self.assertEqual(proof["report_inventory"][0]["evidence_ids"], ["ev-price-1"])
            self.assertEqual(proof["downstream_models_started"], [])
            self.assertTrue((run / "research/consumption-proof.json").is_file())

    def test_downstream_ready_rejects_missing_company_research(self) -> None:
        report = _report()
        bundle = _bundle(report)
        bundle["consumability"] = "DOWNSTREAM_READY"
        bundle = finalize_holding_research_bundle(bundle)
        with self.assertRaisesRegex(
            MultiDimensionalResearchError, "COMPANY_RESEARCH_NOT_READY"
        ):
            validate_holding_research_bundle(
                bundle,
                expected_bindings=BUNDLE_BINDINGS,
                expected_common_stock_ids=SECURITIES,
                dimension_reports=[report],
            )

    def test_empty_unresolved_questions_require_reason(self) -> None:
        report = _report()
        bundle = _bundle(report)
        bundle["no_unresolved_reason"] = None
        bundle = finalize_holding_research_bundle(bundle)
        with self.assertRaisesRegex(
            MultiDimensionalResearchError, "UNRESOLVED_REASON"
        ):
            validate_holding_research_bundle(
                bundle,
                expected_bindings=BUNDLE_BINDINGS,
                expected_common_stock_ids=SECURITIES,
                dimension_reports=[report],
            )

    def test_unresolved_question_rejects_dangling_report(self) -> None:
        report = _report()
        bundle = _bundle(report)
        bundle["unresolved_cross_dimension_questions"] = [{
            "question_id": "question-1",
            "security_ids": ["US:AAPL"],
            "capabilities": ["TECHNICAL_STRUCTURE"],
            "question": "什么事实会推翻当前相对强弱解释？",
            "report_refs": ["missing-report"],
            "claim_refs": ["claim-1"],
        }]
        bundle["no_unresolved_reason"] = None
        bundle = finalize_holding_research_bundle(bundle)
        with self.assertRaisesRegex(
            MultiDimensionalResearchError, "QUESTION_REPORT_DANGLING"
        ):
            validate_holding_research_bundle(
                bundle,
                expected_bindings=BUNDLE_BINDINGS,
                expected_common_stock_ids=SECURITIES,
                dimension_reports=[report],
            )

    def test_configuration_block_cannot_be_relabelled_as_source_limited(self) -> None:
        from product.council.multidimensional_research import envelope_research_dimension_draft

        task = {
            "run_id": "run-1", "invocation_id": "invocation-1",
            "task_id": "research-report-aapl", "agent": "runtime_company_analyst",
            "capability": "RESEARCH_REPORT", "scope": "PER_SECURITY",
            "security_ids": ["US:AAPL"],
            "time_context": _report(capability="RESEARCH_REPORT")["time_context"],
            "material_preparation": {"status": "BLOCKED_CONFIGURATION"},
        }
        invocation = {
            "run_id": "run-1", "invocation_id": "invocation-1",
            "model": "gpt-5.6-terra", "prompt_hash": "e" * 64, "input_refs": [],
            "skill": {"name": "research-report-analysis", "version": "1.2.0", "content_hash": "d" * 64},
            "agent_binding": {"name": "runtime_company_analyst", "version": "3.0.20"},
        }
        draft = {
            "run_id": "run-1", "invocation_id": "invocation-1", "agent": "runtime_company_analyst",
            "status": "SOURCE_LIMITED", "sufficiency": "INSUFFICIENT",
            "evaluation_status": "SOURCE_LIMITED", "summary": "错误地写成来源受限。",
            "claims": [], "assumptions": [], "calculations": [], "documents": [],
            "research_relationships": [], "limitations": ["缺配置"],
            "observation_conditions": [],
            "data_gaps": [{"gap_id": "gap-1", "reason_code": "API_KEY_REQUIRED", "description": "缺少配置", "impact": "无法读取正文"}],
            "artifact_refs": [],
        }
        with self.assertRaisesRegex(MultiDimensionalResearchError, "CONFIGURATION_BLOCK_STATE_INVALID"):
            envelope_research_dimension_draft(
                draft, task=task, invocation=invocation, expected_bindings=BINDINGS,
                allowed_security_ids=SECURITIES, allowed_evidence_ids=[], allowed_documents=[],
            )

    def test_bundle_requires_every_security_capability_pair(self) -> None:
        report = _report()
        bundle = _bundle(report)
        bundle["coverage"].pop()
        bundle = finalize_holding_research_bundle(bundle)
        with self.assertRaisesRegex(MultiDimensionalResearchError, "COVERAGE_INVALID"):
            validate_holding_research_bundle(
                bundle,
                expected_bindings=BUNDLE_BINDINGS,
                expected_common_stock_ids=SECURITIES,
                dimension_reports=[report],
            )

    def test_bundle_rejects_dangling_report_reference(self) -> None:
        report = _report()
        bundle = _bundle(report)
        bundle["coverage"][1]["report_id"] = "missing-report"
        bundle["coverage"][1]["gap_reason"] = None
        bundle = finalize_holding_research_bundle(bundle)
        with self.assertRaisesRegex(MultiDimensionalResearchError, "REPORT_DANGLING"):
            validate_holding_research_bundle(
                bundle,
                expected_bindings=BUNDLE_BINDINGS,
                expected_common_stock_ids=SECURITIES,
                dimension_reports=[report],
            )


if __name__ == "__main__":
    unittest.main()
