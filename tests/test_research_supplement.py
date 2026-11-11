from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.mcp.live.research_supplement import (
    BACKGROUND_GROUPS,
    build_capability,
    build_capture_batch,
    build_company_background_snapshot,
    assemble_company_background,
    build_research_supplement_package,
    build_supplement_fact,
    load_source_plan,
    render_company_background_markdown,
    select_dataset_source,
    normalize_sec_guidance_candidate,
    normalize_sec_financial_history,
    normalize_sec_company_profile,
    compare_actual_to_expectation,
    validate_capture_batch,
    validate_company_background_snapshot,
    validate_source_plan,
)
from product.mcp.provenance import content_hash


NOW = "2026-09-15T12:00:00Z"
SECURITY = "US:COMMON_STOCK:AAPL"


def group_set(*, identity_id: str | None = None) -> dict:
    groups = {
        name: {
            "status": "UNKNOWN",
            "evidence_ids": [],
            "gaps": ["尚无可验证 Evidence"],
            "limitations": [],
        }
        for name in BACKGROUND_GROUPS
    }
    if identity_id is not None:
        groups["identity_profile"] = {
            "status": "COVERED",
            "evidence_ids": [identity_id],
            "gaps": [],
            "limitations": [],
        }
    return groups


def identity_fact(batch_id="batch-1"):
    return build_supplement_fact(
        security_id=SECURITY,
        dataset="identity_profile",
        semantic_field="legal_name",
        value="Apple Inc.",
        source_id="sec-submissions:0000320193",
        source_family="sec",
        source_locator="https://data.sec.gov/submissions/CIK0000320193.json",
        source_version="sec-submissions/1.0.0",
        as_of="2026-09-14T00:00:00Z",
        published_at="2026-09-14T08:00:00Z",
        retrieved_at="2026-09-15T10:00:00Z",
        raw_content_hash="a" * 64,
        batch_id=batch_id,
    )


