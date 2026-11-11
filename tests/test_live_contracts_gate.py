from copy import deepcopy
from datetime import datetime, UTC
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.mcp.live.contracts import validate_contract, SCHEMAS, normalize_sec_fact, compare_live_financials
from product.mcp.live.identity import parse_sec_ticker_map, bind_portfolio_identity, freeze_identity, verify_frozen_identity
from product.mcp.provenance import content_hash
from product.runtime.hashing import legacy_envelope_hash
from product.mcp.live.cache import SnapshotCache


class Calendar:
    version = "synthetic-calendar/1"
    content_hash = "c" * 64

    def completed_sessions(self, cutoff):
        return ["2026-09-08T20:00:00Z", "2026-09-09T20:00:00Z"]


class LiveContractGateTests(unittest.TestCase):
    def setUp(self):
        self.portfolio = {"schema_version": "live-portfolio/1.0.0", "base_currency": "USD",
            "portfolio_complete": True, "synthetic_portfolio": True, "source_id": "synthetic-input",
            "as_of": "2026-09-10T00:00:00Z", "retrieved_at": "2026-09-10T00:00:00Z", "cash": 100,
            "holding_horizon": "6 months", "research_question": "Why hold?",
            "mandate": {"version": "synthetic/1", "max_position_weight": 0.6, "minimum_cash_weight": 0.1},
            "positions": [{"security_id": "TEST", "ticker": "TEST", "exchange": "XNAS", "share_class": "common",
                           "quantity": 10, "cost_basis": 1}], "focus_security_id": "TEST"}
        self.fact = {"schema_version": "live-fact/1.0.0", "evidence_id": "price", "security_id": "TEST",
            "semantic_field": "close_price", "value": "20", "unit": "USD", "currency": "USD",
            "source_id": "synthetic-market", "source_type": "yahoo", "source_locator": "synthetic",
            "source_version": "synthetic/1", "as_of": "2026-09-09T20:00:00Z",
            "published_at": "2026-09-09T20:00:00Z", "published_at_policy": "synthetic-close",
            "retrieved_at": "2026-09-10T00:00:00Z", "raw_content_hash": "a" * 64,
            "kind": "price", "usage": "current", "metadata": {"price_basis": "provider_close",
                "calendar_version": Calendar.version, "calendar_hash": Calendar.content_hash},
            "parent_ids": [], "parent_hashes": []}
        self.access = {"schema_version": "live-source-access/1.0.0", "provider": "yahoo", "client_version": "synthetic/1",
            "adapter_version": "synthetic/1", "status": "AUTHORIZED", "purpose": "personal-research",
            "terms_url": "synthetic-test-only", "checked_at": "2026-09-10T00:00:00Z",
            "free_features": ["synthetic"], "limitations": ["not real authorization"], "domains": ["example.invalid"], "request_budget": 1}

    def identity(self):
        raw = json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                          "data": [[i + 1, "Synthetic", p["ticker"], "Nasdaq"] for i, p in enumerate(self.portfolio["positions"])]}).encode()
        mapping = parse_sec_ticker_map(raw, retrieved_at="2026-09-10T00:00:00Z")
        metadata = [dict(m, security_type="COMMON_STOCK", currency="USD", share_class="common", filing_regime="DOMESTIC_10K_10Q") for m in mapping]
        return freeze_identity(self.portfolio, sec_mapping=mapping, security_metadata=metadata, cutoff="2026-09-10T01:00:00Z")

    def snapshot(self, facts=None, identity=None):
        return freeze_snapshot(snapshot_id="synthetic", portfolio=self.portfolio,
            request_started_at="2026-09-10T00:00:00Z", decision_cutoff="2026-09-10T01:00:00Z",
            facts=[self.fact] if facts is None else facts, source_access=[self.access],
            raw_records=[], collection_events=[], gaps=[], identity=identity)

    def test_portfolio_rejects_bad_inputs(self):
        mutations = [{"cash": float("nan")}, {"cash": float("inf")}, {"base_currency": "EUR"},
                     {"portfolio_complete": False}, {"focus_security_id": "absent"}]
        for changes in mutations:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_contract("portfolio", dict(self.portfolio, **changes))
        for changes in ({"quantity": 0}, {"quantity": True}, {"quantity": -1}, {"price": 10}, {"exchange": "OTC"}):
            value = deepcopy(self.portfolio)
            value["positions"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_contract("portfolio", value)

    def test_required_completeness_and_quantity_contract(self):
        for key in ("portfolio_complete", "holding_horizon", "mandate", "focus_security_id"):
            value = deepcopy(self.portfolio)
            del value[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_contract("portfolio", value)
        for quantity in (float("nan"), float("inf"), "10", None):
            value = deepcopy(self.portfolio)
            value["positions"][0]["quantity"] = quantity
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                validate_contract("portfolio", value)
        value = deepcopy(self.portfolio)
        value["positions"].append(dict(value["positions"][0], security_id="OTHER", share_class="B"))
        with self.assertRaises(ValueError):
            validate_contract("portfolio", value)

    def test_schema_copies_match_canonical(self):
        schema = json.loads((SCHEMAS / "live-snapshot.schema.json").read_text())
        for kind, key in (("fact", "facts"), ("source-access", "source_access")):
            canonical = json.loads((SCHEMAS / f"live-{kind}.schema.json").read_text())
            canonical.pop("$schema")
            canonical.pop("title")
            self.assertEqual(schema["properties"][key]["items"], canonical)

    def test_identity_binding_rejects_etf_class_and_cik_mismatch(self):
        raw = json.dumps({"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "Synthetic", "TEST", "Nasdaq"]]}).encode()
        mapping = parse_sec_ticker_map(raw, retrieved_at="2026-09-10T00:00:00Z")
        metadata = dict(mapping[0], security_type="COMMON_STOCK", currency="USD", share_class="common", filing_regime="DOMESTIC_10K_10Q")
        result = bind_portfolio_identity(self.portfolio, sec_mapping=mapping, security_metadata=[metadata])
        self.assertEqual(result["bindings"][0]["cik"], "0000000001")
        for mutation in ({"security_type": "ETF"}, {"share_class": "B"}, {"cik": "2"}, {"filing_regime": "20F"}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                bind_portfolio_identity(self.portfolio, sec_mapping=mapping, security_metadata=[dict(metadata, **mutation)])

