"""U.S. House members' stock trades from Periodic Transaction Reports (PTR), clerk.house.gov.

Point in time by filing date (the date a report became public). Amounts are ranges as filed.
The Senate (efdsearch.senate.gov) requires accepting terms of use on the website and is not covered.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from io import BytesIO
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.request import Request

from product.mcp import settings
from product.mcp.data_tools import DataToolError, _cutoff, _ticker
from product.mcp.live import macro
from product.mcp.provenance import iso_utc

INDEX_ZIP = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_PDF = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
ROW = re.compile(
    r"(?P<asset>[^()\n]{2,120}?)\s*\((?P<ticker>[A-Z][A-Z.]{0,6})\)\s*\[(?P<kind>[A-Z]{2})\]\s*"
    r"(?P<type>P|S(?: \(partial\))?|E)\s+(?P<trade>\d{2}/\d{2}/\d{4})\s+(?P<notified>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<amount>\$[\d,]+\s*-\s*\$[\d,]+|Over \$[\d,]+|\$[\d,]+ +-)")
TYPES = {"P": "purchase", "S": "sale", "S (partial)": "partial_sale", "E": "exchange"}


def _index_dir() -> Path:
    path = settings.cache().root / "derived" / "house-ptr"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get(url: str) -> bytes:
    response = macro._http(Request(url, headers={"User-Agent": settings.sec_user_agent()}))
    if response.status != 200:
        raise DataToolError(f"HOUSE_HTTP_{response.status}")
    return response.body


def _filings(year: int) -> list[dict[str, str]]:
    raw = _get(INDEX_ZIP.format(year=year))
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        root = ET.fromstring(archive.read(f"{year}FD.xml"))
    out = []
    for member in root:
        if member.findtext("FilingType") != "P":
            continue
        filed = datetime.strptime(member.findtext("FilingDate") or "", "%m/%d/%Y").date()
        name = " ".join(x for x in (member.findtext("First"), member.findtext("Last")) if x)
        out.append({"doc_id": member.findtext("DocID") or "", "member": name,
                    "district": member.findtext("StateDst") or "", "filed": filed.isoformat()})
    return out


def _parse_pdf(raw: bytes) -> list[dict[str, str]]:
    from pypdf import PdfReader
    text = " ".join(" ".join(page.extract_text() or "" for page in PdfReader(BytesIO(raw)).pages)
                    .replace("\x00", "").split())
    rows = []
    for m in ROW.finditer(text):
        # The asset group also swallows preceding text; the owner code (SP/JT/DC) right before the asset name
        # marks where the row starts. Without one the filer owns it.
        head = m.group("asset")
        owner = "self"
        found = list(re.finditer(r"(?:^|\s)(SP|JT|DC)\s+", head))
        if found:
            owner, head = found[-1].group(1), head[found[-1].end():]
        else:
            head = re.split(r"\$200\?|: [^:]*?(?=\s[A-Z][a-z])", head)[-1]
        rows.append({"owner": owner, "asset": head.strip()[-80:],
                     "ticker": m.group("ticker"), "asset_type": m.group("kind"),
                     "type": TYPES.get(m.group("type"), m.group("type")),
                     "trade_date": datetime.strptime(m.group("trade"), "%m/%d/%Y").date().isoformat(),
                     "amount": " ".join(m.group("amount").split())})
    return rows


def update_index(year: int, max_new: int | None = None) -> dict[str, Any]:
    """Download and parse PTRs of `year` not yet indexed. Returns counts."""
    path = _index_dir() / f"{year}.json"
    index = json.loads(path.read_text()) if path.exists() else {"year": year, "reports": {}}
    todo = [f for f in _filings(year) if f["doc_id"] not in index["reports"]]
    if max_new is not None:
        todo = todo[:max_new]
    for filing in todo:
        try:
            rows = _parse_pdf(_get(PTR_PDF.format(year=year, doc_id=filing["doc_id"])))
            index["reports"][filing["doc_id"]] = {**filing, "rows": rows, "status": "PARSED" if rows else "NO_TEXT_ROWS"}
        except Exception as exc:  # noqa: BLE001 - record and continue
            index["reports"][filing["doc_id"]] = {**filing, "rows": [], "status": f"ERROR {type(exc).__name__}"}
    index["updated_at"] = iso_utc(datetime.now(UTC))
    path.write_text(json.dumps(index, ensure_ascii=False))
    return {"year": year, "new_reports": len(todo), "total_reports": len(index["reports"])}


def get_congress_trades(ticker: str, days: int = 365, as_of: str | None = None) -> dict[str, Any]:
    cutoff = _cutoff(as_of)
    symbol = _ticker(ticker)
    days = max(30, min(int(days), 730))
    start = (cutoff - timedelta(days=days)).date()
    end = cutoff.date()
    rows, coverage = [], {}
    for year in range(start.year, end.year + 1):
        path = _index_dir() / f"{year}.json"
        if year == datetime.now(UTC).year:
            try:
                update_index(year, max_new=40)  # keep the current year fresh, a few reports per call
            except Exception:  # noqa: BLE001 - fall back to the existing index
                pass
        if not path.exists():
            coverage[str(year)] = "NOT_INDEXED (run scripts/build-house-ptr-index.py)"
            continue
        index = json.loads(path.read_text())
        reports = index["reports"].values()
        coverage[str(year)] = {"reports": len(index["reports"]),
                               "unreadable": sum(1 for r in reports if r["status"] != "PARSED"),
                               "updated_at": index.get("updated_at")}
        for report in reports:
            filed = date.fromisoformat(report["filed"])
            if not start <= filed <= end:
                continue
            for row in report["rows"]:
                if row["ticker"] == symbol:
                    rows.append([report["filed"], row["trade_date"], report["member"], report["district"],
                                 row["owner"], row["type"], row["amount"], row["asset_type"], report["doc_id"]])
    rows.sort(reverse=True)
    summary: dict[str, int] = {}
    for r in rows:
        summary[r[5]] = summary.get(r[5], 0) + 1
    return {
        "ticker": symbol, "window": [start.isoformat(), end.isoformat()],
        "summary_by_type": summary, "members": len({r[2] for r in rows}),
        "columns": ["filed", "trade_date", "member", "district", "owner", "type", "amount_range", "asset_type",
                    "doc_id"],
        "rows": rows[:50], "coverage": coverage,
        "provenance": {"source_id": "house-clerk-ptr", "source_locator": INDEX_ZIP.format(year=end.year),
                       "notes": "U.S. House Periodic Transaction Reports filed within the window (point in time by "
                                "filing date; trades can be reported up to 45 days late). Amounts are ranges. "
                                "Owner: self, SP spouse, JT joint, DC dependent child. asset_type ST stock, OP option. "
                                "Scanned/handwritten reports cannot be parsed (counted as unreadable). Senate not "
                                "covered."},
    }
