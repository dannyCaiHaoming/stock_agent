from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evals.ablation import AblationEvaluator, VariantRun
from evals.grading import (
    DeterministicGateInput,
    DeterministicGateSuite,
    EvidenceReasoningCase,
    EvidenceReasoningGrader,
)
from evals.outcomes import HorizonOutcome, MultiHorizonOutcomeEvaluator, ThesisEventStatus
from evals.promotion import (
    CandidateEvaluation,
    HoldoutStrategy,
    PromotionGate,
    SplitMetrics,
)
from product.contracts.base import ContractValidationError, ProducerKind, ProducerRef
from product.contracts.evidence import FactEnvelope
from product.trace import (
    AppendOnlyTraceStore,
    DecisionTrace,
    PointInTimeReplay,
    TraceStage,
    TraceValidationError,
    VersionLock,
)


def version_lock(suffix: str = "1") -> VersionLock:
    return VersionLock(
        model_snapshot=f"model-{suffix}",
        skills={"portfolio-council": f"skill-{suffix}"},
        agents={"cio": f"agent-{suffix}"},
        schemas={"decision-trace": f"schema-{suffix}"},
        mcp_adapters={"fixture": f"mcp-{suffix}"},
        risk_policy=f"risk-{suffix}",
        data_snapshot=f"data-{suffix}",
    )


def complete_trace(*, suffix: str = "1"):
    trace = DecisionTrace(
        run_id=f"run-{suffix}",
        trace_id=f"trace-{suffix}",
        decision_cutoff="2026-01-02T16:00:00+00:00",
        versions=version_lock(suffix),
    )
    stages = (
        (TraceStage.INPUT, "portfolio"),
        (TraceStage.RESEARCH_PLAN, "plan"),
        (TraceStage.DELEGATION, "delegation"),
        (TraceStage.TOOL_CALL, "tool-call"),
        (TraceStage.EVIDENCE, "evidence"),
        (TraceStage.AGENT_REPORT, "report"),
        (TraceStage.CIO_DRAFT, "draft"),
        (TraceStage.RISK_REPORT, "risk"),
        (TraceStage.FINAL_OUTPUT, "final"),
    )
    for minute, (stage, artifact) in enumerate(stages):
        trace.append(
            event_id=f"event-{suffix}-{minute}",
            stage=stage,
            occurred_at=f"2026-01-02T15:{minute:02d}:00+00:00",
            producer_id="system",
            artifact_id=f"artifact-{suffix}-{artifact}",
            input_artifact_ids=(),
            payload={"stage": stage.value},
        )
    return trace.snapshot(require_complete=True)


class DecisionTraceTests(unittest.TestCase):
    def test_complete_trace_is_sealed_and_serializable(self):
        snapshot = complete_trace()
        self.assertTrue(snapshot.complete)
        self.assertTrue(snapshot.promotable)
        self.assertIn('"FINAL_OUTPUT"', snapshot.to_json())

    def test_final_output_requires_all_stages(self):
        trace = DecisionTrace("run-x", "trace-x", "2026-01-02T16:00:00+00:00", version_lock())
        with self.assertRaises(TraceValidationError):
            trace.append(
                event_id="event-final",
                stage=TraceStage.FINAL_OUTPUT,
                occurred_at="2026-01-02T15:00:00+00:00",
                producer_id="cio",
                artifact_id="artifact-final",
                payload={},
            )
        self.assertEqual((), trace.snapshot().events)

    def test_version_lock_is_fail_closed(self):
        with self.assertRaises(ContractValidationError):
            VersionLock(
                model_snapshot="model",
                skills={},
                agents={"cio": "1"},
                schemas={"trace": "1"},
                mcp_adapters={"fixture": "1"},
                risk_policy="risk",
                data_snapshot="data",
            )

    def test_trace_store_never_overwrites_a_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AppendOnlyTraceStore(Path(directory) / "traces.jsonl")
            snapshot = complete_trace()
            store.append(snapshot)
            with self.assertRaises(TraceValidationError):
                store.append(snapshot)
            records = tuple(store.iter_records())
            self.assertEqual(1, len(records))
            self.assertEqual("trace-1", records[0]["trace_id"])

    def test_point_in_time_replay_excludes_future_revisions(self):
        common = dict(
            security_id="security-1",
            field_or_statement="revenue",
            value=100,
            unit="USD",
            source_type="filing",
            source_locator="fixture://filing",
            as_of="2025-12-31",
            source_version_or_hash="hash",
        )
        original = FactEnvelope(
            fact_id="fact-original",
            source_id="source-original",
            retrieved_at="2026-01-02T10:00:00+00:00",
            **common,
        )
        revision = FactEnvelope(
            fact_id="fact-revision",
            source_id="source-revision",
            retrieved_at="2026-01-03T10:00:00+00:00",
            **common,
        )
        selection = PointInTimeReplay.select_facts(
            (revision, original), "2026-01-02T16:00:00+00:00"
        )
        self.assertEqual((original,), selection.facts)
        self.assertEqual(("fact-revision",), selection.excluded_future_fact_ids)


