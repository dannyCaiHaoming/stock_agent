from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from product.mcp.live.moomoo_public_news import fetch_news_search
from product.mcp.live.research_supplement_collection import capture_public_company_news_result
from product.mcp.live.sec_client import Response


NOW = datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc)
PUBLISHED = int(datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc).timestamp())


class MoomooPublicNewsTests(unittest.TestCase):
    def fetch(self, payload, *, status=200, cutoff=None):
        requests = []

        def transport(request):
            requests.append(request)
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            return Response(status, body)

        with tempfile.TemporaryDirectory() as temp:
            result = fetch_news_search(
                keyword="MRVL", news_type=3, cache_root=Path(temp),
                decision_cutoff=cutoff, transport=transport, now=lambda: NOW,
            )
            self.assertEqual(len(list((Path(temp) / "records").iterdir())), 1)
        return result, requests

    def test_metadata_only_deduplicated_and_frozen(self):
        url = "https://www.moomoo.com/news/post/42"
        result, requests = self.fetch({"code": 0, "data": [
            {"news_id": "42", "news_type": 3, "title": "<em>Marvell</em> rated Buy",
             "publish_time": str(PUBLISHED), "url": url + "?src=39"},
            {"news_id": "42", "news_type": 3, "title": "Marvell rated Buy",
             "publish_time": str(PUBLISHED), "url": url + "?utm_source=moomoo"},
        ]})
        self.assertEqual(len(requests), 1)
        self.assertIn("news_type=3", requests[0].full_url)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["title"], "Marvell rated Buy")
        self.assertEqual(result["candidates"][0]["canonical_url"], url)
        self.assertEqual(result["excluded"], [{"reason": "DUPLICATE"}])
        self.assertEqual(result["provider"], "moomoo_public_news")
        self.assertEqual(len(result["raw_content_hash"]), 64)

    def test_empty_future_and_historical_cutoff_stay_empty(self):
        empty, _ = self.fetch({"code": 0, "data": []})
        self.assertEqual(empty["candidates"], [])
        future, _ = self.fetch({"code": 0, "data": [
            {"news_id": "1", "news_type": 3, "title": "MRVL future",
             "publish_time": str(int(NOW.timestamp()) + 60),
             "url": "https://www.moomoo.com/news/post/1"},
        ]})
        self.assertEqual(future["candidates"], [])
        self.assertEqual(future["excluded"][0]["reason"], "FUTURE_OR_UNAVAILABLE_AT_CUTOFF")
        old, _ = self.fetch({"code": 0, "data": [
            {"news_id": "2", "news_type": 3, "title": "MRVL rating",
             "publish_time": str(PUBLISHED),
             "url": "https://www.moomoo.com/news/post/2"},
        ]}, cutoff="2026-09-25T00:00:00Z")
        self.assertEqual(old["candidates"], [])

    def test_failure_codes_do_not_expose_provider_body(self):
        for payload, status, expected in (
            (b"private provider error", 403, "MOOMOO_PUBLIC_NEWS_HTTP_403"),
            (b"not-json", 200, "MOOMOO_PUBLIC_NEWS_RESPONSE_INVALID"),
            ({"code": 9, "message": "token=private", "data": []}, 200,
             "MOOMOO_PUBLIC_NEWS_RESPONSE_INVALID"),
        ):
            with self.subTest(expected=expected), self.assertRaises(ValueError) as caught:
                self.fetch(payload, status=status)
            self.assertEqual(str(caught.exception), expected)

    def test_company_leads_exclude_marvelous_and_etf_without_claiming_body(self):
        def transport(request):
            news_type = 3 if "news_type=3" in request.full_url else 2
            rows = [
                {"news_id": "rating", "news_type": news_type,
                 "title": "MRVL analyst raises rating" if news_type == 3 else "Marvell Technology earnings announcement",
                 "publish_time": str(PUBLISHED), "url": f"https://www.moomoo.com/news/post/{news_type}"},
                {"news_id": "wrong", "news_type": news_type,
                 "title": "Marvelous Entertainment announces game",
                 "publish_time": str(PUBLISHED), "url": f"https://www.moomoo.com/news/post/wrong-{news_type}"},
                {"news_id": "etf", "news_type": news_type,
                 "title": "MRVL leveraged ETF rises",
                 "publish_time": str(PUBLISHED), "url": f"https://www.moomoo.com/news/post/etf-{news_type}"},
            ]
            return Response(200, json.dumps({"code": 0, "data": rows}).encode())

        with tempfile.TemporaryDirectory() as temp:
            result = capture_public_company_news_result(
                security_id="US:COMMON_STOCK:MRVL", ticker="MRVL",
                issuer_name="Marvell Technology Inc.", cache_root=Path(temp),
                transport=transport, now=lambda: NOW,
            )
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIn("MOOMOO_PUBLIC_NEWS_ISSUER_UNVERIFIED", result["gaps"])
        self.assertIn("MOOMOO_PUBLIC_NEWS_NON_ISSUER_INSTRUMENT", result["gaps"])
        for fact in result["evidence"]:
            self.assertEqual(fact["value"]["content_tier"], "LEAD_ONLY")
            self.assertFalse(fact["value"]["body_verified"])
            self.assertEqual(fact["source_family"], "moomoo_public_news")
        self.assertEqual(
            {fact["value"]["lead_kind"] for fact in result["evidence"]},
            {"NOTICE_INDEX", "RATING_OR_RESEARCH_NEWS"},
        )

    def test_company_missing_body_does_not_turn_empty_search_into_evidence(self):
        def transport(_request):
            return Response(200, b'{"code":0,"data":[]}')

        with tempfile.TemporaryDirectory() as temp:
            result = capture_public_company_news_result(
                security_id="US:COMMON_STOCK:MRVL", ticker="MRVL",
                issuer_name="Marvell Technology Inc.", cache_root=Path(temp),
                transport=transport, now=lambda: NOW,
            )
        self.assertEqual(result["status"], "SOURCE_LIMITED")
        self.assertEqual(result["evidence"], [])


if __name__ == "__main__":
    unittest.main()
