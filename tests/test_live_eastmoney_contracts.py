"""新版来源、真实 SDK 内存采集及追加缓存测试；无市场网络请求。"""
from copy import deepcopy
from datetime import datetime, UTC, timedelta
from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import validate_contract, validate_current_sources
from product.mcp.live.eastmoney_transport import EastmoneyClient, ADAPTER_VERSION, AKSHARE_VERSION
from product.mcp.live.sec import ADAPTER_VERSION as SEC_VERSION
from product.mcp.live.sec_client import CLIENT_VERSION
from product.mcp.provenance import content_hash
from tests.test_live_eastmoney_transport import response, payload
from tests import test_live_contracts_gate as legacy_examples

NOW = datetime(2026, 9, 10, tzinfo=UTC)


def access(provider="eastmoney"):
    return {"schema_version": "live-source-access/2.0.0", "provider": provider,
            "client_version": f"akshare/{AKSHARE_VERSION}" if provider == "eastmoney" else CLIENT_VERSION,
            "adapter_version": ADAPTER_VERSION if provider == "eastmoney" else SEC_VERSION,
            "status": "AUTHORIZED", "purpose": "personal-research", "terms_url": "synthetic-test-only",
            "checked_at": NOW.isoformat(), "free_features": ["synthetic"],
            "limitations": ["synthetic authorization: never use for real fetching"],
            "domains": ["63.push2his.eastmoney.com"] if provider == "eastmoney" else ["data.sec.gov", "www.sec.gov"],
            "request_budget": 3}


class EastmoneyContractTests(unittest.TestCase):
    def test_current_access_and_rejected_old_mixed_trial_drift(self):
        good = [access(), access("sec")]
        self.assertEqual(set(validate_current_sources(good)), {"eastmoney", "sec"})
        for changes in ({"provider": "yahoo"}, {"schema_version": "live-source-access/1.0.0"},
                        {"purpose": "TECHNICAL_TRIAL"}, {"eligible_for_council": False},
                        {"domains": ["*"]}, {"client_version": "akshare/unknown"}, {"status": "UNCONFIRMED"}):
            bad = deepcopy(good); bad[0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_current_sources(bad)

    def test_old_snapshot_unchanged_new_snapshot_cannot_hide_yahoo(self):
        setup = legacy_examples.LiveContractGateTests(); setup.setUp()
        historical = setup.snapshot()
        validate_contract("snapshot", historical)
        current = deepcopy(historical)
        current.update(schema_version="live-snapshot/2.0.0", source_access=[access(), access("sec")])
        def seal():
            current["snapshot_hash"] = content_hash({k:v for k,v in current.items() if k != "snapshot_hash"})
        seal()
        with self.assertRaisesRegex(ValueError, "MIXED_SOURCE"): validate_contract("snapshot", current)
        current["facts"][0].update(schema_version="live-fact/2.0.0", source_type="eastmoney")
        seal()
        validate_contract("snapshot", current)
        self.assertEqual(historical["facts"][0]["source_type"], "yahoo")
        bad = deepcopy(current["facts"][0]); bad["schema_version"] = "live-fact/9.0.0"
        with self.assertRaises(ValueError): validate_contract("fact", bad)

    def test_unauthorized_rejected_before_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            for state in ("UNCONFIRMED", "PAUSED"):
                with self.assertRaisesRegex(ValueError, "NOT_AUTHORIZED"):
                    EastmoneyClient(dict(access(), status=state), SnapshotCache(Path(temp)),
                                    transport=lambda *a, **k: self.fail("不能请求"), now=lambda: NOW)

    @unittest.skipUnless(find_spec("akshare"), "真实 SDK 在隔离 live 环境执行")
    def test_shared_budget_rate_distinct_cache_and_original_retrieval(self):
        calls, sleeps = [], []
        clock = [NOW]
        def transport(url, **kwargs):
            calls.append(kwargs)
            p = payload(); p["data"]["code"] = kwargs["params"]["secid"].split(".",1)[1]
            return response(p)
        with tempfile.TemporaryDirectory() as temp:
            cache = SnapshotCache(Path(temp))
            client = EastmoneyClient(access(), cache, transport=transport, now=lambda: clock[0],
                                     monotonic=lambda: 0, sleep=sleeps.append)
            args = dict(start="2026-09-08", end="2026-09-09")
            with patch("requests.sessions.Session.request", side_effect=AssertionError("NETWORK_FORBIDDEN")):
                record = client.fetch(symbol="105.MSFT", **args)
                clock[0] += timedelta(seconds=10)
                again = client.fetch(symbol="105.MSFT", **args)
                self.assertEqual(record, again)
                client.fetch(symbol="105.TEST", **args)
                self.assertEqual(client.requests, 2)
                self.assertEqual(sleeps, [1])
                self.assertIsNone(cache.lookup(dict(record["key"], provider="yahoo")))
                newer = client.fetch(symbol="105.MSFT", refresh=True, **args)
                self.assertEqual(newer["retrieved_at"], record["retrieved_at"])
                with self.assertRaisesRegex(ValueError, "BUDGET_EXHAUSTED"):
                    client.fetch(symbol="105.EXTRA", **args)
            self.assertEqual(len(calls), 3)
            self.assertNotIn("quantity", str(calls))

    @unittest.skipUnless(find_spec("akshare"), "真实 SDK 在隔离 live 环境执行")
    def test_denial_blocks_subsequent_symbol(self):
        with tempfile.TemporaryDirectory() as temp:
            client = EastmoneyClient(access(), SnapshotCache(Path(temp)),
                transport=lambda *a, **k: response(status=429), now=lambda: NOW, sleep=lambda _: None)
            for symbol in ("105.MSFT", "105.TEST"):
                with self.assertRaisesRegex(ValueError, "HTTP_429"):
                    client.fetch(symbol=symbol, start="2026-09-08", end="2026-09-09")
            self.assertEqual(client.requests, 1)


if __name__ == "__main__": unittest.main()
