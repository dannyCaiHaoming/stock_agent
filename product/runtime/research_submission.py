"""语义草稿提交与预检查；正式接受仍由可信 Stop 全量验证，不负责调度。"""
from __future__ import annotations

import json
import os
import re
import secrets
import copy
import fcntl
from pathlib import Path
from typing import Any

from product.runtime.hashing import canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError
from product.runtime.multidimensional_references import (
    load_reference_packet, scoped_claim_reference, VERSION as REFERENCE_VERSION,
)

LEGACY_VERSION = "research-object-submission/1.0.0"
PREVIOUS_VERSION = "research-object-submission/2.0.0"
VERSION = "research-object-submission/3.0.0"
FORMAL_VERSION = "research-object-submission/4.0.0"
SHORT_RECEIPT_VERSION = "research-object-submission/5.0.0"
BOUNDED_REVISION_VERSION = "research-object-submission/6.0.0"
LATEST_VERSION = BOUNDED_REVISION_VERSION
SHORT_RECEIPT_VERSIONS = {SHORT_RECEIPT_VERSION, BOUNDED_REVISION_VERSION}
FORMAL_VERSIONS = {FORMAL_VERSION, *SHORT_RECEIPT_VERSIONS}
READ_VERSIONS = {LEGACY_VERSION, PREVIOUS_VERSION, VERSION, *FORMAL_VERSIONS}
# 历史草稿装配不是当前提交权限。旧包仍按原算法读取，不能因此开放旧写入。
ASSEMBLY_VERSIONS = {VERSION, *FORMAL_VERSIONS}
WRITE_VERSIONS = {BOUNDED_REVISION_VERSION}
PERMISSION = "research_report.submit"
IDENTITY_FIELDS = {"run_id", "invocation_id", "agent"}
MAX_BYTES = 256 * 1024
MAX_STORED_BYTES = MAX_BYTES * 2 + 32768
MAX_CITATION_REVIEW_PAIRS = 32
MAX_CITATION_REVIEW_BYTES = 16 * 1024
MAX_MONETARY_REVIEW_FINDINGS = 32
MAX_SOURCE_REVIEW_PAIRS = 4
MAX_SOURCE_REVIEW_PER_CLAIM = 2
MAX_SOURCE_REVIEW_BYTES = 12 * 1024


def require_write_protocol(task: dict[str, Any]) -> None:
    """当前对象写入只允许原生选择协议，历史装配版本不等于执行准入。"""
    if task.get("submission_version") not in WRITE_VERSIONS:
        raise ValueError("RESEARCH_SUBMISSION_LEGACY_READ_ONLY")
    from product.runtime.calculation_handoff import VERSION as SELECTION_VERSION
    if task.get("calculation_selection_version") != SELECTION_VERSION:
        raise ValueError("RESEARCH_SUBMISSION_SELECTION_PROTOCOL_INVALID")


def tool_manifest() -> dict[str, Any]:
    return {
        "name": "research_report_submit",
        "description": "仅用于明确提供 submission_contract 和 submission_token 的 RESEARCH_REPORT 任务；工具可见不代表任务已获授权。首稿 draft 只写研究和明确选择，禁止填写 run_id/agent/invocation_id 或凭据。当前有界协议最多首稿加一次原 Agent 修订，无效授权首稿也占额度。修订必须使用反馈所给 base_draft_ref 与 changes，仅修改 allowed_paths，不能重交整稿或借新回执无限重试。读取 citation_review、monetary_review、source_evidence_review，核对上游限定及实际查询的原文；这些是辅助检查而非研究语义通过证明。最终只原样返回 final_message 短引用，不抄 hash；正式接受仍依赖可信执行身份和完整 Stop 校验。其它任务禁止使用本工具，沿本任务实际输出契约执行。",
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        "inputSchema": {
            "type": "object", "required": ["invocation_id", "submission_token", "draft"], "additionalProperties": False,
            "properties": {"invocation_id": {"type": "string"}, "submission_token": {"type": "string"}, "draft": {"type": "object"}},
        },
    }


def _packet(root: Path, invocation_id: str, *, include_dependencies: bool = True,
            for_execution: bool = True) -> dict[str, Any]:
    packet = load_reference_packet(root, invocation_id, include_dependencies=include_dependencies,
                                   for_execution=for_execution)
    task = packet["task"]
    if task.get("submission_version") not in READ_VERSIONS or task.get("capability") != "RESEARCH_REPORT":
        raise ValueError("RESEARCH_SUBMISSION_NOT_ENABLED")
    index = json.loads((root / "research/dispatch-index.json").read_text())
    indexed = next(t for t in index["tasks"] if t["invocation_id"] == invocation_id)
    path = root / indexed["invocation_path"]
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("RESEARCH_SUBMISSION_PATH_INVALID")
    invocation = json.loads(path.read_text())
    if invocation.get("manifest_hash") != legacy_envelope_hash(invocation, hash_field="manifest_hash"):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    if PERMISSION not in invocation.get("tool_permissions", []):
        raise ValueError("RESEARCH_SUBMISSION_NOT_AUTHORIZED")
    return packet


def _directory(root: Path, invocation_id: str, *, create: bool = True) -> Path:
    # No caller-controlled path. Reject symlinks in every created component.
    result = root
    for part in ("research", "submissions", canonical_hash({"invocation_id": invocation_id})[:24]):
        result = result / part
        if result.is_symlink():
            raise ValueError("RESEARCH_SUBMISSION_PATH_INVALID")
        if create:
            result.mkdir(exist_ok=True)
    return result


