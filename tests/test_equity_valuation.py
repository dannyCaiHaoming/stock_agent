from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from product.deterministic.equity_valuation import (
    EquityValuationError,
    aggregate_ttm,
    build_fundamental_supplement,
    build_metric,
    build_peer_comparison,
    build_trailing_pe_history,
    build_valuation_snapshot,
    calculate_financial_ratios,
    compare_guidance_versions,
    cumulative_period_difference,
    derive_current_valuation,
    derive_forward_pe,
    midrank_percentile,
    reconcile_adjusted_metric,
    provider_metrics_from_yahoo,
    select_pit_version,
    align_price_and_per_share_input,
    validate_fundamental_supplement,
    validate_peer_comparison,
    validate_valuation_history,
    validate_valuation_snapshot,
    validate_market_cap_inputs,
)


CUTOFF = "2026-09-17T12:00:00Z"
SECURITY = "US:COMMON_STOCK:TEST"


def quarter(index: int, value: str, *, metric="revenue"):
    starts = ("2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01")
    ends = ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
    return {
        "security_id": SECURITY, "metric": metric, "value": value,
        "period_start": starts[index], "period_end": ends[index],
        "context_type": "independent_quarter", "accounting_basis": "GAAP",
        "currency": "USD", "unit": "USD", "evidence_refs": [f"ev-q{index}"],
    }


class ValuationContractTests(unittest.TestCase):
    def metric(self):
        return build_metric(
            name="trailing_pe", origin="DERIVED", value="20", status="AVAILABLE",
            source_id="sec+yahoo", as_of=CUTOFF, retrieved_at=CUTOFF,
            published_at="2026-08-01T00:00:00Z", price_at=CUTOFF,
            financial_period="2026-06-30", fiscal_basis="TTM",
            accounting_basis="GAAP", evidence_refs=["ev-eps", "ev-price"],
            formula="price / TTM diluted EPS", calculation_ref="calc:pe:1",
        )

    def test_snapshot_keeps_provenance_and_hash(self):
        value = build_valuation_snapshot(
            snapshot_id="valuation-1", security_id=SECURITY,
            decision_cutoff=CUTOFF, valuation_at=CUTOFF,
            price_basis="CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
            metrics=[self.metric()],
        )
        validate_valuation_snapshot(value)
        broken = deepcopy(value)
        broken["metrics"][0]["source_id"] = ""
        broken["artifact_hash"] = value["artifact_hash"]
        with self.assertRaisesRegex(EquityValuationError, "PROVENANCE_MISSING"):
            validate_valuation_snapshot(broken)

    def test_provider_unknown_publication_not_forged(self):
        metric = build_metric(
            name="forward_pe", origin="PROVIDER_REPORTED", value="21",
            status="AVAILABLE", source_id="yahoo", as_of=CUTOFF,
            retrieved_at=CUTOFF, published_at=None, evidence_refs=["ev-yahoo"],
        )
        self.assertIsNone(metric["published_at"])
        self.assertIsNone(metric["calculation_ref"])

    def test_derived_available_requires_formula_and_lineage(self):
        with self.assertRaisesRegex(EquityValuationError, "CALCULATION_REQUIRED"):
            build_metric(
                name="trailing_pe", origin="DERIVED", value="20", status="AVAILABLE",
                source_id="sec", as_of=CUTOFF, retrieved_at=CUTOFF,
                evidence_refs=["ev"],
            )


