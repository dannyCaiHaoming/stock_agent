import unittest

from product.council import CouncilOrchestrator
from product.council.output import FinalPlanError, NO_TRADE_REASONS, validate_final_plan


class FakeRisk:
    def __init__(self, statuses=("APPROVED",)):
        self.statuses = list(statuses)
        self.calls = 0

    def preflight(self, portfolio):
        return {"status": "READY", "policy_version": "risk-1", "cash": portfolio["cash"]}

    def final_check(self, portfolio, draft):
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return {
            "status": status,
            "policy_version": "risk-1",
            "violations": [] if status == "APPROVED" else ["MAX_POSITION"],
            "feasible_bounds": {"max_weight": 0.10},
        }


def report_agent(request):
    assert "peer_reports" not in request
    assert request["isolation"] == "first-pass-no-peer-conclusions"
    return {
        "claims": [{"claim_id": request["capability"], "evidence_refs": ["fact-1"]}],
        "counter_evidence_refs": ["fact-2"],
        "data_gaps": [],
        "confidence": 0.6,
    }


def synthesize(portfolio, reports, preflight):
    return {
        "schema_version": "1.0.0",
        "decisions": [
            {
                "security_id": "AAA",
                "action": "ADD",
                "target_weight_range": [0.07, 0.09],
                "maximum_notional": 9000,
                "time_horizon": "20d",
                "thesis": "Evidence-backed draft supplied by the CIO callback.",
                "counter_thesis": "Demand may weaken.",
                "evidence_refs": ["fact-1"],
                "invalidation_conditions": ["Revenue falls below the stated threshold."],
                "unresolved_uncertainties": ["Next filing is pending."],
            }
        ],
        "conflicts": [{"claim": "growth", "reports": [r["capability"] for r in reports]}],
    }


class CouncilTests(unittest.TestCase):
    def setUp(self):
        self.agents = {
            "company-research": report_agent,
            "counter-thesis": report_agent,
            "market-catalyst": report_agent,
        }
        self.portfolio = {"cash": 20_000, "positions": [{"security_id": "AAA"}]}

    def test_dynamic_delegation_does_not_call_every_agent(self):
        result = CouncilOrchestrator(self.agents).run(
            portfolio=self.portfolio,
            requested_capabilities=["company-research", "counter-thesis"],
            evidence_refs=["fact-1", "fact-2"],
            cio_synthesize=synthesize,
            risk_engine=FakeRisk(),
            decision_cutoff="2026-01-02T00:00:00+00:00",
        )
        self.assertEqual(2, len(result.reports))
        self.assertNotIn("market-catalyst", {r["capability"] for r in result.reports})
        self.assertTrue(result.final_plan["advisory_only"])
        self.assertTrue(result.final_plan["decisions"][0]["invalidation_conditions"])
        self.assertTrue(result.final_plan["conflicts"])

    def test_risk_revision_is_bounded_to_one(self):
        risk = FakeRisk(("REVISE_REQUIRED", "REVISE_REQUIRED", "APPROVED"))
        result = CouncilOrchestrator(self.agents).run(
            portfolio=self.portfolio,
            requested_capabilities=["company-research"],
            evidence_refs=["fact-1"],
            cio_synthesize=synthesize,
            cio_revise=lambda draft, report: draft,
            risk_engine=risk,
        )
        self.assertEqual(2, risk.calls)
        self.assertEqual(2, len(result.draft_versions))
        self.assertEqual("NO_TRADE", result.final_plan["decisions"][0]["action"])
        self.assertEqual("RISK_VETO", result.final_plan["decisions"][0]["no_trade_reason"])

    def test_final_plan_rejects_execution_fields(self):
        plan = synthesize(self.portfolio, [], {})
        plan.update({"advisory_only": True, "risk_report": {"status": "APPROVED"}})
        plan["decisions"][0]["order_id"] = "forbidden"
        with self.assertRaises(FinalPlanError):
            validate_final_plan(plan)

    def test_unknown_capability_fails_closed(self):
        with self.assertRaises(ValueError):
            CouncilOrchestrator(self.agents).run(
                portfolio=self.portfolio,
                requested_capabilities=["macro-oracle"],
                evidence_refs=[],
                cio_synthesize=synthesize,
                risk_engine=FakeRisk(),
            )

    def test_all_standard_no_trade_reasons_are_structurally_valid(self):
        for reason in NO_TRADE_REASONS:
            with self.subTest(reason=reason):
                plan = {
                    "schema_version": "1.0.0",
                    "advisory_only": True,
                    "risk_report": {"status": "APPROVED", "policy_version": "risk-1"},
                    "decisions": [
                        {
                            "security_id": "AAA",
                            "action": "NO_TRADE",
                            "no_trade_reason": reason,
                            "reevaluation_conditions": ["Refresh or resolve the recorded blocker."],
                        }
                    ],
                }
                self.assertEqual(reason, validate_final_plan(plan)["decisions"][0]["no_trade_reason"])


if __name__ == "__main__":
    unittest.main()
