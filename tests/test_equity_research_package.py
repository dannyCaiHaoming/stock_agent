from __future__ import annotations

from copy import deepcopy
import unittest

from product.deterministic.equity_valuation import (
    build_fundamental_supplement,
    build_metric,
    build_peer_comparison,
    build_valuation_snapshot,
)
from product.runtime.equity_research_package import (
    EquityResearchPackageError,
    GateScopedEquityResearchTools,
    build_equity_research_package,
    validate_equity_research_package,
)
from product.runtime.fixture_mcp import ToolAccessError
from product.runtime.hashing import canonical_hash


CUTOFF = "2026-09-17T12:00:00Z"
SECURITY = "US:COMMON_STOCK:TEST"


def gate():
    evidence_ids = [
        "ev-base", "ev-peer", "ev-base-price", "ev-base-shares", "ev-base-revenue",
        "ev-peer-price", "ev-peer-shares", "ev-peer-revenue",
    ]
    value = {
        "run_id": "run-1", "decision_cutoff": CUTOFF,
        "allowed_evidence_ids": evidence_ids,
        "allowed_evidence": [
            {"evidence_id": evidence_id, "security_id": SECURITY if "base" in evidence_id else "US:COMMON_STOCK:PEER"}
            for evidence_id in evidence_ids
        ],
        "excluded_evidence_ids": [], "excluded": [], "input_evidence_ids": evidence_ids,
    }
    value["bundle_hash"] = canonical_hash(value)
    return value


def artifacts():
    provider = build_metric(
        name="trailing_pe", origin="PROVIDER_REPORTED", value="20",
        status="AVAILABLE", source_id="yahoo", as_of=CUTOFF,
        retrieved_at=CUTOFF, published_at=None,
        evidence_refs=["raw:yahoo:" + "a" * 64],
    )
    derived = build_metric(
        name="trailing_pe", origin="DERIVED", value="21", status="AVAILABLE",
        source_id="sec+yahoo", as_of=CUTOFF, retrieved_at=CUTOFF,
        published_at="2026-08-01T00:00:00Z", evidence_refs=["ev-base"],
        formula="price / EPS", calculation_ref="calc:pe",
    )
    snapshot = build_valuation_snapshot(
        snapshot_id="valuation", security_id=SECURITY, decision_cutoff=CUTOFF,
        valuation_at=CUTOFF,
        price_basis="CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
        metrics=[provider, derived],
    )
    item = {
        "item_id": "quality-1", "claim_status": "VERIFIED_FACT", "source_id": "sec",
        "as_of": "2026-06-30T00:00:00Z", "retrieved_at": CUTOFF,
        "published_at": "2026-08-01T00:00:00Z", "period": "2026Q2",
        "definition": "reported", "unit": "USD", "evidence_refs": ["ev-base"],
        "calculation_ref": None,
    }
    groups = {name: {"status": "PARTIAL", "coverage": "fixture", "reason": None, "items": [deepcopy(item) | {"item_id": name}]} for name in (
        "guidance", "earnings_quality", "debt_liquidity", "operating_kpis", "governance", "earnings_expectations", "financial_ratios"
    )}
    fundamental = build_fundamental_supplement(
        supplement_id="fundamental", security_id=SECURITY,
        decision_cutoff=CUTOFF, groups=groups,
    )
    candidates = [
        {"security_id": "US:COMMON_STOCK:PEER", "reason": "same market", "status": "INCLUDED", "evidence_refs": ["ev-peer"]},
    ]
    def company(security_id, ref, value):
        return {
            "security_id": security_id, "fiscal_period": "2026Q2", "currency": "USD",
            "metrics": [{
                "name": "trailing_pe", "metric_basis_id": "PRICE_OVER_GAAP_TTM_EPS", "value": value, "unit": "ratio", "basis": "TTM GAAP",
                "status": "COMPARABLE", "source_id": "sec+yahoo", "as_of": "2026-06-30T00:00:00Z",
                "retrieved_at": CUTOFF, "published_at": "2026-08-01T00:00:00Z", "period": "TTM 2026Q2",
                "evidence_refs": [ref], "formula": None, "calculation_ref": None, "calculation": None,
            }], "comparability_notes": ["same market"],
        }
    peers = [{
        **company("US:COMMON_STOCK:PEER", "ev-peer", "18"),
    }]
    peer = build_peer_comparison(
        comparison_id="peers", target_security_id=SECURITY,
        decision_cutoff=CUTOFF, candidates=candidates,
        target=company(SECURITY, "ev-base", "20"), peers=peers,
    )
    return {"valuation_snapshot": snapshot, "fundamental_supplement": fundamental, "peer_comparison": peer}


