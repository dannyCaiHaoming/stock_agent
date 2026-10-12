"""冻结历史Company报告包的纯读取校验；不创建旧宿主执行器。"""
from __future__ import annotations
import hashlib
from typing import Mapping
from product.runtime.hashing import canonical_hash, verify_legacy_object_hash, HashContractError

class ReportPackageError(ValueError):
    pass

ResearchMemoryError = ReportPackageError

def validate_company_package(value):
    from product.runtime.research_memory import report_reuse_key
    required = {
        "schema_version", "security_id", "research_input_fingerprint",
        "reuse_key", "report", "markdown", "request", "evidence",
        "calculations", "attachment", "validation", "manifest",
    }
    if set(value) != required or value.get("schema_version") != "company-research-report-package/1.0.0":
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_INVALID")
    if value.get("reuse_key") != report_reuse_key(
        str(value.get("security_id")), str(value.get("research_input_fingerprint")),
    ):
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_BINDING_INVALID")
    report = value.get("report")
    manifest = value.get("manifest")
    if not isinstance(report, Mapping) or not isinstance(manifest, Mapping):
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_INVALID")
    request = value.get("request")
    supported_request = {
        "equity-research-report/1.0.0": "holding-research-request/1.0.0",
        "equity-research-report/2.0.0": "holding-research-request/2.0.0",
    }.get(report.get("schema_version"))
    if supported_request is None:
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_READER_UNSUPPORTED_VERSION")
    if not isinstance(request, Mapping) or request.get("schema_version") != supported_request:
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_BINDING_INVALID")
    from product.council.common_stock_research import validate_equity_research_report
    try:
        validate_equity_research_report(report, request=request,
            calculation_artifact_ids=[item["calculation_id"] for item in value["calculations"]
                if isinstance(item, Mapping) and "calculation_id" in item])
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_BINDING_INVALID") from exc
    try:
        verify_legacy_object_hash(report, manifest.get("report_hash"), kind="canonical-object",
                                  location="company-research-report-package:report")
    except HashContractError as exc:
        raise ResearchMemoryError(f"RESEARCH_MEMORY_REPORT_PACKAGE_HASH_MISMATCH:{exc}") from exc
    expected_hashes = {
        "request_hash": canonical_hash(value["request"]),
        "evidence_hash": canonical_hash(value["evidence"]),
        "calculation_hash": canonical_hash(value["calculations"]),
        "attachment_hash": canonical_hash(value["attachment"]),
        "markdown_hash": hashlib.sha256(
            str(value["markdown"]).encode("utf-8")
        ).hexdigest(),
    }
    if any(manifest.get(field) != digest for field, digest in expected_hashes.items()):
        raise ResearchMemoryError("RESEARCH_MEMORY_REPORT_PACKAGE_HASH_MISMATCH")
    return value
