"""既有研究入口共用的任务限定引用；只做精确转换，不改研究语义。"""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from product.runtime.hashing import (
    canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError,
)


LEGACY_VERSION = "multidimensional-references/1.0.0"
VERSION = "multidimensional-references/2.0.0"
READ_VERSIONS = {LEGACY_VERSION, VERSION}
CLAIM_REFERENCE_PREFIX = "rc1."
EVIDENCE_FIELDS = {"evidence_refs", "counter_evidence_refs", "input_evidence_refs",
                   "evidence_ids", "allowed_evidence_ids", "public_lead_evidence_ids"}
CLAIM_FIELDS = {"research_claim_refs", "target_claim_refs", "allowed_research_claim_ids"}
DOCUMENT_FIELDS = {"document_refs", "document_selections"}
REPORT_FIELDS = {"report_ids", "report_selections"}


def reference_output_schema(schema: Mapping[str, Any], mapping: Mapping[str, Any]) -> dict[str, Any]:
    """沿原业务 Schema 绑定 Evidence 短允许集，不复制研究字段规则。"""
    validate_reference_map(mapping)
    allowed = list(mapping["evidence"])
    identity = {"type": "string", "enum": allowed} if allowed else {"not": {}}
    reports = {value: ref for ref, value in mapping.get("reports", {}).items()}

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return copy.deepcopy(node)
        result = {key: walk(item) for key, item in node.items() if key != "x-evidence-id-constraint"}
        if "evidence_id" in result.get("$defs", {}):
            result["$defs"]["evidence_id"] = copy.deepcopy(identity)
        for name, field in result.get("properties", {}).items():
            if name in EVIDENCE_FIELDS and "items" in field and "$ref" not in field["items"]:
                field["items"] = copy.deepcopy(identity)
            elif name == "evidence_id":
                result["properties"][name] = copy.deepcopy(identity)
            elif reports and name in REPORT_FIELDS and "items" in field:
                old = field["items"].get("enum")
                field["items"] = {"type": "string", "enum":
                    [reports[value] for value in old if value in reports] if old is not None else list(reports.values())}
            elif reports and name == "report_id":
                old = field.get("enum")
                result["properties"][name] = {"type": "string", "enum":
                    [reports[value] for value in old if value in reports] if old is not None else list(reports.values())}
        return result

    return walk(dict(schema))


