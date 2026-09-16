"""单证券行情来源选择：只处理数据可用性，不承载投资判断或 LLM 编排。"""
from copy import deepcopy
from datetime import date
import re

from product.mcp.live.contracts import validate_contract, require_source_admission
from product.mcp.provenance import content_hash, parse_timestamp, iso_utc

POLICY = {
    "version": "live-market-routing/1.0.0",
    "providers": ["yahoo", "eastmoney"],
    "fallback_codes": ["YAHOO_TRANSPORT_FAILURE", "YAHOO_HTTP_500", "YAHOO_HTTP_502",
                       "YAHOO_HTTP_503", "YAHOO_HTTP_504", "MARKET_NO_COMPLETED_PRICE",
                       "MARKET_NO_FRESH_PRICE"],
    "price_basis": "provider_close", "max_provider_attempts": 1,
}


def policy_lock():
    return {"version": POLICY["version"], "hash": content_hash(POLICY)}


def provider_versions():
    from product.mcp.live.market import MARKET_VERSION, YFINANCE_VERSION
    from product.mcp.live.eastmoney_transport import ADAPTER_VERSION, AKSHARE_VERSION
    return {"yahoo": (f"yfinance/{YFINANCE_VERSION}", MARKET_VERSION),
            "eastmoney": (f"akshare/{AKSHARE_VERSION}", ADAPTER_VERSION)}


def validate_source_version(entry):
    """新拓扑准入元数据的客户端、适配器与最小端点集合；不导入 SDK。"""
    from product.mcp.live.nasdaq import CLIENT_VERSION as NC, ADAPTER_VERSION as NA
    from product.mcp.live.sec_client import CLIENT_VERSION as SC
    from product.mcp.live.sec import ADAPTER_VERSION as SA
    expected = {**provider_versions(), "nasdaq": (NC, NA), "sec": (SC, SA)}
    domains = {"nasdaq": {"api.nasdaq.com"}, "sec": {"data.sec.gov", "www.sec.gov"},
               "yahoo": {"query1.finance.yahoo.com", "query2.finance.yahoo.com", "fc.yahoo.com"},
               "eastmoney": {"63.push2his.eastmoney.com"}}
    provider = entry["provider"]
    if (entry["client_version"], entry["adapter_version"]) != expected[provider]:
        raise ValueError("LIVE_ROUTING_VERSION_MISMATCH")
    actual = set(entry["domains"])
    if not actual or not actual <= domains[provider] or len(actual) != len(entry["domains"]):
        raise ValueError("LIVE_ROUTING_DOMAINS_INVALID")
    if provider != "yahoo" and actual != domains[provider]:
        raise ValueError("LIVE_ROUTING_DOMAINS_INCOMPLETE")


