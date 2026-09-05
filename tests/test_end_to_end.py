from __future__ import annotations

import unittest
from datetime import timedelta
from decimal import Decimal

from product.council import (
    CouncilOrchestrator,
    DeterministicRiskAdapter,
    build_council_trace,
)
from product.deterministic.policy import RiskPolicy
from product.deterministic.portfolio import (
    PriceObservation,
    SecurityRecord,
    normalize_portfolio,
)
from product.deterministic.risk import RiskEngine
from product.mcp.reference_adapter import ReferenceAdapter
from product.trace import VersionLock


D = Decimal
CUTOFF = "2026-01-02T22:00:00+00:00"


def snapshot():
    return normalize_portfolio(
        {
            "snapshot_id": "fixture-portfolio",
            "base_currency": "USD",
            "benchmark": "FIXTURE-INDEX",
            "mandate_version": "mandate/1",
            "cash": "2500",
            "declared_total_value": "10000",
            "positions": [
                {"identifier": "AAA", "quantity": "50"},
                {"identifier": "BBB", "quantity": "25"},
            ],
        },
        securities=(
            SecurityRecord("SEC-AAA", ("AAA",), "Technology"),
            SecurityRecord("SEC-BBB", ("BBB",), "Healthcare"),
        ),
        prices={
            "SEC-AAA": PriceObservation(
                "SEC-AAA", D("100"), "2026-01-02T21:00:00Z", "market-fixture", "USD", D("100000")
            ),
            "SEC-BBB": PriceObservation(
                "SEC-BBB", D("100"), "2026-01-02T21:00:00Z", "market-fixture", "USD", D("100000")
            ),
        },
        cutoff=CUTOFF,
        max_price_age=timedelta(hours=2),
    )


def policy(*, max_price_age: timedelta = timedelta(hours=2)) -> RiskPolicy:
    return RiskPolicy(
        version="risk/1",
        mandate_version="mandate/1",
        max_position_weight=D("0.65"),
        max_sector_weight=D("0.80"),
        min_cash_weight=D("0.10"),
        max_turnover=D("0.40"),
        max_adv_participation=D("0.20"),
        max_price_age=max_price_age,
    )


def portfolio_mapping() -> dict:
    return {
        "snapshot_id": "fixture-portfolio",
        "cash": 2500,
        "positions": [
            {"security_id": "SEC-AAA", "current_weight": 0.50},
            {"security_id": "SEC-BBB", "current_weight": 0.25},
        ],
    }


def research_agent(scenario: str):
    def run(request):
        assert request["isolation"] == "first-pass-no-peer-conclusions"
        assert "peer_reports" not in request
        return {
            "status": "CONFLICT" if scenario == "conflict" else "COMPLETE",
            "claims": [{"claim_id": f"claim-{request['capability']}", "evidence_refs": request["evidence_refs"]}],
            "counter_evidence_refs": list(request["evidence_refs"][-1:]),
            "data_gaps": [],
            "confidence": 0.7,
        }

    return run


def actionable_decision(target=(0.45, 0.50)) -> dict:
    return {
        "security_id": "SEC-AAA",
        "action": "HOLD" if target == (0.45, 0.50) else "ADD",
        "target_weight_range": list(target),
        "maximum_notional": 2000,
        "time_horizon": "20d",
        "thesis": "Fixture CIO synthesis based on cited company evidence.",
        "counter_thesis": "The cited operating evidence could weaken.",
        "evidence_refs": ["fact-fixture"],
        "invalidation_conditions": ["Refresh evidence if the next filing changes the thesis."],
        "unresolved_uncertainties": ["Next filing has not been published."],
    }


def synthesis(mode: str):
    def run(portfolio, reports, preflight):
        if any(report["status"] == "CONFLICT" for report in reports):
            return {
                "schema_version": "1.0.0",
                "decisions": [
                    {
                        "security_id": "SEC-AAA",
                        "action": "NO_TRADE",
                        "no_trade_reason": "MATERIAL_SOURCE_CONFLICT",
                        "reevaluation_conditions": ["Resolve the conflicting source values."],
                    }
                ],
            }
        target = (0.60, 0.70) if mode in {"revision", "veto"} else (0.45, 0.50)
        return {"schema_version": "1.0.0", "decisions": [actionable_decision(target)]}

    return run


