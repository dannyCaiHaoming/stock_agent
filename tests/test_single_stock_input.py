"""零模型身份接缝；合成 HTTP 记录不冒充真实 ALB 取数。"""
from copy import deepcopy
import hashlib
import json
import unittest
from pathlib import Path
import tempfile

from product.mcp.live.identity import parse_sec_ticker_map
from product.mcp.live.security_metadata import parse_chart_identity, bind_disclosure_security
from product.mcp.provenance import content_hash
from product.runtime.single_stock_input import (
    DEFAULT_QUESTION, build_single_stock_request, normalize_single_stock_intent,
    resolve_single_stock_identity, single_stock_subject, validate_single_stock_request,
)

AT = "2026-10-02T00:00:00Z"


def alb_identity():
    mapping = parse_sec_ticker_map(json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
        "data": [[915913, "ALB synthetic issuer", "ALB", "NYSE"]]}).encode(), retrieved_at=AT)
    raw = json.dumps({"chart": {"error": None, "result": [{"meta": {
        "symbol": "ALB", "instrumentType": "EQUITY", "currency": "USD",
        "exchangeName": "NYQ", "exchangeTimezoneName": "America/New_York"}}]}}).encode()
    record = {"raw_content_hash": hashlib.sha256(raw).hexdigest(), "retrieved_at": AT,
              "key": {"endpoint": "https://query1.finance.yahoo.com/v8/finance/chart/ALB"}}
    quote = parse_chart_identity(raw, ticker="ALB", record=record)
    cover = b'<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">Common Stock</ix:nonNumeric><ix:nonNumeric name="dei:TradingSymbol" contextRef="C">ALB</ix:nonNumeric><ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">NYSE</ix:nonNumeric>'
    document = {"form": "10-K", "raw_content_hash": hashlib.sha256(cover).hexdigest(),
        "cik": "0000915913", "source_id": "sec-synthetic-cover", "source_locator": "https://www.sec.gov/synthetic/cover.htm",
        "retrieved_at": AT, "published_at": "2026-02-01T00:00:00Z", "accession": "0000915913-26-000001"}
    return mapping, [bind_disclosure_security(cover, document, quote)]


def alb_request():
    mapping, metadata = alb_identity()
    return build_single_stock_request(normalize_single_stock_intent("alb", at=AT),
        sec_mapping=mapping, security_metadata=metadata, resolved_cutoff=AT, request_id="synthetic-alb")


class SingleStockInputTests(unittest.TestCase):
    def test_real_parsers_resolve_nyse_common_stock_without_account(self):
        request = alb_request()
        validate_single_stock_request(request)
        self.assertEqual(request["security"]["exchange"], "XNYS")
        self.assertEqual(request["security"]["cik"], "0000915913")
        self.assertEqual(request["research_question"], DEFAULT_QUESTION)
        self.assertEqual(request["resolved_cutoff"], AT)
        self.assertEqual(single_stock_subject(request)["security_id"], "US:COMMON_STOCK:ALB")
        for forbidden in ("portfolio", "quantity", "cost", "cash", "confirmation", "handoff_hash"):
            self.assertNotIn(forbidden, request)

    def test_unknown_ambiguous_foreign_etf_and_conflicting_identity_rejected(self):
        mapping, metadata = alb_identity()
        cases = [(mapping, []), (mapping * 2, metadata), ([], metadata)]
        for field, bad in (("security_type", "ETF"), ("exchange", "XNAS"), ("cik", "0000000001"),
                           ("filing_regime", "FOREIGN_20F"), ("currency", "HKD")):
            changed = deepcopy(metadata)
            changed[0][field] = bad
            cases.append((mapping, changed))
        for listing, covers in cases:
            with self.subTest(listing=listing, covers=covers), self.assertRaises(ValueError):
                resolve_single_stock_identity("ALB", sec_mapping=listing, security_metadata=covers, cutoff=AT)

    def test_dates_and_blank_question_fail_closed(self):
        for cutoff in ("2027-01-01T00:00:00Z", "2026-10-01", "garbage", None):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                normalize_single_stock_intent("ALB", cutoff=cutoff, at=AT)
        for symbol in ("ALB,MRVL", "", "US:ALB", 1):
            with self.assertRaises(ValueError):
                normalize_single_stock_intent(symbol, at=AT)
        with self.assertRaises(ValueError):
            normalize_single_stock_intent("ALB", question=" ", at=AT)

    def test_rehash_does_not_make_identity_or_future_provenance_valid(self):
        for field, bad in (("security_id", "US:COMMON_STOCK:MRVL"), ("cik", "0000000001")):
            request = alb_request()
            request["security"][field] = bad
            request["request_hash"] = content_hash({k: v for k, v in request.items() if k != "request_hash"})
            with self.assertRaises(ValueError):
                validate_single_stock_request(request)
        mapping, metadata = alb_identity()
        metadata[0]["retrieved_at"] = "2026-10-03T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "AFTER_CUTOFF"):
            resolve_single_stock_identity("ALB", sec_mapping=mapping, security_metadata=metadata, cutoff=AT)

    def test_explicit_cutoff_requires_frozen_identity_not_today_mapping(self):
        mapping, metadata = alb_identity()
        intent = normalize_single_stock_intent("ALB", cutoff="2026-09-01T00:00:00Z", at=AT)
        with self.assertRaisesRegex(ValueError, "AFTER_CUTOFF"):
            build_single_stock_request(intent, sec_mapping=mapping, security_metadata=metadata,
                resolved_cutoff=intent["requested_cutoff"])


