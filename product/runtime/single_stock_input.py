"""非持仓单股请求：核实来源身份和时点，不推断持仓或投资动作。"""
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from uuid import uuid4

from product.mcp.live.identity import IDENTITY_VERSION
from product.mcp.live.sec import normalize_cik
from product.mcp.live.security_metadata import METADATA_VERSION, EASTMONEY_METADATA_VERSION
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp
from product.runtime.schema_validation import validate_schema_instance

VERSION = "single-stock-research-request/1.0.0"
INPUT_KIND = "SINGLE_STOCK_RESEARCH"
SCHEMA = Path(__file__).resolve().parents[1] / "schemas/runtime/single-stock-research-request.schema.json"
DEFAULT_QUESTION = "分析公司的经营质量、财务与估值依据、市场及宏观传导、主要反证和重评条件；仅形成研究综合，不提供交易动作或账户建议。"


def normalize_single_stock_intent(symbol, *, question=None, cutoff="latest", at=None):
    """核实用户语法；尚未核实的 ticker 不能被视为证券身份。"""
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,14}", symbol.strip()):
        raise ValueError("SINGLE_STOCK_SYMBOL_INVALID")
    if question is not None and (not isinstance(question, str) or not question.strip()):
        raise ValueError("SINGLE_STOCK_QUESTION_INVALID")
    observed = iso_utc(at or datetime.now(UTC))
    latest = isinstance(cutoff, str) and cutoff.lower() == "latest"
    try:
        requested = None if latest else iso_utc(cutoff)
    except (AttributeError, TypeError, ValueError):
        raise ValueError("SINGLE_STOCK_CUTOFF_INVALID") from None
    if requested and parse_timestamp(requested) > parse_timestamp(observed):
        raise ValueError("SINGLE_STOCK_FUTURE_CUTOFF")
    return {"ticker": symbol.strip().upper(), "research_question": question.strip() if question else DEFAULT_QUESTION,
            "cutoff_mode": "LATEST" if latest else "EXPLICIT", "requested_cutoff": requested,
            "requested_at": observed}


def resolve_single_stock_identity(ticker, *, sec_mapping, security_metadata, cutoff):
    """SEC 当前映射 + 已经原适配器交叉核实的申报封面/行情身份。"""
    listings = [row for row in sec_mapping if row.get("ticker") == ticker]
    covers = [row for row in security_metadata if row.get("ticker") == ticker]
    if len(listings) != 1 or len(covers) != 1:
        raise ValueError("SINGLE_STOCK_IDENTITY_AMBIGUOUS_OR_MISSING")
    listing, cover = listings[0], covers[0]
    quote = cover.get("quote_identity", {})
    if (listing.get("identity_version") != IDENTITY_VERSION
            or cover.get("metadata_version") not in {METADATA_VERSION, EASTMONEY_METADATA_VERSION}
            or listing.get("exchange") not in {"XNAS", "XNYS", "XASE"}
            or listing["exchange"] != cover.get("exchange") or quote.get("exchange") != cover.get("exchange")
            or quote.get("ticker") != ticker or quote.get("currency") != "USD"
            or cover.get("currency") != "USD" or cover.get("security_type") != "COMMON_STOCK"
            or cover.get("filing_regime") != "DOMESTIC_10K_10Q" or cover.get("form") not in {"10-K", "10-Q"}
            or not isinstance(cover.get("share_class"), str) or not cover["share_class"]
            or not isinstance(listing.get("issuer_name"), str) or not listing["issuer_name"].strip()
            or normalize_cik(cover.get("cik")) != normalize_cik(listing.get("cik"))):
        raise ValueError("SINGLE_STOCK_IDENTITY_UNSUPPORTED_OR_CONFLICT")
    for row in (listing, cover, quote):
        if any(not row.get(key) for key in ("source_id", "source_locator", "as_of", "retrieved_at", "raw_content_hash")):
            raise ValueError("SINGLE_STOCK_IDENTITY_PROVENANCE_MISSING")
        if not re.fullmatch(r"[a-f0-9]{64}", row["raw_content_hash"]):
            raise ValueError("SINGLE_STOCK_IDENTITY_HASH_INVALID")
        if parse_timestamp(row["as_of"]) > parse_timestamp(row["retrieved_at"]):
            raise ValueError("SINGLE_STOCK_IDENTITY_TIME_INVALID")
        if parse_timestamp(row["retrieved_at"]) > parse_timestamp(cutoff):
            raise ValueError("SINGLE_STOCK_IDENTITY_AFTER_CUTOFF")
    if parse_timestamp(cover["published_at"]) > parse_timestamp(cutoff):
        raise ValueError("SINGLE_STOCK_IDENTITY_AFTER_CUTOFF")
    return {"security_id": f"US:COMMON_STOCK:{ticker}", "ticker": ticker,
            "asset_type": "COMMON_STOCK", "market": "US", "currency": "USD",
            "exchange": listing["exchange"], "share_class": cover["share_class"],
            "cik": normalize_cik(listing["cik"]), "issuer_name": listing["issuer_name"],
            "identity_status": "RESOLVED", "sec_mapping_hash": content_hash(listing),
            "security_metadata_hash": content_hash(cover)}


