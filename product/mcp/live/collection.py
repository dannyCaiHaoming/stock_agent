"""持仓范围内的先采集后冻结；仅调用数据适配，不调用模型。"""
from datetime import date, datetime, UTC, timedelta
from decimal import Decimal
from pathlib import Path
import json
from uuid import uuid4

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import external_path, validate_contract, normalize_sec_fact, compare_live_financials, require_source_admission, source_is_admitted
from product.mcp.live.identity import freeze_identity
from product.mcp.live.market import collect_daily, ExchangeCalendar, MARKET_VERSION, YFINANCE_VERSION
from product.mcp.live.sec import ADAPTER_VERSION
from product.mcp.live.sec_client import SecClient, CLIENT_VERSION
from product.mcp.live.security_metadata import parse_chart_identity, bind_disclosure_security, METADATA_VERSION
from product.mcp.provenance import iso_utc, parse_timestamp
from product.runtime.live_input import freeze_snapshot, load_live_portfolio

COLLECTION_VERSION = "live-collection/3.0.6"
FINANCIAL_TAGS = {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                  "NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities", "CashAndCashEquivalentsAtCarryingValue",
                  "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "LongTermDebtCurrent",
                  "LongTermDebtNoncurrent", "LongTermDebt", "ShortTermBorrowings", "DebtCurrent",
                  "EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted",
                  "GrossProfit", "OperatingIncomeLoss",
                  "PaymentsToAcquirePropertyPlantAndEquipment",
                  "PaymentsForAdditionsToPropertyPlantAndEquipment",
                  "DepreciationDepletionAndAmortization", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment",
                  "ShareBasedCompensation", "StockBasedCompensation",
                  "WeightedAverageNumberOfDilutedSharesOutstanding",
                  "CommonStockSharesOutstanding", "CommonStocksIncludingAdditionalPaidInCapital",
                  "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
                  "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
                  "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
                  "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
                  "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
                  "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
                  "Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent",
                  "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                  "AccountsReceivableNetCurrent", "InventoryNet", "AccountsPayableCurrent",
                  "ResearchAndDevelopmentExpense", "InterestExpense", "InterestExpenseNonOperating",
                  "PaymentsOfDividends", "PaymentsForRepurchaseOfCommonStock",
                  "CommonStockDividendsPerShareDeclared", "PropertyPlantAndEquipmentNet",
                  "RetainedEarningsAccumulatedDeficit"}


def _financial_period_bucket(fact):
    form = fact["form"].removesuffix("/A")
    fiscal_period = fact.get("fiscal_period")
    if form == "10-K" or fiscal_period == "FY":
        return "annual"
    if form == "10-Q":
        if fact["context_type"] == "instant":
            return "independent_quarter"
        if fact.get("period_start"):
            days = (date.fromisoformat(fact["period_end"]) - date.fromisoformat(fact["period_start"])).days
            if days <= 120:
                return "independent_quarter"
        return "cumulative_quarter"
    return "other"


def _select_financial_periods(values, *, annual_limit=3, quarter_limit=8, other_limit=8):
    """按期间选取并保留同一期间的全部修订，不静默挑选一个 accession。"""
    by_bucket = {}
    for fact in values:
        by_bucket.setdefault(_financial_period_bucket(fact), []).append(fact)
    selected, omitted = [], 0
    limits = {
        "annual": annual_limit,
        "independent_quarter": quarter_limit,
        "cumulative_quarter": quarter_limit,
        "other": other_limit,
    }
    for bucket, rows in sorted(by_bucket.items()):
        periods = sorted({row["period_end"] for row in rows}, reverse=True)
        accepted_periods = set(periods[:limits[bucket]])
        accepted = [row for row in rows if row["period_end"] in accepted_periods]
        selected.extend(accepted)
        omitted += len(rows) - len(accepted)
    selected.sort(
        key=lambda f: (f["period_end"], f.get("period_start") or "", f["published_at"], f["evidence_id"]),
        reverse=True,
    )
    return selected, omitted


