from __future__ import annotations

import unittest
from pathlib import Path

from learning.attribution import AttributionDataset
from learning.feedback import FeedbackCategory, HumanFeedback, HumanFeedbackLog
from learning.outcomes import MarketOutcome, MarketOutcomeLog, ThesisOutcome
from learning.permissions import LearningPermissionError, LearningPermissionPolicy
from learning.promotion import ApprovedVersion, PromotionAction, PromotionLedger
from learning.reflection import (
    ImprovementProposal,
    ImprovementTarget,
    ReflectionEngine,
    ReflectionRequest,
)
from learning.validation import (
    AdversarialRecord,
    RegressionRecord,
    ReplayRecord,
    ShadowRunRecord,
    ValidationBundle,
    ValidationHistory,
)
from product.contracts.base import ContractValidationError
from product.trace import DecisionTrace, TraceStage, VersionLock


def versions(suffix: str) -> VersionLock:
    return VersionLock(
        model_snapshot=f"model-{suffix}",
        skills={"portfolio-council": f"skill-{suffix}"},
        agents={"cio": f"agent-{suffix}"},
        schemas={"trace": f"schema-{suffix}"},
        mcp_adapters={"fixture": f"mcp-{suffix}"},
        risk_policy=f"risk-{suffix}",
        data_snapshot=f"data-{suffix}",
    )


def trace_snapshot():
    trace = DecisionTrace(
        "run-learning",
        "trace-learning",
        "2026-01-02T16:00:00+00:00",
        versions("1"),
    )
    stages = (
        TraceStage.INPUT,
        TraceStage.RESEARCH_PLAN,
        TraceStage.DELEGATION,
        TraceStage.TOOL_CALL,
        TraceStage.EVIDENCE,
        TraceStage.AGENT_REPORT,
        TraceStage.CIO_DRAFT,
        TraceStage.RISK_REPORT,
        TraceStage.FINAL_OUTPUT,
    )
    for minute, stage in enumerate(stages):
        trace.append(
            event_id=f"event-learning-{minute}",
            stage=stage,
            occurred_at=f"2026-01-02T15:{minute:02d}:00+00:00",
            producer_id="system",
            artifact_id=("artifact-final" if stage is TraceStage.FINAL_OUTPUT else f"artifact-{minute}"),
            payload={"stage": stage.value},
        )
    return trace.snapshot(require_complete=True)


def feedback(category: FeedbackCategory, suffix: str) -> HumanFeedback:
    return HumanFeedback(
        feedback_id=f"feedback-{suffix}",
        run_id="run-learning",
        artifact_id="artifact-5",
        category=category,
        submitted_at="2026-01-03T10:00:00+00:00",
        author_id="reviewer-1",
        details="human-labelled observation",
        versions=versions("1"),
        claim_id="claim-1" if category is FeedbackCategory.FACT_ERROR else None,
        fact_id="fact-1" if category is FeedbackCategory.FACT_ERROR else None,
        agent_id="company-analyst",
    )


def outcome(horizon: str, suffix: str) -> MarketOutcome:
    return MarketOutcome(
        outcome_id=f"outcome-{suffix}",
        run_id="run-learning",
        decision_artifact_id="artifact-final",
        benchmark_id="benchmark-1",
        horizon=horizon,
        decision_at="2026-01-02T16:00:00+00:00",
        observed_at="2026-02-02T16:00:00+00:00",
        portfolio_return=0.02,
        benchmark_return=0.01,
        max_drawdown=-0.03,
        gross_exposure=0.9,
        turnover=0.1,
        simulated_cost=0.001,
        thesis_outcome=ThesisOutcome.UNRESOLVED,
    )


def validation_bundle(*, passed: bool = True) -> ValidationBundle:
    return ValidationBundle(
        replay=ReplayRecord(
            "replay-1", "proposal-1", "version-2", ("2026-01-02T16:00:00+00:00",), ("case-1",), passed
        ),
        regression=RegressionRecord(
            "regression-1", "proposal-1", passed, passed, 0 if passed else 1, ("report-1",)
        ),
        adversarial=AdversarialRecord("adversarial-1", "proposal-1", ("attack-1",), passed),
        shadow=ShadowRunRecord(
            "shadow-1",
            "proposal-1",
            "version-2",
            "2026-02-01T10:00:00+00:00",
            "2026-02-02T10:00:00+00:00",
            ("trace-shadow-1",),
            0 if passed else 1,
            passed,
        ),
    )