def validate_selection(selection, facts=None):
    """即使上游重算 selection_hash，也必须满足来源顺序与回退条件。"""
    if selection["selection_hash"] != content_hash({k: v for k, v in selection.items() if k != "selection_hash"}):
        raise ValueError("LIVE_SELECTION_HASH_MISMATCH")
    if selection["routing_policy"] != policy_lock():
        raise ValueError("LIVE_ROUTING_POLICY_DRIFT")
    window = selection["window"]
    if not 0 < (date.fromisoformat(window["end"]) - date.fromisoformat(window["start"])).days <= 366:
        raise ValueError("LIVE_ROUTING_WINDOW_INVALID")
    attempts = selection["attempts"]
    if not 1 <= len(attempts) <= 2 or [a["provider"] for a in attempts] != POLICY["providers"][:len(attempts)]:
        raise ValueError("LIVE_ROUTING_ATTEMPT_ORDER_INVALID")
    if len(attempts) == 2 and (attempts[0]["status"] != "FAILED" or attempts[0]["failure_code"] not in POLICY["fallback_codes"]):
        raise ValueError("LIVE_ROUTING_FALLBACK_FORBIDDEN")
    for attempt in attempts:
        if (attempt["client_version"], attempt["adapter_version"]) != provider_versions()[attempt["provider"]]:
            raise ValueError("LIVE_ROUTING_VERSION_MISMATCH")
        if (attempt["status"] == "SUCCEEDED") != (attempt["failure_code"] is None):
            raise ValueError("LIVE_ROUTING_ATTEMPT_STATE_INVALID")
        if parse_timestamp(attempt["started_at"]) > parse_timestamp(attempt["completed_at"]):
            raise ValueError("LIVE_ROUTING_ATTEMPT_TIME_INVALID")
    chosen = selection["selected_provider"]
    if chosen is None:
        if any(a["status"] == "SUCCEEDED" for a in attempts) or selection["evidence_ids"] or selection["raw_hashes"]:
            raise ValueError("LIVE_ROUTING_EMPTY_SELECTION_INVALID")
    elif attempts[-1]["provider"] != chosen or attempts[-1]["status"] != "SUCCEEDED":
        raise ValueError("LIVE_ROUTING_SELECTED_ATTEMPT_INVALID")
    elif not selection["evidence_ids"] or not selection["raw_hashes"]:
        raise ValueError("LIVE_ROUTING_SUCCESS_WITHOUT_EVIDENCE")
    if facts is not None:
        if sorted(f["evidence_id"] for f in facts) != selection["evidence_ids"]:
            raise ValueError("LIVE_SELECTION_EVIDENCE_MISMATCH")
        if sorted(set(f["raw_content_hash"] for f in facts)) != selection["raw_hashes"]:
            raise ValueError("LIVE_SELECTION_RAW_MISMATCH")
        if any(f["security_id"] != selection["security_id"] or f["source_type"] != chosen for f in facts):
            raise ValueError("LIVE_SELECTION_SOURCE_MIXED")
        if chosen is not None:
            expected_version = "/".join(provider_versions()[chosen])
            expected_schema = "live-fact/1.0.0" if chosen == "yahoo" else "live-fact/2.0.0"
            if any(f["source_version"] != expected_version or f["schema_version"] != expected_schema for f in facts):
                raise ValueError("LIVE_SELECTION_FACT_VERSION_MISMATCH")


