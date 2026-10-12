"""无业务判断的金额数量级换算。"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from product.runtime.hashing import legacy_envelope_hash


MONETARY_SCALE_FACTORS = {
    "one": Decimal("1"),
    "thousand": Decimal("1000"),
    "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
    "万": Decimal("10000"),
    "亿": Decimal("100000000"),
}


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid decimal input: {name}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite decimal input: {name}")
    return result


def scale_factor(scale: str) -> Decimal:
    if scale not in MONETARY_SCALE_FACTORS:
        raise ValueError(
            "unsupported monetary scale; allowed=" + ",".join(MONETARY_SCALE_FACTORS)
        )
    return MONETARY_SCALE_FACTORS[scale]


def convert_monetary_value(
    *, value: object, source_scale: str, target_scale: str
) -> str:
    amount = _decimal(value, "value")
    converted = amount * scale_factor(source_scale) / scale_factor(target_scale)
    return format(converted.normalize(), "f")


def require_monetary_equivalence(
    *, source_value: object, source_scale: str,
    reported_value: object, reported_scale: str,
) -> None:
    source = _decimal(source_value, "source_value") * scale_factor(source_scale)
    reported = _decimal(reported_value, "reported_value") * scale_factor(reported_scale)
    if source != reported:
        raise ValueError("reported monetary amount does not match source magnitude")


_CHINESE_USD_HUNDRED_MILLION = re.compile(
    r"(?<![\d.,])(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*亿美元"
)
_DOLLAR_PREFIX_HUNDRED_MILLION = re.compile(
    r"\$(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*亿"
)
_OTHER_CURRENCY_BEFORE_DOLLAR = re.compile(
    r"(?<![A-Za-z])(?:HKD|HK|CAD|CA|C|AUD|AU|SGD|SG|NZD|NZ|TWD|NT|RMB|JPY|EUR|GBP|CHF|"
    r"港币|港元|加元|澳元|新元|欧元|英镑|人民币|[€£¥])\s*[:：]?\s*$",
    re.IGNORECASE,
)
_EXPLICIT_DOLLAR_CODE_PREFIX = re.compile(r"(?<![A-Za-z])([A-Z]{1,3})\s*[:：]?\s*$")
_ENGLISH_USD_BILLION = re.compile(
    r"(?<![\d.,])(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*billion\s*USD\b"
    r"|\bUSD\s*(?P<prefixed>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*billion\b"
    r"|\$(?P<symbol_amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*billion\b",
    re.IGNORECASE,
)


def _explicit_amounts(pattern: re.Pattern[str], text: str) -> list[Decimal]:
    result = []
    for match in pattern.finditer(text):
        symbol = match.groupdict().get("symbol_amount")
        if symbol is not None and _other_dollar_currency_prefix(text, match.start()):
            continue
        raw = match.group("amount") or match.groupdict().get("prefixed") or symbol
        try:
            amount = Decimal(raw.replace(",", ""))
        except (AttributeError, InvalidOperation):
            continue
        if amount.is_finite():
            result.append(amount)
    return result


def _other_dollar_currency_prefix(text: str, start: int) -> bool:
    preceding = text[max(0, start - 12):start]
    immediate = preceding[-1:] if preceding else ""
    before_separator = preceding.rstrip(" \t:：")[-1:]
    explicit_code = _EXPLICIT_DOLLAR_CODE_PREFIX.search(preceding)
    if explicit_code:
        return explicit_code.group(1) not in {"USD", "US"}
    return bool(
        (immediate and immediate.isascii() and immediate.isalpha())
        or (before_separator and unicodedata.category(before_separator) == "Sc")
        or _OTHER_CURRENCY_BEFORE_DOLLAR.search(preceding)
    )


def _unprefixed_dollar_yi_amounts(text: str) -> list[Decimal]:
    result = []
    for match in _DOLLAR_PREFIX_HUNDRED_MILLION.finditer(text):
        if _other_dollar_currency_prefix(text, match.start()):
            continue
        try:
            amount = Decimal(match.group("amount").replace(",", ""))
        except InvalidOperation:
            continue
        if amount.is_finite():
            result.append(amount)
    return result


def research_report_monetary_findings(
    draft: Mapping[str, Any], *, task: Mapping[str, Any], gate: Mapping[str, Any],
    reference_packet: Mapping[str, Any], selected_upstream: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Locate an unreceipted USD scale rewrite with one identifiable cited source."""
    from product.runtime.research_submission import ASSEMBLY_VERSIONS

    if task.get("capability") != "RESEARCH_REPORT" or task.get("submission_version") not in ASSEMBLY_VERSIONS:
        return []
    if gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash"):
        raise ValueError("DIMENSION_REPORT_MONETARY_GATE_INVALID")
    allowed = set(task.get("allowed_evidence_ids", []))
    evidence = {item["evidence_id"]: item for item in gate.get("allowed_evidence", [])
                if item.get("evidence_id") in allowed}
    mapping = reference_packet.get("reference_map", {})
    evidence_map = mapping.get("evidence", {})
    claim_map = mapping.get("claims", {})
    dependencies = {
        (report["report_id"], claim["claim_id"]): claim.get("statement", "")
        for report in reference_packet.get("dependency_reports", [])
        for claim in report.get("claims", [])
        if isinstance(claim, Mapping)
    }
    findings = []
    claims = draft.get("claims", [])
    local_claim_ids = {
        claim.get("claim_id") for claim in claims if isinstance(claim, Mapping)
        and isinstance(claim.get("claim_id"), str)
    } if isinstance(claims, list) else set()
    for index, claim in enumerate(claims if isinstance(claims, list) else []):
        if not isinstance(claim, Mapping) or not isinstance(claim.get("statement"), str):
            continue
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs):
            continue
        cited_ids = [evidence_map.get(ref, ref) for ref in refs]
        if len(cited_ids) != len(set(cited_ids)) or any(source_id not in evidence for source_id in cited_ids):
            continue
        reported = _explicit_amounts(_ENGLISH_USD_BILLION, claim["statement"])
        if not reported:
            continue
        cited_contents = []
        for source_id in cited_ids:
            value = evidence[source_id].get("value")
            cited_contents.append((source_id, value.get("content_tier"), value.get("content"))
                                  if isinstance(value, Mapping) else (source_id, None, None))
        upstream_english = set()
        ambiguous_upstream = False
        upstream_refs = claim.get("research_claim_refs", [])
        if not isinstance(upstream_refs, list):
            continue  # Original schema validation handles malformed draft fields.
        for ref in upstream_refs:
            if not isinstance(ref, str):
                continue
            if ref in local_claim_ids:
                continue  # Local claims take precedence over same-named dependencies.
            mapped = claim_map.get(ref)
            if isinstance(mapped, Mapping):
                upstream_english.update(_explicit_amounts(
                    _ENGLISH_USD_BILLION,
                    str(dependencies.get((mapped.get("report_id"), mapped.get("claim_id")), "")),
                ))
            else:
                matches = [statement for (_, claim_id), statement in dependencies.items() if claim_id == ref]
                if len(matches) == 1:
                    upstream_english.update(_explicit_amounts(_ENGLISH_USD_BILLION, str(matches[0])))
                elif len(matches) > 1:
                    ambiguous_upstream = True
        if ambiguous_upstream:
            continue
        for amount_index, target in enumerate(reported):
            if target in upstream_english:
                continue
            matching_sources = []
            original_english = False
            for source_id, tier, content in cited_contents:
                if not isinstance(content, str):
                    continue
                if target in _explicit_amounts(_ENGLISH_USD_BILLION, content):
                    original_english = True
                    break
                originals = {amount: "亿美元" for amount in _explicit_amounts(
                    _CHINESE_USD_HUNDRED_MILLION, content,
                )}
                for amount in _unprefixed_dollar_yi_amounts(content):
                    originals.setdefault(amount, "$亿")
                for original, source_unit in originals.items():
                    try:
                        require_monetary_equivalence(
                            source_value=original, source_scale="亿",
                            reported_value=target, reported_scale="billion",
                        )
                    except ValueError:
                        continue
                    matching_sources.append((source_id, tier, original, source_unit))
            # Multiple matching Evidence are ambiguous, even when only one is licensed.
            # Repeated identical amounts inside one Evidence do not create a new source.
            if original_english or len(matching_sources) != 1:
                continue
            source_id, tier, original, source_unit = matching_sources[0]
            if tier != "LICENSED_API_CONTENT":
                continue
            short_ids = [short for short, full in evidence_map.items() if full == source_id]
            if len(short_ids) != 1:
                continue
            verified = False
            for selection in selected_upstream:
                calculation = selection.get("calculation", {})
                output = selection.get("verified_output", {})
                if (selection.get("claim_id") != claim.get("claim_id")
                        or calculation.get("input_evidence_refs") != [source_id]
                        or output.get("operation") != "monetary_scale"
                        or output.get("evidence_ids") != [source_id]):
                    continue
                for conversion in output.get("conversions", []):
                    if (conversion.get("source_scale") != "亿"
                            or conversion.get("target_scale") != "billion"):
                        continue
                    try:
                        source_amount = Decimal(str(conversion.get("source_value")).replace(",", ""))
                        converted = Decimal(str(conversion.get("converted_value")).replace(",", ""))
                    except InvalidOperation:
                        continue
                    if source_amount.is_finite() and converted.is_finite() and source_amount == original and converted == target:
                        verified = True
                        break
                if verified:
                    break
            if not verified:
                findings.append({
                    "code": "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                    "path": f"claims[{index}].statement", "identifier": short_ids[0],
                    "amount_index": amount_index,
                    "source_unit": source_unit, "reported_unit": "billion USD",
                    "source_value": str(original) if len(str(original)) <= 64 else None,
                    "reported_value": str(target) if len(str(target)) <= 64 else None,
                    "amount_index_basis": "FINAL_ASSEMBLED_STATEMENT",
                })
    return findings


