"""可复算的普通股估值、PIT 历史和基本面比率；不产生投资判断。"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.hashing import canonical_hash


SNAPSHOT_VERSION = "equity-valuation-snapshot/1.0.0"
HISTORY_VERSION = "equity-valuation-history/1.0.0"
FUNDAMENTAL_VERSION = "company-fundamental-supplement/1.0.0"
PEER_VERSION = "peer-comparison/1.0.0"
FUNDAMENTAL_GROUPS = (
    "guidance", "earnings_quality", "debt_liquidity", "operating_kpis",
    "governance", "earnings_expectations", "financial_ratios",
)
METRIC_NAMES = {
    "trailing_pe", "forward_pe", "price_to_sales", "price_to_book",
    "fcf_yield", "enterprise_value", "ev_to_ebitda",
}
METRIC_STATUSES = {
    "AVAILABLE", "NOT_APPLICABLE", "INPUT_MISSING", "BASIS_UNKNOWN",
    "CONFLICT", "SOURCE_UNSUPPORTED",
}


class EquityValuationError(ValueError):
    pass


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EquityValuationError(f"VALUATION_NUMBER_INVALID:{name}") from exc
    if not result.is_finite():
        raise EquityValuationError(f"VALUATION_NUMBER_INVALID:{name}")
    return result


def _hash_without(value: Mapping[str, Any], field: str = "artifact_hash") -> str:
    return canonical_hash({key: item for key, item in value.items() if key != field})


def _require_time(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EquityValuationError(f"VALUATION_TIME_MISSING:{name}")
    try:
        return parse_timestamp(value)
    except (TypeError, ValueError) as exc:
        raise EquityValuationError(f"VALUATION_TIME_INVALID:{name}") from exc


def _canonical_ids(values: Any, name: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(item, str) or not item for item in values):
        raise EquityValuationError(f"VALUATION_IDS_INVALID:{name}")
    if len(values) != len(set(values)) or values != sorted(values):
        raise EquityValuationError(f"VALUATION_IDS_NOT_CANONICAL:{name}")
    if not allow_empty and not values:
        raise EquityValuationError(f"VALUATION_IDS_EMPTY:{name}")
    return values


def build_metric(
    *, name: str, origin: str, value: Any | None, status: str,
    source_id: str, as_of: str, retrieved_at: str,
    evidence_refs: Sequence[str], unit: str = "ratio", currency: str | None = None,
    reason: str | None = None, price_at: str | None = None,
    financial_period: str | None = None, fiscal_basis: str | None = None,
    accounting_basis: str | None = None, published_at: str | None = None,
    formula: str | None = None, calculation_ref: str | None = None,
) -> dict[str, Any]:
    """建立逐指标记录；未知 published_at 保持 null。"""

    if name not in METRIC_NAMES or origin not in {"PROVIDER_REPORTED", "DERIVED"}:
        raise EquityValuationError("VALUATION_METRIC_IDENTITY_INVALID")
    if status not in METRIC_STATUSES:
        raise EquityValuationError("VALUATION_METRIC_STATUS_INVALID")
    available = status == "AVAILABLE"
    if available != (value is not None):
        raise EquityValuationError("VALUATION_METRIC_VALUE_STATUS_INVALID")
    if not available and not reason:
        raise EquityValuationError("VALUATION_METRIC_REASON_REQUIRED")
    if origin == "DERIVED" and available and (not formula or not calculation_ref):
        raise EquityValuationError("VALUATION_METRIC_CALCULATION_REQUIRED")
    if origin == "PROVIDER_REPORTED" and calculation_ref is not None:
        raise EquityValuationError("VALUATION_PROVIDER_CALCULATION_FORBIDDEN")
    as_time = _require_time(as_of, "as_of")
    retrieved_time = _require_time(retrieved_at, "retrieved_at")
    if published_at is not None and _require_time(published_at, "published_at") > retrieved_time:
        raise EquityValuationError("VALUATION_PUBLISHED_AFTER_RETRIEVAL")
    if price_at is not None:
        _require_time(price_at, "price_at")
    refs = sorted(set(evidence_refs))
    if not source_id or not unit or (available and not refs):
        raise EquityValuationError("VALUATION_METRIC_PROVENANCE_INVALID")
    rendered = None if value is None else format(_decimal(value, "value"), "f")
    payload = {
        "name": name, "origin": origin, "value": rendered, "status": status,
        "reason": reason, "currency": currency, "unit": unit,
        "price_at": iso_utc(price_at) if price_at else None,
        "financial_period": financial_period, "fiscal_basis": fiscal_basis,
        "accounting_basis": accounting_basis, "source_id": source_id,
        "as_of": iso_utc(as_time), "retrieved_at": iso_utc(retrieved_time),
        "published_at": iso_utc(published_at) if published_at else None,
        "evidence_refs": refs, "formula": formula, "calculation_ref": calculation_ref,
    }
    payload["metric_id"] = f"metric:{name}:{origin.lower()}:{canonical_hash(payload)[:16]}"
    return payload


def _derived_metric(
    name: str, *, numerator: Any | None, denominator: Any | None,
    formula: str, source_id: str, as_of: str, retrieved_at: str,
    evidence_refs: Sequence[str], price_at: str | None, financial_period: str | None,
    currency: str | None = None, allow_negative_numerator: bool = False,
    non_positive_reason: str = "NON_POSITIVE_DENOMINATOR",
) -> dict[str, Any]:
    if numerator is None or denominator is None:
        return build_metric(
            name=name, origin="DERIVED", value=None, status="INPUT_MISSING",
            reason="REQUIRED_INPUT_MISSING", source_id=source_id, as_of=as_of,
            retrieved_at=retrieved_at, evidence_refs=evidence_refs,
            price_at=price_at, financial_period=financial_period, currency=currency,
        )
    top, bottom = _decimal(numerator, "numerator"), _decimal(denominator, "denominator")
    if bottom <= 0 or (top <= 0 and not allow_negative_numerator):
        return build_metric(
            name=name, origin="DERIVED", value=None, status="NOT_APPLICABLE",
            reason=non_positive_reason, source_id=source_id, as_of=as_of,
            retrieved_at=retrieved_at, evidence_refs=evidence_refs,
            price_at=price_at, financial_period=financial_period, currency=currency,
        )
    calculation = {
        "method": name, "formula": formula,
        "inputs": {"numerator": format(top, "f"), "denominator": format(bottom, "f")},
        "as_of": iso_utc(as_of), "evidence_refs": sorted(set(evidence_refs)),
    }
    calculation_ref = f"calc:{name}:{canonical_hash(calculation)[:16]}"
    return build_metric(
        name=name, origin="DERIVED", value=top / bottom, status="AVAILABLE",
        reason=None, source_id=source_id, as_of=as_of, retrieved_at=retrieved_at,
        evidence_refs=evidence_refs, price_at=price_at,
        financial_period=financial_period, currency=currency, formula=formula,
        calculation_ref=calculation_ref,
    )


def derive_current_valuation(
    *, price: Any, shares_outstanding: Any, ttm_eps: Any | None,
    ttm_revenue: Any | None, common_equity: Any | None,
    ttm_operating_cash_flow: Any | None, ttm_capex: Any | None,
    debt: Any | None, cash: Any | None, preferred_stock: Any | None,
    noncontrolling_interest: Any | None, ttm_ebitda: Any | None,
    security_id: str, valuation_at: str, financial_period: str,
    currency: str, source_id: str, retrieved_at: str,
    evidence_refs: Sequence[str], lease_policy: str | None = None,
) -> list[dict[str, Any]]:
    """按明确股本和 EV 构成计算当前估值；缺 EV 项不默认零。"""

    px, shares = _decimal(price, "price"), _decimal(shares_outstanding, "shares_outstanding")
    if px <= 0 or shares <= 0:
        raise EquityValuationError("VALUATION_PRICE_OR_SHARES_INVALID")
    market_cap = px * shares
    metrics = [
        _derived_metric(
            "trailing_pe", numerator=px, denominator=ttm_eps,
            formula="price / TTM diluted EPS", source_id=source_id,
            as_of=valuation_at, retrieved_at=retrieved_at, evidence_refs=evidence_refs,
            price_at=valuation_at, financial_period=financial_period, currency=None,
            non_positive_reason="NON_POSITIVE_TTM_EPS",
        ),
        _derived_metric(
            "price_to_sales", numerator=market_cap, denominator=ttm_revenue,
            formula="market capitalization / TTM revenue", source_id=source_id,
            as_of=valuation_at, retrieved_at=retrieved_at, evidence_refs=evidence_refs,
            price_at=valuation_at, financial_period=financial_period,
            non_positive_reason="NON_POSITIVE_TTM_REVENUE",
        ),
        _derived_metric(
            "price_to_book", numerator=market_cap, denominator=common_equity,
            formula="market capitalization / common shareholders equity", source_id=source_id,
            as_of=valuation_at, retrieved_at=retrieved_at, evidence_refs=evidence_refs,
            price_at=valuation_at, financial_period=financial_period,
            non_positive_reason="NON_POSITIVE_COMMON_EQUITY",
        ),
    ]
    fcf = None
    if ttm_operating_cash_flow is not None and ttm_capex is not None:
        fcf = _decimal(ttm_operating_cash_flow, "ttm_operating_cash_flow") - abs(_decimal(ttm_capex, "ttm_capex"))
    metrics.append(_derived_metric(
        "fcf_yield", numerator=fcf, denominator=market_cap,
        formula="(TTM operating cash flow - absolute TTM capex) / market capitalization",
        source_id=source_id, as_of=valuation_at, retrieved_at=retrieved_at,
        evidence_refs=evidence_refs, price_at=valuation_at,
        financial_period=financial_period, allow_negative_numerator=True,
        non_positive_reason="NON_POSITIVE_MARKET_CAP",
    ))
    ev_inputs = (debt, cash, preferred_stock, noncontrolling_interest)
    if any(item is None for item in ev_inputs):
        ev_metric = build_metric(
            name="enterprise_value", origin="DERIVED", value=None,
            status="INPUT_MISSING", reason="EV_COMPONENT_MISSING",
            source_id=source_id, as_of=valuation_at, retrieved_at=retrieved_at,
            evidence_refs=evidence_refs, unit=currency, currency=currency,
            price_at=valuation_at, financial_period=financial_period,
        )
    else:
        ev = market_cap + _decimal(debt, "debt") + _decimal(preferred_stock, "preferred_stock") + _decimal(noncontrolling_interest, "noncontrolling_interest") - _decimal(cash, "cash")
        calc = {"formula": "market_cap + debt + preferred + NCI - cash", "lease_policy": lease_policy, "evidence_refs": sorted(set(evidence_refs))}
        ev_metric = build_metric(
            name="enterprise_value", origin="DERIVED", value=ev,
            status="AVAILABLE", reason=None, source_id=source_id,
            as_of=valuation_at, retrieved_at=retrieved_at,
            evidence_refs=evidence_refs, unit=currency, currency=currency,
            price_at=valuation_at, financial_period=financial_period,
            formula=calc["formula"], calculation_ref=f"calc:enterprise-value:{canonical_hash(calc)[:16]}",
        )
    metrics.append(ev_metric)
    metrics.append(_derived_metric(
        "ev_to_ebitda", numerator=ev_metric["value"] if ev_metric["status"] == "AVAILABLE" else None,
        denominator=ttm_ebitda, formula="enterprise value / TTM EBITDA",
        source_id=source_id, as_of=valuation_at, retrieved_at=retrieved_at,
        evidence_refs=evidence_refs, price_at=valuation_at,
        financial_period=financial_period, non_positive_reason="NON_POSITIVE_TTM_EBITDA",
    ))
    return metrics


def derive_forward_pe(
    *, price: Any, forecast_eps: Any | None, forecast_period: str | None,
    accounting_basis: str | None, source_id: str, valuation_at: str,
    retrieved_at: str, evidence_refs: Sequence[str], currency: str,
) -> dict[str, Any]:
    """只在预测财政期和会计基础明确时派生 forward PE。"""

    if forecast_period not in {"FY1", "FY2", "NTM"} or accounting_basis not in {"GAAP", "ADJUSTED"}:
        return build_metric(
            name="forward_pe", origin="DERIVED", value=None,
            status="BASIS_UNKNOWN", reason="FORECAST_PERIOD_OR_ACCOUNTING_BASIS_UNKNOWN",
            source_id=source_id, as_of=valuation_at, retrieved_at=retrieved_at,
            evidence_refs=evidence_refs, currency=currency, price_at=valuation_at,
            financial_period=forecast_period, fiscal_basis=forecast_period,
            accounting_basis=accounting_basis,
        )
    return _derived_metric(
        "forward_pe", numerator=price, denominator=forecast_eps,
        formula="price / forward diluted EPS", source_id=source_id,
        as_of=valuation_at, retrieved_at=retrieved_at,
        evidence_refs=evidence_refs, price_at=valuation_at,
        financial_period=forecast_period, currency=currency,
        non_positive_reason="NON_POSITIVE_FORWARD_EPS",
    ) | {"fiscal_basis": forecast_period, "accounting_basis": accounting_basis}


def provider_metrics_from_yahoo(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把 Yahoo 当前供应商值转成 published_at 未知的并列指标。"""

    fields = snapshot.get("fields")
    if not isinstance(fields, Mapping):
        raise EquityValuationError("YAHOO_VALUATION_FIELDS_INVALID")
    mapping = {
        "trailingPE": "trailing_pe", "forwardPE": "forward_pe",
        "priceToSalesTrailing12Months": "price_to_sales",
        "priceToBook": "price_to_book", "enterpriseValue": "enterprise_value",
        "enterpriseToEbitda": "ev_to_ebitda",
    }
    raw_ref = f"raw:yahoo:{snapshot.get('raw_content_hash')}"
    metrics = []
    for field, name in mapping.items():
        if fields.get(field) is None:
            continue
        metrics.append(build_metric(
            name=name, origin="PROVIDER_REPORTED", value=fields[field],
            status="AVAILABLE", reason=None, source_id=str(snapshot["source_id"]),
            as_of=str(snapshot["as_of"]), retrieved_at=str(snapshot["retrieved_at"]),
            published_at=None, evidence_refs=[raw_ref],
            unit="USD" if name == "enterprise_value" else "ratio",
            currency=fields.get("currency") if name == "enterprise_value" else None,
            price_at=str(snapshot["as_of"]),
            financial_period=None, fiscal_basis=None, accounting_basis=None,
        ))
    return metrics