def _assemble_v3_draft(draft: dict[str, Any], packet: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Expand explicit choices from the verified task packet, without editing research prose."""
    result = copy.deepcopy(draft)
    if "document_selections" in result:
        choices = result.pop("document_selections")
        result["documents"] = _selected_documents(draft, packet, choices)
    selections = result.pop("upstream_calculation_selections", [])
    if not isinstance(selections, list):
        raise ValueError("RESEARCH_SUBMISSION_CALCULATION_SELECTION_INVALID")
    dependency_by_id = {item["report_id"]: item for item in packet.get("dependency_reports", [])}
    claims = {item.get("claim_id"): item for item in result.get("claims", []) if isinstance(item, dict)}
    from product.runtime.multidimensional_references import translate_references
    full_claims = translate_references(
        result.get("claims", []), packet["reference_map"], local_claims=set(claims)
    ) if packet.get("reference_map") is not None else result.get("claims", [])
    full_by_id = {item.get("claim_id"): item for item in full_claims if isinstance(item, dict)}
    validated = []
    seen = set()
    for item in selections:
        required = {"claim_id", "report_id", "source_claim_id", "calculation_id"}
        if not isinstance(item, dict) or set(item) != required or any(
            not isinstance(item[key], str) or not item[key] for key in required
        ):
            raise ValueError("RESEARCH_SUBMISSION_CALCULATION_SELECTION_INVALID")
        identity = tuple(item[key] for key in ("claim_id", "report_id", "source_claim_id", "calculation_id"))
        if identity in seen:
            raise ValueError("RESEARCH_SUBMISSION_CALCULATION_SELECTION_AMBIGUOUS")
        seen.add(identity)
        claim = full_by_id.get(item["claim_id"])
        dependency = dependency_by_id.get(item["report_id"])
        source_ref = (scoped_claim_reference(dependency, item["source_claim_id"])
                      if isinstance(dependency, dict) and packet.get("reference_map", {}).get("binding", {}).get("version") == REFERENCE_VERSION
                      else item["source_claim_id"])
        if (not isinstance(claim, dict) or not isinstance(dependency, dict)
                or source_ref not in claim.get("research_claim_refs", [])):
            raise ValueError("RESEARCH_SUBMISSION_CALCULATION_CLAIM_MISMATCH")
        matches = [record for record in dependency.get("verified_calculations", [])
                   if record["claim_id"] == item["source_claim_id"]
                   and record["calculation_id"] == item["calculation_id"]]
        if len(matches) != 1:
            raise ValueError("RESEARCH_SUBMISSION_CALCULATION_NOT_VERIFIED")
        validated.append({
            **item, "report_hash": dependency["report_hash"],
            "report_artifact_ref": dependency["artifact_ref"],
            "calculation": copy.deepcopy(matches[0]),
        })
    return result, validated


def _assemble_v4_draft(draft: dict[str, Any], packet: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Bind Agent-authored relation clauses to this claim's verified dependencies."""
    result = copy.deepcopy(draft)
    claims = result.get("claims")
    if not isinstance(claims, list):
        raise ValueError("RESEARCH_SUBMISSION_RELATION_CLAIMS_INVALID")
    local_ids = {claim.get("claim_id") for claim in claims if isinstance(claim, dict)}
    mapping = packet.get("reference_map") or {}
    from product.runtime.multidimensional_references import validate_reference_map
    validate_reference_map(mapping)
    short = mapping["claims"]
    verified = {
        (report["report_id"], claim["claim_id"])
        for report in packet.get("dependency_reports", []) for claim in report["claims"]
    }
    by_full_id: dict[str, tuple[str, str]] = {}
    for report in packet.get("dependency_reports", []):
        for claim in report["claims"]:
            report_id, claim_id = report["report_id"], claim["claim_id"]
            reference = (scoped_claim_reference(report, claim_id)
                         if mapping["binding"]["version"] == REFERENCE_VERSION else claim_id)
            if reference in by_full_id:
                raise ValueError("RESEARCH_SUBMISSION_RELATION_DEPENDENCY_AMBIGUOUS")
            by_full_id[reference] = (report_id, claim_id)
    if local_ids & (set(short) | set(by_full_id)):
        raise ValueError("RESEARCH_SUBMISSION_RELATION_REFERENCE_COLLISION")

    def external(ref: Any, path: str) -> tuple[str, str] | None:
        if not isinstance(ref, str):
            raise ValueError(f"RESEARCH_SUBMISSION_RELATION_REFERENCE_INVALID:{path}")
        if ref in local_ids:
            return None
        if ref in short:
            item = short[ref]
            identity = (item["report_id"], item["claim_id"])
        elif ref.startswith("c."):
            raise ValueError(f"MULTIDIMENSIONAL_REFERENCE_UNKNOWN:{path}:{ref}")
        else:
            identity = by_full_id.get(ref)
        if identity not in verified:
            raise ValueError(f"RESEARCH_SUBMISSION_RELATION_REFERENCE_INVALID:{path}:{ref}")
        return identity

    for index, claim in enumerate(claims):
        path = f"claims[{index}]"
        if not isinstance(claim, dict) or "statement" in claim:
            raise ValueError(f"RESEARCH_SUBMISSION_RELATION_PROTOCOL_MIXED:{path}")
        core = claim.pop("core_statement", None)
        clauses = claim.pop("research_relation_clauses", None)
        refs = claim.get("research_claim_refs")
        if not isinstance(core, str) or not core.strip() or not isinstance(clauses, list) or not isinstance(refs, list):
            raise ValueError(f"RESEARCH_SUBMISSION_RELATION_SHAPE_INVALID:{path}")
        expected = []
        for ref_index, ref in enumerate(refs):
            identity = external(ref, f"{path}.research_claim_refs[{ref_index}]")
            if identity is not None:
                expected.append(identity)
        if len(expected) != len(set(expected)):
            raise ValueError(f"RESEARCH_SUBMISSION_RELATION_DUPLICATE:{path}.research_claim_refs")
        authored: dict[tuple[str, str], str] = {}
        for clause_index, clause in enumerate(clauses):
            location = f"{path}.research_relation_clauses[{clause_index}]"
            if not isinstance(clause, dict) or set(clause) != {"research_claim_ref", "relation_statement"}:
                raise ValueError(f"RESEARCH_SUBMISSION_RELATION_SHAPE_INVALID:{location}")
            identity = external(clause["research_claim_ref"], f"{location}.research_claim_ref")
            sentence = clause["relation_statement"]
            if identity is None or not isinstance(sentence, str) or not sentence.strip():
                raise ValueError(f"RESEARCH_SUBMISSION_RELATION_SHAPE_INVALID:{location}")
            if identity in authored:
                raise ValueError(f"RESEARCH_SUBMISSION_RELATION_DUPLICATE:{location}")
            authored[identity] = sentence
        missing = next((identity for identity in expected if identity not in authored), None)
        if missing is not None:
            raise ValueError(f"RESEARCH_SUBMISSION_RELATION_MISSING:{path}:{missing[1]}")
        extra = next((identity for identity in authored if identity not in expected), None)
        if extra is not None:
            raise ValueError(f"RESEARCH_SUBMISSION_RELATION_EXTRA:{path}:{extra[1]}")
        claim["statement"] = " ".join([core, *[clause["relation_statement"] for clause in clauses]])
    return _assemble_v3_draft(result, packet)


def _assemble_draft(draft: dict[str, Any], packet: dict[str, Any], *, root: Path | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if "calculation_selections" in draft:
        from product.runtime.calculation_handoff import validate_semantic_selection_draft
        validate_semantic_selection_draft(draft, packet)
        if root is None:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_CONTEXT_REQUIRED")
        from product.runtime.calculation_handoff import assemble_calculation_selections
        draft = assemble_calculation_selections(root, packet, draft)
    return (_assemble_v4_draft if packet["task"]["submission_version"] in FORMAL_VERSIONS
            else _assemble_v3_draft)(draft, packet)


def _v4_reference_binding(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "short_to_full": {
            short: item.get("canonical_ref", item["claim_id"])
            for short, item in packet["reference_map"]["claims"].items()
        },
        "external_claim_ids": sorted({
            item.get("canonical_ref", item["claim_id"])
            for item in packet["reference_map"]["claims"].values()
        }),
    }


def _verify_v4_saved_statements(
    draft: dict[str, Any], report: dict[str, Any], reference_binding: dict[str, Any],
) -> None:
    """Recheck exact original refs and prose in saved or copied v4 packages."""
    source_claims = draft.get("claims")
    final_claims = report.get("claims")
    short = reference_binding.get("short_to_full") if isinstance(reference_binding, dict) else None
    external_ids = reference_binding.get("external_claim_ids") if isinstance(reference_binding, dict) else None
    if (not isinstance(source_claims, list) or not isinstance(final_claims, list)
            or len(source_claims) != len(final_claims) or not isinstance(short, dict)
            or not isinstance(external_ids, list) or any(not isinstance(x, str) for x in external_ids)
            or len(external_ids) != len(set(external_ids))
            or len(short.values()) != len(set(short.values()))
            or any(not isinstance(k, str) or not isinstance(v, str) or v not in external_ids
                   for k, v in short.items())):
        raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")
    local_ids = {claim.get("claim_id") for claim in source_claims if isinstance(claim, dict)}
    if local_ids & (set(short) | set(external_ids)):
        raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")

    def resolve_ref(ref: Any) -> str:
        if not isinstance(ref, str):
            raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")
        if ref in local_ids:
            return ref
        if ref in short:
            return short[ref]
        if ref in external_ids:
            return ref
        raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")

    for source, final in zip(source_claims, final_claims):
        if not isinstance(source, dict) or not isinstance(final, dict):
            raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")
        core = source.get("core_statement")
        clauses = source.get("research_relation_clauses")
        refs = source.get("research_claim_refs")
        if ("statement" in source or not isinstance(core, str) or not core.strip()
                or not isinstance(clauses, list)
                or not isinstance(refs, list)
                or not all(isinstance(clause, dict)
                           and set(clause) == {"research_claim_ref", "relation_statement"}
                           and isinstance(clause.get("relation_statement"), str)
                           and clause["relation_statement"].strip()
                           for clause in clauses)):
            raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")
        resolved = [resolve_ref(ref) for ref in refs]
        external_refs = [ref for ref in resolved if ref not in local_ids]
        clause_refs = [resolve_ref(clause.get("research_claim_ref")) for clause in clauses]
        if (final.get("research_claim_refs") != resolved or len(external_refs) != len(set(external_refs))
                or len(clause_refs) != len(set(clause_refs)) or set(clause_refs) != set(external_refs)):
            raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")
        expected = " ".join([core, *[clause["relation_statement"] for clause in clauses]])
        if final.get("claim_id") != source.get("claim_id") or final.get("statement") != expected:
            raise ValueError("RESEARCH_SUBMISSION_RELATION_SAVED_MISMATCH")


def _selected_documents(draft: dict[str, Any], packet: dict[str, Any], choices: Any) -> list[dict[str, Any]]:
    """Check document identity before storing a submission; never choose for the Agent."""
    if "documents" in draft:
        raise ValueError("RESEARCH_SUBMISSION_DOCUMENT_PROTOCOL_MIXED")
    if not isinstance(choices, list) or any(not isinstance(x, str) for x in choices):
        raise ValueError("RESEARCH_SUBMISSION_DOCUMENT_SELECTION_INVALID")
    if len(choices) != len(set(choices)):
        raise ValueError("RESEARCH_SUBMISSION_DOCUMENT_SELECTION_AMBIGUOUS")
    if packet.get("reference_map") is not None:
        from product.runtime.multidimensional_references import translate_references
        mapping = packet["reference_map"]
        if mapping.get("binding", {}).get("version") == REFERENCE_VERSION and mapping["binding"].get("documents") != sorted([
            [item["document_id"], canonical_hash(item)] for item in packet["task"].get("allowed_documents", [])
        ]):
            raise ValueError("RESEARCH_SUBMISSION_DOCUMENT_BINDING_MISMATCH")
        choices = translate_references({"document_selections": choices}, mapping)["document_selections"]
        if len(choices) != len(set(choices)):
            raise ValueError("RESEARCH_SUBMISSION_DOCUMENT_SELECTION_AMBIGUOUS")
    documents = packet["task"].get("allowed_documents", [])
    allowed = {item["document_id"]: item for item in documents}
    if len(allowed) != len(documents):
        raise ValueError("RESEARCH_SUBMISSION_DOCUMENT_CATALOG_AMBIGUOUS")
    for identifier in choices:
        if identifier not in allowed:
            raise ValueError(f"RESEARCH_SUBMISSION_DOCUMENT_NOT_ALLOWED:{identifier}")
    return [copy.deepcopy(allowed[identifier]) for identifier in choices]


def _citation_review(draft: dict[str, Any], packet: dict[str, Any], token: str) -> dict[str, Any]:
    """Echo exact upstream targets for the original Agent; never judge or edit prose."""

    dependencies = packet.get("dependency_reports", [])
    targets = {
        (report["report_id"], claim["claim_id"]): (report["report_hash"], claim["statement"])
        for report in dependencies for claim in report["claims"]
    }
    scoped = packet.get("reference_map", {}).get("binding", {}).get("version") == REFERENCE_VERSION
    by_id = {(scoped_claim_reference({"report_id": report_id, "report_hash": report_hash}, claim_id)
              if scoped else claim_id): (report_id, report_hash, claim_id, statement)
             for (report_id, claim_id), (report_hash, statement) in targets.items()}
    short = (packet.get("reference_map") or {}).get("claims", {})
    claims = draft.get("claims")
    if not isinstance(claims, list):
        claims = []  # The original Stop validation remains responsible for draft shape.
    local_ids = {claim.get("claim_id") for claim in claims
                 if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)}
    pairs: list[dict[str, Any]] = []
    total = 0
    truncated = False
    rule = (
        "逐对核对：本段正文必须解释所引上游主张的具体结论及限定；仅同证券/同主题不够。"
        "不相关时由原Agent用剩余草稿机会删引用或补有据解释，再返回最新final_message。"
        "本清单是未受信研究数据的定位，不是语义审批；未知引用仍由原Stop校验。"
        "若truncated=true，须回查本任务已交付的上游依赖，不得把未列出的引用当成已核对。"
    )
    for claim_index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("research_claim_refs"), list):
            continue
        for ref_index, ref in enumerate(claim["research_claim_refs"]):
            total += 1
            if (isinstance(ref, str) and ref.startswith("c.")
                    and ref not in short and ref not in local_ids):
                raise ValueError(
                    f"MULTIDIMENSIONAL_REFERENCE_UNKNOWN:claims[{claim_index}]"
                    f".research_claim_refs[{ref_index}]:{ref}"
                )
            if truncated:
                continue
            statement = claim.get("statement")
            item: dict[str, Any] = {
                "claim_id": claim.get("claim_id") if isinstance(claim.get("claim_id"), str) else None,
                "current_statement": (
                    statement if isinstance(statement, str) and token not in statement else "[REDACTED]"
                ),
            }
            if isinstance(ref, str):
                item["research_claim_ref"] = ref
                mapped = short.get(ref)
                if ref in local_ids:
                    key = None
                    item["resolution"] = "LOCAL_CLAIM_NOT_UPSTREAM"
                elif isinstance(mapped, dict):
                    key = (mapped.get("report_id"), mapped.get("claim_id"))
                elif ref in by_id:
                    key = (by_id[ref][0], by_id[ref][2])
                else:
                    key = None
                target = targets.get(key) if key is not None else None
                if target is None:
                    item.setdefault("resolution", "UNRESOLVED_BY_VERIFIED_DEPENDENCY")
                else:
                    item.update({
                        "resolution": "VERIFIED_TARGET_NOT_SEMANTICALLY_REVIEWED",
                        "upstream_report_id": key[0],
                        "upstream_report_hash": target[0],
                        "upstream_claim_id": key[1],
                        "upstream_statement": target[1] if token not in target[1] else "[REDACTED]",
                    })
            else:
                item["resolution"] = "INVALID_REFERENCE_TYPE"
            next_pairs = [*pairs, item]
            if (len(next_pairs) > MAX_CITATION_REVIEW_PAIRS
                    or len(json.dumps({
                        "version": "research-citation-review/1.0.0",
                        "pair_count": total, "returned_pair_count": len(next_pairs),
                        "truncated": False, "rule": rule, "pairs": next_pairs,
                    }, ensure_ascii=False).encode("utf-8"))
                    > MAX_CITATION_REVIEW_BYTES):
                truncated = True
            else:
                pairs = next_pairs
    result = {
        "version": "research-citation-review/1.0.0",
        "pair_count": total, "returned_pair_count": len(pairs),
        "truncated": truncated, "rule": rule, "pairs": pairs,
    }
    while (pairs and len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
           > MAX_CITATION_REVIEW_BYTES):
        pairs.pop()
        result["returned_pair_count"] = len(pairs)
        result["truncated"] = True
    return result