class EvaluationTests(unittest.TestCase):
    def test_deterministic_hard_gates_are_repeatable(self):
        inputs = DeterministicGateInput(True, True, False, True, True, True)
        first = DeterministicGateSuite.evaluate(inputs)
        second = DeterministicGateSuite.evaluate(inputs)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertFalse(first.passed)
        self.assertEqual(("risk_engine",), first.failed_gate_names)

    def test_reasoning_grader_matches_human_labels(self):
        good = EvidenceReasoningCase(
            case_id="good",
            citation_support=(True, True),
            thesis_present=True,
            counter_thesis_present=True,
            conflict_handled=True,
            invalidation_conditions=("margin falls below threshold",),
            confidence=0.8,
            outcome_label=True,
            human_accept=True,
        )
        poor = EvidenceReasoningCase(
            case_id="poor",
            citation_support=(False, False),
            thesis_present=True,
            counter_thesis_present=False,
            conflict_handled=False,
            invalidation_conditions=(),
            confidence=0.7,
            outcome_label=False,
            human_accept=False,
        )
        report = EvidenceReasoningGrader().validate_against_human_labels((good, poor))
        self.assertTrue(report.accepted)
        self.assertEqual(1.0, report.human_agreement)
        self.assertIsNotNone(report.grades[0].calibration_loss)

    def test_outcome_eval_is_multi_horizon_and_has_no_correctness_label(self):
        observations = (
            HorizonOutcome("1m", -0.02, -0.03, -0.05, 0.9, 0.1, 0.001, ThesisEventStatus.UNRESOLVED),
            HorizonOutcome("6m", 0.08, 0.04, -0.08, 0.85, 0.2, 0.002, ThesisEventStatus.REALIZED),
        )
        report = MultiHorizonOutcomeEvaluator.evaluate(observations)
        self.assertIsNone(report.correctness_label)
        self.assertEqual(("1m", 0.009999999999999998), report.relative_returns[0])
        with self.assertRaises(ValueError):
            MultiHorizonOutcomeEvaluator.evaluate(observations[:1])

    def test_ablation_reports_quality_tokens_and_latency(self):
        baseline = VariantRun("cio", ("cio",), 0.70, 1000, 100, 20)
        candidate = VariantRun("council", ("cio", "skeptic"), 0.76, 1800, 160, 20)
        result = AblationEvaluator(minimum_quality_gain=0.05).compare(baseline, candidate)
        self.assertTrue(result.accepted)
        self.assertEqual(800, result.token_delta)
        self.assertEqual(60, result.latency_delta_ms)

    def test_promotion_rejects_training_gain_with_holdout_regression(self):
        strategy = HoldoutStrategy("fixed-v1", ("train-1",), ("holdout-1",))
        evaluation = CandidateEvaluation(
            candidate_version="candidate-2",
            strategy=strategy,
            training=SplitMetrics(0.6, 0.9),
            holdout=SplitMetrics(0.8, 0.79),
            deterministic_gates_passed=True,
            hard_constraint_regressions=0,
            adversarial_passed=True,
            ablation_passed=True,
        )
        decision = PromotionGate.evaluate(evaluation)
        self.assertFalse(decision.accepted)
        self.assertIn("holdout quality regressed", decision.reasons)


if __name__ == "__main__":
    unittest.main()
