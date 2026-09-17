"""SEC Form 13F 信息表解析与两期封装；覆盖仅限明确管理人集合。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from product.mcp.live.research_supplement import build_supplement_fact
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


PARSER_VERSION = "sec-13f-information-table/1.1.0"
MAX_BYTES = 16 * 1024 * 1024


class _FilingIndexRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.current: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "tr":
            self.current = {"text": [], "hrefs": []}
        elif tag.casefold() == "a" and self.current is not None:
            href = dict(attrs).get("href")
            if href:
                self.current["hrefs"].append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "tr" and self.current is not None:
            self.rows.append(self.current)
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.current is not None and data.strip():
            self.current["text"].append(data.strip())


def select_13f_information_tables(
    raw: bytes, *, filing: Mapping[str, Any], index_record: Mapping[str, Any], limit: int = 10,
) -> dict[str, Any]:
    if filing.get("form") not in {"13F-HR", "13F-HR/A"}:
        raise ValueError("SEC_13F_FORM_INVALID")
    if not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError("SEC_13F_ATTACHMENT_LIMIT_INVALID")
    if not raw or len(raw) > MAX_BYTES \
            or hashlib.sha256(raw).hexdigest() != index_record.get("raw_content_hash"):
        raise ValueError("SEC_13F_INDEX_HASH_OR_SIZE_INVALID")
    cik = re.sub(r"\D", "", str(filing.get("cik", filing.get("manager_cik", ""))))
    accession = str(filing.get("accession", ""))
    if not cik or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
        raise ValueError("SEC_13F_FILING_IDENTITY_INVALID")
    prefix = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
    parser = _FilingIndexRows()
    try:
        parser.feed(raw.decode("utf-8", "strict"))
        parser.close()
    except (UnicodeError, ValueError) as exc:
        raise ValueError("SEC_13F_INDEX_INVALID") from exc
    candidates = []
    for row in parser.rows:
        description = " ".join(row["text"])
        if "information table" not in description.casefold():
            continue
        for href in row["hrefs"]:
            parsed = urlsplit(href)
            if parsed.query or parsed.fragment or parsed.username or parsed.password:
                raise ValueError("SEC_13F_ATTACHMENT_URL_INVALID")
            if parsed.scheme or parsed.netloc:
                url = href
            elif href.startswith("/"):
                url = "https://www.sec.gov" + href
            else:
                url = prefix + href
            if not url.startswith(prefix):
                raise ValueError("SEC_13F_ATTACHMENT_BINDING_MISMATCH")
            relative = url[len(prefix):]
            submission_url = url
            if "/" in relative:
                display_directory, filename = relative.split("/", 1)
                if not re.fullmatch(r"xsl[A-Za-z0-9_-]+", display_directory):
                    raise ValueError("SEC_13F_ATTACHMENT_URL_INVALID")
                relative = filename
                url = prefix + filename
            if "/" in relative or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*\.xml", relative, re.I):
                raise ValueError("SEC_13F_ATTACHMENT_URL_INVALID")
            candidates.append({
                "document_url": url, "filename": relative,
                "submission_document_url": submission_url,
                "description": description, "row_index": len(candidates),
            })
    unique = []
    seen = set()
    for item in candidates:
        if item["document_url"] not in seen:
            unique.append(item)
            seen.add(item["document_url"])
    return {
        "selected": unique[:limit],
        "omitted": unique[limit:],
        "gaps": ([] if unique else [{"reason": "SEC_13F_INFORMATION_TABLE_NOT_FOUND"}]),
        "coverage": "FILING_INDEX_ROWS_MATCHING_INFORMATION_TABLE",
        "index_raw_content_hash": index_record["raw_content_hash"],
    }


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, name: str) -> str | None:
    found = next((item for item in node.iter() if _local(item.tag).casefold() == name.casefold()), None)
    return (found.text or "").strip() if found is not None and (found.text or "").strip() else None


def _decimal(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"SEC_13F_VALUE_INVALID:{field}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"SEC_13F_VALUE_INVALID:{field}")
    return format(number, "f")


def parse_13f_information_table(
    raw: bytes, *, filing: Mapping[str, Any], cusip_map: Mapping[str, str],
    retrieved_at: str, part_index: int = 1, part_count: int = 1,
) -> dict[str, Any]:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("SEC_13F_DOCUMENT_SIZE_INVALID")
    if filing.get("form") not in {"13F-HR", "13F-HR/A"}:
        raise ValueError("SEC_13F_FORM_INVALID")
    if not isinstance(part_index, int) or not isinstance(part_count, int) or not 1 <= part_index <= part_count <= 100:
        raise ValueError("SEC_13F_PART_INVALID")
    published = iso_utc(filing["published_at"])
    retrieved = iso_utc(retrieved_at)
    if parse_timestamp(published) > parse_timestamp(retrieved):
        raise ValueError("SEC_13F_PUBLICATION_AFTER_RETRIEVAL")
    report_period = str(filing["report_period"])
    as_of = f"{report_period}T00:00:00Z"
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("SEC_13F_XML_INVALID") from exc
    raw_hash = hashlib.sha256(raw).hexdigest()
    evidence, gaps = [], []
    for index, row in enumerate(item for item in root.iter() if _local(item.tag).casefold() == "infotable"):
        cusip = (_child_text(row, "cusip") or "").upper().replace(" ", "")
        if not re.fullmatch(r"[0-9A-Z]{9}", cusip):
            raise ValueError("SEC_13F_CUSIP_INVALID")
        security_id = cusip_map.get(cusip)
        if security_id is None:
            gaps.append({
                "reason": "SEC_13F_CUSIP_UNMAPPED", "cusip": cusip,
                "manager_cik": filing["manager_cik"], "report_period": report_period,
            })
            continue
        value = {
            "manager_cik": str(filing["manager_cik"]),
            "manager_name": filing.get("manager_name"),
            "report_period": report_period,
            "issuer_name": _child_text(row, "nameOfIssuer"),
            "title_of_class": _child_text(row, "titleOfClass"),
            "cusip": cusip,
            "reported_value_thousands_usd": _decimal(_child_text(row, "value"), "value"),
            "shares_or_principal": _decimal(_child_text(row, "sshPrnamt"), "shares_or_principal"),
            "shares_or_principal_type": _child_text(row, "sshPrnamtType"),
            "put_call": _child_text(row, "putCall"),
            "investment_discretion": _child_text(row, "investmentDiscretion"),
            "other_manager": _child_text(row, "otherManager"),
            "voting_authority": {
                "sole": _decimal(_child_text(row, "Sole"), "voting_sole"),
                "shared": _decimal(_child_text(row, "Shared"), "voting_shared"),
                "none": _decimal(_child_text(row, "None"), "voting_none"),
            },
            "form": filing["form"],
            "accession": filing.get("accession"),
            "amendment_type": filing.get("amendment_type"),
            "amendment_number": filing.get("amendment_number"),
            "part_index": part_index,
            "part_count": part_count,
            "row_index": index,
        }
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="institutional_ownership",
            semantic_field="sec_13f_holding", value=value,
            source_id=(
                f"sec-13f:{filing['manager_cik']}:{filing.get('accession')}:"
                f"part-{part_index}:row-{index}"
            ),
            source_family="sec", source_locator=str(filing["document_url"]),
            source_version=PARSER_VERSION, as_of=as_of, published_at=published,
            retrieved_at=retrieved, raw_content_hash=raw_hash,
            limitations=[
                "仅覆盖明确管理人集合，不代表全市场机构持仓",
                "数量按申报原值保存，未自动进行拆股回溯调整",
            ],
        ))
    return {
        "schema_version": "sec-13f-part/1.0.0",
        "manager_cik": str(filing["manager_cik"]),
        "report_period": report_period,
        "form": filing["form"],
        "accession": filing.get("accession"),
        "amendment_type": filing.get("amendment_type"),
        "part_index": part_index,
        "part_count": part_count,
        "evidence": evidence,
        "gaps": gaps,
        "raw_content_hash": raw_hash,
        "parser_version": PARSER_VERSION,
    }


def assemble_13f_period(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not parts:
        raise ValueError("SEC_13F_PARTS_EMPTY")
    manager = {str(part.get("manager_cik")) for part in parts}
    periods = {part.get("report_period") for part in parts}
    accessions = {part.get("accession") for part in parts}
    expected_count = {part.get("part_count") for part in parts}
    if len(manager) != 1 or len(periods) != 1 or len(accessions) != 1 or len(expected_count) != 1:
        raise ValueError("SEC_13F_PART_BINDING_MISMATCH")
    count = expected_count.pop()
    if {part.get("part_index") for part in parts} != set(range(1, count + 1)):
        raise ValueError("SEC_13F_PART_COVERAGE_INCOMPLETE")
    evidence = [fact for part in parts for fact in part["evidence"]]
    if len({fact["evidence_id"] for fact in evidence}) != len(evidence):
        raise ValueError("SEC_13F_EVIDENCE_DUPLICATE")
    body = {
        "schema_version": "sec-13f-period/1.0.0",
        "manager_cik": next(iter(manager)),
        "report_period": next(iter(periods)),
        "accession": next(iter(accessions)),
        "form": parts[0]["form"],
        "amendment_type": parts[0].get("amendment_type"),
        "coverage": "COMPLETE_FOR_LISTED_MANAGER_ACCESSION_PARTS",
        "part_count": count,
        "evidence": sorted(evidence, key=lambda item: item["evidence_id"]),
        "gaps": [gap for part in parts for gap in part.get("gaps", [])],
        "raw_hashes": sorted(part["raw_content_hash"] for part in parts),
    }
    body["period_hash"] = content_hash(body)
    return body


def compare_13f_periods(
    current: Mapping[str, Any], prior: Mapping[str, Any], *, split_adjustments: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if current.get("manager_cik") != prior.get("manager_cik") or current.get("report_period") <= prior.get("report_period"):
        raise ValueError("SEC_13F_PERIOD_COMPARISON_INVALID")
    split_adjustments = split_adjustments or {}
    current_by_security: dict[str, list[Mapping[str, Any]]] = {}
    prior_by_security: dict[str, list[Mapping[str, Any]]] = {}
    for fact in current["evidence"]:
        current_by_security.setdefault(fact["security_id"], []).append(fact)
    for fact in prior["evidence"]:
        prior_by_security.setdefault(fact["security_id"], []).append(fact)

    def comparable_position(facts: Sequence[Mapping[str, Any]]) -> tuple[str | None, list[list[str | None]]]:
        signatures = sorted({
            (fact["value"].get("shares_or_principal_type"), fact["value"].get("put_call"))
            for fact in facts
        }, key=lambda item: (str(item[0]), str(item[1])))
        if not facts or len(signatures) != 1:
            return None, [list(item) for item in signatures]
        total = sum(Decimal(str(fact["value"]["shares_or_principal"])) for fact in facts)
        return format(total, "f"), [list(signatures[0])]

    rows = []
    for security_id in sorted(set(current_by_security) | set(prior_by_security)):
        latest = current_by_security.get(security_id, [])
        earlier = prior_by_security.get(security_id, [])
        latest_position, latest_signatures = comparable_position(latest)
        earlier_position, earlier_signatures = comparable_position(earlier)
        adjustment = split_adjustments.get(security_id)
        if adjustment is not None:
            if set(adjustment) != {"factor", "source_id", "as_of", "retrieved_at"}:
                raise ValueError("SEC_13F_SPLIT_ADJUSTMENT_PROVENANCE_INVALID")
            _decimal(str(adjustment["factor"]), "split_factor")
        if not latest or not earlier:
            status = "NOT_COMPARABLE_MISSING_PERIOD"
        elif latest_position is None or earlier_position is None or latest_signatures != earlier_signatures:
            status = "NOT_COMPARABLE_MIXED_POSITION_TYPES"
        elif adjustment is not None:
            status = "ADJUSTMENT_AVAILABLE_REQUIRES_EXPLICIT_CALCULATION"
        else:
            status = "RAW_REPORTED_NOT_SPLIT_ADJUSTED"
        rows.append({
            "security_id": security_id,
            "current_evidence_ids": sorted(fact["evidence_id"] for fact in latest),
            "prior_evidence_ids": sorted(fact["evidence_id"] for fact in earlier),
            "current_reported_position": latest_position,
            "prior_reported_position": earlier_position,
            "position_signatures": {
                "current": latest_signatures, "prior": earlier_signatures,
            },
            "aggregation_basis": "SUM_WITHIN_IDENTICAL_SHARES_OR_PRINCIPAL_TYPE_AND_PUT_CALL",
            "comparison_status": status,
            "split_adjustment": dict(adjustment) if adjustment is not None else None,
        })
    body = {
        "schema_version": "sec-13f-two-period-comparison/1.1.0",
        "manager_cik": current["manager_cik"],
        "current_period": current["report_period"],
        "prior_period": prior["report_period"],
        "coverage": "LISTED_MANAGER_AND_MAPPED_SECURITIES_ONLY",
        "rows": rows,
        "source_period_hashes": [current["period_hash"], prior["period_hash"]],
    }
    body["comparison_hash"] = content_hash(body)
    return body
