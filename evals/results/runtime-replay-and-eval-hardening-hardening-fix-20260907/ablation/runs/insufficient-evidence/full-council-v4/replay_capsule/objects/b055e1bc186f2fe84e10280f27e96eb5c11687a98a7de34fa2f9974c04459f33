"""An append-only JSONL store with in-memory bitemporal indexes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from product.mcp.provenance import (
    FactEnvelope,
    canonical_json,
    content_hash,
    parse_timestamp,
)


class AppendOnlyEvidenceStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._records: list[FactEnvelope] = []
        self._by_id: dict[str, FactEnvelope] = {}
        if self._path is not None and self._path.exists():
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        with self._path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    fact = FactEnvelope.from_dict(json.loads(line))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid evidence record at line {line_number}") from exc
                self._index(fact)

    def _index(self, fact: FactEnvelope) -> None:
        existing = self._by_id.get(fact.fact_id)
        if existing is not None:
            if canonical_json(existing.to_dict()) != canonical_json(fact.to_dict()):
                raise ValueError(f"immutable fact_id reused with different content: {fact.fact_id}")
            return
        self._records.append(fact)
        self._by_id[fact.fact_id] = fact

    def append(self, fact: FactEnvelope) -> bool:
        """Append a new immutable fact; exact repeats are idempotent."""

        existing = self._by_id.get(fact.fact_id)
        if existing is not None:
            if canonical_json(existing.to_dict()) != canonical_json(fact.to_dict()):
                raise ValueError(f"immutable fact_id reused with different content: {fact.fact_id}")
            return False
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(canonical_json(fact.to_dict()))
                stream.write("\n")
                stream.flush()
        self._index(fact)
        return True

    def append_many(self, facts: Iterable[FactEnvelope]) -> int:
        return sum(1 for fact in facts if self.append(fact))

    def get(self, fact_id: str) -> FactEnvelope | None:
        return self._by_id.get(fact_id)

    def query(
        self,
        *,
        security_id: str | None = None,
        semantic_field: str | None = None,
        as_of_lte: str | None = None,
        retrieved_at_lte: str | None = None,
    ) -> tuple[FactEnvelope, ...]:
        as_of_cutoff = parse_timestamp(as_of_lte) if as_of_lte is not None else None
        retrieval_cutoff = (
            parse_timestamp(retrieved_at_lte) if retrieved_at_lte is not None else None
        )
        selected: list[FactEnvelope] = []
        for fact in self._records:
            if security_id is not None and fact.security_id != security_id:
                continue
            if semantic_field is not None and fact.semantic_field != semantic_field:
                continue
            if as_of_cutoff is not None and parse_timestamp(fact.as_of) > as_of_cutoff:
                continue
            if retrieval_cutoff is not None and parse_timestamp(fact.retrieved_at) > retrieval_cutoff:
                continue
            selected.append(fact)
        return tuple(sorted(selected, key=lambda item: (item.as_of, item.retrieved_at, item.fact_id)))

    def snapshot_hash(self) -> str:
        return content_hash([fact.to_dict() for fact in self._records])

    def __len__(self) -> int:
        return len(self._records)
