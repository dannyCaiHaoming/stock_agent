import hashlib
import unittest

from product.mcp.live.attachments import earnings_attachments
from product.mcp.live.filing_selection import select_filings


class FilingSelectionTests(unittest.TestCase):
    def filing(self, number, form, published, period="2026-06-30"):
        accession = f"0000000001-26-{number:06d}"
        return {"accession": accession, "form": form, "cik": "0000000001", "report_date": period,
                "published_at": published, "retrieved_at": "2026-09-01T00:00:00Z"}

    def test_select_annual_newer_quarter_and_three_events(self):
        rows = [self.filing(1, "10-K", "2026-02-01T00:00:00Z", "2025-12-31"),
                self.filing(2, "10-Q", "2026-08-01T00:00:00Z"),
                self.filing(3, "10-K/A", "2026-08-02T00:00:00Z", "2025-12-31")]
        rows += [self.filing(10 + i, "8-K", f"2026-08-{10+i:02d}T00:00:00Z") for i in range(4)]
        rows.append(self.filing(20, "10-Q", "2026-12-01T00:00:00Z"))
        result = select_filings({r["accession"]: r for r in rows}, selection_as_of="2026-09-10T00:00:00Z")
        self.assertEqual(len(result["selected"]), 6)
        self.assertEqual(len(result["omitted_event_accessions"]), 1)
        self.assertEqual(len(result["excluded"]), 1)
        self.assertEqual(result["selected"][0]["form"], "10-K")

    def test_event_budget_preserves_core_filings_and_marks_omissions(self):
        rows = [
            self.filing(1, "10-K", "2026-02-01T00:00:00Z", "2025-12-31"),
            self.filing(2, "10-Q", "2026-08-01T00:00:00Z"),
            *[self.filing(10 + i, "8-K", f"2026-08-{10+i:02d}T00:00:00Z") for i in range(3)],
        ]
        result = select_filings(
            {row["accession"]: row for row in rows},
            selection_as_of="2026-09-10T00:00:00Z", event_limit=1,
        )
        self.assertEqual([row["form"] for row in result["selected"]], ["10-K", "10-Q", "8-K"])
        self.assertEqual(len(result["omitted_event_accessions"]), 2)
        for invalid in (-1, 4, True):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "SELECTION_BUDGET"):
                select_filings({}, selection_as_of="2026-09-10T00:00:00Z", event_limit=invalid)

    def test_empty_and_cross_issuer(self):
        self.assertIn("ANNUAL_DISCLOSURE_MISSING", select_filings({}, selection_as_of="2026-09-10T00:00:00Z")["gaps"])
        first = self.filing(1, "10-K", "2026-02-01T00:00:00Z")
        other = dict(self.filing(2, "10-K", "2026-03-01T00:00:00Z"), cik="0000000002")
        with self.assertRaises(ValueError):
            select_filings({r["accession"]: r for r in (first, other)}, selection_as_of="2026-09-10T00:00:00Z")

    def index(self, href="earnings.htm", description="Earnings release", limit=3):
        raw = f'<table><tr><td>2</td><td>{description}</td><td><a href="{href}">earnings.htm</a></td><td>EX-99.1</td><td>1000</td></tr></table>'.encode()
        metadata = {"source_locator": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/0000000001-26-000001-index.html",
                    "source_id": "synthetic", "raw_content_hash": hashlib.sha256(raw).hexdigest(),
                    "retrieved_at": "2026-09-10T00:00:00Z"}
        return earnings_attachments(raw, metadata, limit=limit)

    def test_attachment_provenance_and_budget(self):
        result = self.index()
        self.assertEqual(len(result["selected"]), 1)
        self.assertEqual(result["selected"][0]["exhibit_type"], "EX-99.1")
        self.assertEqual(len(self.index(limit=0)["omitted"]), 1)

    def test_external_or_other_accession_rejected(self):
        for href in ("https://example.invalid/earnings.htm", "../other/earnings.htm", "earnings.htm?secret=1"):
            with self.subTest(href=href), self.assertRaises(ValueError):
                self.index(href=href)

    def test_unverified_purpose_is_gap(self):
        result = self.index(description="Exhibit")
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["rejected"][0]["reason"], "EXHIBIT_PURPOSE_NOT_VERIFIED")
