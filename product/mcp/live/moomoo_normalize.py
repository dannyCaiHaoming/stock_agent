"""Moomoo SG 官方 OpenD Quote 响应的供应商语义标准化。"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from product.mcp.live.research_supplement import build_supplement_fact
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


ADAPTER_VERSION = "moomoo-opend-research-normalization/1.2.0"


def _semantic_key(prefix: str, *parts: Any) -> str:
    return f"{prefix}:{content_hash([str(part) for part in parts])[:16]}"


def _decimal(value: Any, field: str, *, positive: bool = False) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"MOOMOO_VALUE_INVALID:{field}") from exc
    if not number.is_finite() or positive and number <= 0:
        raise ValueError(f"MOOMOO_VALUE_INVALID:{field}")
    return format(number, "f")


def _optional_decimal(value: Any, field: str) -> str | None:
    if value in (None, "", "N/A", "--"):
        return None
    return _decimal(value, field)


def normalize_company_profile(
    profile: Mapping[str, Any], *, security_id: str, ticker: str,
    retrieved_at: str, raw_content_hash: str, source_locator: str,
    source_version: str = ADAPTER_VERSION,
) -> dict[str, Any]:
    required = {"symbol", "legal_name", "business_summary"}
    if not required <= set(profile) or profile["symbol"] != ticker:
        raise ValueError("MOOMOO_PROFILE_SECURITY_MISMATCH")
    value = {
        "legal_name": profile["legal_name"],
        "business_summary": profile["business_summary"],
        "industry": profile.get("industry"),
        "sector": profile.get("sector"),
        "classification_system": profile.get("classification_system", "MOOMOO_PROVIDER_CLASSIFICATION"),
        "headquarters": profile.get("headquarters"),
        "website": profile.get("website"),
        "employees": profile.get("employees"),
        "employee_as_of": profile.get("employee_as_of"),
    }
    fact = build_supplement_fact(
        security_id=security_id, dataset="identity_profile",
        semantic_field="moomoo_company_profile", value=value,
        source_id=f"moomoo-sg-profile:{ticker}", source_family="moomoo_sg",
        source_locator=source_locator, source_version=source_version,
        as_of=profile.get("as_of", retrieved_at),
        published_at=profile.get("published_at", retrieved_at),
        retrieved_at=retrieved_at, raw_content_hash=raw_content_hash,
        limitations=[
            "供应商当前档案；行业体系与 SEC/Yahoo 分开保留",
            "缺少 employee_as_of 时员工数不得用于历史比较",
        ] + (["员工数缺少明确时点"] if value["employees"] is not None and value["employee_as_of"] is None else []),
    )
    return {"adapter_version": ADAPTER_VERSION, "evidence": [fact], "gaps": []}


def normalize_money_flow_rows(
    rows: Sequence[Mapping[str, Any]], *, security_id: str, ticker: str,
    retrieved_at: str, raw_content_hash: str, source_locator: str,
    source_version: str = ADAPTER_VERSION,
) -> dict[str, Any]:
    evidence, gaps, seen = [], [], set()
    retrieved = iso_utc(retrieved_at)
    for row in rows:
        required = {"category", "amount", "currency", "unit", "period_start", "period_end", "as_of", "definition"}
        if not required <= set(row):
            raise ValueError("MOOMOO_MONEY_FLOW_FIELDS_MISSING")
        key = (row["category"], row["period_start"], row["period_end"])
        if key in seen:
            raise ValueError("MOOMOO_MONEY_FLOW_DUPLICATE")
        seen.add(key)
        if row["currency"] not in {"USD", "SGD", "HKD"} or not row["unit"] or not row["definition"]:
            raise ValueError("MOOMOO_MONEY_FLOW_SEMANTICS_INVALID")
        value = {
            "category": row["category"],
            "amount": _decimal(row["amount"], "amount"),
            "currency": row["currency"],
            "unit": row["unit"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "definition": row["definition"],
            "provider_direction_label": row.get("direction_label"),
            "provider_valid_time": row.get("provider_valid_time"),
        }
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="vendor_money_flow",
            semantic_field=f"moomoo_vendor_money_flow:{row['category']}", value=value,
            source_id=f"moomoo-sg-money-flow:{ticker}", source_family="moomoo_sg",
            source_locator=source_locator, source_version=source_version,
            as_of=row["as_of"], published_at=row.get("published_at", row["as_of"]),
            retrieved_at=retrieved, raw_content_hash=raw_content_hash,
            limitations=[
                "供应商分类定义按原样保留；类别标签不证明真实买卖方身份",
                "不得由正负号推断未来资金方向或投资结论",
            ],
        ))
    if not evidence:
        gaps.append({"reason": "MOOMOO_MONEY_FLOW_EMPTY"})
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": gaps}


def normalize_institutional_rows(
    rows: Sequence[Mapping[str, Any]], *, security_id: str, ticker: str,
    retrieved_at: str, raw_content_hash: str, source_locator: str,
    source_version: str = ADAPTER_VERSION,
) -> dict[str, Any]:
    evidence, periods = [], set()
    for row in rows:
        required = {"holder_name", "report_period", "position", "unit", "as_of", "source_declaration"}
        if not required <= set(row) or not row["holder_name"] or not row["source_declaration"]:
            raise ValueError("MOOMOO_INSTITUTION_FIELDS_MISSING")
        periods.add(row["report_period"])
        value = {
            "holder_name": row["holder_name"], "report_period": row["report_period"],
            "position": _decimal(row["position"], "position"), "unit": row["unit"],
            "change": _decimal(row["change"], "change") if row.get("change") is not None else None,
            "source_declaration": row["source_declaration"],
        }
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="institutional_ownership",
            semantic_field=_semantic_key(
                "moomoo_institutional_holding", row["holder_name"], row["report_period"],
            ), value=value,
            source_id=f"moomoo-sg-institutional:{ticker}", source_family="moomoo_sg",
            source_locator=source_locator, source_version=source_version,
            as_of=row["as_of"], published_at=row.get("published_at", row["as_of"]),
            retrieved_at=retrieved_at, raw_content_hash=raw_content_hash,
            limitations=["二级供应商资料；原始申报与修订状态应以 SEC 为主", "覆盖集合不代表全市场机构持仓"],
        ))
    gaps = []
    if len(periods) < 2:
        gaps.append({"reason": "MOOMOO_INSTITUTION_SINGLE_PERIOD_ONLY", "periods": sorted(periods)})
    return {
        "adapter_version": ADAPTER_VERSION, "coverage": "SUPPLEMENTAL_NOT_AUTHORITATIVE",
        "periods": sorted(periods), "evidence": evidence, "gaps": gaps,
    }


def normalize_option_rows(
    rows: Sequence[Mapping[str, Any]], *, security_id: str, ticker: str,
    retrieved_at: str, raw_content_hash: str, source_locator: str,
    source_version: str = ADAPTER_VERSION,
) -> dict[str, Any]:
    evidence, gaps = [], []
    for row in rows:
        required = {"contract_symbol", "option_type", "expiration", "strike", "as_of"}
        if not required <= set(row) or row["option_type"] not in {"CALL", "PUT"}:
            raise ValueError("MOOMOO_OPTION_FIELDS_INVALID")
        value = {
            "contract_symbol": row["contract_symbol"], "option_type": row["option_type"],
            "expiration": row["expiration"], "strike": _decimal(row["strike"], "strike", positive=True),
            "bid": _decimal(row["bid"], "bid") if row.get("bid") is not None else None,
            "ask": _decimal(row["ask"], "ask") if row.get("ask") is not None else None,
            "volume": _decimal(row["volume"], "volume") if row.get("volume") is not None else None,
            "open_interest": _decimal(row["open_interest"], "open_interest") if row.get("open_interest") is not None else None,
            "implied_volatility": _decimal(row["implied_volatility"], "implied_volatility") if row.get("implied_volatility") is not None else None,
            "provider_quote_time": row.get("quote_time"),
            "provider_open_interest_time": row.get("open_interest_time"),
        }
        if value["bid"] is not None and value["ask"] is not None and Decimal(value["ask"]) < Decimal(value["bid"]):
            raise ValueError("MOOMOO_OPTION_CROSSED_QUOTE")
        if value["provider_quote_time"] is None:
            gaps.append({"reason": "MOOMOO_OPTION_QUOTE_TIME_MISSING", "contract_symbol": row["contract_symbol"]})
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="options_snapshot",
            semantic_field=_semantic_key(
                "moomoo_option_contract", row["contract_symbol"], row["as_of"],
            ), value=value,
            source_id=f"moomoo-sg-options:{ticker}", source_family="moomoo_sg",
            source_locator=source_locator, source_version=source_version,
            as_of=row["as_of"], published_at=row.get("published_at", row["as_of"]),
            retrieved_at=retrieved_at, raw_content_hash=raw_content_hash,
            limitations=["Moomoo SG 二级期权快照；不得与 Yahoo 不同时点报价静默拼接", "成交方向不可由 volume/OI 推断"],
        ))
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": gaps}


def normalize_research_rows(
    rows: Sequence[Mapping[str, Any]], *, security_id: str, ticker: str,
    retrieved_at: str, raw_content_hash: str, source_locator: str,
    source_version: str = ADAPTER_VERSION,
) -> dict[str, Any]:
    tiers = {"METADATA", "ABSTRACT", "REPUBLISHED_EXCERPT", "FULL_TEXT"}
    evidence, gaps = [], []
    for row in rows:
        required = {"title", "publisher", "published_at", "content_tier", "as_of"}
        if not required <= set(row) or row["content_tier"] not in tiers:
            raise ValueError("MOOMOO_RESEARCH_FIELDS_INVALID")
        if row["content_tier"] == "FULL_TEXT" and row.get("content_permission") != "VERIFIED_REUSABLE":
            raise ValueError("MOOMOO_RESEARCH_FULL_TEXT_PERMISSION_REQUIRED")
        value = {
            "title": row["title"], "publisher": row["publisher"],
            "rating": row.get("rating"), "summary": row.get("summary"),
            "content_tier": row["content_tier"], "original_source_url": row.get("original_source_url"),
            "content_permission": row.get("content_permission", "UNKNOWN"),
        }
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="research_discovery",
            semantic_field=_semantic_key(
                "moomoo_research_item", row["publisher"], row["title"], row["published_at"],
            ), value=value,
            source_id=f"moomoo-sg-research:{ticker}", source_family="moomoo_sg",
            source_locator=source_locator, source_version=source_version,
            as_of=row["as_of"], published_at=row["published_at"], retrieved_at=retrieved_at,
            raw_content_hash=raw_content_hash,
            limitations=["单篇资料不构成研报对比", "转载、摘要与原始正文层级不得混同"],
        ))
    if len(evidence) < 2:
        gaps.append({"reason": "RESEARCH_COMPARISON_NOT_COMPLETE", "item_count": len(evidence)})
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": gaps}


def normalize_expectation_rows(
    rows: Sequence[Mapping[str, Any]], *, security_id: str, ticker: str,
    retrieved_at: str, raw_content_hash: str, source_locator: str,
    source_version: str = ADAPTER_VERSION,
) -> dict[str, Any]:
    evidence, gaps = [], []
    for row in rows:
        required = {"fiscal_period", "metric", "average", "accounting_basis", "as_of"}
        if not required <= set(row) or row["metric"] not in {"EPS", "REVENUE"} \
                or row["accounting_basis"] not in {"GAAP", "NON_GAAP", "UNKNOWN"}:
            raise ValueError("MOOMOO_EXPECTATION_FIELDS_INVALID")
        value = {
            "fiscal_period": row["fiscal_period"], "metric": row["metric"],
            "average": _decimal(row["average"], "average"),
            "low": _decimal(row["low"], "low") if row.get("low") is not None else None,
            "high": _decimal(row["high"], "high") if row.get("high") is not None else None,
            "number_of_analysts": row.get("number_of_analysts"),
            "accounting_basis": row["accounting_basis"],
            "vintage_at": row.get("vintage_at"),
            "rating": row.get("rating"), "target_price": row.get("target_price"),
        }
        limitations = ["供应商一致预期，不是发行人指引"]
        if value["vintage_at"] is None:
            limitations.append("历史 vintage 未知，禁止形成实际值相对预期差")
        if value["accounting_basis"] == "UNKNOWN":
            limitations.append("GAAP/非 GAAP 口径未知，禁止与 SEC 实际值直接比较")
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="analyst_expectations",
            semantic_field=_semantic_key(
                "moomoo_analyst_expectation", row["fiscal_period"], row["metric"], row["as_of"],
            ), value=value,
            source_id=f"moomoo-sg-expectations:{ticker}", source_family="moomoo_sg",
            source_locator=source_locator, source_version=source_version,
            as_of=row["as_of"], published_at=row.get("published_at", row["as_of"]),
            retrieved_at=retrieved_at, raw_content_hash=raw_content_hash,
            limitations=limitations,
        ))
    if not evidence:
        gaps.append({"reason": "MOOMOO_EXPECTATIONS_EMPTY"})
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": gaps}


def _capture_rows(capture: Mapping[str, Any], *, method: str) -> list[Mapping[str, Any]]:
    if capture.get("method") != method or capture.get("region") != "SG" \
            or capture.get("security_market") != "US" \
            or not isinstance(capture.get("payload"), Mapping) \
            or capture["payload"].get("kind") != "DATAFRAME" \
            or not isinstance(capture["payload"].get("rows"), list):
        raise ValueError("MOOMOO_OPEND_CAPTURE_INVALID")
    return capture["payload"]["rows"]


def _capture_dict(capture: Mapping[str, Any], *, method: str) -> Mapping[str, Any]:
    if capture.get("method") != method or capture.get("region") != "SG" \
            or capture.get("security_market") != "US" \
            or not isinstance(capture.get("payload"), Mapping) \
            or capture["payload"].get("kind") != "DICT" \
            or not isinstance(capture["payload"].get("value"), Mapping):
        raise ValueError("MOOMOO_OPEND_CAPTURE_INVALID")
    return capture["payload"]["value"]


def _capture_attrs(capture: Mapping[str, Any], *, method: str) -> Mapping[str, Any]:
    _capture_rows(capture, method=method)
    attrs = capture["payload"].get("attrs", {})
    if not isinstance(attrs, Mapping):
        raise ValueError("MOOMOO_OPEND_CAPTURE_ATTRS_INVALID")
    return attrs


def _capture_source_version(capture: Mapping[str, Any]) -> str:
    return (
        f"{ADAPTER_VERSION};opend/{capture.get('server_version') or 'unverified'};"
        f"sdk/{capture.get('sdk_version')};"
        f"method/{capture.get('method')};manifest/{str(capture.get('manifest_hash'))[:16]}"
    )


def _market_time(value: str, *, market: str = "US") -> str:
    if not isinstance(value, str):
        raise ValueError("MOOMOO_OPEND_TIME_INVALID")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("MOOMOO_OPEND_TIME_INVALID") from exc
    zone = ZoneInfo("America/New_York") if market == "US" else timezone.utc
    return iso_utc(parsed.replace(tzinfo=zone))


def _unix_time(value: Any) -> str:
    try:
        timestamp = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("MOOMOO_OPEND_TIME_INVALID") from exc
    if timestamp > 100_000_000_000_000:
        timestamp //= 1_000_000
    elif timestamp > 100_000_000_000:
        timestamp //= 1_000
    return iso_utc(datetime.fromtimestamp(timestamp, tz=timezone.utc))


def _date_time(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("MOOMOO_OPEND_DATE_INVALID")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("MOOMOO_OPEND_DATE_INVALID") from exc
    return iso_utc(parsed.replace(tzinfo=timezone.utc))


def _provider_as_of(value: Any, retrieved_at: str) -> tuple[str, dict[str, Any] | None]:
    provider_time = _unix_time(value)
    if parse_timestamp(provider_time) <= parse_timestamp(retrieved_at):
        return provider_time, None
    return iso_utc(retrieved_at), {
        "reason": "MOOMOO_PROVIDER_CLOCK_AHEAD_OF_RETRIEVAL",
        "provider_time": provider_time,
        "retrieved_at": iso_utc(retrieved_at),
    }


def normalize_opend_company_profile(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    rows = _capture_rows(capture, method="get_company_profile")
    values = {
        str(row.get("name")): row.get("value")
        for row in rows if row.get("name") is not None
    }
    code = values.get("公司代码", values.get("Company Code"))
    if code != ticker or capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_PROFILE_SECURITY_MISMATCH")
    name = values.get("公司名称", values.get("Company Name"))
    summary = values.get("公司简介", values.get("Company Profile"))
    if not name or not summary:
        raise ValueError("MOOMOO_PROFILE_FIELDS_MISSING")
    employee_value = values.get("员工数量", values.get("Employees"))
    try:
        employees = int(employee_value) if employee_value not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise ValueError("MOOMOO_PROFILE_EMPLOYEES_INVALID") from exc
    value = {
        "provider_company_code": code,
        "provider_display_name": name,
        "business_summary": summary,
        "listing_date": values.get("上市日期", values.get("Listing Date")),
        "isin": values.get("ISIN代码", values.get("ISIN")),
        "founded": values.get("成立日期", values.get("Founded")),
        "chief_executive": values.get("CEO"),
        "listing_market": values.get("所属市场", values.get("Market")),
        "employees": employees,
        "fiscal_year_end": values.get("年结日", values.get("Fiscal Year End")),
        "address": values.get("公司地址", values.get("Address")),
        "city": values.get("城市", values.get("City")),
        "region": values.get("省份", values.get("State")),
        "country": values.get("国家", values.get("Country")),
        "postal_code": values.get("邮编", values.get("Postal Code")),
        "website": values.get("网址", values.get("Website")),
    }
    fact = build_supplement_fact(
        security_id=security_id, dataset="identity_profile",
        semantic_field="moomoo_company_profile", value=value,
        source_id=f"moomoo-sg-opend-profile:{ticker}", source_family="moomoo_sg",
        source_locator=f"moomoo-opend://get_company_profile/US.{ticker}",
        source_version=_capture_source_version(capture),
        as_of=capture["retrieved_at"], published_at=capture["retrieved_at"],
        retrieved_at=capture["retrieved_at"], raw_content_hash=capture["raw_content_hash"],
        limitations=[
            "Moomoo 当前供应商档案，不替代 SEC 法定名称与原始披露",
            "员工数和当前高管缺少独立历史生效区间，不用于历史 cutoff 回填",
            "供应商界面语言影响名称与摘要文本",
        ],
    )
    return {"adapter_version": ADAPTER_VERSION, "evidence": [fact], "gaps": []}


def normalize_opend_capital_flow(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    rows = _capture_rows(capture, method="get_capital_flow")
    if capture.get("security_code") != f"US.{ticker}" or not rows:
        raise ValueError("MOOMOO_MONEY_FLOW_SECURITY_MISMATCH")
    required = {
        "last_valid_time", "in_flow", "super_in_flow", "big_in_flow",
        "mid_in_flow", "sml_in_flow", "main_in_flow", "capital_flow_item_time",
    }
    if any(not required <= set(row) for row in rows):
        raise ValueError("MOOMOO_MONEY_FLOW_FIELDS_MISSING")
    retrieved_at = parse_timestamp(capture["retrieved_at"])
    eligible_rows = [
        row for row in rows
        if parse_timestamp(_market_time(row["capital_flow_item_time"])) <= retrieved_at
    ]
    if not eligible_rows:
        return {
            "adapter_version": ADAPTER_VERSION, "evidence": [],
            "gaps": [{
                "reason": "MOOMOO_FLOW_NO_COMPLETED_INTERVAL",
                "raw_row_count": len(rows), "retrieved_at": capture["retrieved_at"],
            }],
            "coverage": {
                "raw_row_count": len(rows), "eligible_row_count": 0,
                "market_timezone": "America/New_York",
            },
        }
    first, last = eligible_rows[0], eligible_rows[-1]
    period_start = _market_time(first["capital_flow_item_time"])
    period_end = _market_time(last["capital_flow_item_time"])
    raw_valid_time = last["last_valid_time"]
    observed_at = (
        _market_time(raw_valid_time)
        if raw_valid_time not in (None, "", "N/A", "--") else None
    )
    definitions = {
        "overall": ("in_flow", "Moomoo overall net capital inflow"),
        "extra_large_order": ("super_in_flow", "Moomoo extra-large orders net inflow"),
        "large_order": ("big_in_flow", "Moomoo large orders net inflow"),
        "medium_order": ("mid_in_flow", "Moomoo medium orders net inflow"),
        "small_order": ("sml_in_flow", "Moomoo small orders net inflow"),
        "block_order": ("main_in_flow", "Moomoo block orders net inflow; historical periods only"),
    }
    normalized = []
    gaps = []
    excluded_rows = len(rows) - len(eligible_rows)
    if excluded_rows:
        gaps.append({
            "reason": "MOOMOO_FLOW_INCOMPLETE_INTERVAL_EXCLUDED",
            "excluded_row_count": excluded_rows,
            "retrieved_at": capture["retrieved_at"],
        })
    provider_valid_time = observed_at
    if observed_at is None:
        gaps.append({
            "reason": "MOOMOO_PROVIDER_VALID_TIME_UNAVAILABLE",
            "impact": "供应商未返回独立有效时间，Evidence 仅使用已完成区间终点。",
        })
    elif parse_timestamp(observed_at) > retrieved_at:
        provider_valid_time = None
        gaps.append({
            "reason": "MOOMOO_PROVIDER_CLOCK_AHEAD_OF_RETRIEVAL",
            "provider_valid_time": observed_at,
            "retrieved_at": capture["retrieved_at"],
            "impact": "未来的供应商时钟值仅保留在 gap，不进入 Evidence value。",
        })
    for category, (field, definition) in definitions.items():
        amount = last[field]
        if amount in (None, "", "N/A", "--"):
            gaps.append({"reason": "MOOMOO_MONEY_FLOW_FIELD_UNAVAILABLE", "field": field})
            continue
        normalized.append({
            "category": category,
            "amount": amount,
            "currency": "USD",
            "unit": "USD",
            "period_start": period_start,
            "period_end": period_end,
            "as_of": period_end,
            "published_at": capture["retrieved_at"],
            "definition": definition,
            "provider_valid_time": provider_valid_time,
        })
    result = normalize_money_flow_rows(
        normalized, security_id=security_id, ticker=ticker,
        retrieved_at=capture["retrieved_at"], raw_content_hash=capture["raw_content_hash"],
        source_locator=f"moomoo-opend://get_capital_flow/US.{ticker}?period_type=INTRADAY",
        source_version=_capture_source_version(capture),
    )
    result["gaps"].extend(gaps)
    result["coverage"] = {
        "raw_row_count": len(rows),
        "eligible_row_count": len(eligible_rows),
        "period_start": period_start,
        "period_end": period_end,
        "last_valid_time": observed_at,
        "market_timezone": "America/New_York",
    }
    return result


def normalize_opend_analyst_consensus(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    value = _capture_dict(capture, method="get_research_analyst_consensus")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_EXPECTATION_SECURITY_MISMATCH")
    required = {"highest", "average", "lowest", "rating", "total", "update_time", "buy", "hold", "sell"}
    if not required <= set(value):
        raise ValueError("MOOMOO_EXPECTATION_FIELDS_INVALID")
    as_of = _unix_time(value["update_time"])
    fact = build_supplement_fact(
        security_id=security_id, dataset="analyst_expectations",
        semantic_field="moomoo_analyst_consensus", value={
            "target_price_high": _decimal(value["highest"], "highest"),
            "target_price_average": _decimal(value["average"], "average"),
            "target_price_low": _decimal(value["lowest"], "lowest"),
            "rating": value["rating"],
            "analyst_count": value["total"],
            "buy_percent": _decimal(value["buy"], "buy"),
            "hold_percent": _decimal(value["hold"], "hold"),
            "sell_percent": _decimal(value["sell"], "sell"),
            "provider_update_time": value.get("update_time_str"),
        },
        source_id=f"moomoo-sg-opend-consensus:{ticker}", source_family="moomoo_sg",
        source_locator=f"moomoo-opend://get_research_analyst_consensus/US.{ticker}",
        source_version=_capture_source_version(capture),
        as_of=as_of, published_at=as_of, retrieved_at=capture["retrieved_at"],
        raw_content_hash=capture["raw_content_hash"],
        limitations=[
            "供应商当前评级与目标价共识，不是发行人指引或本系统投资动作",
            "返回未提供预测财政期、口径和历史 vintage，禁止生成历史预期差",
        ],
    )
    return {"adapter_version": ADAPTER_VERSION, "evidence": [fact], "gaps": [
        {"reason": "CONSENSUS_FISCAL_PERIOD_NOT_PROVIDED"},
        {"reason": "CONSENSUS_HISTORICAL_VINTAGE_NOT_PROVIDED"},
    ]}


def normalize_opend_morningstar_report(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    value = _capture_dict(capture, method="get_research_morningstar_report")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_RESEARCH_SECURITY_MISMATCH")
    required = {
        "rating_type", "star_rating", "star_update_time", "fair_value",
        "economic_moat_content", "uncertainty_content", "financial_health_content",
        "capital_allocation_content", "investment_thesis_content", "bull_say", "bear_say",
        "analyst_note_content", "analyst_report_update_time",
    }
    if not required <= set(value):
        raise ValueError("MOOMOO_RESEARCH_FIELDS_INVALID")
    as_of = _unix_time(value["analyst_report_update_time"] or value["star_update_time"])
    report_value = {
        "publisher": "Morningstar via Moomoo OpenAPI",
        "content_tier": "LICENSED_API_CONTENT",
        "rating_type": value["rating_type"],
        "star_rating": value["star_rating"],
        "fair_value": value["fair_value"],
        "fair_value_content": value.get("fair_value_content"),
        "economic_moat_label": value.get("economic_moat_label"),
        "economic_moat_content": value["economic_moat_content"],
        "uncertainty_label": value.get("uncertainty_label"),
        "uncertainty_content": value["uncertainty_content"],
        "financial_health_content": value["financial_health_content"],
        "capital_allocation_label": value.get("capital_allocation_label"),
        "capital_allocation_content": value["capital_allocation_content"],
        "investment_thesis_content": value["investment_thesis_content"],
        "bull_say": value["bull_say"],
        "bear_say": value["bear_say"],
        "analyst_note_title": value.get("analyst_note_title"),
        "analyst_note_content": value["analyst_note_content"],
        "provider_update_time": value.get("analyst_report_update_time_str"),
    }
    fact = build_supplement_fact(
        security_id=security_id, dataset="research_discovery",
        semantic_field="moomoo_morningstar_research", value=report_value,
        source_id=f"moomoo-sg-opend-morningstar:{ticker}", source_family="moomoo_sg",
        source_locator=f"moomoo-opend://get_research_morningstar_report/US.{ticker}",
        source_version=_capture_source_version(capture),
        as_of=as_of, published_at=as_of, retrieved_at=capture["retrieved_at"],
        raw_content_hash=capture["raw_content_hash"],
        limitations=[
            "Morningstar 供应商观点，不是 SEC 原始披露或本系统投资结论",
            "通过用户有权访问的 Moomoo OpenAPI 获取，仅限内部研究，不声明再分发许可",
            "单份研究内容不构成跨机构研报对比完成",
        ],
    )
    return {"adapter_version": ADAPTER_VERSION, "evidence": [fact], "gaps": [
        {"reason": "RESEARCH_COMPARISON_NOT_COMPLETE", "item_count": 1}
    ]}


def normalize_opend_institutional_aggregate(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    rows = _capture_rows(capture, method="get_shareholders_institutional")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_INSTITUTION_SECURITY_MISMATCH")
    required = {
        "period_text", "institution_quantity", "institution_quantity_change",
        "holder_quantity", "holder_quantity_change", "holder_pct",
        "holder_pct_change", "next_key", "update_time", "update_time_str",
    }
    evidence, gaps, periods = [], [], set()
    for row in rows:
        if not required <= set(row) or not row["period_text"]:
            raise ValueError("MOOMOO_INSTITUTION_FIELDS_MISSING")
        as_of, clock_gap = _provider_as_of(row["update_time"], capture["retrieved_at"])
        if clock_gap is not None:
            gaps.append(clock_gap)
        period = str(row["period_text"])
        periods.add(period)
        value = {
            "period_label": period,
            "institution_count": row["institution_quantity"],
            "institution_count_change": row["institution_quantity_change"],
            "aggregate_holder_quantity": _optional_decimal(row["holder_quantity"], "holder_quantity"),
            "aggregate_holder_quantity_change": _optional_decimal(
                row["holder_quantity_change"], "holder_quantity_change",
            ),
            "aggregate_holder_percent": _optional_decimal(row["holder_pct"], "holder_pct"),
            "aggregate_holder_percent_change": _optional_decimal(
                row["holder_pct_change"], "holder_pct_change",
            ),
            "provider_update_time": row["update_time_str"],
            "page_next_key": row["next_key"],
            "source_declaration": "Moomoo OpenAPI institutional aggregate",
        }
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="institutional_ownership",
            semantic_field=_semantic_key("moomoo_institutional_aggregate", period),
            value=value, source_id=f"moomoo-sg-opend-institutional:{ticker}",
            source_family="moomoo_sg",
            source_locator=f"moomoo-opend://get_shareholders_institutional/US.{ticker}",
            source_version=_capture_source_version(capture), as_of=as_of,
            published_at=as_of, retrieved_at=capture["retrieved_at"],
            raw_content_hash=capture["raw_content_hash"], limitations=[
                "Moomoo 二级供应商的期间汇总，不是逐管理人 13F 原始申报",
                "period_label 是供应商展示期；当前季度可能未结束，不推定为季度末已披露持仓",
                "机构数与汇总持股变化不得冒充全市场机构覆盖或 SEC 修订关系",
            ],
        ))
    if len(periods) < 2:
        gaps.append({"reason": "MOOMOO_INSTITUTION_SINGLE_PERIOD_ONLY", "periods": sorted(periods)})
    return {
        "adapter_version": ADAPTER_VERSION,
        "coverage": "SECONDARY_VENDOR_AGGREGATE_NOT_13F",
        "periods": sorted(periods), "evidence": evidence, "gaps": gaps,
    }


def normalize_opend_insider_holders(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    rows = _capture_rows(capture, method="get_insider_holder_list")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_INSIDER_SECURITY_MISMATCH")
    required = {
        "holder_id", "holder_quantity", "holder_pct", "name", "title",
        "all_count", "next_key", "insider_total_count", "insider_bought_count",
        "insider_sold_count",
    }
    evidence = []
    for row in rows:
        if not required <= set(row) or not row["holder_id"] or not row["name"]:
            raise ValueError("MOOMOO_INSIDER_HOLDER_FIELDS_MISSING")
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="insider_transactions",
            semantic_field=_semantic_key("moomoo_insider_holder", row["holder_id"]),
            value={
                "holder_id": str(row["holder_id"]), "public_name": row["name"],
                "title": row["title"],
                "holder_quantity": _optional_decimal(row["holder_quantity"], "holder_quantity"),
                "holder_percent": _optional_decimal(row["holder_pct"], "holder_pct"),
                "provider_total_count": row["insider_total_count"],
                "provider_bought_count": row["insider_bought_count"],
                "provider_sold_count": row["insider_sold_count"],
                "page_next_key": row["next_key"],
            },
            source_id=f"moomoo-sg-opend-insider-holder:{ticker}", source_family="moomoo_sg",
            source_locator=f"moomoo-opend://get_insider_holder_list/US.{ticker}",
            source_version=_capture_source_version(capture),
            as_of=capture["retrieved_at"], published_at=capture["retrieved_at"],
            retrieved_at=capture["retrieved_at"], raw_content_hash=capture["raw_content_hash"],
            limitations=[
                "供应商当前内部人持股列表；未提供该持股数的独立生效时间",
                "公开披露人名是研究事实，不是项目登录账号或私人账户资料",
                "交易分类和完整性以 SEC Form 3/4/5 原始申报为准",
            ],
        ))
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": [
        {"reason": "MOOMOO_INSIDER_HOLDER_AS_OF_NOT_PROVIDED"}
    ]}


def normalize_opend_insider_trades(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    rows = _capture_rows(capture, method="get_insider_trade_list")
    attrs = _capture_attrs(capture, method="get_insider_trade_list")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_INSIDER_SECURITY_MISMATCH")
    required = {
        "trade_shares", "min_trade_date", "min_trade_date_str", "max_trade_date",
        "max_trade_date_str", "min_price", "max_price", "security_holder_quantity",
        "is_proposed_sale_of_securities", "holder_id", "name", "title",
        "security_description", "transaction_type", "source_group_name",
    }
    evidence = []
    for row in rows:
        if not required <= set(row) or not row["holder_id"] or not row["name"]:
            raise ValueError("MOOMOO_INSIDER_TRADE_FIELDS_MISSING")
        as_of = _unix_time(row["max_trade_date"])
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="insider_transactions",
            semantic_field=_semantic_key(
                "moomoo_insider_trade", row["holder_id"], row["min_trade_date"],
                row["max_trade_date"], row["transaction_type"], row["security_description"],
            ),
            value={
                "holder_id": str(row["holder_id"]), "public_name": row["name"],
                "title": row["title"], "transaction_type": row["transaction_type"],
                "security_description": row["security_description"],
                "trade_shares": _optional_decimal(row["trade_shares"], "trade_shares"),
                "min_price": _optional_decimal(row["min_price"], "min_price"),
                "max_price": _optional_decimal(row["max_price"], "max_price"),
                "post_transaction_quantity": _optional_decimal(
                    row["security_holder_quantity"], "security_holder_quantity",
                ),
                "trade_date_start": row["min_trade_date_str"],
                "trade_date_end": row["max_trade_date_str"],
                "is_proposed_sale_of_securities": bool(row["is_proposed_sale_of_securities"]),
                "source_group_name": row["source_group_name"],
            },
            source_id=f"moomoo-sg-opend-insider-trade:{ticker}", source_family="moomoo_sg",
            source_locator=f"moomoo-opend://get_insider_trade_list/US.{ticker}",
            source_version=_capture_source_version(capture), as_of=as_of,
            published_at=capture["retrieved_at"], retrieved_at=capture["retrieved_at"],
            raw_content_hash=capture["raw_content_hash"], limitations=[
                "Moomoo 二级供应商交易聚合；min/max 日期可能表示一个聚合区间",
                "transaction_type 按供应商原标签保留，不推断交易动机或未来方向",
                "申报日、交易代码、直接/间接和衍生品细节应以 SEC 原始申报为准",
            ],
        ))
    return {
        "adapter_version": ADAPTER_VERSION, "evidence": evidence,
        "coverage": {"returned_rows": len(rows), "all_count": attrs.get("all_count"),
                     "next_key": attrs.get("next_key")},
        "gaps": ([] if str(attrs.get("next_key", "-1")) == "-1" else [{
            "reason": "MOOMOO_INSIDER_TRADES_MORE_PAGES", "next_key": attrs.get("next_key"),
        }]),
    }


def normalize_opend_option_chain(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    rows = _capture_rows(capture, method="get_option_chain")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_OPTION_SECURITY_MISMATCH")
    required = {
        "code", "name", "lot_size", "stock_type", "option_type", "stock_owner",
        "strike_time", "strike_price", "suspension", "stock_id", "index_option_type",
        "expiration_cycle", "option_standard_type", "option_settlement_mode",
    }
    evidence, expirations = [], set()
    for row in rows:
        if not required <= set(row) or row["stock_owner"] != f"US.{ticker}" \
                or row["option_type"] not in {"CALL", "PUT"}:
            raise ValueError("MOOMOO_OPTION_FIELDS_INVALID")
        expirations.add(str(row["strike_time"]))
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="options_snapshot",
            semantic_field=_semantic_key("moomoo_static_option_contract", row["code"]),
            value={
                "snapshot_kind": "STATIC_CONTRACT_CHAIN", "contract_symbol": row["code"],
                "provider_name": row["name"], "underlying": row["stock_owner"],
                "option_type": row["option_type"], "expiration": row["strike_time"],
                "strike": _decimal(row["strike_price"], "strike_price", positive=True),
                "lot_size": row["lot_size"], "stock_type": row["stock_type"],
                "suspension": bool(row["suspension"]),
                "expiration_cycle": row["expiration_cycle"],
                "option_standard_type": row["option_standard_type"],
                "option_settlement_mode": row["option_settlement_mode"],
                "bid": None, "ask": None, "last": None, "volume": None,
                "open_interest": None, "implied_volatility": None, "greeks": None,
            },
            source_id=f"moomoo-sg-opend-option-chain:{ticker}", source_family="moomoo_sg",
            source_locator=f"moomoo-opend://get_option_chain/US.{ticker}",
            source_version=_capture_source_version(capture),
            as_of=capture["retrieved_at"], published_at=capture["retrieved_at"],
            retrieved_at=capture["retrieved_at"], raw_content_hash=capture["raw_content_hash"],
            limitations=[
                "该 OpenAPI 响应仅含静态合约属性，不是动态报价快照",
                "bid/ask/last/volume/OI/IV/Greeks 不可用，不补零且不与 Yahoo 静默拼接",
            ],
        ))
    return {
        "adapter_version": ADAPTER_VERSION, "evidence": evidence,
        "coverage": {"contract_count": len(evidence), "expirations": sorted(expirations)},
        "gaps": [{"reason": "MOOMOO_OPTION_DYNAMIC_FIELDS_UNAVAILABLE"}],
    }


def normalize_opend_rating_summary(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    value = _capture_dict(capture, method="get_research_rating_summary")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_RESEARCH_SECURITY_MISMATCH")
    summaries = value.get("inst_rating_summary_list")
    if not isinstance(summaries, list) or "next_key" not in value:
        raise ValueError("MOOMOO_RATING_FIELDS_INVALID")
    evidence, gaps = [], []
    for summary in summaries:
        info = summary.get("institution_info")
        items = summary.get("rating_item_list")
        if not isinstance(info, Mapping) or not isinstance(items, list) \
                or not info.get("institution_uid") or not info.get("institution_name"):
            raise ValueError("MOOMOO_RATING_FIELDS_INVALID")
        for item in items:
            required = {"recommendation_date", "recommendation_date_str", "rating", "update_time"}
            if not required <= set(item):
                raise ValueError("MOOMOO_RATING_FIELDS_INVALID")
            as_of = _unix_time(item["recommendation_date"])
            evidence.append(build_supplement_fact(
                security_id=security_id, dataset="research_discovery",
                semantic_field=_semantic_key(
                    "moomoo_rating_item", info["institution_uid"], item["recommendation_date"],
                    item["rating"], item.get("target_price"),
                ),
                value={
                    "content_tier": "RATING_SUMMARY",
                    "institution_uid": str(info["institution_uid"]),
                    "institution_name": info["institution_name"],
                    "institution_en_name": info.get("institution_en_name"),
                    "institution_source_name": info.get("institution_source_name"),
                    "recommendation_date": item["recommendation_date_str"],
                    "rating": item["rating"],
                    "target_price": _optional_decimal(item.get("target_price"), "target_price"),
                    "rating_url": item.get("rating_url"),
                    "provider_update_time": item.get("update_time_str"),
                },
                source_id=f"moomoo-sg-opend-rating:{ticker}", source_family="moomoo_sg",
                source_locator=f"moomoo-opend://get_research_rating_summary/US.{ticker}",
                source_version=_capture_source_version(capture), as_of=as_of,
                published_at=as_of, retrieved_at=capture["retrieved_at"],
                raw_content_hash=capture["raw_content_hash"], limitations=[
                    "机构评级和目标价是外部观点，不是本系统投资动作",
                    "评级摘要不是研报正文；不声明 rating_url 内容的再分发许可",
                    "供应商分页列表不证明机构覆盖完整",
                ],
            ))
    if str(value["next_key"]) != "-1":
        gaps.append({"reason": "MOOMOO_RATING_MORE_PAGES", "next_key": value["next_key"]})
    if not evidence:
        gaps.append({"reason": "MOOMOO_RATING_ITEMS_EMPTY"})
    gaps.append({"reason": "RATING_SUMMARY_IS_NOT_RESEARCH_FULL_TEXT"})
    return {"adapter_version": ADAPTER_VERSION, "evidence": evidence, "gaps": gaps}


def normalize_opend_short_interest(
    capture: Mapping[str, Any], *, security_id: str, ticker: str,
) -> dict[str, Any]:
    rows = _capture_rows(capture, method="get_short_interest")
    attrs = _capture_attrs(capture, method="get_short_interest")
    if capture.get("security_code") != f"US.{ticker}":
        raise ValueError("MOOMOO_SHORT_SECURITY_MISMATCH")
    required = {
        "timestamp", "timestamp_str", "shares_short", "short_percent",
        "avg_daily_share_volume", "days_to_cover", "close_price", "last_close_price",
    }
    evidence = []
    for row in rows:
        if not required <= set(row):
            raise ValueError("MOOMOO_SHORT_FIELDS_INVALID")
        as_of = _unix_time(row["timestamp"])
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="share_short_context",
            semantic_field=_semantic_key("moomoo_short_interest", row["timestamp"]),
            value={
                "statistic_type": "SHORT_INTEREST",
                "statistics_date": row["timestamp_str"],
                "shares_short": _optional_decimal(row["shares_short"], "shares_short"),
                "short_percent": _optional_decimal(row["short_percent"], "short_percent"),
                "average_daily_share_volume": _optional_decimal(
                    row["avg_daily_share_volume"], "avg_daily_share_volume",
                ),
                "days_to_cover": _optional_decimal(row["days_to_cover"], "days_to_cover"),
                "close_price": _optional_decimal(row["close_price"], "close_price"),
                "last_close_price": _optional_decimal(row["last_close_price"], "last_close_price"),
                "borrow_fee": None,
            },
            source_id=f"moomoo-sg-opend-short-interest:{ticker}", source_family="moomoo_sg",
            source_locator=f"moomoo-opend://get_short_interest/US.{ticker}",
            source_version=_capture_source_version(capture), as_of=as_of,
            published_at=capture["retrieved_at"], retrieved_at=capture["retrieved_at"],
            raw_content_hash=capture["raw_content_hash"], limitations=[
                "short interest 与 short volume 是不同口径，不得互换",
                "未提供借券费率，不推算借券成本或挤空评分",
                "Moomoo 为二级供应商快照，统计定义和修订应保留来源版本",
            ],
        ))
    return {
        "adapter_version": ADAPTER_VERSION, "evidence": evidence,
        "gaps": ([] if str(attrs.get("next_key", "-1")) == "-1" else [{
            "reason": "MOOMOO_SHORT_INTEREST_MORE_PAGES", "next_key": attrs.get("next_key"),
        }]),
    }