class CurrentValuationTests(unittest.TestCase):
    def test_current_metrics_keep_negative_fcf_and_missing_ev(self):
        metrics = derive_current_valuation(
            price="100", shares_outstanding="10", ttm_eps="5",
            ttm_revenue="500", common_equity="250",
            ttm_operating_cash_flow="10", ttm_capex="20",
            debt=None, cash="50", preferred_stock="0",
            noncontrolling_interest="0", ttm_ebitda="40",
            security_id=SECURITY, valuation_at=CUTOFF,
            financial_period="2026-06-30", currency="USD",
            source_id="sec+yahoo", retrieved_at=CUTOFF,
            evidence_refs=["ev-1", "ev-2"],
        )
        by_name = {item["name"]: item for item in metrics}
        self.assertEqual("20", by_name["trailing_pe"]["value"])
        self.assertEqual("-0.01", by_name["fcf_yield"]["value"])
        self.assertEqual("INPUT_MISSING", by_name["enterprise_value"]["status"])
        self.assertEqual("INPUT_MISSING", by_name["ev_to_ebitda"]["status"])

    def test_loss_pe_is_not_applicable_but_sales_remains(self):
        metrics = derive_current_valuation(
            price="100", shares_outstanding="10", ttm_eps="-2",
            ttm_revenue="500", common_equity="250", ttm_operating_cash_flow="30",
            ttm_capex="10", debt="100", cash="50", preferred_stock="0",
            noncontrolling_interest="0", ttm_ebitda="40", security_id=SECURITY,
            valuation_at=CUTOFF, financial_period="2026-06-30", currency="USD",
            source_id="sec+yahoo", retrieved_at=CUTOFF, evidence_refs=["ev"],
        )
        by_name = {item["name"]: item for item in metrics}
        self.assertEqual("NOT_APPLICABLE", by_name["trailing_pe"]["status"])
        self.assertEqual("AVAILABLE", by_name["price_to_sales"]["status"])

    def test_forward_pe_requires_basis_and_provider_conflict_is_explicit(self):
        unknown = derive_forward_pe(
            price="100", forecast_eps="5", forecast_period=None,
            accounting_basis="UNKNOWN", source_id="yahoo", valuation_at=CUTOFF,
            retrieved_at=CUTOFF, evidence_refs=["ev-forecast"], currency="USD",
        )
        self.assertEqual("BASIS_UNKNOWN", unknown["status"])
        derived = derive_forward_pe(
            price="100", forecast_eps="5", forecast_period="FY1",
            accounting_basis="GAAP", source_id="yahoo", valuation_at=CUTOFF,
            retrieved_at=CUTOFF, evidence_refs=["ev-forecast"], currency="USD",
        )
        provider = provider_metrics_from_yahoo({
            "fields": {"forwardPE": 22, "currency": "USD"},
            "source_id": "yahoo-summary", "as_of": CUTOFF,
            "retrieved_at": CUTOFF, "raw_content_hash": "a" * 64,
        })[0]
        snapshot = build_valuation_snapshot(
            snapshot_id="conflict", security_id=SECURITY, decision_cutoff=CUTOFF,
            valuation_at=CUTOFF,
            price_basis="CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
            metrics=[provider, derived],
        )
        self.assertEqual("20", derived["value"])
        self.assertTrue(any(item.startswith("METRIC_CONFLICT:forward_pe") for item in snapshot["data_gaps"]))
        self.assertIsNone(provider["published_at"])


