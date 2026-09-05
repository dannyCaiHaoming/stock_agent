"""Candidate version holdout and promotion gates."""

from .gates import (
    CandidateEvaluation,
    HoldoutStrategy,
    PromotionDecision,
    PromotionGate,
    SplitMetrics,
)

__all__ = [
    "CandidateEvaluation",
    "HoldoutStrategy",
    "PromotionDecision",
    "PromotionGate",
    "SplitMetrics",
]
