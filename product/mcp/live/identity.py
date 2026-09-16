"""证券身份绑定：ticker/交易所/股类与 CIK 分开，不将发行人当证券。"""
from product.mcp.live.sec import _decode, normalize_cik
from product.mcp.live.contracts import validate_contract
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp
import hashlib

IDENTITY_VERSION = "us-equity-identity/1.0.0"
EXCHANGES = {"Nasdaq": "XNAS", "NYSE": "XNYS", "NYSE American": "XASE"}


def parse_sec_ticker_map(raw: bytes, *, retrieved_at: str) -> list[dict]:
    value = _decode(raw)
    fields = value["fields"]
    if not isinstance(fields, list) or len(set(fields)) != len(fields) or not {"cik", "name", "ticker", "exchange"} <= set(fields):
        raise ValueError("SEC_TICKER_FIELDS_INVALID")
    output = []
    for index, row in enumerate(value["data"]):
        if not isinstance(row, list) or len(row) != len(fields):
            raise ValueError("SEC_TICKER_ROW_INVALID")
        item = dict(zip(fields, row))
        output.append({"cik": normalize_cik(item["cik"]), "ticker": item["ticker"], "issuer_name": item["name"],
                       "exchange": EXCHANGES.get(item["exchange"]), "provider_exchange": item["exchange"],
                       "source_id": "sec-ticker-map", "source_locator": "https://www.sec.gov/files/company_tickers_exchange.json",
                       "as_of": iso_utc(retrieved_at), "retrieved_at": iso_utc(retrieved_at),
                       "as_of_policy": "observed_current_mapping_not_historical_identity",
                       "raw_content_hash": hashlib.sha256(raw).hexdigest(), "row_index": index,
                       "identity_version": IDENTITY_VERSION})
    return output


def bind_portfolio_identity(portfolio: dict, *, sec_mapping: list[dict], security_metadata: list[dict]) -> dict:
    """security_metadata 必须来自后续已验证身份适配，不能由手填持仓填充。"""
    validate_contract("portfolio", portfolio)
    bindings = []
    collection_only = portfolio.get("schema_version") == "live-portfolio/2.0.0"
    for position in portfolio["positions"]:
        mapping = [
            m for m in sec_mapping
            if m["ticker"] == position["ticker"]
            and (position.get("exchange") is None or m["exchange"] == position["exchange"])
        ]
        candidates = [
            m for m in security_metadata
            if m["ticker"] == position["ticker"]
            and (position.get("exchange") is None or m["exchange"] == position["exchange"])
        ]
        if len(mapping) != 1 or len(candidates) != 1:
            raise ValueError("LIVE_SECURITY_IDENTITY_AMBIGUOUS_OR_MISSING")
        listing, metadata = mapping[0], candidates[0]
        if (
            metadata["security_type"] != "COMMON_STOCK"
            or metadata["currency"] != "USD"
            or (not collection_only and metadata["share_class"] != position["share_class"])
            or (collection_only and position.get("share_class") is not None and metadata["share_class"] != position["share_class"])
        ):
            raise ValueError("LIVE_SECURITY_TYPE_OR_CLASS_UNSUPPORTED")
        if normalize_cik(metadata["cik"]) != listing["cik"] or metadata["filing_regime"] != "DOMESTIC_10K_10Q":
            raise ValueError("LIVE_ISSUER_BINDING_MISMATCH")
        for field in ("source_id", "source_locator", "as_of", "retrieved_at", "raw_content_hash"):
            if not metadata.get(field):
                raise ValueError("LIVE_IDENTITY_PROVENANCE_MISSING")
        iso_utc(metadata["as_of"])
        iso_utc(metadata["retrieved_at"])
        if parse_timestamp(metadata["as_of"]) > parse_timestamp(metadata["retrieved_at"]):
            raise ValueError("LIVE_IDENTITY_TIME_INVALID")
        bindings.append({"security_id": position["security_id"], "ticker": position["ticker"],
                         "exchange": metadata["exchange"], "share_class": metadata["share_class"], "cik": listing["cik"],
                         "sec_mapping_hash": content_hash(listing), "security_metadata_hash": content_hash(metadata)})
    result = {"identity_version": IDENTITY_VERSION, "portfolio_hash": content_hash(portfolio), "bindings": bindings,
              "sec_mapping_hash": content_hash(sec_mapping), "security_metadata_hash": content_hash(security_metadata)}
    result["identity_hash"] = content_hash(result)
    return result


def freeze_identity(portfolio: dict, *, sec_mapping: list[dict], security_metadata: list[dict], cutoff: str) -> dict:
    """保留绑定底层资料；读取时重算，不只信任 identity_hash 摘要。"""
    from copy import deepcopy
    binding = bind_portfolio_identity(portfolio, sec_mapping=sec_mapping, security_metadata=security_metadata)
    for item in [*sec_mapping, *security_metadata]:
        for field in ("as_of", "retrieved_at"):
            if parse_timestamp(item[field]) > parse_timestamp(cutoff):
                raise ValueError("LIVE_IDENTITY_AFTER_CUTOFF")
    return deepcopy({"binding": binding, "sec_mapping": sec_mapping, "security_metadata": security_metadata})


def verify_frozen_identity(portfolio: dict, frozen: dict | None, *, cutoff: str) -> dict:
    if not isinstance(frozen, dict) or set(frozen) != {"binding", "sec_mapping", "security_metadata"}:
        raise ValueError("LIVE_IDENTITY_SNAPSHOT_MISSING")
    rebuilt = freeze_identity(portfolio, sec_mapping=frozen["sec_mapping"],
                              security_metadata=frozen["security_metadata"], cutoff=cutoff)
    if frozen != rebuilt:
        raise ValueError("LIVE_IDENTITY_BINDING_MISMATCH")
    return rebuilt["binding"]
