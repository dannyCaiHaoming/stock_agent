"""Candidate version holdout and promotion gates."""

from .gates import (
    CandidateEvaluation,
    HoldoutStrategy,
    PromotionDecision,
    PromotionGate,
    SplitMetrics,
)
from .runtime_gate import RuntimePromotionError, run_promotion_gate
from .test_evidence import (
    DeterministicTestEvidenceError,
    run_deterministic_test_evidence,
    verify_deterministic_test_evidence,
)

__all__ = [
    "CandidateEvaluation",
    "HoldoutStrategy",
    "PromotionDecision",
    "PromotionGate",
    "RuntimePromotionError",
    "DeterministicTestEvidenceError",
    "run_promotion_gate",
    "run_deterministic_test_evidence",
    "verify_deterministic_test_evidence",
    "SplitMetrics",
]
