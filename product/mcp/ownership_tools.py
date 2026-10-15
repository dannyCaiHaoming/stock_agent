"""Ownership tools for the stock-data MCP server: insider transactions (SEC Form 4).

Point in time by SEC acceptance time. Numbers are as reported (not split-adjusted); interpretation is left
to the agent.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
import re
import xml.etree.ElementTree as ET
from typing import Any

from product.mcp import data_tools, settings
from product.mcp.data_tools import DataToolError, _cutoff, _num
from product.mcp.live.sec_client import SecClient
from product.mcp.provenance import iso_utc, parse_timestamp

OPEN_MARKET = {"P": "open_market_purchase", "S": "open_market_sale"}
OTHER_CODES = {"A": "grant_or_award", "M": "option_exercise", "F": "tax_withholding", "G": "gift",
               "C": "conversion", "X": "option_exercise_in_the_money", "D": "disposition_to_issuer",
               "J": "other", "W": "will_or_inheritance", "I": "discretionary", "V": "voluntary_report"}
MAX_FILINGS = 60


def _text(node: ET.Element, path: str) -> str | None:
    found = node.find(path)
    return found.text.strip() if found is not None and found.text and found.text.strip() else None


def _dec(value: str | None) -> Decimal | None:
    try:
        return Decimal(value) if value is not None else None
    except InvalidOperation:
        return None


def _raw_xml_url(document_url: str) -> str:
    # Primary document is often the XSL-rendered view (".../xslF345X05/form4.xml"); the raw XML sits one level up.
    return re.sub(r"/xslF345X\d+/", "/", document_url)


def _parse(raw: bytes) -> dict[str, Any]:
    root = ET.fromstring(raw)
    owners = []
    for owner in root.findall(".//reportingOwner"):
        rel = owner.find("reportingOwnerRelationship")
        roles = [name for name, tag in (("director", "isDirector"), ("officer", "isOfficer"),
                                        ("10%_owner", "isTenPercentOwner"), ("other", "isOther"))
                 if rel is not None and _text(rel, tag) in ("1", "true")]
        title = _text(rel, "officerTitle") if rel is not None else None
        owners.append({"name": _text(owner, "reportingOwnerId/rptOwnerName"),
                       "roles": roles + ([title] if title else [])})
    footnotes = " ".join((f.text or "") for f in root.findall(".//footnotes/footnote"))
    plan = (_text(root, "aff10b5One") in ("1", "true")) or bool(re.search(r"10b5-1", footnotes, re.I))
    rows = []
    for node in root.findall(".//nonDerivativeTransaction"):
        rows.append({"date": _text(node, "transactionDate/value"),
                     "code": _text(node, "transactionCoding/transactionCode"),
                     "acquired_disposed": _text(node, "transactionAmounts/transactionAcquiredDisposedCode/value"),
                     "shares": _dec(_text(node, "transactionAmounts/transactionShares/value")),
                     "price": _dec(_text(node, "transactionAmounts/transactionPricePerShare/value")),
                     "shares_after": _dec(_text(node, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"))})
    return {"owners": owners, "rule_10b5_1": plan, "transactions": rows}


def get_insider_transactions(ticker: str, days: int = 180, as_of: str | None = None) -> dict[str, Any]:
    cutoff = _cutoff(as_of)
    days = max(30, min(int(days), 730))
    start = cutoff - timedelta(days=days)
    identity = data_tools.resolve_company(ticker)
    client = SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=MAX_FILINGS + 10)
    filings, _ = data_tools._submissions(identity, client, cutoff)
    form4 = sorted((f for f in filings.values() if f["form"] in ("4", "4/A")
                    and start <= parse_timestamp(f["published_at"]) <= cutoff),
                   key=lambda f: f["published_at"], reverse=True)
    skipped = max(0, len(form4) - MAX_FILINGS)
    open_market, other = [], {}
    errors = 0
    for filing in form4[:MAX_FILINGS]:
        try:
            record = client.fetch(_raw_xml_url(filing["document_url"]), max_age_seconds=365 * 86400,
                                  stable_document=True)
            parsed = _parse(client.cache.read(record))
        except Exception:  # noqa: BLE001 - count and continue; one bad filing must not hide the rest
            errors += 1
            continue
        who = "; ".join(o["name"] or "?" for o in parsed["owners"])
        roles = sorted({r for o in parsed["owners"] for r in o["roles"]})
        for t in parsed["transactions"]:
            if t["code"] in OPEN_MARKET:
                value = t["shares"] * t["price"] if t["shares"] is not None and t["price"] is not None else None
                open_market.append([filing["published_at"][:10], t["date"], who, ", ".join(roles),
                                    OPEN_MARKET[t["code"]], _num(t["shares"]), _num(t["price"]),
                                    _num(value, 0), parsed["rule_10b5_1"], _num(t["shares_after"]),
                                    filing["accession"]])
            elif t["code"]:
                other[OTHER_CODES.get(t["code"], t["code"])] = other.get(OTHER_CODES.get(t["code"], t["code"]), 0) + 1

    def total(kind: str, plan: bool | None = None) -> dict[str, Any]:
        rows = [r for r in open_market if r[4] == kind and (plan is None or r[8] == plan)]
        value = sum((Decimal(r[7]) for r in rows if r[7] is not None), Decimal(0))
        return {"transactions": len(rows), "insiders": len({r[2] for r in rows}), "value_usd": _num(value, 0)}
    return {
        "ticker": identity["ticker"], "window": [iso_utc(start)[:10], iso_utc(cutoff)[:10]],
        "form4_filings_in_window": len(form4), "form4_parsed": min(len(form4), MAX_FILINGS) - errors,
        "form4_not_read": skipped + errors,
        "summary": {"open_market_purchases": total("open_market_purchase"),
                    "open_market_sales": total("open_market_sale"),
                    "open_market_sales_under_10b5_1_plan": total("open_market_sale", True),
                    "other_transactions_by_type": other},
        "columns": ["filed", "trade_date", "insider", "role", "type", "shares", "price", "value_usd",
                    "rule_10b5_1_plan", "shares_owned_after", "accession"],
        "open_market_rows": open_market[:40],
        "provenance": {"source_id": f"sec-form4-{identity['cik']}", "as_of": iso_utc(cutoff),
                       "notes": "SEC Form 4 non-derivative transactions, filed within the window (point in time by "
                                "acceptance time). Shares/prices as reported, not split-adjusted. 10b5-1 flag from "
                                "the form checkbox or footnotes. Grants, exercises and tax withholding are counted "
                                "only. Most recent 60 filings are read."},
    }


# Well-known 13F filers tracked for "smart money" positioning (CIKs resolved via EDGAR company search,
# 2026-10-15). This is a fixed sample, not the whole institutional market.
TRACKED_13F = {
    "Berkshire Hathaway": "0001067983", "Bridgewater Associates": "0001350694",
    "Renaissance Technologies": "0001037389", "Pershing Square": "0001336528", "Appaloosa": "0001656456",
    "Baupost Group": "0001054420", "Tiger Global": "0001167483", "Coatue": "0001135730",
    "Lone Pine": "0001061165", "Viking Global": "0001103804", "Third Point": "0001040273",
    "Duquesne Family Office": "0001536411", "Soros Fund Management": "0001029160",
    "Scion Asset Management": "0001649339", "Elliott Investment Management": "0001791786",
    "D1 Capital Partners": "0001747057", "Maverick Capital": "0000934639", "Icahn (Carl C)": "0000921669",
}
_SUFFIXES = re.compile(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|HOLDINGS?|GROUP|NV|SA|AG|"
                       r"CL|CLASS|COM|NEW|DEL|THE)\b")


def _norm(name: str) -> str:
    return " ".join(_SUFFIXES.sub(" ", re.sub(r"[^A-Z0-9 ]", " ", name.upper())).split())


def _info_table(client: SecClient, cik: str, filing: dict) -> list[dict[str, Any]]:
    from product.mcp.live.attachments import _Rows
    prefix = filing["document_url"].rsplit("/", 1)[0]
    index = client.fetch(f"{prefix}/{filing['accession']}-index.html", max_age_seconds=365 * 86400,
                         stable_document=True)
    parser = _Rows()
    parser.feed(client.cache.read(index).decode("utf-8", errors="replace"))
    parser.close()
    # Raw XML only: the "/xslForm13F_X02/" links are the rendered HTML view.
    raw_xml = [(cells, links[0]) for cells, links in parser.rows
               if links and links[0].lower().endswith(".xml") and "/xsl" not in links[0].lower()
               and "primary_doc" not in links[0].lower()]
    xml_links = [link for cells, link in raw_xml if "INFORMATION TABLE" in " ".join(cells).upper()] \
        or [link for _, link in raw_xml]
    if not xml_links:
        raise DataToolError("13F_INFORMATION_TABLE_NOT_FOUND")
    href = xml_links[0]
    url = href if href.startswith("http") else f"https://www.sec.gov{href}"
    record = client.fetch(url, max_age_seconds=365 * 86400, stable_document=True)
    root = ET.fromstring(client.cache.read(record))
    rows = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].lower() != "infotable":
            continue
        def child(name: str) -> str | None:
            for c in node.iter():
                if c.tag.rsplit("}", 1)[-1] == name and c.text and c.text.strip():
                    return c.text.strip()
            return None
        rows.append({"issuer": child("nameOfIssuer") or "", "class": child("titleOfClass"),
                     "cusip": (child("cusip") or "").upper(), "value": _dec(child("value")),
                     "shares": _dec(child("sshPrnamt")), "put_call": child("putCall")})
    return rows


def get_fund_holdings(ticker: str, as_of: str | None = None) -> dict[str, Any]:
    cutoff = _cutoff(as_of)
    identity = data_tools.resolve_company(ticker)
    target = _norm(identity["name"])
    client = SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=120)
    out, notes = [], []
    for fund, cik in TRACKED_13F.items():
        try:
            filings, _ = data_tools._submissions({"cik": cik}, client, cutoff)
            reports = sorted((f for f in filings.values() if f["form"] == "13F-HR"
                              and parse_timestamp(f["published_at"]) <= cutoff),
                             key=lambda f: f["published_at"], reverse=True)[:2]
            if not reports:
                notes.append(f"{fund}: no 13F-HR filed before as_of")
                continue
            periods = []
            for filing in reports:
                rows = [r for r in _info_table(client, cik, filing) if r["issuer"] and _norm(r["issuer"]) == target]
                shares = sum((r["shares"] for r in rows if r["shares"] is not None and not r["put_call"]), Decimal(0))
                options = sorted({f"{r['put_call']} {_num(r['shares'])}" for r in rows if r["put_call"]})
                periods.append({"period": filing["report_date"], "filed": filing["published_at"][:10],
                                "shares": shares, "options": options,
                                "classes": sorted({r["class"] or "" for r in rows if not r["put_call"]})})
            latest = periods[0]
            prior = periods[1] if len(periods) > 1 else None
            if latest["shares"] == 0 and not latest["options"] and (prior is None or prior["shares"] == 0):
                continue
            change = None
            if prior is not None:
                change = "new" if prior["shares"] == 0 and latest["shares"] > 0 else \
                    "exited" if latest["shares"] == 0 and prior["shares"] > 0 else \
                    (_num((latest["shares"] / prior["shares"] - 1) * 100, 1) + "%") if prior["shares"] else None
            out.append([fund, latest["period"], latest["filed"], _num(latest["shares"]),
                        _num(prior["shares"]) if prior else None, change, ", ".join(latest["options"]) or None,
                        ", ".join(latest["classes"])])
        except Exception as exc:  # noqa: BLE001 - one fund failing must not hide the others
            notes.append(f"{fund}: {type(exc).__name__}: {str(exc)[:120]}")
    return {
        "ticker": identity["ticker"], "issuer_name_matched": identity["name"], "as_of": iso_utc(cutoff),
        "columns": ["fund", "report_period", "filed", "shares", "prior_quarter_shares", "change",
                    "options_put_call", "classes"],
        "rows": out, "funds_tracked": len(TRACKED_13F), "notes": notes,
        "provenance": {"source_id": "sec-13f-tracked-funds",
                       "notes": "Latest two 13F-HR reports filed before as_of for a fixed list of well-known managers "
                                "(not the whole market). 13F is filed up to 45 days after quarter end, long equity "
                                "positions only; share counts as reported (not split-adjusted). Issuer matched by "
                                "normalized name; amendments ignored."},
    }
