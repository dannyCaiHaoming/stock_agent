"""采集/缓存接缝仅使用 fake transport 和独立临时目录。"""
from datetime import datetime, UTC, timedelta
from pathlib import Path
import tempfile
import unittest
import json

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.sec_client import FetchError, Response, SecClient, validate_sec_url

URL = "https://data.sec.gov/submissions/CIK0000000001.json"
SECOND = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"


class SecClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = SnapshotCache(Path(self.temp.name))
        self.now = datetime(2026, 9, 10, tzinfo=UTC)
        self.elapsed = 0
        self.calls = []

    def client(self, responses, budget=20):
        iterator = iter(responses)

        def transport(url, user_agent):
            self.calls.append((url, user_agent))
            result = next(iterator)
            if isinstance(result, Exception):
                raise result
            return result

        def sleep(seconds):
            self.elapsed += seconds

        return SecClient(self.cache, user_agent="synthetic-test contact@example.invalid",
                         transport=transport, now=lambda: self.now,
                         monotonic=lambda: self.elapsed, sleep=sleep, request_budget=budget)

    def test_cache_hit_preserves_timestamp_and_refresh_appends(self):
        client = self.client([Response(200, b"one"), Response(200, b"one"), Response(200, b"two")])
        first = client.fetch(URL, max_age_seconds=100)
        self.now += timedelta(seconds=5)
        self.assertEqual(first, client.fetch(URL, max_age_seconds=100))
        self.assertEqual(client.requests, 1)
        self.assertEqual(first, client.fetch(URL, max_age_seconds=100, refresh=True))
        second = client.fetch(URL, max_age_seconds=100, refresh=True)
        self.assertNotEqual(first["record_hash"], second["record_hash"])
        self.assertEqual(self.cache.read(first), b"one")
        self.assertEqual(self.cache.read(second), b"two")
        self.assertNotIn("contact@example.invalid", str(client.events))
        for path in Path(self.temp.name).rglob("*"):
            if path.is_file():
                self.assertNotIn(b"contact@example.invalid", path.read_bytes())

    def test_permission_errors_no_retry(self):
        for status in (401, 403, 302):
            with self.subTest(status=status):
                client = self.client([Response(status, b"private")])
                with self.assertRaisesRegex(FetchError, f"SEC_HTTP_{status}"):
                    client.fetch(URL, max_age_seconds=0)
                self.assertEqual(client.requests, 1)

    def test_ticker_map_read_through_verified_cache(self):
        raw = json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                          "data": [[1, "Synthetic", "TEST", "Nasdaq"]]}).encode()
        client = self.client([Response(200, raw)])
        first = client.read_ticker_map(max_age_seconds=100)
        self.now += timedelta(seconds=5)
        second = client.read_ticker_map(max_age_seconds=100)
        self.assertEqual(first, second)
        self.assertEqual(client.requests, 1)
        self.assertEqual(first["mapping"][0]["cik"], "0000000001")
        self.assertEqual(first["mapping"][0]["raw_content_hash"], first["record"]["raw_content_hash"])

    def test_rate_limit_and_timeout_are_bounded(self):
        client = self.client([Response(429, b"", "3"), TimeoutError(), Response(200, b"ok")])
        client.fetch(URL, max_age_seconds=0)
        self.assertEqual(client.requests, 3)
        self.assertGreaterEqual(self.elapsed, 5)
        client = self.client([TimeoutError()] * 3)
        with self.assertRaisesRegex(FetchError, "SEC_TIMEOUT"):
            client.fetch(SECOND, max_age_seconds=0)
        self.assertEqual(client.requests, 3)

    def test_retry_after_not_truncated_or_guessed(self):
        for retry in ("999", "nan", "-1", "nonsense"):
            client = self.client([Response(429, b"", retry)])
            with self.subTest(retry=retry), self.assertRaisesRegex(FetchError, "SEC_RETRY_AFTER"):
                client.fetch(URL, max_age_seconds=0)
            self.assertEqual(client.requests, 1)

    def test_budget_and_partial_failure(self):
        client = self.client([Response(200, b"ok")], budget=1)
        result = client.fetch_many([URL, URL, SECOND], max_age_seconds=100, refresh=True)
        self.assertEqual(result["actual_requests"], 1)
        self.assertIn(URL, result["results"])
        self.assertEqual(result["failures"][SECOND], "SEC_BUDGET_EXHAUSTED")

    def test_request_spacing_and_stale_cache(self):
        client = self.client([Response(200, b"old"), Response(200, b"new")])
        first = client.fetch(URL, max_age_seconds=1)
        self.now += timedelta(seconds=2)
        second = client.fetch(URL, max_age_seconds=1)
        self.assertNotEqual(first["record_hash"], second["record_hash"])
        self.assertGreaterEqual(self.elapsed, 0.5)

    def test_stable_archive_document_ignores_ttl_and_recovers_missing_object(self):
        filing = {
            "cik": "0000000001",
            "accession": "0000000001-26-000001",
            "form": "10-K",
            "published_at": "2026-02-01T00:00:00Z",
            "published_at_policy": "submission_acceptance_datetime",
            "document_url": (
                "https://www.sec.gov/Archives/edgar/data/1/"
                "000000000126000001/report.htm"
            ),
        }
        raw = b"<html>stable filing</html>"
        client = self.client([Response(200, raw), Response(200, raw)])
        first = client.read_document(filing, max_age_seconds=1)
        self.now += timedelta(days=2)
        second = client.read_document(filing, max_age_seconds=1)
        self.assertEqual(first["raw_content_hash"], second["raw_content_hash"])
        self.assertEqual(1, client.requests)
        self.assertEqual("stable_cache_hit", client.events[-1]["status"])

        object_path = Path(self.temp.name) / "objects" / first["raw_content_hash"]
        object_path.unlink()
        recovered = client.read_document(filing, max_age_seconds=1)
        self.assertEqual(2, client.requests)
        self.assertEqual(raw, self.cache.read(recovered["cache_record"]))
        self.assertEqual(
            "VERIFIED_PROVIDER_REFETCH", client.events[-1]["cache_recovery"],
        )

    def test_stable_archive_document_recovers_corrupt_object_and_fails_closed_if_refetch_fails(self):
        filing = {
            "cik": "0000000001",
            "accession": "0000000001-26-000001",
            "form": "10-K",
            "published_at": "2026-02-01T00:00:00Z",
            "published_at_policy": "submission_acceptance_datetime",
            "document_url": (
                "https://www.sec.gov/Archives/edgar/data/1/"
                "000000000126000001/report.htm"
            ),
        }
        raw = b"<html>stable filing</html>"
        client = self.client([Response(200, raw), Response(200, raw)])
        first = client.read_document(filing, max_age_seconds=1)
        object_path = Path(self.temp.name) / "objects" / first["raw_content_hash"]
        object_path.write_bytes(b"tampered")

        recovered = client.read_document(filing, max_age_seconds=1)
        self.assertEqual(raw, self.cache.read(recovered["cache_record"]))
        self.assertEqual(
            "VERIFIED_PROVIDER_REFETCH", client.events[-1]["cache_recovery"],
        )
        self.assertEqual("CACHE_OBJECT_HASH_MISMATCH", client.events[-1]["cache_failure_code"])

        object_path.write_bytes(b"tampered-again")
        failing = self.client([Response(503, b"")] * 3)
        with self.assertRaisesRegex(FetchError, "SEC_HTTP_503"):
            failing.read_document(filing, max_age_seconds=1)
        self.assertEqual(3, failing.requests)
        self.assertFalse(any(event.get("status") == "stable_cache_hit" for event in failing.events))
        self.assertEqual(b"tampered-again", object_path.read_bytes())

    def test_endpoint_restriction(self):
        for url in (URL + "?quantity=100", URL.replace("https", "http"),
                    "https://data.sec.gov.evil.test/submissions/CIK0000000001.json",
                    "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/../secret",
                    "https://user@data.sec.gov/submissions/CIK0000000001.json"):
            with self.subTest(url=url), self.assertRaises(FetchError):
                validate_sec_url(url)
        client = self.client([])
        with self.assertRaises(FetchError):
            client.fetch_many([URL, "holding question"], max_age_seconds=100)
        self.assertEqual(self.calls, [])

    def test_sec_xsl_archive_document_is_allowed_without_broadening_archive_scope(self):
        prefix = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/"
        for document in (
            "xslF345X06/form4.xml",
            "xsl144X01/primary_doc.xml",
            "xslN-PX_X01/primary_doc.xml",
            "xslSCHEDULE_13G_X02/primary_doc.xml",
        ):
            with self.subTest(document=document):
                self.assertEqual(prefix + document, validate_sec_url(prefix + document))

        for document in (
            "other/form4.xml",
            "xslF345X06/sub/form4.xml",
            "xslF345X06/../secret",
            "xslF345X06/%2e%2e",
            "xslF345X06%2fform4.xml",
            "xslF345X06\\form4.xml",
            "xslF345X06//form4.xml",
            "xslF345X06/form4.xml?download=1",
            "xslF345X06/form4.xml#fragment",
        ):
            with self.subTest(document=document), self.assertRaisesRegex(
                FetchError, "SEC_ENDPOINT_REJECTED"
            ):
                validate_sec_url(prefix + document)

    def test_sec_xsl_document_reaches_transport_and_cache(self):
        url = (
            "https://www.sec.gov/Archives/edgar/data/1/"
            "000000000126000001/xslF345X06/form4.xml"
        )
        client = self.client([Response(200, b"<ownershipDocument/>")])
        record = client.fetch(url, max_age_seconds=0)
        self.assertEqual(self.calls[0][0], url)
        self.assertEqual(self.cache.read(record), b"<ownershipDocument/>")

    def test_ownership_reader_fetches_raw_xml_sibling_and_preserves_submission_url(self):
        prefix = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/"
        submitted_url = prefix + "xslF345X06/form4.xml"
        raw_url = prefix + "form4.xml"
        filing = {
            "cik": "0000000001",
            "accession": "0000000001-26-000001",
            "form": "4",
            "published_at": "2026-09-09T00:00:00Z",
            "document_url": submitted_url,
        }
        client = self.client([Response(200, b"<ownershipDocument/>")])
        result = client.read_ownership_document(filing, max_age_seconds=0)
        self.assertEqual(self.calls[0][0], raw_url)
        self.assertEqual(result["raw_document_url"], raw_url)
        self.assertEqual(result["submission_document_url"], submitted_url)
        self.assertEqual(result["filing"]["document_url"], raw_url)
        self.assertEqual(
            result["filing"]["document_resolution_version"],
            "sec-ownership-document-resolution/1.0.0",
        )

    def test_ownership_reader_rejects_wrong_accession_binding_before_transport(self):
        filing = {
            "cik": "0000000001",
            "accession": "0000000001-26-000001",
            "form": "4",
            "published_at": "2026-09-09T00:00:00Z",
            "document_url": (
                "https://www.sec.gov/Archives/edgar/data/1/"
                "000000000126000002/xslF345X06/form4.xml"
            ),
        }
        client = self.client([])
        with self.assertRaisesRegex(FetchError, "SEC_DOCUMENT_BINDING_MISMATCH"):
            client.read_ownership_document(filing, max_age_seconds=0)
        self.assertEqual(self.calls, [])

    def test_13f_reader_discovers_and_fetches_only_bound_information_table(self):
        prefix = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/"
        index = b'''<html><table>
          <tr><td><a href="cover.xml">cover.xml</a></td><td>13F-HR</td></tr>
          <tr><td><a href="infotable.xml">infotable.xml</a></td><td>INFORMATION TABLE</td></tr>
        </table></html>'''
        table = b"<informationTable/>"
        filing = {
            "cik": "0000000001", "accession": "0000000001-26-000001",
            "form": "13F-HR", "published_at": "2026-09-09T00:00:00Z",
            "document_url": prefix + "cover.xml",
        }
        client = self.client([Response(200, index), Response(200, table)])
        result = client.read_13f_information_tables(filing, max_age_seconds=0)
        self.assertEqual(self.calls[0][0], prefix + "0000000001-26-000001-index.html")
        self.assertEqual(self.calls[1][0], prefix + "infotable.xml")
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(self.cache.read(result["documents"][0]["record"]), table)

    def test_cache_corruption_fail_closed(self):
        client = self.client([Response(200, b"ok")])
        record = client.fetch(URL, max_age_seconds=100)
        path = Path(self.temp.name) / "objects" / record["raw_content_hash"]
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "CACHE_OBJECT_HASH_MISMATCH"):
            client.fetch(URL, max_age_seconds=100)
        self.assertEqual(client.requests, 1)

    def test_repo_cache_rejected(self):
        with self.assertRaisesRegex(ValueError, "LIVE_CACHE_MUST_BE_EXTERNAL"):
            SnapshotCache(Path(__file__).resolve().parents[1] / "private-cache")

    def test_history_page_raw_provenance_and_budget(self):
        name = "CIK0000000001-submissions-001.json"
        body = {"cik": 1, "filings": {"files": [{"name": name}, {"name": name}]}}
        page = {"accessionNumber": ["0000000001-25-000001"], "form": ["10-K"],
                "acceptanceDateTime": ["2025-08-01T00:00:00Z"],
                "reportDate": ["2025-06-30"], "primaryDocument": ["old.htm"]}
        raw = json.dumps(page).encode()
        client = self.client([Response(200, json.dumps(body).encode()), Response(200, raw)])
        record = client.submissions("1", max_age_seconds=100)
        omitted = client.read_history(record, cik="1", max_pages=0, max_age_seconds=100)
        self.assertTrue(omitted["truncated"])
        self.assertEqual(client.requests, 1)
        result = client.read_history(record, cik="1", max_pages=1, max_age_seconds=100)
        filing = result["filings"]["0000000001-25-000001"]
        self.assertTrue(filing["source_locator"].endswith(name))
        self.assertEqual(filing["raw_content_hash"], result["records"][0]["raw_content_hash"])
        self.assertFalse(result["truncated"])
        self.assertEqual(client.requests, 2)

    def test_history_wrong_issuer_name_rejected_before_request(self):
        body = {"cik": 1, "filings": {"files": [{"name": "CIK0000000002-submissions-001.json"}]}}
        client = self.client([Response(200, json.dumps(body).encode())])
        record = client.submissions("1", max_age_seconds=100)
        with self.assertRaisesRegex(FetchError, "SEC_PAGE_NAME_INVALID"):
            client.read_history(record, cik="1", max_pages=1, max_age_seconds=100)
        self.assertEqual(client.requests, 1)

    def test_history_missing_document_record_survives_client(self):
        name = "CIK0000000001-submissions-001.json"
        body = {"cik": 1, "filings": {"files": [{"name": name}]}}
        page = {"accessionNumber": ["0000000001-25-000001"], "form": ["10-K"],
                "acceptanceDateTime": ["2025-08-01T00:00:00Z"],
                "reportDate": ["2025-06-30"], "primaryDocument": [""]}
        client = self.client([Response(200, json.dumps(body).encode()), Response(200, json.dumps(page).encode())])
        record = client.submissions("1", max_age_seconds=100)
        result = client.read_history(record, cik="1", max_pages=1, max_age_seconds=100)
        self.assertEqual(result["filings"], {})
        self.assertEqual(result["excluded"][0]["raw_content_hash"], result["records"][0]["raw_content_hash"])
        self.assertEqual(result["excluded"][0]["reason"], "SEC_HISTORY_DOCUMENT_MISSING")
        self.assertEqual(client.requests, 2)

    def test_fetch_parse_document_chain(self):
        accession = "0000000001-26-000001"
        submissions = {"cik": 1, "filings": {"recent": {
            "accessionNumber": [accession], "form": ["10-Q"],
            "acceptanceDateTime": ["2026-08-01T12:00:00Z"],
            "primaryDocument": ["report.htm"], "reportDate": ["2026-06-30"]}}}
        facts = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"accn": accession, "form": "10-Q", "val": 10,
             "start": "2026-01-01", "end": "2026-06-30"}]}}}}}
        client = self.client([Response(200, json.dumps(submissions).encode()),
                              Response(200, json.dumps(facts).encode()),
                              Response(200, b"<html>synthetic disclosure</html>")])
        result = client.read_company("1", security_id="TEST", max_age_seconds=60)
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["coverage"], "RECENT_SUBMISSIONS_ONLY")
        filing = result["filings"][accession]
        document = client.read_document(filing, max_age_seconds=60)
        self.assertEqual(document["published_at"], filing["published_at"])
        self.assertEqual(client.requests, 3)
        self.assertIn(b"synthetic disclosure", self.cache.read(document["cache_record"]))
        with self.assertRaisesRegex(FetchError, "SEC_DOCUMENT_BINDING_MISMATCH"):
            client.read_document(dict(filing, cik="2"), max_age_seconds=60)
        self.assertEqual(client.requests, 3)

    def test_selected_disclosures_include_bound_earnings_attachment(self):
        prefix = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001"
        annual = {"accession": "0000000001-26-000001", "cik": "0000000001", "form": "10-K",
                  "document_url": f"{prefix}/annual.htm", "report_date": "2025-12-31",
                  "published_at": "2026-02-01T00:00:00Z", "retrieved_at": "2026-09-01T00:00:00Z",
                  "published_at_policy": "submission_acceptance_datetime"}
        event_prefix = "https://www.sec.gov/Archives/edgar/data/1/000000000126000002"
        event = dict(annual, accession="0000000001-26-000002", form="8-K", report_date="2026-08-01",
                     document_url=f"{event_prefix}/event.htm", published_at="2026-08-01T00:00:00Z")
        index = b'<table><tr><td>2</td><td>Earnings release</td><td><a href="earnings.htm">earnings.htm</a></td><td>EX-99.1</td><td>10</td></tr></table>'
        client = self.client([Response(200, b"<h2>Item 1. Business</h2><p>Synthetic products</p>"),
                              Response(200, b"<p>Item 2.02 Results</p>"), Response(200, index),
                              Response(200, b"<p>Synthetic earnings</p>")])
        result = client.read_selected_disclosures({p["accession"]: p for p in (annual, event)},
                    selection_as_of="2026-09-10T00:00:00Z", max_age_seconds=100)
        self.assertEqual(client.requests, 4)
        self.assertIn("Synthetic products", result["documents"][0]["sections"]["evidence"][0]["text"])
        attachment = result["documents"][1]["attachments"]["documents"][0]
        self.assertEqual(attachment["source_locator"], f"{event_prefix}/earnings.htm")
        self.assertEqual(attachment["accession"], event["accession"])
        self.assertEqual(attachment["attachment_selection"]["index_raw_hash"],
                         result["documents"][1]["attachments"]["index"]["raw_content_hash"])
if __name__ == "__main__":
    unittest.main()
