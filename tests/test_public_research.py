from __future__ import annotations

from datetime import datetime, UTC
import json
from pathlib import Path
import tempfile
import unittest

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.public_research import (
    OpenAlexResearchClient, normalize_grobid_xml, normalize_search_results,
)
from product.mcp.live.sec_client import Response


NOW = datetime(2026, 9, 15, 2, 0, tzinfo=UTC)


def policy():
    return {
        "adapter_version": "openalex-public-research/1.0.0",
        "authentication": "optional_for_search_required_for_content",
        "domains": ["api.openalex.org", "content.openalex.org"],
        "search_endpoint": "https://api.openalex.org/works",
        "content_endpoint_template": "https://content.openalex.org/works/{work_id}.grobid-xml",
        "request_budget": {"searches_per_security": 1, "candidates_per_security": 2, "content_attempts_per_security": 1},
        "limitations": ["synthetic"],
    }


def search_body():
    return json.dumps({"results": [{
        "id": "https://openalex.org/W123", "title": "Silicon carbide market study",
        "publication_date": "2026-09-01", "doi": "https://doi.org/10.1/test",
        "authorships": [{"author": {"display_name": "Researcher"}}],
        "primary_location": {"source": {"display_name": "Journal"}},
        "content_urls": {"grobid_xml": "https://content.openalex.org/works/W123.grobid-xml"},
    }, {
        "id": "https://openalex.org/W124", "title": "Future paper",
        "publication_date": "2026-10-01", "authorships": [],
        "primary_location": None, "content_urls": {}, "doi": None,
    }]}).encode()


XML = b'''<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><div><head>Results</head><p>Observed technical result.</p></div></body></text></TEI>'''


class PublicResearchTests(unittest.TestCase):
    def test_search_lead_is_not_body_and_future_is_excluded(self):
        value = normalize_search_results(
            search_body(), query="Wolfspeed silicon carbide", security_id="US:COMMON_STOCK:WOLF",
            retrieved_at="2026-09-15T02:00:00Z", decision_cutoff="2026-09-15T02:00:00Z",
            max_candidates=2,
        )
        self.assertEqual(value["candidates"][0]["verification_status"], "LEAD_ONLY")
        self.assertEqual(value["candidates"][0]["material_type"], "SEARCH_LEAD")
        self.assertEqual(value["excluded"][0]["exclusion_reason"], "FUTURE_PUBLICATION")

    def test_grobid_body_has_hash_location_and_untrusted_marker(self):
        candidate = normalize_search_results(
            search_body(), query="q", security_id="US:COMMON_STOCK:WOLF",
            retrieved_at="2026-09-15T02:00:00Z", decision_cutoff="2026-09-15T02:00:00Z",
            max_candidates=2,
        )["candidates"][0]
        document = normalize_grobid_xml(XML, candidate=candidate, retrieved_at="2026-09-15T02:01:00Z")
        self.assertEqual(document["verification_status"], "BODY_VERIFIED")
        self.assertEqual(document["locations"], ["Results"])
        self.assertTrue(document["untrusted_content"])

    def test_client_enforces_budget_scope_and_external_key(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def transport(request, **kwargs):
                calls.append((request.full_url, kwargs))
                return Response(200, search_body() if "api.openalex" in request.full_url else XML)
            client = OpenAlexResearchClient(
                policy(), SnapshotCache(Path(temp)), now=lambda: NOW, transport=transport,
            )
            result = client.search(query="Wolfspeed silicon carbide", security_id="US:COMMON_STOCK:WOLF", decision_cutoff="2026-09-15T02:00:00Z")
            with self.assertRaisesRegex(ValueError, "BUDGET"):
                client.search(query="again", security_id="US:COMMON_STOCK:WOLF", decision_cutoff="2026-09-15T02:00:00Z")
            with self.assertRaisesRegex(ValueError, "API_KEY_REQUIRED"):
                client.fetch(result["candidates"][0])
            keyed = OpenAlexResearchClient(
                policy(), SnapshotCache(Path(temp)), api_key="secret-not-persisted",
                now=lambda: NOW, transport=transport,
            )
            document = keyed.fetch(result["candidates"][0])
            self.assertEqual(document["verification_status"], "BODY_VERIFIED")
            self.assertNotIn("secret-not-persisted", json.dumps(keyed.events) + json.dumps(document))
            self.assertIn("api_key=secret-not-persisted", calls[-1][0])


if __name__ == "__main__":
    unittest.main()