def ttm_company(security_id, prefix):
    revenue_ref, price_ref, shares_ref = f"{prefix}-revenue", f"{prefix}-price", f"{prefix}-shares"
    revenue_calculation = {
        "formula_version": "peer-ttm-sum/1.0.0", "annual": "100",
        "current_ytd": "20", "prior_ytd": "20", "result": "100",
        "input_evidence_refs": [revenue_ref],
    }
    revenue = {
        "name": "revenue", "metric_basis_id": "GAAP_TTM_REVENUE", "value": "100",
        "unit": "USD", "basis": "FY + current YTD - prior YTD", "status": "COMPARABLE",
        "source_id": "sec", "as_of": "2026-06-30T00:00:00Z", "retrieved_at": CUTOFF,
        "published_at": "2026-08-01T00:00:00Z", "period": "TTM 2026Q2",
        "evidence_refs": [revenue_ref], "formula": "FY + current YTD - prior YTD",
        "calculation_ref": f"calc:peer-metric:{canonical_hash(revenue_calculation)[:16]}",
        "calculation": revenue_calculation,
    }
    margin_calculation = {
        "formula_version": "peer-operating-margin/1.0.0", "operating_income": "10",
        "revenue": "100", "input_evidence_refs": [revenue_ref],
    }
    margin = {
        "name": "operating_margin", "metric_basis_id": "GAAP_TTM_OPERATING_MARGIN", "value": "0.1",
        "unit": "ratio", "basis": "GAAP TTM", "status": "LIMITED_COMPARABILITY",
        "source_id": "sec", "as_of": "2026-06-30T00:00:00Z", "retrieved_at": CUTOFF,
        "published_at": "2026-08-01T00:00:00Z", "period": "TTM 2026Q2",
        "evidence_refs": [revenue_ref], "formula": "operating income / revenue",
        "calculation_ref": f"calc:peer-metric:{canonical_hash(margin_calculation)[:16]}",
        "calculation": margin_calculation,
    }
    ps_calculation = {
        "formula_version": "peer-price-to-sales/1.0.0", "price": "20",
        "actual_common_shares_outstanding": "10", "market_cap": "200", "revenue": "100",
        "input_evidence_refs": sorted([price_ref, shares_ref, revenue_ref]),
        "price_evidence_ref": price_ref, "shares_evidence_ref": shares_ref,
        "revenue_evidence_refs": [revenue_ref], "price_source_id": "yahoo",
        "shares_source_id": "sec", "revenue_source_id": "sec",
    }
    ps = {
        "name": "price_to_sales", "metric_basis_id": "MARKET_CAP_OVER_GAAP_TTM_REVENUE", "value": "2",
        "unit": "ratio", "basis": "market cap / GAAP TTM revenue", "status": "LIMITED_COMPARABILITY",
        "source_id": "sec+yahoo", "as_of": "2026-06-30T00:00:00Z", "retrieved_at": CUTOFF,
        "published_at": "2026-08-01T00:00:00Z", "period": "TTM 2026Q2",
        "evidence_refs": sorted([price_ref, shares_ref, revenue_ref]), "formula": "market cap / revenue",
        "calculation_ref": f"calc:peer-metric:{canonical_hash(ps_calculation)[:16]}",
        "calculation": ps_calculation,
    }
    return {
        "security_id": security_id, "fiscal_period": "2026Q2", "currency": "USD",
        "metrics": [revenue, margin, ps], "comparability_notes": ["bounded peer"],
    }


