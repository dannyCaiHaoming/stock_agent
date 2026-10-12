"""Provider-neutral, read-only market research data access."""

from .provenance import FactEnvelope, normalize_fact

__all__ = [
    "FactEnvelope",
    "normalize_fact",
]
