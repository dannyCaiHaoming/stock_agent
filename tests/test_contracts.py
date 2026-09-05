"""Focused contract tests for OpenSpec tasks 2.1 through 2.6."""

from __future__ import annotations

import json
import unittest

from product.contracts import (
    AdvisoryPlanItem,
    AgentResearchReport,
    ArtifactEnvelope,
    Assumption,
    CatalystEvent,
    CatalystMap,
    Claim,
    ClaimKind,
    ContractValidationError,
    CounterThesisReport,
    CouncilDraftDecision,
    DecisionAction,
    DecisionTrace,
    EvidenceBundle,
    FactEnvelope,
    FeedbackType,
    FinalDecisionPlan,
    FreshnessStatus,
    HumanFeedback,
    IdentifierResolution,
    ImprovementProposal,
    ImprovementTarget,
    Mandate,
    MarketOutcome,
    NoTradeReason,
    PortfolioInput,
    PortfolioPositionInput,
    PortfolioSnapshot,
    ProducerKind,
    ProducerRef,
    PromotionRecord,
    PromotionStatus,
    RiskCheckReport,
    RiskStatus,
    SecurityIdentifier,
    SnapshotPosition,
    TargetWeightRange,
    ThesisEventStatus,
    TraceEvent,
    ValuationAssessment,
    ValuationScenario,
    VersionManifest,
    validate_artifact_lineage,
)


NOW = "2026-09-04T09:30:00+08:00"
LATER = "2026-10-04T09:30:00+08:00"


def envelope(
    artifact_id: str,
    *inputs: str,
    run_id: str = "run-001",
    trace_id: str = "trace-001",
    kind: ProducerKind = ProducerKind.SYSTEM,
    producer_id: str = "contract-tests",
) -> ArtifactEnvelope:
    return ArtifactEnvelope(
        schema_version="1.0.0",
        artifact_id=artifact_id,
        run_id=run_id,
        trace_id=trace_id,
        producer=ProducerRef(kind=kind, producer_id=producer_id, version="1.0.0"),
        created_at=NOW,
        input_artifact_ids=tuple(inputs),
    )


def resolved_security(value: str = "AAA", canonical_id: str = "security-aaa") -> SecurityIdentifier:
    return SecurityIdentifier(
        scheme="TICKER",
        value=value,
        market="TEST",
        resolution=IdentifierResolution.RESOLVED,
        canonical_id=canonical_id,
    )


def fact(**overrides: object) -> FactEnvelope:
    values: dict[str, object] = {
        "fact_id": "fact-revenue",
        "security_id": "security-aaa",
        "field_or_statement": "Revenue",
        "value": 100.0,
        "unit": "USD_million",
        "source_id": "source-filing-001",
        "source_type": "REGULATORY_FILING",
        "source_locator": "filing://issuer/2026-q2#revenue",
        "as_of": "2026-06-30",
        "retrieved_at": NOW,
        "source_version_or_hash": "sha256:abc123",
        "freshness_status": FreshnessStatus.CURRENT,
        "quality_flags": (),
    }
    values.update(overrides)
    return FactEnvelope(**values)  # type: ignore[arg-type]


def mandate() -> Mandate:
    return Mandate(
        envelope=envelope("artifact-mandate"),
        mandate_id="mandate-test",
        mandate_version="1.0.0",
        base_currency="USD",
        allowed_markets=("TEST",),
        benchmark_id="benchmark-test",
    )


def portfolio_input(*positions: PortfolioPositionInput, env: ArtifactEnvelope | None = None) -> PortfolioInput:
    return PortfolioInput(
        envelope=env or envelope("artifact-portfolio-input", "artifact-mandate"),
        positions=positions,
        cash=1_000.0,
        base_currency="USD",
        benchmark_id="benchmark-test",
        mandate_artifact_id="artifact-mandate",
    )