def _source_evidence_review(
    root: Path, draft: dict[str, Any], packet: dict[str, Any], token: str,
) -> dict[str, Any]:
    """Privately echo bounded text already queried by this exact report task."""

    result: dict[str, Any] = {
        "version": "queried-source-excerpt-review/1.0.0", "status": "NOT_AVAILABLE",
        "pair_count": 0, "returned_pair_count": 0, "truncated": False, "pairs": [],
    }
    task = packet["task"]
    if (task.get("source_evidence_review") != result["version"]
            or task.get("capability") != "RESEARCH_REPORT"
            or task.get("submission_version") not in ASSEMBLY_VERSIONS):
        return result
    events_path = root / "events/mcp/events.jsonl"
    if not events_path.is_file() or events_path.is_symlink():
        return result
    try:
        queried: set[str] = set()
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event_type") != "mcp_tool_result" or event.get("tool") not in {
                "fixture_evidence.query", "live_evidence.query",
            }:
                continue
            if (event.get("run_id") != task["run_id"]
                    or event.get("invocation_id") != task["invocation_id"]
                    or event.get("agent") != task["agent"]):
                continue
            event_hash = event.get("event_hash")
            if event_hash != legacy_envelope_hash(event, hash_field="event_hash"):
                continue
            queried.update(ref for ref in event.get("evidence_ids", []) if isinstance(ref, str))
        if not queried:
            return result
        gate = json.loads((root / "evidence/gate.json").read_text(encoding="utf-8"))
        if gate.get("bundle_hash") != legacy_envelope_hash(
            gate, hash_field="bundle_hash"
        ):
            return result
    except (OSError, ValueError, TypeError, KeyError):
        return result
    allowed = set(task.get("allowed_evidence_ids", []))
    facts = {item["evidence_id"]: item for item in gate.get("allowed_evidence", [])
             if item.get("evidence_id") in allowed and item.get("evidence_id") in queried}
    short = (packet.get("reference_map") or {}).get("evidence", {})
    claims = draft.get("claims")
    if not isinstance(claims, list):
        return result
    groups: list[list[dict[str, Any]]] = []
    total = 0
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("statement"), str):
            continue
        refs = claim.get("evidence_refs", [])
        if not isinstance(refs, list):
            continue
        group: list[dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, str):
                continue
            full = short.get(ref, ref)
            fact = facts.get(full)
            value = fact.get("value") if isinstance(fact, dict) else None
            if (not isinstance(value, dict) or value.get("content_tier") != "LICENSED_API_CONTENT"
                    or not isinstance(value.get("content"), str)):
                continue
            total += 1
            if len(group) >= MAX_SOURCE_REVIEW_PER_CLAIM:
                result["truncated"] = True
                continue
            content = value["content"]
            if token in content or token in claim["statement"]:
                continue
            # Small sections remain intact; longer text is a pointer back to
            # the already authorized query, not an alternative full-text copy.
            excerpt = content if len(content) <= 1200 else content[:500]
            group.append({
                "path": f"claims[{index}].statement", "claim_id": claim.get("claim_id"),
                "evidence_ref": ref, "current_statement": claim["statement"][:700],
                "source_excerpt": excerpt, "source_excerpt_truncated": len(content) > len(excerpt),
            })
        if group:
            groups.append(group)
    # Give each claim one source before spending the bounded response on its
    # second source; otherwise a long opening claim can hide later conflicts.
    source_frequency = {
        ref: sum(pair["evidence_ref"] == ref for group in groups for pair in group)
        for group in groups for ref in (pair["evidence_ref"] for pair in group)
    }
    for group in groups:
        group.sort(key=lambda pair: -source_frequency[pair["evidence_ref"]])
    pairs: list[dict[str, Any]] = []
    for offset in range(MAX_SOURCE_REVIEW_PER_CLAIM):
        ordered = groups if offset == 0 else list(reversed(groups))
        for group in ordered:
            if len(group) <= offset:
                continue
            pair = group[offset]
            candidate = [*pairs, pair]
            probe = {**result, "status": "AVAILABLE", "pair_count": total,
                     "returned_pair_count": len(candidate), "pairs": candidate}
            if len(candidate) > MAX_SOURCE_REVIEW_PAIRS or len(json.dumps(
                probe, ensure_ascii=False,
            ).encode("utf-8")) > MAX_SOURCE_REVIEW_BYTES:
                result["truncated"] = True
            else:
                pairs = candidate
    result.update(
        status="AVAILABLE" if total else "NOT_AVAILABLE", pair_count=total,
        returned_pair_count=len(pairs), pairs=pairs,
        truncated=result["truncated"] or len(pairs) < total,
    )
    return result


