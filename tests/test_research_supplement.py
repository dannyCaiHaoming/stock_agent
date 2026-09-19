from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

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
from product.runtime.common_stock_data import attach_research_supplement, merge_research_supplement_evidence
from product.runtime.fixture_mcp import ToolAccessError
from product.runtime.research_supplement_mcp import GateScopedResearchSupplementTools


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
    def test_provider_results_assemble_background_and_extra_research_package(self):
        identity = identity_fact("batch-assembled")
        option = build_supplement_fact(
            security_id=SECURITY, dataset="options_snapshot", semantic_field="option_contract",
            value={"contract": "AAPL261218C00100000"}, source_id="yahoo-options",
            source_family="yahoo", source_locator="https://query2.finance.yahoo.com/options",
            source_version="synthetic/1", as_of=NOW, published_at=NOW, retrieved_at=NOW,
            raw_content_hash="d" * 64,
            batch_id="batch-assembled",
        )
        assembled = assemble_company_background(
            snapshot_id="assembled", batch_id="batch-assembled", security_id=SECURITY,
            ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
            dataset_results=[
                {"source": "sec", "dataset": "identity_profile", "status": "AVAILABLE",
                 "failure_code": None, "evidence": [identity], "gaps": [], "limitations": []},
                {"source": "moomoo_sg", "dataset": "identity_profile", "status": "BLOCKED_CONFIGURATION",
                 "failure_code": "MOOMOO_SG_SESSION_REFERENCE_MISSING", "evidence": [],
                 "gaps": ["会话待提供"], "limitations": []},
                {"source": "yahoo", "dataset": "options_snapshot", "status": "AVAILABLE",
                 "failure_code": None, "evidence": [option], "gaps": [], "limitations": []},
            ],
        )
        background = assembled["background"]
        self.assertEqual(background["groups"]["identity_profile"]["status"], "PARTIAL")
        self.assertEqual(len(background["groups"]["identity_profile"]["source_attempts"]), 2)
        self.assertEqual(assembled["extra_evidence"][0]["dataset"], "options_snapshot")
        self.assertEqual(background["evidence"][0]["batch_id"], "batch-assembled")
        self.assertEqual(background["evidence"][0]["source_type"], "PRIMARY_DISCLOSURE")
        capabilities = [
            build_capability(
                source=source, region=region, security_id=SECURITY, dataset=dataset,
                status="AVAILABLE", fields=[dataset], endpoint_version="synthetic/1",
                checked_at=NOW, as_of=NOW, attempt_count=1, limitations=[],
                evidence_ids=[
                    identity["evidence_id"] if dataset == "identity_profile" else option["evidence_id"]
                ],
                raw_content_hashes=["a" * 64 if dataset == "identity_profile" else "d" * 64],
            )
            for source, region, dataset in (
                ("sec", "US", "identity_profile"), ("yahoo", "US", "options_snapshot"),
            )
        ]
        capabilities.append(build_capability(
            source="moomoo_sg", region="SG", security_id=SECURITY,
            dataset="identity_profile", status="BLOCKED_CONFIGURATION", fields=[],
            endpoint_version=None, checked_at=NOW, as_of=NOW, attempt_count=1,
            limitations=["会话待提供"],
            failure_code="MOOMOO_SG_SESSION_REFERENCE_MISSING",
        ))
        batch = build_capture_batch(
            batch_id="batch-assembled", security_id=SECURITY,
            decision_cutoff=NOW, created_at=NOW, capabilities=capabilities,
            source_selections=assembled["source_selections"],
        )
        package = build_research_supplement_package(
            batch=batch, background=background, extra_evidence=assembled["extra_evidence"],
        )
        self.assertEqual(set(package["evidence_ids"]), {identity["evidence_id"], option["evidence_id"]})
        prepared = {
            "gate": {
                "run_id": "run-package", "decision_cutoff": NOW,
                "input_evidence_ids": [], "allowed_evidence": [], "allowed_evidence_ids": [],
                "excluded": [], "excluded_evidence_ids": [], "bundle_hash": "a" * 64,
            },
            "preparation": {
                "common_cutoff": NOW, "preparation_hash": "b" * 64,
                "items": [{
                    "security_id": SECURITY, "status": "READY", "evidence_ids": [],
                }],
            },
        }
        merged = merge_research_supplement_evidence(
            prepared, background=background, package=package, batch=batch,
            allowed_security_ids={SECURITY},
        )
        self.assertEqual(
            set(package["evidence_ids"]),
            set(merged["preparation"]["items"][0]["evidence_ids"]),
        )
        tools = GateScopedResearchSupplementTools(
            background=background, package=package, batch=batch, gate=merged["gate"],
            run_id="run-package", agent="runtime_company_analyst", invocation_id="inv-package",
        )
        queried = tools.query(
            run_id="run-package", agent="runtime_company_analyst", invocation_id="inv-package",
            security_id=SECURITY, datasets=["options_snapshot"], decision_cutoff=NOW,
            batch_id="batch-assembled",
        )
        self.assertEqual(queried["evidence"][0]["evidence_id"], option["evidence_id"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "data"
            inputs = root / "inputs"
            data_dir.mkdir()
            inputs.mkdir()
            (data_dir / "gate.json").write_text(json.dumps(prepared["gate"]), encoding="utf-8")
            (data_dir / "data-preparation.json").write_text(
                json.dumps(prepared["preparation"]), encoding="utf-8"
            )
            (data_dir / "collection-input.json").write_text(json.dumps({
                "schema_version": "live-portfolio/2.0.0",
                "purpose": "COMMON_STOCK_DATA_COLLECTION",
                "base_currency": "USD",
                "source_id": "portfolio-handoff:test",
                "as_of": NOW,
                "retrieved_at": NOW,
                "positions": [{
                    "security_id": SECURITY, "ticker": "AAPL",
                    "exchange": None, "share_class": None,
                }],
            }), encoding="utf-8")
            paths = {}
            for name, value in (
                ("background.json", background), ("package.json", package), ("batch.json", batch),
            ):
                paths[name] = inputs / name
                paths[name].write_text(json.dumps(value), encoding="utf-8")
            attached = attach_research_supplement(
                data_dir, background_path=paths["background.json"],
                package_path=paths["package.json"], batch_path=paths["batch.json"],
            )
            self.assertEqual(attached["status"], "ATTACHED")
            self.assertTrue((data_dir / "company-background.md").is_file())
            frozen_gate = json.loads((data_dir / "gate.json").read_text(encoding="utf-8"))
            self.assertIn(option["evidence_id"], frozen_gate["allowed_evidence_ids"])
            with self.assertRaisesRegex(ValueError, "ALREADY_ATTACHED"):
                attach_research_supplement(
                    data_dir, background_path=paths["background.json"],
                    package_path=paths["package.json"], batch_path=paths["batch.json"],
                )

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

    def test_gate_merge_preserves_sidecar_and_old_base_shape(self):
        fact = identity_fact()
        snapshot = build_company_background_snapshot(
            snapshot_id="background-merge", batch_id="batch-1", security_id=SECURITY,
            ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
            evidence=[fact], groups=group_set(identity_id=fact["evidence_id"]),
        )
        prepared = {
            "gate": {
                "decision_cutoff": NOW, "input_evidence_ids": [],
                "allowed_evidence": [], "allowed_evidence_ids": [], "excluded": [],
                "excluded_evidence_ids": [], "bundle_hash": "a" * 64,
            },
            "preparation": {
                "common_cutoff": NOW,
                "preparation_hash": "b" * 64,
            },
        }
        merged = merge_research_supplement_evidence(
            prepared, background=snapshot, allowed_security_ids={SECURITY},
        )
        self.assertEqual(merged["gate"]["allowed_evidence_ids"], [fact["evidence_id"]])
        self.assertEqual(merged["preparation"]["research_supplement"]["snapshot_hash"], snapshot["snapshot_hash"])
        self.assertNotIn("source_access", snapshot)

        later_prepared = deepcopy(prepared)
        later_prepared["gate"]["decision_cutoff"] = "2026-09-15T13:00:00Z"
        later_prepared["preparation"]["common_cutoff"] = "2026-09-15T13:00:00Z"
        later = merge_research_supplement_evidence(
            later_prepared, background=snapshot,
            allowed_security_ids={SECURITY},
        )
        self.assertEqual(
            "2026-09-15T13:00:00Z", later["gate"]["decision_cutoff"],
        )
        self.assertEqual(
            [fact["evidence_id"]], later["gate"]["allowed_evidence_ids"],
        )

        tampered = deepcopy(snapshot)
        tampered["snapshot_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            validate_company_background_snapshot(tampered)

        mismatched_cutoff = deepcopy(prepared)
        mismatched_cutoff["gate"]["decision_cutoff"] = "2026-09-15T11:59:59Z"
        with self.assertRaisesRegex(ValueError, "CUTOFF_MISMATCH"):
            merge_research_supplement_evidence(
                mismatched_cutoff, background=snapshot,
                allowed_security_ids={SECURITY},
            )
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_SCOPE_MISMATCH"):
            merge_research_supplement_evidence(
                prepared, background=snapshot,
                allowed_security_ids={"US:COMMON_STOCK:MSFT"},
            )

    def test_frozen_query_is_scoped_by_security_dataset_cutoff_and_batch(self):
        fact = identity_fact()
        snapshot = build_company_background_snapshot(
            snapshot_id="background-query", batch_id="batch-1", security_id=SECURITY,
            ticker="AAPL", decision_cutoff=NOW, created_at=NOW,
            evidence=[fact], groups=group_set(identity_id=fact["evidence_id"]),
        )
        prepared = {
            "gate": {
                "run_id": "run-1", "decision_cutoff": NOW,
                "input_evidence_ids": [], "allowed_evidence": [], "allowed_evidence_ids": [],
                "excluded": [], "excluded_evidence_ids": [], "bundle_hash": "a" * 64,
            },
            "preparation": {"common_cutoff": NOW, "preparation_hash": "b" * 64},
        }
        merged = merge_research_supplement_evidence(
            prepared, background=snapshot, allowed_security_ids={SECURITY},
        )
        tools = GateScopedResearchSupplementTools(
            background=snapshot, gate=merged["gate"], run_id="run-1",
            agent="runtime_company_analyst", invocation_id="inv-1",
        )
        result = tools.query(
            run_id="run-1", agent="runtime_company_analyst", invocation_id="inv-1",
            security_id=SECURITY, datasets=["identity_profile"],
            decision_cutoff=NOW, batch_id="batch-1",
        )
        self.assertEqual(result["evidence"][0]["evidence_id"], fact["evidence_id"])
        self.assertEqual(tools.events[-1]["access_mode"], "read")
        with self.assertRaisesRegex(ToolAccessError, "BATCH_SCOPE_MISMATCH"):
            tools.query(
                run_id="run-1", agent="runtime_company_analyst", invocation_id="inv-1",
                security_id=SECURITY, datasets=["identity_profile"],
                decision_cutoff=NOW, batch_id="other",
            )

if __name__ == "__main__":
    unittest.main()