def collect_selected_market(*, security_id, start, end, access, fetchers, cache, calendar, now):
    """fetchers 是既有数据采集函数，返回 evidence/records；不接受模型输出。

    单次调用最多一次主源及一次备用调用；各适配内部有限重试属于其 HTTP
    预算。行情身份校验在 fetcher 返回前完成，SEC 封面绑定由 collection 在
    冻结前执行；任何未知错误禁止故障转移。
    """
    if not isinstance(security_id, str) or not security_id.strip():
        raise ValueError("LIVE_ROUTING_SECURITY_INVALID")
    if not 0 < (date.fromisoformat(end) - date.fromisoformat(start)).days <= 366:
        raise ValueError("LIVE_ROUTING_WINDOW_INVALID")
    if set(access) != set(POLICY["providers"]) or set(fetchers) != set(POLICY["providers"]):
        raise ValueError("LIVE_ROUTING_PROVIDERS_INVALID")
    for provider, entry in access.items():
        validate_contract("source-access", entry)
        if entry["provider"] != provider or entry["schema_version"] not in ("live-source-access/3.0.0", "live-source-access/4.0.0"):
            raise ValueError("LIVE_ROUTING_ACCESS_INVALID")
        if (entry["client_version"], entry["adapter_version"]) != provider_versions()[provider]:
            raise ValueError("LIVE_ROUTING_VERSION_MISMATCH")
    attempts, selected, result = [], None, {"evidence": [], "records": {}, "gaps": []}
    audit_records = {}
    for provider in POLICY["providers"]:
        entry = access[provider]
        attempt = {"provider": provider, "client_version": entry["client_version"],
                   "adapter_version": entry["adapter_version"], "started_at": iso_utc(now()),
                   "status": "FAILED", "failure_code": None}
        attempts.append(attempt)
        try:
            require_source_admission(entry, at=attempt["started_at"])
            if parse_timestamp(entry["checked_at"]) > parse_timestamp(attempt["started_at"]):
                raise ValueError("LIVE_ACCESS_CHECKED_IN_FUTURE")
            candidate = deepcopy(fetchers[provider]())
            observed = now()
            facts, records = candidate["evidence"], list(candidate["records"].values())
            raw_hashes = set()
            for record in records:
                if (record["record_hash"] != content_hash({k: v for k, v in record.items() if k != "record_hash"})
                        or record["key_hash"] != content_hash(record["key"])):
                    raise ValueError("LIVE_SELECTION_RECORD_HASH_MISMATCH")
                cache.read(record)  # 根据实际缓存字节验证 hash，不相信摘要状态。
                if record["key"].get("provider") != provider:
                    raise ValueError("LIVE_SELECTION_RECORD_SOURCE_MISMATCH")
                if parse_timestamp(record["retrieved_at"]) > observed:
                    raise ValueError("LIVE_SELECTION_FUTURE_RECORD")
                raw_hashes.add(record["raw_content_hash"])
                audit_records[record["record_hash"]] = record
            seen = set()
            for fact in facts:
                validate_contract("fact", fact)
                if (fact["source_version"] != "/".join(provider_versions()[provider])
                        or fact["schema_version"] != ("live-fact/1.0.0" if provider == "yahoo" else "live-fact/2.0.0")):
                    raise ValueError("LIVE_SELECTION_FACT_VERSION_MISMATCH")
                if (fact["security_id"] != security_id or fact["source_type"] != provider
                        or fact["kind"] != "price" or fact["semantic_field"] != "close_price"
                        or fact["currency"] != "USD" or fact["metadata"].get("price_basis") != POLICY["price_basis"]):
                    raise ValueError("LIVE_SELECTION_SOURCE_MIXED")
                if fact["evidence_id"] in seen:
                    raise ValueError("LIVE_SELECTION_DUPLICATE_EVIDENCE")
                seen.add(fact["evidence_id"])
                if fact["raw_content_hash"] not in raw_hashes:
                    raise ValueError("LIVE_SELECTION_RAW_MISSING")
                if not any(r["raw_content_hash"] == fact["raw_content_hash"]
                           and r["retrieved_at"] == fact["retrieved_at"] for r in records):
                    raise ValueError("LIVE_SELECTION_RETRIEVAL_MISMATCH")
                day = fact["metadata"].get("trading_date")
                if not isinstance(day, str) or not start <= day < end:
                    raise ValueError("LIVE_SELECTION_WINDOW_MISMATCH")
                if calendar.session_close(day) != fact["as_of"]:
                    raise ValueError("LIVE_SELECTION_SESSION_MISMATCH")
                if any(parse_timestamp(fact[k]) > observed for k in ("as_of", "published_at", "retrieved_at")):
                    raise ValueError("LIVE_SELECTION_FUTURE_EVIDENCE")
                if any(parse_timestamp(fact[k]) > parse_timestamp(fact["retrieved_at"]) for k in ("as_of", "published_at")):
                    raise ValueError("LIVE_SELECTION_FACT_TIME_INVALID")
            if not facts:
                raise ValueError("MARKET_NO_COMPLETED_PRICE")
            sessions = sorted(parse_timestamp(t) for t in calendar.completed_sessions(observed))
            if len(sessions) < 2 or len(sessions) != len(set(sessions)) or sessions[-1] > observed:
                raise ValueError("LIVE_ROUTING_CALENDAR_INVALID")
            if not any(parse_timestamp(f["as_of"]) in sessions[-2:] for f in facts):
                raise ValueError("MARKET_NO_FRESH_PRICE")
            selected, result = provider, candidate
            attempt["status"] = "SUCCEEDED"
        except (ValueError, KeyError, TypeError) as exc:
            code = str(exc)
            attempt["failure_code"] = code if re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", code) else "LIVE_ROUTING_OUTPUT_INVALID"
        finally:
            attempt["completed_at"] = iso_utc(now())
        if selected is not None or attempt["failure_code"] not in POLICY["fallback_codes"]:
            break
    selection = {"schema_version": "live-source-selection/1.0.0", "security_id": security_id,
                 "window": {"start": start, "end": end}, "routing_policy": policy_lock(),
                 "attempts": attempts, "selected_provider": selected,
                 "price_basis": POLICY["price_basis"],
                 "evidence_ids": sorted(f["evidence_id"] for f in result["evidence"]),
                 "raw_hashes": sorted(set(f["raw_content_hash"] for f in result["evidence"]))}
    selection["selection_hash"] = content_hash(selection)
    validate_contract("source-selection", selection)
    validate_selection(selection, result["evidence"])
    return {"selection": selection, "market": result, "audit_records": audit_records,
            "status": "SELECTED" if selected else "FAILED",
            "failure_code": None if selected else attempts[-1]["failure_code"]}
