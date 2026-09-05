"""Contracts for reconstructing a complete Portfolio Council decision."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Iterator, Mapping, Sequence, TypeVar

from product.contracts.base import (
    ContractValidationError,
    JsonContract,
    require_identifier,
    require_iso_datetime,
    require_text,
    require_unique,
)


class TraceValidationError(ContractValidationError):
    """Raised when a trace cannot be replayed or promoted safely."""


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _immutable_json_object(value: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TraceValidationError(f"{field_name} must be a JSON object")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise TraceValidationError(f"{field_name} must be JSON-compatible") from exc
    return decoded


V = TypeVar("V")


class _FrozenMapping(Mapping[str, V]):
    def __init__(self, values: Mapping[str, V]):
        self._values = dict(values)

    def __getitem__(self, key: str) -> V:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, V]:
        return dict(self._values)


def _version_map(value: Mapping[str, str], field_name: str) -> Mapping[str, str]:
    if not value:
        raise TraceValidationError(f"{field_name} must not be empty")
    copied: dict[str, str] = {}
    for key, version in value.items():
        require_identifier(key, f"{field_name} key")
        require_text(version, f"{field_name}[{key}]")
        copied[key] = version
    return _FrozenMapping(copied)


@dataclass(frozen=True, slots=True)
class VersionLock(JsonContract):
    """All mutable runtime dependencies pinned for replay and promotion."""

    schema_name: ClassVar[str] = "decision-version-lock"

    model_snapshot: str
    skills: Mapping[str, str]
    agents: Mapping[str, str]
    schemas: Mapping[str, str]
    mcp_adapters: Mapping[str, str]
    risk_policy: str
    data_snapshot: str

    def __post_init__(self) -> None:
        require_text(self.model_snapshot, "model_snapshot")
        require_text(self.risk_policy, "risk_policy")
        require_text(self.data_snapshot, "data_snapshot")
        for name in ("skills", "agents", "schemas", "mcp_adapters"):
            object.__setattr__(self, name, _version_map(getattr(self, name), name))

    @property
    def complete(self) -> bool:
        return True


class TraceStage(str, Enum):
    INPUT = "INPUT"
    RESEARCH_PLAN = "RESEARCH_PLAN"
    DELEGATION = "DELEGATION"
    TOOL_CALL = "TOOL_CALL"
    EVIDENCE = "EVIDENCE"
    AGENT_REPORT = "AGENT_REPORT"
    CIO_DRAFT = "CIO_DRAFT"
    CIO_REVISION = "CIO_REVISION"
    RISK_REPORT = "RISK_REPORT"
    FINAL_OUTPUT = "FINAL_OUTPUT"
    PERMISSION_DENIAL = "PERMISSION_DENIAL"


REQUIRED_TRACE_STAGES = frozenset(
    {
        TraceStage.INPUT,
        TraceStage.RESEARCH_PLAN,
        TraceStage.DELEGATION,
        TraceStage.TOOL_CALL,
        TraceStage.EVIDENCE,
        TraceStage.AGENT_REPORT,
        TraceStage.CIO_DRAFT,
        TraceStage.RISK_REPORT,
        TraceStage.FINAL_OUTPUT,
    }
)


@dataclass(frozen=True, slots=True)
class TraceEvent(JsonContract):
    schema_name: ClassVar[str] = "decision-trace-event"

    event_id: str
    sequence: int
    stage: TraceStage
    occurred_at: str
    producer_id: str
    artifact_id: str | None
    input_artifact_ids: tuple[str, ...]
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        require_identifier(self.event_id, "event_id")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise TraceValidationError("sequence must be a positive integer")
        require_iso_datetime(self.occurred_at, "occurred_at")
        require_identifier(self.producer_id, "producer_id")
        if self.artifact_id is not None:
            require_identifier(self.artifact_id, "artifact_id")
        for index, artifact_id in enumerate(self.input_artifact_ids):
            require_identifier(artifact_id, f"input_artifact_ids[{index}]")
        require_unique(self.input_artifact_ids, "input_artifact_ids")
        object.__setattr__(self, "payload", _FrozenMapping(_immutable_json_object(self.payload, "payload")))


@dataclass(frozen=True, slots=True)
class DecisionTraceSnapshot(JsonContract):
    schema_name: ClassVar[str] = "decision-trace"

    run_id: str
    trace_id: str
    decision_cutoff: str
    versions: VersionLock
    events: tuple[TraceEvent, ...]

    def __post_init__(self) -> None:
        require_identifier(self.run_id, "run_id")
        require_identifier(self.trace_id, "trace_id")
        require_iso_datetime(self.decision_cutoff, "decision_cutoff")
        _validate_event_sequence(self.events)

    @property
    def complete(self) -> bool:
        try:
            validate_complete_trace(self.events)
        except TraceValidationError:
            return False
        return True

    def require_complete(self) -> None:
        validate_complete_trace(self.events)

    @property
    def promotable(self) -> bool:
        return self.complete and self.versions.complete


def _validate_event_sequence(events: Sequence[TraceEvent]) -> None:
    sequences = [event.sequence for event in events]
    if sequences != list(range(1, len(events) + 1)):
        raise TraceValidationError("trace event sequences must be contiguous and start at 1")
    require_unique([event.event_id for event in events], "trace event IDs")
    previous: datetime | None = None
    for event in events:
        current = _instant(event.occurred_at)
        if previous is not None and current < previous:
            raise TraceValidationError("trace events must be appended in occurred_at order")
        previous = current


def validate_complete_trace(events: Sequence[TraceEvent]) -> None:
    _validate_event_sequence(events)
    present = {event.stage for event in events}
    missing = sorted(stage.value for stage in REQUIRED_TRACE_STAGES - present)
    if missing:
        raise TraceValidationError(f"decision trace is incomplete; missing stages: {missing}")
    if events[-1].stage is not TraceStage.FINAL_OUTPUT:
        raise TraceValidationError("FINAL_OUTPUT must be the last trace event")

    first_position = {stage: next(i for i, event in enumerate(events) if event.stage is stage) for stage in present}
    ordered = (
        TraceStage.INPUT,
        TraceStage.RESEARCH_PLAN,
        TraceStage.DELEGATION,
        TraceStage.TOOL_CALL,
        TraceStage.EVIDENCE,
        TraceStage.AGENT_REPORT,
        TraceStage.CIO_DRAFT,
    )
    if [first_position[stage] for stage in ordered] != sorted(first_position[stage] for stage in ordered):
        raise TraceValidationError("research trace stages are out of causal order")

    revisions = [i for i, event in enumerate(events) if event.stage is TraceStage.CIO_REVISION]
    risks = [i for i, event in enumerate(events) if event.stage is TraceStage.RISK_REPORT]
    draft = first_position[TraceStage.CIO_DRAFT]
    final = first_position[TraceStage.FINAL_OUTPUT]
    if not risks or risks[0] <= draft or risks[-1] >= final:
        raise TraceValidationError("risk report must occur after CIO draft and before final output")
    if len(revisions) > 1:
        raise TraceValidationError("at most one CIO revision is permitted")
    if revisions:
        revision = revisions[0]
        if not any(draft < risk < revision for risk in risks):
            raise TraceValidationError("CIO revision requires a preceding risk report")
        if not any(revision < risk < final for risk in risks):
            raise TraceValidationError("CIO revision requires a subsequent risk report")


class DecisionTrace:
    """In-memory append-only trace builder with immutable snapshots."""

    def __init__(self, run_id: str, trace_id: str, decision_cutoff: str, versions: VersionLock):
        require_identifier(run_id, "run_id")
        require_identifier(trace_id, "trace_id")
        require_iso_datetime(decision_cutoff, "decision_cutoff")
        self._run_id = run_id
        self._trace_id = trace_id
        self._decision_cutoff = decision_cutoff
        self._versions = versions
        self._events: list[TraceEvent] = []
        self._sealed = False

    def append(
        self,
        *,
        event_id: str,
        stage: TraceStage,
        occurred_at: str,
        producer_id: str,
        payload: Mapping[str, Any],
        artifact_id: str | None = None,
        input_artifact_ids: Sequence[str] = (),
    ) -> TraceEvent:
        if self._sealed:
            raise TraceValidationError("a completed decision trace is append-only and sealed")
        event = TraceEvent(
            event_id=event_id,
            sequence=len(self._events) + 1,
            stage=stage,
            occurred_at=occurred_at,
            producer_id=producer_id,
            artifact_id=artifact_id,
            input_artifact_ids=tuple(input_artifact_ids),
            payload=payload,
        )
        if any(existing.event_id == event.event_id for existing in self._events):
            raise TraceValidationError(f"duplicate event_id: {event.event_id}")
        if self._events and _instant(event.occurred_at) < _instant(self._events[-1].occurred_at):
            raise TraceValidationError("new trace events cannot precede already appended events")
        if stage is TraceStage.FINAL_OUTPUT:
            validate_complete_trace((*self._events, event))
            self._sealed = True
        self._events.append(event)
        return event

    def snapshot(self, *, require_complete: bool = False) -> DecisionTraceSnapshot:
        snapshot = DecisionTraceSnapshot(
            run_id=self._run_id,
            trace_id=self._trace_id,
            decision_cutoff=self._decision_cutoff,
            versions=self._versions,
            events=tuple(self._events),
        )
        if require_complete:
            snapshot.require_complete()
        return snapshot
