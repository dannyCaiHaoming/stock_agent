"""SEC 响应的确定性解析。此模块不执行网络请求或投资判断。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp

ADAPTER_VERSION = "sec-parser/0.2.0"
HISTORY_ISOLATION_VERSION = "sec-history-isolation/1.0.0"
PRIMARY_DOCUMENT_PATH_PATTERN = (
    r"(?:xsl[A-Za-z0-9_-]+/)?[A-Za-z0-9_-][A-Za-z0-9_.-]*"
)


def normalize_cik(value: str | int) -> str:
    text = str(value)
    if not re.fullmatch(r"[0-9]{1,10}", text) or int(text) == 0:
        raise ValueError("SEC_CIK_INVALID")
    return text.zfill(10)


def _decode(raw: bytes) -> dict:
    def reject(value):
        raise ValueError("SEC_NON_FINITE_JSON")

    result = json.loads(raw, parse_float=Decimal, parse_constant=reject)
    if not isinstance(result, dict):
        raise ValueError("SEC_RESPONSE_NOT_OBJECT")
    return result


def parse_submissions(raw: bytes, *, cik: str, retrieved_at: str) -> dict[str, dict]:
    """读取 recent 平行数组；历史分页由后续采集器单独获取，不假装完整。"""
    cik = normalize_cik(cik)
    retrieved_at = iso_utc(retrieved_at)
    body = _decode(raw)
    if normalize_cik(body["cik"]) != cik:
        raise ValueError("SEC_CIK_MISMATCH")
    recent = body["filings"]["recent"]
    return _parse_submission_rows(recent, raw=raw, cik=cik, retrieved_at=retrieved_at,
                                  locator=f"https://data.sec.gov/submissions/CIK{cik}.json")


def parse_submission_page(raw: bytes, *, cik: str, name: str, retrieved_at: str,
                          excluded: list | None = None) -> dict:
    cik = normalize_cik(cik)
    if not re.fullmatch(rf"CIK{cik}-submissions-[0-9]{{3}}\.json", name):
        raise ValueError("SEC_PAGE_NAME_INVALID")
    return _parse_submission_rows(_decode(raw), raw=raw, cik=cik,
                                  retrieved_at=iso_utc(retrieved_at),
                                  locator=f"https://data.sec.gov/submissions/{name}",
                                  excluded=excluded)


def _parse_submission_rows(recent: dict, *, raw: bytes, cik: str,
                           retrieved_at: str, locator: str, excluded: list | None = None) -> dict:
    fields = ("accessionNumber", "acceptanceDateTime", "form", "primaryDocument", "reportDate")
    if any(not isinstance(recent.get(key), list) for key in fields):
        raise ValueError("SEC_SUBMISSIONS_ARRAY_MISSING")
    if len({len(recent[key]) for key in fields}) != 1:
        raise ValueError("SEC_SUBMISSIONS_ARRAY_LENGTH")
    result = {}
    seen = set()
    isolated = []
    raw_hash = hashlib.sha256(raw).hexdigest()
    for index, (accession, accepted, form, document, period) in enumerate(zip(*(recent[key] for key in fields))):
        if not isinstance(accession, str) or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
            raise ValueError("SEC_ACCESSION_INVALID")
        # SEC 的所有权等 XML 申报可带一个 xsl 展示目录；保留原路径，
        # 不解码/截断，不允许任意子目录、绝对 URL 或路径穿越。
        missing_document = document == "" and excluded is not None
        if not missing_document and (not isinstance(document, str) or not re.fullmatch(
            PRIMARY_DOCUMENT_PATH_PATTERN, document
        )):
            raise ValueError("SEC_DOCUMENT_INVALID")
        published = iso_utc(accepted)  # 不用 filingDate/reportDate 冒充公开时间。
        if parse_timestamp(published) > parse_timestamp(retrieved_at):
            raise ValueError("SEC_ACCEPTED_AFTER_RETRIEVAL")
        if period:
            date.fromisoformat(period)
        if not isinstance(form, str) or not form or not isinstance(period, str):
            raise ValueError("SEC_SUBMISSION_METADATA_INVALID")
        if accession in seen:
            raise ValueError("SEC_ACCESSION_DUPLICATE")
        seen.add(accession)
        filing = {
            "cik": cik, "accession": accession, "form": form,
            "report_date": period or None,
            "published_at": published, "as_of": published,
            "published_at_policy": "submission_acceptance_datetime",
            "published_at_precision": "second",
            "retrieved_at": retrieved_at, "source_id": f"sec-submissions-{cik}",
            "source_locator": locator,
            "raw_content_hash": raw_hash, "adapter_version": ADAPTER_VERSION,
        }
        if missing_document:
            isolated.append({**filing, "row_index": index,
                             "reason": "SEC_HISTORY_DOCUMENT_MISSING",
                             "isolation_version": HISTORY_ISOLATION_VERSION})
        else:
            result[accession] = {**filing,
                "document_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{document}"}
    if excluded is not None:
        excluded.extend(isolated)
    return result


def parse_companyfacts(raw: bytes, *, cik: str, security_id: str,
                       retrieved_at: str, filings: dict[str, dict]) -> dict:
    """保留期间、单位及修订；缺少公开时点的行隔离，不推定可用。"""
    cik = normalize_cik(cik)
    retrieved_at = iso_utc(retrieved_at)
    if not isinstance(security_id, str) or not security_id.strip():
        raise ValueError("SEC_SECURITY_ID_REQUIRED")
    body = _decode(raw)
    if normalize_cik(body["cik"]) != cik:
        raise ValueError("SEC_CIK_MISMATCH")
    raw_hash = hashlib.sha256(raw).hexdigest()
    evidence, excluded = [], []
    for taxonomy, concepts in body["facts"].items():
        for tag, concept in concepts.items():
            for unit, rows in concept["units"].items():
                for index, row in enumerate(rows):
                    accession = row["accn"]
                    filing = filings.get(accession)
                    if filing is None:
                        excluded.append({"accession": accession, "taxonomy": taxonomy,
                                         "tag": tag, "unit": unit, "row_index": index,
                                         "reason": "SEC_PUBLICATION_NOT_VERIFIED"})
                        continue
                    if filing["cik"] != cik or filing["accession"] != accession or filing["form"] != row["form"]:
                        raise ValueError("SEC_FILING_BINDING_MISMATCH")
                    published = iso_utc(filing["published_at"])
                    if parse_timestamp(published) > parse_timestamp(retrieved_at):
                        raise ValueError("SEC_ACCEPTED_AFTER_RETRIEVAL")
                    end = date.fromisoformat(row["end"])
                    start = date.fromisoformat(row["start"]) if "start" in row else None
                    if start and start > end:
                        raise ValueError("SEC_PERIOD_INVALID")
                    try:
                        number = Decimal(str(row["val"]))
                    except InvalidOperation as exc:
                        raise ValueError("SEC_VALUE_INVALID") from exc
                    if not number.is_finite():
                        raise ValueError("SEC_VALUE_NON_FINITE")
                    fact = {
                        "security_id": security_id, "cik": cik, "accession": accession,
                        "taxonomy": taxonomy, "tag": tag, "unit": unit,
                        "value": format(number, "f"), "form": row["form"],
                        "period_start": start.isoformat() if start else None,
                        "period_end": end.isoformat(), "context_type": "duration" if start else "instant",
                        "frame": row.get("frame"), "fiscal_year": row.get("fy"),
                        "fiscal_period": row.get("fp"),
                        "as_of": f"{end.isoformat()}T00:00:00Z", "published_at": published,
                        "published_at_policy": filing["published_at_policy"],
                        "published_at_precision": filing["published_at_precision"],
                        "retrieved_at": retrieved_at, "source_id": f"sec-companyfacts-{cik}",
                        "source_locator": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                        "raw_content_hash": raw_hash,
                        "publication_source_hash": content_hash(filing),
                        "publication_retrieved_at": filing["retrieved_at"],
                        "row_locator": {"taxonomy": taxonomy, "tag": tag, "unit": unit, "index": index},
                        "adapter_version": ADAPTER_VERSION,
                    }
                    fact["evidence_id"] = "ev-sec-" + content_hash(fact)
                    evidence.append(fact)
    return {"evidence": evidence, "excluded": excluded, "raw_content_hash": raw_hash}
