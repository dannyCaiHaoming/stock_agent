"""从 SEC 文档索引定位业绩附件候选；不跟随外站或任意链接。"""
import hashlib
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

from product.mcp.live.sec_client import validate_sec_url

ATTACHMENT_VERSION = "sec-exhibit-index/1.0.0"


class _Rows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.cells, self.links, self.cell = [], None, [], None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells, self.links = [], []
        elif tag in ("td", "th") and self.cells is not None:
            self.cell = []
        elif tag == "a" and self.cell is not None:
            href = dict(attrs).get("href")
            if href is not None:
                self.links.append(href)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.cells is not None:
            self.rows.append((self.cells, self.links))
            self.cells, self.cell = None, None


def earnings_attachments(raw: bytes, index_document: dict, *, limit: int = 3) -> dict:
    if type(limit) is not int or limit < 0 or limit > 3:
        raise ValueError("SEC_ATTACHMENT_BUDGET_INVALID")
    if hashlib.sha256(raw).hexdigest() != index_document["raw_content_hash"]:
        raise ValueError("SEC_INDEX_HASH_MISMATCH")
    index_url = validate_sec_url(index_document["source_locator"])
    prefix = index_url.rsplit("/", 1)[0] + "/"
    parser = _Rows()
    parser.feed(raw.decode("utf-8", errors="strict"))
    parser.close()
    candidates, rejected, seen = [], [], set()
    for row_index, (cells, links) in enumerate(parser.rows):
        if len(cells) != 5 or not re.fullmatch(r"EX-99(?:\.\d+)?", cells[3], re.I):
            continue
        if not re.search(r"earnings|financial\s+results|results\s+of\s+operations", cells[1], re.I):
            rejected.append({"row_index": row_index, "reason": "EXHIBIT_PURPOSE_NOT_VERIFIED"})
            continue
        if len(links) != 1:
            raise ValueError("SEC_ATTACHMENT_LINK_AMBIGUOUS")
        url = urljoin(index_url, links[0])
        validate_sec_url(url)
        if not url.startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*\.html?", url[len(prefix):], re.I):
            raise ValueError("SEC_ATTACHMENT_PATH_REJECTED")
        if url in seen:
            continue
        seen.add(url)
        candidates.append({"document_url": url, "description": cells[1], "exhibit_type": cells[3],
                           "index_row": row_index, "index_source_id": index_document["source_id"],
                           "index_url": index_url, "index_raw_hash": index_document["raw_content_hash"],
                           "index_retrieved_at": index_document["retrieved_at"],
                           "selection_version": ATTACHMENT_VERSION})
    return {"selected": candidates[:limit], "omitted": candidates[limit:], "rejected": rejected,
            "coverage": "DESCRIPTION_MATCHED_EXHIBITS_ONLY", "selection_version": ATTACHMENT_VERSION}