def versions(model: str = "model-snapshot-1") -> VersionManifest:
    return VersionManifest(
        model_snapshot=model,
        skill_versions={"portfolio-council": "1.0.0"},
        agent_versions={"runtime-company-analyst": "1.0.0"},
        schema_versions={"artifact-envelope": "1.0.0"},
        mcp_adapter_versions={"fixture-adapter": "1.0.0"},
        risk_policy_version="risk-policy-1",
        data_snapshot_version="data-snapshot-1",
    )


class CommonEnvelopeTests(unittest.TestCase):
    def test_common_envelope_is_versioned_json_and_lineage_resolves(self) -> None:
        policy = mandate()
        portfolio = portfolio_input(
            PortfolioPositionInput(security=resolved_security(), quantity=10, cost_basis=50.0)
        )

        validate_artifact_lineage((policy, portfolio))
        payload = json.loads(portfolio.to_json())

        self.assertEqual(payload["envelope"]["schema_version"], "1.0.0")
        self.assertEqual(payload["envelope"]["producer"]["version"], "1.0.0")
        self.assertEqual(payload["envelope"]["input_artifact_ids"], ["artifact-mandate"])

    def test_unknown_and_cross_run_lineage_are_rejected(self) -> None:
        portfolio = portfolio_input(
            PortfolioPositionInput(security=resolved_security(), quantity=10),
            env=envelope("artifact-portfolio-input", "artifact-mandate"),
        )
        with self.assertRaisesRegex(ContractValidationError, "unknown input artifact"):
            validate_artifact_lineage((portfolio,))

        other_run_mandate = Mandate(
            envelope=envelope("artifact-mandate", run_id="run-002"),
            mandate_id="mandate-test",
            mandate_version="1.0.0",
            base_currency="USD",
            allowed_markets=("TEST",),
            benchmark_id="benchmark-test",
        )
        with self.assertRaisesRegex(ContractValidationError, "different run_id"):
            validate_artifact_lineage((other_run_mandate, portfolio))

    def test_self_reference_and_duplicate_inputs_are_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            envelope("artifact-self", "artifact-self")
        with self.assertRaises(ContractValidationError):
            envelope("artifact-child", "artifact-parent", "artifact-parent")


class EvidenceContractTests(unittest.TestCase):
    def test_fact_requires_source_and_bitemporal_fields(self) -> None:
        for field_name in ("source_id", "as_of", "retrieved_at"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ContractValidationError):
                    fact(**{field_name: ""})

    def test_fact_rejects_naive_retrieval_time_and_non_json_value(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "UTC offset"):
            fact(retrieved_at="2026-09-04T09:30:00")
        with self.assertRaisesRegex(ContractValidationError, "not JSON-compatible"):
            fact(value=object())

    def test_evidence_bundle_closes_claim_references(self) -> None:
        evidence_fact = fact()
        assumption = Assumption(
            assumption_id="assumption-margin",
            statement="Margins remain near the recent range",
            rationale="Scenario input, not an observed fact",
        )
        claim = Claim(
            claim_id="claim-growth",
            statement="Revenue growth is durable under the stated assumption",
            kind=ClaimKind.INTERPRETIVE,
            evidence_fact_ids=(evidence_fact.fact_id,),
            assumption_ids=(assumption.assumption_id,),
            counter_evidence_fact_ids=(evidence_fact.fact_id,),
        )
        bundle = EvidenceBundle(
            envelope=envelope("artifact-evidence"),
            facts=(evidence_fact,),
            claims=(claim,),
            assumptions=(assumption,),
        )

        self.assertEqual(bundle.claims[0].evidence_fact_ids, ("fact-revenue",))
        self.assertEqual(bundle.claims[0].assumption_ids, ("assumption-margin",))
        self.assertEqual(bundle.claims[0].counter_evidence_fact_ids, ("fact-revenue",))

        with self.assertRaisesRegex(ContractValidationError, "unknown facts"):
            EvidenceBundle(
                envelope=envelope("artifact-broken-evidence"),
                facts=(evidence_fact,),
                claims=(
                    Claim(
                        claim_id="claim-broken",
                        statement="Unsupported reference",
                        kind=ClaimKind.FACTUAL,
                        evidence_fact_ids=("fact-missing",),
                    ),
                ),
            )

    def test_claim_must_reference_fact_or_explicit_assumption(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "at least one fact"):
            Claim(
                claim_id="claim-unsupported",
                statement="Unsupported material claim",
                kind=ClaimKind.INTERPRETIVE,
            )


