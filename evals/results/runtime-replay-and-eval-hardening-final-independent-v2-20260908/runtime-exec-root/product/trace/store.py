"""Durable append-only JSON Lines storage for decision trace events."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

from .models import DecisionTraceSnapshot, TraceValidationError


class AppendOnlyTraceStore:
    """Append immutable trace snapshots without replacing historical records."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, snapshot: DecisionTraceSnapshot) -> None:
        snapshot.require_complete()
        existing_ids = {record["trace_id"] for record in self.iter_records()}
        if snapshot.trace_id in existing_ids:
            raise TraceValidationError(f"trace_id already exists: {snapshot.trace_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = snapshot.to_json() + "\n"
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, payload.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def iter_records(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TraceValidationError(
                        f"invalid trace store JSON on line {line_number}"
                    ) from exc
                if not isinstance(record, dict):
                    raise TraceValidationError(f"trace store line {line_number} is not an object")
                yield record