def _event_path(root: Path, path: Path) -> Path:
    if (not path.resolve().is_relative_to(root.resolve())
            or any(part.is_symlink() for part in (path, *path.parents)
                   if part != root and root in part.parents)):
        raise ValueError("RESEARCH_SUBMISSION_EVENT_PATH_INVALID")
    return path


def _verify_submission_event(root: Path, invocation_id: str, number: int, digest: str) -> None:
    path = _event_path(root, root / "events/mcp/events.jsonl")
    if not path.is_file():
        raise ValueError("RESEARCH_SUBMISSION_EVENT_MISSING")
    matches = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("RESEARCH_SUBMISSION_EVENT_INVALID")
        if item.get("tool") == "research_report.submit" and item.get("invocation_id") == invocation_id and item.get("submission") == number:
            try:
                verify_legacy_envelope_hash(item, hash_field="event_hash", location="events/mcp/events.jsonl:research_report.submit")
            except HashContractError as exc:
                raise ValueError(f"RESEARCH_SUBMISSION_EVENT_DRIFT:{exc}") from exc
            matches.append(item)
    if len(matches) != 1 or matches[0].get("output_hash") != digest:
        raise ValueError("RESEARCH_SUBMISSION_EVENT_BINDING_INVALID")


def _stored_submission(root: Path, packet: dict, number: int, *, require_event=True) -> dict:
    path = _directory(root, packet["identity"]["invocation_id"], create=False) / f"{number}.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_STORED_BYTES:
        raise ValueError("RESEARCH_SUBMISSION_PATH_INVALID")
    value = json.loads(path.read_text())
    expected = {"version": packet["task"]["submission_version"], "identity": packet["identity"],
                "packet_hash": canonical_hash(packet)}
    if (value.get("binding") != expected or value.get("content_hash") != legacy_envelope_hash(value, hash_field="content_hash")):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    if require_event:
        _verify_submission_event(root, packet["identity"]["invocation_id"], number, value["content_hash"])
    return value


def submission_event_identity(root: Path, invocation_id: str, number: int,
                              digest: str, *, require_event: bool = True) -> dict[str, str]:
    """从精确草稿和冻结任务读取身份；不猜 invocation 前缀、不回写历史事件。"""
    if not isinstance(invocation_id, str) or not invocation_id or type(number) is not int or number not in (1, 2):
        raise ValueError("RESEARCH_SUBMISSION_EVENT_BINDING_INVALID")
    packet = _packet(root, invocation_id, for_execution=False)
    value = _stored_submission(root, packet, number, require_event=require_event)
    if value["content_hash"] != digest:
        raise ValueError("RESEARCH_SUBMISSION_EVENT_BINDING_INVALID")
    return dict(packet["identity"])


def _preflight_bounded(root: Path, packet: dict, draft: dict) -> tuple[dict, dict | None, list]:
    """只诊断草稿/选择，不伪造 Start、正文充分性或已接受报告。"""
    from product.runtime.schema_validation import validate_schema_instance, schema_issue_locations
    from product.runtime.calculation_handoff import semantic_selection_draft_schema
    from product.runtime.local_revision import located_paths

    # 用交付端共用的纯 Schema 派生器；生成上下文会读取计算目录，不能放在结构检查前。
    schema = semantic_selection_draft_schema(packet)
    findings = []
    try:
        findings = schema_issue_locations(draft, schema)
        if len(json.dumps(findings, ensure_ascii=False).encode("utf-8")) > 12 * 1024:
            findings = []
            raise ValueError("RESEARCH_SUBMISSION_DIAGNOSTICS_TOO_LARGE")
        validate_schema_instance(draft, schema)
        assembled, selected = _assemble_draft(draft, packet, root=root)
        return {"status": "PASSED"}, assembled, selected
    except (KeyError, TypeError, ValueError) as exc:
        code = str(exc)
        if len(code.encode("utf-8")) > 4096:
            code = "RESEARCH_SUBMISSION_DIAGNOSTICS_TOO_LARGE"
        # 已有程序错误格式的路径段；引用文本只能处于后续段，不能制造允许路径。
        if not findings:
            segments = code.split(":", 2)
            if (len(segments) >= 2 and segments[0].startswith(("RESEARCH_SUBMISSION_RELATION_", "MULTIDIMENSIONAL_REFERENCE_UNKNOWN"))
                    and re.fullmatch(r"claims\[\d+\](?:\.[A-Za-z_][A-Za-z_0-9]*|\[\d+\])*", segments[1])):
                findings.append({"code": segments[0], "path": segments[1]})
            if code.startswith("RESEARCH_SUBMISSION_DOCUMENT_NOT_ALLOWED:"):
                identifier = code.split(":", 1)[1]
                findings.extend({"code": "RESEARCH_SUBMISSION_DOCUMENT_NOT_ALLOWED", "path": f"document_selections[{i}]"}
                                for i, ref in enumerate(draft.get("document_selections", [])) if ref == identifier)
        return {"status": "FAILED", "failure_code": code, "findings": findings,
                "allowed_paths": located_paths(findings)}, None, []


