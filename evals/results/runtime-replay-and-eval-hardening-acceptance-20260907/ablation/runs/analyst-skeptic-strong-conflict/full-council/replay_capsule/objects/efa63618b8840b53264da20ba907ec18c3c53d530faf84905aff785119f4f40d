"""Bounded, deterministic validation for specialist format-only repairs."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from .hashing import canonical_hash
from .validation import ArtifactValidationError, collect_evidence_refs


FORMAT_REPAIR_VERSION = "specialist-format-repair/2.0.0"
FORMAT_ONLY_ERRORS = (
    "AgentResearchReport keys invalid",
    "CounterThesisReport keys invalid",
    "SCHEMA_VERSION_MISMATCH",
)
FACT_BEARING_SECTIONS = {"claims", "challenges", "assumptions"}


def is_format_only_error(error: Exception) -> bool:
    message = str(error)
    return any(message.startswith(prefix) for prefix in FORMAT_ONLY_ERRORS)


def _fact_atoms(value: Any, *, inside_fact_section: bool = False) -> list[str]:
    atoms: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            active = inside_fact_section or str(key) in FACT_BEARING_SECTIONS
            if active:
                atoms.extend(_fact_atoms(item, inside_fact_section=True))
    elif isinstance(value, list):
        for item in value:
            atoms.extend(_fact_atoms(item, inside_fact_section=inside_fact_section))
    elif inside_fact_section and value is not None:
        atoms.append(canonical_hash({"fact_atom": value}))
    return sorted(atoms)


def build_format_repair_request(
    report: Mapping[str, Any],
    *,
    run_id: str,
    agent_name: str,
    validation_error: Exception,
) -> dict[str, Any]:
    """Create a one-shot repair envelope without interpreting investment content."""

    if not is_format_only_error(validation_error):
        raise ArtifactValidationError("NON_FORMAT_ERROR_NOT_REPAIRABLE")
    original_refs = sorted(collect_evidence_refs(report))
    request: dict[str, Any] = {
        "schema_version": FORMAT_REPAIR_VERSION,
        "run_id": run_id,
        "agent": agent_name,
        "invocation_id": report.get("invocation_id"),
        "repair_number": 1,
        "maximum_repairs": 1,
        "validation_error": str(validation_error),
        "original_report_hash": canonical_hash(report),
        "original_evidence_refs": original_refs,
        "original_fact_atoms": _fact_atoms(report),
        "permitted_change": "FORMAT_ONLY",
        "repaired_output_relative_path": f"repairs/{agent_name}-attempt-2.json",
    }
    request["request_hash"] = canonical_hash(request)
    return request


def verify_format_repair(
    original: Mapping[str, Any],
    repaired: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    run_id: str,
    agent_name: str,
    allowed_evidence_ids: Sequence[str],
) -> None:
    """Reject identity drift, new facts, and any Evidence-set expansion."""

    body = dict(request)
    claimed_hash = body.pop("request_hash", None)
    if claimed_hash != canonical_hash(body):
        raise ArtifactValidationError("FORMAT_REPAIR_REQUEST_HASH_MISMATCH")
    expected = {
        "schema_version": FORMAT_REPAIR_VERSION,
        "run_id": run_id,
        "agent": agent_name,
        "repair_number": 1,
        "maximum_repairs": 1,
        "permitted_change": "FORMAT_ONLY",
    }
    if any(request.get(key) != value for key, value in expected.items()):
        raise ArtifactValidationError("FORMAT_REPAIR_REQUEST_IDENTITY_MISMATCH")
    if request.get("original_report_hash") != canonical_hash(original):
        raise ArtifactValidationError("FORMAT_REPAIR_ORIGINAL_HASH_MISMATCH")
    if repaired.get("run_id") != run_id or repaired.get("agent") != agent_name:
        raise ArtifactValidationError("FORMAT_REPAIR_OUTPUT_IDENTITY_MISMATCH")
    if repaired.get("invocation_id") != request.get("invocation_id"):
        raise ArtifactValidationError("FORMAT_REPAIR_INVOCATION_MISMATCH")

    original_refs = set(str(item) for item in request.get("original_evidence_refs", []))
    repaired_refs = collect_evidence_refs(repaired)
    if not repaired_refs <= original_refs:
        raise ArtifactValidationError("FORMAT_REPAIR_EXPANDED_EVIDENCE_SET")
    if not repaired_refs <= set(allowed_evidence_ids):
        raise ArtifactValidationError("FORMAT_REPAIR_REFERENCES_UNAVAILABLE_EVIDENCE")

    original_atoms = Counter(str(item) for item in request.get("original_fact_atoms", []))
    repaired_atoms = Counter(_fact_atoms(repaired))
    if repaired_atoms - original_atoms:
        raise ArtifactValidationError("FORMAT_REPAIR_ADDED_FACT_CONTENT")
