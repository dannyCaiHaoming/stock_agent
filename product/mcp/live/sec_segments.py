"""有界 SEC XBRL/iXBRL 分部维度解析；不把合计值推断为分部。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import re
from typing import Any, Mapping
from xml.etree import ElementTree as ET

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


PARSER_VERSION = "sec-segment-xbrl/1.0.0"
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attribute(element: ET.Element, name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local(key).casefold() == name.casefold():
            return value
    return None


def _normalize_cik(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not digits:
        raise ValueError("SEC_SEGMENT_CIK_INVALID")
    return digits.zfill(10)


def _contexts(root: ET.Element, *, cik: str) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    for element in root.iter():
        if _local(element.tag).casefold() != "context":
            continue
        identifier = next((node for node in element.iter() if _local(node.tag).casefold() == "identifier"), None)
        if identifier is None or _normalize_cik(identifier.text or "") != cik:
            raise ValueError("SEC_SEGMENT_CONTEXT_CIK_MISMATCH")
        context_id = element.attrib.get("id")
        if not context_id or context_id in contexts:
            raise ValueError("SEC_SEGMENT_CONTEXT_ID_INVALID")
        members = []
        for node in element.iter():
            local = _local(node.tag).casefold()
            if local == "explicitmember":
                dimension = _attribute(node, "dimension")
                member = (node.text or "").strip()
                if not dimension or not member:
                    raise ValueError("SEC_SEGMENT_DIMENSION_INVALID")
                members.append({"axis": dimension, "member": member, "member_type": "explicit"})
            elif local == "typedmember":
                dimension = _attribute(node, "dimension")
                if not dimension:
                    raise ValueError("SEC_SEGMENT_DIMENSION_INVALID")
                children = list(node)
                typed = ET.tostring(children[0], encoding="unicode") if children else ""
                if not typed:
                    raise ValueError("SEC_SEGMENT_TYPED_MEMBER_INVALID")
                members.append({"axis": dimension, "member": typed, "member_type": "typed"})
        period = next((node for node in element.iter() if _local(node.tag).casefold() == "period"), None)
        if period is None:
            raise ValueError("SEC_SEGMENT_PERIOD_MISSING")
        dates = {_local(node.tag).casefold(): (node.text or "").strip() for node in period}
        if "instant" in dates:
            start, end, context_type = None, dates["instant"], "instant"
        elif "startdate" in dates and "enddate" in dates:
            start, end, context_type = dates["startdate"], dates["enddate"], "duration"
            if date.fromisoformat(start) > date.fromisoformat(end):
                raise ValueError("SEC_SEGMENT_PERIOD_INVALID")
        else:
            raise ValueError("SEC_SEGMENT_PERIOD_INVALID")
        contexts[context_id] = {
            "context_id": context_id, "context_type": context_type,
            "period_start": start, "period_end": end,
            "axis_members": sorted(members, key=lambda item: (item["axis"], item["member"])),
        }
    return contexts


def _units(root: ET.Element) -> dict[str, str]:
    units = {}
    for element in root.iter():
        if _local(element.tag).casefold() != "unit":
            continue
        unit_id = element.attrib.get("id")
        measures = [(node.text or "").strip() for node in element.iter() if _local(node.tag).casefold() == "measure"]
        if unit_id and measures:
            units[unit_id] = "*".join(measures)
    return units


def parse_segment_facts(
    raw: bytes, document: Mapping[str, Any], *, max_facts: int = 2000,
) -> dict[str, Any]:
    required = {
        "raw_content_hash", "source_id", "source_locator", "cik", "accession",
        "form", "published_at", "retrieved_at",
    }
    if any(not document.get(key) for key in required):
        raise ValueError("SEC_SEGMENT_DOCUMENT_PROVENANCE_MISSING")
    if len(raw) > MAX_DOCUMENT_BYTES or hashlib.sha256(raw).hexdigest() != document["raw_content_hash"]:
        raise ValueError("SEC_SEGMENT_DOCUMENT_HASH_OR_SIZE_INVALID")
    if not isinstance(max_facts, int) or not 0 < max_facts <= 5000:
        raise ValueError("SEC_SEGMENT_FACT_BUDGET_INVALID")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("SEC_SEGMENT_XML_INVALID") from exc
    cik = _normalize_cik(str(document["cik"]))
    contexts = _contexts(root, cik=cik)
    units = _units(root)
    retrieved = iso_utc(document["retrieved_at"])
    published = iso_utc(document["published_at"])
    if parse_timestamp(published) > parse_timestamp(retrieved):
        raise ValueError("SEC_SEGMENT_PUBLICATION_AFTER_RETRIEVAL")
    evidence, candidates, invalid_numeric, duplicate_numeric = [], 0, 0, 0
    seen_evidence_ids: set[str] = set()
    for element in root.iter():
        context_ref = _attribute(element, "contextref")
        if not context_ref or context_ref not in contexts:
            continue
        context = contexts[context_ref]
        if not context["axis_members"]:
            continue
        local = _local(element.tag)
        if local.casefold() in {"context", "explicitmember", "typedmember"}:
            continue
        unit_ref = _attribute(element, "unitref")
        if not unit_ref or (_attribute(element, "nil") or "").casefold() in {"true", "1"}:
            continue
        candidates += 1
        if len(evidence) >= max_facts:
            continue
        name = _attribute(element, "name")
        concept = name or local
        raw_value = "".join(element.itertext()).strip().replace(",", "")
        if not raw_value:
            continue
        sign = _attribute(element, "sign")
        try:
            number = Decimal(raw_value)
            scale = int(_attribute(element, "scale") or "0")
            number *= Decimal(10) ** scale
            if sign == "-":
                number = -number
        except (InvalidOperation, ValueError):
            invalid_numeric += 1
            continue
        member_text = " ".join(item["member"] for item in context["axis_members"]).casefold()
        segment_role = "ELIMINATION_OR_CONSOLIDATION" if any(
            token in member_text for token in ("elimination", "consolidat", "reconcil")
        ) else "REPORTED_MEMBER"
        fact = {
            "security_id": document.get("security_id"),
            "cik": cik,
            "accession": document["accession"],
            "form": document["form"],
            "concept": concept,
            "value": format(number, "f"),
            "unit": units.get(unit_ref),
            "decimals": _attribute(element, "decimals"),
            **context,
            "segment_role": segment_role,
            "as_of": f"{context['period_end']}T00:00:00Z",
            "published_at": published,
            "retrieved_at": retrieved,
            "source_id": document["source_id"],
            "source_locator": document["source_locator"],
            "raw_content_hash": document["raw_content_hash"],
            "parser_version": PARSER_VERSION,
            "aggregation_status": "REPORTED_CONTEXT_ONLY_NOT_SUMMED",
        }
        fact["evidence_id"] = "ev-sec-segment-" + content_hash(fact)
        if fact["evidence_id"] in seen_evidence_ids:
            duplicate_numeric += 1
            continue
        seen_evidence_ids.add(fact["evidence_id"])
        evidence.append(fact)
    gaps = []
    if not evidence:
        gaps.append({"reason": "SEC_SEGMENT_DIMENSION_FACTS_NOT_FOUND"})
    if candidates > max_facts:
        gaps.append({
            "reason": "SEC_SEGMENT_FACT_BUDGET_EXHAUSTED",
            "candidate_count": candidates, "emitted_count": len(evidence),
        })
    if invalid_numeric:
        gaps.append({
            "reason": "SEC_SEGMENT_NUMERIC_FACT_INVALID",
            "candidate_count": candidates, "invalid_count": invalid_numeric,
        })
    if duplicate_numeric:
        gaps.append({
            "reason": "SEC_SEGMENT_DUPLICATE_FACT_DEDUPLICATED",
            "candidate_count": candidates, "duplicate_count": duplicate_numeric,
        })
    return {
        "parser_version": PARSER_VERSION,
        "coverage": "DIMENSIONED_REPORTED_FACTS_ONLY",
        "evidence": evidence,
        "gaps": gaps,
        "raw_content_hash": document["raw_content_hash"],
    }
