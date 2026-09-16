"""从行情身份字段与 SEC 封面普通股标签交叉绑定；不从 ticker 猜证券类型。"""
import hashlib
from html.parser import HTMLParser
import json
import re
from pathlib import Path

from product.mcp.provenance import iso_utc, parse_timestamp

METADATA_VERSION = "us-equity-security-metadata/1.0.0"
EASTMONEY_METADATA_VERSION = "us-equity-security-metadata/2.0.0"
YAHOO_EXCHANGES = {"NMS": "XNAS", "NGM": "XNAS", "NCM": "XNAS", "NYQ": "XNYS", "ASE": "XASE"}
SEC_EXCHANGES = {"NASDAQ": "XNAS", "THE NASDAQ STOCK MARKET LLC": "XNAS",
                 "THE NASDAQ GLOBAL SELECT MARKET": "XNAS",
                 "NYSE": "XNYS", "NEW YORK STOCK EXCHANGE": "XNYS",
                 "NYSEAMER": "XASE", "NYSE AMERICAN": "XASE"}


def eastmoney_policy():
    from product.mcp.provenance import content_hash
    value = json.loads(Path(__file__).with_name("eastmoney-identity-policy.json").read_text())
    if (value.get("policy_version") != "eastmoney-us-identity/1.0.0"
            or value.get("provider") != "eastmoney" or value.get("client") != "akshare/1.18.94"
            or value.get("market_codes") != {"XNAS": 105, "XNYS": 106, "XASE": 107}
            or value.get("currency") != "USD"):
        raise ValueError("EASTMONEY_IDENTITY_POLICY_INVALID")
    return value, content_hash(value)


def eastmoney_symbol(ticker, exchange):
    policy, _ = eastmoney_policy()
    # 标点股类代码不能静默将 '-'、'.' 相互替换；明确拒绝待核实的编码。
    if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,14}", ticker) or exchange not in policy["market_codes"]:
        raise ValueError("EASTMONEY_SECURITY_MAPPING_UNSUPPORTED")
    return f"{policy['market_codes'][exchange]}.{ticker}"


def parse_eastmoney_identity(raw, *, ticker, exchange, record):
    from product.mcp.live.eastmoney_transport import ADAPTER_VERSION, AKSHARE_VERSION, ENDPOINT
    policy, policy_hash = eastmoney_policy()
    symbol = eastmoney_symbol(ticker, exchange)
    key = record["key"]
    if (hashlib.sha256(raw).hexdigest() != record["raw_content_hash"]
            or key.get("provider") != "eastmoney" or key.get("provider_symbol") != symbol
            or key.get("client_version") != AKSHARE_VERSION or key.get("adapter_version") != ADAPTER_VERSION
            or key.get("endpoint") != ENDPOINT):
        raise ValueError("EASTMONEY_IDENTITY_SOURCE_MISMATCH")
    data = json.loads(raw)
    meta = data.get("data")
    if (data.get("rc") != 0 or not isinstance(meta, dict) or meta.get("code") != ticker
            or type(meta.get("market")) is not int or meta["market"] != policy["market_codes"][exchange]):
        raise ValueError("EASTMONEY_IDENTITY_RESPONSE_MISMATCH")
    return {"ticker": ticker, "exchange": exchange, "currency": policy["currency"],
            "provider_symbol": symbol, "market": meta["market"],
            "source_id": "eastmoney-kline-identity", "source_locator": ENDPOINT,
            "as_of": record["retrieved_at"], "retrieved_at": record["retrieved_at"],
            "as_of_policy": "observed_current_identity_not_historical",
            "raw_content_hash": record["raw_content_hash"], "metadata_version": EASTMONEY_METADATA_VERSION,
            "identity_policy_version": policy["policy_version"], "identity_policy_hash": policy_hash,
            "currency_policy": "akshare-stock_us_hist-documented-USD"}


def parse_chart_identity(raw: bytes, *, ticker: str, record: dict) -> dict:
    if hashlib.sha256(raw).hexdigest() != record["raw_content_hash"]:
        raise ValueError("YAHOO_METADATA_HASH_MISMATCH")
    body = json.loads(raw)
    chart = body["chart"]
    if chart.get("error") or not isinstance(chart.get("result"), list) or len(chart["result"]) != 1:
        raise ValueError("YAHOO_METADATA_RESULT_INVALID")
    metadata = chart["result"][0]["meta"]
    if (metadata.get("symbol") != ticker or metadata.get("instrumentType") != "EQUITY"
            or metadata.get("currency") != "USD" or metadata.get("exchangeName") not in YAHOO_EXCHANGES
            or metadata.get("exchangeTimezoneName") != "America/New_York"):
        raise ValueError("YAHOO_SECURITY_METADATA_UNSUPPORTED")
    return {"ticker": ticker, "exchange": YAHOO_EXCHANGES[metadata["exchangeName"]], "currency": "USD",
            "source_id": "yahoo-chart-identity", "source_locator": record["key"]["endpoint"],
            "as_of": record["retrieved_at"], "retrieved_at": record["retrieved_at"],
            "as_of_policy": "observed_current_identity_not_historical", "raw_content_hash": record["raw_content_hash"],
            "metadata_version": METADATA_VERSION}


class CoverTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items, self.active = [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "ix:nonnumeric":
            if self.active is not None:
                raise ValueError("SEC_COVER_NESTED_TAG")
            name = attrs.get("name", "")
            if name.startswith("dei:") and name.split(":", 1)[1] in ("TradingSymbol", "Security12bTitle", "SecurityExchangeName"):
                self.active = {"field": name.split(":", 1)[1], "context": attrs.get("contextref"), "text": []}
                if not self.active["context"] or attrs.get("continuedat"):
                    raise ValueError("SEC_COVER_CONTEXT_OR_CONTINUATION_UNSUPPORTED")

    def handle_data(self, data):
        if self.active is not None:
            self.active["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "ix:nonnumeric" and self.active is not None:
            self.items.append(dict(self.active, text=" ".join("".join(self.active["text"]).split())))
            self.active = None


def bind_disclosure_security(raw: bytes, document: dict, quote: dict) -> dict:
    if document["form"] not in ("10-K", "10-Q"):
        raise ValueError("SEC_DOMESTIC_FILING_REQUIRED")
    if hashlib.sha256(raw).hexdigest() != document["raw_content_hash"]:
        raise ValueError("SEC_COVER_HASH_MISMATCH")
    parser = CoverTags()
    parser.feed(raw.decode("utf-8", errors="strict"))
    parser.close()
    if parser.active is not None:
        raise ValueError("SEC_COVER_UNCLOSED_TAG")
    groups = {}
    for item in parser.items:
        groups.setdefault(item["context"], {}).setdefault(item["field"], set()).add(item["text"])
    matched = []
    for context, fields in groups.items():
        if fields.get("TradingSymbol") != {quote["ticker"]}:
            continue
        if any(len(fields.get(key, ())) != 1 for key in ("Security12bTitle", "SecurityExchangeName")):
            raise ValueError("SEC_COVER_IDENTITY_AMBIGUOUS")
        title = next(iter(fields["Security12bTitle"]))
        exchange = next(iter(fields["SecurityExchangeName"])).upper()
        # 同一封面可以在不同 XBRL context 中以相同符号登记普通股和债券。
        # 仅排除明确的定息债券标题；仍需唯一普通股 context，未知类型不猜测。
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%\s+(?:Notes|Bonds)\s+due\s+[0-9]{4}", title, re.I):
            continue
        if (not re.search(r"\b(common stock|common shares|ordinary shares)\b", title, re.I)
                or re.search(r"depositary|depository|preferred|preference|units|warrants", title, re.I)):
            raise ValueError("SEC_COMMON_STOCK_NOT_VERIFIED")
        if SEC_EXCHANGES.get(exchange) != quote["exchange"]:
            raise ValueError("SEC_EASTMONEY_EXCHANGE_CONFLICT" if quote.get("metadata_version") == EASTMONEY_METADATA_VERSION else "SEC_YAHOO_EXCHANGE_CONFLICT")
        classes = re.findall(r"\bClass\s+([A-Z0-9]+)\b", title, re.I)
        if len(set(c.upper() for c in classes)) > 1:
            raise ValueError("SEC_SHARE_CLASS_AMBIGUOUS")
        matched.append((context, title, classes[0].upper() if classes else "common"))
    if len(matched) != 1:
        raise ValueError("SEC_COVER_IDENTITY_AMBIGUOUS_OR_MISSING")
    context, title, share_class = matched[0]
    retrieved = max((document["retrieved_at"], quote["retrieved_at"]), key=parse_timestamp)
    return {"ticker": quote["ticker"], "exchange": quote["exchange"], "currency": quote["currency"],
            "security_type": "COMMON_STOCK", "share_class": share_class, "cik": document["cik"],
            "filing_regime": "DOMESTIC_10K_10Q", "source_id": document["source_id"],
            "source_locator": document["source_locator"], "as_of": quote["as_of"],
            "retrieved_at": iso_utc(retrieved), "raw_content_hash": document["raw_content_hash"],
            "cover_context": context, "security_title": title, "accession": document["accession"], "form": document["form"],
            "published_at": document["published_at"], "quote_identity": quote,
            "metadata_version": quote.get("metadata_version", METADATA_VERSION)}
