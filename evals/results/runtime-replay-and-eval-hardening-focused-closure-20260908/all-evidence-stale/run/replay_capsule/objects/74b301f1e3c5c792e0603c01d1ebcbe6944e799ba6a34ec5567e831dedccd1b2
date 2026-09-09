"""Deterministic normalization and provenance envelopes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


def parse_timestamp(value: str | datetime | date) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, tzinfo=UTC)
    else:
        text = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def iso_utc(value: str | datetime | date) -> str:
    return parse_timestamp(value).isoformat().replace("+00:00", "Z")


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return iso_utc(value)
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_value(value: Any, value_type: str | None) -> Any:
    if value_type == "number" or isinstance(value, (int, float, Decimal)):
        try:
            return format(Decimal(str(value)), "f")
        except InvalidOperation as exc:
            raise ValueError(f"invalid numeric value: {value!r}") from exc
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("boolean facts require a bool value")
        return value
    return value


@dataclass(frozen=True, slots=True)
class FactEnvelope:
    fact_id: str
    security_id: str
    semantic_field: str
    value: Any
    value_type: str
    unit: str | None
    currency: str | None
    source_timezone: str
    source_id: str
    source_type: str
    source_locator: str
    source_version: str | None
    as_of: str
    retrieved_at: str
    content_hash: str
    adapter_version: str
    freshness_status: str = "UNASSESSED"
    quality_flags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FactEnvelope":
        payload = dict(value)
        payload["quality_flags"] = tuple(payload.get("quality_flags", ()))
        return cls(**payload)


_REQUIRED_RAW_FIELDS = (
    "security_id",
    "semantic_field",
    "value",
    "source_id",
    "source_type",
    "source_locator",
    "as_of",
    "retrieved_at",
)


def normalize_fact(
    raw: Mapping[str, Any], *, adapter_version: str = "reference/1.0.0"
) -> FactEnvelope:
    """Normalize one source observation without dropping its provenance."""

    missing = [name for name in _REQUIRED_RAW_FIELDS if raw.get(name) is None]
    if missing:
        raise ValueError(f"fact is missing required provenance: {', '.join(missing)}")

    value_type = str(raw.get("value_type") or "string")
    normalized_value = _normalize_value(raw["value"], value_type)
    raw_hash = content_hash(dict(raw))
    as_of = iso_utc(raw["as_of"])
    retrieved_at = iso_utc(raw["retrieved_at"])
    if parse_timestamp(retrieved_at) < parse_timestamp(as_of):
        raise ValueError("retrieved_at cannot precede as_of")

    identity = {
        "security_id": raw["security_id"],
        "semantic_field": raw["semantic_field"],
        "source_id": raw["source_id"],
        "as_of": as_of,
        "retrieved_at": retrieved_at,
        "content_hash": raw_hash,
    }
    fact_id = f"fact_{content_hash(identity)[:24]}"
    return FactEnvelope(
        fact_id=fact_id,
        security_id=str(raw["security_id"]),
        semantic_field=str(raw["semantic_field"]),
        value=normalized_value,
        value_type=value_type,
        unit=str(raw["unit"]) if raw.get("unit") is not None else None,
        currency=str(raw["currency"]) if raw.get("currency") is not None else None,
        source_timezone=str(raw.get("source_timezone") or "UTC"),
        source_id=str(raw["source_id"]),
        source_type=str(raw["source_type"]),
        source_locator=str(raw["source_locator"]),
        source_version=(
            str(raw["source_version"]) if raw.get("source_version") is not None else None
        ),
        as_of=as_of,
        retrieved_at=retrieved_at,
        content_hash=raw_hash,
        adapter_version=adapter_version,
    )
