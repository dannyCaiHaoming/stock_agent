"""SEC 基本面补充的有界选择与确定性标准化；不做主观评分。"""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash


ADAPTER_VERSION = "company-fundamental-supplement/1.0.0"
DOCUMENT_BUDGET = {
    "annual": 2, "quarterly": 4, "earnings_releases": 4,
    "proxy": 2, "other_8k": 8, "total": 32,
}
FINANCIAL_TAG_PRIORITY = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
    "net_income": ("NetIncomeLoss",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"),
    "sbc": ("ShareBasedCompensation", "StockBasedCompensation"),
    "shares_outstanding": ("CommonStockSharesOutstanding",),
    "weighted_diluted_shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "assets": ("Assets",), "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "common_equity": ("StockholdersEquity",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "cash_and_restricted_cash": ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",),
    "receivables": ("AccountsReceivableNetCurrent",), "inventory": ("InventoryNet",),
    "interest_expense": ("InterestExpenseNonOperating", "InterestExpense"),
    "repurchases": ("PaymentsForRepurchaseOfCommonStock",),
    "dividends": ("PaymentsOfDividends",),
}
DEBT_BUCKET_TAGS = {
    "next_12_months": "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
    "year_2": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
    "year_3": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
    "year_4": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
    "year_5": "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
    "after_year_5": "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
}


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"FUNDAMENTAL_NUMBER_INVALID:{name}") from exc
    if not result.is_finite():
        raise ValueError(f"FUNDAMENTAL_NUMBER_INVALID:{name}")
    return result


def select_disclosure_documents(
    documents: Sequence[Mapping[str, Any]], *, decision_cutoff: str,
) -> dict[str, Any]:
    """按表单类别选择最新且去重的申报，预算截断不等于未披露。"""

    cutoff = parse_timestamp(decision_cutoff)
    categories: dict[str, list[dict[str, Any]]] = {name: [] for name in DOCUMENT_BUDGET if name != "total"}
    seen: set[str] = set()
    rejected: list[dict[str, str]] = []
    for source in documents:
        item = deepcopy(dict(source))
        accession = item.get("accession")
        published_at = item.get("published_at")
        if not isinstance(accession, str) or not isinstance(published_at, str):
            rejected.append({"accession": str(accession), "reason": "IDENTITY_OR_TIME_MISSING"})
            continue
        if accession in seen:
            continue
        seen.add(accession)
        published = parse_timestamp(published_at)
        if published > cutoff:
            rejected.append({"accession": accession, "reason": "AFTER_CUTOFF"})
            continue
        form = str(item.get("form", "")).removesuffix("/A")
        if form == "10-K":
            category = "annual"
        elif form == "10-Q":
            category = "quarterly"
        elif form in {"DEF 14A", "DEF 14C"}:
            category = "proxy"
        elif form == "8-K" and item.get("is_earnings_release") is True:
            category = "earnings_releases"
        elif form == "8-K" and cutoff - published <= timedelta(days=366):
            category = "other_8k"
        else:
            rejected.append({"accession": accession, "reason": "FORM_OR_WINDOW_NOT_SELECTED"})
            continue
        categories[category].append(item)
    selected: list[dict[str, Any]] = []
    omitted: dict[str, int] = {}
    status: dict[str, str] = {}
    for category, rows in categories.items():
        rows.sort(key=lambda item: (item["published_at"], item["accession"]), reverse=True)
        accepted = rows[:DOCUMENT_BUDGET[category]]
        selected.extend(accepted)
        omitted[category] = max(0, len(rows) - len(accepted))
        if omitted[category]:
            status[category] = "BUDGET_TRUNCATED"
        elif accepted:
            status[category] = "DOCUMENTS_SELECTED"
        else:
            status[category] = "NO_DOCUMENT_FOUND_IN_BOUNDED_SEARCH"
    selected.sort(key=lambda item: (item["published_at"], item["accession"]), reverse=True)
    if len(selected) > DOCUMENT_BUDGET["total"]:
        overflow = selected[DOCUMENT_BUDGET["total"]:]
        selected = selected[:DOCUMENT_BUDGET["total"]]
        for item in overflow:
            rejected.append({"accession": item["accession"], "reason": "TOTAL_BUDGET_TRUNCATED"})
    return {
        "adapter_version": ADAPTER_VERSION,
        "decision_cutoff": iso_utc(decision_cutoff),
        "budget": dict(DOCUMENT_BUDGET), "selected": selected,
        "selected_accessions": [item["accession"] for item in selected],
        "category_status": status, "omitted_counts": omitted,
        "rejected": rejected,
        "coverage_limitation": "NO_DOCUMENT_FOUND_IN_BOUNDED_SEARCH_DOES_NOT_PROVE_NOT_DISCLOSED",
    }