class PeriodAndHistoryTests(unittest.TestCase):
    def test_ttm_four_quarters_and_eps_policy(self):
        result = aggregate_ttm([quarter(i, str(i + 1)) for i in range(4)], metric="revenue")
        self.assertEqual("10", result["value"])
        with self.assertRaisesRegex(EquityValuationError, "EPS_SUM_REQUIRES"):
            aggregate_ttm([quarter(i, "1", metric="diluted_eps") for i in range(4)], metric="diluted_eps")
        eps = aggregate_ttm(
            [quarter(i, "1", metric="diluted_eps") for i in range(4)],
            metric="diluted_eps", allow_eps_sum=True,
        )
        self.assertIn("不保证", eps["limitation"])

    def test_cumulative_cash_flow_allowed_eps_rejected(self):
        earlier = {**quarter(0, "10"), "period_end": "2025-03-31", "fiscal_year": "2025"}
        later = {**quarter(1, "30"), "period_start": "2025-01-01", "period_end": "2025-06-30", "fiscal_year": "2025"}
        self.assertEqual("20", cumulative_period_difference(later=later, earlier=earlier, metric="operating_cash_flow")["value"])
        with self.assertRaisesRegex(EquityValuationError, "EPS_DIFFERENCE_FORBIDDEN"):
            cumulative_period_difference(later=later, earlier=earlier, metric="diluted_eps")

    def test_pit_selects_public_version_and_date_only_next_day(self):
        rows = [
            {"evidence_id": "old", "published_at": "2026-05-01", "value": "4"},
            {"evidence_id": "new", "published_at": "2026-08-01T10:00:00Z", "value": "5"},
        ]
        self.assertIsNone(select_pit_version(rows, valuation_at="2026-05-01T23:59:59Z"))
        self.assertEqual("old", select_pit_version(rows, valuation_at="2026-05-02T23:59:59Z")["evidence_id"])

    def test_monthly_history_coverage_and_midrank(self):
        prices = []
        for year in (2024, 2025):
            for month in range(1, 13):
                prices.append({
                    "date": f"{year}-{month:02d}-28", "close": "100",
                    "source_id": "yahoo-daily", "retrieved_at": "2026-09-01T00:00:00Z",
                    "evidence_refs": [f"p-{year}-{month}"],
                    "price_basis": "CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
                    "dividend_adjusted": False, "currency": "USD",
                    "security_id": SECURITY, "segment_id": "continuing-entity",
                })
        eps = []
        for index, row in enumerate(prices):
            year, month = map(int, row["date"].split("-")[:2])
            prior_year, prior_month = (year - 1, 12) if month == 1 else (year, month - 1)
            eps.append({
                "published_at": f"{year}-{month:02d}-01T00:00:00Z",
                "retrieved_at": "2026-09-01T00:00:00Z",
                "financial_period": f"{prior_year}-{prior_month:02d}-28",
                "value": "5", "evidence_refs": [f"eps-{index}"],
                "source_id": "sec-companyfacts",
                "share_basis": "SPLIT_ADJUSTED", "currency": "USD",
                "security_id": SECURITY, "segment_id": "continuing-entity",
            })
        value = build_trailing_pe_history(
            history_id="history-1", security_id=SECURITY, decision_cutoff=CUTOFF,
            requested_start="2024-01-01", requested_end="2025-12-31",
            price_rows=prices, eps_versions=eps, current_value="20",
            current_price_row={**prices[-1], "close": "110"},
            minimum_points=23,
        )
        validate_valuation_history(value)
        self.assertEqual(24, value["valid_points"])
        self.assertEqual(23, value["reference_points"])
        self.assertEqual("AVAILABLE", value["percentile_status"])
        self.assertEqual("110", value["points"][-1]["price"])
        self.assertEqual(Decimal("50"), midrank_percentile("20", ["10", "20", "30"]))

        broken = deepcopy(value)
        broken["points"][0]["source_id"] = ""
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "POINT_PROVENANCE_MISSING"):
            validate_valuation_history(broken)
        broken = deepcopy(value)
        broken["percentile"] = "99.9"
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "PERCENTILE_INVALID"):
            validate_valuation_history(broken)
        broken = deepcopy(value)
        broken["reference_coverage_ratio"] = "0.5"
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "COVERAGE_INVALID"):
            validate_valuation_history(broken)

    def test_current_point_is_excluded_from_percentile_reference(self):
        prices = [{
            "date": f"2024-{month:02d}-28", "close": str(month),
            "source_id": "yahoo-daily", "retrieved_at": "2026-09-01T00:00:00Z",
            "evidence_refs": [f"p-{month}"],
            "price_basis": "CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
            "dividend_adjusted": False, "currency": "USD",
            "security_id": SECURITY, "segment_id": "continuing-entity",
        } for month in range(1, 4)]
        eps = [{
            "published_at": "2023-12-01T00:00:00Z", "retrieved_at": "2026-09-01T00:00:00Z",
            "source_id": "sec-companyfacts", "financial_period": "2023-11-30", "value": "1",
            "evidence_refs": ["eps"], "share_basis": "SPLIT_ADJUSTED", "currency": "USD",
            "security_id": SECURITY, "segment_id": "continuing-entity",
        }]
        value = build_trailing_pe_history(
            history_id="exclude-current", security_id=SECURITY, decision_cutoff=CUTOFF,
            requested_start="2024-01-01", requested_end="2024-03-31", price_rows=prices,
            eps_versions=eps, current_value="3", current_price_row=prices[-1],
            minimum_points=2, minimum_coverage=Decimal("0.8"),
        )
        self.assertEqual(3, value["valid_points"])
        self.assertEqual(2, value["reference_points"])
        self.assertEqual("100.0", value["percentile"])

    def test_price_basis_rejects_dividend_adjusted_and_cross_security(self):
        with self.assertRaisesRegex(EquityValuationError, "PRICE_BASIS_INVALID"):
            align_price_and_per_share_input(
                price="100", per_share_value="5", price_basis="TOTAL_RETURN_ADJUSTED",
                per_share_basis="SPLIT_ADJUSTED", dividend_adjusted=True,
                currency="USD", per_share_currency="USD", security_id=SECURITY,
                per_share_security_id=SECURITY, segment_id="old", per_share_segment_id="old",
            )
        with self.assertRaisesRegex(EquityValuationError, "SECURITY_MISMATCH"):
            align_price_and_per_share_input(
                price="100", per_share_value="5",
                price_basis="CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED",
                per_share_basis="SPLIT_ADJUSTED", dividend_adjusted=False,
                currency="USD", per_share_currency="USD", security_id=SECURITY,
                per_share_security_id="US:COMMON_STOCK:OTHER",
                segment_id="old", per_share_segment_id="old",
            )

    def test_market_cap_rejects_weighted_or_stale_or_unverified_adr_shares(self):
        with self.assertRaisesRegex(EquityValuationError, "SHARE_COUNT_KIND"):
            validate_market_cap_inputs(
                shares="100", share_count_kind="WEIGHTED_AVERAGE_DILUTED",
                price_share_class="A", shares_share_class="A",
                shares_as_of="2026-06-30T00:00:00Z", valuation_at=CUTOFF,
            )
        with self.assertRaisesRegex(EquityValuationError, "ADR_RATIO_UNVERIFIED"):
            validate_market_cap_inputs(
                shares="100", share_count_kind="ACTUAL_COMMON_SHARES_OUTSTANDING",
                price_share_class="ADR", shares_share_class="ADR",
                shares_as_of="2026-06-30T00:00:00Z", valuation_at=CUTOFF,
                adr_ratio_status="UNKNOWN",
            )
        with self.assertRaisesRegex(EquityValuationError, "SHARE_COUNT_STALE"):
            validate_market_cap_inputs(
                shares="100", share_count_kind="ACTUAL_COMMON_SHARES_OUTSTANDING",
                price_share_class="A", shares_share_class="A",
                shares_as_of="2025-01-01T00:00:00Z", valuation_at=CUTOFF,
            )


