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
from product.runtime.evidence_gate import run_live_evidence_gate
from product.runtime.live_input import freeze_snapshot, load_live_portfolio, value_portfolio, build_live_specialist_inputs
from product.runtime.invocation import build_specialist_inputs
from product.runtime.risk_runtime import check_live_cio_draft
from product.runtime.live_mcp import GateScopedLiveTools, StatelessLiveTools
from product.runtime.live_report import render_live_report
from product.runtime.run_package import prepare_live_run, prepare_cio, finalize_cio
from product.runtime.live_context import load_live_run_context
from product.runtime.discovery import discover_product_resources
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

    def test_max_count_duplicates_and_external_input(self):
        for count in (2, 4):
            value = deepcopy(self.portfolio)
            value["positions"] *= count
            with self.assertRaises(ValueError):
                validate_contract("portfolio", value)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "portfolio.json"
            path.write_text(json.dumps(self.portfolio))
            self.assertEqual(load_live_portfolio(path), self.portfolio)
        with self.assertRaisesRegex(ValueError, "INSIDE_REPOSITORY"):
            load_live_portfolio(Path(__file__).resolve())

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

    def test_value_uses_gate_price_not_cost(self):
        snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="live-test", calendar=Calendar()).artifact
        result = value_portfolio(self.portfolio, snapshot, gate, calendar=Calendar())
        self.assertEqual(result["total_value"], "300")
        self.assertEqual(result["positions"][0]["price"], "20")

    def test_future_information_excluded(self):
        for field, reason in (("as_of", "FUTURE_AS_OF"), ("published_at", "FUTURE_PUBLICATION"), ("retrieved_at", "FUTURE_RETRIEVAL")):
            fact = deepcopy(self.fact)
            fact[field] = "2026-09-11T00:00:00Z"
            result = run_live_evidence_gate(self.snapshot([fact]), run_id="live-test", calendar=Calendar()).artifact
            self.assertEqual(result["allowed_evidence"], [])
            self.assertIn(reason, result["excluded"][0]["reason_codes"])

    def test_calendar_and_access_fail_closed(self):
        snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="live-test").artifact
        self.assertIn("PRICE_CALENDAR_REQUIRED", gate["excluded"][0]["reason_codes"])
        self.access["status"] = "PAUSED"
        gate = run_live_evidence_gate(self.snapshot(), run_id="live-test", calendar=Calendar()).artifact
        self.assertIn("SOURCE_NOT_AUTHORIZED", gate["excluded"][0]["reason_codes"])

    def test_calendar_lock_drift_rejected(self):
        for key in ("calendar_version", "calendar_hash"):
            fact = deepcopy(self.fact)
            fact["metadata"][key] = "different"
            gate = run_live_evidence_gate(self.snapshot([fact]), run_id="test", calendar=Calendar()).artifact
            self.assertEqual(gate["allowed_evidence_ids"], [])
            self.assertIn("PRICE_CALENDAR_LOCK_MISMATCH", gate["excluded"][0]["reason_codes"])

    def test_missing_price_stops_whole_portfolio(self):
        self.portfolio["positions"].append(dict(self.portfolio["positions"][0], security_id="SECOND", ticker="SECOND"))
        snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="live-test", calendar=Calendar()).artifact
        with self.assertRaisesRegex(ValueError, "LIVE_PRICE_MISSING:SECOND"):
            value_portfolio(self.portfolio, snapshot, gate, calendar=Calendar())

    def test_rehashed_forged_gate_is_rejected(self):
        snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="live-test", calendar=Calendar()).artifact
        gate["allowed_evidence"][0]["value"] = "999"
        gate["bundle_hash"] = content_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
        with self.assertRaisesRegex(ValueError, "REVALIDATION_FAILED"):
            value_portfolio(self.portfolio, snapshot, gate, calendar=Calendar())

    def test_empty_and_snapshot_tamper(self):
        snapshot = self.snapshot([])
        self.assertEqual(run_live_evidence_gate(snapshot, run_id="live-test").allowed_ids, ())
        snapshot["decision_cutoff"] = "2026-10-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_HASH_MISMATCH"):
            run_live_evidence_gate(snapshot, run_id="live-test")

    def test_parent_exclusion_closure_cycle_and_hash(self):
        parent = dict(self.fact, retrieved_at="2026-09-11T00:00:00Z")
        derived = dict(self.fact, evidence_id="derived", kind="derived", source_type="derived",
                       parent_ids=["price"], parent_hashes=[content_hash(parent)], metadata={"formula": "parent*1"})
        result = run_live_evidence_gate(self.snapshot([derived, parent]), run_id="live-test", calendar=Calendar()).artifact
        self.assertIn("PARENT_EXCLUDED", result["excluded"][0]["reason_codes"])
        for mutation, message in (({"parent_ids": ["missing"]}, "CLOSURE"),
                                  ({"parent_ids": ["derived"]}, "CYCLE"),
                                  ({"parent_hashes": ["0" * 64]}, "HASH_MISMATCH")):
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, message):
                run_live_evidence_gate(self.snapshot([dict(derived, **mutation), parent]), run_id="live-test", calendar=Calendar())

    def test_financial_freshness_uses_period_not_download(self):
        self.access["provider"] = "sec"
        fact = dict(self.fact, kind="financial", source_type="sec", semantic_field="us-gaap.Revenues",
                    as_of="2025-12-31T00:00:00Z", metadata={"form": "10-Q", "period_end": "2025-12-31"})
        gate = run_live_evidence_gate(self.snapshot([fact]), run_id="live-test").artifact
        self.assertIn("STALE", gate["excluded"][0]["reason_codes"])
        fact["usage"] = "comparison"
        self.assertEqual(run_live_evidence_gate(self.snapshot([fact]), run_id="live-test").allowed_ids, ("price",))

    def test_current_sec_ownership_is_authorized_and_stale_disclosure_is_rejected(self):
        self.access["provider"] = "sec"
        fact = dict(
            self.fact,
            evidence_id="ownership",
            kind="ownership",
            semantic_field="ownership_insider_transaction",
            source_id="sec-ownership-synthetic",
            source_type="sec",
            source_version="sec-ownership-xml/1.1.1",
            value={"transaction_code": "P"},
            unit="reported_transaction",
            currency=None,
            as_of="2026-09-09T00:00:00Z",
            published_at="2026-09-09T21:30:00Z",
            metadata={"form": "4"},
        )
        gate = run_live_evidence_gate(self.snapshot([fact]), run_id="live-test").artifact
        self.assertEqual(gate["allowed_evidence_ids"], ["ownership"])

        stale = dict(
            fact,
            as_of="2026-05-01T00:00:00Z",
            published_at="2026-05-02T00:00:00Z",
        )
        gate = run_live_evidence_gate(self.snapshot([stale]), run_id="live-test").artifact
        self.assertEqual(gate["allowed_evidence_ids"], [])
        self.assertIn("STALE", gate["excluded"][0]["reason_codes"])

    def test_explicit_focus_keeps_full_portfolio_context(self):
        self.portfolio["positions"].append(dict(self.portfolio["positions"][0], security_id="SECOND", ticker="SECOND"))
        snapshot = self.snapshot()
        runtime_input = {"portfolio": dict(self.portfolio, positions=[dict(p, price=20) for p in self.portfolio["positions"]]),
                         "decision_cutoff": snapshot["decision_cutoff"]}
        for reverse in (False, True):
            if reverse:
                runtime_input["portfolio"]["positions"].reverse()
            specialist = build_specialist_inputs(run_id="test", fixture=runtime_input, allowed_evidence_ids=["price"],
                          research_question="synthetic", focus_security_id="SECOND")
            self.assertTrue(all(s["security_id"] == "SECOND" for s in specialist.values()))
            self.assertTrue(all(len(s["portfolio_summary"]["positions"]) == 2 for s in specialist.values()))

    def test_identity_binding_rejects_etf_class_and_cik_mismatch(self):
        raw = json.dumps({"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "Synthetic", "TEST", "Nasdaq"]]}).encode()
        mapping = parse_sec_ticker_map(raw, retrieved_at="2026-09-10T00:00:00Z")
        metadata = dict(mapping[0], security_type="COMMON_STOCK", currency="USD", share_class="common", filing_regime="DOMESTIC_10K_10Q")
        result = bind_portfolio_identity(self.portfolio, sec_mapping=mapping, security_metadata=[metadata])
        self.assertEqual(result["bindings"][0]["cik"], "0000000001")
        for mutation in ({"security_type": "ETF"}, {"share_class": "B"}, {"cik": "2"}, {"filing_regime": "20F"}):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                bind_portfolio_identity(self.portfolio, sec_mapping=mapping, security_metadata=[dict(metadata, **mutation)])

    def test_sec_normalization_and_derived_gate_chain(self):
        self.access["provider"] = "sec"
        raw = {"evidence_id": "financial-current", "security_id": "TEST", "taxonomy": "us-gaap", "tag": "Revenues",
               "value": "120", "unit": "USD", "source_id": "sec-synthetic", "source_locator": "synthetic",
               "adapter_version": "synthetic/1", "as_of": "2026-06-30T00:00:00Z",
               "published_at": "2026-08-01T00:00:00Z", "retrieved_at": "2026-08-02T00:00:00Z",
               "publication_retrieved_at": "2026-09-10T00:00:00Z", "raw_content_hash": "a" * 64,
               "cik": "0000000001", "form": "10-Q", "context_type": "duration", "period_start": "2026-01-01", "period_end": "2026-06-30"}
        current = normalize_sec_fact(raw, security_id="TEST")
        prior = normalize_sec_fact(dict(raw, evidence_id="financial-prior", value="100", period_start="2025-01-01",
                                   period_end="2025-06-30", as_of="2025-06-30T00:00:00Z"), security_id="TEST", usage="comparison")
        self.assertEqual(current["retrieved_at"], raw["publication_retrieved_at"])
        derivative = compare_live_financials(current["evidence_id"], prior["evidence_id"], {p["evidence_id"]: p for p in (current, prior)})
        gate = run_live_evidence_gate(self.snapshot([derivative, prior, current]), run_id="test").artifact
        self.assertEqual(len(gate["allowed_evidence_ids"]), 3)
        self.assertEqual(derivative["value"]["absolute_change"], "20")

    def test_live_risk_reuses_engine_and_keeps_veto(self):
        snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="test", calendar=Calendar()).artifact
        draft = {"action": "NO_TRADE", "security_id": "TEST", "target_weight_range": None, "maximum_notional": None,
                 "no_trade_reason": "synthetic", "no_trade_explanation": "synthetic", "reevaluation_conditions": ["synthetic"]}
        result = check_live_cio_draft(self.portfolio, snapshot, gate, draft, run_id="test", calendar=Calendar())
        self.assertEqual(result["producer"], "deterministic_risk_engine")
        self.assertEqual(result["final_action"], "NO_TRADE")
        self.assertEqual(result["check"]["mandate_version"], "synthetic/1")
        self.assertTrue(result["valuation_hash"])
        unscoped = check_live_cio_draft(self.portfolio, snapshot, gate, dict(draft, security_id=None), run_id="test", calendar=Calendar())
        self.assertEqual(unscoped["final_action"], "NO_TRADE")
        with self.assertRaisesRegex(ValueError, "NO_TRADE_EXECUTION_FIELDS_FORBIDDEN"):
            check_live_cio_draft(self.portfolio, snapshot, gate, dict(draft, maximum_notional=0), run_id="test", calendar=Calendar())

    def test_live_tools_only_expose_verified_gate(self):
        snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="test", calendar=Calendar()).artifact
        tools = GateScopedLiveTools(snapshot, gate, run_id="test", agent="runtime_skeptic", invocation_id="i", calendar=Calendar())
        result = tools.query(run_id="test", agent="runtime_skeptic", invocation_id="i", evidence_ids=["price"])
        self.assertIn("20", str(result))
        for changes in ({"run_id": "other"}, {"invocation_id": "other"}, {"evidence_ids": ["absent"]}):
            args = dict(run_id="test", agent="runtime_skeptic", invocation_id="i", evidence_ids=["price"])
            args.update(changes)
            with self.assertRaises(ValueError):
                tools.query(**args)
        self.assertEqual(tools.events[0]["tool"], "live_evidence.query")
        self.assertEqual(tools.events[0]["adapter_version"], "live-gate-scoped/1.0.0")
        self.assertEqual(result["adapter_version"], "live-gate-scoped/1.0.0")
        self.assertEqual(tools.events[0]["output_hash"], content_hash(result))

    def test_live_inputs_gate_before_context_and_independent_copies(self):
        future = dict(self.fact, evidence_id="future", retrieved_at="2026-09-11T00:00:00Z")
        snapshot = self.snapshot([self.fact, future], identity=self.identity())
        gate = run_live_evidence_gate(snapshot, run_id="test", calendar=Calendar()).artifact
        inputs = build_live_specialist_inputs(self.portfolio, snapshot, gate, calendar=Calendar())
        analyst, skeptic = inputs["runtime_company_analyst"], inputs["runtime_skeptic"]
        for value in inputs.values():
            self.assertEqual(value["allowed_evidence_ids"], ["price"])
            self.assertEqual(value["evidence_access"], "live_evidence.query")
            self.assertEqual(value["portfolio_summary"]["positions"][0]["price_evidence_id"], "price")
            self.assertNotIn("future", json.dumps(value))
            self.assertNotIn("fixture", json.dumps(value))
        analyst["portfolio_summary"]["positions"][0]["price"] = "999"
        self.assertEqual(skeptic["portfolio_summary"]["positions"][0]["price"], "20")
        snapshot = self.snapshot([future], identity=self.identity())
        gate = run_live_evidence_gate(snapshot, run_id="test", calendar=Calendar()).artifact
        with self.assertRaisesRegex(ValueError, "LIVE_PRICE_MISSING"):
            build_live_specialist_inputs(self.portfolio, snapshot, gate, calendar=Calendar())

    def test_identity_bottom_up_validation_before_agent(self):
        snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="test", calendar=Calendar()).artifact
        with self.assertRaisesRegex(ValueError, "IDENTITY_SNAPSHOT_MISSING"):
            build_live_specialist_inputs(self.portfolio, snapshot, gate, calendar=Calendar())
        identity = self.identity()
        identity["binding"]["bindings"][0]["cik"] = "0000000002"
        with self.assertRaisesRegex(ValueError, "IDENTITY_BINDING_MISMATCH"):
            verify_frozen_identity(self.portfolio, identity, cutoff="2026-09-10T01:00:00Z")
        identity = self.identity()
        identity["security_metadata"][0]["retrieved_at"] = "2026-09-11T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "IDENTITY_AFTER_CUTOFF"):
            verify_frozen_identity(self.portfolio, identity, cutoff="2026-09-10T01:00:00Z")

    def test_each_focus_input_shares_full_portfolio_and_snapshot(self):
        for ticker in ("SECOND", "THIRD"):
            self.portfolio["positions"].append(dict(self.portfolio["positions"][0], security_id=ticker, ticker=ticker))
        facts = [dict(self.fact, security_id=p["security_id"], evidence_id=f"price-{p['security_id']}") for p in self.portfolio["positions"]]
        snapshot = self.snapshot(facts, identity=self.identity())
        before = content_hash(self.portfolio)
        for position in self.portfolio["positions"]:
            run_id = f"focus-{position['security_id']}"
            gate = run_live_evidence_gate(snapshot, run_id=run_id, calendar=Calendar()).artifact
            inputs = build_live_specialist_inputs(self.portfolio, snapshot, gate, calendar=Calendar(), focus_security_id=position["security_id"])
            for value in inputs.values():
                self.assertEqual(value["security_id"], position["security_id"])
                self.assertEqual(value["portfolio_hash"], before)
                self.assertEqual(value["snapshot_hash"], snapshot["snapshot_hash"])
                self.assertEqual(len(value["portfolio_summary"]["positions"]), 3)
            self.assertEqual(value_portfolio(self.portfolio, snapshot, gate, calendar=Calendar())["total_value"], "700")
        self.assertEqual(content_hash(self.portfolio), before)

    def test_chinese_report_keeps_canonical_refs_and_no_trade_nulls(self):
        gate = run_live_evidence_gate(self.snapshot(), run_id="test", calendar=Calendar()).artifact
        item = {"action": "NO_TRADE", "security_id": "TEST", "target_weight_range": None, "maximum_notional": None,
                "no_trade_reason": "synthetic", "no_trade_explanation": "合成说明", "reevaluation_conditions": ["取得新披露"],
                "evidence_refs": ["price"], "thesis": "合成逻辑，非投资建议。"}
        decision = {"run_id": "test", "terminal_state": "SAFE_NO_TRADE", "advisory_only": True,
                    "decisions": [item], "risk_report": {"status": "APPROVED"}}
        reports = {"runtime_company_analyst": {"run_id": "test", "claims": [{"kind": "FACT", "statement": "合成价格",
                    "evidence_refs": ["price"], "assumption_ids": []}]}}
        report = render_live_report(decision, gate=gate, reports=reports, holding_horizon="六个月")
        for text in ("行情与业绩事实", "独立反证", "source_id", "synthetic-market", "2026-09-09T20:00:00Z", "暂不操作说明"):
            self.assertIn(text, report)
        item["maximum_notional"] = 0
        with self.assertRaisesRegex(ValueError, "NO_TRADE_EXECUTION_FIELDS_FORBIDDEN"):
            render_live_report(decision, gate=gate, reports=reports, holding_horizon="六个月")
        item["maximum_notional"] = None
        item["evidence_refs"] = ["price|source"]
        with self.assertRaises(ValueError):
            render_live_report(decision, gate=gate, reports=reports, holding_horizon="六个月")
        item["evidence_refs"] = ["price"]
        reports["runtime_company_analyst"]["claims"][0]["evidence_refs"] = []
        with self.assertRaisesRegex(ValueError, "UNGROUNDED_FACT"):
            render_live_report(decision, gate=gate, reports=reports, holding_horizon="六个月")

    @unittest.skipUnless(importlib.util.find_spec("exchange_calendars"), "可选 live 日历未安装")
    def test_live_prepare_reuses_native_invocations_without_fixture_alias(self):
        from product.mcp.live.market import ExchangeCalendar
        calendar = ExchangeCalendar(start="2026-09-01", end="2026-09-11")
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            cache = SnapshotCache(directory / "cache")
            mapping_raw = json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                                      "data": [[1, "Synthetic", "TEST", "Nasdaq"]]}).encode()
            records = [cache.store({"provider": "sec", "url": "synthetic-map"}, mapping_raw, retrieved_at="2026-09-10T00:00:00Z"),
                       cache.store({"provider": "yahoo", "ticker": "TEST"}, b"synthetic-price", retrieved_at="2026-09-10T00:00:00Z")]
            fact = deepcopy(self.fact)
            fact["raw_content_hash"] = records[1]["raw_content_hash"]
            fact["metadata"].update(calendar_version=calendar.version, calendar_hash=calendar.content_hash)
            snapshot = freeze_snapshot(snapshot_id="test", portfolio=self.portfolio, request_started_at="2026-09-10T00:00:00Z",
                decision_cutoff="2026-09-10T01:00:00Z", facts=[fact], source_access=[self.access], raw_records=records,
                collection_events=[], gaps=[], identity=self.identity())
            portfolio_path, snapshot_path = directory / "portfolio.json", directory / "snapshot.json"
            portfolio_path.write_text(json.dumps(self.portfolio))
            snapshot_path.write_text(json.dumps(snapshot))
            result = prepare_live_run(root, portfolio_path=portfolio_path, snapshot_path=snapshot_path,
                cache_root=cache.root, calendar=calendar, run_dir=directory / "run", run_id="synthetic-prepare",
                model=discover_product_resources(root).version_manifest["model"], authenticity_required=False)
            self.assertEqual(result["next_state"], "DISPATCH_REQUIRED", result)
            run_dir = directory / "run"
            manifest = json.loads((run_dir / "run_manifest.json").read_text())
            self.assertNotIn("fixture", manifest)
            self.assertNotIn("fixture_id", manifest)
            self.assertFalse((run_dir / "audit/fixture_snapshot.json").exists())
            self.assertFalse((run_dir / "decision.json").exists())
            loaded = load_live_run_context(run_dir, manifest)
            self.assertEqual(loaded[1], snapshot)
            for name in ("runtime_company_analyst", "runtime_skeptic"):
                invocation = json.loads((run_dir / f"invocations/{name}.json").read_text())
                self.assertEqual(invocation["source_context"]["source_mode"], "live")
                self.assertTrue(all(tool.startswith("live_") for tool in invocation["tool_permissions"]))
                tools = StatelessLiveTools()
                answer = tools.query(run_dir=str(run_dir), run_id=manifest["run_id"], agent=name,
                                     invocation_id=invocation["invocation_id"], evidence_ids=["price"])
                self.assertEqual(answer["adapter_version"], "live-gate-scoped/1.0.0")
                with self.assertRaises(ValueError):
                    tools.query(run_dir=str(run_dir), run_id="other", agent=name,
                                invocation_id=invocation["invocation_id"], evidence_ids=["price"])
            # 仅合成报告驱动确定性接缝，不冒充 LLM 执行证明。
            from tests.test_native_run_package import specialist_outputs, cio_output, write_json
            specialist_outputs(run_dir)
            for name in ("runtime_company_analyst", "runtime_skeptic"):
                path = run_dir / f"agents/{name}.json"
                text = path.read_text()
                for old in ("ev-normal-revenue", "ev-normal-debt", "ev-normal-margin"):
                    text = text.replace(old, "price")
                path.write_text(text)
            result = prepare_cio(root, run_dir=run_dir, model=manifest["model"])
            self.assertEqual(result["next_state"], "CIO_SYNTHESIS_REQUIRED", result)
            cio_input = json.loads((run_dir / "inputs/runtime_cio.json").read_text())
            self.assertEqual(cio_input["portfolio_hash"], content_hash(self.portfolio))
            self.assertEqual(cio_input["security_id"], "TEST")
            draft = cio_output(run_dir)
            draft.update(action="NO_TRADE", security_id="TEST", target_weight_range=None, maximum_notional=None,
                         no_trade_reason="INSUFFICIENT_EVIDENCE", no_trade_explanation="合成测试缺少披露",
                         reevaluation_conditions=["取得披露"], evidence_refs=["price"])
            write_json(run_dir / "cio/runtime_cio.json", draft)
            finished = finalize_cio(root, run_dir=run_dir)
            self.assertEqual(finished["next_state"], "SAFE_NO_TRADE", finished)
            self.assertTrue((run_dir / "risk/check-1.json").is_file())
            self.assertIn("证据来源与时间", (run_dir / "report.md").read_text())
            self.assertIn("组合总值（USD）：300", (run_dir / "report.md").read_text())
            decision = json.loads((run_dir / "decision.json").read_text())
            self.assertIsNone(decision["decisions"][0]["maximum_notional"])
            from product.runtime.trace_validation import validate_decision_trace
            from product.runtime.replay import replay_run
            trace = json.loads((run_dir / "decision_trace.json").read_text())
            validate_decision_trace(trace, run_dir=run_dir)
            replay = replay_run(root, run_dir=run_dir)
            self.assertEqual(replay["status"], "PASSED")
            self.assertFalse(replay["execution_replay_ready"])
            from product.runtime.native_eval import evaluate_run, persist_eval_result
            from product.runtime.release_gate import check_run
            with self.assertRaisesRegex(ValueError, "TEST_ONLY_RUN"):
                evaluate_run(root, run_dir=run_dir)
            evaluated = evaluate_run(root, run_dir=run_dir, allow_test_artifacts=True)
            self.assertNotIn("fixture_id", evaluated)
            self.assertEqual(evaluated["checks"]["research_quality"], "REQUIRES_BOUND_SEMANTIC_EVAL")
            persist_eval_result(evaluated, run_dir=run_dir)
            verdict, exit_code = check_run(root, run_dir=run_dir)
            self.assertEqual(exit_code, 0, verdict)
            self.assertEqual(verdict["category"], "RUNTIME_SAFE_RESEARCH_UNASSESSED")
            from product.runtime.runtime_eval import prepare_eval_job, build_eval_smoke_prompt
            eval_dir = directory / "semantic-eval"
            grading = prepare_eval_job(root, run_dir=run_dir, eval_dir=eval_dir, eval_id="synthetic-live-eval")
            self.assertEqual(grading["next_state"], "SEMANTIC_GRADING_REQUIRED")
            grading_input = json.loads((eval_dir / "grader-input.json").read_text())
            self.assertEqual(grading_input["artifacts"]["audit/live/portfolio.json"], self.portfolio)
            self.assertIn("live-us-equity-rubric-v1.json", build_eval_smoke_prompt(root, eval_dir=eval_dir))
            self.assertFalse((eval_dir / "result.json").exists())
            # 仅注入测试评分，验证真实评分作业的输入绑定/失败传播；不冒充 LLM 评分。
            from tests.test_runtime_eval_job import semantic_result
            from product.runtime.runtime_eval import finalize_eval_job, verify_runtime_eval_job
            grade = semantic_result(eval_dir, status="FAIL", grade=0)
            grade["grader"]["rubric_hash"] = "0" * 64
            grade["output_hash"] = content_hash({k:v for k,v in grade.items() if k != "output_hash"})
            grade_path = directory / "synthetic-grade.json"
            grade_path.write_text(json.dumps(grade))
            with self.assertRaisesRegex(ValueError, "GRADER_LINEAGE"):
                finalize_eval_job(root, eval_dir=eval_dir, semantic_result_path=grade_path)
            grade_path.write_text(json.dumps(semantic_result(eval_dir, status="FAIL", grade=0)))
            quality = finalize_eval_job(root, eval_dir=eval_dir, semantic_result_path=grade_path)
            self.assertEqual(quality["status"], "FAIL")
            self.assertTrue((eval_dir / "eval/result.json").is_file())
            verify_runtime_eval_job(root, eval_result_path=eval_dir / "eval/result.json")
            saved = run_dir / "audit/live/snapshot.json"
            saved.write_text(saved.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "LIVE_RUN_SOURCE_HASH_MISMATCH"):
                load_live_run_context(run_dir, manifest)