class LearningObservationTests(unittest.TestCase):
    def test_all_feedback_categories_are_typed_and_append_only(self):
        log = HumanFeedbackLog()
        for index, category in enumerate(FeedbackCategory):
            log.append(feedback(category, str(index)))
        self.assertEqual(set(FeedbackCategory), {item.category for item in log.records})
        with self.assertRaises(ContractValidationError):
            log.append(log.records[0])

    def test_outcomes_are_post_decision_and_not_research_inputs(self):
        observation = outcome("1m", "1m")
        self.assertFalse(observation.research_input_eligible)
        log = MarketOutcomeLog()
        log.append(observation)
        with self.assertRaises(ContractValidationError):
            MarketOutcome(
                outcome_id="future-leak",
                run_id="run-learning",
                decision_artifact_id="artifact-final",
                benchmark_id="benchmark-1",
                horizon="invalid",
                decision_at="2026-01-02T16:00:00+00:00",
                observed_at="2026-01-01T16:00:00+00:00",
                portfolio_return=0,
                benchmark_return=0,
                max_drawdown=0,
                gross_exposure=0,
                turnover=0,
                simulated_cost=0,
                thesis_outcome=ThesisOutcome.UNRESOLVED,
            )

    def test_attribution_retains_trace_versions_feedback_benchmark_and_outcomes(self):
        trace = trace_snapshot()
        item = feedback(FeedbackCategory.REASONING_GAP, "reasoning")
        observation = outcome("1m", "1m")
        dataset = AttributionDataset.build(
            "dataset-1", (trace,), (item,), (observation,), {"run-learning": "benchmark-1"}
        )
        sample = dataset.samples[0]
        self.assertIs(trace, sample.trace)
        self.assertEqual(trace.versions, sample.versions)
        self.assertEqual((item,), sample.feedback)
        self.assertEqual((observation,), sample.outcomes)


class ReflectionAndPromotionTests(unittest.TestCase):
    def _dataset(self) -> AttributionDataset:
        return AttributionDataset.build(
            "dataset-1",
            (trace_snapshot(),),
            (feedback(FeedbackCategory.REASONING_GAP, "reflection"),),
            (outcome("1m", "reflection"),),
            {"run-learning": "benchmark-1"},
        )

    def test_reflection_can_only_return_an_improvement_proposal(self):
        request = ReflectionRequest(
            proposal_id="proposal-1",
            created_at="2026-02-03T10:00:00+00:00",
            failure_pattern="counter evidence repeatedly omitted",
            evidence_artifact_ids=("artifact-5",),
            root_cause_hypotheses=("skill stopping condition is underspecified",),
            target=ImprovementTarget.SKILL,
            proposed_change="require explicit counter-evidence search completion",
            expected_metrics={"counter_evidence_recall": 0.1},
            degradation_risks=("higher latency",),
            replay_plan="replay fixed training and holdout cases point in time",
            rollback_plan="restore the prior approved skill version",
        )
        proposal = ReflectionEngine.reflect(self._dataset(), request)
        self.assertIsInstance(proposal, ImprovementProposal)
        self.assertFalse(proposal.production_write_authorized)
        self.assertTrue(proposal.replay_plan)
        self.assertTrue(proposal.rollback_plan)

    def test_learning_permission_policy_denies_all_production_writes(self):
        root = Path(__file__).resolve().parents[1]
        policy = LearningPermissionPolicy(root)
        protected = (
            "product/skills/company-research/SKILL.md",
            "product/.codex/agents/runtime_company_analyst.toml",
            "product/contracts/evidence.py",
            "product/deterministic/risk_policy.py",
            "product/version-manifest.json",
        )
        for path in protected:
            with self.subTest(path=path), self.assertRaises(LearningPermissionError):
                policy.assert_can_write(path)
        self.assertTrue(policy.can_write("learning/reflection_proposals/proposal.json"))

    def test_validation_history_is_append_only_and_failed_candidate_cannot_promote(self):
        history = ValidationHistory()
        passing = validation_bundle(passed=True)
        history.append(passing)
        with self.assertRaises(ContractValidationError):
            history.append(passing)
        ledger = PromotionLedger(ApprovedVersion("version-1", versions("1")))
        with self.assertRaises(ContractValidationError):
            ledger.promote(
                record_id="promotion-failed",
                candidate=ApprovedVersion("version-2", versions("2")),
                validation=validation_bundle(passed=False),
                approved_by="reviewer-1",
                approved_at="2026-02-04T10:00:00+00:00",
                rationale="must fail",
                rollback_conditions=("critical regression",),
            )
        self.assertEqual("version-1", ledger.active_version.version_id)

    def test_human_promotion_and_rollback_preserve_history(self):
        original_trace = trace_snapshot()
        ledger = PromotionLedger(ApprovedVersion("version-1", versions("1")))
        promotion = ledger.promote(
            record_id="promotion-1",
            candidate=ApprovedVersion("version-2", versions("2")),
            validation=validation_bundle(passed=True),
            approved_by="reviewer-1",
            approved_at="2026-02-04T10:00:00+00:00",
            rationale="holdout and shadow gates passed",
            rollback_conditions=("critical shadow regression",),
        )
        rollback = ledger.rollback(
            record_id="rollback-1",
            approved_by="reviewer-2",
            approved_at="2026-02-05T10:00:00+00:00",
            rationale="critical regression observed",
            triggering_evaluation_record_ids=("shadow-regression-2",),
            rollback_conditions=("restore after corrected candidate passes",),
        )
        self.assertEqual(PromotionAction.PROMOTE, promotion.action)
        self.assertEqual(PromotionAction.ROLLBACK, rollback.action)
        self.assertEqual("version-1", ledger.active_version.version_id)
        self.assertEqual(2, len(ledger.records))
        self.assertEqual(2, len(ledger.approved_versions))
        self.assertTrue(original_trace.complete)


if __name__ == "__main__":
    unittest.main()