def _bounded_repair(base: dict, packet: dict, findings: list, code: str) -> dict | None:
    from product.runtime.local_revision import located_paths, VERSION as REVISION_VERSION
    allowed = located_paths(findings)
    if not allowed:
        return None
    result = {"repair_contract": REVISION_VERSION, "base_draft_ref": "b." + secrets.token_urlsafe(18),
              "allowed_paths": allowed, "base_hash": canonical_hash(base["draft"]),
              "source_content_hash": base["content_hash"], "packet_hash": canonical_hash(packet),
              "validation_error": code}
    if code == "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED":
        result["monetary_findings"] = [
            {key: finding[key] for key in (
                "code", "path", "identifier", "amount_index", "source_unit", "reported_unit",
                "source_value", "reported_value", "amount_index_basis",
            ) if key in finding}
            for finding in findings
            if finding.get("code") == code
        ][:MAX_MONETARY_REVIEW_FINDINGS]
    return result if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= 15 * 1024 else None


def _repair_path(root: Path, packet: dict) -> Path:
    path = _directory(root, packet["identity"]["invocation_id"]) / "1.repair.json"
    if path.is_symlink():
        raise ValueError("RESEARCH_SUBMISSION_PATH_INVALID")
    return path


def _save_repair(path: Path, repair: dict) -> None:
    repair = {**repair, "content_hash": legacy_envelope_hash(repair, hash_field="content_hash")}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(repair, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def _read_repair(root: Path, packet: dict, base: dict) -> dict:
    path = _repair_path(root, packet)
    if not path.is_file() or path.stat().st_size > 16 * 1024:
        raise ValueError("RESEARCH_SUBMISSION_REVISION_NOT_AUTHORIZED")
    repair = json.loads(path.read_text())
    if (repair.get("content_hash") != legacy_envelope_hash(repair, hash_field="content_hash")
            or repair.get("packet_hash") != canonical_hash(packet)
            or repair.get("source_content_hash") != base["content_hash"]
            or repair.get("base_hash") != canonical_hash(base["draft"])):
        raise ValueError("RESEARCH_SUBMISSION_REVISION_BINDING_INVALID")
    # 约束来自实际工具反馈，或者可信第一份 Stop；不能信一个自行重签的 sidecar。
    event_path = _event_path(root, root / "events/mcp/events.jsonl")
    events = [json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
    if any(not isinstance(event, dict) for event in events):
        raise ValueError("RESEARCH_SUBMISSION_EVENT_INVALID")
    proof = any(event.get("tool") == "research_report.submit" and event.get("invocation_id") == packet["identity"]["invocation_id"]
                and event.get("submission") == 1 and event.get("repair_binding_hash") == repair["content_hash"]
                and event.get("event_hash") == legacy_envelope_hash(event, hash_field="event_hash") for event in events)
    if not proof:
        logs = [_event_path(root, log) for log in (root / "invocation").rglob("subagent-events.jsonl")]
        proof = any(isinstance(event, dict) and event.get("identity_binding", {}).get("status") == "BOUND"
                    and event.get("trusted_task_binding", {}).get("invocation_id") == packet["identity"]["invocation_id"]
                    and event.get("submission_binding", {}).get("content_hash") == base["content_hash"]
                    and event.get("repair_request", {}).get("binding_hash") == repair["content_hash"]
                    and event.get("event_hash") == legacy_envelope_hash(event, hash_field="event_hash")
                    for log in logs for line in log.read_text().splitlines() if line.strip()
                    for event in [json.loads(line)])
    if not proof:
        raise ValueError("RESEARCH_SUBMISSION_REVISION_PROOF_MISSING")
    return repair


def _verify_bounded_revision(root: Path, packet: dict, value: dict) -> None:
    if "revision_binding_hash" not in value:
        if value.get("submission_ref", "").startswith("r2."):
            raise ValueError("RESEARCH_SUBMISSION_REVISION_BINDING_INVALID")
        return
    from product.runtime.local_revision import _apply
    base = _stored_submission(root, packet, 1)
    repair = _read_repair(root, packet, base)
    authored = value.get("authored_submission")
    if (value["revision_binding_hash"] != repair["content_hash"] or not isinstance(authored, dict)
            or set(authored) != {"base_draft_ref", "changes"} or authored["base_draft_ref"] != repair["base_draft_ref"]):
        raise ValueError("RESEARCH_SUBMISSION_REVISION_BINDING_INVALID")
    draft = _apply(base["draft"], authored["changes"], repair["allowed_paths"])
    if canonical_hash(draft) != canonical_hash(value["draft"]):
        raise ValueError("RESEARCH_SUBMISSION_REVISION_CONTENT_DRIFT")


def _submit_bounded(root: Path, packet: dict, authored: dict, token: str) -> dict:
    if not isinstance(authored, dict) or IDENTITY_FIELDS & authored.keys():
        raise ValueError("RESEARCH_SUBMISSION_DRAFT_IDENTITY_FORBIDDEN")
    body = json.dumps(authored, ensure_ascii=False, allow_nan=False)
    if token in body:
        raise ValueError("RESEARCH_SUBMISSION_CREDENTIAL_IN_DRAFT")
    if len(body.encode()) > MAX_BYTES:
        raise ValueError("RESEARCH_SUBMISSION_TOO_LARGE")
    _event_path(root, root / "events/mcp/events.jsonl")  # 不向链接指向的目录写入提交事件。
    directory = _directory(root, packet["identity"]["invocation_id"])
    lock_path = directory / ".submit.lock"
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        number = 1 if not (directory / "1.json").exists() else 2
        if (directory / "2.json").exists():
            raise ValueError("RESEARCH_SUBMISSION_LIMIT_EXHAUSTED")
        draft = authored
        revision_binding = None
        if number == 2:
            from product.runtime.local_revision import _apply
            base = _stored_submission(root, packet, 1)
            repair = _read_repair(root, packet, base)
            revision_binding = repair["content_hash"]
            try:
                if (set(authored) != {"base_draft_ref", "changes"} or authored["base_draft_ref"] != repair["base_draft_ref"]):
                    raise ValueError("RESEARCH_SUBMISSION_BASE_REFERENCE_INVALID")
                draft = _apply(base["draft"], authored["changes"], repair["allowed_paths"])
            except ValueError as exc:
                draft = authored
                validation, assembled, selected = {"status": "FAILED", "failure_code": str(exc), "findings": []}, None, []
            else:
                validation, assembled, selected = _preflight_bounded(root, packet, draft)
        else:
            validation, assembled, selected = _preflight_bounded(root, packet, draft)
        value = {"binding": {"version": BOUNDED_REVISION_VERSION, "identity": packet["identity"], "packet_hash": canonical_hash(packet)},
                 "draft": draft, "authored_submission": authored, "validation_result": validation,
                 "submission_ref": f"r{number}.{secrets.token_urlsafe(18)}"}
        if revision_binding is not None:
            value["revision_binding_hash"] = revision_binding
        value["content_hash"] = legacy_envelope_hash(value, hash_field="content_hash")
        path = directory / f"{number}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        repair = None
        if number == 1 and validation["status"] == "FAILED":
            repair = _bounded_repair(value, packet, validation.get("findings", []), validation["failure_code"])
            if repair:
                _save_repair(_repair_path(root, packet), repair)
                repair = json.loads(_repair_path(root, packet).read_text())
        empty_citation = {"pair_count": 0, "pairs": [], "truncated": False}
        empty_source = {"pair_count": 0, "status": "NOT_EVALUATED", "pairs": []}
        citation = _citation_review(assembled, packet, token) if assembled else empty_citation
        source = _source_evidence_review(root, assembled, packet, token) if assembled else empty_source
        monetary = _monetary_review(root, assembled, packet, selected)
        from product.runtime.local_revision import REVISION_FORMAT_GUIDE
        return {"status": "DRAFT_STORED_NOT_VALIDATED" if validation["status"] == "PASSED" else "DRAFT_REJECTED",
                "submission": number, "content_hash": value["content_hash"], "final_message": value["submission_ref"],
                "validation_result": validation, "citation_review": citation, "source_evidence_review": source,
                "monetary_review": monetary,
                **({"repair": {**{k: repair[k] for k in ("repair_contract", "base_draft_ref", "allowed_paths", "validation_error")},
                               "revision_format_guide": copy.deepcopy(REVISION_FORMAT_GUIDE)},
                    "repair_binding_hash": repair["content_hash"]} if repair else {})}


def _monetary_review(root: Path, assembled: dict | None, packet: dict, selected: list) -> dict:
    result: dict[str, Any] = {"status": "NOT_EVALUATED", "findings": []}
    if assembled is None:
        return result
    try:
        selected = selected_calculation_outputs(root, selected)
        claims = assembled.get("claims")
        if not (isinstance(claims, list) and all(
            isinstance(claim, dict) and isinstance(claim.get("research_claim_refs", []), list)
            for claim in claims
        )):
            return result
        from product.runtime.monetary import research_report_monetary_findings
        gate = json.loads((root / "evidence/gate.json").read_text())
        findings = research_report_monetary_findings(
            assembled, task=packet["task"], gate=gate,
            reference_packet=packet, selected_upstream=selected,
        )
        return {"status": "LOCATED" if findings else "NONE_LOCATED",
                "findings": findings[:MAX_MONETARY_REVIEW_FINDINGS], "finding_count": len(findings),
                "truncated": len(findings) > MAX_MONETARY_REVIEW_FINDINGS}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return {**result, "failure_code": str(exc)}  # 非接受证明，Stop 仍运行完整校验。


def submit(root: Path, invocation_id: str, draft: dict[str, Any], *, submission_token: str | None = None) -> dict[str, Any]:
    # 先核验协议/访问凭据，再读研究依赖；旧任务不能因缺依赖掩盖退役原因。
    packet = _packet(root, invocation_id, include_dependencies=False)
    require_write_protocol(packet["task"])
    expected_token = packet.get("submission_access", {}).get("token")
    # Bearer capability for accidental misrouting, NOT MCP caller authentication.
    # Validate before creating a directory or consuming either draft slot.
    if (not isinstance(expected_token, str) or len(expected_token) < 32
            or not isinstance(submission_token, str)
            or not secrets.compare_digest(submission_token.encode(), expected_token.encode())):
        raise ValueError("RESEARCH_SUBMISSION_CREDENTIAL_INVALID")
    packet = _packet(root, invocation_id)
    return _submit_bounded(root, packet, draft, expected_token)


def resolve(root: Path, payload: dict[str, Any], record: dict[str, Any], attempt: int, *,
            for_execution: bool = False) -> dict[str, Any]:
    """按冻结版本只读解析；当前 Stop 必须另外满足执行准入。"""
    trusted = record.get("trusted_task_binding") or {}
    if (record.get("identity_binding") or {}).get("status") != "BOUND":
        return payload  # Original capture reports the binding failure.
    index = json.loads((root / "research/dispatch-index.json").read_text())
    tasks = [t for t in index["tasks"] if t["invocation_id"] == trusted["invocation_id"]]
    if len(tasks) != 1 or tasks[0].get("submission_version") not in READ_VERSIONS:
        return payload
    packet = _packet(root, trusted["invocation_id"])
    if for_execution:
        require_write_protocol(packet["task"])
    version = packet["task"]["submission_version"]
    record["submission_mode"] = version
    if version in SHORT_RECEIPT_VERSIONS:
        receipt_ref = payload.get("last_assistant_message")
        if not isinstance(receipt_ref, str) or re.fullmatch(r"r[12]\.[A-Za-z0-9_-]{24}", receipt_ref) is None:
            raise ValueError("RESEARCH_SUBMISSION_RECEIPT_REQUIRED")
        number = int(receipt_ref[1])
    else:
        try:
            receipt = json.loads(payload["last_assistant_message"])
        except json.JSONDecodeError as exc:
            raise ValueError("RESEARCH_OUTPUT_JSON_INVALID") from exc
        receipt_keys = {"submission", "content_hash"} if version != LEGACY_VERSION else {"submission"}
        if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
            raise ValueError("RESEARCH_SUBMISSION_RECEIPT_REQUIRED")
        number = receipt["submission"]
    if type(number) is not int or number not in (1, 2) or number < attempt:
        raise ValueError("RESEARCH_SUBMISSION_RECEIPT_INVALID")
    path = _directory(root, trusted["invocation_id"], create=False) / f"{number}.json"
    limit = MAX_STORED_BYTES if version == BOUNDED_REVISION_VERSION else MAX_BYTES + 16384
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("RESEARCH_SUBMISSION_PATH_INVALID")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    try:
        verify_legacy_envelope_hash(value, hash_field="content_hash", location=str(path.relative_to(root)))
    except HashContractError as exc:
        raise ValueError(f"RESEARCH_SUBMISSION_BINDING_INVALID:{exc}") from exc
    binding = {"version": version, "identity": packet["identity"], "packet_hash": canonical_hash(packet)}
    if (value.get("binding") != binding or value.get("content_hash") != legacy_envelope_hash(
        value, hash_field="content_hash"
    ) or not isinstance(value.get("draft"), dict) or IDENTITY_FIELDS & value["draft"].keys()):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    if version in SHORT_RECEIPT_VERSIONS:
        if value.get("submission_ref") != receipt_ref:
            raise ValueError("RESEARCH_SUBMISSION_RECEIPT_INVALID")
    elif version != LEGACY_VERSION and receipt["content_hash"] != value["content_hash"]:
        raise ValueError("RESEARCH_SUBMISSION_RECEIPT_INVALID")
    record["submission_binding"] = {"version": version, "submission": number,
                                    "content_hash": value["content_hash"], "path": str(path.relative_to(root)),
                                    **({"submission_ref": receipt_ref} if version in SHORT_RECEIPT_VERSIONS else {})}
    if version == BOUNDED_REVISION_VERSION:
        _verify_submission_event(root, trusted["invocation_id"], number, value["content_hash"])
        if value.get("validation_result", {}).get("status") == "FAILED":
            raise ValueError(value["validation_result"]["failure_code"])
        _verify_bounded_revision(root, packet, value)
    draft = value["draft"]
    if version in ASSEMBLY_VERSIONS:
        draft, selections = _assemble_draft(draft, packet, root=root)
        record["upstream_calculation_selections"] = selections
    # Existing trusted identity envelope and all original validators remain authoritative.
    return {**payload, "last_assistant_message": json.dumps({**draft, **{
        key: trusted[key] for key in IDENTITY_FIELDS
    }}, ensure_ascii=False, allow_nan=False)}


def mark_accepted(root: Path, record: dict[str, Any], report: dict[str, Any]) -> dict[str, Any] | None:
    """Bind the saved final report to the exact submitted draft and its choices."""
    binding = record.get("submission_binding") or {}
    if binding.get("version") in READ_VERSIONS - WRITE_VERSIONS:
        raise ValueError("RESEARCH_SUBMISSION_LEGACY_READ_ONLY")
    if binding.get("version") not in ASSEMBLY_VERSIONS:
        return None
    if binding.get("version") not in WRITE_VERSIONS:
        raise ValueError("RESEARCH_SUBMISSION_LEGACY_READ_ONLY")
    invocation_id = report["invocation_id"]
    packet = _packet(root, invocation_id)
    require_write_protocol(packet["task"])
    if binding["version"] != packet["task"]["submission_version"]:
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    gate = json.loads((root / "evidence/gate.json").read_text(encoding="utf-8"))
    gate_hash = gate.get("bundle_hash")
    if (not isinstance(gate_hash, str)
            or gate_hash != legacy_envelope_hash(gate, hash_field="bundle_hash")
            or packet.get("reference_map", {}).get("binding", {}).get("gate_hash") != canonical_hash(gate)):
        raise ValueError("RESEARCH_SUBMISSION_GATE_BINDING_INVALID")
    directory = _directory(root, invocation_id)
    source = directory / f"{binding['submission']}.json"
    if source.is_symlink() or not source.is_file():
        raise ValueError("RESEARCH_SUBMISSION_PATH_INVALID")
    stored = json.loads(source.read_text(encoding="utf-8"))
    try:
        verify_legacy_envelope_hash(stored, hash_field="content_hash", location=str(source.relative_to(root)))
    except HashContractError as exc:
        raise ValueError(f"RESEARCH_SUBMISSION_BINDING_INVALID:{exc}") from exc
    if (stored.get("content_hash") != binding["content_hash"]
            or stored.get("content_hash") != legacy_envelope_hash(
                stored, hash_field="content_hash"
            )):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    selected = record.get("upstream_calculation_selections", [])
    marker = {
        "version": binding["version"], "invocation_id": invocation_id,
        "report_id": report["report_id"], "report_hash": report["report_hash"],
        "source_gate_hash": gate_hash,
        "submission": binding["submission"],
        "submission_content_hash": binding["content_hash"],
        "upstream_calculation_selections": copy.deepcopy(selected),
    }
    if binding["version"] in SHORT_RECEIPT_VERSIONS:
        if stored.get("submission_ref") != binding.get("submission_ref"):
            raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
        marker["submission_ref"] = binding["submission_ref"]
    if binding["version"] in FORMAL_VERSIONS:
        marker["relation_reference_binding"] = _v4_reference_binding(packet)
        _verify_v4_saved_statements(stored["draft"], report, marker["relation_reference_binding"])
    marker["marker_hash"] = canonical_hash(marker)
    path = directory / "accepted.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(marker, stream, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(path.relative_to(root)), "marker_hash": marker["marker_hash"]}


def selected_calculation_outputs(root: Path, selections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read the exact original tool output; never derive a number from report prose."""
    results = []
    for choice in selections:
        ledger = (root / choice["calculation"]["artifact_ref"]).resolve()
        if not ledger.is_relative_to(root.resolve()) or not ledger.is_file():
            raise ValueError("RESEARCH_SUBMISSION_CALCULATION_ARTIFACT_INVALID")
        receipts = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        matches = [receipt for receipt in receipts
                   if receipt.get("calculation_id") == choice["calculation_id"]
                   and receipt.get("receipt_hash") == choice["calculation"]["receipt_hash"]
                   and receipt.get("receipt_hash") == legacy_envelope_hash(
                       receipt, hash_field="receipt_hash"
                   )]
        if len(matches) != 1 or not isinstance(matches[0].get("output"), dict):
            raise ValueError("RESEARCH_SUBMISSION_CALCULATION_RECORD_MISSING")
        results.append({**choice, "verified_output": copy.deepcopy(matches[0]["output"])})
    return results


def _selected_calculations_from_copied_package(
    root: Path, report: dict[str, Any], directory: Path,
) -> list[dict[str, Any]]:
    """Recheck copied lineage without copying private dispatch credentials."""
    marker_path = directory / "accepted.json"
    if marker_path.is_symlink() or not marker_path.is_file():
        bundle_path = root / "research/holding-research-bundle.json"
        if bundle_path.is_file():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            if str(marker_path.relative_to(root)) in bundle.get("artifact_refs", []):
                raise ValueError("RESEARCH_SUBMISSION_COPIED_RECORD_MISSING")
        return []  # Historical reports have no v3 selection record.
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    gate = json.loads((root / "evidence/gate.json").read_text(encoding="utf-8"))
    cutoff = report.get("bindings", {}).get("decision_cutoff")
    if (gate.get("bundle_hash") != legacy_envelope_hash(
            gate, hash_field="bundle_hash"
        ) or not isinstance(cutoff, str) or gate.get("decision_cutoff") != cutoff
            or gate.get("run_id") != report.get("run_id")):
        raise ValueError("RESEARCH_SUBMISSION_COPIED_GATE_INVALID")
    bundle_path = root / "research/holding-research-bundle.json"
    if bundle_path.is_file():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        if (bundle.get("decision_cutoff") != cutoff
                or bundle.get("run_id") != report.get("run_id")):
            raise ValueError("RESEARCH_SUBMISSION_COPIED_GATE_INVALID")
    source_gate_hashes = {
        item.get("gate_hash") for item in gate.get("source_gates", [])
        if item.get("role") == "BASE_MULTIDIMENSIONAL"
    }
    if (marker.get("marker_hash") != legacy_envelope_hash(marker, hash_field="marker_hash") or marker.get("version") not in ASSEMBLY_VERSIONS
            or marker.get("report_id") != report.get("report_id")
            or marker.get("report_hash") != report.get("report_hash")
            or marker.get("invocation_id") != report.get("invocation_id")
            or marker.get("source_gate_hash") not in source_gate_hashes):
        raise ValueError("RESEARCH_SUBMISSION_COPIED_RECORD_INVALID")
    number = marker.get("submission")
    if type(number) is not int or number not in (1, 2):
        raise ValueError("RESEARCH_SUBMISSION_COPIED_RECORD_INVALID")
    source_path = directory / f"{number}.json"
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError("RESEARCH_SUBMISSION_COPIED_RECORD_MISSING")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if (source.get("content_hash") != marker.get("submission_content_hash")
            or source.get("content_hash") != legacy_envelope_hash(
                source, hash_field="content_hash"
            ) or source.get("binding", {}).get("version") != marker.get("version")):
        raise ValueError("RESEARCH_SUBMISSION_COPIED_RECORD_INVALID")
    if marker["version"] in SHORT_RECEIPT_VERSIONS and (
        marker.get("submission_ref") != source.get("submission_ref")
        or not isinstance(marker.get("submission_ref"), str)
        or re.fullmatch(r"r[12]\.[A-Za-z0-9_-]{24}", marker["submission_ref"]) is None
        or int(marker["submission_ref"][1]) != number
    ):
        raise ValueError("RESEARCH_SUBMISSION_COPIED_RECORD_INVALID")
    if marker["version"] in FORMAL_VERSIONS:
        _verify_v4_saved_statements(source["draft"], report, marker.get("relation_reference_binding"))
    authored = source.get("draft", {}).get("upstream_calculation_selections", [])
    selections = marker.get("upstream_calculation_selections", [])
    keys = ("claim_id", "report_id", "source_claim_id", "calculation_id")
    if (not isinstance(authored, list) or not isinstance(selections, list)
            or [{key: item.get(key) for key in keys} for item in selections] != authored):
        raise ValueError("RESEARCH_SUBMISSION_COPIED_SELECTION_MISMATCH")
    local_claims = {item["claim_id"]: item for item in report.get("claims", [])}
    events_path = root / "events/mcp/events.jsonl"
    if selections and (events_path.is_symlink() or not events_path.is_file()):
        raise ValueError("RESEARCH_SUBMISSION_COPIED_EVENT_MISSING")
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()] if selections else []
    for choice in selections:
        claim = local_claims.get(choice.get("claim_id"))
        source_ref = scoped_claim_reference(choice, choice["source_claim_id"])
        refs = claim.get("research_claim_refs", []) if isinstance(claim, dict) else []
        binding = marker.get("relation_reference_binding", {})
        accepts_bare = (marker.get("version") == VERSION
                        or choice.get("source_claim_id") in binding.get("external_claim_ids", []))
        if not isinstance(claim, dict) or (source_ref not in refs and not (
            accepts_bare and choice.get("source_claim_id") in refs
        )):
            raise ValueError("RESEARCH_SUBMISSION_COPIED_SELECTION_MISMATCH")
        relative = choice.get("report_artifact_ref")
        if not isinstance(relative, str):
            raise ValueError("RESEARCH_SUBMISSION_COPIED_SELECTION_MISMATCH")
        upstream_path = (root / relative).resolve()
        if not upstream_path.is_relative_to(root.resolve()) or not upstream_path.is_file():
            raise ValueError("RESEARCH_SUBMISSION_COPIED_DEPENDENCY_MISSING")
        upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
        if (upstream.get("report_id") != choice.get("report_id")
                or upstream.get("report_hash") != choice.get("report_hash")
                or upstream.get("report_hash") != legacy_envelope_hash(upstream, hash_field="report_hash") or upstream.get("run_id") != report.get("run_id")
                or upstream.get("bindings", {}).get("decision_cutoff") != report.get("bindings", {}).get("decision_cutoff")):
            raise ValueError("RESEARCH_SUBMISSION_COPIED_DEPENDENCY_INVALID")
        source_claims = [item for item in upstream.get("claims", [])
                         if item.get("claim_id") == choice.get("source_claim_id")]
        source_calculations = [item for item in upstream.get("calculations", [])
                               if item.get("calculation_id") == choice.get("calculation_id")]
        calculation = choice.get("calculation", {})
        if (len(source_claims) != 1 or len(source_calculations) != 1
                or choice.get("calculation_id") not in source_claims[0].get("calculation_refs", [])
                or any(calculation.get(key) != source_calculations[0].get(key)
                       for key in ("calculation_id", "method", "value", "unit",
                                   "input_evidence_refs", "artifact_ref"))):
            raise ValueError("RESEARCH_SUBMISSION_COPIED_CALCULATION_INVALID")
        matching_events = [event for event in events
                           if event.get("event_hash") == calculation.get("tool_event_hash")
                           and event.get("event_hash") == legacy_envelope_hash(
                               event, hash_field="event_hash"
                           )]
        if len(matching_events) != 1:
            raise ValueError("RESEARCH_SUBMISSION_COPIED_EVENT_INVALID")
    outputs = selected_calculation_outputs(root, selections)
    for choice, output in zip(selections, outputs):
        event = next(item for item in events
                     if item.get("event_hash") == choice["calculation"]["tool_event_hash"])
        ledger = root / choice["calculation"]["artifact_ref"]
        receipts = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
        receipt = next(item for item in receipts
                       if item.get("receipt_hash") == choice["calculation"]["receipt_hash"])
        inputs = {
            key: receipt[key] for key in (
                "run_id", "agent", "invocation_id", "calculation_id", "operation", "evidence_ids"
            )
        }
        if output["verified_output"].get("target_scale") is not None:
            inputs["target_scale"] = output["verified_output"]["target_scale"]
        if (event.get("tool") != "fixture_math.calculate"
                or event.get("calculation_id") != choice["calculation_id"]
                or any(event.get(key) != receipt.get(key) for key in (
                    "run_id", "agent", "invocation_id", "operation", "evidence_ids"
                ))
                or event.get("input_hash") != canonical_hash(inputs)
                or event.get("output_hash") != canonical_hash(output["verified_output"])):
            raise ValueError("RESEARCH_SUBMISSION_COPIED_EVENT_INVALID")
    return outputs


def selected_calculations_for_report(
    root: Path, report: dict[str, Any], *, for_execution: bool = True,
) -> list[dict[str, Any]]:
    """Revalidate the saved choice and original receipts for rendering/downstream use."""
    if report.get("report_hash") != legacy_envelope_hash(report, hash_field="report_hash"):
        raise ValueError("RESEARCH_SUBMISSION_REPORT_HASH_INVALID")
    directory = _directory(root, report["invocation_id"], create=False)
    if not (root / "research/dispatch-index.json").is_file():
        return _selected_calculations_from_copied_package(root, report, directory)
    packet = load_reference_packet(root, report["invocation_id"], for_execution=for_execution)
    version = packet["task"].get("submission_version")
    if version not in ASSEMBLY_VERSIONS:
        return []
    path = directory / "accepted.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("RESEARCH_SUBMISSION_ACCEPTED_RECORD_MISSING")
    marker = json.loads(path.read_text(encoding="utf-8"))
    if (marker.get("marker_hash") != legacy_envelope_hash(marker, hash_field="marker_hash") or marker.get("version") != version
            or marker.get("report_id") != report["report_id"]
            or marker.get("report_hash") != report["report_hash"]
            or marker.get("invocation_id") != report["invocation_id"]
            or marker.get("source_gate_hash") != json.loads(
                (root / "evidence/gate.json").read_text(encoding="utf-8")
            ).get("bundle_hash")):
        raise ValueError("RESEARCH_SUBMISSION_ACCEPTED_RECORD_INVALID")
    number = marker.get("submission")
    if type(number) is not int or number not in (1, 2):
        raise ValueError("RESEARCH_SUBMISSION_ACCEPTED_RECORD_INVALID")
    source = directory / f"{number}.json"
    if source.is_symlink() or not source.is_file():
        raise ValueError("RESEARCH_SUBMISSION_PATH_INVALID")
    stored = json.loads(source.read_text(encoding="utf-8"))
    if (stored.get("content_hash") != marker.get("submission_content_hash")
            or stored.get("content_hash") != legacy_envelope_hash(
                stored, hash_field="content_hash"
            ) or stored.get("binding") != {
                "version": version, "identity": packet["identity"],
                "packet_hash": canonical_hash(packet),
            }):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    assembled, selections = _assemble_draft(stored["draft"], packet, root=root)
    if version in SHORT_RECEIPT_VERSIONS and (
        marker.get("submission_ref") != stored.get("submission_ref")
        or not isinstance(marker.get("submission_ref"), str)
        or re.fullmatch(r"r[12]\.[A-Za-z0-9_-]{24}", marker["submission_ref"]) is None
        or int(marker["submission_ref"][1]) != number
    ):
        raise ValueError("RESEARCH_SUBMISSION_ACCEPTED_RECORD_INVALID")
    if version in FORMAL_VERSIONS:
        if marker.get("relation_reference_binding") != _v4_reference_binding(packet):
            raise ValueError("RESEARCH_SUBMISSION_RELATION_BINDING_INVALID")
        _verify_v4_saved_statements(stored["draft"], report, marker["relation_reference_binding"])
    if selections != marker.get("upstream_calculation_selections"):
        raise ValueError("RESEARCH_SUBMISSION_ACCEPTED_RECORD_INVALID")
    return selected_calculation_outputs(root, selections)