def model_claim_targets(mapping: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Readable targets only; exact report-version hashes stay on the runtime side."""
    validate_reference_map(mapping)
    return {short: {key: item[key] for key in ("report_id", "claim_id")}
            for short, item in mapping["claims"].items()}


def scoped_claim_reference(report: Mapping[str, Any], claim_id: str) -> str:
    """Lossless versioned identity, not a fuzzy lookup or model-authored hash.

    Hex encoding retains arbitrary UTF-8 report/claim identities while fitting the
    existing formal canonical-ID string fields. The report hash is a version lock.
    Models receive c.* aliases; only deterministic assembly emits this long ID.
    """
    report_id, digest = report.get("report_id"), report.get("report_hash")
    if (not isinstance(report_id, str) or not report_id
            or not isinstance(claim_id, str) or not claim_id
            or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
        raise ValueError("RESEARCH_CLAIM_BINDING_INVALID")
    return f"{CLAIM_REFERENCE_PREFIX}{report_id.encode().hex()}.{digest}.{claim_id.encode().hex()}"


def parse_scoped_claim_reference(reference: str) -> dict[str, str]:
    """Decode a formal ID for readers; decoding alone never proves authorization."""
    try:
        prefix, report_id, digest, claim_id = reference.split(".")
        result = {"report_id": bytes.fromhex(report_id).decode("utf-8"),
                  "report_hash": digest, "claim_id": bytes.fromhex(claim_id).decode("utf-8")}
        if prefix != "rc1" or scoped_claim_reference(result, result["claim_id"]) != reference:
            raise ValueError()
        return result
    except (AttributeError, TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("RESEARCH_CLAIM_REFERENCE_INVALID") from exc


def known_claim_references(reports, *, allow_legacy: bool = True) -> list[str]:
    """Admit exact report versions; old bare IDs are readable only if unambiguous."""
    scoped, counts, identities = set(), {}, set()
    for report in reports:
        identity = (report.get("report_id"), report.get("report_hash"))
        if identity in identities:
            raise ValueError("RESEARCH_CLAIM_REPORT_DUPLICATE")
        identities.add(identity)
        local = set()
        for claim in report.get("claims", []):
            claim_id = claim.get("claim_id")
            if claim_id in local:
                raise ValueError("RESEARCH_CLAIM_LOCAL_DUPLICATE")
            local.add(claim_id)
            scoped.add(scoped_claim_reference(report, claim_id))
            counts[claim_id] = counts.get(claim_id, 0) + 1
    if allow_legacy:
        scoped.update(key for key, count in counts.items() if count == 1)
    return sorted(scoped)


def build_reference_map(packet: Mapping[str, Any], gate_hash: str, run_dir: str) -> dict[str, Any]:
    dependencies = packet.get("dependency_reports", [])
    if len({r["report_id"] for r in dependencies}) != len(dependencies):
        raise ValueError("MULTIDIMENSIONAL_REFERENCE_REPORT_AMBIGUOUS")
    binding = {
        "version": packet.get("reference_transport_version", VERSION), "identity": packet["identity"], "gate_hash": gate_hash,
        "run_dir": run_dir, "packet_hash": canonical_hash(packet),
        "evidence_ids": sorted(packet["allowed_evidence_ids"]),
        "dependencies": sorted(
            [[r["report_id"], r["report_hash"]] for r in dependencies]
        ),
    }
    documents = packet.get("task", {}).get("allowed_documents", [])
    if binding["version"] == VERSION:
        document_ids = [item["document_id"] for item in documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("MULTIDIMENSIONAL_REFERENCE_DOCUMENT_AMBIGUOUS")
        binding["documents"] = sorted([[item["document_id"], canonical_hash(item)] for item in documents])
        if "report_catalog" in packet:
            reports = packet["report_catalog"]
            if len({item["report_id"] for item in reports}) != len(reports):
                raise ValueError("MULTIDIMENSIONAL_REFERENCE_REPORT_AMBIGUOUS")
            binding["reports"] = sorted([[item["report_id"], canonical_hash(item)] for item in reports])
    scope = canonical_hash(binding)[:12]
    evidence = {f"e.{scope}.{i}": identifier
                for i, identifier in enumerate(binding["evidence_ids"], 1)}
    claims = {}
    seen = set()
    for report in sorted(dependencies, key=lambda r: (r["report_id"], r["report_hash"])):
        local = set()
        for claim in sorted(report["claims"], key=lambda c: c["claim_id"]):
            identifier = claim["claim_id"]
            if identifier in local or (binding["version"] == LEGACY_VERSION and identifier in seen):
                raise ValueError("MULTIDIMENSIONAL_REFERENCE_CLAIM_AMBIGUOUS")
            local.add(identifier)
            seen.add(identifier)
            claims[f"c.{scope}.{len(claims) + 1}"] = {
                "report_id": report["report_id"], "claim_id": identifier,
                **({"report_hash": report["report_hash"],
                    "canonical_ref": scoped_claim_reference(report, identifier)}
                   if binding["version"] == VERSION else {}),
            }
    result = {"binding": binding, "evidence": evidence, "claims": claims}
    if binding["version"] == VERSION:
        result["documents"] = {f"d.{scope}.{i}": identity
                               for i, (identity, _) in enumerate(binding["documents"], 1)}
        if "reports" in binding:
            result["reports"] = {f"p.{scope}.{i}": identity
                                 for i, (identity, _) in enumerate(binding["reports"], 1)}
    return {**result, "map_hash": legacy_envelope_hash(result, hash_field="map_hash")}


def validate_reference_map(mapping: Mapping[str, Any]) -> None:
    if mapping.get("binding", {}).get("version") not in READ_VERSIONS:
        raise ValueError("MULTIDIMENSIONAL_REFERENCE_MAP_INVALID")
    try:
        verify_legacy_envelope_hash(mapping, hash_field="map_hash", location="task/reference-map")
    except HashContractError as exc:
        raise ValueError(f"MULTIDIMENSIONAL_REFERENCE_MAP_INVALID:{exc}") from exc
    if mapping["binding"]["version"] == VERSION:
        binding = mapping["binding"]
        scope = canonical_hash(binding)[:12]
        evidence = {f"e.{scope}.{i}": value for i, value in enumerate(binding["evidence_ids"], 1)}
        if evidence != mapping.get("evidence"):
            raise ValueError("MULTIDIMENSIONAL_REFERENCE_MAP_INVALID")
        documents = {f"d.{scope}.{i}": identity
                     for i, (identity, _) in enumerate(binding["documents"], 1)}
        if documents != mapping.get("documents"):
            raise ValueError("MULTIDIMENSIONAL_REFERENCE_MAP_INVALID")
        if "reports" in binding:
            reports = {f"p.{scope}.{i}": identity
                       for i, (identity, _) in enumerate(binding["reports"], 1)}
            if reports != mapping.get("reports") or len(set(reports.values())) != len(reports):
                raise ValueError("MULTIDIMENSIONAL_REFERENCE_MAP_INVALID")
        elif "reports" in mapping:
            raise ValueError("MULTIDIMENSIONAL_REFERENCE_MAP_INVALID")
        seen = set()
        claim_table = mapping.get("claims", {})
        if set(claim_table) != {f"c.{scope}.{i}" for i in range(1, len(claim_table) + 1)}:
            raise ValueError("MULTIDIMENSIONAL_REFERENCE_MAP_INVALID")
        for short, item in claim_table.items():
            ref = scoped_claim_reference(item, item["claim_id"])
            if (item.get("canonical_ref") != ref or ref in seen
                    or [item["report_id"], item["report_hash"]] not in binding["dependencies"]):
                raise ValueError("MULTIDIMENSIONAL_REFERENCE_MAP_INVALID")
            seen.add(ref)


def translate_references(value: Any, mapping: Mapping[str, Any], *,
                         to_model: bool = False, local_claims: set[str] | None = None) -> Any:
    """Translate only explicit reference fields; never prose, identities or values."""
    validate_reference_map(mapping)
    if mapping["binding"]["version"] == VERSION and any(
        identifier.startswith(("e.", "c.", "d.", "k.", "p.", CLAIM_REFERENCE_PREFIX))
        for identifier in (local_claims or set())
    ):
        raise ValueError("MULTIDIMENSIONAL_REFERENCE_LOCAL_NAMESPACE_COLLISION")
    evidence = dict(mapping["evidence"])
    documents = dict(mapping.get("documents", {}))
    reports = dict(mapping.get("reports", {}))
    claims = {k: v.get("canonical_ref", v["claim_id"]) for k, v in mapping["claims"].items()}
    if to_model:
        evidence = {v: k for k, v in evidence.items()}
        documents = {v: k for k, v in documents.items()}
        reports = {v: k for k, v in reports.items()}
        claims = {v: k for k, v in claims.items()}

    def resolve(ref: Any, table: Mapping[str, str], path: str) -> Any:
        if not isinstance(ref, str):
            return ref  # Original Schema is responsible for invalid types.
        if ref in table:
            return table[ref]
        if not to_model and ref.startswith(("e.", "c.", "d.", "k.", "p.", CLAIM_REFERENCE_PREFIX)):
            # Canonical refs produced by this exact verified map are accepted;
            # refs from other tasks/types/versions are never guessed or trimmed.
            if ref in table.values():
                return ref
            raise ValueError(f"MULTIDIMENSIONAL_REFERENCE_UNKNOWN:{path}:{ref}")
        return ref  # Full IDs and local claims still pass the original validators.

    def walk(item: Any, path: str = "") -> Any:
        if isinstance(item, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(item)]
        if not isinstance(item, dict):
            return copy.deepcopy(item)
        result = {}
        for key, child in item.items():
            location = f"{path}.{key}" if path else key
            if key == "evidence_id":
                result[key] = resolve(child, evidence, location)
            elif key in {"document_id", "duplicate_of", "revision_of"}:
                result[key] = resolve(child, documents, location)
            elif reports and key == "report_id":
                result[key] = resolve(child, reports, location)
            elif reports and key in REPORT_FIELDS and isinstance(child, list):
                result[key] = [resolve(ref, reports, f"{location}[{i}]") for i, ref in enumerate(child)]
            elif key in EVIDENCE_FIELDS | CLAIM_FIELDS | DOCUMENT_FIELDS and isinstance(child, list):
                table = evidence if key in EVIDENCE_FIELDS else documents if key in DOCUMENT_FIELDS else claims
                result[key] = [
                    ref if key in CLAIM_FIELDS and ref in (local_claims or set())
                    else resolve(ref, table, f"{location}[{i}]")
                    for i, ref in enumerate(child)
                ]
            elif key in {"value", "metadata", "output_schema", "identity"}:
                result[key] = copy.deepcopy(child)
            else:
                result[key] = walk(child, location)
        return result

    return walk(value)
