"""Human-controlled promotion and append-only rollback ledger."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from product.contracts.base import (
    ContractValidationError,
    JsonContract,
    require_identifier,
    require_iso_datetime,
    require_text,
)
from product.trace import VersionLock

from .validation import ValidationBundle


@dataclass(frozen=True, slots=True)
class ApprovedVersion(JsonContract):
    schema_name: ClassVar[str] = "approved-version"

    version_id: str
    versions: VersionLock

    def __post_init__(self) -> None:
        require_identifier(self.version_id, "version_id")


class PromotionAction(str, Enum):
    PROMOTE = "PROMOTE"
    ROLLBACK = "ROLLBACK"


@dataclass(frozen=True, slots=True)
class PromotionRecord(JsonContract):
    schema_name: ClassVar[str] = "promotion-record"

    record_id: str
    action: PromotionAction
    from_version_id: str
    to_version_id: str
    from_versions: VersionLock
    to_versions: VersionLock
    evaluation_record_ids: tuple[str, ...]
    approved_by: str
    approved_at: str
    rationale: str
    rollback_conditions: tuple[str, ...]
    parent_record_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("record_id", "from_version_id", "to_version_id", "approved_by"):
            require_identifier(getattr(self, name), name)
        if self.from_version_id == self.to_version_id:
            raise ContractValidationError("promotion must change the active version")
        if not self.evaluation_record_ids:
            raise ContractValidationError("promotion record requires evaluation evidence")
        for record_id in self.evaluation_record_ids:
            require_identifier(record_id, "evaluation_record_id")
        require_iso_datetime(self.approved_at, "approved_at")
        require_text(self.rationale, "rationale")
        if not self.rollback_conditions or any(not item.strip() for item in self.rollback_conditions):
            raise ContractValidationError("rollback conditions must be explicit")
        if self.parent_record_id is not None:
            require_identifier(self.parent_record_id, "parent_record_id")
        if self.action is PromotionAction.ROLLBACK and self.parent_record_id is None:
            raise ContractValidationError("rollback record must identify the promotion being rolled back")


class PromotionLedger:
    """Derives the active version from immutable human approval records."""

    def __init__(self, initial_version: ApprovedVersion):
        self._initial = initial_version
        self._active = initial_version
        self._approved_versions: list[ApprovedVersion] = [initial_version]
        self._records: list[PromotionRecord] = []

    @property
    def active_version(self) -> ApprovedVersion:
        return self._active

    @property
    def records(self) -> tuple[PromotionRecord, ...]:
        return tuple(self._records)

    @property
    def approved_versions(self) -> tuple[ApprovedVersion, ...]:
        return tuple(self._approved_versions)

    def promote(
        self,
        *,
        record_id: str,
        candidate: ApprovedVersion,
        validation: ValidationBundle,
        approved_by: str,
        approved_at: str,
        rationale: str,
        rollback_conditions: tuple[str, ...],
    ) -> PromotionRecord:
        if not validation.passed:
            raise ContractValidationError("failed candidate cannot be promoted")
        if any(item.version_id == candidate.version_id for item in self._approved_versions):
            raise ContractValidationError("candidate version was already approved")
        record = PromotionRecord(
            record_id=record_id,
            action=PromotionAction.PROMOTE,
            from_version_id=self._active.version_id,
            to_version_id=candidate.version_id,
            from_versions=self._active.versions,
            to_versions=candidate.versions,
            evaluation_record_ids=validation.record_ids,
            approved_by=approved_by,
            approved_at=approved_at,
            rationale=rationale,
            rollback_conditions=rollback_conditions,
        )
        self._records.append(record)
        self._approved_versions.append(candidate)
        self._active = candidate
        return record

    def rollback(
        self,
        *,
        record_id: str,
        approved_by: str,
        approved_at: str,
        rationale: str,
        triggering_evaluation_record_ids: tuple[str, ...],
        rollback_conditions: tuple[str, ...],
    ) -> PromotionRecord:
        promotion = next(
            (
                record
                for record in reversed(self._records)
                if record.action is PromotionAction.PROMOTE
                and record.to_version_id == self._active.version_id
            ),
            None,
        )
        if promotion is None:
            raise ContractValidationError("active version has no prior promotion to roll back")
        previous = next(
            item for item in reversed(self._approved_versions) if item.version_id == promotion.from_version_id
        )
        record = PromotionRecord(
            record_id=record_id,
            action=PromotionAction.ROLLBACK,
            from_version_id=self._active.version_id,
            to_version_id=previous.version_id,
            from_versions=self._active.versions,
            to_versions=previous.versions,
            evaluation_record_ids=triggering_evaluation_record_ids,
            approved_by=approved_by,
            approved_at=approved_at,
            rationale=rationale,
            rollback_conditions=rollback_conditions,
            parent_record_id=promotion.record_id,
        )
        self._records.append(record)
        self._active = previous
        return record