class SourcePlanTests(unittest.TestCase):
    def test_money_flow_has_no_fallback_and_selection_is_single_source(self):
        plan = load_source_plan()
        route = next(item for item in plan["datasets"] if item["dataset"] == "vendor_money_flow")
        self.assertEqual(route["primary"], "moomoo_sg")

    def test_unimplemented_relationship_and_guidance_fallbacks_are_not_claimed(self):
        plan = load_source_plan()
        routes = {item["dataset"]: item for item in plan["datasets"]}
        route = routes["vendor_money_flow"]
        self.assertIsNone(routes["relationships"]["fallback"])
        self.assertIsNone(routes["earnings_guidance"]["fallback"])
        self.assertEqual(routes["options_snapshot"]["primary"], "yahoo")
        self.assertEqual(routes["options_snapshot"]["fallback"], "moomoo_sg")
        self.assertIsNone(route["fallback"])
        selected = select_dataset_source(
            plan,
            dataset="options_snapshot",
            attempts=[
                {"source": "yahoo", "status": "SOURCE_LIMITED"},
                {"source": "moomoo_sg", "status": "AVAILABLE"},
            ],
        )
        self.assertEqual(selected["selected_source"], "moomoo_sg")
        with self.assertRaisesRegex(ValueError, "ATTEMPT_COUNT"):
            select_dataset_source(
                plan,
                dataset="vendor_money_flow",
                attempts=[
                    {"source": "moomoo_sg", "status": "FAILED"},
                    {"source": "yahoo", "status": "AVAILABLE"},
                ],
            )

    def test_cross_region_or_two_fallback_plan_is_rejected(self):
        plan = load_source_plan()
        broken = deepcopy(plan)
        broken["datasets"][0]["fallback"] = "futu_cn"
        with self.assertRaisesRegex(ValueError, "FALLBACK_INVALID"):
            validate_source_plan(broken)
        broken = deepcopy(plan)
        broken["datasets"][0]["max_fallback_attempts"] = 2
        with self.assertRaisesRegex(ValueError, "FALLBACK_BUDGET_INVALID"):
            validate_source_plan(broken)

    def test_assembly_rejects_fallback_after_primary_success(self):
        with self.assertRaisesRegex(ValueError, "FALLBACK_AFTER_SUCCESS"):
            assemble_company_background(
                snapshot_id="bad-fallback", batch_id="batch-bad",
                security_id=SECURITY, ticker="AAPL",
                decision_cutoff=NOW, created_at=NOW,
                dataset_results=[{
                    "source": "sec", "dataset": "financial_history",
                    "status": "AVAILABLE", "failure_code": None,
                    "evidence": [], "gaps": [], "limitations": [],
                }, {
                    "source": "yahoo", "dataset": "financial_history",
                    "status": "AVAILABLE", "failure_code": None,
                    "evidence": [], "gaps": [], "limitations": [],
                }],
            )

    def test_capability_batch_keeps_source_failures_independent(self):
        sec = build_capability(
            source="sec", region="US", security_id=SECURITY, dataset="financial_history",
            status="AVAILABLE", fields=["revenue"], endpoint_version="sec-xbrl/1.0.0",
            checked_at=NOW, as_of="2026-09-14T00:00:00Z", attempt_count=1,
            limitations=[], evidence_ids=["ev-sec"], raw_content_hashes=["a" * 64],
        )
        moomoo = build_capability(
            source="moomoo_sg", region="SG", security_id=SECURITY,
            dataset="vendor_money_flow", status="BLOCKED_CONFIGURATION", fields=[],
            endpoint_version=None, checked_at=NOW, as_of="2026-09-14T00:00:00Z",
            attempt_count=1, limitations=["会话引用尚未提供"],
            failure_code="MOOMOO_SG_SESSION_REFERENCE_MISSING",
        )
        batch = build_capture_batch(
            batch_id="batch-1", security_id=SECURITY,
            decision_cutoff=NOW, created_at=NOW, capabilities=[sec, moomoo],
            source_selections=[{
                "dataset": "financial_history", "primary": "sec", "fallback": "yahoo",
                "selected_source": "sec", "fallback_reason": None,
                "supplemental_sources_used": [],
                "attempts": [{"source": "sec", "status": "AVAILABLE", "failure_code": None}],
            }, {
                "dataset": "vendor_money_flow", "primary": "moomoo_sg", "fallback": None,
                "selected_source": None, "fallback_reason": None,
                "supplemental_sources_used": [],
                "attempts": [{
                    "source": "moomoo_sg", "status": "BLOCKED_CONFIGURATION",
                    "failure_code": "MOOMOO_SG_SESSION_REFERENCE_MISSING",
                }],
            }],
        )
        self.assertEqual([item["status"] for item in batch["capabilities"]], ["AVAILABLE", "BLOCKED_CONFIGURATION"])

        forged = deepcopy(batch)
        forged["source_selections"][0]["primary"] = "yahoo"
        forged["batch_hash"] = content_hash({
            key: item for key, item in forged.items() if key != "batch_hash"
        })
        with self.assertRaisesRegex(ValueError, "ROUTE_MISMATCH"):
            validate_capture_batch(forged)