def build_valuation_snapshot(
    *, snapshot_id: str, security_id: str, decision_cutoff: str,
    valuation_at: str, price_basis: str, metrics: Sequence[Mapping[str, Any]],
    data_gaps: Sequence[str] = (),
) -> dict[str, Any]:
    gaps = set(data_gaps)
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for item in metrics:
        if item.get("status") == "AVAILABLE":
            by_name.setdefault(str(item.get("name")), []).append(item)
    for name, rows in by_name.items():
        provider = next((item for item in rows if item.get("origin") == "PROVIDER_REPORTED"), None)
        derived = next((item for item in rows if item.get("origin") == "DERIVED"), None)
        if provider and derived and _decimal(provider["value"], "provider") != _decimal(derived["value"], "derived"):
            gaps.add(f"METRIC_CONFLICT:{name}:provider={provider['value']}:derived={derived['value']}")
    value = {
        "schema_version": SNAPSHOT_VERSION, "snapshot_id": snapshot_id,
        "security_id": security_id, "decision_cutoff": iso_utc(decision_cutoff),
        "valuation_at": iso_utc(valuation_at), "price_basis": price_basis,
        "metrics": [deepcopy(dict(item)) for item in metrics],
        "data_gaps": sorted(gaps),
    }
    value["artifact_hash"] = canonical_hash(value)
    validate_valuation_snapshot(value)
    return value


