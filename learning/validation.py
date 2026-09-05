"""Append-only validation records for Improvement Proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from product.contracts.base import ContractValidationError, require_identifier, require_iso_datetime


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    record_id: str
    proposal_id: str
    candidate_version: str
    decision_cutoffs: tuple[str, ...]
    case_ids: tuple[str, ...]
    passed: bool

    def __post_init__(self) -> None:
        for name in ("record_id", "proposal_id"):
            require_identifier(getattr(self, name), name)
        if not self.candidate_version.strip() or not self.decision_cutoffs or not self.case_ids:
            raise ContractValidationError("replay record requires version, cutoffs, and cases")
        for cutoff in self.decision_cutoffs:
            require_iso_datetime(cutoff, "decision_cutoff")


@dataclass(frozen=True, slots=True)
class RegressionRecord:
    record_id: str
    proposal_id: str
    deterministic_passed: bool
    holdout_passed: bool
    hard_constraint_regressions: int
    report_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.record_id, "record_id")
        require_identifier(self.proposal_id, "proposal_id")
        if self.hard_constraint_regressions < 0 or not self.report_artifact_ids:
            raise ContractValidationError("regression record requires reports and valid regression count")

    @property
    def passed(self) -> bool:
        return (
            self.deterministic_passed
            and self.holdout_passed
            and self.hard_constraint_regressions == 0
        )


@dataclass(frozen=True, slots=True)
class AdversarialRecord:
    record_id: str
    proposal_id: str
    case_ids: tuple[str, ...]
    passed: bool

    def __post_init__(self) -> None:
        require_identifier(self.record_id, "record_id")
        require_identifier(self.proposal_id, "proposal_id")
        if not self.case_ids:
            raise ContractValidationError("adversarial record requires cases")


@dataclass(frozen=True, slots=True)
class ShadowRunRecord:
    record_id: str
    proposal_id: str
    candidate_version: str
    started_at: str
    completed_at: str
    trace_ids: tuple[str, ...]
    critical_regressions: int
    passed: bool

    def __post_init__(self) -> None:
        require_identifier(self.record_id, "record_id")
        require_identifier(self.proposal_id, "proposal_id")
        if not self.candidate_version.strip() or not self.trace_ids:
            raise ContractValidationError("shadow run requires candidate version and traces")
        require_iso_datetime(self.started_at, "started_at")
        require_iso_datetime(self.completed_at, "completed_at")
        started = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(self.completed_at.replace("Z", "+00:00"))
        if completed < started:
            raise ContractValidationError("shadow run completion cannot precede start")
        if self.critical_regressions < 0:
            raise ContractValidationError("critical_regressions must not be negative")
        if self.passed and self.critical_regressions:
            raise ContractValidationError("shadow run with critical regressions cannot pass")


@dataclass(frozen=True, slots=True)
class ValidationBundle:
    replay: ReplayRecord
    regression: RegressionRecord
    adversarial: AdversarialRecord
    shadow: ShadowRunRecord

    def __post_init__(self) -> None:
        proposals = {
            self.replay.proposal_id,
            self.regression.proposal_id,
            self.adversarial.proposal_id,
            self.shadow.proposal_id,
        }
        if len(proposals) != 1:
            raise ContractValidationError("all validation records must reference one proposal")

    @property
    def passed(self) -> bool:
        return (
            self.replay.passed
            and self.regression.passed
            and self.adversarial.passed
            and self.shadow.passed
            and self.shadow.critical_regressions == 0
        )

    @property
    def record_ids(self) -> tuple[str, ...]:
        return (
            self.replay.record_id,
            self.regression.record_id,
            self.adversarial.record_id,
            self.shadow.record_id,
        )


class ValidationHistory:
    def __init__(self) -> None:
        self._bundles: list[ValidationBundle] = []

    def append(self, bundle: ValidationBundle) -> None:
        known = {record_id for item in self._bundles for record_id in item.record_ids}
        overlap = known & set(bundle.record_ids)
        if overlap:
            raise ContractValidationError(f"validation records are append-only: {sorted(overlap)}")
        self._bundles.append(bundle)

    @property
    def bundles(self) -> tuple[ValidationBundle, ...]:
        return tuple(self._bundles)