def monetary_repetition_context(
    draft: Mapping[str, Any], findings: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Open exact repeated gap descriptions for author review, not factual validation."""
    located_amounts = set()
    claims = draft.get("claims", [])
    if not isinstance(claims, list):
        return []
    for finding in findings:
        if finding.get("code") != "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED":
            continue
        match = re.fullmatch(r"claims\[(\d+)\]\.statement", str(finding.get("path", "")))
        offset = finding.get("amount_index")
        if not match or type(offset) is not int or offset < 0 or int(match[1]) >= len(claims):
            continue
        claim = claims[int(match[1])]
        if not isinstance(claim, Mapping):
            continue
        statement = claim.get("statement")
        if statement is None and isinstance(claim.get("core_statement"), str):
            clauses = claim.get("research_relation_clauses", [])
            if not isinstance(clauses, list) or any(
                not isinstance(c, Mapping) or not isinstance(c.get("relation_statement"), str) for c in clauses
            ):
                continue
            statement = " ".join([claim["core_statement"], *(c["relation_statement"] for c in clauses)])
        if not isinstance(statement, str):
            continue
        amounts = _explicit_amounts(_ENGLISH_USD_BILLION, statement)
        if offset < len(amounts):
            located_amounts.add(amounts[offset])
    gaps = draft.get("data_gaps", [])
    if not located_amounts or not isinstance(gaps, list):
        return []
    context = []
    for index, gap in enumerate(gaps):
        if not isinstance(gap, Mapping) or not isinstance(gap.get("description"), str):
            continue
        if located_amounts.intersection(_explicit_amounts(_ENGLISH_USD_BILLION, gap["description"])):
            context.append({"path": f"data_gaps[{index}].description",
                            "status": "REPEATED_EXPLICIT_AMOUNT_AUTHOR_RECHECK"})
        if len(context) >= 32:
            break
    return context
