"""Canonical hashing helpers for replayable runtime artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data with stable ordering and separators."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    """Return the SHA-256 digest of canonical JSON data."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    """Return a SHA-256 digest for an exact file payload."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


LEGACY_CANONICAL_HASH = "canonical-json/1.0.0"
LEGACY_PROVENANCE_HASH = "provenance-json/1.0.0"


def _legacy_provenance_default(value: object) -> str:
    """旧来源契约：Decimal 是字符串，日期是 UTC 零点，不迁移旧摘要。"""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        parsed = value if isinstance(value, datetime) else datetime(
            value.year, value.month, value.day, tzinfo=UTC,
        )
        if parsed.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def legacy_provenance_json(value: object) -> str:
    """来源旧版本的唯一序列化实现；与纯 JSON 契约显式区分。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=_legacy_provenance_default)


def legacy_provenance_hash(value: object) -> str:
    return hashlib.sha256(legacy_provenance_json(value).encode("utf-8")).hexdigest()


def verify_legacy_object_hash(
    value: Any, expected: str, *, kind: str, location: str,
    algorithm: str = LEGACY_CANONICAL_HASH,
) -> None:
    """按已声明旧算法校验对象/投影，不从摘要形状猜算法或范围。"""
    if kind not in {"canonical-object", "fact-content", "delivered-view"}:
        raise HashContractError(f"HASH_KIND_UNSUPPORTED:{kind}:{location}")
    algorithms = {LEGACY_CANONICAL_HASH: canonical_hash, LEGACY_PROVENANCE_HASH: legacy_provenance_hash}
    if algorithm not in algorithms:
        raise HashContractError(f"HASH_ALGORITHM_UNSUPPORTED:{algorithm}:{location}")
    actual = algorithms[algorithm](value)
    if expected != actual:
        raise HashContractError(
            f"HASH_MISMATCH:{kind}:{algorithm}:{location}:expected={expected}:actual={actual}"
        )


def verify_file_hash(path: Path, expected: str, *, location: str) -> None:
    """文件按原始字节校验，不能先解析成 JSON 后替代。"""
    actual = file_hash(path)
    if expected != actual:
        raise HashContractError(
            f"HASH_MISMATCH:file-bytes:sha256/1.0.0:{location}:expected={expected}:actual={actual}"
        )


def legacy_envelope_hash(value: Mapping[str, Any], *, hash_field: str) -> str:
    """Preserve v1 envelope digests while centralizing self-field exclusion."""

    if not isinstance(value, Mapping) or not isinstance(hash_field, str) or not hash_field:
        raise HashContractError("HASH_ENVELOPE_INVALID:$")
    return canonical_hash({key: item for key, item in value.items() if key != hash_field})


def verify_legacy_envelope_hash(
    value: Mapping[str, Any], *, hash_field: str, location: str,
) -> None:
    """Validate v1 self-excluding JSON with a scoped diagnostic, no migration."""
    actual = legacy_envelope_hash(value, hash_field=hash_field)
    expected = value.get(hash_field)
    if expected != actual:
        raise HashContractError(
            f"HASH_MISMATCH:self-excluding-envelope:{LEGACY_CANONICAL_HASH}:"
            f"{location}:field={hash_field}:expected={expected}:actual={actual}"
        )


# Existing canonical_hash/content_hash values have no algorithm label. Keep
# their byte representation unchanged for frozen artifacts; new writes must
# opt into this domain-separated contract explicitly.
CANONICAL_HASH_V2 = "canonical-json/2.0.0"
HASH_KINDS = frozenset({
    "canonical-object", "self-excluding-envelope", "fact-content", "delivered-view",
})


class HashContractError(ValueError):
    """A typed hash cannot be produced or verified under its declared contract."""


def _hash_value_v2(value: Any, path: str) -> list[Any]:
    """Encode a value as an unambiguous, type-tagged JSON tree."""

    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise HashContractError(f"HASH_VALUE_NONFINITE:{path}")
        return ["float", repr(value)]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise HashContractError(f"HASH_VALUE_NONFINITE:{path}")
        return ["decimal", format(value, "f")]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise HashContractError(f"HASH_TIMEZONE_REQUIRED:{path}")
        return ["datetime", value.astimezone(UTC).isoformat().replace("+00:00", "Z")]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, str):
        # Preserve Unicode code points exactly; no implicit NFC conversion.
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise HashContractError(f"HASH_UNICODE_INVALID:{path}") from exc
        return ["string", value]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise HashContractError(f"HASH_OBJECT_KEY_INVALID:{path}")
        for key in value:
            try:
                key.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise HashContractError(f"HASH_UNICODE_INVALID:{path}") from exc
        return ["object", [
            [key, _hash_value_v2(value[key], f"{path}.{key}")]
            for key in sorted(value)
        ]]
    if isinstance(value, (list, tuple)):
        return ["array", [
            _hash_value_v2(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]]
    raise HashContractError(f"HASH_VALUE_UNSUPPORTED:{path}:{type(value).__name__}")


def canonical_json_v2(value: Any) -> str:
    """Version-two UTF-8 JSON serialization with explicit scalar types."""

    return json.dumps(
        _hash_value_v2(value, "$"), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def typed_hash(value: Any, *, kind: str) -> str:
    """Hash a projected object without conflating different semantic domains."""

    if kind not in HASH_KINDS:
        raise HashContractError(f"HASH_KIND_UNSUPPORTED:{kind}")
    try:
        serialized = canonical_json_v2(value)
    except HashContractError as exc:
        raise HashContractError(f"{exc}:{kind}:{CANONICAL_HASH_V2}") from exc
    payload = f"stock-agent:{kind}:{CANONICAL_HASH_V2}\n{serialized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def envelope_hash(value: Mapping[str, Any], *, hash_field: str) -> str:
    """Hash an envelope excluding only its named, top-level self-hash field."""

    if not isinstance(value, Mapping):
        raise HashContractError("HASH_ENVELOPE_INVALID:$")
    if not isinstance(hash_field, str) or not hash_field:
        raise HashContractError("HASH_FIELD_INVALID:$")
    return typed_hash(
        {key: item for key, item in value.items() if key != hash_field},
        kind="self-excluding-envelope",
    )


def verify_typed_hash(
    value: Any, expected: str, *, kind: str, location: str,
) -> None:
    """Verify a v2 digest with a diagnostic that names its semantic contract."""

    actual = typed_hash(value, kind=kind)
    if not isinstance(expected, str) or actual != expected:
        raise HashContractError(
            f"HASH_MISMATCH:{kind}:{CANONICAL_HASH_V2}:{location}"
        )