class SingleStockCompanyTests(unittest.TestCase):
    def prepare_values(self):
        from product.council.intake_planning import build_common_stock_council_request
        from product.runtime.common_stock_stage import current_research_bindings
        from product.council.common_stock_research import prepare_common_stock_research_stage
        from product.runtime.hashing import canonical_hash
        source = alb_request()
        facts = [{"evidence_id": "ev-alb-revenue", "security_id": "US:COMMON_STOCK:ALB",
                  "semantic_field": "revenue", "value": "100", "source_id": "synthetic-sec",
                  "as_of": "2026-06-30T00:00:00Z", "retrieved_at": "2026-07-01T00:00:00Z"}]
        gate = {"run_id": "synthetic-alb-research", "decision_cutoff": AT,
                "input_evidence_ids": ["ev-alb-revenue"], "allowed_evidence_ids": ["ev-alb-revenue"],
                "excluded_evidence_ids": [], "allowed_evidence": facts, "excluded": []}
        gate["bundle_hash"] = canonical_hash(gate)
        council = build_common_stock_council_request(source, request_id="synthetic-council-alb",
                                                    research_question=source["research_question"])
        agent, skills = current_research_bindings(Path(__file__).resolve().parents[1])
        stage = prepare_common_stock_research_stage(source, council, gate, run_id=gate["run_id"],
            batch_id="synthetic-alb-batch", agent_binding=agent, skill_bindings=skills,
            effective_concurrency=1, execution_mode_reason="one research target")
        return source, council, gate, stage

class SingleStockDownstreamTests(unittest.TestCase):

    def test_latest_freeze_preserves_preparation_and_rejects_wrong_lineage(self):
        from product.runtime.single_stock_input import freeze_latest_research_request, validate_preparation_request_lineage
        source = alb_request()
        original = deepcopy(source)
        final = freeze_latest_research_request(source, resolved_cutoff="2026-10-02T01:00:00Z")
        validate_preparation_request_lineage(final, source)
        self.assertEqual(source, original)
        self.assertNotEqual(final["request_hash"], source["request_hash"])
        changed = deepcopy(source)
        changed["research_question"] = "different question"
        changed["request_hash"] = content_hash({k: v for k, v in changed.items() if k != "request_hash"})
        with self.assertRaises(ValueError):
            validate_preparation_request_lineage(final, changed)
        with self.assertRaises(ValueError):
            freeze_latest_research_request(source, resolved_cutoff="2026-10-01T00:00:00Z")

if __name__ == "__main__":
    unittest.main()