def validate_valuation_snapshot(value: Mapping[str, Any]) -> None:
    expected = {"schema_version", "snapshot_id", "security_id", "decision_cutoff", "valuation_at", "price_basis", "metrics", "data_gaps", "artifact_hash"}
    if set(value) != expected or value.get("schema_version") != SNAPSHOT_VERSION:
        raise EquityValuationError("VALUATION_SNAPSHOT_SHAPE_INVALID")
    cutoff = _require_time(value["decision_cutoff"], "decision_cutoff")
    valuation_at = _require_time(value["valuation_at"], "valuation_at")
    if valuation_at > cutoff:
        raise EquityValuationError("VALUATION_SNAPSHOT_AFTER_CUTOFF")
    metrics = value.get("metrics")
    if not isinstance(metrics, list) or len({item.get("metric_id") for item in metrics if isinstance(item, Mapping)}) != len(metrics):
        raise EquityValuationError("VALUATION_METRICS_INVALID")
    for item in metrics:
        if not isinstance(item, Mapping) or item.get("name") not in METRIC_NAMES or item.get("status") not in METRIC_STATUSES:
            raise EquityValuationError("VALUATION_METRIC_INVALID")
        for field in ("source_id", "as_of", "retrieved_at"):
            if not item.get(field):
                raise EquityValuationError(f"VALUATION_METRIC_PROVENANCE_MISSING:{field}")
        if max(_require_time(item["as_of"], "metric.as_of"), _require_time(item["retrieved_at"], "metric.retrieved_at")) > cutoff:
            raise EquityValuationError("VALUATION_METRIC_AFTER_CUTOFF")
        if item.get("published_at") is not None and _require_time(item["published_at"], "metric.published_at") > cutoff:
            raise EquityValuationError("VALUATION_METRIC_AFTER_CUTOFF")
        _canonical_ids(item.get("evidence_refs"), "metric.evidence_refs")
    if value.get("artifact_hash") != _hash_without(value):
        raise EquityValuationError("VALUATION_SNAPSHOT_HASH_MISMATCH")


def _period_bounds(item: Mapping[str, Any]) -> tuple[date, date]:
    try:
        return date.fromisoformat(str(item["period_start"])), date.fromisoformat(str(item["period_end"]))
    except (KeyError, ValueError) as exc:
        raise EquityValuationError("VALUATION_PERIOD_INVALID") from exc


def aggregate_ttm(
    periods: Sequence[Mapping[str, Any]], *, metric: str, allow_eps_sum: bool = False,
) -> dict[str, Any]:
    """汇总四个兼容且互不重叠季度；累计 EPS 明确拒绝。"""

    if len(periods) != 4:
        raise EquityValuationError("TTM_REQUIRES_FOUR_QUARTERS")
    ordered = sorted((dict(item) for item in periods), key=lambda item: _period_bounds(item)[0])
    bases = {(item.get("security_id"), item.get("accounting_basis"), item.get("currency"), item.get("unit")) for item in ordered}
    if len(bases) != 1:
        raise EquityValuationError("TTM_BASIS_INCOMPATIBLE")
    for index, item in enumerate(ordered):
        start, end = _period_bounds(item)
        if item.get("context_type") != "independent_quarter" or end < start:
            raise EquityValuationError("TTM_PERIOD_NOT_INDEPENDENT_QUARTER")
        if index and start <= _period_bounds(ordered[index - 1])[1]:
            raise EquityValuationError("TTM_PERIOD_OVERLAP")
        if metric == "diluted_eps" and not allow_eps_sum:
            raise EquityValuationError("TTM_EPS_SUM_REQUIRES_EXPLICIT_POLICY")
    total = sum((_decimal(item.get("value"), "period.value") for item in ordered), Decimal(0))
    return {
        "metric": metric, "value": format(total, "f"),
        "period_start": _period_bounds(ordered[0])[0].isoformat(),
        "period_end": _period_bounds(ordered[-1])[1].isoformat(),
        "method": "SUM_FOUR_DISCLOSED_INDEPENDENT_QUARTERS",
        "limitation": "季度 diluted EPS 汇总不保证等于公司重算全年 diluted EPS" if metric == "diluted_eps" else None,
        "evidence_refs": sorted({str(ref) for item in ordered for ref in item.get("evidence_refs", [])}),
    }


def cumulative_period_difference(*, later: Mapping[str, Any], earlier: Mapping[str, Any], metric: str) -> dict[str, Any]:
    if metric == "diluted_eps":
        raise EquityValuationError("CUMULATIVE_EPS_DIFFERENCE_FORBIDDEN")
    if any(later.get(field) != earlier.get(field) for field in ("security_id", "accounting_basis", "currency", "unit", "fiscal_year")):
        raise EquityValuationError("CUMULATIVE_BASIS_INCOMPATIBLE")
    later_start, later_end = _period_bounds(later)
    earlier_start, earlier_end = _period_bounds(earlier)
    if later_start != earlier_start or earlier_end >= later_end:
        raise EquityValuationError("CUMULATIVE_PERIODS_NOT_NESTED")
    return {
        "metric": metric,
        "value": format(_decimal(later["value"], "later.value") - _decimal(earlier["value"], "earlier.value"), "f"),
        "period_start": (earlier_end + timedelta(days=1)).isoformat(),
        "period_end": later_end.isoformat(), "method": "CUMULATIVE_DIFFERENCE",
        "evidence_refs": sorted(set(later.get("evidence_refs", [])) | set(earlier.get("evidence_refs", []))),
    }


