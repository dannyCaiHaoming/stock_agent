"""Research Memory 与冻结运行产物的只读浏览适配器。"""

from __future__ import annotations

from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote

from product.council.common_stock_research import validate_equity_research_report
from product.council.multidimensional_research import validate_research_dimension_report
from product.council.research_visuals import validate_visual_bundle
from product.runtime.equity_research_package import validate_equity_research_package
from product.runtime.hashing import canonical_hash
from product.runtime.research_memory import MEMORY_SCHEMA_VERSION, fact_content_hash, report_reuse_key
from product.runtime.schema_validation import validate_schema_instance


class BrowserDataError(ValueError):
    """只包含可安全显示的稳定错误码。"""


SUPPORTED_MEMORY_VERSION = MEMORY_SCHEMA_VERSION
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200
FAILED_ATTEMPTS = {"SOURCE_LIMITED", "FAILED_VALIDATION", "FAILED_PERSISTENCE", "LOCK_TIMEOUT"}
MARKET_FIELDS = {
    "open_price", "high_price", "low_price", "historical_close_price",
    "adjusted_close_price", "close_price", "share_volume", "cash_dividend",
    "stock_split_ratio",
}
VALUATION_HINTS = ("price_to_", "valuation", "market_cap", "enterprise_value", "trailing_pe", "forward_pe")
FINANCIAL_METRICS = (
    ("revenue", "营收", {"revenue", "us-gaap.RevenueFromContractWithCustomerExcludingAssessedTax"}),
    ("net_income", "净利润", {"net_income", "us-gaap.NetIncomeLoss"}),
    ("diluted_eps", "稀释 EPS", {"diluted_eps", "us-gaap.EarningsPerShareDiluted"}),
    ("operating_cash_flow", "经营现金流", {"operating_cash_flow", "us-gaap.NetCashProvidedByUsedInOperatingActivities"}),
    ("capital_expenditure", "资本开支", {"capital_expenditure", "capital_expenditures", "us-gaap.PaymentsToAcquirePropertyPlantAndEquipment"}),
    ("cash", "现金及现金等价物", {"cash", "cash_and_cash_equivalents", "us-gaap.CashAndCashEquivalentsAtCarryingValue", "us-gaap.CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"}),
    ("debt", "长期债务", {"debt", "long_term_debt", "us-gaap.LongTermDebt", "us-gaap.LongTermDebtNoncurrent"}),
)
DISCLOSURE_FIELDS = {
    "risk_factors", "management_discussion", "business",
    "ownership_insider_transaction",
}
DISCLOSURE_LABELS = {
    "business": "业务概况",
    "management_discussion": "管理层讨论与分析（MD&A）",
    "risk_factors": "风险因素",
    "ownership_insider_transaction": "内部人交易披露",
}
TRANSACTION_CODE_LABELS = {
    "A": "授予、奖励或其他取得",
    "D": "向发行人处置或返还",
    "F": "以证券支付税款或行权价",
    "G": "赠与",
    "M": "期权或衍生证券行权/转换",
    "P": "公开市场或私人购买",
    "S": "公开市场或私人出售",
}
COMPANY_RESEARCH_CAPABILITIES = (
    "FUNDAMENTAL_EVENT", "RESEARCH_REPORT",
    "OWNERSHIP_DISCLOSURE", "INDUSTRY_COMPARISON",
)
REPORT_INDEX_STATUS_BY_REPORT_STATUS = {
    "COMPLETE": "VALID_RESEARCH",
    "LOW_CONFIDENCE": "LOW_CONFIDENCE",
    "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
    "TIMEOUT": "FAILED",
}
KNOWN_RUN_MARKERS = ("run_manifest.json", "source-bundle.json", "data-preparation.json")
KNOWN_DIRECT_ARTIFACTS = (
    "official-macro-snapshot.json", "benchmark-snapshot.json",
    "market-context-snapshot.json", "market-state-calculation.json",
)
PRIVATE_KEYS = {
    "request", "user_request", "original_request", "private_request",
    "account", "account_context", "portfolio", "portfolio_context",
    "credential", "credentials", "api_key", "token", "password",
}
REPORT_KEYS = {
    "schema_version", "report_id", "research_id", "title", "status",
    "evaluation_status", "decision_cutoff", "security", "security_id",
    "security_ids", "capability", "summary", "research_summary", "sections", "claims",
    "assumptions", "calculations", "interpretations", "limitations",
    "observation_conditions", "invalidation_conditions", "data_gaps",
    "documents", "research_relationships", "artifact_refs", "bindings",
    "counter_evidence_refs", "reevaluation_triggers", "monitoring_indicators",
    "confidence", "confidence_rationale", "skill_execution", "research_scope",
    "run_id", "invocation_id", "agent",
}
HOLDING_RESEARCH_REQUEST_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas/runtime/holding-research-request.schema.json").read_text(
        encoding="utf-8",
    )
)


def _safe_regular_file(root: Path, path: Path) -> bool:
    """Require a regular file whose full path stays under a symlink-free root."""

    try:
        root = root.resolve(strict=True)
        if path.is_symlink() or not path.is_file():
            return False
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            return False
        current = path.parent
        while current != root:
            if current.is_symlink() or not current.is_relative_to(root):
                return False
            current = current.parent
        return not root.is_symlink()
    except (OSError, RuntimeError):
        return False


