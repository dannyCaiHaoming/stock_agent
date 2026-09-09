"""Shared primitives for versioned, JSON-compatible product contracts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, ClassVar, Mapping, Sequence


class ContractValidationError(ValueError):
    """Raised when a contract violates a structural product invariant."""


class ProducerKind(str, Enum):
    CIO = "CIO"
    RUNTIME_AGENT = "RUNTIME_AGENT"
    MCP_TOOL = "MCP_TOOL"
    RISK_ENGINE = "RISK_ENGINE"
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"
    REFLECTION = "REFLECTION"


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


def require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string")


def require_identifier(value: str, field_name: str) -> None:
    require_text(value, field_name)
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ContractValidationError(
            f"{field_name} must be a stable identifier using letters, digits, '.', '_', ':', '/', or '-'"
        )


def require_iso_date_or_datetime(value: str, field_name: str) -> None:
    require_text(value, field_name)
    try:
        if "T" in value or " " in value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ContractValidationError(f"{field_name} datetime must include a UTC offset")
        else:
            date.fromisoformat(value)
    except ContractValidationError:
        raise
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} must be an ISO-8601 date or datetime") from exc


def require_iso_datetime(value: str, field_name: str) -> None:
    require_text(value, field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractValidationError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must include a UTC offset")


def require_finite_number(value: int | float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractValidationError(f"{field_name} must be a finite JSON number")


def require_fraction(value: int | float, field_name: str) -> None:
    require_finite_number(value, field_name)
    if not 0 <= value <= 1:
        raise ContractValidationError(f"{field_name} must be between 0 and 1")


def require_unique(values: Sequence[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ContractValidationError(f"{field_name} must not contain duplicates")


def require_non_empty_sequence(values: Sequence[Any], field_name: str) -> None:
    if not values:
        raise ContractValidationError(f"{field_name} must not be empty")


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractValidationError("JSON object keys must be strings")
            converted[key] = _json_value(item)
        return converted
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        require_finite_number(value, "JSON value")
        return value
    raise ContractValidationError(f"value of type {type(value).__name__} is not JSON-compatible")


class JsonContract:
    """Mixin for dataclass contracts that serialize without third-party libraries."""

    schema_name: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        converted = _json_value(self)
        if not isinstance(converted, dict):
            raise ContractValidationError("top-level contract must serialize to a JSON object")
        return converted

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ProducerRef(JsonContract):
    schema_name: ClassVar[str] = "producer-ref"

    kind: ProducerKind
    producer_id: str
    version: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProducerKind):
            raise ContractValidationError("producer kind must be a ProducerKind value")
        require_identifier(self.producer_id, "producer_id")
        require_text(self.version, "producer version")


@dataclass(frozen=True, slots=True)
class ArtifactEnvelope(JsonContract):
    """Common lineage envelope carried by every top-level artifact contract."""

    schema_name: ClassVar[str] = "artifact-envelope"

    schema_version: str
    artifact_id: str
    run_id: str
    trace_id: str
    producer: ProducerRef
    created_at: str
    input_artifact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.schema_version, "schema_version")
        require_identifier(self.artifact_id, "artifact_id")
        require_identifier(self.run_id, "run_id")
        require_identifier(self.trace_id, "trace_id")
        require_iso_datetime(self.created_at, "created_at")
        for index, artifact_id in enumerate(self.input_artifact_ids):
            require_identifier(artifact_id, f"input_artifact_ids[{index}]")
        require_unique(self.input_artifact_ids, "input_artifact_ids")
        if self.artifact_id in self.input_artifact_ids:
            raise ContractValidationError("an artifact cannot list itself as an input")


class ArtifactContract(JsonContract):
    """Marker base for top-level artifacts with a common envelope."""

    envelope: ArtifactEnvelope


def require_lineage_member(envelope: ArtifactEnvelope, artifact_id: str, field_name: str) -> None:
    require_identifier(artifact_id, field_name)
    if artifact_id not in envelope.input_artifact_ids:
        raise ContractValidationError(f"{field_name} must also appear in envelope.input_artifact_ids")


def validate_artifact_lineage(
    artifacts: Sequence[ArtifactContract], *, external_artifact_ids: Sequence[str] = ()
) -> None:
    """Resolve common-envelope lineage for an artifact collection.

    External IDs make intentionally out-of-batch immutable inputs explicit while
    preserving strict detection of broken references.
    """

    ids = [artifact.envelope.artifact_id for artifact in artifacts]
    require_unique(ids, "artifact IDs")
    artifacts_by_id = {artifact.envelope.artifact_id: artifact for artifact in artifacts}
    known_ids = set(ids) | set(external_artifact_ids)
    for artifact in artifacts:
        for input_id in artifact.envelope.input_artifact_ids:
            if input_id not in known_ids:
                raise ContractValidationError(
                    f"artifact {artifact.envelope.artifact_id} references unknown input artifact {input_id}"
                )
            referenced = artifacts_by_id.get(input_id)
            if referenced is not None and referenced.envelope.run_id != artifact.envelope.run_id:
                raise ContractValidationError(
                    f"artifact {artifact.envelope.artifact_id} and input {input_id} have different run_id values"
                )