def normalize_financial_fields(facts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """按同期间同单位选择标准字段；同义标签不得重复加总。"""

    normalized, conflicts, missing = [], [], []
    for semantic_field, priority in FINANCIAL_TAG_PRIORITY.items():
        candidates = [dict(item) for item in facts if item.get("metadata", {}).get("tag") in priority]
        if not candidates:
            missing.append(semantic_field)
            continue
        by_context: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for item in candidates:
            metadata = item.get("metadata", {})
            key = (
                metadata.get("period_start"), metadata.get("period_end"),
                item.get("unit") or metadata.get("unit"), metadata.get("context_type"),
            )
            by_context.setdefault(key, []).append(item)
        for key, rows in sorted(by_context.items(), key=lambda pair: repr(pair[0])):
            values = {str(item.get("value")) for item in rows}
            if len(values) > 1:
                conflicts.append({
                    "semantic_field": semantic_field, "context": list(key),
                    "evidence_refs": sorted(item["evidence_id"] for item in rows),
                    "reason": "ALTERNATIVE_TAG_VALUES_CONFLICT",
                })
                continue
            rows.sort(key=lambda item: (priority.index(item["metadata"]["tag"]), item["evidence_id"]))
            chosen = rows[0]
            normalized.append({
                "semantic_field": semantic_field, "value": str(chosen["value"]),
                "unit": chosen.get("unit") or chosen["metadata"].get("unit"),
                "period_start": chosen["metadata"].get("period_start"),
                "period_end": chosen["metadata"].get("period_end"),
                "context_type": chosen["metadata"].get("context_type"),
                "source_tag": chosen["metadata"]["tag"],
                "evidence_refs": sorted(item["evidence_id"] for item in rows),
                "alternative_tags_deduplicated": sorted({item["metadata"]["tag"] for item in rows}),
            })
    return {"adapter_version": ADAPTER_VERSION, "fields": normalized, "conflicts": conflicts, "missing_fields": missing}


def verified_disclosure_item(
    candidate: Mapping[str, Any], *, item_id: str, definition: str,
    period: str | None, unit: str | None, review_evidence_refs: Sequence[str],
    effective_at: str | None = None,
) -> dict[str, Any]:
    """只有带原文定位和显式核实引用的候选才能提升为事实。"""

    value = candidate.get("value") if isinstance(candidate.get("value"), Mapping) else candidate
    locator = {
        "accession": value.get("accession"), "section": value.get("section"),
        "raw_character_spans": value.get("raw_character_spans"),
    }
    if not locator["accession"] or not locator["section"] or not locator["raw_character_spans"]:
        raise ValueError("FUNDAMENTAL_DISCLOSURE_LOCATOR_MISSING")
    refs = sorted(set(candidate.get("evidence_refs", [candidate.get("evidence_id")])) | set(review_evidence_refs))
    if any(not isinstance(item, str) or not item for item in refs) or len(refs) < 2:
        raise ValueError("FUNDAMENTAL_REVIEW_EVIDENCE_MISSING")
    return {
        "item_id": item_id, "claim_status": "VERIFIED_FACT",
        "source_id": candidate["source_id"], "as_of": iso_utc(candidate["as_of"]),
        "retrieved_at": iso_utc(candidate["retrieved_at"]),
        "published_at": iso_utc(candidate["published_at"]) if candidate.get("published_at") else None,
        "effective_at": iso_utc(effective_at) if effective_at else None,
        "period": period, "definition": definition, "unit": unit,
        "source_locator": candidate.get("source_locator"), "text_locator": locator,
        "evidence_refs": refs, "calculation_ref": None,
    }


def build_debt_liquidity_record(
    *, facts: Sequence[Mapping[str, Any]], carrying_debt: Any | None,
    unrestricted_cash: Any | None, restricted_cash: Any | None,
    lease_scope: str, principal_scope: str,
) -> dict[str, Any]:
    by_tag: dict[str, Mapping[str, Any]] = {}
    for item in facts:
        tag = item.get("metadata", {}).get("tag")
        if tag in DEBT_BUCKET_TAGS.values() and tag not in by_tag:
            by_tag[tag] = item
    buckets = []
    for bucket, tag in DEBT_BUCKET_TAGS.items():
        item = by_tag.get(tag)
        if item is not None:
            buckets.append({
                "bucket": bucket, "amount": format(_decimal(item["value"], tag), "f"),
                "unit": item.get("unit") or item.get("metadata", {}).get("unit"),
                "evidence_refs": [item["evidence_id"]],
            })
    principal = sum((_decimal(item["amount"], "bucket.amount") for item in buckets), Decimal(0))
    carrying = _decimal(carrying_debt, "carrying_debt") if carrying_debt is not None else None
    difference = principal - carrying if carrying is not None else None
    return {
        "buckets": buckets, "principal_total": format(principal, "f"),
        "carrying_debt": format(carrying, "f") if carrying is not None else None,
        "unexplained_difference": format(difference, "f") if difference is not None else None,
        "reconciliation_status": (
            "NOT_AVAILABLE" if carrying is None else
            "RECONCILED" if difference == 0 else "UNEXPLAINED_DIFFERENCE"
        ),
        "unrestricted_cash": format(_decimal(unrestricted_cash, "unrestricted_cash"), "f") if unrestricted_cash is not None else None,
        "restricted_cash": format(_decimal(restricted_cash, "restricted_cash"), "f") if restricted_cash is not None else None,
        "lease_scope": lease_scope, "principal_scope": principal_scope,
        "limitations": [
            "受限现金未从债务中自动抵扣",
            "期限表本金与账面债务差异未被强制分配到期限桶",
        ],
    }


def build_operating_kpi_item(
    *, item_id: str, name: str, value: Any, unit: str, period: str,
    definition: str, definition_version: str, scope: str,
    source_id: str, as_of: str, published_at: str, retrieved_at: str,
    evidence_refs: Sequence[str], anonymous_counterparty: bool = False,
) -> dict[str, Any]:
    if not all((name, unit, period, definition, definition_version, scope, source_id)):
        raise ValueError("OPERATING_KPI_DEFINITION_INCOMPLETE")
    return {
        "item_id": item_id, "claim_status": "VERIFIED_FACT", "name": name,
        "value": format(_decimal(value, "kpi.value"), "f"), "unit": unit,
        "period": period, "definition": definition,
        "definition_version": definition_version, "scope": scope,
        "anonymous_counterparty": anonymous_counterparty,
        "source_id": source_id, "as_of": iso_utc(as_of),
        "published_at": iso_utc(published_at), "retrieved_at": iso_utc(retrieved_at),
        "evidence_refs": sorted(set(evidence_refs)), "calculation_ref": None,
    }


def build_actual_expectation_record(
    *, provider_reported: Mapping[str, Any], comparison: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if comparison is None:
        return {
            "status": "PROVIDER_REPORTED_UNVERIFIED", "comparison": None,
            "reason": "PRE_ANNOUNCEMENT_VINTAGE_NOT_VERIFIED",
            "provider_snapshot": deepcopy(dict(provider_reported)),
        }
    parents = comparison.get("parent_ids")
    if not isinstance(parents, list) or len(parents) != 2:
        raise ValueError("EXPECTATION_COMPARISON_LINEAGE_INVALID")
    return {
        "status": "VERIFIED_COMPARISON", "comparison": deepcopy(dict(comparison)),
        "reason": None, "provider_snapshot": deepcopy(dict(provider_reported)),
    }


def build_earnings_quality_record(
    *, stock_based_compensation: Mapping[str, Any] | None,
    repurchases: Mapping[str, Any] | None,
    actual_shares_outstanding: Mapping[str, Any] | None,
    weighted_average_diluted_shares: Mapping[str, Any] | None,
    gaap_reconciliation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """分列资本分配与股数事实；金额不被确定性解释成净稀释。"""

    def normalize(item: Mapping[str, Any] | None, *, kind: str) -> dict[str, Any] | None:
        if item is None:
            return None
        required = {"value", "unit", "period", "evidence_refs"}
        if not required <= set(item) or not item.get("evidence_refs"):
            raise ValueError(f"EARNINGS_QUALITY_INPUT_INCOMPLETE:{kind}")
        return {
            "kind": kind, "value": format(_decimal(item["value"], kind), "f"),
            "unit": item["unit"], "period": item["period"],
            "evidence_refs": sorted(set(item["evidence_refs"])),
        }

    actual = normalize(actual_shares_outstanding, kind="ACTUAL_PERIOD_END_SHARES")
    weighted = normalize(weighted_average_diluted_shares, kind="WEIGHTED_AVERAGE_DILUTED_SHARES")
    if actual and weighted and actual["unit"] != weighted["unit"]:
        raise ValueError("EARNINGS_QUALITY_SHARE_UNIT_MISMATCH")
    return {
        "stock_based_compensation": normalize(stock_based_compensation, kind="SBC_EXPENSE"),
        "repurchases": normalize(repurchases, kind="CASH_PAID_FOR_REPURCHASES"),
        "actual_shares_outstanding": actual,
        "weighted_average_diluted_shares": weighted,
        "gaap_reconciliation": deepcopy(dict(gaap_reconciliation)) if gaap_reconciliation else None,
        "net_dilution": None,
        "limitations": [
            "SBC 与回购金额不构成净稀释计算",
            "期末实际股数与加权平均稀释股数用途不同，保持分列",
            "税前与税后调节项只按已核实桥接的符号和税基呈现",
        ],
    }