class PortfolioContractTests(unittest.TestCase):
    def test_valid_resolved_portfolio_input(self) -> None:
        portfolio = portfolio_input(
            PortfolioPositionInput(security=resolved_security(), quantity=10, cost_basis=40.0)
        )
        self.assertEqual(portfolio.positions[0].security.canonical_id, "security-aaa")

    def test_normalized_snapshot_keeps_source_and_mandate_lineage(self) -> None:
        snapshot = PortfolioSnapshot(
            envelope=envelope(
                "artifact-portfolio-snapshot", "artifact-portfolio-input", "artifact-mandate"
            ),
            source_portfolio_artifact_id="artifact-portfolio-input",
            mandate_artifact_id="artifact-mandate",
            as_of=NOW,
            positions=(
                SnapshotPosition(
                    security_id="security-aaa",
                    quantity=10,
                    price=50.0,
                    market_value=500.0,
                    weight=0.33,
                    price_as_of=NOW,
                ),
            ),
            cash=1_000.0,
            total_value=1_500.0,
            base_currency="USD",
            benchmark_id="benchmark-test",
        )
        payload = snapshot.to_dict()
        self.assertEqual(payload["source_portfolio_artifact_id"], "artifact-portfolio-input")
        self.assertEqual(payload["mandate_artifact_id"], "artifact-mandate")

    def test_duplicate_canonical_security_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "must not contain duplicates"):
            portfolio_input(
                PortfolioPositionInput(security=resolved_security("AAA"), quantity=10),
                PortfolioPositionInput(security=resolved_security("AAA.US"), quantity=5),
            )

    def test_unknown_security_is_rejected_without_guessing(self) -> None:
        unknown = SecurityIdentifier(
            scheme="TICKER",
            value="UNKNOWN",
            market="TEST",
            resolution=IdentifierResolution.UNKNOWN,
        )
        with self.assertRaisesRegex(ContractValidationError, "must not guess"):
            portfolio_input(PortfolioPositionInput(security=unknown, quantity=10))

    def test_ambiguous_security_is_rejected_without_guessing(self) -> None:
        ambiguous = SecurityIdentifier(
            scheme="TICKER",
            value="ABC",
            market="TEST",
            resolution=IdentifierResolution.AMBIGUOUS,
            candidates=("security-abc-a", "security-abc-b"),
        )
        with self.assertRaisesRegex(ContractValidationError, "must not guess"):
            portfolio_input(PortfolioPositionInput(security=ambiguous, quantity=10))