class EquityResearchPackageTests(unittest.TestCase):
    def package(self):
        frozen_gate = gate()
        package = build_equity_research_package(
            package_id="package-1", run_id="run-1", security_id=SECURITY,
            decision_cutoff=CUTOFF, gate_bundle_hash=frozen_gate["bundle_hash"],
            artifacts=artifacts(), raw_input_refs=[{
                "ref": "raw:yahoo:" + "a" * 64, "source_id": "yahoo-summary",
                "retrieved_at": CUTOFF, "raw_content_hash": "a" * 64,
            }],
        )
        return frozen_gate, package

    def test_package_closes_gate_and_raw_lineage(self):
        frozen_gate, package = self.package()
        validate_equity_research_package(package, gate=frozen_gate)
        self.assertEqual(3, len(package["artifacts"]))
        self.assertEqual(frozen_gate["bundle_hash"], package["gate_bundle_hash"])

    def test_tamper_wrong_security_and_future_raw_fail(self):
        frozen_gate, package = self.package()
        broken = deepcopy(package)
        broken["artifacts"][0]["artifact"]["security_id"] = "US:COMMON_STOCK:OTHER"
        broken["package_hash"] = canonical_hash({key: item for key, item in broken.items() if key != "package_hash"})
        with self.assertRaises(EquityResearchPackageError):
            validate_equity_research_package(broken, gate=frozen_gate)
        broken = deepcopy(package)
        broken["raw_input_refs"][0]["retrieved_at"] = "2026-09-18T00:00:00Z"
        broken["package_hash"] = canonical_hash({key: item for key, item in broken.items() if key != "package_hash"})
        with self.assertRaisesRegex(EquityResearchPackageError, "AFTER_CUTOFF"):
            validate_equity_research_package(broken, gate=frozen_gate)

    def test_gate_cutoff_must_match_package_cutoff(self):
        frozen_gate, package = self.package()
        broken_gate = deepcopy(frozen_gate)
        broken_gate["decision_cutoff"] = "2026-09-17T11:59:59Z"
        broken_gate["bundle_hash"] = canonical_hash({
            key: item for key, item in broken_gate.items() if key != "bundle_hash"
        })
        broken_package = deepcopy(package)
        broken_package["gate_bundle_hash"] = broken_gate["bundle_hash"]
        broken_package["package_hash"] = canonical_hash({
            key: item for key, item in broken_package.items() if key != "package_hash"
        })
        with self.assertRaisesRegex(EquityResearchPackageError, "CUTOFF_MISMATCH"):
            validate_equity_research_package(broken_package, gate=broken_gate)

    def test_package_rejects_coherent_cross_metric_ttm_tampering(self):
        frozen_gate = gate()
        peer = build_peer_comparison(
            comparison_id="ttm-peers", target_security_id=SECURITY,
            decision_cutoff=CUTOFF,
            candidates=[{
                "security_id": "US:COMMON_STOCK:PEER", "reason": "same market",
                "status": "INCLUDED", "evidence_refs": ["ev-peer"],
            }],
            target=ttm_company(SECURITY, "ev-base"),
            peers=[ttm_company("US:COMMON_STOCK:PEER", "ev-peer")],
        )
        package = build_equity_research_package(
            package_id="ttm-package", run_id="run-1", security_id=SECURITY,
            decision_cutoff=CUTOFF, gate_bundle_hash=frozen_gate["bundle_hash"],
            artifacts={"peer_comparison": peer},
        )

        def rehash(value):
            entry = value["artifacts"][0]
            artifact = entry["artifact"]
            artifact["artifact_hash"] = canonical_hash({
                key: item for key, item in artifact.items() if key != "artifact_hash"
            })
            entry["artifact_hash"] = artifact["artifact_hash"]
            value["package_hash"] = canonical_hash({
                key: item for key, item in value.items() if key != "package_hash"
            })

        broken = deepcopy(package)
        metrics = broken["artifacts"][0]["artifact"]["target"]["metrics"]
        ps = next(item for item in metrics if item["name"] == "price_to_sales")
        ps["calculation"]["revenue"] = "1"
        ps["value"] = "200"
        ps["calculation_ref"] = f"calc:peer-metric:{canonical_hash(ps['calculation'])[:16]}"
        rehash(broken)
        with self.assertRaisesRegex(EquityResearchPackageError, "ARTIFACT_INVALID"):
            validate_equity_research_package(broken, gate=frozen_gate)

        broken = deepcopy(package)
        metrics = broken["artifacts"][0]["artifact"]["target"]["metrics"]
        revenue = next(item for item in metrics if item["name"] == "revenue")
        revenue["calculation"]["annual"] = "101"
        revenue["calculation"]["result"] = "101"
        revenue["value"] = "101"
        revenue["calculation_ref"] = f"calc:peer-metric:{canonical_hash(revenue['calculation'])[:16]}"
        rehash(broken)
        with self.assertRaisesRegex(EquityResearchPackageError, "ARTIFACT_INVALID"):
            validate_equity_research_package(broken, gate=frozen_gate)

    def test_read_only_tool_is_invocation_security_cutoff_scoped(self):
        frozen_gate, package = self.package()
        tool = GateScopedEquityResearchTools(
            package=package, gate=frozen_gate, run_id="run-1",
            agent="runtime_company_analyst", invocation_id="inv-1",
        )
        output = tool.query(
            run_id="run-1", agent="runtime_company_analyst", invocation_id="inv-1",
            security_id=SECURITY, decision_cutoff=CUTOFF,
            kinds=["valuation_snapshot", "fundamental_supplement"],
        )
        self.assertEqual({"valuation_snapshot", "fundamental_supplement"}, set(output["artifacts"]))
        self.assertEqual("read", tool.events[0]["access_mode"])
        with self.assertRaisesRegex(ToolAccessError, "SECURITY_SCOPE"):
            tool.query(
                run_id="run-1", agent="runtime_company_analyst", invocation_id="inv-1",
                security_id="US:COMMON_STOCK:OTHER", decision_cutoff=CUTOFF,
                kinds=["valuation_snapshot"],
            )


if __name__ == "__main__":
    unittest.main()