def version_lock() -> VersionLock:
    return VersionLock(
        model_snapshot="fixture-model/1",
        skills={"portfolio-council": "1.0.0", "company-research": "1.0.0", "counter-thesis": "1.0.0"},
        agents={"cio": "1.0.0", "company-analyst": "1.0.0", "skeptic": "1.0.0"},
        schemas={"decision-trace": "1.0.0", "final-decision-plan": "1.0.0"},
        mcp_adapters={"reference": "1.0.0"},
        risk_policy="risk/1",
        data_snapshot="fixture/normal/1",
    )


class PortfolioCouncilEndToEndTests(unittest.TestCase):
    def _run(self, scenario="normal", mode="normal", *, risk_policy=None, revise=None):
        evidence = ReferenceAdapter().evidence_artifact(scenario)
        refs = [fact["fact_id"] for fact in evidence["facts"]]
        snap = snapshot()
        adapter = DeterministicRiskAdapter(snap, RiskEngine(risk_policy or policy()))
        agents = {
            "company-research": research_agent(scenario),
            "counter-thesis": research_agent(scenario),
        }
        result = CouncilOrchestrator(agents).run(
            portfolio=portfolio_mapping(),
            requested_capabilities=("company-research", "counter-thesis"),
            evidence_refs=refs,
            cio_synthesize=synthesis(mode),
            cio_revise=revise,
            risk_engine=adapter,
            decision_cutoff=CUTOFF,
        )
        return result, refs

    def test_normal_fixture_uses_real_risk_engine_and_complete_trace(self):
        result, refs = self._run()
        self.assertEqual("APPROVED", result.final_plan["risk_report"]["status"])
        self.assertTrue(result.final_plan["advisory_only"])
        trace = build_council_trace(
            run_id="run-e2e-normal",
            trace_id="trace-e2e-normal",
            decision_cutoff=CUTOFF,
            versions=version_lock(),
            result=result,
            evidence_refs=refs,
        )
        self.assertTrue(trace.complete)
        produced: set[str] = set()
        for event in trace.events:
            self.assertTrue(set(event.input_artifact_ids) <= produced)
            if event.artifact_id:
                produced.add(event.artifact_id)

    def test_stale_preflight_stops_before_agent_research(self):
        result, _ = self._run(risk_policy=policy(max_price_age=timedelta(minutes=30)))
        self.assertEqual((), result.reports)
        self.assertEqual("NO_TRADE", result.final_plan["decisions"][0]["action"])
        self.assertEqual("STALE_DATA", result.final_plan["decisions"][0]["no_trade_reason"])

    def test_material_source_conflict_yields_structured_no_trade(self):
        result, _ = self._run(scenario="conflict")
        decision = result.final_plan["decisions"][0]
        self.assertEqual("NO_TRADE", decision["action"])
        self.assertEqual("MATERIAL_SOURCE_CONFLICT", decision["no_trade_reason"])
        self.assertTrue(decision["reevaluation_conditions"])

    def test_risk_revision_can_succeed_once(self):
        result, refs = self._run(
            mode="revision",
            revise=lambda draft, risk: {
                "schema_version": "1.0.0",
                "decisions": [actionable_decision((0.55, 0.60))],
            },
        )
        self.assertEqual(2, len(result.risk_reports))
        self.assertEqual("REVISE_REQUIRED", result.risk_reports[0]["status"])
        self.assertEqual("APPROVED", result.risk_reports[1]["status"])
        trace = build_council_trace(
            run_id="run-e2e-revision",
            trace_id="trace-e2e-revision",
            decision_cutoff=CUTOFF,
            versions=version_lock(),
            result=result,
            evidence_refs=refs,
        )
        self.assertTrue(trace.complete)

    def test_second_noncompliant_draft_is_final_veto(self):
        result, _ = self._run(mode="veto", revise=lambda draft, risk: draft)
        self.assertEqual(2, len(result.risk_reports))
        self.assertEqual("NO_TRADE", result.final_plan["decisions"][0]["action"])
        self.assertEqual("RISK_VETO", result.final_plan["decisions"][0]["no_trade_reason"])


if __name__ == "__main__":
    unittest.main()