class CompanyBackgroundTests(unittest.TestCase):
    def test_yahoo_partial_options_accepts_same_contract_opend_field_supplement(self):
        facts = [build_supplement_fact(
            security_id=SECURITY, dataset="options_snapshot",
            semantic_field=f"option_contract:{source}",
            value={"contract_symbol": "AAPL261218C00100000", "source": source},
            source_id=f"{source}-options", source_family=source,
            source_locator=f"synthetic:{source}", source_version="synthetic/1",
            as_of=NOW, published_at=NOW, retrieved_at=NOW,
            raw_content_hash=("d" if source == "yahoo" else "e") * 64,
        ) for source in ("yahoo", "moomoo_sg")]
        assembled = assemble_company_background(
            snapshot_id="option-field-supplement", batch_id="option-batch",
            security_id=SECURITY, ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
            dataset_results=[
                {"source": source, "dataset": "options_snapshot",
                 "status": "PARTIAL" if source == "yahoo" else "AVAILABLE",
                 "failure_code": None, "evidence": [fact], "gaps": [], "limitations": []}
                for source, fact in zip(("yahoo", "moomoo_sg"), facts)
            ],
        )
        selection = next(item for item in assembled["source_selections"]
                         if item["dataset"] == "options_snapshot")
        self.assertEqual(selection["selected_source"], "yahoo")
        self.assertEqual(selection["supplemental_sources_used"], ["moomoo_sg"])
        self.assertEqual({fact["source_family"] for fact in assembled["extra_evidence"]},
                         {"yahoo", "moomoo_sg"})

    def test_sec_profile_preserves_legal_identity_and_current_mapping_boundary(self):
        result = normalize_sec_company_profile({
            "cik": "0000320193", "ticker": "AAPL", "issuer_name": "Apple Inc.",
            "exchange": "XNAS", "source_id": "sec-ticker-map",
            "source_locator": "https://www.sec.gov/files/company_tickers_exchange.json",
            "as_of": NOW, "retrieved_at": NOW, "raw_content_hash": "a" * 64,
            "identity_version": "us-equity-identity/1.0.0",
        }, security_id=SECURITY)
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["legal_name"], "Apple Inc.")
        self.assertIn("不是历史", " ".join(fact["limitations"]))

    def test_sec_financial_history_preserves_accession_and_raw_parent(self):
        live_fact = {
            "schema_version": "live-fact/1.0.0", "evidence_id": "ev-sec-parent",
            "security_id": SECURITY, "semantic_field": "us-gaap.Revenues",
            "value": "1000", "unit": "USD", "currency": "USD",
            "source_id": "sec-companyfacts-0000320193", "source_type": "sec",
            "source_locator": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            "source_version": "sec-edgar/1", "as_of": "2025-09-27T00:00:00Z",
            "published_at": "2025-10-31T10:01:26Z", "published_at_policy": "acceptance",
            "retrieved_at": NOW, "raw_content_hash": "f" * 64,
            "kind": "financial", "usage": "current", "parent_ids": [], "parent_hashes": [],
            "metadata": {
                "taxonomy": "us-gaap", "tag": "Revenues", "form": "10-K",
                "accession": "0000320193-25-000079", "period_start": "2024-09-29",
                "period_end": "2025-09-27", "context_type": "duration",
                "fiscal_year": 2025, "fiscal_period": "FY",
            },
        }
        normalized = normalize_sec_financial_history([live_fact], security_id=SECURITY)
        fact = normalized["evidence"][0]
        self.assertEqual(fact["dataset"], "financial_history")
        self.assertEqual(fact["value"]["accession"], "0000320193-25-000079")
        self.assertEqual(fact["value"]["parent_evidence_id"], "ev-sec-parent")
        self.assertEqual(fact["raw_content_hash"], "f" * 64)

    def test_profile_classification_conflicts_are_kept_by_source(self):
        facts = [
            build_supplement_fact(
                security_id=SECURITY, dataset="identity_profile", semantic_field="provider_profile",
                value={"industry": industry, "classification_system": system},
                source_id=f"{source}-profile", source_family=source,
                source_locator=f"https://{source}.example/profile", source_version="synthetic/1",
                as_of=NOW, published_at=NOW, retrieved_at=NOW,
                raw_content_hash=letter * 64,
                limitations=["当前快照，不是历史分类"],
                batch_id="batch-1",
            )
            for source, industry, system, letter in (
                ("yahoo", "Consumer Electronics", "YAHOO", "a"),
                ("moomoo_sg", "Technology Hardware", "MOOMOO_VENDOR", "b"),
            )
        ]
        groups = group_set()
        groups["identity_profile"] = {
            "status": "PARTIAL", "evidence_ids": [item["evidence_id"] for item in facts],
            "gaps": ["分类冲突待研究层解释"], "limitations": [],
        }
        snapshot = build_company_background_snapshot(
            snapshot_id="profile-conflict", batch_id="batch-1", security_id=SECURITY,
            ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
            evidence=facts, groups=groups,
        )
        self.assertEqual(
            {item["source_family"] for item in snapshot["evidence"]}, {"yahoo", "moomoo_sg"}
        )
        self.assertEqual(snapshot["status"], "PARTIAL")

    def test_sec_guidance_remains_candidate_and_expectation_comparison_is_strict(self):
        guidance = normalize_sec_guidance_candidate({
            "evidence_id": "sec-text-1", "section": "earnings_release",
            "text": "Issuer expects revenue between 10 and 12.",
            "source_id": "sec-filing", "source_locator": "https://www.sec.gov/filing",
            "as_of": "2026-09-10T00:00:00Z", "published_at": "2026-09-10T20:00:00Z",
            "retrieved_at": NOW, "raw_content_hash": "c" * 64, "form": "8-K",
            "accession": "sample", "raw_character_spans": [[0, 44]], "truncated": False,
            "parser_version": "sec-sections/test",
        }, security_id=SECURITY)["evidence"][0]
        self.assertEqual(guidance["value"]["claim_status"], "CANDIDATE_REQUIRES_EVIDENCE_REVIEW")
        self.assertIn("不得作为 SEC 实际", " ".join(guidance["limitations"]))

        actual = dict(identity_fact(), evidence_id="actual", value={
            "fiscal_period": "2026-Q4", "metric": "EPS", "accounting_basis": "GAAP", "amount": "-0.4",
        }, published_at="2026-11-01T20:00:00Z")
        expectation = dict(identity_fact(), evidence_id="expectation", value={
            "fiscal_period": "2026-Q4", "metric": "EPS", "accounting_basis": "GAAP",
            "average": "-0.5", "vintage_at": "2026-10-01T00:00:00Z",
        })
        comparison = compare_actual_to_expectation(
            actual=actual, expectation=expectation, calculated_at="2026-11-02T00:00:00Z"
        )
        self.assertIsNone(comparison["percent_difference"])
        self.assertEqual(comparison["percent_unavailable_reason"], "NON_POSITIVE_EXPECTATION_BASE")
        missing_vintage = deepcopy(expectation)
        missing_vintage["value"]["vintage_at"] = None
        with self.assertRaisesRegex(ValueError, "VINTAGE_UNKNOWN"):
            compare_actual_to_expectation(
                actual=actual, expectation=missing_vintage, calculated_at="2026-11-02T00:00:00Z"
            )
        wrong_period = deepcopy(expectation)
        wrong_period["value"]["fiscal_period"] = "2027-Q1"
        with self.assertRaisesRegex(ValueError, "BASIS_MISMATCH"):
            compare_actual_to_expectation(
                actual=actual, expectation=wrong_period, calculated_at="2026-11-02T00:00:00Z"
            )

    def test_snapshot_requires_identity_and_closes_all_references(self):
        fact = identity_fact()
        snapshot = build_company_background_snapshot(
            snapshot_id="background-1", batch_id="batch-1", security_id=SECURITY,
            ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
            evidence=[fact], groups=group_set(identity_id=fact["evidence_id"]),
        )
        self.assertEqual(snapshot["status"], "PARTIAL")
        markdown = render_company_background_markdown(snapshot)
        self.assertIn("身份与公司档案", markdown)
        self.assertIn("INSUFFICIENT", render_company_background_markdown(
            build_company_background_snapshot(
                snapshot_id="background-empty", batch_id="batch-1", security_id=SECURITY,
                ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
                evidence=[], groups=group_set(),
            )
        ))

        dangling_groups = group_set(identity_id="ev-missing")
        with self.assertRaisesRegex(ValueError, "DANGLING_REFERENCE"):
            build_company_background_snapshot(
                snapshot_id="background-bad", batch_id="batch-1", security_id=SECURITY,
                ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
                evidence=[], groups=dangling_groups,
            )

    def test_wrong_security_or_future_fact_fails_closed(self):
        fact = identity_fact()
        wrong = deepcopy(fact)
        wrong["security_id"] = "US:COMMON_STOCK:MSFT"
        with self.assertRaisesRegex(ValueError, "SECURITY_MISMATCH"):
            build_company_background_snapshot(
                snapshot_id="background-wrong", batch_id="batch-1", security_id=SECURITY,
                ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
                evidence=[wrong], groups=group_set(identity_id=wrong["evidence_id"]),
            )
        future = deepcopy(fact)
        future["retrieved_at"] = "2026-09-16T10:00:00Z"
        with self.assertRaisesRegex(ValueError, "FUTURE_EVIDENCE"):
            build_company_background_snapshot(
                snapshot_id="background-future", batch_id="batch-1", security_id=SECURITY,
                ticker="AAPL", decision_cutoff=NOW, created_at="2026-09-16T10:00:00Z",
                evidence=[future], groups=group_set(identity_id=future["evidence_id"]),
            )


if __name__ == "__main__":
    unittest.main()