def select_pit_version(rows: Sequence[Mapping[str, Any]], *, valuation_at: str) -> dict[str, Any] | None:
    """选择观察点当时已公开的最新版本；只知日期时从下一日生效。"""

    point = _require_time(valuation_at, "valuation_at")
    eligible: list[tuple[datetime, Mapping[str, Any]]] = []
    for row in rows:
        published = row.get("published_at")
        if not isinstance(published, str):
            continue
        if "T" in published:
            effective = parse_timestamp(published)
        else:
            effective = datetime.combine(date.fromisoformat(published) + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        if effective <= point:
            eligible.append((effective, row))
    if not eligible:
        return None
    _, chosen = max(eligible, key=lambda pair: (pair[0], str(pair[1].get("evidence_id", ""))))
    return deepcopy(dict(chosen))


def monthly_observations(rows: Sequence[Mapping[str, Any]], *, start: str, end: str) -> list[dict[str, Any]]:
    start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
    by_month: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        current = date.fromisoformat(str(row["date"]))
        if start_date <= current <= end_date:
            key = (current.year, current.month)
            if key not in by_month or current > date.fromisoformat(str(by_month[key]["date"])):
                by_month[key] = deepcopy(dict(row))
    return [by_month[key] for key in sorted(by_month)]


def align_price_and_per_share_input(
    *, price: Any, per_share_value: Any, price_basis: str,
    per_share_basis: str, dividend_adjusted: bool, currency: str,
    per_share_currency: str, security_id: str, per_share_security_id: str,
    segment_id: str, per_share_segment_id: str,
) -> tuple[Decimal, Decimal]:
    """核对价格与每股量的证券、币种、股本和分段基准。"""

    if dividend_adjusted or price_basis != "CLOSE_SPLIT_ADJUSTED_NOT_DIVIDEND_ADJUSTED":
        raise EquityValuationError("VALUATION_PRICE_BASIS_INVALID")
    if per_share_basis != "SPLIT_ADJUSTED":
        raise EquityValuationError("VALUATION_PER_SHARE_BASIS_INVALID")
    if currency != per_share_currency:
        raise EquityValuationError("VALUATION_CURRENCY_MISMATCH")
    if security_id != per_share_security_id:
        raise EquityValuationError("VALUATION_SECURITY_MISMATCH")
    if segment_id != per_share_segment_id:
        raise EquityValuationError("VALUATION_SEGMENT_DISCONTINUITY")
    px, amount = _decimal(price, "price"), _decimal(per_share_value, "per_share_value")
    if px <= 0:
        raise EquityValuationError("VALUATION_PRICE_INVALID")
    return px, amount


def validate_market_cap_inputs(
    *, shares: Any, share_count_kind: str, price_share_class: str | None,
    shares_share_class: str | None, shares_as_of: str, valuation_at: str,
    adr_ratio_status: str = "NOT_APPLICABLE", maximum_age_days: int = 180,
) -> Decimal:
    """拒绝加权 EPS 股数、过期股数及未核实 ADR/股类换算。"""

    if share_count_kind != "ACTUAL_COMMON_SHARES_OUTSTANDING":
        raise EquityValuationError("MARKET_CAP_SHARE_COUNT_KIND_INVALID")
    if not price_share_class or not shares_share_class or price_share_class != shares_share_class:
        raise EquityValuationError("MARKET_CAP_SHARE_CLASS_UNKNOWN_OR_MISMATCH")
    if adr_ratio_status not in {"NOT_APPLICABLE", "VERIFIED"}:
        raise EquityValuationError("MARKET_CAP_ADR_RATIO_UNVERIFIED")
    share_date = parse_timestamp(shares_as_of).date()
    valuation_date = parse_timestamp(valuation_at).date()
    if valuation_date < share_date or (valuation_date - share_date).days > maximum_age_days:
        raise EquityValuationError("MARKET_CAP_SHARE_COUNT_STALE")
    result = _decimal(shares, "shares")
    if result <= 0:
        raise EquityValuationError("MARKET_CAP_SHARE_COUNT_INVALID")
    return result


def midrank_percentile(current: Any, history: Sequence[Any]) -> Decimal:
    values = [_decimal(item, "history") for item in history]
    if not values:
        raise EquityValuationError("PERCENTILE_HISTORY_EMPTY")
    target = _decimal(current, "current")
    less = sum(item < target for item in values)
    equal = sum(item == target for item in values)
    return Decimal(100) * (Decimal(less) + Decimal("0.5") * Decimal(equal)) / Decimal(len(values))


def build_trailing_pe_history(
    *, history_id: str, security_id: str, decision_cutoff: str,
    requested_start: str, requested_end: str, price_rows: Sequence[Mapping[str, Any]],
    eps_versions: Sequence[Mapping[str, Any]], current_value: Any | None,
    segment_id: str = "continuing-entity", current_price_row: Mapping[str, Any] | None = None,
    minimum_points: int = 24,
    minimum_coverage: Decimal = Decimal("0.8"),
) -> dict[str, Any]:
    monthly = monthly_observations(price_rows, start=requested_start, end=requested_end)
    current_date: str | None = None
    if current_price_row is not None:
        current_date = str(current_price_row["date"])
        monthly = [item for item in monthly if str(item["date"]) != current_date]
        monthly.append(deepcopy(dict(current_price_row)))
        monthly.sort(key=lambda item: str(item["date"]))
    points: list[dict[str, Any]] = []
    for price_row in monthly:
        valuation_date = str(price_row["date"])
        point_time = f"{valuation_date}T23:59:59Z"
        eps = select_pit_version(eps_versions, valuation_at=point_time)
        price_source_id = str(price_row.get("source_id") or "")
        price_retrieved_at = price_row.get("retrieved_at")
        if not price_source_id or not price_retrieved_at:
            raise EquityValuationError("VALUATION_HISTORY_PRICE_PROVENANCE_MISSING")
        price_retrieved = iso_utc(str(price_retrieved_at))
        is_current = current_date is not None and valuation_date == current_date
        base = {
            "valuation_date": valuation_date, "price": str(price_row.get("close")) if price_row.get("close") is not None else None,
            "value": None, "status": "INPUT_MISSING", "reason": "PIT_EPS_MISSING",
            "financial_period": None, "published_at": None, "retrieved_at": price_retrieved,
            "source_id": price_source_id, "as_of": point_time,
            "currency": price_row.get("currency"), "unit": "ratio",
            "formula": "split-adjusted close / PIT TTM diluted EPS",
            "formula_version": "trailing-pe-pit/1.0.0", "calculation_ref": None,
            "calculation": None, "is_current": is_current,
            "evidence_refs": sorted(set(price_row.get("evidence_refs", []))), "segment_id": segment_id,
        }
        if eps is not None:
            eps_source_id = str(eps.get("source_id") or "")
            if not eps_source_id or not eps.get("retrieved_at"):
                raise EquityValuationError("VALUATION_HISTORY_EPS_PROVENANCE_MISSING")
            retrieved_at = max(
                parse_timestamp(price_retrieved), parse_timestamp(iso_utc(str(eps["retrieved_at"])))
            ).isoformat().replace("+00:00", "Z")
            base.update(
                financial_period=eps.get("financial_period"),
                published_at=iso_utc(eps["published_at"]) if "T" in str(eps["published_at"]) else f"{eps['published_at']}T00:00:00Z",
                retrieved_at=retrieved_at,
                source_id="+".join(sorted({price_source_id, eps_source_id})),
                evidence_refs=sorted(set(base["evidence_refs"]) | set(eps.get("evidence_refs", []))),
            )
            age = date.fromisoformat(valuation_date) - date.fromisoformat(str(eps["financial_period"])[:10])
            if age.days > 180:
                base.update(status="STALE", reason="TTM_FINANCIAL_PERIOD_STALE")
            else:
                try:
                    price, denominator = align_price_and_per_share_input(
                        price=price_row["close"], per_share_value=eps["value"],
                        price_basis=str(price_row.get("price_basis")),
                        per_share_basis=str(eps.get("share_basis")),
                        dividend_adjusted=bool(price_row.get("dividend_adjusted")),
                        currency=str(price_row.get("currency")),
                        per_share_currency=str(eps.get("currency")),
                        security_id=str(price_row.get("security_id")),
                        per_share_security_id=str(eps.get("security_id")),
                        segment_id=str(price_row.get("segment_id", segment_id)),
                        per_share_segment_id=str(eps.get("segment_id", segment_id)),
                    )
                except EquityValuationError as exc:
                    code = str(exc)
                    base.update(
                        status="DISCONTINUITY" if "SEGMENT" in code or "SECURITY" in code else "INPUT_MISSING",
                        reason=code,
                    )
                    points.append(base)
                    continue
                if denominator <= 0:
                    base.update(status="NOT_APPLICABLE", reason="NON_POSITIVE_TTM_EPS")
                elif price <= 0:
                    base.update(status="INPUT_MISSING", reason="PRICE_INVALID")
                else:
                    calculation = {
                        "formula_version": base["formula_version"],
                        "price": format(price, "f"), "ttm_diluted_eps": format(denominator, "f"),
                        "price_basis": price_row.get("price_basis"),
                        "per_share_basis": eps.get("share_basis"),
                        "currency": price_row.get("currency"),
                    }
                    base.update(
                        value=format(price / denominator, "f"), status="AVAILABLE", reason=None,
                        calculation=calculation,
                        calculation_ref=f"calc:trailing-pe-point:{canonical_hash(calculation)[:16]}",
                    )
        points.append(base)
    valid = [item for item in points if item["status"] == "AVAILABLE"]
    reference = [item for item in valid if not item["is_current"]]
    reference_requested = [item for item in points if not item["is_current"]]
    coverage = Decimal(len(valid)) / Decimal(len(monthly)) if monthly else Decimal(0)
    reference_coverage = Decimal(len(reference)) / Decimal(len(reference_requested)) if reference_requested else Decimal(0)
    percentile = None
    if current_value is None:
        percentile_status = "CURRENT_VALUE_UNAVAILABLE"
    elif len(reference) < minimum_points or reference_coverage < minimum_coverage:
        percentile_status = "INSUFFICIENT_HISTORY"
    else:
        percentile_status = "AVAILABLE"
        percentile = format(midrank_percentile(current_value, [item["value"] for item in reference]), "f")
    actual = None if not points else {"start": points[0]["valuation_date"], "end": points[-1]["valuation_date"]}
    value = {
        "schema_version": HISTORY_VERSION, "history_id": history_id,
        "security_id": security_id, "decision_cutoff": iso_utc(decision_cutoff),
        "metric": "trailing_pe", "requested_window": {"start": requested_start, "end": requested_end},
        "actual_window": actual, "points": points, "valid_points": len(valid),
        "coverage_ratio": format(coverage, "f"), "percentile": percentile,
        "current_value": None if current_value is None else format(_decimal(current_value, "current_value"), "f"),
        "reference_points": len(reference),
        "reference_coverage_ratio": format(reference_coverage, "f"),
        "current_point_date": current_date,
        "minimum_reference_points": minimum_points,
        "minimum_reference_coverage": format(minimum_coverage, "f"),
        "percentile_status": percentile_status,
        "reconstruction_policy": "ORIGINAL_PUBLIC_VERSION_AS_KNOWN_AT_POINT_RETRIEVED_LATER",
        "data_gaps": sorted({item["reason"] for item in points if item["reason"]}),
    }
    value["artifact_hash"] = canonical_hash(value)
    validate_valuation_history(value)
    return value


def validate_valuation_history(value: Mapping[str, Any]) -> None:
    cutoff = _require_time(value.get("decision_cutoff"), "decision_cutoff")
    if value.get("schema_version") != HISTORY_VERSION or value.get("artifact_hash") != _hash_without(value):
        raise EquityValuationError("VALUATION_HISTORY_INVALID")
    dates = [item.get("valuation_date") for item in value.get("points", [])]
    if dates != sorted(set(dates)):
        raise EquityValuationError("VALUATION_HISTORY_DATES_INVALID")
    for item in value.get("points", []):
        for field in ("source_id", "as_of", "retrieved_at", "unit", "formula", "formula_version"):
            if not item.get(field):
                raise EquityValuationError(f"VALUATION_HISTORY_POINT_PROVENANCE_MISSING:{field}")
        if item.get("unit") != "ratio" or item.get("formula_version") != "trailing-pe-pit/1.0.0":
            raise EquityValuationError("VALUATION_HISTORY_POINT_BASIS_INVALID")
        if _require_time(item["as_of"], "point.as_of") > cutoff:
            raise EquityValuationError("VALUATION_HISTORY_POINT_AFTER_CUTOFF")
        if item.get("published_at") and _require_time(item["published_at"], "point.published_at") > datetime.combine(date.fromisoformat(item["valuation_date"]), datetime.max.time(), tzinfo=timezone.utc):
            raise EquityValuationError("VALUATION_HISTORY_PIT_LEAKAGE")
        if item.get("retrieved_at") and _require_time(item["retrieved_at"], "point.retrieved_at") > cutoff:
            raise EquityValuationError("VALUATION_HISTORY_RETRIEVED_AFTER_CUTOFF")
        _canonical_ids(item.get("evidence_refs"), "point.evidence_refs")
        calculation = item.get("calculation")
        if item.get("status") == "AVAILABLE":
            if not isinstance(calculation, Mapping) or item.get("calculation_ref") != f"calc:trailing-pe-point:{canonical_hash(calculation)[:16]}":
                raise EquityValuationError("VALUATION_HISTORY_CALCULATION_INVALID")
            if _decimal(calculation.get("price"), "point.calculation.price") / _decimal(calculation.get("ttm_diluted_eps"), "point.calculation.ttm_diluted_eps") != _decimal(item.get("value"), "point.value"):
                raise EquityValuationError("VALUATION_HISTORY_CALCULATION_RESULT_INVALID")
        elif calculation is not None or item.get("calculation_ref") is not None:
            raise EquityValuationError("VALUATION_HISTORY_UNAVAILABLE_CALCULATION_INVALID")
    valid = sum(item.get("status") == "AVAILABLE" for item in value.get("points", []))
    if valid != value.get("valid_points"):
        raise EquityValuationError("VALUATION_HISTORY_COUNT_INVALID")
    reference = sum(item.get("status") == "AVAILABLE" and not item.get("is_current") for item in value.get("points", []))
    if reference != value.get("reference_points") or sum(bool(item.get("is_current")) for item in value.get("points", [])) > 1:
        raise EquityValuationError("VALUATION_HISTORY_REFERENCE_COUNT_INVALID")
    points = value.get("points", [])
    expected_coverage = Decimal(valid) / Decimal(len(points)) if points else Decimal(0)
    reference_requested = [item for item in points if not item.get("is_current")]
    expected_reference_coverage = Decimal(reference) / Decimal(len(reference_requested)) if reference_requested else Decimal(0)
    if _decimal(value.get("coverage_ratio"), "coverage_ratio") != expected_coverage or _decimal(value.get("reference_coverage_ratio"), "reference_coverage_ratio") != expected_reference_coverage:
        raise EquityValuationError("VALUATION_HISTORY_COVERAGE_INVALID")
    current_points = [item for item in points if item.get("is_current")]
    if (current_points[0]["valuation_date"] if current_points else None) != value.get("current_point_date"):
        raise EquityValuationError("VALUATION_HISTORY_CURRENT_POINT_INVALID")
    minimum_points = int(value.get("minimum_reference_points"))
    minimum_coverage = _decimal(value.get("minimum_reference_coverage"), "minimum_reference_coverage")
    current_value = value.get("current_value")
    if current_value is None:
        expected_status, expected_percentile = "CURRENT_VALUE_UNAVAILABLE", None
    elif reference < minimum_points or expected_reference_coverage < minimum_coverage:
        expected_status, expected_percentile = "INSUFFICIENT_HISTORY", None
    else:
        expected_status = "AVAILABLE"
        expected_percentile = format(midrank_percentile(current_value, [item["value"] for item in points if item.get("status") == "AVAILABLE" and not item.get("is_current")]), "f")
    if value.get("percentile_status") != expected_status or value.get("percentile") != expected_percentile:
        raise EquityValuationError("VALUATION_HISTORY_PERCENTILE_INVALID")


def calculate_financial_ratios(
    *, ttm_net_income: Any, beginning_equity: Any | None, ending_equity: Any,
    beginning_assets: Any | None, ending_assets: Any, current_assets: Any,
    current_liabilities: Any, cash_and_equivalents: Any,
    marketable_securities: Any, net_receivables: Any, restricted_cash: Any,
    interest_bearing_debt: Any, ttm_ebit: Any, ttm_interest_expense: Any | None,
    ttm_operating_cash_flow: Any, ttm_sbc: Any, ttm_revenue: Any,
    nopat: Any | None = None, beginning_invested_capital: Any | None = None,
    ending_invested_capital: Any | None = None,
    evidence_refs: Sequence[str] = (),
) -> dict[str, dict[str, str | None]]:
    """按规格定义计算比率；不提供阈值或综合评分。"""

    numbers = {name: _decimal(value, name) for name, value in {
        "ttm_net_income": ttm_net_income, "ending_equity": ending_equity,
        "ending_assets": ending_assets, "current_assets": current_assets,
        "current_liabilities": current_liabilities, "cash_and_equivalents": cash_and_equivalents,
        "marketable_securities": marketable_securities, "net_receivables": net_receivables,
        "restricted_cash": restricted_cash, "interest_bearing_debt": interest_bearing_debt,
        "ttm_ebit": ttm_ebit,
        "ttm_operating_cash_flow": ttm_operating_cash_flow, "ttm_sbc": ttm_sbc,
        "ttm_revenue": ttm_revenue,
    }.items()}
    if numbers["current_liabilities"] <= 0 or numbers["ttm_revenue"] <= 0:
        raise EquityValuationError("FINANCIAL_RATIO_REQUIRED_DENOMINATOR_INVALID")
    unrestricted_cash = numbers["cash_and_equivalents"] - numbers["restricted_cash"]
    if unrestricted_cash < 0:
        raise EquityValuationError("RESTRICTED_CASH_EXCEEDS_CASH")

    refs = sorted(set(evidence_refs))

    def result(value: Decimal | None, formula: str, status: str = "AVAILABLE", reason: str | None = None) -> dict[str, Any]:
        payload = {
            "value": format(value, "f") if value is not None else None,
            "formula": formula, "status": status, "reason": reason,
            "evidence_refs": refs,
        }
        payload["calculation_ref"] = (
            f"calc:financial-ratio:{canonical_hash(payload)[:16]}"
            if status == "AVAILABLE" else None
        )
        return payload

    ratios: dict[str, dict[str, str | None]] = {
        "current_ratio": result(numbers["current_assets"] / numbers["current_liabilities"], "current assets / current liabilities"),
        "quick_ratio": result((unrestricted_cash + numbers["marketable_securities"] + numbers["net_receivables"]) / numbers["current_liabilities"], "(unrestricted cash + marketable securities + net receivables) / current liabilities"),
        "cash_ratio": result((unrestricted_cash + numbers["marketable_securities"]) / numbers["current_liabilities"], "(unrestricted cash + marketable securities) / current liabilities"),
        "sbc_to_revenue": result(numbers["ttm_sbc"] / numbers["ttm_revenue"], "TTM SBC / TTM revenue"),
    }
    if beginning_equity is None:
        ratios["roe"] = result(None, "TTM net income / average common equity", "INPUT_MISSING", "BEGINNING_EQUITY_MISSING")
    else:
        average = (_decimal(beginning_equity, "beginning_equity") + numbers["ending_equity"]) / 2
        ratios["roe"] = result(numbers["ttm_net_income"] / average, "TTM net income / average common equity") if average > 0 else result(None, "TTM net income / average common equity", "NOT_APPLICABLE", "NON_POSITIVE_AVERAGE_EQUITY")
    if beginning_assets is None:
        ratios["roa"] = result(None, "TTM net income / average total assets", "INPUT_MISSING", "BEGINNING_ASSETS_MISSING")
    else:
        average = (_decimal(beginning_assets, "beginning_assets") + numbers["ending_assets"]) / 2
        ratios["roa"] = result(numbers["ttm_net_income"] / average, "TTM net income / average total assets") if average > 0 else result(None, "TTM net income / average total assets", "NOT_APPLICABLE", "NON_POSITIVE_AVERAGE_ASSETS")
    ratios["debt_to_equity"] = result(numbers["interest_bearing_debt"] / numbers["ending_equity"], "interest-bearing debt / common equity") if numbers["ending_equity"] > 0 else result(None, "interest-bearing debt / common equity", "NOT_APPLICABLE", "NON_POSITIVE_EQUITY")
    if ttm_interest_expense is None:
        ratios["interest_coverage"] = result(
            None, "TTM EBIT / TTM interest expense", "INPUT_MISSING",
            "INTEREST_EXPENSE_MISSING",
        )
    else:
        interest_expense = _decimal(ttm_interest_expense, "ttm_interest_expense")
        ratios["interest_coverage"] = result(numbers["ttm_ebit"] / interest_expense, "TTM EBIT / TTM interest expense") if interest_expense > 0 else result(None, "TTM EBIT / TTM interest expense", "NOT_APPLICABLE", "NON_POSITIVE_INTEREST_EXPENSE")
    ratios["ocf_to_net_income"] = result(numbers["ttm_operating_cash_flow"] / numbers["ttm_net_income"], "TTM OCF / TTM net income") if numbers["ttm_net_income"] > 0 else result(None, "TTM OCF / TTM net income", "NOT_APPLICABLE", "NON_POSITIVE_NET_INCOME")
    if nopat is None or beginning_invested_capital is None or ending_invested_capital is None:
        ratios["roic"] = result(None, "NOPAT / average invested capital", "INPUT_MISSING", "NOPAT_OR_INVESTED_CAPITAL_MISSING")
    else:
        average = (_decimal(beginning_invested_capital, "beginning_invested_capital") + _decimal(ending_invested_capital, "ending_invested_capital")) / 2
        ratios["roic"] = result(_decimal(nopat, "nopat") / average, "NOPAT / average invested capital") if average > 0 else result(None, "NOPAT / average invested capital", "NOT_APPLICABLE", "NON_POSITIVE_INVESTED_CAPITAL")
    return ratios


def build_fundamental_supplement(
    *, supplement_id: str, security_id: str, decision_cutoff: str,
    groups: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if set(groups) != set(FUNDAMENTAL_GROUPS):
        raise EquityValuationError("FUNDAMENTAL_GROUP_SET_INVALID")
    value = {
        "schema_version": FUNDAMENTAL_VERSION, "supplement_id": supplement_id,
        "security_id": security_id, "decision_cutoff": iso_utc(decision_cutoff),
        "document_budget": {"annual": 2, "quarterly": 4, "earnings_releases": 4, "proxy": 2, "other_8k": 8, "total": 32},
        "groups": {name: deepcopy(dict(groups[name])) for name in FUNDAMENTAL_GROUPS},
    }
    value["artifact_hash"] = canonical_hash(value)
    validate_fundamental_supplement(value)
    return value


def validate_fundamental_supplement(value: Mapping[str, Any]) -> None:
    cutoff = _require_time(value.get("decision_cutoff"), "decision_cutoff")
    if value.get("schema_version") != FUNDAMENTAL_VERSION or value.get("artifact_hash") != _hash_without(value):
        raise EquityValuationError("FUNDAMENTAL_SUPPLEMENT_INVALID")
    groups = value.get("groups")
    if not isinstance(groups, Mapping) or set(groups) != set(FUNDAMENTAL_GROUPS):
        raise EquityValuationError("FUNDAMENTAL_GROUP_SET_INVALID")
    seen: set[str] = set()
    for name, group in groups.items():
        if set(group) != {"status", "coverage", "reason", "items"} or group["status"] not in {"COVERED", "PARTIAL", "SOURCE_LIMITED", "NOT_DISCLOSED", "UNVERIFIED"}:
            raise EquityValuationError(f"FUNDAMENTAL_GROUP_INVALID:{name}")
        for item in group["items"]:
            if item.get("item_id") in seen:
                raise EquityValuationError("FUNDAMENTAL_ITEM_DUPLICATE")
            seen.add(item.get("item_id"))
            for field in ("source_id", "as_of", "retrieved_at"):
                if not item.get(field):
                    raise EquityValuationError(f"FUNDAMENTAL_PROVENANCE_MISSING:{field}")
            times = [_require_time(item["as_of"], "item.as_of"), _require_time(item["retrieved_at"], "item.retrieved_at")]
            if item.get("published_at"):
                times.append(_require_time(item["published_at"], "item.published_at"))
            if max(times) > cutoff:
                raise EquityValuationError("FUNDAMENTAL_ITEM_AFTER_CUTOFF")
            _canonical_ids(item.get("evidence_refs"), "fundamental.evidence_refs", allow_empty=item.get("claim_status") == "CANDIDATE")


def compare_guidance_versions(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("metric", "target_period", "unit", "accounting_basis")
    if any(previous.get(key) != current.get(key) for key in keys):
        return {"status": "NOT_COMPARABLE", "reason": "GUIDANCE_BASIS_CHANGED", "lower_change": None, "upper_change": None, "midpoint_change": None}
    if current.get("status") == "WITHDRAWN":
        return {"status": "WITHDRAWN", "reason": None, "lower_change": None, "upper_change": None, "midpoint_change": None}
    try:
        previous_lower, previous_upper = _decimal(previous["lower"], "previous.lower"), _decimal(previous["upper"], "previous.upper")
        current_lower, current_upper = _decimal(current["lower"], "current.lower"), _decimal(current["upper"], "current.upper")
    except KeyError as exc:
        raise EquityValuationError("GUIDANCE_NUMERIC_RANGE_REQUIRED") from exc
    return {
        "status": "COMPARABLE", "reason": None,
        "lower_change": format(current_lower - previous_lower, "f"),
        "upper_change": format(current_upper - previous_upper, "f"),
        "midpoint_change": format((current_lower + current_upper - previous_lower - previous_upper) / 2, "f"),
    }


def reconcile_adjusted_metric(
    *, gaap_value: Any, adjustments: Sequence[Mapping[str, Any]],
    adjusted_value: Any, display_increment: Any,
) -> dict[str, Any]:
    gaap, target, increment = _decimal(gaap_value, "gaap_value"), _decimal(adjusted_value, "adjusted_value"), abs(_decimal(display_increment, "display_increment"))
    if increment <= 0:
        raise EquityValuationError("RECONCILIATION_DISPLAY_INCREMENT_INVALID")
    total = gaap
    for item in adjustments:
        if item.get("tax_basis") not in {"PRE_TAX", "AFTER_TAX", "NOT_APPLICABLE"}:
            raise EquityValuationError("RECONCILIATION_TAX_BASIS_INVALID")
        sign = item.get("sign")
        if sign not in {"ADD", "SUBTRACT"}:
            raise EquityValuationError("RECONCILIATION_SIGN_INVALID")
        amount = _decimal(item.get("amount"), "adjustment.amount")
        total += amount if sign == "ADD" else -amount
    difference = total - target
    tolerance = increment / 2
    return {"recalculated": format(total, "f"), "reported_adjusted": format(target, "f"), "difference": format(difference, "f"), "tolerance": format(tolerance, "f"), "status": "RECONCILED" if abs(difference) <= tolerance else "UNRECONCILED"}


def build_peer_comparison(
    *, comparison_id: str, target_security_id: str, decision_cutoff: str,
    candidates: Sequence[Mapping[str, Any]], target: Mapping[str, Any],
    peers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not 1 <= len(candidates) <= 5 or len({item.get("security_id") for item in candidates}) != len(candidates):
        raise EquityValuationError("PEER_CANDIDATE_BUDGET_INVALID")
    included = {item["security_id"] for item in candidates if item.get("status") == "INCLUDED"}
    if {item.get("security_id") for item in peers} - included:
        raise EquityValuationError("PEER_NOT_IN_INCLUDED_CANDIDATES")
    metric_sets = [
        {(metric.get("name"), metric.get("metric_basis_id"), metric.get("unit")) for metric in company.get("metrics", []) if metric.get("status") in {"COMPARABLE", "LIMITED_COMPARABILITY"}}
        for company in [target, *peers]
    ]
    common_metrics = set.intersection(*metric_sets) if metric_sets else set()
    valuation_metrics = {"trailing_pe", "price_to_sales", "price_to_book", "fcf_yield", "ev_to_ebitda"}
    valuation_common = any(
        name in valuation_metrics and (name != "price_to_sales" or basis_id == "MARKET_CAP_OVER_GAAP_TTM_REVENUE")
        for name, basis_id, _unit in common_metrics
    )
    coverage = "COMPLETE" if len(peers) >= 2 and len(common_metrics) >= 3 and valuation_common else "INSUFFICIENT_PEERS"
    value = {
        "schema_version": PEER_VERSION, "comparison_id": comparison_id,
        "target_security_id": target_security_id, "decision_cutoff": iso_utc(decision_cutoff),
        "candidate_count": len(candidates), "candidates": [deepcopy(dict(item)) for item in candidates],
        "target": deepcopy(dict(target)),
        "peers": [deepcopy(dict(item)) for item in peers], "coverage_status": coverage,
    }
    value["artifact_hash"] = canonical_hash(value)
    validate_peer_comparison(value)
    return value


def validate_peer_comparison(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != PEER_VERSION or value.get("artifact_hash") != _hash_without(value):
        raise EquityValuationError("PEER_COMPARISON_INVALID")
    if value.get("candidate_count") != len(value.get("candidates", [])) or not 1 <= value["candidate_count"] <= 5:
        raise EquityValuationError("PEER_CANDIDATE_BUDGET_INVALID")
    if len(value.get("peers", [])) > 5:
        raise EquityValuationError("PEER_BUDGET_EXCEEDED")
    cutoff = _require_time(value.get("decision_cutoff"), "decision_cutoff")
    if cutoff > datetime.now(timezone.utc) + timedelta(days=1):
        raise EquityValuationError("PEER_CUTOFF_IMPLAUSIBLE")
    candidate_ids: set[str] = set()
    for candidate in value["candidates"]:
        if candidate.get("status") not in {"INCLUDED", "EXCLUDED_NOT_COMPARABLE", "SOURCE_LIMITED"}:
            raise EquityValuationError("PEER_CANDIDATE_STATUS_INVALID")
        if not candidate.get("security_id") or candidate["security_id"] in candidate_ids:
            raise EquityValuationError("PEER_CANDIDATE_ID_INVALID")
        candidate_ids.add(candidate["security_id"])
        _canonical_ids(candidate.get("evidence_refs"), "candidate.evidence_refs", allow_empty=False)
    peer_ids: set[str] = set()
    included = {item["security_id"] for item in value["candidates"] if item["status"] == "INCLUDED"}
    companies = [value.get("target"), *value["peers"]]
    if not isinstance(companies[0], Mapping) or companies[0].get("security_id") != value.get("target_security_id"):
        raise EquityValuationError("PEER_TARGET_INVALID")
    for index, peer in enumerate(companies):
        if not peer.get("security_id") or peer["security_id"] in peer_ids or (index > 0 and peer["security_id"] not in included):
            raise EquityValuationError("PEER_ID_INVALID")
        peer_ids.add(peer["security_id"])
        metrics = peer.get("metrics", [])
        for metric in metrics:
            if metric.get("status") not in {"COMPARABLE", "LIMITED_COMPARABILITY", "NOT_COMPARABLE", "INPUT_MISSING"}:
                raise EquityValuationError("PEER_METRIC_STATUS_INVALID")
            if metric["status"] in {"COMPARABLE", "LIMITED_COMPARABILITY"} and metric.get("value") is None:
                raise EquityValuationError("PEER_METRIC_VALUE_REQUIRED")
            _canonical_ids(
                metric.get("evidence_refs"), "peer.metric.evidence_refs",
                allow_empty=metric.get("status") == "INPUT_MISSING",
            )
            for field in ("metric_basis_id", "source_id", "as_of", "retrieved_at", "period", "unit"):
                if not metric.get(field):
                    raise EquityValuationError(f"PEER_METRIC_PROVENANCE_MISSING:{field}")
            for field in ("as_of", "retrieved_at", "published_at"):
                if metric.get(field) and _require_time(metric[field], f"peer.metric.{field}") > cutoff:
                    raise EquityValuationError("PEER_METRIC_AFTER_CUTOFF")
            calculation = metric.get("calculation")
            if calculation is not None:
                expected = f"calc:peer-metric:{canonical_hash(calculation)[:16]}"
                if metric.get("calculation_ref") != expected or not metric.get("formula"):
                    raise EquityValuationError("PEER_METRIC_CALCULATION_INVALID")
                input_refs = calculation.get("input_evidence_refs")
                if not isinstance(input_refs, list) or not input_refs or not set(input_refs) <= set(metric.get("evidence_refs", [])):
                    raise EquityValuationError("PEER_METRIC_CALCULATION_EVIDENCE_INVALID")
                formula_version = calculation.get("formula_version")
                if formula_version == "peer-ttm-sum/1.0.0":
                    result = _decimal(calculation.get("annual"), "peer.annual") + _decimal(calculation.get("current_ytd"), "peer.current_ytd") - _decimal(calculation.get("prior_ytd"), "peer.prior_ytd")
                    if _decimal(calculation.get("result"), "peer.result") != result or _decimal(metric.get("value"), "peer.value") != result:
                        raise EquityValuationError("PEER_METRIC_CALCULATION_RESULT_INVALID")
                elif formula_version == "peer-operating-margin/1.0.0":
                    result = _decimal(calculation.get("operating_income"), "peer.operating_income") / _decimal(calculation.get("revenue"), "peer.revenue")
                    if _decimal(metric.get("value"), "peer.value") != result:
                        raise EquityValuationError("PEER_METRIC_CALCULATION_RESULT_INVALID")
                elif formula_version == "peer-price-to-sales/1.0.0":
                    price = _decimal(calculation.get("price"), "peer.price")
                    shares = _decimal(calculation.get("actual_common_shares_outstanding"), "peer.shares")
                    market_cap = _decimal(calculation.get("market_cap"), "peer.market_cap")
                    revenue = _decimal(calculation.get("revenue"), "peer.revenue")
                    price_ref, shares_ref = calculation.get("price_evidence_ref"), calculation.get("shares_evidence_ref")
                    revenue_refs = calculation.get("revenue_evidence_refs")
                    required_refs = {price_ref, shares_ref}
                    required_sources = {
                        calculation.get("price_source_id"), calculation.get("shares_source_id"),
                        calculation.get("revenue_source_id"),
                    }
                    if (
                        None in required_refs or price_ref == shares_ref or not required_refs <= set(input_refs)
                        or not isinstance(revenue_refs, list) or not revenue_refs or not set(revenue_refs) <= set(input_refs)
                        or None in required_sources or any(str(source) not in str(metric.get("source_id")) for source in required_sources)
                        or metric.get("metric_basis_id") != "MARKET_CAP_OVER_GAAP_TTM_REVENUE"
                        or price * shares != market_cap or _decimal(metric.get("value"), "peer.value") != market_cap / revenue
                    ):
                        raise EquityValuationError("PEER_METRIC_CALCULATION_RESULT_INVALID")
                elif formula_version == "validated-snapshot-reference/1.0.0":
                    if not calculation.get("snapshot_id") or not calculation.get("metric_id") or not calculation.get("source_calculation_ref"):
                        raise EquityValuationError("PEER_METRIC_CALCULATION_RESULT_INVALID")
                else:
                    raise EquityValuationError("PEER_METRIC_FORMULA_VERSION_INVALID")
            elif metric.get("calculation_ref") is not None or metric.get("formula") is not None:
                raise EquityValuationError("PEER_METRIC_CALCULATION_INVALID")
        ttm_revenues = [
            metric for metric in metrics
            if metric.get("name") == "revenue"
            and metric.get("metric_basis_id") == "GAAP_TTM_REVENUE"
            and metric.get("status") in {"COMPARABLE", "LIMITED_COMPARABILITY"}
        ]
        if len(ttm_revenues) > 1:
            raise EquityValuationError("PEER_TTM_REVENUE_AMBIGUOUS")
        if ttm_revenues:
            revenue_metric = ttm_revenues[0]
            revenue_value = _decimal(revenue_metric.get("value"), "peer.ttm_revenue")
            revenue_period = revenue_metric.get("period")
            revenue_calculation = revenue_metric.get("calculation")
            if (
                not isinstance(revenue_calculation, Mapping)
                or revenue_calculation.get("formula_version") != "peer-ttm-sum/1.0.0"
                or _decimal(revenue_calculation.get("result"), "peer.ttm_revenue.result") != revenue_value
            ):
                raise EquityValuationError("PEER_TTM_REVENUE_BINDING_INVALID")
            for dependent in metrics:
                basis_id = dependent.get("metric_basis_id")
                if basis_id not in {"GAAP_TTM_OPERATING_MARGIN", "MARKET_CAP_OVER_GAAP_TTM_REVENUE"}:
                    continue
                calculation = dependent.get("calculation")
                if (
                    not isinstance(calculation, Mapping)
                    or dependent.get("period") != revenue_period
                    or _decimal(calculation.get("revenue"), "peer.dependent.revenue") != revenue_value
                    or not set(revenue_metric.get("evidence_refs", [])) <= set(dependent.get("evidence_refs", []))
                ):
                    raise EquityValuationError("PEER_TTM_REVENUE_BINDING_INVALID")
    metric_sets = [
        {(metric.get("name"), metric.get("metric_basis_id"), metric.get("unit")) for metric in company.get("metrics", []) if metric.get("status") in {"COMPARABLE", "LIMITED_COMPARABILITY"}}
        for company in companies
    ]
    common_metrics = set.intersection(*metric_sets) if metric_sets else set()
    valuation_common = any(
        name in {"trailing_pe", "price_to_sales", "price_to_book", "fcf_yield", "ev_to_ebitda"}
        and (name != "price_to_sales" or basis_id == "MARKET_CAP_OVER_GAAP_TTM_REVENUE")
        for name, basis_id, _unit in common_metrics
    )
    expected_coverage = "COMPLETE" if len(value["peers"]) >= 2 and len(common_metrics) >= 3 and valuation_common else "INSUFFICIENT_PEERS"
    if value.get("coverage_status") != expected_coverage:
        raise EquityValuationError("PEER_COVERAGE_STATUS_INVALID")
