"""有限披露章节提取；位置单位为严格解码后的原始 HTML 字符。"""
from __future__ import annotations

import hashlib
from html import unescape
from html.parser import HTMLParser
import re

from product.mcp.provenance import content_hash

PARSER_VERSION = "sec-sections/0.3.1"
SECTION_NAMES = ("business", "risk_factors", "management_discussion")


def _heading_word(word: str) -> str:
    # SEC small-cap headings can split a word across HTML text nodes. Match
    # that whitespace without rewriting the text or its source offsets.
    return r"\s*".join(re.escape(letter) for letter in word)


SECTION_PATTERNS = (
    ("business", _heading_word("business") + r"\b"),
    ("risk_factors", _heading_word("risk") + r"\s+" + _heading_word("factors") + r"\b"),
    ("management_discussion", _heading_word("management") +
     r"\s*(?:[’']\s*s|s)?\s+" + _heading_word("discussion") + r"\b"),
)


def _section_name(title: str) -> str | None:
    return next((name for name, pattern in SECTION_PATTERNS
                 if re.match(pattern, title.lstrip(), re.I)), None)


class _Text(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.lines = [0]
        self.lines.extend(match.end() for match in re.finditer("\n", source))
        self.parts, self.spans, self.hidden = [], [], []
        self.length = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "ix:hidden"):
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[:self.hidden.index(tag)]

    def handle_startendtag(self, tag, attrs):
        pass

    def _add(self, raw, value):
        if self.hidden or not value.strip():
            return
        line, column = self.getpos()
        start = self.lines[line - 1] + column
        self.parts.append(value + " ")
        self.spans.append((self.length, self.length + len(value), start, start + len(raw)))
        self.length += len(value) + 1

    def handle_data(self, data):
        self._add(data, data)

    def handle_entityref(self, name):
        raw = f"&{name};"
        self._add(raw, unescape(raw))

    def handle_charref(self, name):
        raw = f"&#{name};"
        self._add(raw, unescape(raw))


def extract_sections(raw: bytes, document: dict, *, encoding: str = "utf-8",
                     section_limit: int = 8000, total_limit: int = 20000) -> dict:
    if any(type(value) is not int or value <= 0 for value in (section_limit, total_limit)):
        raise ValueError("SEC_TEXT_BUDGET_INVALID")
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("SEC_TEXT_TOO_LARGE")
    if hashlib.sha256(raw).hexdigest() != document["raw_content_hash"]:
        raise ValueError("SEC_DOCUMENT_HASH_MISMATCH")
    if encoding not in ("utf-8", "windows-1252"):
        raise ValueError("SEC_TEXT_ENCODING_UNSUPPORTED")
    source = raw.decode(encoding, errors="strict")
    parser = _Text(source)
    parser.feed(source)
    parser.close()
    text = "".join(parser.parts)
    candidates = re.finditer(
        r"\bItem\s+\d+(?:\.\d+|[A-Z])?\b\s*(?P<delimiter>[.:-])?\s*", text, re.I)
    # Bare page headers ("Item 1") and inline references ("Item 7 of this
    # Form") are not section ends. A title without punctuation is accepted
    # only for one of the explicitly supported sections.
    headings = [match for match in candidates
                if match.group("delimiter") or _section_name(text[match.end():match.end() + 200])]
    pieces, found, remaining = [], set(), total_limit
    omitted_occurrences = []
    section_remaining = dict.fromkeys(SECTION_NAMES, section_limit)
    for i, heading in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        title = text[heading.end():end].lstrip()
        section = _section_name(title)
        if section is None:
            continue
        found.add(section)
        # 保留重复标题的不同位置，不把目录条目偷偷当作完整正文。
        keep = min(end - heading.start(), section_remaining[section], remaining)
        if keep <= 0:
            omitted_occurrences.append({"section": section, "normalized_text_range": [heading.start(), end],
                                        "reason": "TEXT_BUDGET_EXHAUSTED"})
            continue
        stop = heading.start() + keep
        spans = [[start, finish] for left, right, start, finish in parser.spans
                 if left < stop and right > heading.start()]
        fact = {key: document[key] for key in ("source_id", "source_locator", "as_of",
                "published_at", "retrieved_at", "raw_content_hash", "cik", "accession", "form")}
        fact.update(section=section, text=text[heading.start():stop],
                    raw_character_spans=spans, normalized_text_range=[heading.start(), stop],
                    locator_policy="raw-decoded-html-character-spans/end-exclusive",
                    encoding=encoding, parser_version=PARSER_VERSION,
                    untrusted_data=True, truncated=stop < end)
        fact["evidence_id"] = "ev-sec-text-" + content_hash(fact)
        pieces.append(fact)
        remaining -= keep
        section_remaining[section] -= keep
    return {"evidence": pieces, "missing_sections": sorted(set(SECTION_NAMES) - found),
            "unemitted_sections": sorted(found - {piece["section"] for piece in pieces}),
            "budget_exhausted": remaining == 0,
            "omitted_occurrences": omitted_occurrences,
            "coverage": "HEADING_MATCHES_ONLY_NOT_VERIFIED_COMPLETE",
            "parser_version": PARSER_VERSION}


def extract_earnings_exhibit(raw: bytes, document: dict, *, limit: int = 8000) -> dict:
    """只提取已由限定索引识别的业绩附件；截断保留，不以文本执行指令。"""
    if (type(limit) is not int or limit <= 0 or limit > 8000 or not document.get("attachment_selection")
            or document["form"] not in ("8-K", "8-K/A")):
        raise ValueError("SEC_EARNINGS_EXHIBIT_SELECTION_REQUIRED")
    if hashlib.sha256(raw).hexdigest() != document["raw_content_hash"] or len(raw) > 32 * 1024 * 1024:
        raise ValueError("SEC_DOCUMENT_HASH_OR_SIZE_INVALID")
    source = raw.decode("utf-8", errors="strict")
    parser = _Text(source)
    parser.feed(source)
    parser.close()
    text = "".join(parser.parts)
    if not text.strip():
        return {"evidence": [], "gap": "EARNINGS_EXHIBIT_TEXT_EMPTY"}
    stop = min(len(text), limit)
    fact = {key: document[key] for key in ("source_id", "source_locator", "as_of", "published_at",
        "retrieved_at", "raw_content_hash", "cik", "accession", "form")}
    fact.update(section="earnings_release", text=text[:stop],
        raw_character_spans=[[start, finish] for left, right, start, finish in parser.spans if left < stop and right > 0],
        normalized_text_range=[0, stop], locator_policy="raw-decoded-html-character-spans/end-exclusive",
        encoding="utf-8", parser_version=PARSER_VERSION, untrusted_data=True, truncated=stop < len(text),
        attachment_selection=document["attachment_selection"])
    fact["evidence_id"] = "ev-sec-text-" + content_hash(fact)
    return {"evidence": [fact], "gap": "EARNINGS_EXHIBIT_TEXT_TRUNCATED" if fact["truncated"] else None}