def research_financials(raw_facts, *, security_id, selection_time):
    """有限标准字段/期间选择，不作投资评分；截断与不可比均明示。"""
    cutoff = parse_timestamp(selection_time)
    groups, facts, gaps = {}, [], []
    unsupported_taxonomy = 0
    for fact in raw_facts:
        if fact["taxonomy"] != "us-gaap":
            unsupported_taxonomy += 1
            continue
        if fact["tag"] not in FINANCIAL_TAGS:
            continue
        if (cutoff - parse_timestamp(fact["as_of"])).days > 1200:
            continue
        key = (fact["tag"], fact["unit"], fact["context_type"], fact["form"].removesuffix("/A"))
        groups.setdefault(key, []).append(fact)
    for key, values in sorted(groups.items()):
        selected, omitted = _select_financial_periods(values)
        for index, fact in enumerate(selected):
            facts.append(normalize_sec_fact(fact, security_id=security_id, usage="current" if index == 0 else "comparison"))
        if omitted:
            gaps.append({"security_id": security_id, "reason": "FINANCIAL_SELECTION_TRUNCATED", "group": list(key), "omitted_count": omitted})
    if unsupported_taxonomy:
        gaps.append({
            "security_id": security_id, "reason": "UNSUPPORTED_TAXONOMY_EXCLUDED",
            "count": unsupported_taxonomy,
        })
    if not facts:
        gaps.append({"security_id": security_id, "reason": "STANDARD_FINANCIALS_MISSING"})
    expected = {
        "revenue": {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"},
        "net_income": {"NetIncomeLoss"},
        "operating_cash_flow": {"NetCashProvidedByUsedInOperatingActivities"},
        "cash": {"CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"},
        "debt": {"LongTermDebtCurrent", "LongTermDebtNoncurrent", "LongTermDebt", "ShortTermBorrowings", "DebtCurrent"},
        "diluted_eps": {"EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"},
        "operating_profit": {"OperatingIncomeLoss"},
        "balance_sheet": {
            "Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent",
            "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        },
        "working_capital": {"AccountsReceivableNetCurrent", "InventoryNet", "AccountsPayableCurrent"},
        "research_and_development": {"ResearchAndDevelopmentExpense"},
        "interest_expense": {"InterestExpense", "InterestExpenseNonOperating"},
        "dividends_and_repurchases": {
            "PaymentsOfDividends", "PaymentsForRepurchaseOfCommonStock",
            "CommonStockDividendsPerShareDeclared",
        },
        "capital_expenditure": {"PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"},
        "dilution_inputs": {"WeightedAverageNumberOfDilutedSharesOutstanding", "CommonStockSharesOutstanding", "ShareBasedCompensation", "StockBasedCompensation"},
        "debt_maturity_schedule": {
            "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
            "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
            "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
            "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
            "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
            "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
        },
    }
    available_tags = {fact["metadata"]["tag"] for fact in facts}
    gaps.extend({"security_id": security_id, "reason": "STANDARD_METRIC_MISSING", "metric": metric}
                for metric, tags in expected.items() if not tags & available_tags)
    annual_periods = {
        fact["metadata"]["period_end"] for fact in facts
        if _financial_period_bucket(fact["metadata"]) == "annual"
    }
    independent_quarters = {
        fact["metadata"]["period_end"] for fact in facts
        if _financial_period_bucket(fact["metadata"]) == "independent_quarter"
    }
    cumulative_quarters = {
        fact["metadata"]["period_end"] for fact in facts
        if _financial_period_bucket(fact["metadata"]) == "cumulative_quarter"
    }
    gaps.append({
        "security_id": security_id,
        "reason": "FINANCIAL_HISTORY_COVERAGE",
        "annual_periods": len(annual_periods),
        "independent_quarters": len(independent_quarters),
        "target_annual_periods": 3,
        "target_independent_quarters": 8,
        "status": "TARGET_MET" if len(annual_periods) >= 3 and len(independent_quarters) >= 8 else "PARTIAL",
    })
    if cumulative_quarters:
        gaps.append({
            "security_id": security_id,
            "reason": "CUMULATIVE_QUARTER_NOT_SPLIT",
            "period_ends": sorted(cumulative_quarters),
            "impact": "未用累计 YTD 值推算独立季度；需同口径父期间后再确定性拆分。",
        })
    # SEC companyfacts 不保留 XBRL dimension/member，不能用合计值伪造分部。
    # 分部资料仍可由已冻结的 10-K/10-Q 正文供 LLM 定性解释；结构化分部
    # 数值需未来读取 filing XBRL instance 后才能关闭此缺口。
    gaps.append({
        "security_id": security_id,
        "reason": "SEGMENT_DIMENSION_DATA_NOT_AVAILABLE_FROM_COMPANYFACTS",
        "impact": "不能仅凭 companyfacts 合计值形成结构化分部桥接或分部排名。",
    })
    by_id = {f["evidence_id"]: f for f in facts}
    derived = []
    for current in (f for f in facts if f["usage"] == "current"):
        comparisons = []
        for prior in facts:
            if current["evidence_id"] == prior["evidence_id"]:
                continue
            try:
                comparisons.append(compare_live_financials(current["evidence_id"], prior["evidence_id"], by_id))
            except ValueError:
                continue
        # Repeated disclosures of the same comparable value are not a value
        # conflict. Keep every pair and its original parent provenance; never
        # pick an accession silently or collapse differing revisions.
        results = {tuple((key, Decimal(value) if value is not None else None)
                         for key, value in sorted(item["value"].items())) for item in comparisons}
        if comparisons and len(results) == 1:
            derived.extend(comparisons)
        else:
            gaps.append({"security_id": security_id, "reason": "COMPARABLE_PERIOD_MISSING_OR_AMBIGUOUS", "field": current["semantic_field"]})
    return facts + derived, gaps


def research_valuation_financials(
    raw_facts, *, security_id, selection_time, annual_limit=7, quarter_limit=24,
):
    """为五年 PIT 估值保留较长窗口和同期间全部公开版本。

    与 ``research_financials`` 的当前背景窗口分离，避免扩大旧 sidecar；本函数
    不挑选“最新重述覆盖历史”，逐点生效由估值模块依据 published_at 完成。
    """
    cutoff = parse_timestamp(selection_time)
    groups, normalized, gaps = {}, [], []
    for fact in raw_facts:
        if fact.get("taxonomy") != "us-gaap":
            continue
        if fact.get("tag") not in FINANCIAL_TAGS:
            continue
        try:
            published = parse_timestamp(fact["published_at"])
            as_of = parse_timestamp(fact["as_of"])
        except (KeyError, TypeError, ValueError):
            gaps.append({"security_id": security_id, "reason": "VALUATION_FINANCIAL_TIME_INVALID"})
            continue
        if max(published, as_of) > cutoff:
            gaps.append({
                "security_id": security_id, "reason": "VALUATION_FINANCIAL_AFTER_CUTOFF",
                "tag": fact["tag"], "accession": fact.get("accession"),
            })
            continue
        key = (
            fact["tag"], fact["unit"], fact["context_type"],
            fact["form"].removesuffix("/A"),
        )
        groups.setdefault(key, []).append(fact)
    for key, values in sorted(groups.items()):
        selected, omitted = _select_financial_periods(
            values, annual_limit=annual_limit, quarter_limit=quarter_limit,
            other_limit=quarter_limit,
        )
        for fact in selected:
            value = normalize_sec_fact(fact, security_id=security_id, usage="comparison")
            value["metadata"]["historical_version_policy"] = "ALL_SELECTED_PUBLIC_VERSIONS"
            normalized.append(value)
        if omitted:
            gaps.append({
                "security_id": security_id,
                "reason": "VALUATION_HISTORY_SELECTION_TRUNCATED",
                "group": list(key), "omitted_count": omitted,
                "annual_limit": annual_limit, "quarter_limit": quarter_limit,
            })
    if not normalized:
        gaps.append({"security_id": security_id, "reason": "VALUATION_HISTORY_FINANCIALS_MISSING"})
    return sorted(
        normalized,
        key=lambda item: (
            item["metadata"]["period_end"], item["published_at"], item["evidence_id"],
        ),
    ), gaps


def collect_security_market(security, *, start, end, policies, session, cache, calendar, now,
                            backup_client, market_collector=collect_daily):
    """将实际两路适配接入单证券选择；SEC 封面绑定仍在冻结前统一执行。"""
    from product.mcp.live.source_routing import collect_selected_market
    from product.mcp.live.security_metadata import eastmoney_symbol, parse_eastmoney_identity
    from product.mcp.live.eastmoney_market import normalize_record

    def primary():
        result = market_collector([{k: security[k] for k in ("security_id", "ticker", "currency")}],
            start=start, end=end, source_access=policies["yahoo"], cache=cache,
            calendar=calendar, retrieved_at=now, max_age_seconds=86400, session=session)
        if not result["evidence"]:
            return result
        key = {"provider": "yahoo", "kind": "security-identity", "ticker": security["ticker"], "metadata_version": METADATA_VERSION}
        matching = [item["record"] for item in session.live_boundary.chart_records if item["ticker"] == security["ticker"]]
        if matching:
            record = matching[-1]
            alias = cache.store(key, json.dumps(record, sort_keys=True).encode(), retrieved_at=record["retrieved_at"])
        else:
            alias = cache.lookup(key)
            if alias is None:
                raise ValueError("LIVE_SECURITY_IDENTITY_SOURCE_MISSING")
            record = json.loads(cache.read(alias))
        quote = parse_chart_identity(cache.read(record), ticker=security["ticker"], record=record)
        if quote["exchange"] != security["exchange"]:
            raise ValueError("LIVE_SECURITY_EXCHANGE_CONFLICT")
        result["records"].update(quote=record, quote_alias=alias)
        result["quote_identity"] = quote
        return result

    def backup():
        symbol = eastmoney_symbol(security["ticker"], security["exchange"])
        # Yahoo 的 end 为开区间；东方财富请求为闭区间。
        last = (datetime.fromisoformat(end).date() - timedelta(days=1)).isoformat()
        record = backup_client.fetch(symbol=symbol, start=start, end=last)
        raw = cache.read(record)
        quote = parse_eastmoney_identity(raw, ticker=security["ticker"], exchange=security["exchange"], record=record)
        normalized = normalize_record(record, raw, security_id=security["security_id"], provider_symbol=symbol, calendar=calendar)
        return dict(normalized, records={symbol: record}, quote_identity=quote)

    return collect_selected_market(security_id=security["security_id"], start=start, end=end,
        access={key: policies[key] for key in ("yahoo", "eastmoney")}, fetchers={"yahoo": primary, "eastmoney": backup},
        cache=cache, calendar=calendar, now=now)


def validate_live_collection_configuration(access_path: Path, *, at) -> list[dict]:
    """在创建客户端或发送请求前验证当前只读来源配置。"""

    access = json.loads(external_path(access_path).read_text(encoding="utf-8"))
    if not isinstance(access, list) or len(access) not in (2, 4):
        raise ValueError("LIVE_TWO_SOURCE_ACCESS_RECORDS_REQUIRED")
    for entry in access:
        validate_contract("source-access", entry)
    policies = {entry["provider"]: entry for entry in access}
    routed = len(access) == 4
    expected = {"yahoo", "eastmoney", "sec", "nasdaq"} if routed else {"yahoo", "sec"}
    if set(policies) != expected or any(not source_is_admitted(entry, at=at) for entry in access):
        raise ValueError("LIVE_SOURCE_PAUSED_OR_NOT_AUTHORIZED")
    if not routed:
        raise ValueError("LIVE_CURRENT_SOURCE_TOPOLOGY_REQUIRED")
    if any(entry["schema_version"] != "live-source-access/4.0.0" for entry in access):
        raise ValueError("LIVE_ROUTING_ACCESS_VERSION_INVALID")
    for provider, client, adapter in (
        ("yahoo", f"yfinance/{YFINANCE_VERSION}", MARKET_VERSION),
        ("sec", CLIENT_VERSION, ADAPTER_VERSION),
    ):
        if policies[provider]["client_version"] != client or policies[provider]["adapter_version"] != adapter:
            raise ValueError("LIVE_SOURCE_VERSION_MISMATCH")
    if not {"data.sec.gov", "www.sec.gov"} <= set(policies["sec"]["domains"]):
        raise ValueError("SEC_REQUIRED_DOMAINS_NOT_AUTHORIZED")
    for entry in access:
        require_source_admission(entry, at=at)
    if any(parse_timestamp(entry["checked_at"]) > parse_timestamp(at) for entry in access):
        raise ValueError("LIVE_ACCESS_CHECKED_IN_FUTURE")
    return access


def collect_live_snapshot(portfolio_path: Path, *, access_path: Path, output_dir: Path, cache_root: Path,
                          sec_user_agent: str, now=lambda: datetime.now(UTC), sec_factory=SecClient,
                          session_factory=None, market_collector=collect_daily, calendar_factory=ExchangeCalendar,
                          universe_factory=None, backup_factory=None):
    """依赖注入仅用于零网络测试；产品入口不提供 fake/test 开关。"""
    portfolio = load_live_portfolio(portfolio_path)
    started = now()
    access = validate_live_collection_configuration(access_path, at=started)
    policies = {entry["provider"]: entry for entry in access}
    routed = len(access) == 4
    destination = external_path(output_dir)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    cache = SnapshotCache(cache_root)
    records, facts, gaps, events, metadata, mapping = {}, [], [], [], [], []
    session, stage = None, "SEC_MAPPING"
    universe, selections, chosen_quotes = None, [], {}
    def keep(record):
        records[record["record_hash"]] = record
        return record
    try:
        if routed:
            from product.mcp.live.nasdaq import NasdaqClient
            from product.mcp.live.eastmoney_transport import EastmoneyClient
            stage = "NASDAQ_UNIVERSE"
            universe_client = (universe_factory or NasdaqClient)(policies["nasdaq"], cache)
            universe = (
                universe_client.collect_download()
                if hasattr(universe_client, "collect_download")
                else universe_client.collect()
            )
            for page in universe["pages"]:
                keep(page["record"])
            events.extend(universe["events"])
            # A directory is auxiliary to a user-specified holding. Only the
            # explicit availability failures are nonfatal; corrupt data is not.
            directory_unavailable = universe_client.failure_code in {
                "NASDAQ_TRANSPORT_FAILURE", "NASDAQ_REQUEST_BUDGET_EXHAUSTED",
                "NASDAQ_HTTP_401", "NASDAQ_HTTP_403", "NASDAQ_HTTP_429",
                "NASDAQ_HTTP_500", "NASDAQ_HTTP_502", "NASDAQ_HTTP_503", "NASDAQ_HTTP_504",
            }
            if universe_client.failure_code and not directory_unavailable:
                raise ValueError(universe_client.failure_code)
            if universe["completeness"] != "COMPLETE":
                gaps.append({"reason": "UNIVERSE_PARTIAL", "details": universe["gaps"]})
            backup_client = (backup_factory or EastmoneyClient)(policies["eastmoney"], cache)
        stage = "SEC_MAPPING"
        sec = sec_factory(cache, user_agent=sec_user_agent, request_budget=policies["sec"]["request_budget"],
                          source_access=policies["sec"])
        mapped = sec.read_ticker_map(max_age_seconds=86400)
        keep(mapped["record"])
        selected = []
        for position in portfolio["positions"]:
            matches = [
                m for m in mapped["mapping"]
                if m["ticker"] == position["ticker"]
                and (position.get("exchange") is None or m["exchange"] == position["exchange"])
            ]
            if len(matches) != 1:
                raise ValueError("LIVE_SECURITY_IDENTITY_AMBIGUOUS_OR_MISSING")
            mapping.extend(matches)
            selected.append(dict(
                position, exchange=matches[0]["exchange"],
                cik=matches[0]["cik"], currency="USD",
            ))
        calendar = calendar_factory(start=(started.date() - timedelta(days=370)).isoformat(), end=(started.date() + timedelta(days=2)).isoformat())
        stage = "YAHOO_COLLECTION"
        if session_factory is None:
            from product.mcp.live.yahoo_transport import create_yahoo_session
            session_factory = create_yahoo_session
        session = session_factory(policies["yahoo"], tickers=[p["ticker"] for p in selected], state_dir=destination / "yahoo-state", cache=cache)
        if routed:
            market = {"evidence": [], "gaps": [], "records": {}}
            for security in selected:
                routed_result = collect_security_market(security,
                    start=(started.date() - timedelta(days=365)).isoformat(), end=(started.date() + timedelta(days=1)).isoformat(),
                    policies=policies, session=session, cache=cache, calendar=calendar, now=now,
                    backup_client=backup_client, market_collector=market_collector)
                selections.append(routed_result["selection"])
                # 未被选中的合法原文保留在审计包，不混入研究事实或估值输入。
                for record in routed_result["audit_records"].values():
                    keep(record)
                events.append({"producer": "live-market-routing", "completed_at": iso_utc(now()),
                               "source_selection": routed_result["selection"],
                               "audit_record_hashes": sorted(routed_result["audit_records"])})
                if routed_result["status"] != "SELECTED":
                    raise ValueError(routed_result["failure_code"])
                item = routed_result["market"]
                market["evidence"].extend(item["evidence"])
                market["gaps"].extend(item["gaps"])
                for record in item["records"].values():
                    market["records"][record["record_hash"]] = record
                    key = record.get("key", {})
                    if (
                        routed_result["selection"]["selected_provider"] == "yahoo"
                        and key.get("provider") == "yahoo"
                        and key.get("interval") == "1d"
                    ):
                        from product.mcp.live.market import normalize_cached_research_series
                        research_series = normalize_cached_research_series(
                            record, cache.read(record), security_id=security["security_id"],
                            ticker=security["ticker"], currency=security["currency"],
                            calendar=calendar,
                        )
                        facts.extend(research_series["evidence"])
                        gaps.extend(
                            dict(gap, security_id=security["security_id"])
                            for gap in research_series["gaps"]
                        )
                chosen_quotes[security["ticker"]] = item["quote_identity"]
        else:
            market = market_collector([{k:p[k] for k in ("security_id", "ticker", "currency")} for p in selected],
            start=(started.date() - timedelta(days=365)).isoformat(), end=(started.date() + timedelta(days=1)).isoformat(),
            source_access=policies["yahoo"], cache=cache, calendar=calendar, retrieved_at=now,
            max_age_seconds=86400, session=session)
        facts.extend(market["evidence"])
        gaps.extend(market["gaps"])
        for record in market["records"].values():
            keep(record)
        quote_records = {}
        for item in session.live_boundary.chart_records:
            record = keep(item["record"])
            key = {"provider": "yahoo", "kind": "security-identity", "ticker": item["ticker"], "metadata_version": METADATA_VERSION}
            keep(cache.store(key, json.dumps(record, sort_keys=True).encode(), retrieved_at=record["retrieved_at"]))
            quote_records[item["ticker"]] = record
        for security in selected:
            stage = "SEC_COMPANY_COLLECTION"
            company = sec.read_company(security["cik"], security_id=security["security_id"], max_history_pages=1, max_age_seconds=86400)
            for record in (company["submissions_record"], company["companyfacts_record"], *company["history"]["records"]):
                keep(record)
            selection_time = iso_utc(now())
            if company["history"].get("excluded"):
                gaps.append({"security_id": security["security_id"], "reason": "SEC_HISTORY_DOCUMENT_MISSING"})
                events.append({"producer": "sec-history-parser", "completed_at": selection_time,
                               "security_id": security["security_id"], "coverage": company["coverage"],
                               "excluded": company["history"]["excluded"]})
            financials, financial_gaps = research_financials(company["evidence"], security_id=security["security_id"], selection_time=selection_time)
            facts.extend(financials)
            gaps.extend(financial_gaps)
            if company.get("excluded"):
                gaps.append({"security_id": security["security_id"], "reason": "FINANCIAL_PARSER_EXCLUDED"})
                events.append({"producer": "sec-financial-parser", "completed_at": selection_time, "excluded": company["excluded"]})
            disclosures = sec.read_selected_disclosures(
                company["filings"], selection_as_of=selection_time,
                event_limit=1, attachment_limit=1, max_age_seconds=86400,
            )
            events.append({"producer": "sec-disclosure-selection", "completed_at": iso_utc(now()),
                "selection": disclosures["selection"], "history_omitted_pages": company["history"]["omitted_pages"]})
            gaps.extend({"security_id": security["security_id"], "reason": reason} for reason in disclosures["selection"]["gaps"])
            if company["history"]["omitted_pages"] or disclosures["selection"]["omitted_event_accessions"]:
                gaps.append({"security_id": security["security_id"], "reason": "DISCLOSURE_HISTORY_OR_EVENTS_TRUNCATED"})
            covers = []
            for entry in disclosures["documents"]:
                document = entry["document"]
                keep(document["cache_record"])
                if document["form"] in ("10-K", "10-Q"):
                    covers.append(document)
                for fact in entry.get("sections", {}).get("evidence", []):
                    facts.append(normalize_sec_fact(fact, security_id=security["security_id"]))
                if "sections" in entry:
                    gaps.append({"security_id": security["security_id"], "disclosure_coverage": {k:v for k,v in entry["sections"].items() if k != "evidence"}})
                attachments = entry.get("attachments", {})
                if attachments:
                    keep(attachments["index"]["cache_record"])
                    for attached in attachments["documents"]:
                        keep(attached["cache_record"])
                        from product.mcp.live.disclosure import extract_earnings_exhibit
                        excerpt = extract_earnings_exhibit(cache.read(attached["cache_record"]), attached)
                        facts.extend(normalize_sec_fact(fact, security_id=security["security_id"]) for fact in excerpt["evidence"])
                        if excerpt["gap"]:
                            gaps.append({"security_id": security["security_id"], "reason": excerpt["gap"]})
                    events.append({"producer": "sec-exhibit-selection", "completed_at": iso_utc(now()), "selection": attachments["selection"]})
            # 内部人披露是附加研究能力：每证券只取截止时点前最新一份
            # Form 3/4/5，预算/来源失败不得删除已取得的公司财务资料。
            ownership_candidates = sorted(
                (
                    filing for filing in company["filings"].values()
                    if filing["form"] in {"3", "3/A", "4", "4/A", "5", "5/A"}
                    and parse_timestamp(filing["published_at"]) <= parse_timestamp(selection_time)
                ),
                key=lambda filing: (parse_timestamp(filing["published_at"]), filing["accession"]),
                reverse=True,
            )[:1]
            if not ownership_candidates:
                gaps.append({"security_id": security["security_id"], "reason": "SEC_OWNERSHIP_FILING_NOT_FOUND"})
            for filing in ownership_candidates:
                try:
                    ownership_document = sec.read_ownership_document(
                        filing, max_age_seconds=86400
                    )
                    record = ownership_document["record"]
                    keep(record)
                    from product.mcp.live.ownership import parse_ownership_document
                    ownership = parse_ownership_document(
                        cache.read(record), filing=ownership_document["filing"],
                        security_id=security["security_id"], retrieved_at=record["retrieved_at"],
                    )
                    facts.extend(ownership["evidence"])
                    gaps.extend(
                        dict(item, security_id=security["security_id"])
                        for item in ownership["gaps"]
                    )
                    events.append({
                        "producer": "sec-ownership-parser", "completed_at": iso_utc(now()),
                        "security_id": security["security_id"], "accession": filing["accession"],
                        "record_hash": record["record_hash"], "evidence_ids": [
                            item["evidence_id"] for item in ownership["evidence"]
                        ], "coverage": ownership["coverage"],
                        "submission_document_url": ownership_document["submission_document_url"],
                        "raw_document_url": ownership_document["raw_document_url"],
                        "document_resolution_version": ownership_document["resolution_version"],
                    })
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    code = str(exc).split(":", 1)[0]
                    gaps.append({
                        "security_id": security["security_id"],
                        "reason": "SEC_OWNERSHIP_SOURCE_LIMITED",
                        "failure_code": code,
                    })
                    events.append({
                        "producer": "sec-ownership-parser", "completed_at": iso_utc(now()),
                        "security_id": security["security_id"], "status": "SOURCE_LIMITED",
                        "failure_code": code,
                    })
            quote_record = quote_records.get(security["ticker"])
            stage = "SEC_YAHOO_IDENTITY_BINDING"
            if quote_record is None:
                alias = cache.lookup({"provider": "yahoo", "kind": "security-identity", "ticker": security["ticker"], "metadata_version": METADATA_VERSION})
                if alias:
                    keep(alias)
                    quote_record = keep(json.loads(cache.read(alias)))
            if (not quote_record and not routed) or not covers:
                raise ValueError("LIVE_SECURITY_IDENTITY_SOURCE_MISSING")
            quote = chosen_quotes[security["ticker"]] if routed else parse_chart_identity(cache.read(quote_record), ticker=security["ticker"], record=quote_record)
            cover = max(covers, key=lambda d: parse_timestamp(d["published_at"]))
            metadata.append(bind_disclosure_security(cache.read(cover["cache_record"]), cover, quote))
        events.extend(dict(event, completed_at=event.get("completed_at", event.get("cache_read_at", iso_utc(now())))) for event in sec.events)
        events.extend(session.live_boundary.events)
        if routed:
            events.extend(backup_client.events)
        cutoff = iso_utc(now())
        stage = "FREEZE"
        identity = freeze_identity(portfolio, sec_mapping=mapping, security_metadata=metadata, cutoff=cutoff)
        snapshot = freeze_snapshot(snapshot_id=f"live-snapshot-{uuid4()}", portfolio=portfolio,
            request_started_at=iso_utc(started), decision_cutoff=cutoff, facts=facts, source_access=access,
            raw_records=list(records.values()), collection_events=events,
            gaps=[g if isinstance(g, str) else json.dumps(g, ensure_ascii=False, sort_keys=True) for g in gaps], identity=identity,
            **({"universe": universe, "source_selections": selections} if routed else {}))
        for name, value in (("portfolio.json", portfolio), ("snapshot.json", snapshot), ("calendar.json", calendar.lock_record())):
            with (destination / name).open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return {"status": "FROZEN", "collection_version": COLLECTION_VERSION, "snapshot_hash": snapshot["snapshot_hash"],
                "snapshot_path": str(destination / "snapshot.json"), "portfolio_path": str(destination / "portfolio.json"),
                "calendar_lock": str(destination / "calendar.json"), "cache_root": str(cache.root)}
    except Exception as exc:
        # 不保存异常正文/请求头，以免 SDK 异常含 cookie 或联系身份。
        import re
        token = str(exc).split(":", 1)[0]
        safe_code = token if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", token) else "LIVE_COLLECTION_FAILED"
        failure = {"status": "FAILED", "collection_version": COLLECTION_VERSION,
                   "failure_type": type(exc).__name__, "failed_stage": stage, "completed_at": iso_utc(now()),
                   "failure_code": safe_code,
                   "source_selections": selections,
                   "events": [*events, *getattr(locals().get("backup_client"), "events", []),
                              *getattr(locals().get("sec"), "events", []),
                              *getattr(getattr(session, "live_boundary", None), "events", [])]}
        with (destination / "collection-error.json").open("x", encoding="utf-8") as stream:
            json.dump(failure, stream, ensure_ascii=False, sort_keys=True)
        raise ValueError(f"{safe_code}:see collection-error.json") from None
    finally:
        if session is not None:
            session.close()
