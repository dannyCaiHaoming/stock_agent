from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from product.mcp.live.moomoo_public_news import fetch_news_search
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

if __name__ == "__main__":
    unittest.main()
