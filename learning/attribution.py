"""Point-in-time attribution samples retaining original source artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from product.contracts.base import ContractValidationError, require_identifier
from product.trace import DecisionTraceSnapshot, TraceStage

from .feedback import HumanFeedback
from .outcomes import MarketOutcome


@dataclass(frozen=True, slots=True)
class AttributionSample:
    sample_id: str
    trace: DecisionTraceSnapshot
    feedback: tuple[HumanFeedback, ...]
    outcomes: tuple[MarketOutcome, ...]
    benchmark_id: str

    def __post_init__(self) -> None:
        require_identifier(self.sample_id, "sample_id")
        require_identifier(self.benchmark_id, "benchmark_id")
        self.trace.require_complete()
        artifact_ids = {event.artifact_id for event in self.trace.events if event.artifact_id}
        for item in self.feedback:
            if item.run_id != self.trace.run_id or item.artifact_id not in artifact_ids:
                raise ContractValidationError("feedback must reference an artifact in the original trace")
        final_ids = {
            event.artifact_id
            for event in self.trace.events
            if event.stage is TraceStage.FINAL_OUTPUT and event.artifact_id
        }
        for item in self.outcomes:
            if item.run_id != self.trace.run_id or item.decision_artifact_id not in final_ids:
                raise ContractValidationError("outcome must reference the trace's final decision artifact")
            if item.benchmark_id != self.benchmark_id:
                raise ContractValidationError("outcome benchmark must match the attribution sample")

    @property
    def versions(self):
        return self.trace.versions


@dataclass(frozen=True, slots=True)
class AttributionDataset:
    dataset_id: str
    samples: tuple[AttributionSample, ...]

    def __post_init__(self) -> None:
        require_identifier(self.dataset_id, "dataset_id")
        if not self.samples:
            raise ContractValidationError("attribution dataset must not be empty")
        ids = [sample.sample_id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ContractValidationError("attribution sample IDs must be unique")

    @classmethod
    def build(
        cls,
        dataset_id: str,
        traces: Iterable[DecisionTraceSnapshot],
        feedback: Iterable[HumanFeedback],
        outcomes: Iterable[MarketOutcome],
        benchmarks: dict[str, str],
    ) -> "AttributionDataset":
        feedback_items = tuple(feedback)
        outcome_items = tuple(outcomes)
        samples = []
        for trace in traces:
            if trace.run_id not in benchmarks:
                raise ContractValidationError(f"missing benchmark for run {trace.run_id}")
            samples.append(
                AttributionSample(
                    sample_id=f"sample:{trace.run_id}",
                    trace=trace,
                    feedback=tuple(item for item in feedback_items if item.run_id == trace.run_id),
                    outcomes=tuple(item for item in outcome_items if item.run_id == trace.run_id),
                    benchmark_id=benchmarks[trace.run_id],
                )
            )
        return cls(dataset_id=dataset_id, samples=tuple(samples))
