"""既有 Company Analyst 的冻结披露候选输入/输出确定性接缝。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


INPUT_VERSION = "company-disclosure-candidate-input/1.0.0"
OUTPUT_VERSION = "company-disclosure-candidate-output/1.0.0"
CLAIM_TYPES = {"BUSINESS", "KPI", "RELATIONSHIP", "GUIDANCE"}


def build_candidate_input(
    disclosures: Sequence[Mapping[str, Any]], *, security_id: str,
    decision_cutoff: str, batch_id: str,
) -> dict[str, Any]:
    cutoff = parse_timestamp(decision_cutoff)
    evidence, seen = [], set()
    for item in disclosures:
        required = {
            "evidence_id", "source_id", "source_locator", "as_of", "published_at",
            "retrieved_at", "raw_content_hash", "text", "raw_character_spans", "truncated",
        }
        if not required <= set(item):
            raise ValueError("DISCLOSURE_CANDIDATE_PROVENANCE_MISSING")
        if item["evidence_id"] in seen:
            raise ValueError("DISCLOSURE_CANDIDATE_EVIDENCE_DUPLICATE")
        seen.add(item["evidence_id"])
        if max(
            parse_timestamp(item["as_of"]), parse_timestamp(item["published_at"]),
            parse_timestamp(item["retrieved_at"]),
        ) > cutoff:
            raise ValueError("DISCLOSURE_CANDIDATE_FUTURE_EVIDENCE")
        if not item["raw_character_spans"]:
            raise ValueError("DISCLOSURE_CANDIDATE_LOCATOR_MISSING")
        evidence.append({
            "evidence_id": item["evidence_id"], "security_id": security_id,
            "source_id": item["source_id"], "source_locator": item["source_locator"],
            "as_of": iso_utc(item["as_of"]), "published_at": iso_utc(item["published_at"]),
            "retrieved_at": iso_utc(item["retrieved_at"]),
            "raw_content_hash": item["raw_content_hash"], "text": item["text"],
            "raw_character_spans": deepcopy(item["raw_character_spans"]),
            "truncated": bool(item["truncated"]),
        })
    body = {
        "schema_version": INPUT_VERSION, "batch_id": batch_id,
        "security_id": security_id, "decision_cutoff": iso_utc(decision_cutoff),
        "evidence": sorted(evidence, key=lambda item: item["evidence_id"]),
        "allowed_claim_types": sorted(CLAIM_TYPES),
        "instructions": {
            "require_direct_citation": True,
            "preserve_anonymous_relationships": True,
            "peer_candidate_is_not_relationship_evidence": True,
            "truncated_source_requires_limitation": True,
        },
    }
    body["input_hash"] = content_hash(body)
    return body


def validate_candidate_output(
    candidate_input: Mapping[str, Any], output: Mapping[str, Any],
) -> None:
    required = {"schema_version", "input_hash", "security_id", "claims", "output_hash"}
    if set(output) != required or output.get("schema_version") != OUTPUT_VERSION:
        raise ValueError("DISCLOSURE_CANDIDATE_OUTPUT_SHAPE_INVALID")
    if output["input_hash"] != candidate_input["input_hash"] \
            or output["security_id"] != candidate_input["security_id"]:
        raise ValueError("DISCLOSURE_CANDIDATE_INPUT_BINDING_INVALID")
    by_id = {item["evidence_id"]: item for item in candidate_input["evidence"]}
    claim_ids = set()
    for claim in output["claims"]:
        fields = {
            "claim_id", "claim_type", "text", "evidence_id", "source_quote",
            "relationship_basis", "anonymity_status", "object_name", "limitations",
        }
        if not isinstance(claim, Mapping) or set(claim) != fields:
            raise ValueError("DISCLOSURE_CANDIDATE_CLAIM_SHAPE_INVALID")
        if claim["claim_id"] in claim_ids:
            raise ValueError("DISCLOSURE_CANDIDATE_CLAIM_DUPLICATE")
        claim_ids.add(claim["claim_id"])
        evidence = by_id.get(claim["evidence_id"])
        if evidence is None:
            raise ValueError("DISCLOSURE_CANDIDATE_CITATION_INVALID")
        if claim["claim_type"] not in CLAIM_TYPES or not claim["text"] or not claim["source_quote"]:
            raise ValueError("DISCLOSURE_CANDIDATE_CLAIM_INVALID")
        if claim["source_quote"] not in evidence["text"]:
            raise ValueError("DISCLOSURE_CANDIDATE_QUOTE_NOT_FOUND")
        if evidence["truncated"] and "SOURCE_TRUNCATED" not in claim["limitations"]:
            raise ValueError("DISCLOSURE_CANDIDATE_TRUNCATION_UNACKNOWLEDGED")
        if claim["claim_type"] == "RELATIONSHIP":
            if claim["relationship_basis"] not in {"DIRECT_DISCLOSURE", "ANONYMOUS_DISCLOSURE"}:
                raise ValueError("DISCLOSURE_CANDIDATE_RELATIONSHIP_BASIS_INVALID")
            if claim["anonymity_status"] == "ANONYMOUS" and claim["object_name"] is not None:
                raise ValueError("DISCLOSURE_CANDIDATE_ANONYMITY_VIOLATION")
            if claim["relationship_basis"] == "ANONYMOUS_DISCLOSURE" \
                    and claim["anonymity_status"] != "ANONYMOUS":
                raise ValueError("DISCLOSURE_CANDIDATE_ANONYMITY_STATUS_INVALID")
        elif claim["relationship_basis"] is not None or claim["anonymity_status"] != "NOT_APPLICABLE" \
                or claim["object_name"] is not None:
            raise ValueError("DISCLOSURE_CANDIDATE_RELATIONSHIP_FIELDS_UNEXPECTED")
        if not isinstance(claim["limitations"], list):
            raise ValueError("DISCLOSURE_CANDIDATE_LIMITATIONS_INVALID")
    expected = content_hash({key: item for key, item in output.items() if key != "output_hash"})
    if output["output_hash"] != expected:
        raise ValueError("DISCLOSURE_CANDIDATE_OUTPUT_HASH_MISMATCH")


def build_candidate_output(
    candidate_input: Mapping[str, Any], *, claims: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output = {
        "schema_version": OUTPUT_VERSION,
        "input_hash": candidate_input["input_hash"],
        "security_id": candidate_input["security_id"],
        "claims": [deepcopy(dict(item)) for item in claims],
    }
    output["output_hash"] = content_hash(output)
    validate_candidate_output(candidate_input, output)
    return output
