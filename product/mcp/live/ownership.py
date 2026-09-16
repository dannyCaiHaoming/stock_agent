"""SEC Forms 3/4/5 的有界 XML 解析；不推断交易动机或资金方向。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from product.mcp.live.contracts import validate_contract
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


PARSER_VERSION = "sec-ownership-xml/1.1.1"
MAX_BYTES = 4 * 1024 * 1024


def _text(node: ET.Element, path: str) -> str | None:
    found = node.find(path)
    if found is None or found.text is None or not found.text.strip():
        return None
    return found.text.strip()


def _decimal(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"SEC_OWNERSHIP_VALUE_INVALID:{field}") from exc
    if not number.is_finite():
        raise ValueError(f"SEC_OWNERSHIP_VALUE_INVALID:{field}")
    return format(number, "f")


def parse_ownership_document(
    raw: bytes, *, filing: Mapping[str, Any], security_id: str,
    retrieved_at: str,
) -> dict[str, Any]:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("SEC_OWNERSHIP_DOCUMENT_SIZE_INVALID")
    if filing.get("form") not in {"3", "3/A", "4", "4/A", "5", "5/A"}:
        raise ValueError("SEC_OWNERSHIP_FORM_UNSUPPORTED")
    if not security_id:
        raise ValueError("SEC_OWNERSHIP_SECURITY_REQUIRED")
    published_at = iso_utc(str(filing["published_at"]))
    retrieved_at = iso_utc(retrieved_at)
    if parse_timestamp(published_at) > parse_timestamp(retrieved_at):
        raise ValueError("SEC_OWNERSHIP_PUBLICATION_AFTER_RETRIEVAL")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("SEC_OWNERSHIP_XML_INVALID") from exc
    if root.tag.rsplit("}", 1)[-1] != "ownershipDocument":
        raise ValueError("SEC_OWNERSHIP_ROOT_INVALID")
    issuer_cik = _text(root, ".//issuer/issuerCik")
    owner_cik = _text(root, ".//reportingOwner/reportingOwnerId/rptOwnerCik")
    owner_name = _text(root, ".//reportingOwner/reportingOwnerId/rptOwnerName")
    relationships = {
        name: _text(root, f".//reportingOwner/reportingOwnerRelationship/{name}") == "1"
        for name in ("isDirector", "isOfficer", "isTenPercentOwner", "isOther")
    }
    raw_hash = hashlib.sha256(raw).hexdigest()
    transactions = []
    tables = (
        ("nonDerivativeTransaction", "NON_DERIVATIVE"),
        ("derivativeTransaction", "DERIVATIVE"),
    )
    for element_name, instrument_type in tables:
        for index, node in enumerate(root.findall(f".//{element_name}")):
            transaction_date = _text(node, "transactionDate/value")
            if transaction_date is None:
                raise ValueError("SEC_OWNERSHIP_TRANSACTION_DATE_MISSING")
            day = date.fromisoformat(transaction_date)
            code = _text(node, "transactionCoding/transactionCode")
            acquired_disposed = _text(node, "transactionAmounts/transactionAcquiredDisposedCode/value")
            item = {
                "instrument_type": instrument_type,
                "security_title": _text(node, "securityTitle/value"),
                "transaction_date": day.isoformat(),
                "transaction_code": code,
                "acquired_disposed_code": acquired_disposed,
                "shares": _decimal(_text(node, "transactionAmounts/transactionShares/value"), "shares"),
                "price_per_share": _decimal(_text(node, "transactionAmounts/transactionPricePerShare/value"), "price"),
                "post_transaction_amount": _decimal(
                    _text(node, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"), "post_amount"
                ),
                "ownership_nature": _text(node, "ownershipNature/directOrIndirectOwnership/value"),
                "footnote_ids": sorted({
                    child.attrib["id"]
                    for child in node.findall(".//*[@id]")
                    if child.attrib.get("id")
                }),
            }
            fact = {
                "schema_version": "live-fact/1.0.0",
                "security_id": security_id,
                "semantic_field": "ownership_insider_transaction",
                "value": item,
                "unit": "reported_transaction",
                "currency": "USD" if item["price_per_share"] is not None else None,
                "source_id": f"sec-ownership-{filing.get('accession')}",
                # source_type 对应获准的数据供应方；ownership 由 kind 与
                # semantic_field 表达，避免 Gate 将合法 SEC 披露误判为未授权来源。
                "source_type": "sec",
                "source_locator": str(filing["document_url"]),
                "source_version": PARSER_VERSION,
                "as_of": f"{day.isoformat()}T00:00:00Z",
                "published_at": published_at,
                "published_at_policy": "submission_acceptance_datetime",
                "retrieved_at": retrieved_at,
                "raw_content_hash": raw_hash,
                "kind": "ownership",
                "usage": "current",
                "metadata": {
                    "form": filing["form"], "accession": filing.get("accession"),
                    "submission_document_url": filing.get(
                        "submission_document_url", filing["document_url"]
                    ),
                    "document_resolution_version": filing.get("document_resolution_version"),
                    "issuer_cik": issuer_cik, "owner_cik": owner_cik,
                    "owner_name": owner_name, "relationships": relationships,
                    "transaction_index": index,
                    "quantity_basis": "as_reported/not_split_adjusted",
                    "direction_semantics": "A/D code only; motive and market direction not inferred",
                },
                "parent_ids": [], "parent_hashes": [],
            }
            fact["evidence_id"] = "ev-sec-ownership-" + content_hash(fact)
            validate_contract("fact", fact)
            transactions.append(fact)
    return {
        "evidence": transactions,
        "gaps": ([] if transactions else [{"reason": "SEC_OWNERSHIP_NO_TRANSACTIONS"}]),
        "raw_content_hash": raw_hash,
        "parser_version": PARSER_VERSION,
        "coverage": "FORMS_3_4_5_TRANSACTION_TABLES_ONLY",
    }