class FundamentalAndPeerTests(unittest.TestCase):
    def item(self, item_id="item-1"):
        return {
            "item_id": item_id, "claim_status": "VERIFIED_FACT", "source_id": "sec:filing",
            "as_of": "2026-06-30T00:00:00Z", "retrieved_at": CUTOFF,
            "published_at": "2026-08-01T00:00:00Z", "period": "2026Q2",
            "definition": "reported value", "unit": "USD", "evidence_refs": [f"ev-{item_id}"],
            "calculation_ref": None,
        }

    def test_fundamental_groups_and_cutoff(self):
        groups = {name: {"status": "PARTIAL", "coverage": "1 item", "reason": None, "items": [self.item(name)]} for name in (
            "guidance", "earnings_quality", "debt_liquidity", "operating_kpis", "governance", "earnings_expectations", "financial_ratios"
        )}
        value = build_fundamental_supplement(
            supplement_id="fund-1", security_id=SECURITY,
            decision_cutoff=CUTOFF, groups=groups,
        )
        validate_fundamental_supplement(value)
        broken = deepcopy(value)
        broken["groups"]["guidance"]["items"][0]["retrieved_at"] = "2026-09-18T00:00:00Z"
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({key: item for key, item in broken.items() if key != "artifact_hash"})
        with self.assertRaisesRegex(EquityValuationError, "AFTER_CUTOFF"):
            validate_fundamental_supplement(broken)

    def test_guidance_period_change_and_reconciliation(self):
        prior = {"metric": "revenue", "target_period": "FY2027", "unit": "USDm", "accounting_basis": "GAAP", "lower": "100", "upper": "110"}
        current = {**prior, "lower": "105", "upper": "115"}
        self.assertEqual("5", compare_guidance_versions(prior, current)["midpoint_change"])
        next_year = {**current, "target_period": "FY2028"}
        self.assertEqual("NOT_COMPARABLE", compare_guidance_versions(prior, next_year)["status"])
        reconciled = reconcile_adjusted_metric(
            gaap_value="100", adjustments=[{"amount": "10", "sign": "ADD", "tax_basis": "AFTER_TAX"}],
            adjusted_value="110", display_increment="1",
        )
        self.assertEqual("RECONCILED", reconciled["status"])

    def test_financial_ratios_keep_missing_and_non_positive_status(self):
        ratios = calculate_financial_ratios(
            ttm_net_income="-10", beginning_equity=None, ending_equity="100",
            beginning_assets="180", ending_assets="220", current_assets="80",
            current_liabilities="40", cash_and_equivalents="25",
            marketable_securities="5", net_receivables="15", restricted_cash="5",
            interest_bearing_debt="60", ttm_ebit="-5", ttm_interest_expense="2",
            ttm_operating_cash_flow="20", ttm_sbc="5", ttm_revenue="200",
            evidence_refs=["ev-assets", "ev-income"],
        )
        self.assertEqual("INPUT_MISSING", ratios["roe"]["status"])
        self.assertEqual("NOT_APPLICABLE", ratios["ocf_to_net_income"]["status"])
        self.assertEqual("-2.5", ratios["interest_coverage"]["value"])
        self.assertEqual("INPUT_MISSING", ratios["roic"]["status"])

    def test_financial_ratios_keep_missing_interest_expense(self):
        ratios = calculate_financial_ratios(
            ttm_net_income="10", beginning_equity="90", ending_equity="110",
            beginning_assets="180", ending_assets="220", current_assets="80",
            current_liabilities="40", cash_and_equivalents="25",
            marketable_securities="5", net_receivables="15", restricted_cash="5",
            interest_bearing_debt="60", ttm_ebit="12", ttm_interest_expense=None,
            ttm_operating_cash_flow="20", ttm_sbc="5", ttm_revenue="200",
            evidence_refs=["ev-assets", "ev-income"],
        )
        self.assertEqual("INPUT_MISSING", ratios["interest_coverage"]["status"])
        self.assertEqual("INTEREST_EXPENSE_MISSING", ratios["interest_coverage"]["reason"])
        self.assertIsNone(ratios["interest_coverage"]["value"])
        self.assertEqual(["ev-assets", "ev-income"], ratios["current_ratio"]["evidence_refs"])
        self.assertTrue(ratios["current_ratio"]["calculation_ref"].startswith("calc:financial-ratio:"))

    def test_bounded_peers_do_not_rank(self):
        candidates = [
            {"security_id": "US:COMMON_STOCK:A", "reason": "same business", "status": "INCLUDED", "evidence_refs": ["ev-a"]},
            {"security_id": "US:COMMON_STOCK:B", "reason": "same market", "status": "INCLUDED", "evidence_refs": ["ev-b"]},
        ]
        def company(security_id, ref):
            def reported(name, value, evidence_ref=None):
                calculation = None
                formula = None
                calculation_ref = None
                if name == "revenue":
                    calculation = {
                        "formula_version": "peer-ttm-sum/1.0.0", "annual": value,
                        "current_ytd": "0", "prior_ytd": "0", "result": value,
                        "input_evidence_refs": [evidence_ref or ref],
                    }
                    formula = "FY + current YTD - prior YTD"
                    calculation_ref = f"calc:peer-metric:{__import__('product.runtime.hashing', fromlist=['canonical_hash']).canonical_hash(calculation)[:16]}"
                return {
                "name": name, "metric_basis_id": f"GAAP_TTM_{name.upper()}", "value": value, "unit": "USD", "basis": "TTM GAAP",
                "status": "COMPARABLE", "source_id": "sec-companyfacts", "as_of": "2026-06-30T00:00:00Z",
                "retrieved_at": CUTOFF, "published_at": "2026-08-01T00:00:00Z", "period": "2026Q2",
                "evidence_refs": [evidence_ref or ref], "formula": formula,
                "calculation_ref": calculation_ref, "calculation": calculation,
                }
            price_ref, shares_ref, revenue_ref = f"{ref}-price", f"{ref}-shares", f"{ref}-revenue"
            calculation = {"price": "20", "actual_common_shares_outstanding": "10", "market_cap": "200", "revenue": "100", "formula_version": "peer-price-to-sales/1.0.0", "input_evidence_refs": sorted([price_ref, shares_ref, revenue_ref]), "price_evidence_ref": price_ref, "shares_evidence_ref": shares_ref, "revenue_evidence_refs": [revenue_ref], "price_source_id": "yahoo-daily", "shares_source_id": "sec-companyfacts", "revenue_source_id": "sec-companyfacts"}
            return {
                "security_id": security_id, "fiscal_period": "2026Q2", "currency": "USD",
                "metrics": [reported("revenue", "100", revenue_ref), reported("operating_income", "10"), {
                    "name": "price_to_sales", "metric_basis_id": "MARKET_CAP_OVER_GAAP_TTM_REVENUE", "value": "2", "unit": "ratio", "basis": "market cap / TTM GAAP revenue",
                    "status": "LIMITED_COMPARABILITY", "source_id": "sec-companyfacts+yahoo-daily", "as_of": "2026-06-30T00:00:00Z",
                    "retrieved_at": CUTOFF, "published_at": "2026-08-01T00:00:00Z", "period": "2026Q2",
                    "evidence_refs": sorted([price_ref, shares_ref, revenue_ref]), "formula": "market cap / revenue",
                    "calculation_ref": f"calc:peer-metric:{__import__('product.runtime.hashing', fromlist=['canonical_hash']).canonical_hash(calculation)[:16]}",
                    "calculation": calculation,
                }], "comparability_notes": ["same basis"],
            }
        peers = [{
            **company(item["security_id"], item["evidence_refs"][0]),
            "comparability_notes": [item["reason"]],
        } for item in candidates]
        target = company(SECURITY, "ev-target")
        value = build_peer_comparison(
            comparison_id="peers-1", target_security_id=SECURITY,
            decision_cutoff=CUTOFF, candidates=candidates, target=target, peers=peers,
        )
        validate_peer_comparison(value)
        self.assertEqual("COMPLETE", value["coverage_status"])
        self.assertNotIn("rank", value)
        with self.assertRaisesRegex(EquityValuationError, "BUDGET"):
            build_peer_comparison(
                comparison_id="bad", target_security_id=SECURITY,
                decision_cutoff=CUTOFF, candidates=candidates * 3, target=target, peers=[],
            )
        broken = deepcopy(value)
        broken["peers"][0]["metrics"][0]["status"] = "RANKED_WINNER"
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "METRIC_STATUS_INVALID"):
            validate_peer_comparison(broken)
        broken = deepcopy(value)
        broken["target"]["metrics"][0]["retrieved_at"] = "2026-09-18T00:00:00Z"
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "PEER_METRIC_AFTER_CUTOFF"):
            validate_peer_comparison(broken)
        broken = deepcopy(value)
        broken["coverage_status"] = "INSUFFICIENT_PEERS"
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "COVERAGE_STATUS_INVALID"):
            validate_peer_comparison(broken)
        broken = deepcopy(value)
        metric = broken["target"]["metrics"][-1]
        metric["calculation"]["revenue"] = "1"
        metric["calculation_ref"] = "calc:peer-metric:" + __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash(metric["calculation"])[:16]
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "CALCULATION_RESULT_INVALID"):
            validate_peer_comparison(broken)
        broken = deepcopy(value)
        metric = broken["target"]["metrics"][-1]
        metric["evidence_refs"].remove(metric["calculation"]["price_evidence_ref"])
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "CALCULATION_EVIDENCE_INVALID"):
            validate_peer_comparison(broken)
        broken = deepcopy(value)
        metric = broken["target"]["metrics"][-1]
        metric["calculation"]["revenue"] = "1"
        metric["value"] = format(Decimal(metric["calculation"]["market_cap"]), "f")
        metric["calculation_ref"] = "calc:peer-metric:" + __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash(metric["calculation"])[:16]
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "TTM_REVENUE_BINDING_INVALID"):
            validate_peer_comparison(broken)
        broken = deepcopy(value)
        revenue = broken["target"]["metrics"][0]
        revenue["calculation"] = {
            "formula_version": "peer-ttm-sum/1.0.0", "annual": "101",
            "current_ytd": "0", "prior_ytd": "0", "result": "101",
            "input_evidence_refs": list(revenue["evidence_refs"]),
        }
        revenue["value"] = "101"
        revenue["formula"] = "FY + current YTD - prior YTD"
        revenue["calculation_ref"] = "calc:peer-metric:" + __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash(revenue["calculation"])[:16]
        broken["artifact_hash"] = __import__("product.runtime.hashing", fromlist=["canonical_hash"]).canonical_hash({
            key: item for key, item in broken.items() if key != "artifact_hash"
        })
        with self.assertRaisesRegex(EquityValuationError, "TTM_REVENUE_BINDING_INVALID"):
            validate_peer_comparison(broken)


if __name__ == "__main__":
    unittest.main()
