"""合成 SEC 响应测试：不联网、不包含真实持仓或联系身份。"""
import copy
import hashlib
import json
import unittest

from product.mcp.live.sec import normalize_cik, parse_companyfacts, parse_submissions, parse_submission_page


class SecParserTests(unittest.TestCase):
    def setUp(self):
        self.accession = "0000000001-26-000001"
        self.retrieved = "2026-08-01T12:00:00Z"
        self.submissions = {"cik": 1, "filings": {"recent": {
            "accessionNumber": [self.accession],
            "acceptanceDateTime": ["2026-07-30T16:30:00-04:00"],
            "form": ["10-Q"], "primaryDocument": ["example.htm"],
            "reportDate": ["2026-06-30"],
        }}}
        self.row = {"accn": self.accession, "form": "10-Q", "start": "2026-01-01",
                    "end": "2026-06-30", "val": 123, "fy": 2026, "fp": "Q2"}

    def filings(self):
        return parse_submissions(json.dumps(self.submissions).encode(), cik="1", retrieved_at=self.retrieved)

    def facts(self, rows=None, units=None):
        body = {"cik": 1, "facts": {"us-gaap": {"Revenues": {
            "units": units if units is not None else {"USD": rows if rows is not None else [self.row]}
        }}}}
        return parse_companyfacts(json.dumps(body).encode(), cik="1", security_id="TEST",
                                  retrieved_at=self.retrieved, filings=self.filings())

    def test_cik_validation(self):
        self.assertEqual(normalize_cik(1), "0000000001")
        for value in (True, 0, "../1", "1.0", "12345678901"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_cik(value)

    def test_publication_and_provenance(self):
        fact = self.facts()["evidence"][0]
        self.assertEqual(fact["published_at"], "2026-07-30T20:30:00Z")
        self.assertEqual(fact["period_end"], "2026-06-30")
        for field in ("source_id", "as_of", "retrieved_at", "raw_content_hash", "publication_source_hash"):
            self.assertTrue(fact[field])
        self.assertEqual(self.facts(), self.facts())

    def test_ytd_and_quarter_not_conflated(self):
        quarter = dict(self.row, start="2026-04-01")
        rows = self.facts([self.row, quarter])["evidence"]
        self.assertNotEqual(rows[0]["period_start"], rows[1]["period_start"])
        self.assertNotEqual(rows[0]["evidence_id"], rows[1]["evidence_id"])

    def test_units_separate_and_missing_not_zero(self):
        rows = self.facts(units={"USD": [self.row], "EUR": [self.row]})["evidence"]
        self.assertEqual({row["unit"] for row in rows}, {"USD", "EUR"})
        self.assertEqual(self.facts([])["evidence"], [])

    def test_unverified_accession_excluded(self):
        result = self.facts([dict(self.row, accn="0000000001-26-000002")])
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["excluded"][0]["reason"], "SEC_PUBLICATION_NOT_VERIFIED")

    def test_bad_numeric_period_and_binding_rejected(self):
        for changes in ({"val": "NaN"}, {"val": True}, {"val": float("inf")},
                        {"start": "2026-07-01"}, {"form": "10-K"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.facts([dict(self.row, **changes)])

    def test_submissions_malformed_rejected(self):
        original = copy.deepcopy(self.submissions)
        for field, value in (("primaryDocument", ["../secret"]), ("reportDate", []),
                             ("acceptanceDateTime", ["2026-07-30"]),
                             ("acceptanceDateTime", ["2026-08-02T00:00:00Z"]),
                             ("accessionNumber", ["bad"])):
            self.submissions = copy.deepcopy(original)
            self.submissions["filings"]["recent"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.filings()

    def test_revision_retained(self):
        recent = self.submissions["filings"]["recent"]
        for values in recent.values():
            values.append(values[0])
        recent["accessionNumber"][1] = "0000000001-26-000002"
        recent["form"][1] = "10-Q/A"
        rows = self.facts([self.row, dict(self.row, accn=recent["accessionNumber"][1], form="10-Q/A", val=124)])["evidence"]
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["accession"], rows[1]["accession"])

    def test_sec_xsl_document_path_preserved(self):
        recent = self.submissions["filings"]["recent"]
        recent["form"] = ["4"]
        for document in ("xslF345X06/form4.xml", "xsl144X01/primary_doc.xml",
                         "xslN-PX_X01/primary_doc.xml",
                         "xslSCHEDULE_13G_X02/primary_doc.xml"):
            with self.subTest(document=document):
                recent["primaryDocument"] = [document]
                filing = self.filings()[self.accession]
                self.assertEqual(filing["document_url"],
                                 "https://www.sec.gov/Archives/edgar/data/1/"
                                 + self.accession.replace("-", "") + "/" + document)
                self.assertEqual(filing["form"], "4")

    def test_sec_xsl_path_cannot_escape_accession(self):
        for document in ("../secret", "xslF345X06/../secret", "/form4.xml",
                         "//example.com/form4.xml", "https://example.com/form4.xml",
                         "xslF345X06/%2e%2e", "xslF345X06%2fform4.xml",
                         "xslF345X06\\form4.xml", "xslF345X06//form4.xml",
                         "xslF345X06/sub/form4.xml", "other/form4.xml",
                         "xslN-PX_X01/../secret", "xslN-PX_X01/%2e%2e", "xslN-PX_X01//primary_doc.xml",
                         "xslF345X06/form4.xml?redirect=x", ""):
            with self.subTest(document=document), self.assertRaisesRegex(
                ValueError, "SEC_DOCUMENT_INVALID"
            ):
                self.submissions["filings"]["recent"]["primaryDocument"] = [document]
                self.filings()

    def history(self, page, excluded):
        return parse_submission_page(json.dumps(page).encode(), cik="1",
            name="CIK0000000001-submissions-001.json", retrieved_at=self.retrieved, excluded=excluded)

    def test_history_missing_document_is_explicitly_isolated_with_raw_lineage(self):
        page = copy.deepcopy(self.submissions["filings"]["recent"])
        for values in page.values():
            values.append(values[0])
        page["accessionNumber"][1] = "0000000001-26-000002"
        page["primaryDocument"][1] = ""
        excluded = []
        filings = self.history(page, excluded)
        self.assertEqual(set(filings), {self.accession})
        self.assertEqual(len(excluded), 1)
        row = excluded[0]
        self.assertEqual(row["accession"], page["accessionNumber"][1])
        self.assertEqual(row["row_index"], 1)
        self.assertEqual(row["reason"], "SEC_HISTORY_DOCUMENT_MISSING")
        self.assertEqual(row["isolation_version"], "sec-history-isolation/1.0.0")
        self.assertEqual(row["raw_content_hash"], hashlib.sha256(json.dumps(page).encode()).hexdigest())
        self.assertNotIn("document_url", row)
        for field in ("source_id", "as_of", "retrieved_at", "source_locator"):
            self.assertTrue(row[field])
        body = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            self.row, dict(self.row, accn=row["accession"])]}}}}}
        facts = parse_companyfacts(json.dumps(body).encode(), cik="1", security_id="TEST",
            retrieved_at=self.retrieved, filings=filings)
        self.assertEqual(len(facts["evidence"]), 1)
        self.assertEqual(facts["excluded"][0]["reason"], "SEC_PUBLICATION_NOT_VERIFIED")

    def test_history_isolation_does_not_allow_invalid_paths(self):
        for document in ("../secret", " ", None, "/doc.htm", "xslF345X06/../doc", "https://evil.test/x"):
            page = copy.deepcopy(self.submissions["filings"]["recent"])
            page["primaryDocument"] = [document]
            with self.subTest(document=document), self.assertRaisesRegex(ValueError, "SEC_DOCUMENT_INVALID"):
                self.history(page, [])

    def test_history_missing_document_still_validates_metadata(self):
        for field, value in (("accessionNumber", "bad"), ("acceptanceDateTime", "2027-01-01T00:00:00Z"),
                             ("reportDate", "bad"), ("form", "")):
            page = copy.deepcopy(self.submissions["filings"]["recent"])
            page["primaryDocument"] = [""]
            page[field] = [value]
            excluded = []
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.history(page, excluded)
            self.assertEqual(excluded, [])

    def test_history_duplicate_including_isolated_row_rejected(self):
        for documents in (("", "example.htm"), ("example.htm", ""), ("", "")):
            page = copy.deepcopy(self.submissions["filings"]["recent"])
            for values in page.values():
                values.append(values[0])
            page["primaryDocument"] = list(documents)
            excluded = []
            with self.subTest(documents=documents), self.assertRaisesRegex(ValueError, "SEC_ACCESSION_DUPLICATE"):
                self.history(page, excluded)
            self.assertEqual(excluded, [])

    def test_history_missing_document_requires_explicit_exclusion_sink(self):
        page = copy.deepcopy(self.submissions["filings"]["recent"])
        page["primaryDocument"] = [""]
        with self.assertRaisesRegex(ValueError, "SEC_DOCUMENT_INVALID"):
            self.history(page, None)


if __name__ == "__main__":
    unittest.main()