def build_single_stock_request(intent, *, sec_mapping, security_metadata, resolved_cutoff, request_id=None):
    checked = normalize_single_stock_intent(intent["ticker"], question=intent["research_question"],
        cutoff=intent["requested_cutoff"] if intent["cutoff_mode"] == "EXPLICIT" else "latest",
        at=intent["requested_at"])
    if checked != intent:
        raise ValueError("SINGLE_STOCK_INTENT_MISMATCH")
    cutoff = iso_utc(resolved_cutoff)
    if intent["cutoff_mode"] == "EXPLICIT" and cutoff != intent["requested_cutoff"]:
        raise ValueError("SINGLE_STOCK_EXPLICIT_CUTOFF_MISMATCH")
    security = resolve_single_stock_identity(intent["ticker"], sec_mapping=sec_mapping,
        security_metadata=security_metadata, cutoff=cutoff)
    body = {"schema_version": VERSION, "input_kind": INPUT_KIND,
            "request_id": request_id or f"single-stock-{uuid4()}",
            "research_question": intent["research_question"], "requested_at": intent["requested_at"],
            "cutoff_mode": intent["cutoff_mode"], "requested_cutoff": intent["requested_cutoff"],
            "resolved_cutoff": cutoff, "security": security,
            "identity_sources": {"sec_mapping": deepcopy(sec_mapping), "security_metadata": deepcopy(security_metadata)}}
    body["request_hash"] = content_hash(body)
    validate_single_stock_request(body)
    return body


def validate_single_stock_request(value):
    validate_schema_instance(value, json.loads(SCHEMA.read_text(encoding="utf-8")))
    if value["request_hash"] != content_hash({key: item for key, item in value.items() if key != "request_hash"}):
        raise ValueError("SINGLE_STOCK_REQUEST_HASH_MISMATCH")
    if value["cutoff_mode"] == "LATEST":
        if value["requested_cutoff"] is not None or parse_timestamp(value["requested_at"]) > parse_timestamp(value["resolved_cutoff"]):
            raise ValueError("SINGLE_STOCK_LATEST_CUTOFF_INVALID")
    elif value["requested_cutoff"] != value["resolved_cutoff"]:
        raise ValueError("SINGLE_STOCK_EXPLICIT_CUTOFF_MISMATCH")
    else:
        normalize_single_stock_intent(value["security"]["ticker"], question=value["research_question"],
            cutoff=value["requested_cutoff"], at=value["requested_at"])
    identity = resolve_single_stock_identity(value["security"]["ticker"],
        **value["identity_sources"], cutoff=value["resolved_cutoff"])
    if identity != value["security"]:
        raise ValueError("SINGLE_STOCK_SECURITY_BINDING_MISMATCH")


def single_stock_subject(value):
    validate_single_stock_request(value)
    security = value["security"]
    return {"security_id": security["security_id"], "display_symbol": security["ticker"],
            "display_name": security["issuer_name"], "market": security["market"],
            "asset_type": security["asset_type"], "identity_status": "RESOLVED"}


def freeze_latest_research_request(preparation_request, *, resolved_cutoff):
    """生成新的最终冻结对象；调用方保留原准备请求原字节，不改原审计。"""
    validate_single_stock_request(preparation_request)
    cutoff = iso_utc(resolved_cutoff)
    if preparation_request["cutoff_mode"] != "LATEST":
        if cutoff != preparation_request["resolved_cutoff"]:
            raise ValueError("SINGLE_STOCK_EXPLICIT_CUTOFF_MISMATCH")
        return deepcopy(preparation_request)
    if parse_timestamp(cutoff) < parse_timestamp(preparation_request["resolved_cutoff"]):
        raise ValueError("SINGLE_STOCK_FINAL_CUTOFF_PRECEDES_PREPARATION")
    if cutoff == preparation_request["resolved_cutoff"]:
        return deepcopy(preparation_request)
    value = deepcopy(preparation_request)
    value.update(resolved_cutoff=cutoff, preparation_request_hash=preparation_request["request_hash"])
    value["request_hash"] = content_hash({key: item for key, item in value.items() if key != "request_hash"})
    validate_single_stock_request(value)
    return value


def validate_preparation_request_lineage(final_request, preparation_request):
    """重算新冻结对象，必须是同一真实输入；hash摘要不能单独证明血缘。"""
    validate_single_stock_request(final_request)
    expected = freeze_latest_research_request(preparation_request, resolved_cutoff=final_request["resolved_cutoff"])
    if final_request != expected:
        raise ValueError("SINGLE_STOCK_PREPARATION_LINEAGE_MISMATCH")
