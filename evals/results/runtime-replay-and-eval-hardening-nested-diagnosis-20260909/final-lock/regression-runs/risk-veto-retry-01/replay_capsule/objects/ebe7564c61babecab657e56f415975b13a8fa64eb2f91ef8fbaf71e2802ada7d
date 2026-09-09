"""Canonical hashing helpers for replayable runtime artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data with stable ordering and separators."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    """Return the SHA-256 digest of canonical JSON data."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    """Return a SHA-256 digest for an exact file payload."""

    return hashlib.sha256(path.read_bytes()).hexdigest()
