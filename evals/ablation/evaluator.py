"""Compare quality gains against token and latency costs."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class VariantRun:
    variant_id: str
    agents: tuple[str, ...]
    quality_score: float
    token_count: int
    latency_ms: int
    sample_count: int

    def __post_init__(self) -> None:
        if not self.variant_id.strip() or not self.agents:
            raise ValueError("variant_id and agents are required")
        if not isfinite(self.quality_score) or not 0 <= self.quality_score <= 1:
            raise ValueError("quality_score must be between 0 and 1")
        if self.token_count < 0 or self.latency_ms < 0 or self.sample_count < 1:
            raise ValueError("costs must be non-negative and sample_count must be positive")


@dataclass(frozen=True, slots=True)
class AblationComparison:
    baseline_id: str
    candidate_id: str
    quality_gain: float
    token_delta: int
    latency_delta_ms: int
    accepted: bool
    reason: str


class AblationEvaluator:
    def __init__(self, *, minimum_quality_gain: float):
        if not isfinite(minimum_quality_gain) or minimum_quality_gain < 0:
            raise ValueError("minimum_quality_gain must be non-negative")
        self.minimum_quality_gain = minimum_quality_gain

    def compare(self, baseline: VariantRun, candidate: VariantRun) -> AblationComparison:
        if baseline.sample_count != candidate.sample_count:
            raise ValueError("ablation variants must use the same holdout sample count")
        gain = candidate.quality_score - baseline.quality_score
        accepted = gain >= self.minimum_quality_gain
        return AblationComparison(
            baseline_id=baseline.variant_id,
            candidate_id=candidate.variant_id,
            quality_gain=gain,
            token_delta=candidate.token_count - baseline.token_count,
            latency_delta_ms=candidate.latency_ms - baseline.latency_ms,
            accepted=accepted,
            reason=(
                "quality gain meets the predeclared threshold"
                if accepted
                else "added agents did not produce sufficient quality gain"
            ),
        )