def _json_object(raw: str, code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise BrowserDataError(code) from exc
    if not isinstance(value, dict):
        raise BrowserDataError(code)
    return value


def _safe_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def _semantic_field(fact: Mapping[str, Any]) -> str:
    return str(fact.get("semantic_field", ""))


def _period(fact: Mapping[str, Any]) -> str:
    metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
    return str(metadata.get("period_end") or metadata.get("trading_date") or fact.get("as_of") or "")


def _period_type(fact: Mapping[str, Any]) -> str:
    metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
    if metadata.get("context_type") == "instant":
        return "时点"
    if not metadata.get("period_start"):
        return "期间不明"
    fiscal_period = str(metadata.get("fiscal_period") or "").upper()
    form = str(metadata.get("form") or "").upper()
    frame = str(metadata.get("frame") or "")
    try:
        days = (date.fromisoformat(str(metadata["period_end"])) - date.fromisoformat(str(metadata["period_start"]))).days
    except (KeyError, TypeError, ValueError):
        return "期间不明"
    if form.startswith("10-K") or fiscal_period in {"FY", "YEAR"} or days >= 300:
        return "年度"
    if frame and "Q" in frame and days <= 120:
        return "单季"
    if days <= 120:
        return "单季"
    return "年初至今" if fiscal_period.startswith("Q") else "累计期间"


def _metric_definition(field: str) -> tuple[str, str] | None:
    for metric_id, label, aliases in FINANCIAL_METRICS:
        if field in aliases:
            return metric_id, label
    return None


def _numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in {float("inf"), float("-inf")} else None


def _fact_group(fact: Mapping[str, Any]) -> str:
    field = _semantic_field(fact)
    source = str(fact.get("source_id", "")).casefold()
    metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
    if field in MARKET_FIELDS:
        return "行情事实"
    if any(hint in field.casefold() for hint in VALUATION_HINTS):
        return "估值输入"
    if source.startswith("sec-") or metadata.get("form") or metadata.get("accession"):
        return "财务与披露"
    return "其他事实"


def _external_link(value: Any) -> str | None:
    text = str(value or "")
    return text if text.startswith(("https://", "http://")) else None


def _scrub_private(value: Any) -> Any:
    """保留研究正文结构，同时移除明确的私人请求与账户上下文字段。"""
    if isinstance(value, Mapping):
        return {
            str(key): _scrub_private(child)
            for key, child in value.items()
            if str(key).casefold() not in PRIVATE_KEYS
            and not str(key).casefold().endswith(("_path", "_root"))
        }
    if isinstance(value, list):
        return [_scrub_private(item) for item in value]
    return value


def _string_refs(value: Any, key_name: str) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == key_name:
                if isinstance(child, str):
                    result.add(child)
                elif isinstance(child, list):
                    result.update(item for item in child if isinstance(item, str))
            else:
                result.update(_string_refs(child, key_name))
    elif isinstance(value, list):
        for child in value:
            result.update(_string_refs(child, key_name))
    return result


def _calculation_identities(value: Any) -> set[str]:
    identities: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {"calculation_id", "calculation_ref"} and isinstance(child, str) and child:
                identities.add(child)
            elif key in {"calculation_ids", "calculation_refs"} and isinstance(child, list):
                identities.update(item for item in child if isinstance(item, str) and item)
            else:
                identities.update(_calculation_identities(child))
    elif isinstance(value, list):
        for child in value:
            identities.update(_calculation_identities(child))
    return identities


def _validated_report(
    package: Mapping[str, Any], security_id: str, expected_report_hash: str,
    *, expected_run_id: str, expected_cutoff: str, expected_status: str,
) -> Mapping[str, Any]:
    expected = {
        "schema_version", "security_id", "research_input_fingerprint", "reuse_key",
        "report", "markdown", "request", "evidence", "calculations", "attachment",
        "validation", "manifest",
    }
    if set(package) != expected or package.get("schema_version") != "company-research-report-package/1.0.0":
        raise BrowserDataError("BROWSER_REPORT_PACKAGE_INVALID")
    if package.get("security_id") != security_id or package.get("reuse_key") != report_reuse_key(
        security_id, str(package.get("research_input_fingerprint"))
    ):
        raise BrowserDataError("BROWSER_REPORT_PACKAGE_BINDING_INVALID")
    report, manifest = package.get("report"), package.get("manifest")
    if not isinstance(report, Mapping) or not isinstance(manifest, Mapping):
        raise BrowserDataError("BROWSER_REPORT_PACKAGE_INVALID")
    report_hash = canonical_hash(report)
    expected_hashes = {
        "report_hash": report_hash,
        "request_hash": canonical_hash(package["request"]),
        "evidence_hash": canonical_hash(package["evidence"]),
        "calculation_hash": canonical_hash(package["calculations"]),
        "attachment_hash": canonical_hash(package["attachment"]),
        "markdown_hash": hashlib.sha256(str(package["markdown"]).encode("utf-8")).hexdigest(),
    }
    if report_hash != expected_report_hash or any(manifest.get(key) != value for key, value in expected_hashes.items()):
        raise BrowserDataError("BROWSER_REPORT_HASH_MISMATCH")
    if report.get("schema_version") == "equity-research-report/1.0.0":
        request = package.get("request")
        if not isinstance(request, Mapping):
            raise BrowserDataError("BROWSER_REPORT_CONTRACT_INVALID")
        evidence = package.get("evidence")
        if not isinstance(evidence, list) or any(not isinstance(item, Mapping) for item in evidence):
            raise BrowserDataError("BROWSER_REPORT_CONTRACT_INVALID")
        try:
            validate_schema_instance(request, HOLDING_RESEARCH_REQUEST_SCHEMA)
        except (KeyError, TypeError, ValueError) as exc:
            raise BrowserDataError("BROWSER_REPORT_CONTRACT_INVALID") from exc
        request_body = {key: deepcopy(value) for key, value in request.items() if key != "request_hash"}
        if request.get("request_hash") != canonical_hash(request_body):
            raise BrowserDataError("BROWSER_REPORT_CONTRACT_INVALID")
        request_security = request.get("security") if isinstance(request.get("security"), Mapping) else {}
        if (
            request.get("run_id") != expected_run_id
            or request.get("decision_cutoff") != expected_cutoff
            or request_security.get("security_id") != security_id
        ):
            raise BrowserDataError("BROWSER_REPORT_PACKAGE_BINDING_INVALID")
        evidence_ids = [str(item.get("evidence_id") or "") for item in evidence]
        allowed_evidence_ids = request.get("allowed_evidence_ids")
        if (
            not isinstance(allowed_evidence_ids, list)
            or any(not value for value in evidence_ids)
            or len(evidence_ids) != len(set(evidence_ids))
            or set(evidence_ids) != set(str(item) for item in allowed_evidence_ids)
            or any(
                item.get("security_id") not in {security_id, "MARKET", "US:MARKET"}
                for item in evidence
            )
        ):
            raise BrowserDataError("BROWSER_REPORT_EVIDENCE_BINDING_INVALID")
        attachment = package.get("attachment")
        if attachment is not None:
            if not isinstance(attachment, Mapping):
                raise BrowserDataError("BROWSER_REPORT_ATTACHMENT_INVALID")
            try:
                validate_equity_research_package(attachment)
            except (KeyError, TypeError, ValueError) as exc:
                raise BrowserDataError("BROWSER_REPORT_ATTACHMENT_INVALID") from exc
            if (
                attachment.get("security_id") != security_id
                or attachment.get("run_id") != expected_run_id
                or attachment.get("decision_cutoff") != expected_cutoff
                or attachment.get("gate_bundle_hash") != request.get("evidence_bundle_hash")
            ):
                raise BrowserDataError("BROWSER_REPORT_PACKAGE_BINDING_INVALID")
            attachment_refs = (
                _string_refs(attachment, "evidence_refs")
                | _string_refs(attachment, "input_evidence_refs")
            )
            if {item for item in attachment_refs if not item.startswith("raw:")} - set(evidence_ids):
                raise BrowserDataError("BROWSER_REPORT_EVIDENCE_BINDING_INVALID")
        calculation_ids = sorted(
            _calculation_identities(package.get("calculations"))
            | _calculation_identities(attachment)
        )
        try:
            validate_equity_research_report(
                report, request=request, calculation_artifact_ids=calculation_ids,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BrowserDataError("BROWSER_REPORT_CONTRACT_INVALID") from exc
        bindings = report.get("bindings") if isinstance(report.get("bindings"), Mapping) else {}
        report_security = report.get("security") if isinstance(report.get("security"), Mapping) else {}
        if (
            report_security.get("security_id") != security_id
            or report.get("run_id") != expected_run_id
            or bindings.get("decision_cutoff") != expected_cutoff
            or REPORT_INDEX_STATUS_BY_REPORT_STATUS.get(str(report.get("status"))) != expected_status
        ):
            raise BrowserDataError("BROWSER_REPORT_PACKAGE_BINDING_INVALID")
    return report


class ReadOnlyResearchMemory:
    """不用 ResearchMemory 初始化和迁移的 SQLite 只读视图。"""

    def __init__(self, root: Path, *, busy_timeout_ms: int = 350):
        raw = Path(root).expanduser()
        if raw.is_symlink():
            raise BrowserDataError("BROWSER_MEMORY_ROOT_SYMLINK_REJECTED")
        self.root = raw.resolve()
        self.database_path = self.root / "research-memory.sqlite3"
        self.objects_root = self.root / "objects"
        self.busy_timeout_ms = max(1, min(5000, int(busy_timeout_ms)))
        if (
            not self.root.is_dir()
            or not _safe_regular_file(self.root, self.database_path)
        ):
            raise BrowserDataError("BROWSER_MEMORY_DATABASE_MISSING")
        if self.objects_root.exists() and (
            self.objects_root.is_symlink() or not self.objects_root.is_dir()
        ):
            raise BrowserDataError("BROWSER_MEMORY_OBJECTS_SYMLINK_REJECTED")
        self._check_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        uri = f"file:{quote(str(self.database_path), safe='/')}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=self.busy_timeout_ms / 1000)
        except sqlite3.Error as exc:
            raise BrowserDataError("BROWSER_MEMORY_OPEN_FAILED") from exc
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
        except sqlite3.OperationalError as exc:
            code = "BROWSER_MEMORY_BUSY" if "locked" in str(exc).casefold() else "BROWSER_MEMORY_READ_FAILED"
            raise BrowserDataError(code) from exc
        finally:
            connection.close()

    def _check_schema(self) -> None:
        with self.connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version != SUPPORTED_MEMORY_VERSION:
                raise BrowserDataError("BROWSER_MEMORY_SCHEMA_UNSUPPORTED")
            required = {"fact_versions", "dataset_state", "attempts", "research_views", "reports", "reuse_events"}
            tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables:
                raise BrowserDataError("BROWSER_MEMORY_SCHEMA_INCOMPLETE")

    def _read_object(self, reference: Any, expected_hash: Any) -> dict[str, Any]:
        digest = str(expected_hash or "")
        if len(digest) != 64 or str(reference) != f"objects/{digest}":
            raise BrowserDataError("BROWSER_OBJECT_REFERENCE_INVALID")
        path = self.root / str(reference)
        if not _safe_regular_file(self.objects_root, path):
            raise BrowserDataError("BROWSER_OBJECT_MISSING")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise BrowserDataError("BROWSER_OBJECT_HASH_MISMATCH")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrowserDataError("BROWSER_OBJECT_JSON_INVALID") from exc
        if not isinstance(value, dict):
            raise BrowserDataError("BROWSER_OBJECT_JSON_INVALID")
        return value

    def _all_security_ids(self, connection: sqlite3.Connection) -> list[str]:
        rows = connection.execute(
            "SELECT security_id FROM fact_versions UNION SELECT security_id FROM dataset_state "
            "UNION SELECT security_id FROM research_views UNION SELECT security_id FROM reports ORDER BY security_id"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def _identity(self, connection: sqlite3.Connection, security_id: str) -> dict[str, Any]:
        ticker = None
        company_name = None
        states = connection.execute(
            "SELECT dataset,state_json FROM dataset_state WHERE security_id=? AND dataset IN ('company_profile','live_snapshot') "
            "ORDER BY CASE dataset WHEN 'company_profile' THEN 0 ELSE 1 END",
            (security_id,),
        ).fetchall()
        for row in states:
            state = _json_object(row["state_json"], "BROWSER_MEMORY_STATE_INVALID")
            try:
                value = self._read_object(state.get("object_ref"), state.get("object_hash"))
            except BrowserDataError:
                continue
            ticker = ticker or value.get("ticker")
            if row["dataset"] == "live_snapshot":
                portfolio = value.get("portfolio") if isinstance(value.get("portfolio"), Mapping) else {}
                positions = portfolio.get("positions") if isinstance(portfolio.get("positions"), list) else []
                position = next((item for item in positions if isinstance(item, Mapping) and item.get("security_id") == security_id), None)
                if position:
                    ticker = ticker or position.get("ticker") or position.get("display_symbol")
                    company_name = company_name or position.get("company_name")
            background = value.get("background") if isinstance(value.get("background"), Mapping) else {}
            for fact in background.get("evidence", []) if isinstance(background.get("evidence"), list) else []:
                if isinstance(fact, Mapping) and fact.get("semantic_field") == "company_name":
                    company_name = company_name or fact.get("value")
        row = connection.execute(
            "SELECT payload_json FROM fact_versions WHERE security_id=? AND json_extract(payload_json,'$.semantic_field')='company_name' "
            "ORDER BY published_at DESC,version_hash DESC LIMIT 1",
            (security_id,),
        ).fetchone()
        if row:
            company_name = company_name or _json_object(row[0], "BROWSER_FACT_INVALID").get("value")
        fallback = security_id.rsplit(":", 1)[-1]
        return {"security_id": security_id, "ticker": str(ticker or fallback), "company_name": str(company_name) if company_name else None}

    def _views(self, connection: sqlite3.Connection, security_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT view_manifest_hash,run_id,decision_cutoff,payload_json FROM research_views "
            "WHERE security_id=? ORDER BY decision_cutoff DESC,view_manifest_hash DESC",
            (security_id,),
        ).fetchall()
        values = []
        for row in rows:
            value = _json_object(row["payload_json"], "BROWSER_VIEW_INVALID")
            value.update(
                view_manifest_hash=row["view_manifest_hash"],
                run_id=row["run_id"],
                decision_cutoff=row["decision_cutoff"],
            )
            values.append(value)
        return values

    def _reports(self, connection: sqlite3.Connection, security_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT entry_id,report_hash,package_hash,package_ref,original_run_id,original_invocation_id,"
            "original_report_cutoff,research_status,stored_at FROM reports WHERE security_id=? "
            "ORDER BY original_report_cutoff DESC,entry_id DESC",
            (security_id,),
        ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def _latest_checks(self, connection: sqlite3.Connection, security_id: str) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
        attempts = connection.execute(
            "SELECT attempt_id,provider,dataset,scope,status,started_at,completed_at,details_json FROM attempts "
            "WHERE security_id=? ORDER BY completed_at DESC,attempt_id DESC LIMIT 100",
            (security_id,),
        ).fetchall()
        attempt_values = [
            {**{key: row[key] for key in row.keys() if key != "details_json"}, "details": _json_object(row["details_json"], "BROWSER_ATTEMPT_INVALID")}
            for row in attempts
        ]
        reuse_rows = connection.execute(
            "SELECT event_hash,checked_at,payload_json FROM reuse_events "
            "WHERE json_extract(payload_json,'$.reference.security_id')=? ORDER BY checked_at DESC,event_hash DESC",
            (security_id,),
        ).fetchall()
        reuse_values = [{"event_hash": row["event_hash"], "checked_at": row["checked_at"]} for row in reuse_rows]
        values = [str(item["completed_at"]) for item in attempt_values] + [str(item["checked_at"]) for item in reuse_values]
        return (max(values) if values else None, attempt_values, reuse_values)

    def _states(self, connection: sqlite3.Connection, security_id: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT security_id,provider,dataset,scope,policy_version,revision,last_success_at,freshness_until,watermark,"
            "coverage_json,pending_json,state_json FROM dataset_state WHERE security_id=? ORDER BY dataset,provider,scope",
            (security_id,),
        ).fetchall()
        values = []
        for row in rows:
            value = {key: row[key] for key in row.keys() if not key.endswith("_json")}
            for field in ("coverage", "pending", "state"):
                raw = row[f"{field}_json"]
                try:
                    value[field] = json.loads(raw)
                except json.JSONDecodeError:
                    value[field] = {"status": "INVALID_STORED_JSON"}
            if isinstance(value.get("state"), dict):
                value["state"] = {key: item for key, item in value["state"].items() if key not in {"object_ref", "cache_root"}}
            values.append(value)
        return values

    def _facts_for_view(
        self, connection: sqlite3.Connection, view: Mapping[str, Any] | None, security_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
        requested: list[str] = []
        if view is None:
            rows = connection.execute(
                "SELECT payload_json,logical_key,version_hash FROM fact_versions WHERE security_id=? "
                "ORDER BY published_at DESC,version_hash DESC",
                (security_id,),
            ).fetchall()
        else:
            requested = sorted({str(item) for item in view.get("selected_fact_versions", [])})
            if not requested:
                integrity = {
                    "reference_count": 0, "resolved_count": 0,
                    "missing_count": 0, "invalid_count": 0,
                    "duplicate_count": len(view.get("selected_fact_versions", [])),
                    "complete": True, "mode": "SAVED_VIEW",
                }
                return [], [], integrity
            rows = []
            for start in range(0, len(requested), 500):
                batch = requested[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                rows.extend(connection.execute(
                    f"SELECT payload_json,logical_key,version_hash FROM fact_versions WHERE security_id=? AND version_hash IN ({placeholders})",
                    [security_id, *batch],
                ).fetchall())
        values, issues = [], []
        found = {str(row["version_hash"]) for row in rows}
        for version in sorted(set(requested) - found):
            issues.append({"code": "BROWSER_VIEW_REFERENCE_MISSING", "version_hash": version})
        for row in rows:
            try:
                fact = _json_object(row["payload_json"], "BROWSER_FACT_INVALID")
                if fact_content_hash(fact) != row["version_hash"]:
                    raise BrowserDataError("BROWSER_FACT_HASH_MISMATCH")
            except (BrowserDataError, ValueError, KeyError, TypeError) as exc:
                issues.append({"code": str(exc).split(":", 1)[0], "version_hash": str(row["version_hash"])})
                continue
            fact["logical_key"] = row["logical_key"]
            fact["version_hash"] = row["version_hash"]
            fact["source_link"] = _external_link(fact.get("source_locator"))
            values.append(fact)
        invalid_count = sum(item["code"] != "BROWSER_VIEW_REFERENCE_MISSING" for item in issues)
        reference_count = len(requested) if view is not None else len(rows)
        integrity = {
            "reference_count": reference_count,
            "resolved_count": len(values),
            "missing_count": sum(item["code"] == "BROWSER_VIEW_REFERENCE_MISSING" for item in issues),
            "invalid_count": invalid_count,
            "duplicate_count": (
                len(view.get("selected_fact_versions", [])) - len(requested)
                if view is not None else 0
            ),
            "mode": "SAVED_VIEW" if view is not None else "UNFROZEN_FACT_CATALOG",
        }
        integrity["complete"] = (
            integrity["resolved_count"] == integrity["reference_count"]
            and integrity["missing_count"] == 0
            and integrity["invalid_count"] == 0
            and integrity["duplicate_count"] == 0
        )
        return sorted(values, key=lambda item: (_fact_group(item), _semantic_field(item), _period(item), str(item.get("version_hash")))), issues, integrity

    def _selected_view_facts(
        self,
        connection: sqlite3.Connection,
        views: list[dict[str, Any]],
        security_id: str,
        view_hash: str | None,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
        if not views:
            facts, issues, integrity = self._facts_for_view(connection, None, security_id)
            return None, facts, issues, integrity
        evaluated = []
        for view in views:
            facts, issues, integrity = self._facts_for_view(connection, view, security_id)
            view["integrity"] = integrity
            evaluated.append((view, facts, issues, integrity))
        if view_hash:
            selected = next((item for item in evaluated if item[0]["view_manifest_hash"] == view_hash), None)
            if selected is None:
                raise BrowserDataError("BROWSER_VIEW_NOT_FOUND")
            return selected
        return next((item for item in evaluated if item[3]["complete"]), evaluated[0])

    def _summary(self, connection: sqlite3.Connection, security_id: str) -> dict[str, Any]:
        identity = self._identity(connection, security_id)
        views = self._views(connection, security_id)
        reports = self._reports(connection, security_id)
        latest_check, attempts, _reuse = self._latest_checks(connection, security_id)
        latest_view = views[0] if views else None
        latest_report = reports[0] if reports else None
        latest_dataset_status: dict[str, str] = {}
        for item in attempts:
            latest_dataset_status.setdefault(str(item["dataset"]), str(item["status"]))
        gaps = list(latest_view.get("gaps", [])) if latest_view else []
        source_failed = any(status in FAILED_ATTEMPTS for status in latest_dataset_status.values())
        data_cutoff = latest_view.get("decision_cutoff") if latest_view else None
        report_cutoff = latest_report.get("original_report_cutoff") if latest_report else None
        return {
            **identity,
            "data_cutoff": data_cutoff,
            "latest_check": latest_check,
            "report_cutoff": report_cutoff,
            "view_count": len(views),
            "report_count": len(reports),
            "gap_count": len(gaps),
            "source_failed": source_failed,
            "no_report": not reports,
            "new_without_report": bool(data_cutoff and (not report_cutoff or str(data_cutoff) > str(report_cutoff))),
        }

    def list_companies(self, *, query: str = "", status: str = "", page: int = 1, per_page: int = PAGE_SIZE_DEFAULT) -> dict[str, Any]:
        page = _safe_int(page, default=1, minimum=1, maximum=1_000_000)
        per_page = _safe_int(per_page, default=PAGE_SIZE_DEFAULT, minimum=1, maximum=PAGE_SIZE_MAX)
        with self.connect() as connection:
            values = [self._summary(connection, security_id) for security_id in self._all_security_ids(connection)]
        needle = query.strip().casefold()
        if needle:
            values = [item for item in values if needle in " ".join(filter(None, (item["security_id"], item["ticker"], item.get("company_name")))).casefold()]
        filters = {
            "new_without_report": lambda item: item["new_without_report"],
            "gaps": lambda item: item["gap_count"] > 0,
            "source_failed": lambda item: item["source_failed"],
            "no_report": lambda item: item["no_report"],
        }
        if status in filters:
            values = [item for item in values if filters[status](item)]
        values.sort(key=lambda item: (str(item.get("data_cutoff") or item.get("latest_check") or ""), item["security_id"]), reverse=True)
        total = len(values)
        start = (page - 1) * per_page
        return {"items": values[start:start + per_page], "total": total, "page": page, "per_page": per_page}

    @staticmethod
    def _financial_metrics(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for metric_id, label, aliases in FINANCIAL_METRICS:
            candidates = [
                dict(item, period_type=_period_type(item))
                for item in facts
                if _semantic_field(item) in aliases and _numeric(item.get("value")) is not None
            ]
            deduplicated: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
            for item in candidates:
                metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
                key = (
                    str(metadata.get("period_start") or ""),
                    str(metadata.get("period_end") or item.get("as_of") or ""),
                    str(item.get("period_type")), str(item.get("unit") or ""),
                    str(item.get("currency") or ""),
                )
                rank = (
                    str(item.get("published_at") or ""),
                    str(item.get("retrieved_at") or ""),
                    str(item.get("version_hash") or ""),
                )
                current = deduplicated.get(key)
                current_rank = (
                    str(current.get("published_at") or ""),
                    str(current.get("retrieved_at") or ""),
                    str(current.get("version_hash") or ""),
                ) if current else None
                if current is None or rank > current_rank:
                    deduplicated[key] = item
            rows = sorted(
                deduplicated.values(),
                key=lambda item: (
                    _period(item),
                    str((item.get("metadata") or {}).get("period_start") or ""),
                    str(item.get("published_at") or ""),
                ),
            )
            groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for item in rows:
                groups.setdefault((
                    str(item.get("period_type")), str(item.get("unit") or ""),
                    str(item.get("currency") or ""),
                ), []).append(item)
            preferred = sorted(
                groups.items(),
                key=lambda pair: (
                    pair[0][0] == "单季", pair[0][0] == "年度", len(pair[1]),
                    max((_period(item) for item in pair[1]), default=""),
                ),
                reverse=True,
            )
            series = preferred[0][1] if preferred else []
            latest = max(
                rows,
                key=lambda item: (
                    _period(item), item.get("period_type") == "单季",
                    str(item.get("published_at") or ""),
                ),
                default=None,
            )
            models.append({
                "metric_id": metric_id, "label": label, "latest": latest,
                "rows": rows, "series": series,
                "series_status": "AVAILABLE" if len(series) >= 2 else "LIMITED",
                "series_limitation": None if len(series) >= 2 else "COMPARABLE_PERIODS_INSUFFICIENT",
            })
        return models

    @staticmethod
    def _disclosure_models(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """把已保存披露整理为事实时间线，不产生投资影响判断。"""

        def body_text(fact: Mapping[str, Any]) -> str:
            value = fact.get("value")
            if isinstance(value, str):
                return " ".join(value.split())
            if value is None:
                return ""
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

        def is_placeholder(text: str, longest: int) -> bool:
            lowered = text.casefold()
            explicit = "table of contents" in lowered or lowered.startswith("contents")
            return explicit or (longest >= 600 and len(text) <= 180 and len(text) * 3 < longest)

        def transaction_details(fact: Mapping[str, Any]) -> list[dict[str, str]]:
            value = fact.get("value") if isinstance(fact.get("value"), Mapping) else {}
            acquired_disposed = {"A": "取得", "D": "处置"}.get(
                str(value.get("acquired_disposed_code") or "").upper(),
                str(value.get("acquired_disposed_code") or "未报告"),
            )
            code = str(value.get("transaction_code") or "").upper()
            rows = [
                {"label": "交易代码", "value": f"{code or '未报告'} · {TRANSACTION_CODE_LABELS.get(code, 'SEC 未提供本地映射')}"},
                {"label": "取得/处置", "value": acquired_disposed},
                {"label": "证券", "value": str(value.get("security_title") or "未报告")},
                {"label": "数量", "value": str(value.get("shares") if value.get("shares") is not None else "未报告")},
                {"label": "每股价格", "value": str(value.get("price_per_share") if value.get("price_per_share") is not None else "未报告")},
                {"label": "交易后持有量", "value": str(value.get("post_transaction_amount") if value.get("post_transaction_amount") is not None else "未报告")},
                {"label": "持有方式", "value": str(value.get("ownership_nature") or "未报告")},
            ]
            return rows

        def transaction_excerpt(fact: Mapping[str, Any]) -> str:
            value = fact.get("value") if isinstance(fact.get("value"), Mapping) else {}
            code = str(value.get("transaction_code") or "").upper()
            direction = {"A": "取得", "D": "处置"}.get(
                str(value.get("acquired_disposed_code") or "").upper(), "交易",
            )
            pieces = [
                f"{value.get('transaction_date') or _period(fact)} 披露",
                f"代码 {code or '未报告'}（{TRANSACTION_CODE_LABELS.get(code, '未映射')}）",
                f"{direction} {value.get('shares') if value.get('shares') is not None else '未报告'} 股 {value.get('security_title') or '证券'}",
            ]
            if value.get("price_per_share") is not None:
                pieces.append(f"每股价格 {value.get('price_per_share')}")
            if value.get("post_transaction_amount") is not None:
                pieces.append(f"交易后持有 {value.get('post_transaction_amount')}")
            return "；".join(pieces) + "。"

        grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
        for fact in facts:
            field = _semantic_field(fact)
            if field not in DISCLOSURE_FIELDS:
                continue
            metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
            base = (
                field, str(fact.get("source_id") or ""), str(metadata.get("accession") or ""),
                str(metadata.get("form") or ""), _period(fact),
            )
            if field == "ownership_insider_transaction":
                base += (str(metadata.get("transaction_index") if metadata.get("transaction_index") is not None else fact.get("evidence_id") or ""),)
            grouped.setdefault(base, []).append(fact)

        models: list[dict[str, Any]] = []
        for group in grouped.values():
            unique: dict[str, Mapping[str, Any]] = {}
            exact_duplicates: dict[str, list[Mapping[str, Any]]] = {}
            for fact in sorted(
                group,
                key=lambda item: (str(item.get("published_at") or ""), str(item.get("retrieved_at") or ""), str(item.get("version_hash") or "")),
                reverse=True,
            ):
                text = body_text(fact)
                if text in unique:
                    exact_duplicates.setdefault(text, []).append(fact)
                else:
                    unique[text] = fact
                    exact_duplicates.setdefault(text, [])
            candidates = list(unique.values())
            longest = max((len(body_text(item)) for item in candidates), default=0)
            substantive = [item for item in candidates if not is_placeholder(body_text(item), longest)]
            if not substantive and candidates:
                substantive = [max(candidates, key=lambda item: len(body_text(item)))]
            collapsed = [item for item in candidates if item not in substantive]
            for index, fact in enumerate(substantive):
                field = _semantic_field(fact)
                metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
                text = body_text(fact)
                owner_name = str(metadata.get("owner_name") or "")
                title = DISCLOSURE_LABELS.get(field, field)
                if field == "ownership_insider_transaction" and owner_name:
                    title = f"{title} · {owner_name}"
                display_excerpt = transaction_excerpt(fact) if field == "ownership_insider_transaction" else text[:520] + ("…" if len(text) > 520 else "")
                folded = list(exact_duplicates.get(text, []))
                if index == 0:
                    for item in collapsed:
                        folded.append(item)
                        folded.extend(exact_duplicates.get(body_text(item), []))
                models.append({
                    "title": title,
                    "semantic_field": field,
                    "form": metadata.get("form"),
                    "period": _period(fact),
                    "published_at": fact.get("published_at"),
                    "source_id": fact.get("source_id"),
                    "source_link": fact.get("source_link"),
                    "excerpt": display_excerpt,
                    "body": text,
                    "is_excerpt": field != "ownership_insider_transaction" and len(text) > 520,
                    "transaction": transaction_details(fact) if field == "ownership_insider_transaction" else [],
                    "version_hash": fact.get("version_hash"),
                    "collapsed": [
                        {
                            "evidence_id": item.get("evidence_id"),
                            "version_hash": item.get("version_hash"),
                            "source_id": item.get("source_id"),
                            "source_link": item.get("source_link"),
                            "preview": body_text(item)[:180],
                        }
                        for item in folded
                    ],
                })
        return sorted(
            models,
            key=lambda item: (
                str(item.get("published_at") or ""), str(item.get("period") or ""),
                str(item.get("title") or ""), str(item.get("version_hash") or ""),
            ),
            reverse=True,
        )

    def company(self, security_id: str, *, view_hash: str | None = None) -> dict[str, Any]:
        with self.connect() as connection:
            if security_id not in self._all_security_ids(connection):
                raise BrowserDataError("BROWSER_COMPANY_NOT_FOUND")
            summary = self._summary(connection, security_id)
            views = self._views(connection, security_id)
            selected_view, facts, fact_issues, view_integrity = self._selected_view_facts(
                connection, views, security_id, view_hash,
            )
            reports = self._reports(connection, security_id)
            latest_check, attempts, reuse_events = self._latest_checks(connection, security_id)
            states = self._states(connection, security_id)
        groups: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            groups.setdefault(_fact_group(fact), []).append(fact)
        disclosures = self._disclosure_models(facts)
        financial_metrics = self._financial_metrics(facts) if selected_view else []
        return {
            "summary": dict(
                summary,
                data_cutoff=(selected_view or {}).get("decision_cutoff"),
            ),
            "views": views,
            "selected_view": selected_view,
            "facts": facts,
            "fact_issues": fact_issues,
            "view_integrity": view_integrity,
            "fact_groups": groups,
            "financial_metrics": financial_metrics,
            "disclosures": disclosures if selected_view else [],
            "reports": reports,
            "states": states,
            "attempts": attempts,
            "reuse_events": reuse_events,
            "latest_check": latest_check,
            "charts": self._chart_models(
                facts,
                reports,
                decision_cutoff=str(selected_view.get("decision_cutoff")) if selected_view else None,
                run_id=str(selected_view.get("run_id")) if selected_view else None,
            ) if selected_view else [],
        }

    def facts_page(
        self, security_id: str, *, view_hash: str | None = None, group: str = "",
        field: str = "", page: int = 1, per_page: int = 100,
    ) -> dict[str, Any]:
        page = _safe_int(page, default=1, minimum=1, maximum=1_000_000)
        per_page = _safe_int(per_page, default=100, minimum=1, maximum=PAGE_SIZE_MAX)
        with self.connect() as connection:
            if security_id not in self._all_security_ids(connection):
                raise BrowserDataError("BROWSER_COMPANY_NOT_FOUND")
            identity = self._identity(connection, security_id)
            views = self._views(connection, security_id)
            selected, facts, issues, integrity = self._selected_view_facts(
                connection, views, security_id, view_hash,
            )
        groups = sorted({_fact_group(item) for item in facts})
        fields = sorted({_semantic_field(item) for item in facts if not group or _fact_group(item) == group})
        if group:
            facts = [item for item in facts if _fact_group(item) == group]
        if field:
            facts = [item for item in facts if _semantic_field(item) == field]
        total = len(facts)
        start = (page - 1) * per_page
        return {
            "identity": identity, "views": views, "selected_view": selected,
            "items": facts[start:start + per_page], "issues": issues,
            "view_integrity": integrity,
            "groups": groups, "fields": fields, "group": group, "field": field,
            "page": page, "per_page": per_page, "total": total,
        }

    def _chart_models(
        self,
        facts: Sequence[Mapping[str, Any]],
        reports: Sequence[Mapping[str, Any]],
        *,
        decision_cutoff: str | None,
        run_id: str | None,
    ) -> list[dict[str, Any]]:
        visual = None
        for report in reports:
            if (
                decision_cutoff is None or run_id is None
                or str(report.get("original_report_cutoff")) != decision_cutoff
                or str(report.get("original_run_id")) != run_id
            ):
                continue
            try:
                package = self._read_object(report["package_ref"], report["package_hash"])
                attachment = package.get("attachment") if isinstance(package.get("attachment"), Mapping) else None
                if attachment:
                    validate_equity_research_package(attachment)
                    if (
                        str(attachment.get("decision_cutoff")) != decision_cutoff
                        or str(attachment.get("run_id")) != run_id
                    ):
                        continue
                    visual_entry = next((item for item in attachment["artifacts"] if item["kind"] == "visual_bundle"), None)
                    if visual_entry:
                        validate_visual_bundle(visual_entry["artifact"])
                        visual = visual_entry["artifact"]
                        break
            except (BrowserDataError, KeyError, TypeError, ValueError):
                continue
        if visual:
            return deepcopy(visual["charts"])
        fields = {_semantic_field(item) for item in facts}
        price_basis = next((field for field in ("adjusted_close_price", "historical_close_price", "close_price") if field in fields), None)
        price_rows = sorted([
            {
                "date": _period(item), "value": item.get("value"),
                "version_hash": item.get("version_hash"), "source_id": item.get("source_id"),
            }
            for item in facts if price_basis and _semantic_field(item) == price_basis
        ], key=lambda item: str(item["date"]))
        volume_rows = sorted([
            {
                "date": _period(item), "value": item.get("value"),
                "version_hash": item.get("version_hash"), "source_id": item.get("source_id"),
            }
            for item in facts if _semantic_field(item) == "share_volume"
        ], key=lambda item: str(item["date"]))
        charts = [
            {"chart_id": "price_history", "title": "价格走势", "status": "AVAILABLE" if price_rows else "LIMITED", "unit": "price", "basis": price_basis, "data": price_rows[-252:], "limitations": [] if price_rows else ["PRICE_HISTORY_UNAVAILABLE"]},
            {"chart_id": "volume_history", "title": "成交量", "status": "AVAILABLE" if volume_rows else "LIMITED", "unit": "shares", "basis": "share_volume", "data": volume_rows[-252:], "limitations": [] if volume_rows else ["VOLUME_HISTORY_UNAVAILABLE"]},
            {"chart_id": "relative_performance_drawdown", "title": "相对表现与回撤", "status": "LIMITED", "data": [], "limitations": ["BENCHMARK_ATTACHMENT_UNAVAILABLE"]},
        ]
        for metric in self._financial_metrics(facts):
            if metric["metric_id"] not in {
                "revenue", "net_income", "diluted_eps", "operating_cash_flow",
            }:
                continue
            series = metric["series"]
            charts.append({
                "chart_id": f'financial_{metric["metric_id"]}',
                "title": f'{metric["label"]}趋势',
                "status": metric["series_status"],
                "unit": (series[-1].get("unit") if series else None),
                "basis": (series[-1].get("period_type") if series else None),
                "data": [
                    {
                        "period": _period(item), "value": item.get("value"),
                        "version_hash": item.get("version_hash"),
                        "source_id": item.get("source_id"),
                    }
                    for item in series
                ] if len(series) >= 2 else [],
                "limitations": [] if len(series) >= 2 else [metric["series_limitation"]],
            })
        pe_rows = sorted([
            {"period": _period(item), "value": item.get("value"), "version_hash": item.get("version_hash")}
            for item in facts
            if any(hint in _semantic_field(item).casefold() for hint in ("trailing_pe", "price_to_earnings"))
            and _numeric(item.get("value")) is not None
        ], key=lambda item: str(item["period"]))
        charts.append({
            "chart_id": "trailing_pe_history", "title": "Trailing P/E 历史",
            "status": "AVAILABLE" if pe_rows else "LIMITED", "unit": "x",
            "data": pe_rows,
            "limitations": [] if pe_rows else ["PIT_EPS_OR_VALUATION_HISTORY_UNAVAILABLE"],
        })
        return charts

    def report(self, security_id: str, entry_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT entry_id,security_id,report_hash,package_hash,package_ref,original_run_id,original_invocation_id,"
                "original_report_cutoff,research_status,stored_at FROM reports WHERE security_id=? AND entry_id=?",
                (security_id, entry_id),
            ).fetchone()
        if row is None:
            raise BrowserDataError("BROWSER_REPORT_NOT_FOUND")
        package = self._read_object(row["package_ref"], row["package_hash"])
        report = _validated_report(
            package, security_id, str(row["report_hash"]),
            expected_run_id=str(row["original_run_id"]),
            expected_cutoff=str(row["original_report_cutoff"]),
            expected_status=str(row["research_status"]),
        )
        safe_report = _scrub_private({key: report[key] for key in REPORT_KEYS if key in report})
        return {
            "entry_id": row["entry_id"],
            "security_id": security_id,
            "report_hash": row["report_hash"],
            "original_run_id": row["original_run_id"],
            "original_invocation_id": row["original_invocation_id"],
            "original_report_cutoff": row["original_report_cutoff"],
            "research_status": row["research_status"],
            "stored_at": row["stored_at"],
            "report": deepcopy(safe_report),
            "validation": deepcopy(package.get("validation")),
        }

    def compare_views(self, security_id: str, left_hash: str, right_hash: str) -> dict[str, Any]:
        with self.connect() as connection:
            views = self._views(connection, security_id)
            indexed = {item["view_manifest_hash"]: item for item in views}
            if left_hash not in indexed or right_hash not in indexed:
                raise BrowserDataError("BROWSER_VIEW_NOT_FOUND")
            left_facts, left_issues, left_integrity = self._facts_for_view(connection, indexed[left_hash], security_id)
            right_facts, right_issues, right_integrity = self._facts_for_view(connection, indexed[right_hash], security_id)
        left = {str(item["logical_key"]): item for item in left_facts}
        right = {str(item["logical_key"]): item for item in right_facts}
        changes = []
        for key in sorted(set(left) | set(right)):
            before, after = left.get(key), right.get(key)
            if before and after:
                status = "UNCHANGED" if before["version_hash"] == after["version_hash"] else "REVISED"
                sample = after
            elif after:
                status, sample = "RIGHT_ONLY", after
            else:
                status, sample = "LEFT_ONLY", before
            changes.append({"logical_key": key, "group": _fact_group(sample or {}), "status": status, "before": before, "after": after})
        return {
            "security_id": security_id, "left": indexed[left_hash], "right": indexed[right_hash],
            "changes": changes, "issues": left_issues + right_issues,
            "comparison_status": (
                "COMPLETE" if left_integrity["complete"] and right_integrity["complete"]
                else "INCOMPLETE_VIEW_REFERENCES"
            ),
            "left_integrity": left_integrity, "right_integrity": right_integrity,
        }

    def diagnostic(self) -> dict[str, Any]:
        companies = self.list_companies(per_page=PAGE_SIZE_MAX)
        return {"status": "READY", "memory_schema_version": SUPPORTED_MEMORY_VERSION, "company_count": companies["total"]}


class ArtifactCatalog:
    """对显式运行目录做有界、可重复的只读扫描。"""

    def __init__(self, *, run_dirs: Sequence[Path] = (), run_roots: Sequence[Path] = ()):
        self._configured_dirs = tuple(Path(item).expanduser() for item in run_dirs)
        self._configured_roots = tuple(Path(item).expanduser() for item in run_roots)
        self._source_contexts: dict[str, dict[str, str | None]] = {}
        self.artifacts: list[dict[str, Any]] = []
        self.issues: list[dict[str, str]] = []
        self.rescan()

    @staticmethod
    def _accepted_directory(path: Path, *, exact: bool) -> Path | None:
        if path.is_symlink() or not path.is_dir():
            return None
        resolved = path.resolve()
        if exact:
            known = any((resolved / name).is_file() for name in (*KNOWN_RUN_MARKERS, *KNOWN_DIRECT_ARTIFACTS))
            known = known or (resolved / "evidence/source-package").is_dir() or (resolved / "research").is_dir()
        else:
            known = any((resolved / name).is_file() for name in KNOWN_RUN_MARKERS)
        return resolved if known else None

    def _directories(self) -> list[Path]:
        values: set[Path] = set()
        for raw in self._configured_dirs:
            accepted = self._accepted_directory(raw, exact=True)
            if accepted:
                values.add(accepted)
            else:
                self.issues.append({"code": "ARTIFACT_RUN_DIR_UNAVAILABLE", "label": raw.name or "run-dir"})
        for raw in self._configured_roots:
            if raw.is_symlink() or not raw.is_dir():
                self.issues.append({"code": "ARTIFACT_RUN_ROOT_UNAVAILABLE", "label": raw.name or "run-root"})
                continue
            for child in raw.iterdir():
                accepted = self._accepted_directory(child, exact=False)
                if accepted:
                    values.add(accepted)
        return sorted(values, key=str)

    @staticmethod
    def _candidates(root: Path) -> Iterable[Path]:
        fixed = [
            *(root / name for name in KNOWN_DIRECT_ARTIFACTS),
            *(root / "evidence/source-package" / name for name in KNOWN_DIRECT_ARTIFACTS),
        ]
        for path in fixed:
            if _safe_regular_file(root, path):
                yield path
        for pattern in (
            "research/precomputed/*/market-state-calculation.json",
            "research/reports/*/dimension-report.json",
            "research/supplements/*/dimension-report.json",
            "research/equity-attachments/*.json",
        ):
            for path in root.glob(pattern):
                if _safe_regular_file(root, path):
                    yield path

    @staticmethod
    def _identity(value: Mapping[str, Any], digest: str) -> tuple[str, str]:
        schema = str(value.get("schema_version", "UNKNOWN"))
        identifier = next((str(value[key]) for key in (
            "snapshot_hash", "artifact_hash", "report_hash", "package_hash", "bundle_hash",
            "report_id", "package_id", "snapshot_id", "artifact_id",
        ) if value.get(key)), digest)
        return schema, identifier

    @staticmethod
    def _source_id(root: Path) -> str:
        return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()

    @classmethod
    def _source_context(cls, root: Path) -> dict[str, str | None]:
        context: dict[str, str | None] = {
            "source_id": cls._source_id(root), "run_id": None, "decision_cutoff": None,
        }
        for name in KNOWN_RUN_MARKERS:
            path = root / name
            if not _safe_regular_file(root, path):
                continue
            try:
                value = json.loads(path.read_bytes())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, Mapping):
                continue
            execution = value.get("execution") if isinstance(value.get("execution"), Mapping) else {}
            context["run_id"] = str(value.get("run_id") or execution.get("run_id") or "") or None
            context["decision_cutoff"] = str(
                value.get("decision_cutoff") or value.get("as_of") or execution.get("decision_cutoff") or ""
            ) or None
            if context["run_id"] or context["decision_cutoff"]:
                break
        return context

    @staticmethod
    def _kind(value: Mapping[str, Any]) -> tuple[str, bool]:
        schema = str(value.get("schema_version", ""))
        supported = {
            "official-macro-snapshot/1.0.0": "macro_snapshot",
            "official-macro-snapshot/1.1.0": "macro_snapshot",
            "market-context-snapshot/1.0.0": "market_context_snapshot",
            "benchmark-research-snapshot/1.0.0": "benchmark_snapshot",
            "market-state-calculation/1.0.0": "market_calculation",
            "research-dimension-report/1.1.0": "dimension_report",
            "research-dimension-report/2.0.0": "dimension_report",
            "equity-research-attachments/1.0.0": "equity_attachment",
        }
        return supported.get(schema, "unsupported"), schema in supported

    @staticmethod
    def _validate(value: Mapping[str, Any], kind: str) -> None:
        if kind == "dimension_report":
            validate_research_dimension_report(
                value,
                expected_bindings=value.get("bindings", {}),
                allowed_security_ids=value.get("security_ids", []),
                allowed_evidence_ids=sorted(
                    _string_refs(value, "evidence_refs") | _string_refs(value, "input_evidence_refs")
                ),
                known_research_claim_ids=(),
                allowed_documents=value.get("documents", []),
            )
        elif kind == "equity_attachment":
            validate_equity_research_package(value)
        elif kind == "market_calculation":
            if value.get("artifact_hash") != canonical_hash({key: item for key, item in value.items() if key != "artifact_hash"}):
                raise ValueError("MARKET_CALCULATION_HASH_MISMATCH")
        elif kind == "macro_snapshot":
            if value.get("snapshot_hash") != canonical_hash({key: item for key, item in value.items() if key != "snapshot_hash"}):
                # Macro uses content_hash with the same canonical JSON hashing semantics.
                raise ValueError("MACRO_SNAPSHOT_HASH_MISMATCH")
        elif kind == "market_context_snapshot":
            if value.get("snapshot_hash") != canonical_hash({key: item for key, item in value.items() if key != "snapshot_hash"}):
                raise ValueError("MARKET_CONTEXT_SNAPSHOT_HASH_MISMATCH")
        elif kind == "benchmark_snapshot":
            if value.get("snapshot_hash") != canonical_hash({key: item for key, item in value.items() if key != "snapshot_hash"}):
                raise ValueError("BENCHMARK_SNAPSHOT_HASH_MISMATCH")

    def rescan(self) -> dict[str, int]:
        self.artifacts = []
        self.issues = []
        self._source_contexts = {}
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for root in self._directories():
            context = self._source_context(root)
            source_id = str(context["source_id"])
            self._source_contexts[source_id] = context
            for path in self._candidates(root):
                try:
                    raw = path.read_bytes()
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ValueError("NOT_OBJECT")
                    digest = hashlib.sha256(raw).hexdigest()
                    kind, supported = self._kind(value)
                    if supported:
                        self._validate(value, kind)
                    identity = self._identity(value, digest)
                    item = {
                        "kind": kind, "schema_version": str(value.get("schema_version", "UNKNOWN")),
                        "identity": identity[1], "content_hash": digest, "supported": supported,
                        "value": value, "source_label": root.name,
                        "source_ids": [source_id], "source_labels": [root.name],
                    }
                    if kind in {"macro_snapshot", "market_context_snapshot", "equity_attachment"}:
                        self._source_contexts[source_id]["decision_cutoff"] = str(
                            self._source_contexts[source_id].get("decision_cutoff") or value.get("decision_cutoff") or ""
                        ) or None
                    if (
                        kind == "equity_attachment" and value.get("run_id")
                        and not self._source_contexts[source_id].get("run_id")
                    ):
                        self._source_contexts[source_id]["run_id"] = str(value["run_id"])
                    if not supported:
                        self.issues.append({
                            "code": "ARTIFACT_SCHEMA_UNSUPPORTED",
                            "label": f"{item['schema_version']}:{item['identity']}",
                        })
                    grouped.setdefault(identity, []).append(item)
                except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
                    self.issues.append({"code": str(exc).split(":", 1)[0], "label": path.name})
        for identity, items in sorted(grouped.items()):
            unique: dict[str, dict[str, Any]] = {}
            for item in items:
                digest = str(item["content_hash"])
                if digest not in unique:
                    unique[digest] = item
                    continue
                unique[digest]["source_ids"] = sorted(set(unique[digest]["source_ids"]) | set(item["source_ids"]))
                unique[digest]["source_labels"] = sorted(set(unique[digest]["source_labels"]) | set(item["source_labels"]))
            if len(unique) == 1:
                self.artifacts.append(next(iter(unique.values())))
            else:
                self.issues.append({"code": "ARTIFACT_IDENTITY_CONTENT_CONFLICT", "label": f"{identity[0]}:{identity[1]}"})
        self.artifacts.sort(key=lambda item: (item["kind"], item["identity"], item["content_hash"]))
        return {"artifact_count": len(self.artifacts), "issue_count": len(self.issues)}

    def by_kind(self, *kinds: str) -> list[dict[str, Any]]:
        selected = set(kinds)
        return [item for item in self.artifacts if item["kind"] in selected]

    def company_visuals(
        self, security_id: str, decision_cutoff: str | None, run_id: str | None,
    ) -> dict[str, Any] | None:
        """选择与已保存 Company View 精确绑定的冻结图形附件。"""
        if not decision_cutoff or not run_id:
            return None
        candidates: list[dict[str, Any]] = []
        for item in self.by_kind("equity_attachment"):
            package = item["value"]
            if (
                package.get("security_id") != security_id
                or package.get("decision_cutoff") != decision_cutoff
                or package.get("run_id") != run_id
            ):
                continue
            visual_entry = next(
                (entry for entry in package.get("artifacts", []) if entry.get("kind") == "visual_bundle"),
                None,
            )
            if not visual_entry or not isinstance(visual_entry.get("artifact"), Mapping):
                continue
            visual = visual_entry["artifact"]
            try:
                validate_visual_bundle(visual)
            except (KeyError, TypeError, ValueError):
                continue
            if (
                visual.get("security_id") != security_id
                or visual.get("decision_cutoff") != decision_cutoff
                or visual.get("run_id") != run_id
            ):
                continue
            candidates.append({"package": package, "visual": visual})
        if not candidates:
            return None
        by_bundle = {str(item["visual"].get("bundle_hash")): item for item in candidates}
        if len(by_bundle) != 1:
            return {
                "status": "CONFLICT",
                "code": "COMPANY_VISUAL_ATTACHMENT_CONFLICT",
                "decision_cutoff": decision_cutoff,
            }
        selected = next(iter(by_bundle.values()))
        package, visual = selected["package"], selected["visual"]
        return {
            "status": "AVAILABLE",
            "package_id": package.get("package_id"),
            "package_hash": package.get("package_hash"),
            "run_id": package.get("run_id"),
            "decision_cutoff": package.get("decision_cutoff"),
            "bundle_id": visual.get("bundle_id"),
            "bundle_hash": visual.get("bundle_hash"),
            "charts": deepcopy(visual["charts"]),
        }

    @staticmethod
    def _artifact_time(item: Mapping[str, Any]) -> str:
        value = item.get("value") if isinstance(item.get("value"), Mapping) else {}
        direct = value.get("decision_cutoff") or value.get("as_of")
        if direct:
            return str(direct)
        evidence = value.get("evidence") if isinstance(value.get("evidence"), list) else []
        return max((str(fact.get("as_of") or "") for fact in evidence if isinstance(fact, Mapping)), default="")

    @classmethod
    def _select_artifact(
        cls, items: Sequence[Mapping[str, Any]], identity: str | None,
    ) -> dict[str, Any] | None:
        ordered = sorted(items, key=lambda item: (cls._artifact_time(item), str(item.get("content_hash"))), reverse=True)
        if identity:
            return next((dict(item) for item in ordered if item.get("content_hash") == identity), None)
        return dict(ordered[0]) if ordered else None

    @staticmethod
    def _shared_sources(left: Mapping[str, Any], right: Mapping[str, Any]) -> set[str]:
        return set(str(item) for item in left.get("source_ids", [])) & set(
            str(item) for item in right.get("source_ids", [])
        )

    def _report_matches(
        self, report: Mapping[str, Any], selected: Mapping[str, Any], *, selected_cutoff: str | None,
    ) -> bool:
        value = report.get("value") if isinstance(report.get("value"), Mapping) else {}
        bindings = value.get("bindings") if isinstance(value.get("bindings"), Mapping) else {}
        report_cutoff = str(bindings.get("decision_cutoff") or "")
        report_run = str(value.get("run_id") or "")
        for source_id in self._shared_sources(report, selected):
            context = self._source_contexts.get(source_id, {})
            expected_cutoff = str(context.get("decision_cutoff") or selected_cutoff or "")
            expected_run = str(context.get("run_id") or "")
            if not expected_cutoff or report_cutoff != expected_cutoff:
                continue
            if expected_run and report_run != expected_run:
                continue
            return True
        return False

    def _calculation_matches(
        self, calculation: Mapping[str, Any], selected: Mapping[str, Any],
    ) -> bool:
        if not self._shared_sources(calculation, selected):
            return False
        value = calculation.get("value") if isinstance(calculation.get("value"), Mapping) else {}
        snapshot = selected.get("value") if isinstance(selected.get("value"), Mapping) else {}
        if value.get("market_id") != snapshot.get("benchmark_id"):
            return False
        if self._artifact_time(calculation) > self._artifact_time(selected):
            return False
        allowed_refs = {
            str(fact.get("evidence_id") or fact.get("fact_id"))
            for fact in snapshot.get("evidence", []) if isinstance(fact, Mapping)
            and (fact.get("evidence_id") or fact.get("fact_id"))
        }
        required_refs = {
            str(item) for item in value.get("evidence_fact_ids", [])
            if isinstance(item, (str, int))
        }
        if not required_refs <= allowed_refs:
            return False
        for source_id in self._shared_sources(calculation, selected):
            context = self._source_contexts.get(source_id, {})
            expected_run = str(context.get("run_id") or "")
            if expected_run and value.get("run_id") and str(value.get("run_id")) != expected_run:
                continue
            return True
        return False

    def company_reports(
        self, security_id: str, decision_cutoff: str | None, run_id: str | None,
        allowed_evidence_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        """返回与当前公司 View 精确绑定的既有多维报告及逐能力空状态。"""

        entries: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []
        reports = self.by_kind("dimension_report")
        for capability in COMPANY_RESEARCH_CAPABILITIES:
            candidates = [
                item for item in reports
                if item["value"].get("capability") == capability
                and security_id in item["value"].get("security_ids", [])
            ]
            matches = []
            for item in candidates:
                value = item["value"]
                bindings = value.get("bindings") if isinstance(value.get("bindings"), Mapping) else {}
                source_bound = any(
                    self._source_contexts.get(source_id, {}).get("run_id") == run_id
                    and self._source_contexts.get(source_id, {}).get("decision_cutoff") == decision_cutoff
                    for source_id in item.get("source_ids", [])
                )
                if not (
                    decision_cutoff and run_id and source_bound
                    and value.get("run_id") == run_id
                    and bindings.get("decision_cutoff") == decision_cutoff
                ):
                    continue
                try:
                    validate_research_dimension_report(
                        value,
                        expected_bindings=bindings,
                        allowed_security_ids=[security_id],
                        allowed_evidence_ids=sorted(set(allowed_evidence_ids)),
                        known_research_claim_ids=(),
                        allowed_documents=value.get("documents", []),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                matches.append(deepcopy(item))
            if matches:
                entries.append({
                    "capability": capability, "status": "AVAILABLE",
                    "reports": sorted(
                        matches,
                        key=lambda item: (str(item["value"].get("report_id") or ""), str(item.get("content_hash") or "")),
                    ),
                })
            elif candidates:
                entries.append({
                    "capability": capability, "status": "BINDING_FAILED", "reports": [],
                    "code": "COMPANY_DIMENSION_REPORT_BINDING_MISMATCH",
                })
                issues.append({
                    "code": "ARTIFACT_BINDING_MISMATCH",
                    "label": f"{security_id}:{capability}",
                })
            else:
                entries.append({
                    "capability": capability, "status": "NOT_GENERATED", "reports": [],
                })
        return {"items": entries, "issues": issues}

    def macro(self, identity: str | None = None) -> dict[str, Any]:
        snapshots = self.by_kind("macro_snapshot")
        selected = self._select_artifact(snapshots, identity)
        candidates = [
            item for item in self.by_kind("dimension_report")
            if item["value"].get("capability") in {"MACRO_CONTEXT", "MACRO_MARKET"}
        ]
        reports = [
            item for item in candidates if selected is not None and self._report_matches(
                item, selected, selected_cutoff=str(selected["value"].get("decision_cutoff") or "") or None,
            )
        ]
        reports = [
            {
                **item,
                "coverage_label": (
                    "LEGACY_COMBINED_COVERAGE"
                    if item["value"].get("capability") == "MACRO_MARKET"
                    else "MACRO_CONTEXT"
                ),
            }
            for item in reports
        ]
        issues = deepcopy(self.issues)
        if selected is not None and len(reports) != len(candidates):
            issues.append({"code": "ARTIFACT_BINDING_MISMATCH", "label": "macro-report"})
        return {"snapshots": snapshots, "selected": selected, "reports": reports, "issues": issues}

    def market(self, identity: str | None = None) -> dict[str, Any]:
        snapshots = self.by_kind("benchmark_snapshot")
        selected = self._select_artifact(snapshots, identity)
        calculation_candidates = self.by_kind("market_calculation")
        calculations = [item for item in calculation_candidates if selected is not None and self._calculation_matches(item, selected)]
        report_candidates = [
            item for item in self.by_kind("dimension_report")
            if item["value"].get("capability") in {"MARKET_STATE", "MACRO_MARKET"}
        ]
        reports = [
            item for item in report_candidates if selected is not None and self._report_matches(
                item, selected, selected_cutoff=None,
            )
        ]
        reports = [
            {
                **item,
                "coverage_label": (
                    "LEGACY_COMBINED_COVERAGE"
                    if item["value"].get("capability") == "MACRO_MARKET"
                    else "MARKET_STATE"
                ),
            }
            for item in reports
        ]
        issues = deepcopy(self.issues)
        if selected is not None and len(calculations) != len(calculation_candidates):
            issues.append({"code": "ARTIFACT_BINDING_MISMATCH", "label": "market-calculation"})
        if selected is not None and len(reports) != len(report_candidates):
            issues.append({"code": "ARTIFACT_BINDING_MISMATCH", "label": "market-report"})
        return {"snapshots": snapshots, "selected": selected, "calculations": calculations, "reports": reports, "issues": issues}

    def diagnostic(self) -> dict[str, Any]:
        return {"status": "READY", "artifact_count": len(self.artifacts), "issue_count": len(self.issues)}