class ResearchContractTests(unittest.TestCase):
    def test_research_artifacts_keep_facts_assumptions_counter_evidence_and_gaps_distinct(self) -> None:
        report = AgentResearchReport(
            envelope=envelope("artifact-research", "artifact-evidence"),
            scope="Company quality and valuation",
            security_ids=("security-aaa",),
            claim_ids=("claim-growth",),
            fact_ids=("fact-revenue",),
            assumption_ids=("assumption-margin",),
            counter_evidence_fact_ids=("fact-competition",),
            uncertainties=("Demand visibility is limited",),
            data_gaps=("No current customer concentration disclosure",),
            invalidation_conditions=("Revenue growth falls below the scenario floor",),
            confidence=0.6,
            confidence_rationale="Evidence is current but incomplete",
        )
        valuation = ValuationAssessment(
            envelope=envelope("artifact-valuation", "artifact-evidence"),
            security_id="security-aaa",
            scenarios=(
                ValuationScenario(
                    name="base",
                    deterministic_method="discounted-cash-flow",
                    input_fact_ids=("fact-revenue",),
                    assumption_ids=("assumption-margin",),
                    result_value=125.0,
                    currency="USD",
                ),
            ),
            interpretation_claim_ids=("claim-valuation",),
            uncertainties=("Discount rate uncertainty",),
            data_gaps=("No segment forecast",),
        )
        catalyst = CatalystMap(
            envelope=envelope("artifact-catalyst", "artifact-evidence"),
            security_id="security-aaa",
            events=(
                CatalystEvent(
                    event_id="event-results",
                    description="Scheduled results release",
                    window_start="2026-10-01",
                    window_end="2026-10-15",
                    supporting_fact_ids=("fact-calendar",),
                    interpretation="May resolve the stated demand uncertainty",
                ),
            ),
            counter_evidence_fact_ids=("fact-delay-risk",),
            uncertainties=("Release date may change",),
            data_gaps=("No confirmed investor-day agenda",),
        )
        counter = CounterThesisReport(
            envelope=envelope("artifact-counter", "artifact-evidence"),
            security_id="security-aaa",
            challenged_claim_ids=("claim-growth",),
            counter_claim_ids=("claim-competition",),
            supporting_fact_ids=("fact-competition",),
            assumption_ids=("assumption-margin",),
            unresolved_conflicts=("Sources disagree on market share",),
            data_gaps=("No independent channel check",),
            invalidation_conditions=("Market share stabilizes",),
            confidence=0.5,
            confidence_rationale="Counter-evidence is material but incomplete",
        )

        self.assertNotEqual(report.fact_ids, report.assumption_ids)
        self.assertEqual(report.counter_evidence_fact_ids, ("fact-competition",))
        self.assertTrue(report.data_gaps)
        for artifact in (report, valuation, catalyst, counter):
            json.loads(artifact.to_json())

    def test_research_report_cannot_blur_all_support_into_untyped_claims(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "facts and assumptions"):
            AgentResearchReport(
                envelope=envelope("artifact-research", "artifact-evidence"),
                scope="Company research",
                security_ids=("security-aaa",),
                claim_ids=("claim-growth",),
                fact_ids=(),
                assumption_ids=(),
                counter_evidence_fact_ids=(),
                uncertainties=(),
                data_gaps=("All supporting data is absent",),
                invalidation_conditions=("New evidence becomes available",),
                confidence=0.1,
                confidence_rationale="No support",
            )


