"""Small deterministic primitives for the independent personal journal."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


class JournalError(ValueError):
    """A stable diagnostic; messages must not contain raw brokerage material."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        self.code = code
        self.details = dict(details or {})
        super().__init__(message)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_datetime(value: str) -> datetime:
    """Require a real offset. A source date is deliberately not midnight UTC."""
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise JournalError("INVALID_TIME", "时间必须是带时区的 ISO 时刻。") from exc
    if result.tzinfo is None:
        raise JournalError("TIMEZONE_REQUIRED", "时间必须包含可靠时区。")
    return result.astimezone(timezone.utc)


def decimal_value(value: Any, *, field: str = "number", nullable: bool = False) -> Decimal | None:
    if value is None or value == "":
        if nullable:
            return None
        raise JournalError("NUMBER_REQUIRED", f"缺少必要数值字段：{field}。")
    if isinstance(value, bool):
        raise JournalError("INVALID_NUMBER", f"数值字段无效：{field}。")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise JournalError("INVALID_NUMBER", f"数值字段无效：{field}。") from exc
    if not result.is_finite():
        raise JournalError("INVALID_NUMBER", f"数值字段必须有限：{field}。")
    return result


def decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    return format(value.normalize(), "f")
