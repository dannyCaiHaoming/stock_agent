from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.research_consumption_audit import (
    build_research_consumption_audit, render_audit_summary,
)
from product.runtime.hashing import canonical_hash, file_hash


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class ResearchConsumptionAuditTests(unittest.TestCase):
    def test_empty_expected_dataset_and_invocation_scoped_indirect_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            facts = [
                {
                    "evidence_id": "ev-parent", "semantic_field": "us-gaap.EarningsPerShareDiluted",
                    "source_id": "sec-companyfacts", "as_of": "2026-01-31T00:00:00Z",
                    "retrieved_at": "2026-02-01T00:00:00Z", "raw_content_hash": "a" * 64,
                    "metadata": {"period_start": "2025-02-01", "period_end": "2026-01-31"},
                    "parent_ids": [],
                },
                {
                    "evidence_id": "ev-derived", "semantic_field": "us-gaap.EarningsPerShareDiluted",
                    "source_id": "sec-derived", "as_of": "2026-01-31T00:00:00Z",
                    "retrieved_at": "2026-02-01T00:00:00Z", "raw_content_hash": "b" * 64,
                    "metadata": {}, "parent_ids": ["ev-parent"],
                },
                {
                    "evidence_id": "ev-unused", "semantic_field": "business_segments",
                    "source_id": "sec", "as_of": "2026-01-31T00:00:00Z",
                    "retrieved_at": "2026-02-01T00:00:00Z", "raw_content_hash": "f" * 64,
                    "metadata": {}, "parent_ids": [],
                },
                {
                    "evidence_id": "ev-unqueried", "semantic_field": "identity_profile",
                    "source_id": "sec", "as_of": "2026-01-31T00:00:00Z",
                    "retrieved_at": "2026-02-01T00:00:00Z", "raw_content_hash": "e" * 64,
                    "metadata": {}, "parent_ids": [],
                },
                {
                    "evidence_id": "ev-attachment", "semantic_field": "historical_close_price",
                    "source_id": "yahoo-daily", "as_of": "2026-01-31T00:00:00Z",
                    "retrieved_at": "2026-02-01T00:00:00Z", "raw_content_hash": "1" * 64,
                    "metadata": {}, "parent_ids": [],
                },
            ]
            write_json(run / "evidence/gate.json", {
                "run_id": "run-1", "decision_cutoff": "2026-02-02T00:00:00Z",
                "bundle_hash": "c" * 64, "allowed_evidence": facts, "excluded": [],
            })
            write_json(run / "audit/provider-coverage.json", {
                "providers": [{
                    "provider": "moomoo_sg",
                    "dataset_observations": [{
                        "dataset": "market_breadth", "status": "SOURCE_LIMITED",
                        "failure_code": "MOOMOO_OPEND_UNREACHABLE", "evidence_ids": [],
                    }],
                }],
            })
            events = [
                {"event_type": "mcp_tool_result", "invocation_id": "agent-one",
                 "tool": "fixture_evidence.query", "evidence_ids": ["ev-derived"]},
                {"event_type": "mcp_tool_result", "invocation_id": "agent-one",
                 "tool": "fixture_math.calculate", "calculation_id": "calc-1", "evidence_ids": ["ev-derived"]},
                {"event_type": "mcp_tool_result", "invocation_id": "agent-two",
                 "tool": "fixture_evidence.query", "evidence_ids": ["ev-unused"]},
            ]
            path = run / "events/mcp/events.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
            write_json(run / "research/reports/one/dimension-report.json", {
                "report_id": "report-one", "invocation_id": "agent-one",
                "capability": "FUNDAMENTAL_EVENT", "status": "COMPLETE",
                "report_hash": "d" * 64, "claims": [{"calculation_refs": ["calc-1"], "evidence_refs": []}],
            })
            write_json(run / "research/reports/two/dimension-report.json", {
                "report_id": "report-two", "invocation_id": "agent-two",
                "capability": "FUNDAMENTAL_EVENT", "status": "INSUFFICIENT_EVIDENCE",
                "report_hash": "e" * 64, "claims": [],
            })
            write_json(run / "research/reports/failed/dimension-report.json", {
                "report_id": "report-failed", "invocation_id": "agent-failed",
                "capability": "RESEARCH_REPORT", "status": "FAILED",
                "report_hash": "9" * 64, "claims": [],
            })
            write_json(run / "research/skeptic/reports/one/counter-thesis.json", {
                "invocation_id": "agent-skeptic", "status": "LOW_CONFIDENCE",
                "challenges": [],
            })
            package = {
                "run_id": "run-1", "decision_cutoff": "2026-02-02T00:00:00Z",
                "gate_hash": "c" * 64, "package_hash": "p" * 64,
            }
            write_json(run / "research/skeptic/pre-decision-research-package.json", package)
            cio_run = run / "cio"
            write_json(cio_run / "run_manifest.json", {
                "run_id": "cio-1", "source_run_dir": str(run.resolve()),
                "source_run_id": "run-1", "source_package_hash": "p" * 64,
            })
            write_json(cio_run / "predecision-cio-request.json", {
                "run_id": "cio-1", "source_run_id": "run-1",
                "decision_cutoff": "2026-02-02T00:00:00Z", "source_package_hash": "p" * 64,
            })
            write_json(cio_run / "source-inputs/evidence/gate.json", json.loads(
                (run / "evidence/gate.json").read_text(encoding="utf-8"),
            ))
            write_json(cio_run / "source-inputs/research/skeptic/pre-decision-research-package.json", package)
            write_json(cio_run / "cio-research-synthesis.json", {
                "run_id": "cio-1", "status": "LOW_CONFIDENCE",
                "source_run_id": "run-1", "decision_cutoff": "2026-02-02T00:00:00Z",
                "source_package_hash": "p" * 64,
                "consumed_reports": [
                    {"report_id": "report-one"}, {"report_id": "report-failed"},
                    {"report_id": "skeptic-one", "invocation_id": "agent-skeptic"},
                ],
            })
            write_json(run / "research/precomputed/three/technical-calculation.json", {
                "schema_version": "technical-calculation/1.0.0",
                "evidence_fact_ids": ["ev-attachment"],
            })
            write_json(run / "research/reports/three/dimension-report.json", {
                "report_id": "report-three", "invocation_id": "agent-three",
                "capability": "TECHNICAL_STRUCTURE", "status": "COMPLETE",
                "report_hash": "2" * 64,
                "claims": [{"calculation_refs": ["calc.technical"], "evidence_refs": []}],
                "artifact_refs": ["research/precomputed/three/technical-calculation.json"],
            })
            audit = build_research_consumption_audit(run, cio_run=cio_run)
            parent = next(item for item in audit["rows"] if item["source_id"] == "sec-companyfacts")
            self.assertEqual(parent["indirect_refs_by_invocation"], {"agent-one": ["ev-parent"]})
            self.assertNotIn("agent-two", parent["delivered_by_invocation"])
            unused = next(item for item in audit["rows"] if item["sample_evidence_id"] == "ev-unused")
            self.assertEqual(unused["use_status"], "DELIVERED_UNREFERENCED")
            unqueried = next(item for item in audit["rows"] if item["sample_evidence_id"] == "ev-unqueried")
            self.assertEqual(unqueried["use_status"], "AVAILABLE_NOT_QUERIED")
            attachment = next(item for item in audit["rows"]
                              if item["sample_evidence_id"] == "ev-attachment")
            self.assertEqual(attachment["use_status"], "ATTACHMENT_PARENT_LINKED")
            self.assertEqual(attachment["attachment_parent_refs_by_invocation"], {
                "agent-three": ["ev-attachment"],
            })
            self.assertIn("核心资料项 us_cpi_all_items：NO_FROZEN_FACT", render_audit_summary(audit))
            self.assertIn("其中 FAILED 1 份", render_audit_summary(audit))
            self.assertEqual(audit["cio"]["consumed_report_statuses"], [
                {"report_id": "report-failed", "status": "FAILED"},
                {"report_id": "report-one", "status": "COMPLETE"},
                {"report_id": "skeptic-one", "status": "LOW_CONFIDENCE"},
            ])
            self.assertEqual(audit["source_binding"]["cio"], "VERIFIED")
            breadth = next(item for item in audit["coverage_items"]
                           if item["dataset"] == "market_breadth")
            self.assertEqual(breadth["source_status"], "SOURCE_LIMITED")
            missing_company_events = run / "company-without-events"
            missing_company_events.mkdir()
            with self.assertRaisesRegex(ValueError, "RESEARCH_AUDIT_COMPANY_BINDING_INVALID"):
                build_research_consumption_audit(run, company_run=missing_company_events)
            cio_manifest = cio_run / "run_manifest.json"
            write_json(cio_manifest, {
                "run_id": "cio-1", "source_run_dir": str(run.resolve()),
                "source_run_id": "wrong-run", "source_package_hash": "p" * 64,
            })
            with self.assertRaisesRegex(ValueError, "RESEARCH_AUDIT_CIO_BINDING_INVALID"):
                build_research_consumption_audit(run, cio_run=cio_run)

    def test_company_binding_checks_imported_report_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run, company = root / "main", root / "company"
            cutoff = "2026-02-02T00:00:00Z"
            write_json(run / "evidence/gate.json", {
                "run_id": "main-1", "decision_cutoff": cutoff,
                "bundle_hash": "m" * 64, "allowed_evidence": [], "excluded": [],
            })
            write_json(company / "run_manifest.json", {"run_id": "company-1"})
            write_json(company / "evidence/gate.json", {
                "run_id": "company-1", "decision_cutoff": cutoff,
                "bundle_hash": "s" * 64,
            })
            write_json(company / "research/execution-proof.json", {"run_id": "company-1"})
            report = {"report_id": "report-company", "invocation_id": "company-invocation",
                      "status": "LOW_CONFIDENCE"}
            report_hash = canonical_hash(report)
            source_report = company / "research/reports/one/equity-research.json"
            target_report = run / "research/imported-company-research/one/equity-research.json"
            write_json(source_report, report)
            write_json(target_report, report)
            write_json(run / "research/imported-company-research/import-manifest.json", {
                "source_run": str(company.resolve()), "source_run_id": "company-1",
                "target_decision_cutoff": cutoff,
                "source_manifest_file_hash": file_hash(company / "run_manifest.json"),
                "source_execution_proof_file_hash": file_hash(company / "research/execution-proof.json"),
                "reports": [{
                    "report_id": "report-company", "report_hash": report_hash,
                    "source_json_file_hash": file_hash(source_report),
                    "artifact_ref": "research/imported-company-research/one/equity-research.json",
                    "source_gate_hash": "s" * 64, "source_decision_cutoff": cutoff,
                    "source_run_id": "company-1",
                }],
            })
            audit = build_research_consumption_audit(run, company_run=company)
            self.assertEqual(audit["source_binding"]["company"], "VERIFIED")
            write_json(target_report, {**report, "status": "FAILED"})
            with self.assertRaisesRegex(ValueError, "RESEARCH_AUDIT_COMPANY_BINDING_INVALID"):
                build_research_consumption_audit(run, company_run=company)

    def test_missing_event_log_does_not_claim_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            write_json(run / "evidence/gate.json", {
                "run_id": "run-2", "decision_cutoff": "2026-02-02T00:00:00Z",
                "bundle_hash": "c" * 64,
                "allowed_evidence": [{
                    "evidence_id": "ev-one", "semantic_field": "financial_history",
                    "source_id": "sec", "as_of": "2026-01-31T00:00:00Z",
                    "retrieved_at": "2026-02-01T00:00:00Z", "metadata": {},
                }], "excluded": [],
            })
            audit = build_research_consumption_audit(run)
            self.assertEqual(audit["rows"][0]["use_status"], "NOT_VERIFIED")
            self.assertEqual(audit["event_file_presence"], {str(run.resolve()): False})


if __name__ == "__main__":
    unittest.main()