class DecisionAndRiskContractTests(unittest.TestCase):
    def actionable_draft(self) -> CouncilDraftDecision:
        return CouncilDraftDecision(
            envelope=envelope("artifact-draft", "artifact-research"),
            action=DecisionAction.ADD,
            security_id="security-aaa",
            current_weight=0.05,
            target_weight_range=TargetWeightRange(0.06, 0.08),
            maximum_notional=5_000.0,
            time_horizon="3-12 months",
            thesis_claim_ids=("claim-growth",),
            counter_thesis_claim_ids=("claim-competition",),
            evidence_fact_ids=("fact-revenue",),
            invalidation_conditions=("Revenue growth falls below the scenario floor",),
            unresolved_uncertainties=("Demand visibility",),
            confidence=0.6,
        )

    def test_action_risk_and_advisory_only_contracts(self) -> None:
        draft = self.actionable_draft()
        risk = RiskCheckReport(
            envelope=envelope("artifact-risk", "artifact-draft", kind=ProducerKind.RISK_ENGINE),
            status=RiskStatus.APPROVED,
            policy_version="risk-policy-1",
            draft_artifact_id="artifact-draft",
            pre_trade_metrics={"cash_weight": 0.2},
            post_trade_metrics={"cash_weight": 0.17},
        )
        item = AdvisoryPlanItem(
            action=DecisionAction.ADD,
            security_id="security-aaa",
            current_weight=0.05,
            target_weight_range=TargetWeightRange(0.06, 0.08),
            maximum_notional=5_000.0,
            time_horizon="3-12 months",
            thesis_claim_ids=("claim-growth",),
            counter_thesis_claim_ids=("claim-competition",),
            evidence_fact_ids=("fact-revenue",),
            invalidation_conditions=("Revenue growth falls below the scenario floor",),
        )
        final = FinalDecisionPlan(
            envelope=envelope("artifact-final", "artifact-draft", "artifact-risk"),
            draft_artifact_id="artifact-draft",
            risk_report_artifact_id="artifact-risk",
            risk_status=RiskStatus.APPROVED,
            items=(item,),
            advisory_only=True,
        )

        validate_artifact_lineage((draft, risk, final), external_artifact_ids=("artifact-research",))
        self.assertTrue(final.to_dict()["advisory_only"])
        self.assertEqual(final.to_dict()["items"][0]["action"], "ADD")

    def test_invalid_action_range_and_advisory_flag_are_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            TargetWeightRange(0.2, 0.1)

        draft = self.actionable_draft()
        with self.assertRaisesRegex(ContractValidationError, "DecisionAction"):
            CouncilDraftDecision(
                envelope=envelope("artifact-invalid-draft"),
                action="PURCHASE",  # type: ignore[arg-type]
                security_id="security-aaa",
                current_weight=0.0,
                target_weight_range=TargetWeightRange(0.01, 0.02),
                maximum_notional=100.0,
                time_horizon="one year",
                thesis_claim_ids=("claim-growth",),
                counter_thesis_claim_ids=(),
                evidence_fact_ids=("fact-revenue",),
                invalidation_conditions=("Evidence changes",),
                unresolved_uncertainties=(),
                confidence=0.5,
            )

        with self.assertRaisesRegex(ContractValidationError, "advisory_only"):
            FinalDecisionPlan(
                envelope=envelope("artifact-final", "artifact-draft", "artifact-risk"),
                draft_artifact_id="artifact-draft",
                risk_report_artifact_id="artifact-risk",
                risk_status=RiskStatus.APPROVED,
                items=(
                    AdvisoryPlanItem(
                        action=DecisionAction.HOLD,
                        security_id="security-aaa",
                        current_weight=0.05,
                        target_weight_range=TargetWeightRange(0.05, 0.05),
                        maximum_notional=None,
                        time_horizon="3-12 months",
                        thesis_claim_ids=("claim-growth",),
                        counter_thesis_claim_ids=(),
                        evidence_fact_ids=("fact-revenue",),
                        invalidation_conditions=("Evidence changes",),
                    ),
                ),
                advisory_only=False,
            )
        self.assertEqual(draft.action, DecisionAction.ADD)

    def test_non_approved_risk_cannot_emit_actionable_item(self) -> None:
        item = AdvisoryPlanItem(
            action=DecisionAction.BUY,
            security_id="security-aaa",
            current_weight=0.0,
            target_weight_range=TargetWeightRange(0.01, 0.03),
            maximum_notional=1_000.0,
            time_horizon="3-12 months",
            thesis_claim_ids=("claim-growth",),
            counter_thesis_claim_ids=(),
            evidence_fact_ids=("fact-revenue",),
            invalidation_conditions=("Thesis evidence changes",),
        )
        with self.assertRaisesRegex(ContractValidationError, "non-approved"):
            FinalDecisionPlan(
                envelope=envelope("artifact-final", "artifact-draft", "artifact-risk"),
                draft_artifact_id="artifact-draft",
                risk_report_artifact_id="artifact-risk",
                risk_status=RiskStatus.REJECTED,
                items=(item,),
            )

    def test_no_trade_is_structured_and_has_reevaluation_condition(self) -> None:
        no_trade = AdvisoryPlanItem(
            action=DecisionAction.NO_TRADE,
            security_id="security-aaa",
            current_weight=0.05,
            target_weight_range=None,
            maximum_notional=None,
            time_horizon="until evidence refresh",
            thesis_claim_ids=(),
            counter_thesis_claim_ids=(),
            evidence_fact_ids=(),
            invalidation_conditions=(),
            no_trade_reason=NoTradeReason.STALE_DATA,
            no_trade_explanation="A material filing is stale",
            reevaluation_conditions=("Retrieve the current filing",),
        )
        self.assertEqual(no_trade.no_trade_reason, NoTradeReason.STALE_DATA)


class LearningLinkageContractTests(unittest.TestCase):
    def test_trace_feedback_outcome_proposal_and_promotion_link_by_run_and_artifact(self) -> None:
        trace = DecisionTrace(
            envelope=envelope("artifact-trace", "artifact-final"),
            decision_cutoff=NOW,
            versions=versions(),
            artifact_ids=("artifact-final",),
            events=(
                TraceEvent(
                    sequence=0,
                    occurred_at=NOW,
                    event_type="FINAL_PLAN_CREATED",
                    artifact_ids=("artifact-final",),
                    details={"advisory_only": True},
                ),
            ),
        )
        feedback = HumanFeedback(
            envelope=envelope("artifact-feedback", "artifact-final", kind=ProducerKind.HUMAN),
            target_artifact_id="artifact-final",
            feedback_type=FeedbackType.EVIDENCE_MISSING,
            submitted_at=LATER,
            notes="The conclusion omitted a material source",
            target_claim_id="claim-growth",
            target_fact_id="fact-revenue",
            target_agent_id="runtime-company-analyst",
        )
        outcome = MarketOutcome(
            envelope=envelope("artifact-outcome", "artifact-final"),
            decision_artifact_id="artifact-final",
            observed_at=LATER,
            horizon_days=30,
            portfolio_return=-0.02,
            benchmark_return=-0.01,
            thesis_event_status=ThesisEventStatus.PARTIAL,
            observations=("Only one thesis milestone was observable",),
        )
        proposal = ImprovementProposal(
            envelope=envelope(
                "artifact-proposal",
                "artifact-trace",
                "artifact-feedback",
                "artifact-outcome",
                kind=ProducerKind.REFLECTION,
            ),
            trace_artifact_ids=("artifact-trace",),
            observation_artifact_ids=("artifact-feedback", "artifact-outcome"),
            failure_mode="Material counter-evidence was omitted",
            root_cause_hypothesis="Evidence selection stopped too early",
            target=ImprovementTarget.SKILL,
            proposed_change="Require an explicit counter-evidence retrieval pass",
            expected_metrics=("counter-evidence coverage",),
            regression_risks=("higher latency",),
            replay_plan="Replay the held-out evidence omission set",
            rollback_plan="Restore the previous approved Skill version",
        )
        promotion = PromotionRecord(
            envelope=envelope(
                "artifact-promotion", "artifact-proposal", "artifact-evaluation", kind=ProducerKind.HUMAN
            ),
            proposal_artifact_id="artifact-proposal",
            evaluation_artifact_ids=("artifact-evaluation",),
            previous_versions=versions("model-snapshot-1"),
            candidate_versions=versions("model-snapshot-2"),
            status=PromotionStatus.APPROVED,
            approved_by="reviewer-001",
            decided_at=LATER,
            rollback_conditions=("held-out evidence support regresses",),
        )

        validate_artifact_lineage(
            (trace, feedback, outcome, proposal, promotion),
            external_artifact_ids=("artifact-final", "artifact-evaluation"),
        )
        self.assertEqual(
            {artifact.envelope.run_id for artifact in (trace, feedback, outcome, proposal, promotion)},
            {"run-001"},
        )
        self.assertIn(feedback.envelope.artifact_id, proposal.envelope.input_artifact_ids)
        self.assertEqual(promotion.proposal_artifact_id, proposal.envelope.artifact_id)
        for artifact in (trace, feedback, outcome, proposal, promotion):
            json.loads(artifact.to_json())

    def test_explicit_link_must_appear_in_common_envelope(self) -> None:
        with self.assertRaisesRegex(ContractValidationError, "input_artifact_ids"):
            HumanFeedback(
                envelope=envelope("artifact-feedback"),
                target_artifact_id="artifact-final",
                feedback_type=FeedbackType.JUDGMENT_DISAGREEMENT,
                submitted_at=LATER,
                notes="I disagree with the interpretation, not the facts",
            )


if __name__ == "__main__":
    unittest.main()
