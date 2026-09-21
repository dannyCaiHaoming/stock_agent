from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import http.client
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from product.council.common_stock_research import validate_equity_research_report
from product.council.multidimensional_research import finalize_research_dimension_report
from product.council.research_visuals import build_visual_bundle
from product.runtime.equity_research_package import build_equity_research_package
from product.runtime.hashing import canonical_hash
from product.mcp.provenance import content_hash
from product.runtime.live_input import freeze_snapshot
from product.runtime.research_memory import (
    ResearchMemory, ResearchMemoryError, fact_content_hash, report_reuse_key,
)
from product.runtime.research_memory_repair import (
    apply_view_reference_repairs, inspect_view_references,
)
from product.web.app import ResearchBrowser, build_server
from product.web.read_only import ArtifactCatalog, BrowserDataError, ReadOnlyResearchMemory


def dimension_report(
    *, decision_cutoff: str = "2026-09-01T00:00:00Z", run_id: str = "run-1",
    capability: str = "MACRO_MARKET", report_id: str | None = None,
    schema_version: str = "research-dimension-report/1.1.0",
    summary: str = "已保存研究，不在浏览时重算。",
    evidence_id: str = "ev-market-1", security_id: str = "US:MRVL",
) -> dict:
    company_capabilities = {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT"}
    value = {
        "schema_version": schema_version,
        "report_id": report_id or f"dimension-report:{capability.casefold().replace('_', '-')}", "run_id": run_id,
        "invocation_id": "inv-1", "capability": capability,
        "scope": "PER_SECURITY", "security_ids": [security_id],
        "status": "COMPLETE", "sufficiency": "SUFFICIENT", "evaluation_status": "PASS",
        "bindings": {
            "handoff_id": "handoff-1", "handoff_hash": "a" * 64,
            "portfolio_hash": "b" * 64, "council_request_id": "request-1",
            "council_request_hash": "c" * 64,
            "decision_cutoff": decision_cutoff,
        },
        "time_context": {
            "window_start": "2025-09-01T00:00:00Z", "window_end": "2026-09-01T00:00:00Z",
            "benchmark_id": "US:ETF:SPY", "price_adjustment": "ADJUSTED_CLOSE",
            "timezone": "America/New_York",
        },
        "execution": {
            "agent_name": "runtime_company_analyst" if capability in company_capabilities else "runtime_market_catalyst",
            "agent_version": "1.0.0",
            "skill_name": "company-research" if capability == "FUNDAMENTAL_EVENT" else (
                "research-report-analysis" if capability == "RESEARCH_REPORT" else (
                    "ownership-disclosure" if capability == "OWNERSHIP_DISCLOSURE" else (
                        "industry-comparison" if capability == "INDUSTRY_COMPARISON" else "macro-market-analysis"
                    )
                )
            ),
            "skill_version": "1.0.0",
            "skill_hash": "d" * 64, "model": "gpt-5.6-terra", "prompt_hash": "e" * 64,
            "input_refs": ["evidence:bundle:1"], "raw_output_hash": "f" * 64,
        },
        "summary": summary,
        "claims": [{
            "claim_id": "claim-1", "question": "市场环境如何？",
            "statement": "当前只使用冻结市场资料。", "kind": "INTERPRETATION",
            "evidence_refs": [evidence_id], "research_claim_refs": [],
            "document_refs": [], "assumption_ids": [], "calculation_refs": ["calc-1"],
        }],
        "assumptions": [],
        "calculations": [{
            "calculation_id": "calc-1", "method": "saved_window", "value": "0.01",
            "unit": "ratio", "input_evidence_refs": [evidence_id],
            "artifact_ref": "research/precomputed/market/market-state-calculation.json",
        }],
        "documents": [], "research_relationships": [], "limitations": [],
        "observation_conditions": [{
            "condition_id": "condition-1", "description": "资料更新后需重新观察。",
            "claim_refs": ["claim-1"], "evidence_refs": [evidence_id],
        }],
        "data_gaps": [],
        "artifact_refs": ["research/precomputed/market/market-state-calculation.json"],
    }
    return finalize_research_dimension_report(value)


def provider_coverage_fixture(
    *, decision_cutoff: str = "2026-03-02T00:00:00Z",
    security_id: str = "US:MRVL",
) -> dict:
    definitions = (
        ("dot_plot", "MACRO_CONTEXT", 12, "DELIVERED", "ev-dot-1", "AVAILABLE"),
        ("economic_calendar", "MACRO_CONTEXT", 100, "DELIVERED", "ev-calendar-1", "PARTIAL"),
        ("macro_history", "MACRO_CONTEXT", 192, "DELIVERED", "ev-macro-1", "PARTIAL"),
        ("fedwatch_expectations", "MARKET_STATE", 3, "DELIVERED", "ev-fed-1", "AVAILABLE"),
        ("market_breadth", "MARKET_STATE", 0, "NO_GATE_EVIDENCE", None, "SOURCE_LIMITED"),
        ("option_market_statistics", "MARKET_STATE", 37, "DELIVERED", "ev-option-stat-1", "PARTIAL"),
        ("options_snapshot", "OPTIONS_FLOW", 48, "DELIVERED", "ev-option-1", "PARTIAL"),
        ("options_underlying_context", "OPTIONS_FLOW", 1, "DELIVERED", "ev-underlying-1", "PARTIAL"),
        ("vendor_money_flow", "OPTIONS_FLOW", 9, "DELIVERED", "ev-flow-1", "PARTIAL"),
        ("financial_history", "FUNDAMENTAL_EVENT", 200, "DELIVERED", "ev-financial-1", "PARTIAL"),
        ("event_context", "FUNDAMENTAL_EVENT", 0, "NO_GATE_EVIDENCE", None, "NOT_ATTEMPTED"),
        ("analyst_expectations", "RESEARCH_REPORT", 3, "DELIVERED", "ev-analyst-1", "PARTIAL"),
        ("institutional_ownership", "OWNERSHIP_DISCLOSURE", 0, "NO_GATE_EVIDENCE", None, "SOURCE_LIMITED"),
        ("peer_comparison", "INDUSTRY_COMPARISON", 2, "DELIVERED", "ev-peer-1", "AVAILABLE"),
    )
    routes = []
    observations = []
    for dataset, capability, count, delivery, evidence_id, status in definitions:
        routes.append({
            "dataset": dataset, "target_capability": capability,
            "capture_evidence_count": count,
            "gate_eligible_evidence_count": count,
            "delivered_evidence_count": count,
            "delivery_status": delivery, "exclusions": [],
            "actual_research_use_status": "NOT_EVALUATED_AT_PREPARATION",
        })
        observations.append({
            "security_id": security_id, "dataset": dataset, "status": status,
            "failure_code": "FIXTURE_SOURCE_LIMITED" if count == 0 else None,
            "checked_at": decision_cutoff, "as_of": decision_cutoff,
            "evidence_ids": [evidence_id] if evidence_id else [],
            "limitations": ["确定性测试限制"] if count == 0 else [],
        })
    value = {
        "schema_version": "research-provider-coverage/1.0.0",
        "profile_id": "holding-research-inputs/1.0.0",
        "topology_hash": "a" * 64,
        "decision_cutoff": decision_cutoff,
        "providers": [{
            "plane": "RESEARCH_SUPPLEMENT", "provider": "moomoo_sg",
            "region": "SG", "access": "public_read_only",
            "declared_status": "ACTIVE", "observed_status": "PARTIAL",
            "evidence_count": sum(item[2] for item in definitions),
            "capture_evidence_count": sum(item[2] for item in definitions),
            "gate_delivered_evidence_count": sum(item[2] for item in definitions),
            "delivery_status": "DELIVERED",
            "actual_research_use_status": "NOT_EVALUATED_AT_PREPARATION",
            "dataset_observations": observations,
            "failure_codes": ["FIXTURE_SOURCE_LIMITED"],
            "limitations": [],
        }],
        "fallback_policy": {
            "supplement_failure_isolated": True,
            "base_sources_continue": ["sec", "yahoo"],
            "forbidden_fallbacks": ["CLIENT_COOKIE", "PRIVATE_API", "LOGIN_BYPASS"],
            "credential": "must-not-render",
            "local_path": "/private/must-not-render",
        },
        "capability_routing": {
            "dataset_observations": routes,
            "failure_codes": [], "status": "CLOSED",
        },
    }
    value["coverage_hash"] = canonical_hash(value)
    return value


def evidence_gate_fixture(
    *, decision_cutoff: str = "2026-03-02T00:00:00Z",
    run_id: str = "run-1", security_id: str = "US:MRVL",
) -> dict:
    def fact(evidence_id: str, semantic_field: str, value: dict, *, scope: str = security_id) -> dict:
        return {
            "schema_version": "live-fact/1.0.0",
            "evidence_id": evidence_id,
            "security_id": scope,
            "semantic_field": semantic_field,
            "source_id": "fixture-provider",
            "source_type": "SECONDARY_VENDOR",
            "as_of": decision_cutoff,
            "retrieved_at": decision_cutoff,
            "value": value,
            "credentials": "must-not-render",
        }

    allowed = [
        fact("ev-dot-1", "moomoo_dot_plot:2026-4.125", {
            "year": 2026, "rate": 4.125, "vote_count": 12,
            "median_rate": 4.125, "is_median": True, "current_rate": 3.88,
        }, scope="US:MARKET"),
        fact("ev-calendar-1", "moomoo_economic_calendar:cpi", {
            "title": "美国 CPI 同比", "country": "US", "timestamp": 1772409600,
            "star": 3, "actual": "3.4%", "consensus": "3.2%", "previous": "3.1%",
        }, scope="US:MARKET"),
        fact("ev-macro-1", "moomoo_us_cpi_yoy:2026-02", {
            "label": "CPI 同比", "actual": 0.034, "consensus": 0.032,
            "previous": 0.031, "unit_type": "PERCENT", "indicator_id": "us_cpi_yoy",
        }, scope="US:MARKET"),
        fact("ev-fed-1", "moomoo_fedwatch:2026-10-28-4.00-4.25", {
            "meeting_date": "2026-10-28", "target_range": "4.00%-4.25%", "probability": 53.1,
        }, scope="US:MARKET"),
        fact("ev-option-stat-1", "moomoo_option_market_volume:2026-03-02", {
            "time": "2026-03-02", "call_value": 1000, "put_value": 707,
            "total_value": 1707, "ratio": 0.707,
        }, scope="US:MARKET"),
        fact("ev-option-1", "option_chain_contract:MRVL260925C00100000", {
            "contract_symbol": "MRVL260925C00100000", "expiration": "2026-09-25",
            "strike": 100, "option_type": "CALL", "bid": 1.1, "ask": 1.3,
            "last_price": 1.2, "volume": 42, "open_interest": 84,
            "implied_volatility": 0.67922, "greeks": {"delta": None, "token": "must-not-render"},
        }),
        fact("ev-underlying-1", "moomoo_option_underlying_overview:MRVL", {
            "code": "US.MRVL", "name": "Marvell Technology", "iv": 67.922,
            "iv_percentile": 43.65, "iv_rank": 35.158, "hv_30d": 49.2,
            "call_volume": 120, "put_volume": 90,
            "call_open_interest": 1000, "put_open_interest": 743,
        }),
        fact("ev-flow-1", "moomoo_vendor_money_flow:overall", {
            "category": "overall", "amount": -62027577.937,
            "capital_in": 1000000, "capital_out": 63027577.937,
            "currency": "USD", "unit": "currency", "definition": "供应商订单规模分类",
        }),
        fact("ev-not-declared", "moomoo_vendor_money_flow:private", {
            "category": "SHOULD_NOT_RENDER", "amount": 999999,
        }),
    ]
    value = {
        "schema_version": "common-stock-research-evidence-gate/1.0.0",
        "run_id": run_id, "decision_cutoff": decision_cutoff,
        "allowed_evidence_ids": [item["evidence_id"] for item in allowed],
        "allowed_evidence": allowed,
        "excluded_evidence_ids": [], "excluded": [], "conflicts": [],
    }
    value["bundle_hash"] = canonical_hash(value)
    return value


def equity_report_fixture(
    *, run_id: str = "run-1", invocation_id: str = "inv-company-1",
    cutoff: str = "2026-03-02T00:00:00Z", report_id: str = "equity-report-1",
    summary: str = "核心经济逻辑有依据，但现金转化是主要反证。",
) -> tuple[dict, dict]:
    skills = [
        {"name": name, "version": "1.0.0", "content_hash": canonical_hash(name)}
        for name in ("evidence-grounding", "company-research", "valuation", "catalyst-analysis")
    ]
    request = {
        "schema_version": "holding-research-request/1.0.0",
        "run_id": run_id, "invocation_id": invocation_id,
        "handoff_id": "handoff-1", "handoff_hash": "1" * 64,
        "portfolio_hash": "2" * 64, "council_request_id": "council-1",
        "council_request_hash": "3" * 64, "request_id": "holding-request-1",
        "decision_cutoff": cutoff,
        "security": {
            "security_id": "US:MRVL", "display_symbol": "MRVL",
            "display_name": "Marvell Technology", "market": "XNAS",
            "asset_type": "COMMON_STOCK", "identity_status": "USER_CONFIRMED",
        },
        "research_question": "private question must not render",
        "holding_horizon": None,
        "skill_bindings": skills,
        "allowed_evidence_ids": ["ev-revenue"],
        "evidence_bundle_hash": "7" * 64,
        "data_gaps": [],
        "user_context": {"user_thesis": None, "user_questions": []},
        "agent_binding": {
            "name": "runtime_company_analyst", "version": "1.0.0",
            "content_hash": "8" * 64,
        },
    }
    request["request_hash"] = canonical_hash(request)
    section_names = (
        "company_and_core_questions", "business_competition_financials",
        "thesis_and_valuation", "catalysts_and_counterevidence",
        "invalidation_and_monitoring", "gaps_and_confidence",
    )
    report = {
        "schema_version": "equity-research-report/1.0.0",
        "run_id": run_id, "invocation_id": invocation_id,
        "report_id": report_id, "status": "COMPLETE",
        "agent": "runtime_company_analyst",
        "bindings": {
            "handoff_id": request["handoff_id"], "handoff_hash": request["handoff_hash"],
            "portfolio_hash": request["portfolio_hash"],
            "council_request_id": request["council_request_id"],
            "council_request_hash": request["council_request_hash"],
            "holding_research_request_id": request["request_id"],
            "holding_research_request_hash": request["request_hash"],
            "decision_cutoff": cutoff,
        },
        "security": {
            key: request["security"][key]
            for key in ("security_id", "display_symbol", "display_name", "market", "asset_type")
        },
        "research_scope": "SINGLE_COMMON_STOCK_HOLDING",
        "research_summary": {
            "summary": summary, "claim_refs": ["claim-core", "claim-counter"],
            "primary_invalidation_condition_ids": ["condition-demand"],
        },
        "sections": {
            name: {
                "status": "ANALYZED", "narrative": f"{name} 的公司专属分析。",
                "claim_refs": ["claim-core"], "data_gap_ids": ["gap-guidance"],
            }
            for name in section_names
        },
        "claims": [{
            "claim_id": "claim-core", "statement": "收入事实支持当前商业规模判断。",
            "kind": "INTERPRETATION", "evidence_refs": ["ev-revenue"],
            "assumption_ids": ["assumption-demand"], "calculation_refs": [],
            "counter_claim_refs": ["claim-counter"],
            "invalidation_condition_ids": ["condition-demand"],
        }, {
            "claim_id": "claim-counter", "statement": "现金转化仍可能弱于收入增长。",
            "kind": "INTERPRETATION", "evidence_refs": ["ev-revenue"],
            "assumption_ids": [], "calculation_refs": [], "counter_claim_refs": [],
            "invalidation_condition_ids": ["condition-demand"],
        }],
        "assumptions": [{
            "assumption_id": "assumption-demand", "statement": "需求保持稳定。",
            "rationale": "用于检验收入持续性。", "evidence_refs": ["ev-revenue"],
        }],
        "counter_evidence_refs": ["ev-revenue"],
        "invalidation_conditions": [{
            "condition_id": "condition-demand", "description": "收入连续两个可比期间下降。",
            "monitoring_signal": "季度收入同比变化", "claim_refs": ["claim-core"],
            "evidence_refs": ["ev-revenue"],
        }],
        "reevaluation_triggers": [{
            "trigger_id": "trigger-filing", "description": "下一份定期报告发布后重评。",
            "claim_refs": ["claim-core"], "evidence_refs": ["ev-revenue"],
        }],
        "monitoring_indicators": [{
            "indicator_id": "indicator-cash", "description": "经营现金流",
            "why_it_matters": "检验盈利质量。", "baseline": "100", "unit": "USD",
            "comparison_period": "最近披露期间", "reevaluation_rule": "下一可比期间重评。",
            "evidence_refs": ["ev-revenue"],
        }],
        "data_gaps": [{
            "gap_id": "gap-guidance", "reason_code": "NOT_FETCHED",
            "description": "尚未保存公司指引。", "impact": "催化剂判断受限。",
        }],
        "confidence": 0.68,
        "confidence_rationale": "置信度代表证据支持程度，不是上涨概率。",
        "skill_execution": [{
            "skill_name": item["name"], "version": item["version"],
            "invocation_hash": canonical_hash(item["name"] + invocation_id),
        } for item in skills],
        "artifact_refs": [],
    }
    validate_equity_research_report(report, request=request)
    return request, report


class LocalResearchBrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "memory"
        self.root.mkdir()
        self.writer = ResearchMemory(self.root)
        self.first = self.fact(value="100", retrieved_at="2026-03-02T00:00:00Z")
        plan = self.writer.plan("US:MRVL", "sec", "sec_companyfacts", planning_as_of="2026-03-02T00:00:00Z")
        self.writer.ingest_dataset(
            plan=plan, facts=[self.first], status="FETCHED_BOOTSTRAP",
            completed_at="2026-03-02T00:00:00Z", watermark=self.first["as_of"],
            coverage=[{"start": "2026-01-01", "end": "2026-01-31"}],
        )
        self.view1 = self.writer.save_view(
            run_id="run-1", security_id="US:MRVL", decision_cutoff="2026-03-02T00:00:00Z",
            facts=[self.first], gaps=[], conflicts=[],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def fact(**updates):
        value = {
            "evidence_id": "ev-revenue", "security_id": "US:MRVL",
            "source_id": "sec-companyfacts-0001835632",
            "source_locator": "https://data.sec.gov/submissions/example.json",
            "semantic_field": "revenue", "value": "100", "unit": "USD", "currency": "USD",
            "as_of": "2026-01-31T00:00:00Z", "published_at": "2026-03-01T00:00:00Z",
            "retrieved_at": "2026-03-02T00:00:00Z", "raw_content_hash": "a" * 64,
            "metadata": {"period_end": "2026-01-31", "form": "10-K", "accession": "0001"},
        }
        value.update(updates)
        return value

    def reader(self) -> ReadOnlyResearchMemory:
        return ReadOnlyResearchMemory(self.root)

    def store_report(
        self, *, entry_id: str = "entry-1", run_id: str = "run-1",
        invocation_id: str = "inv-company-1", cutoff: str = "2026-03-02T00:00:00Z",
        report_id: str = "equity-report-1", summary: str = "核心经济逻辑有依据，但现金转化是主要反证。",
        package_mutator=None, manifest_mutator=None, index_status: str | None = None,
    ) -> dict:
        request, report = equity_report_fixture(
            run_id=run_id, invocation_id=invocation_id, cutoff=cutoff,
            report_id=report_id, summary=summary,
        )
        fingerprint = f"fingerprint:{entry_id}"
        markdown = summary
        package = {
            "schema_version": "company-research-report-package/1.0.0",
            "security_id": "US:MRVL", "research_input_fingerprint": fingerprint,
            "reuse_key": report_reuse_key("US:MRVL", fingerprint),
            "report": report, "markdown": markdown, "request": request,
            "evidence": [deepcopy(self.first)], "calculations": [], "attachment": None,
            "validation": {},
            "manifest": {},
        }
        if package_mutator is not None:
            package_mutator(package)
        report_hash = canonical_hash(package["report"])
        package["manifest"] = {
            "report_hash": report_hash, "request_hash": canonical_hash(package["request"]),
            "evidence_hash": canonical_hash(package["evidence"]),
            "calculation_hash": canonical_hash(package["calculations"]),
            "attachment_hash": canonical_hash(package["attachment"]),
            "markdown_hash": hashlib.sha256(str(package["markdown"]).encode()).hexdigest(),
        }
        if manifest_mutator is not None:
            manifest_mutator(package["manifest"])
        stored = self.writer.store_object(package)
        with self.writer.session() as connection:
            connection.execute(
                "INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry_id, package["reuse_key"], "US:MRVL", fingerprint,
                    report_hash, stored["object_hash"], stored["object_ref"],
                    run_id, invocation_id, cutoff, index_status or {
                        "COMPLETE": "VALID_RESEARCH",
                        "LOW_CONFIDENCE": "LOW_CONFIDENCE",
                        "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
                        "TIMEOUT": "FAILED",
                    }[str(package["report"].get("status"))],
                    "2026-03-03T00:00:00Z", "{}",
                ),
            )
        return report

    def test_missing_database_does_not_create_and_unknown_schema_fails(self):
        missing = self.base / "missing"
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_MEMORY_DATABASE_MISSING"):
            ReadOnlyResearchMemory(missing)
        self.assertFalse(missing.exists())
        with self.writer.session() as connection:
            connection.execute("PRAGMA user_version=999")
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_MEMORY_SCHEMA_UNSUPPORTED"):
            self.reader()

    def test_connection_is_query_only(self):
        with self.reader().connect() as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM fact_versions")
        with self.writer.session() as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM fact_versions").fetchone()[0])

    def test_company_identity_fallback_pagination_and_status(self):
        result = self.reader().list_companies(query="mrvl", status="no_report", page=1, per_page=1)
        self.assertEqual(1, result["total"])
        item = result["items"][0]
        self.assertEqual("MRVL", item["ticker"])
        self.assertIsNone(item["company_name"])
        self.assertTrue(item["no_report"])
        detail = self.reader().company("US:MRVL")
        self.assertEqual("100", detail["fact_groups"]["财务与披露"][0]["value"])
        self.assertIn("financial_revenue", {item["chart_id"] for item in detail["charts"]})
        self.assertIn("trailing_pe_history", {item["chart_id"] for item in detail["charts"]})
        rendered = ResearchBrowser(self.reader(), ArtifactCatalog()).dispatch(
            "GET", "/companies/US%3AMRVL", {"Host": "localhost"},
        )
        self.assertEqual(200, rendered.status)
        self.assertIn("查看全部财务原始事实与版本", rendered.body.decode())
        facts = self.reader().facts_page("US:MRVL", group="财务与披露", page=1, per_page=1)
        self.assertEqual(1, facts["total"])
        self.assertEqual("revenue", facts["items"][0]["semantic_field"])

    def test_company_without_view_is_an_unfrozen_fact_catalog(self):
        fact = self.fact(
            evidence_id="ev-no-view", security_id="US:NOVIEW", value="321",
            retrieved_at="2026-03-03T00:00:00Z",
        )
        plan = self.writer.plan(
            "US:NOVIEW", "sec", "sec_companyfacts", planning_as_of="2026-03-03T00:00:00Z",
        )
        self.writer.ingest_dataset(
            plan=plan, facts=[fact], status="FETCHED_BOOTSTRAP",
            completed_at="2026-03-03T00:00:00Z",
        )
        model = self.reader().company("US:NOVIEW")
        self.assertIsNone(model["selected_view"])
        self.assertEqual("UNFROZEN_FACT_CATALOG", model["view_integrity"]["mode"])
        self.assertFalse(model["financial_metrics"])
        self.assertFalse(model["charts"])
        app = ResearchBrowser(self.reader(), ArtifactCatalog())
        detail = app.dispatch("GET", "/companies/US%3ANOVIEW", {"Host": "localhost"}).body.decode()
        self.assertIn("未冻结事实目录", detail)
        self.assertNotIn("View 引用完整", detail)
        self.assertNotIn("营收趋势", detail)
        catalog = app.dispatch("GET", "/companies/US%3ANOVIEW/facts", {"Host": "localhost"}).body.decode()
        self.assertIn("未冻结事实目录记录", catalog)
        self.assertNotIn("已选 View 事实", catalog)

    def test_view_comparison_uses_content_versions(self):
        revised = self.fact(
            evidence_id="ev-revenue-revised", value="110", published_at="2026-03-03T00:00:00Z",
            retrieved_at="2026-03-04T00:00:00Z", raw_content_hash="b" * 64,
        )
        plan = self.writer.plan("US:MRVL", "sec", "sec_companyfacts", planning_as_of="2026-03-04T00:00:00Z")
        self.writer.ingest_dataset(plan=plan, facts=[revised], status="FETCHED_INCREMENTAL", completed_at="2026-03-04T00:00:00Z")
        view2 = self.writer.save_view(run_id="run-2", security_id="US:MRVL", decision_cutoff="2026-03-04T00:00:00Z", facts=[revised], gaps=[], conflicts=[])
        compared = self.reader().compare_views("US:MRVL", self.view1["view_manifest_hash"], view2["view_manifest_hash"])
        self.assertEqual(["REVISED"], [item["status"] for item in compared["changes"]])

    def test_save_view_binds_gate_freshness_to_committed_fact_and_rejects_missing(self):
        delivered = dict(
            self.first, freshness_status="FRESH",
            freshness_policy_version="live-freshness/1.0.0",
        )
        view = self.writer.save_view(
            run_id="run-gate", security_id="US:MRVL",
            decision_cutoff="2026-03-02T00:00:00Z",
            facts=[delivered], gaps=[], conflicts=[],
        )
        self.assertEqual([fact_content_hash(self.first)], view["selected_fact_versions"])
        missing = self.fact(evidence_id="ev-not-persisted", value="999")
        with self.assertRaisesRegex(ResearchMemoryError, "VIEW_FACT_NOT_PERSISTED"):
            self.writer.save_view(
                run_id="run-missing", security_id="US:MRVL",
                decision_cutoff="2026-03-02T00:00:00Z",
                facts=[missing], gaps=[], conflicts=[],
            )
        with self.writer.session() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM research_views WHERE run_id='run-missing'"
            ).fetchone()[0]
        self.assertEqual(0, count)

    def test_missing_view_references_are_counted_and_not_selected_by_default(self):
        broken = dict(self.view1)
        broken.update(
            view_id="research-view:broken:US:MRVL", run_id="broken",
            decision_cutoff="2026-04-01T00:00:00Z",
            selected_fact_versions=["f" * 64],
        )
        broken["view_manifest_hash"] = canonical_hash({
            key: value for key, value in broken.items() if key != "view_manifest_hash"
        })
        with self.writer.session() as connection:
            connection.execute(
                "INSERT INTO research_views VALUES(?,?,?,?,?)",
                (broken["view_manifest_hash"], broken["run_id"], broken["security_id"], broken["decision_cutoff"], json.dumps(broken, sort_keys=True, separators=(",", ":"))),
            )
        default = self.reader().company("US:MRVL")
        self.assertEqual(self.view1["view_manifest_hash"], default["selected_view"]["view_manifest_hash"])
        explicit = self.reader().company("US:MRVL", view_hash=broken["view_manifest_hash"])
        self.assertEqual({
            "reference_count": 1, "resolved_count": 0, "missing_count": 1,
            "invalid_count": 0, "duplicate_count": 0, "mode": "SAVED_VIEW",
            "complete": False,
        }, explicit["view_integrity"])
        self.assertEqual("BROWSER_VIEW_REFERENCE_MISSING", explicit["fact_issues"][0]["code"])

    def test_financial_periods_price_volume_and_empty_pe_are_not_mixed(self):
        def financial(field, value, start, end, *, unit="USD", frame=None):
            return self.fact(
                evidence_id=f"{field}:{start}:{end}", semantic_field=field,
                value=value, unit=unit, as_of=f"{end}T00:00:00Z",
                metadata={
                    "period_start": start, "period_end": end, "context_type": "duration",
                    "fiscal_period": "Q2", "fiscal_year": 2027, "form": "10-Q",
                    "frame": frame, "accession": "0002",
                },
            )
        facts = [
            financial("revenue", "100", "2026-02-01", "2026-05-02", frame="CY2026Q1"),
            financial("revenue", "200", "2026-05-03", "2026-08-01", frame="CY2026Q2"),
            financial("revenue", "300", "2026-02-01", "2026-08-01"),
            self.fact(evidence_id="pe-empty", semantic_field="trailing_pe", value=None, unit="x"),
            self.fact(evidence_id="adjusted", semantic_field="adjusted_close_price", value="20", unit="USD", metadata={"trading_date": "2026-08-01"}),
            self.fact(evidence_id="raw-close", semantic_field="historical_close_price", value="30", unit="USD", metadata={"trading_date": "2026-08-01"}),
            self.fact(evidence_id="volume", semantic_field="share_volume", value="1000", unit="shares", metadata={"trading_date": "2026-08-01"}),
        ]
        metrics = self.reader()._financial_metrics(facts)
        revenue = next(item for item in metrics if item["metric_id"] == "revenue")
        self.assertEqual("200", revenue["latest"]["value"])
        self.assertEqual("单季", revenue["latest"]["period_type"])
        self.assertEqual(["100", "200"], [item["value"] for item in revenue["series"]])
        charts = self.reader()._chart_models(
            facts, [], decision_cutoff="2026-08-02T00:00:00Z", run_id="run",
        )
        indexed = {item["chart_id"]: item for item in charts}
        self.assertEqual(["20"], [item["value"] for item in indexed["price_history"]["data"]])
        self.assertEqual(["1000"], [item["value"] for item in indexed["volume_history"]["data"]])
        self.assertEqual("LIMITED", indexed["trailing_pe_history"]["status"])
        self.assertEqual([], indexed["trailing_pe_history"]["data"])

    def test_disclosure_timeline_prefers_body_and_decodes_form4_without_interpretation(self):
        toc = self.fact(
            evidence_id="risk-toc", semantic_field="risk_factors",
            value="Item 1A. Risk Factors ........ 42", raw_content_hash="b" * 64,
            source_id="sec-document-0001", metadata={
                "period_end": "2026-01-31", "form": "10-K", "accession": "0001",
            },
        )
        body_text = "供应链、客户集中度与产品迭代风险需要持续观察。" * 45
        body = self.fact(
            evidence_id="risk-body", semantic_field="risk_factors",
            value=body_text, raw_content_hash="c" * 64,
            source_id="sec-document-0001", metadata={
                "period_end": "2026-01-31", "form": "10-K", "accession": "0001",
            },
        )
        duplicate = self.fact(
            evidence_id="risk-body-revision", semantic_field="risk_factors",
            value=body_text, raw_content_hash="e" * 64,
            source_id="sec-document-0001",
            source_locator="https://www.sec.gov/Archives/duplicate-risk-body.htm",
            published_at="2026-03-01T01:00:00Z",
            retrieved_at="2026-03-03T00:00:00Z", metadata={
                "period_end": "2026-01-31", "form": "10-K", "accession": "0001",
            },
        )
        ownership = self.fact(
            evidence_id="form4-transaction", semantic_field="ownership_insider_transaction",
            value={
                "instrument_type": "NON_DERIVATIVE", "security_title": "Common Stock",
                "transaction_date": "2026-03-01", "transaction_code": "P",
                "acquired_disposed_code": "A", "shares": "1000",
                "price_per_share": "72.50", "post_transaction_amount": "9000",
                "ownership_nature": "D", "footnote_ids": [],
            },
            unit="reported_transaction", source_id="sec-ownership-0002",
            source_locator="https://www.sec.gov/Archives/example.xml",
            raw_content_hash="d" * 64, as_of="2026-03-01T00:00:00Z",
            published_at="2026-03-02T00:00:00Z",
            metadata={
                "form": "4", "accession": "0002", "transaction_index": 0,
                "owner_name": "Example Insider",
            },
        )
        plan = self.writer.plan(
            "US:MRVL", "sec", "sec_documents", planning_as_of="2026-03-03T00:00:00Z",
        )
        self.writer.ingest_dataset(
            plan=plan, facts=[toc, body, duplicate, ownership], status="FETCHED_INCREMENTAL",
            completed_at="2026-03-03T00:00:00Z",
        )
        view = self.writer.save_view(
            run_id="run-events", security_id="US:MRVL",
            decision_cutoff="2026-03-03T00:00:00Z",
            facts=[self.first, toc, body, duplicate, ownership], gaps=[], conflicts=[],
        )
        model = self.reader().company("US:MRVL", view_hash=view["view_manifest_hash"])
        risk = next(item for item in model["disclosures"] if item["semantic_field"] == "risk_factors")
        self.assertIn("供应链", risk["excerpt"])
        self.assertEqual(2, len(risk["collapsed"]))
        self.assertTrue(any("Item 1A" in item["preview"] for item in risk["collapsed"]))
        exact_duplicate = next(item for item in risk["collapsed"] if item["evidence_id"] == "risk-body")
        self.assertEqual("sec-document-0001", exact_duplicate["source_id"])
        self.assertIn("submissions/example.json", exact_duplicate["source_link"])
        self.assertTrue(exact_duplicate["version_hash"])
        form4 = next(item for item in model["disclosures"] if item["semantic_field"] == "ownership_insider_transaction")
        decoded = {item["label"]: item["value"] for item in form4["transaction"]}
        self.assertIn("公开市场或私人购买", decoded["交易代码"])
        self.assertEqual("1000", decoded["数量"])
        page = ResearchBrowser(self.reader(), ArtifactCatalog()).dispatch(
            "GET", f'/companies/US%3AMRVL?view={view["view_manifest_hash"]}',
            {"Host": "localhost"},
        ).body.decode()
        self.assertIn("披露与公司事件", page)
        self.assertIn("已折叠目录或重复片段 · 2", page)
        self.assertIn("submissions/example.json", page)
        self.assertIn("Example Insider", page)
        self.assertIn("代码 P（公开市场或私人购买）", page)
        self.assertIn("仅解码 SEC 披露字段，不推断交易动机、重要性或投资影响", page)
        self.assertNotIn("acquired_disposed_code", page)
        self.assertNotIn("利好", page)

    def test_company_dimension_reports_are_exactly_bound_and_missing_is_not_absence(self):
        run = self.base / "company-dimension-run"
        event_dir = run / "research" / "reports" / "event"
        industry_dir = run / "research" / "reports" / "industry"
        event_dir.mkdir(parents=True)
        industry_dir.mkdir(parents=True)
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": "2026-03-02T00:00:00Z",
        }))
        event = dimension_report(
            decision_cutoff="2026-03-02T00:00:00Z", run_id="run-1",
            capability="FUNDAMENTAL_EVENT", report_id="dimension-report:event",
            summary="已保存的经营事件解读。",
            evidence_id="ev-revenue",
        )
        evidence_mismatch = dimension_report(
            decision_cutoff="2026-03-02T00:00:00Z", run_id="run-1",
            capability="INDUSTRY_COMPARISON", report_id="dimension-report:industry",
            summary="不应借用的 View 外证据报告。",
        )
        (event_dir / "dimension-report.json").write_text(json.dumps(event))
        (industry_dir / "dimension-report.json").write_text(json.dumps(evidence_mismatch))
        dangling = deepcopy(event)
        dangling["report_id"] = "dimension-report:dangling-claim"
        dangling["claims"][0]["research_claim_refs"] = ["claim-does-not-exist"]
        dangling["report_hash"] = canonical_hash({
            key: value for key, value in dangling.items() if key != "report_hash"
        })
        dangling_dir = run / "research" / "reports" / "dangling"
        dangling_dir.mkdir(parents=True)
        (dangling_dir / "dimension-report.json").write_text(json.dumps(dangling))
        foreign_run = self.base / "foreign-company-dimension-run"
        ownership_dir = foreign_run / "research" / "reports" / "ownership"
        ownership_dir.mkdir(parents=True)
        (foreign_run / "run_manifest.json").write_text(json.dumps({
            "run_id": "foreign-run", "decision_cutoff": "2026-03-02T00:00:00Z",
        }))
        source_mismatch = dimension_report(
            decision_cutoff="2026-03-02T00:00:00Z", run_id="run-1",
            capability="OWNERSHIP_DISCLOSURE", report_id="dimension-report:ownership",
            summary="不应借用的其他来源运行报告。", evidence_id="ev-revenue",
        )
        (ownership_dir / "dimension-report.json").write_text(json.dumps(source_mismatch))
        catalog = ArtifactCatalog(run_dirs=[run, foreign_run])
        model = catalog.company_reports(
            "US:MRVL", "2026-03-02T00:00:00Z", "run-1", ["ev-revenue"],
        )
        indexed = {item["capability"]: item for item in model["items"]}
        self.assertEqual("AVAILABLE", indexed["FUNDAMENTAL_EVENT"]["status"])
        self.assertEqual("BINDING_FAILED", indexed["OWNERSHIP_DISCLOSURE"]["status"])
        self.assertEqual("BINDING_FAILED", indexed["INDUSTRY_COMPARISON"]["status"])
        self.assertEqual("NOT_GENERATED", indexed["RESEARCH_REPORT"]["status"])
        self.assertTrue(any(
            item["code"] == "DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING"
            for item in catalog.issues
        ))
        page = ResearchBrowser(self.reader(), catalog).dispatch(
            "GET", "/companies/US%3AMRVL", {"Host": "localhost"},
        ).body.decode()
        self.assertIn("已保存的经营事件解读", page)
        self.assertIn("公开研报分析 · 未生成", page)
        self.assertIn("不代表相关事件或观点不存在", page)
        self.assertIn("持股与内部人披露分析 · 绑定校验失败", page)
        self.assertIn("行业与同行比较 · 绑定校验失败", page)
        self.assertNotIn("不应借用的其他来源运行报告", page)
        self.assertNotIn("不应借用的 View 外证据报告", page)
        self.assertNotIn("claim-does-not-exist", page)

    def test_report_output_is_allowlisted_and_private_context_removed(self):
        report = self.store_report()
        result = self.reader().report("US:MRVL", "entry-1")
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertIn(report["research_summary"]["summary"], serialized)
        self.assertIn("monitoring_indicators", serialized)
        self.assertNotIn("private question must not render", serialized)
        self.assertNotIn(str(self.root), serialized)
        self.store_report(
            entry_id="entry-0", run_id="run-0", invocation_id="inv-company-0",
            cutoff="2026-02-01T00:00:00Z", report_id="equity-report-0",
            summary="上一版本研究摘要。",
        )
        page = ResearchBrowser(self.reader(), ArtifactCatalog()).dispatch(
            "GET", "/companies/US%3AMRVL/report?entry=entry-1&right=entry-0", {"Host": "localhost"},
        ).body.decode()
        for text in (
            "核心经济逻辑有依据", "上一版本研究摘要", "公司概况与核心问题",
            "业务、竞争与财务", "Thesis 与估值", "催化剂与反证",
            "失效条件与监控", "数据缺口与置信度", "研究假设",
            "收入事实支持当前商业规模判断", "下一份定期报告发布后重评",
            "置信度代表证据支持程度，不是上涨概率",
        ):
            self.assertIn(text, page)
        self.assertNotIn("private question must not render", page)

    def test_report_package_rejects_request_evidence_attachment_and_manifest_drift(self):
        prices = [
            {
                "date": date, "open": value, "high": value, "low": value,
                "close": value, "adjusted_close": value, "volume": "1000",
                "evidence_refs": ["ev-revenue"],
            }
            for date, value in (("2026-02-27", "100"), ("2026-03-02", "101"))
        ]
        visual = build_visual_bundle(
            bundle_id="report-visual", report_id="equity-report-valid-attachment",
            run_id="run-1", security_id="US:MRVL",
            decision_cutoff="2026-03-02T00:00:00Z", daily_prices=prices,
            benchmark_prices=prices, financial_periods=[], valuation_history=None,
        )
        attachment = build_equity_research_package(
            package_id="report-attachment", run_id="run-1", security_id="US:MRVL",
            decision_cutoff="2026-03-02T00:00:00Z", gate_bundle_hash="7" * 64,
            artifacts={"visual_bundle": visual},
        )
        self.store_report(
            entry_id="valid-attachment", report_id="equity-report-valid-attachment",
            package_mutator=lambda package: package.__setitem__("attachment", attachment),
        )
        self.assertEqual(
            "equity-report-valid-attachment",
            self.reader().report("US:MRVL", "valid-attachment")["report"]["report_id"],
        )

        self.store_report(entry_id="wrong-index-status", index_status="COMPLETE")
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_REPORT_PACKAGE_BINDING_INVALID"):
            self.reader().report("US:MRVL", "wrong-index-status")

        def invalid_request(package):
            package["request"]["request_hash"] = "f" * 64
            package["report"]["bindings"]["holding_research_request_hash"] = "f" * 64

        self.store_report(entry_id="bad-request", package_mutator=invalid_request)
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_REPORT_CONTRACT_INVALID"):
            self.reader().report("US:MRVL", "bad-request")

        self.store_report(
            entry_id="bad-evidence",
            package_mutator=lambda package: package.__setitem__("evidence", []),
        )
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_REPORT_EVIDENCE_BINDING_INVALID"):
            self.reader().report("US:MRVL", "bad-evidence")

        self.store_report(
            entry_id="bad-attachment",
            package_mutator=lambda package: package.__setitem__("attachment", {
                "schema_version": "equity-research-attachments/1.0.0",
            }),
        )
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_REPORT_ATTACHMENT_INVALID"):
            self.reader().report("US:MRVL", "bad-attachment")

        wrong_gate_attachment = deepcopy(attachment)
        wrong_gate_attachment["gate_bundle_hash"] = "9" * 64
        wrong_gate_attachment["package_hash"] = canonical_hash({
            key: value for key, value in wrong_gate_attachment.items() if key != "package_hash"
        })
        self.store_report(
            entry_id="wrong-attachment-gate",
            package_mutator=lambda package: package.__setitem__("attachment", wrong_gate_attachment),
        )
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_REPORT_PACKAGE_BINDING_INVALID"):
            self.reader().report("US:MRVL", "wrong-attachment-gate")

        self.store_report(
            entry_id="bad-manifest",
            manifest_mutator=lambda manifest: manifest.__setitem__("evidence_hash", "0" * 64),
        )
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_REPORT_HASH_MISMATCH"):
            self.reader().report("US:MRVL", "bad-manifest")

    def test_corrupt_object_isolated_from_company_facts(self):
        with self.writer.session() as connection:
            connection.execute(
                "UPDATE dataset_state SET state_json=? WHERE security_id='US:MRVL'",
                (json.dumps({"object_ref": "objects/" + "f" * 64, "object_hash": "f" * 64}),),
            )
        detail = self.reader().company("US:MRVL")
        self.assertEqual("MRVL", detail["summary"]["ticker"])
        self.assertTrue(detail["facts"])

    def test_memory_objects_directory_symlink_is_rejected(self):
        outside = self.base / "outside-objects"
        (self.root / "objects").rename(outside)
        (self.root / "objects").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(BrowserDataError, "BROWSER_MEMORY_OBJECTS_SYMLINK_REJECTED"):
            self.reader()

    def test_artifact_exact_and_one_level_discovery_dedupe_and_conflict(self):
        root = self.base / "runs"
        run = root / "run-a"
        nested = root / "group" / "run-hidden"
        run.mkdir(parents=True)
        nested.mkdir(parents=True)
        (run / "run_manifest.json").write_text("{}")
        (nested / "run_manifest.json").write_text("{}")
        snapshot = {
            "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": "2026-09-01T00:00:00Z", "evidence": [], "excluded": [],
            "gaps": [], "events": [], "policy_version": "v1", "policy_hash": "a" * 64,
        }
        snapshot["snapshot_hash"] = canonical_hash(snapshot)
        (run / "official-macro-snapshot.json").write_text(json.dumps(snapshot))
        (nested / "official-macro-snapshot.json").write_text(json.dumps(snapshot))
        market = {
            "schema_version": "market-context-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": "2026-09-01T00:00:00Z", "evidence": [], "gaps": [],
            "events": [], "record_hashes": [],
            "adapter_version": "yahoo-public-market-context/1.0.0",
        }
        market["snapshot_hash"] = canonical_hash(market)
        (run / "market-context-snapshot.json").write_text(json.dumps(market))
        catalog = ArtifactCatalog(run_roots=[root], run_dirs=[run])
        self.assertEqual(1, len(catalog.by_kind("macro_snapshot")))
        self.assertEqual(1, len(catalog.by_kind("market_context_snapshot")))
        self.assertEqual("run-a", catalog.by_kind("macro_snapshot")[0]["source_label"])
        first = run / "research" / "equity-attachments"
        first.mkdir(parents=True)
        for index, payload in enumerate(({"schema_version": "future/1", "artifact_id": "same", "x": 1}, {"schema_version": "future/1", "artifact_id": "same", "x": 2})):
            (first / f"future-{index}.json").write_text(json.dumps(payload))
        # Unknown arbitrary files are outside the bounded candidate names/globs.
        catalog.rescan()
        self.assertFalse(any(item["kind"] == "unsupported" for item in catalog.artifacts))
        self.assertTrue(any(item["code"] == "ARTIFACT_IDENTITY_CONTENT_CONFLICT" for item in catalog.issues))
        self.assertTrue(any(item["code"] == "ARTIFACT_SCHEMA_UNSUPPORTED" for item in catalog.issues))

    def test_artifact_nested_directory_symlink_is_rejected(self):
        run = self.base / "symlink-run"
        source_package = self.base / "outside-source-package"
        (run / "evidence").mkdir(parents=True)
        source_package.mkdir()
        (run / "run_manifest.json").write_text("{}")
        snapshot = {
            "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": "2026-09-01T00:00:00Z", "evidence": [], "excluded": [],
            "gaps": [], "events": [], "policy_version": "v1", "policy_hash": "a" * 64,
        }
        snapshot["snapshot_hash"] = canonical_hash(snapshot)
        (source_package / "official-macro-snapshot.json").write_text(json.dumps(snapshot))
        (run / "evidence" / "source-package").symlink_to(source_package, target_is_directory=True)
        catalog = ArtifactCatalog(run_dirs=[run])
        self.assertFalse(catalog.by_kind("macro_snapshot"))

    def test_provider_coverage_registry_projection_and_field_allowlist(self):
        run = self.base / "coverage-run"
        audit = run / "audit"
        audit.mkdir(parents=True)
        cutoff = "2026-03-02T00:00:00Z"
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        coverage = provider_coverage_fixture(decision_cutoff=cutoff)
        (audit / "provider-coverage.json").write_text(json.dumps(coverage))
        catalog = ArtifactCatalog(run_dirs=[run])

        self.assertEqual(1, len(catalog.by_kind("provider_coverage")))
        overview = catalog.coverage_overview()
        self.assertEqual("AVAILABLE", overview["status"])
        self.assertEqual(
            {"MACRO", "MARKET", "COMPANY"},
            {item["domain"] for item in overview["runs"][0]["domains"]},
        )
        company = catalog.company_coverage("US:MRVL", cutoff, "run-1")
        self.assertEqual("AVAILABLE", company["status"])
        self.assertEqual(
            {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT", "OWNERSHIP_DISCLOSURE", "INDUSTRY_COMPARISON", "OPTIONS_FLOW"},
            {item["target_capability"] for item in company["items"]},
        )
        serialized = json.dumps(company, ensure_ascii=False)
        self.assertNotIn("must-not-render", serialized)
        self.assertNotIn("/private/", serialized)
        self.assertNotIn("ev-option-1", serialized)
        other = catalog.company_coverage("US:OTHER", cutoff, "run-1")
        self.assertEqual("AMBIGUOUS_SECURITY_SCOPE", other["status"])
        wrong_run = catalog.company_coverage("US:MRVL", cutoff, "run-other")
        self.assertNotEqual("AVAILABLE", wrong_run["status"])

    def test_provider_coverage_invalid_unknown_and_symlink_are_isolated(self):
        cutoff = "2026-03-02T00:00:00Z"
        invalid = self.base / "invalid-coverage"
        (invalid / "audit").mkdir(parents=True)
        (invalid / "run_manifest.json").write_text(json.dumps({
            "run_id": "invalid", "decision_cutoff": cutoff,
        }))
        broken = provider_coverage_fixture(decision_cutoff=cutoff)
        broken["coverage_hash"] = "0" * 64
        (invalid / "audit" / "provider-coverage.json").write_text(json.dumps(broken))

        future = self.base / "future-coverage"
        (future / "audit").mkdir(parents=True)
        (future / "run_manifest.json").write_text("{}")
        (future / "audit" / "provider-coverage.json").write_text(json.dumps({
            "schema_version": "research-provider-coverage/2.0.0",
            "artifact_id": "/private/must-not-render",
            "coverage_hash": "f" * 64,
        }))

        outside = self.base / "outside-provider-coverage.json"
        outside.write_text(json.dumps(provider_coverage_fixture(decision_cutoff=cutoff)))
        linked = self.base / "linked-coverage"
        (linked / "audit").mkdir(parents=True)
        (linked / "run_manifest.json").write_text("{}")
        (linked / "audit" / "provider-coverage.json").symlink_to(outside)

        catalog = ArtifactCatalog(run_dirs=[invalid, future, linked])
        self.assertFalse(catalog.by_kind("provider_coverage"))
        self.assertTrue(any(item["code"] == "PROVIDER_COVERAGE_HASH_MISMATCH" for item in catalog.issues))
        self.assertTrue(any(item["code"] == "ARTIFACT_SCHEMA_UNSUPPORTED" for item in catalog.issues))
        self.assertNotIn("/private/must-not-render", json.dumps(catalog.issues))

    def test_evidence_gate_projection_requires_valid_hash_allowlist_and_run_binding(self):
        cutoff = "2026-03-02T00:00:00Z"
        valid = self.base / "valid-gate"
        (valid / "audit").mkdir(parents=True)
        (valid / "evidence").mkdir()
        (valid / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (valid / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        (valid / "evidence" / "gate.json").write_text(json.dumps(
            evidence_gate_fixture(decision_cutoff=cutoff)
        ))

        catalog = ArtifactCatalog(run_dirs=[valid])
        self.assertEqual(1, len(catalog.by_kind("evidence_gate")))
        macro = catalog.macro()["evidence_content"]
        market = catalog.market()["evidence_content"]
        self.assertEqual("AVAILABLE", macro["status"])
        self.assertEqual("AVAILABLE", market["status"])
        serialized = json.dumps({"macro": macro, "market": market}, ensure_ascii=False)
        self.assertIn("CPI 同比", serialized)
        self.assertIn("MRVL260925C00100000", serialized)
        self.assertNotIn("must-not-render", serialized)
        self.assertNotIn("SHOULD_NOT_RENDER", serialized)
        self.assertNotIn("ev-option-1", serialized)

        security_mismatch = self.base / "security-mismatched-gate"
        (security_mismatch / "audit").mkdir(parents=True)
        (security_mismatch / "evidence").mkdir()
        (security_mismatch / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (security_mismatch / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        mismatched_security_gate = evidence_gate_fixture(decision_cutoff=cutoff)
        next(
            item for item in mismatched_security_gate["allowed_evidence"]
            if item["evidence_id"] == "ev-option-1"
        )["security_id"] = "US:AAPL"
        mismatched_security_gate["bundle_hash"] = canonical_hash({
            key: value for key, value in mismatched_security_gate.items() if key != "bundle_hash"
        })
        (security_mismatch / "evidence" / "gate.json").write_text(json.dumps(
            mismatched_security_gate
        ))
        mismatched_options = ArtifactCatalog(run_dirs=[security_mismatch]).market()[
            "evidence_content"
        ]["datasets"]["options_snapshot"]
        self.assertEqual([], mismatched_options)

        unsafe_values = self.base / "unsafe-gate-values"
        (unsafe_values / "audit").mkdir(parents=True)
        (unsafe_values / "evidence").mkdir()
        (unsafe_values / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (unsafe_values / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        unsafe_gate = evidence_gate_fixture(decision_cutoff=cutoff)
        unsafe_flow = next(
            item for item in unsafe_gate["allowed_evidence"]
            if item["evidence_id"] == "ev-flow-1"
        )
        unsafe_flow["value"]["definition"] = {
            "account_context": "NESTED_SECRET",
        }
        unsafe_flow["value"]["provider_direction_label"] = "/Users/private/research.txt"
        unsafe_contract = next(
            item for item in unsafe_gate["allowed_evidence"]
            if item["evidence_id"] == "ev-option-1"
        )
        unsafe_contract["value"]["greeks"]["delta"] = {
            "credentials": "NESTED_GREEK_SECRET",
        }
        unsafe_gate["bundle_hash"] = canonical_hash({
            key: value for key, value in unsafe_gate.items() if key != "bundle_hash"
        })
        (unsafe_values / "evidence" / "gate.json").write_text(json.dumps(unsafe_gate))
        unsafe_market = ArtifactCatalog(run_dirs=[unsafe_values]).market()["evidence_content"]
        unsafe_serialized = json.dumps(unsafe_market, ensure_ascii=False)
        self.assertNotIn("NESTED_SECRET", unsafe_serialized)
        self.assertNotIn("NESTED_GREEK_SECRET", unsafe_serialized)
        self.assertNotIn("/Users/private", unsafe_serialized)

        mismatched = self.base / "mismatched-gate"
        (mismatched / "audit").mkdir(parents=True)
        (mismatched / "evidence").mkdir()
        (mismatched / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (mismatched / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        (mismatched / "evidence" / "gate.json").write_text(json.dumps(
            evidence_gate_fixture(decision_cutoff=cutoff, run_id="run-other")
        ))
        self.assertEqual(
            "BINDING_FAILED",
            ArtifactCatalog(run_dirs=[mismatched]).macro()["evidence_content"]["status"],
        )

        cutoff_mismatch = self.base / "cutoff-mismatched-gate"
        (cutoff_mismatch / "audit").mkdir(parents=True)
        (cutoff_mismatch / "evidence").mkdir()
        (cutoff_mismatch / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (cutoff_mismatch / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        (cutoff_mismatch / "evidence" / "gate.json").write_text(json.dumps(
            evidence_gate_fixture(decision_cutoff="2026-03-03T00:00:00Z")
        ))
        self.assertEqual(
            "BINDING_FAILED",
            ArtifactCatalog(run_dirs=[cutoff_mismatch]).market()["evidence_content"]["status"],
        )

        jointly_wrong = self.base / "jointly-wrong-manifest-binding"
        (jointly_wrong / "audit").mkdir(parents=True)
        (jointly_wrong / "evidence").mkdir()
        (jointly_wrong / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": "2026-03-01T00:00:00Z",
        }))
        (jointly_wrong / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        (jointly_wrong / "evidence" / "gate.json").write_text(json.dumps(
            evidence_gate_fixture(decision_cutoff=cutoff)
        ))
        jointly_wrong_catalog = ArtifactCatalog(run_dirs=[jointly_wrong])
        self.assertEqual("BINDING_FAILED", jointly_wrong_catalog.macro()["coverage"]["status"])
        self.assertNotEqual(
            "AVAILABLE", jointly_wrong_catalog.market()["evidence_content"]["status"],
        )

        missing_manifest_binding = self.base / "missing-manifest-binding"
        (missing_manifest_binding / "audit").mkdir(parents=True)
        (missing_manifest_binding / "evidence").mkdir()
        (missing_manifest_binding / "run_manifest.json").write_text("{}")
        (missing_manifest_binding / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        (missing_manifest_binding / "evidence" / "gate.json").write_text(json.dumps(
            evidence_gate_fixture(decision_cutoff=cutoff)
        ))
        missing_catalog = ArtifactCatalog(run_dirs=[missing_manifest_binding])
        self.assertEqual("BINDING_FAILED", missing_catalog.macro()["coverage"]["status"])
        self.assertNotEqual("AVAILABLE", missing_catalog.macro()["evidence_content"]["status"])

        hash_bound = self.base / "hash-bound-manifest"
        (hash_bound / "audit").mkdir(parents=True)
        (hash_bound / "evidence").mkdir()
        hash_bound_coverage = provider_coverage_fixture(decision_cutoff=cutoff)
        hash_bound_gate = evidence_gate_fixture(decision_cutoff=cutoff)
        (hash_bound / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1",
            "provider_coverage_hash": hash_bound_coverage["coverage_hash"],
            "gate_hash": hash_bound_gate["bundle_hash"],
        }))
        (hash_bound / "audit" / "provider-coverage.json").write_text(json.dumps(
            hash_bound_coverage
        ))
        (hash_bound / "evidence" / "gate.json").write_text(json.dumps(hash_bound_gate))
        hash_bound_catalog = ArtifactCatalog(run_dirs=[hash_bound])
        self.assertEqual("AVAILABLE", hash_bound_catalog.macro()["coverage"]["status"])
        self.assertEqual("AVAILABLE", hash_bound_catalog.macro()["evidence_content"]["status"])
        hash_bound_benchmark = {
            "schema_version": "benchmark-research-snapshot/1.0.0",
            "status": "FROZEN", "benchmark_id": "US:ETF:SPY",
            "benchmark_ticker": "SPY", "gaps": [], "evidence": [],
        }
        hash_bound_benchmark["snapshot_hash"] = canonical_hash(hash_bound_benchmark)
        (hash_bound / "benchmark-snapshot.json").write_text(json.dumps(hash_bound_benchmark))
        hash_bound_with_snapshot = ArtifactCatalog(run_dirs=[hash_bound])
        self.assertEqual("AVAILABLE", hash_bound_with_snapshot.market()["coverage"]["status"])
        self.assertEqual(
            "AVAILABLE", hash_bound_with_snapshot.market()["evidence_content"]["status"],
        )

        bad_hash_bound = self.base / "bad-hash-bound-manifest"
        (bad_hash_bound / "audit").mkdir(parents=True)
        (bad_hash_bound / "evidence").mkdir()
        (bad_hash_bound / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
            "provider_coverage_hash": "f" * 64,
            "gate_hash": hash_bound_gate["bundle_hash"],
        }))
        (bad_hash_bound / "audit" / "provider-coverage.json").write_text(json.dumps(
            hash_bound_coverage
        ))
        (bad_hash_bound / "evidence" / "gate.json").write_text(json.dumps(hash_bound_gate))
        bad_hash_macro = {
            "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": cutoff, "evidence": [], "excluded": [], "gaps": [],
            "events": [], "policy_version": "v1", "policy_hash": "a" * 64,
        }
        bad_hash_macro["snapshot_hash"] = canonical_hash(bad_hash_macro)
        (bad_hash_bound / "official-macro-snapshot.json").write_text(json.dumps(bad_hash_macro))
        bad_hash_catalog = ArtifactCatalog(run_dirs=[bad_hash_bound])
        self.assertEqual("BINDING_FAILED", bad_hash_catalog.market()["coverage"]["status"])
        self.assertEqual("BINDING_FAILED", bad_hash_catalog.macro()["coverage"]["status"])
        self.assertEqual("NOT_SAVED", bad_hash_catalog.coverage_overview()["status"])

        invalid = self.base / "invalid-gate"
        (invalid / "audit").mkdir(parents=True)
        (invalid / "evidence").mkdir()
        (invalid / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (invalid / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        broken = evidence_gate_fixture(decision_cutoff=cutoff)
        broken["bundle_hash"] = "0" * 64
        (invalid / "evidence" / "gate.json").write_text(json.dumps(broken))
        invalid_catalog = ArtifactCatalog(run_dirs=[invalid])
        self.assertFalse(invalid_catalog.by_kind("evidence_gate"))
        self.assertEqual("NOT_SAVED", invalid_catalog.market()["evidence_content"]["status"])
        self.assertTrue(any(
            item["code"] == "EVIDENCE_GATE_HASH_MISMATCH"
            for item in invalid_catalog.issues
        ))

        outside_gate = self.base / "outside-evidence-gate.json"
        outside_gate.write_text(json.dumps(evidence_gate_fixture(decision_cutoff=cutoff)))
        linked = self.base / "linked-gate"
        (linked / "audit").mkdir(parents=True)
        (linked / "evidence").mkdir()
        (linked / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (linked / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        (linked / "evidence" / "gate.json").symlink_to(outside_gate)
        linked_catalog = ArtifactCatalog(run_dirs=[linked])
        self.assertFalse(linked_catalog.by_kind("evidence_gate"))
        self.assertEqual("NOT_SAVED", linked_catalog.macro()["evidence_content"]["status"])

    def test_provider_coverage_binding_and_old_run_empty_state(self):
        cutoff = "2026-03-02T00:00:00Z"
        run = self.base / "coverage-binding-run"
        (run / "audit").mkdir(parents=True)
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        coverage = provider_coverage_fixture(decision_cutoff=cutoff)
        (run / "audit" / "provider-coverage.json").write_text(json.dumps(coverage))
        macro = {
            "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": "2026-03-03T00:00:00Z", "evidence": [], "excluded": [],
            "gaps": [], "events": [], "policy_version": "v1", "policy_hash": "a" * 64,
        }
        macro["snapshot_hash"] = canonical_hash(macro)
        (run / "official-macro-snapshot.json").write_text(json.dumps(macro))
        catalog = ArtifactCatalog(run_dirs=[run])
        self.assertEqual("BINDING_FAILED", catalog.macro()["coverage"]["status"])

        manifest_mismatch = self.base / "coverage-manifest-cutoff-mismatch"
        (manifest_mismatch / "audit").mkdir(parents=True)
        (manifest_mismatch / "run_manifest.json").write_text(json.dumps({
            "run_id": "mismatch", "decision_cutoff": "2026-03-03T00:00:00Z",
        }))
        (manifest_mismatch / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        mismatch_overview = ArtifactCatalog(run_dirs=[manifest_mismatch]).coverage_overview()
        self.assertEqual("NOT_SAVED", mismatch_overview["status"])
        self.assertEqual([], mismatch_overview["runs"])
        self.assertTrue(any(
            item["code"] == "PROVIDER_COVERAGE_BINDING_MISMATCH"
            for item in mismatch_overview["issues"]
        ))

        old = self.base / "old-run-without-coverage"
        old.mkdir()
        (old / "run_manifest.json").write_text(json.dumps({
            "run_id": "old", "decision_cutoff": "2026-02-01T00:00:00Z",
        }))
        old_macro = dict(macro, decision_cutoff="2026-02-01T00:00:00Z")
        old_macro["snapshot_hash"] = canonical_hash({
            key: value for key, value in old_macro.items() if key != "snapshot_hash"
        })
        (old / "official-macro-snapshot.json").write_text(json.dumps(old_macro))
        old_catalog = ArtifactCatalog(run_dirs=[old])
        self.assertEqual("NOT_SAVED", old_catalog.macro()["coverage"]["status"])

        same_cutoff_runs = []
        shared_macro = dict(macro, decision_cutoff=cutoff)
        shared_macro["snapshot_hash"] = canonical_hash({
            key: value for key, value in shared_macro.items() if key != "snapshot_hash"
        })
        for index in (1, 2):
            sibling = self.base / f"same-cutoff-{index}"
            (sibling / "audit").mkdir(parents=True)
            (sibling / "run_manifest.json").write_text(json.dumps({
                "run_id": f"same-{index}", "decision_cutoff": cutoff,
            }))
            (sibling / "official-macro-snapshot.json").write_text(json.dumps(shared_macro))
            sibling_coverage = provider_coverage_fixture(decision_cutoff=cutoff)
            (sibling / "audit" / "provider-coverage.json").write_text(json.dumps(sibling_coverage))
            same_cutoff_runs.append(sibling)
        ambiguous = ArtifactCatalog(run_dirs=same_cutoff_runs)
        self.assertEqual("BINDING_FAILED", ambiguous.macro()["coverage"]["status"])

    def test_identical_coverage_content_remains_bound_to_each_run_and_its_reports(self):
        cutoff = "2026-03-02T00:00:00Z"
        runs = []
        for suffix in ("a", "b"):
            run = self.base / f"identical-coverage-{suffix}"
            (run / "audit").mkdir(parents=True)
            report_dir = run / "research" / "reports" / "options"
            report_dir.mkdir(parents=True)
            run_id = f"run-{suffix}"
            (run / "run_manifest.json").write_text(json.dumps({
                "run_id": run_id, "decision_cutoff": cutoff,
            }))
            (run / "audit" / "provider-coverage.json").write_text(json.dumps(
                provider_coverage_fixture(decision_cutoff=cutoff)
            ))
            report = dimension_report(
                decision_cutoff=cutoff, capability="OPTIONS_FLOW", run_id=run_id,
                schema_version="research-dimension-report/2.0.0",
                report_id=f"dimension-report:options-{suffix}", evidence_id="ev-option-1",
            )
            (report_dir / "dimension-report.json").write_text(json.dumps(report))
            runs.append(run)

        catalog = ArtifactCatalog(run_dirs=runs)
        self.assertEqual(1, len(catalog.by_kind("provider_coverage")))
        overview = catalog.coverage_overview()
        self.assertEqual({"run-a", "run-b"}, {item["run_id"] for item in overview["runs"]})
        for suffix in ("a", "b"):
            model = catalog.company_coverage("US:MRVL", cutoff, f"run-{suffix}")
            self.assertEqual("AVAILABLE", model["status"])
            self.assertEqual(f"run-{suffix}", model["run_id"])
            self.assertEqual(
                [f"dimension-report:options-{suffix}"],
                [
                    item["report_id"] for item in model["related_reports"]
                    if item["capability"] == "OPTIONS_FLOW"
                ],
            )

    def test_three_domain_coverage_and_options_rendering(self):
        cutoff = "2026-03-02T00:00:00Z"
        run = self.base / "three-domain-run"
        report_root = run / "research" / "reports"
        (run / "audit").mkdir(parents=True)
        (run / "evidence").mkdir(parents=True)
        (run / "research" / "precomputed" / "market").mkdir(parents=True)
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        coverage = provider_coverage_fixture(decision_cutoff=cutoff)
        (run / "audit" / "provider-coverage.json").write_text(json.dumps(coverage))
        (run / "evidence" / "gate.json").write_text(json.dumps(
            evidence_gate_fixture(decision_cutoff=cutoff)
        ))
        macro = {
            "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": cutoff, "evidence": [], "excluded": [], "gaps": [],
            "events": [], "policy_version": "v1", "policy_hash": "a" * 64,
        }
        macro["snapshot_hash"] = canonical_hash(macro)
        (run / "official-macro-snapshot.json").write_text(json.dumps(macro))
        benchmark = {
            "schema_version": "benchmark-research-snapshot/1.0.0", "status": "FROZEN",
            "benchmark_id": "US:ETF:SPY", "benchmark_ticker": "SPY", "gaps": [],
            "evidence": [],
        }
        benchmark["snapshot_hash"] = canonical_hash(benchmark)
        (run / "benchmark-snapshot.json").write_text(json.dumps(benchmark))
        for name, capability, evidence_id in (
            ("macro", "MACRO_CONTEXT", "ev-dot-1"),
            ("market", "MARKET_STATE", "ev-fed-1"),
            ("options", "OPTIONS_FLOW", "ev-option-1"),
        ):
            directory = report_root / name
            directory.mkdir(parents=True)
            report = dimension_report(
                decision_cutoff=cutoff, capability=capability, run_id="run-1",
                schema_version="research-dimension-report/2.0.0",
                report_id=f"dimension-report:{name}", evidence_id=evidence_id,
            )
            (directory / "dimension-report.json").write_text(json.dumps(report))
        wrong_options = report_root / "wrong-options"
        wrong_options.mkdir(parents=True)
        (wrong_options / "dimension-report.json").write_text(json.dumps(dimension_report(
            decision_cutoff=cutoff, capability="OPTIONS_FLOW", run_id="run-1",
            schema_version="research-dimension-report/2.0.0",
            report_id="dimension-report:wrong-options", evidence_id="ev-option-1",
            security_id="US:OTHER",
        )))

        catalog = ArtifactCatalog(run_dirs=[run])
        application = ResearchBrowser(self.reader(), catalog)
        overview = application.dispatch("GET", "/", {"Host": "localhost"}).body.decode()
        macro_page = application.dispatch("GET", "/macro", {"Host": "localhost"}).body.decode()
        market_page = application.dispatch("GET", "/market", {"Host": "localhost"}).body.decode()
        company_page = application.dispatch("GET", "/companies/US%3AMRVL", {"Host": "localhost"}).body.decode()

        self.assertIn("三域数据覆盖", overview)
        self.assertIn("重新读取本地资料", overview)
        self.assertIn("dot_plot", macro_page)
        self.assertIn("economic_calendar", macro_page)
        self.assertIn("macro_history", macro_page)
        self.assertIn("共享美国宏观环境", macro_page)
        self.assertIn("CPI 同比", macro_page)
        self.assertIn("3.4%", macro_page)
        self.assertIn("美国 CPI 同比", macro_page)
        self.assertIn("4.125%", macro_page)
        self.assertIn("共享宏观环境", macro_page)
        self.assertIn("fedwatch_expectations", market_page)
        self.assertIn("option_market_statistics", market_page)
        self.assertIn("options_snapshot", market_page)
        self.assertIn("options_underlying_context", market_page)
        self.assertIn("vendor_money_flow", market_page)
        self.assertIn("共享市场环境", market_page)
        self.assertIn("53.1%", market_page)
        self.assertIn("MRVL260925C00100000", market_page)
        self.assertIn("67.922%", market_page)
        self.assertIn("供应商资金流分类", market_page)
        self.assertIn("查看 Capture / Gate / Delivered 与来源审计", market_page)
        self.assertNotIn("SHOULD_NOT_RENDER", market_page)
        self.assertIn("dimension-report:options", market_page)
        self.assertNotIn("dimension-report:wrong-options", market_page)
        self.assertIn("实际研究使用未评估", market_page)
        self.assertIn("Evidence 已被报告引用", market_page)
        self.assertIn("financial_history", company_page)
        self.assertIn("NO_GATE_EVIDENCE", company_page)
        self.assertIn("SOURCE_LIMITED", company_page)
        self.assertIn("NOT_ATTEMPTED", company_page)
        self.assertIn("institutional_ownership", company_page)
        self.assertIn("analyst_expectations", company_page)
        combined = overview + macro_page + market_page + company_page
        self.assertNotIn("must-not-render", combined)
        self.assertNotIn("/private/must-not-render", combined)
        self.assertNotIn("ev-option-1", combined)

    def test_macro_full_size_gate_projection_renders_values_not_coverage_placeholders(self):
        cutoff = "2026-03-02T00:00:00Z"
        run = self.base / "full-size-macro-gate"
        (run / "audit").mkdir(parents=True)
        (run / "evidence").mkdir()
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))

        base_gate = evidence_gate_fixture(decision_cutoff=cutoff)
        templates = {
            item["evidence_id"]: item
            for item in base_gate["allowed_evidence"]
        }
        dot_facts = []
        for index in range(12):
            item = deepcopy(templates["ev-dot-1"])
            item["evidence_id"] = f"ev-dot-{index}"
            item["semantic_field"] = f"moomoo_dot_plot:{index}"
            item["value"] = {
                "year": 2026 + index // 4, "rate": 3.5 + index * 0.125,
                "vote_count": index + 1, "median_rate": 4.125,
                "is_median": index in {3, 7, 11}, "current_rate": 3.88,
            }
            dot_facts.append(item)
        calendar_facts = []
        for index in range(100):
            item = deepcopy(templates["ev-calendar-1"])
            item["evidence_id"] = f"ev-calendar-{index}"
            item["semantic_field"] = f"moomoo_economic_calendar:event-{index}"
            item["value"] = {
                "title": f"美国宏观事件 {index + 1}", "country": "US",
                "timestamp": 1772409600 + index * 3600, "star": index % 3 + 1,
                "actual": str(index), "consensus": str(index - 1), "previous": str(index - 2),
            }
            calendar_facts.append(item)
        history_definitions = (
            ("moomoo_us_cpi_yoy", "CPI 同比"),
            ("moomoo_us_core_cpi_yoy", "核心 CPI 同比"),
            ("moomoo_us_pce_yoy", "PCE 同比"),
            ("moomoo_us_ppi_yoy", "PPI 同比"),
            ("moomoo_us_unemployment_rate_vendor", "失业率"),
            ("moomoo_us_nonfarm_payrolls_vendor", "非农就业人数"),
            ("moomoo_us_retail_sales_mom", "零售销售环比"),
            ("moomoo_us_federal_funds_rate_vendor", "联邦基金利率"),
        )
        history_facts = []
        for series_index, (prefix, label) in enumerate(history_definitions):
            for period in range(24):
                item = deepcopy(templates["ev-macro-1"])
                item["evidence_id"] = f"ev-macro-{series_index}-{period}"
                item["semantic_field"] = f"{prefix}:{period}"
                item["as_of"] = f"2025-{period % 12 + 1:02d}-{series_index + 1:02d}T00:00:00Z"
                item["value"] = {
                    "label": label, "actual": 0.01 + period / 1000,
                    "consensus": 0.01, "previous": 0.009,
                    "unit_type": "PERCENT", "indicator_id": f"series-{series_index}",
                }
                history_facts.append(item)
        macro_facts = dot_facts + calendar_facts + history_facts
        retained = [
            item for item in base_gate["allowed_evidence"]
            if item["evidence_id"] not in {"ev-dot-1", "ev-calendar-1", "ev-macro-1"}
        ]
        base_gate["allowed_evidence"] = retained + macro_facts
        base_gate["allowed_evidence_ids"] = [
            item["evidence_id"] for item in base_gate["allowed_evidence"]
        ]
        base_gate["bundle_hash"] = canonical_hash({
            key: value for key, value in base_gate.items() if key != "bundle_hash"
        })
        (run / "evidence" / "gate.json").write_text(json.dumps(base_gate))

        coverage = provider_coverage_fixture(decision_cutoff=cutoff)
        evidence_ids = {
            "dot_plot": [item["evidence_id"] for item in dot_facts],
            "economic_calendar": [item["evidence_id"] for item in calendar_facts],
            "macro_history": [item["evidence_id"] for item in history_facts],
        }
        for provider in coverage["providers"]:
            for observation in provider["dataset_observations"]:
                if observation["dataset"] in evidence_ids:
                    observation["evidence_ids"] = evidence_ids[observation["dataset"]]
        coverage["coverage_hash"] = canonical_hash({
            key: value for key, value in coverage.items() if key != "coverage_hash"
        })
        (run / "audit" / "provider-coverage.json").write_text(json.dumps(coverage))

        catalog = ArtifactCatalog(run_dirs=[run])
        content = catalog.macro()["evidence_content"]
        self.assertEqual(12, len(content["datasets"]["dot_plot"]))
        self.assertEqual(100, len(content["datasets"]["economic_calendar"]))
        self.assertEqual(192, len(content["datasets"]["macro_history"]))
        page = ResearchBrowser(self.reader(), catalog).dispatch(
            "GET", "/macro", {"Host": "localhost"},
        ).body.decode()
        self.assertIn("查看 8 组历史趋势", page)
        self.assertIn("经济日历 · 100 条冻结事件", page)
        self.assertIn("美国宏观事件 100", page)
        self.assertIn("4.125%", page)

    def test_options_reports_reject_cross_security_evidence_and_show_scope(self):
        cutoff = "2026-03-02T00:00:00Z"
        run = self.base / "options-security-binding"
        (run / "audit").mkdir(parents=True)
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        coverage = provider_coverage_fixture(decision_cutoff=cutoff)
        coverage["providers"][0]["dataset_observations"].append({
            "security_id": "US:AAPL", "dataset": "options_snapshot", "status": "PARTIAL",
            "failure_code": None, "checked_at": cutoff, "as_of": cutoff,
            "evidence_ids": ["ev-option-aapl"], "limitations": [],
        })
        coverage["coverage_hash"] = canonical_hash({
            key: value for key, value in coverage.items() if key != "coverage_hash"
        })
        (run / "audit" / "provider-coverage.json").write_text(json.dumps(coverage))
        for name, evidence_id in (("valid", "ev-option-1"), ("cross-security", "ev-option-aapl")):
            report_dir = run / "research" / "reports" / name
            report_dir.mkdir(parents=True)
            report = dimension_report(
                decision_cutoff=cutoff, capability="OPTIONS_FLOW", run_id="run-1",
                schema_version="research-dimension-report/2.0.0",
                report_id=f"dimension-report:{name}", evidence_id=evidence_id,
                security_id="US:MRVL",
            )
            (report_dir / "dimension-report.json").write_text(json.dumps(report))
        mixed_dir = run / "research" / "reports" / "mixed-security"
        mixed_dir.mkdir(parents=True)
        mixed = dimension_report(
            decision_cutoff=cutoff, capability="OPTIONS_FLOW", run_id="run-1",
            schema_version="research-dimension-report/2.0.0",
            report_id="dimension-report:mixed-security", evidence_id="ev-option-1",
            security_id="US:MRVL",
        )
        mixed["claims"][0]["evidence_refs"].append("ev-option-aapl")
        mixed = finalize_research_dimension_report(mixed)
        (mixed_dir / "dimension-report.json").write_text(json.dumps(mixed))

        catalog = ArtifactCatalog(run_dirs=[run])
        option_reports = catalog.market()["option_reports"]
        self.assertEqual(
            ["dimension-report:valid"],
            [item["value"]["report_id"] for item in option_reports],
        )
        page = ResearchBrowser(self.reader(), catalog).dispatch(
            "GET", "/market", {"Host": "localhost"},
        ).body.decode()
        self.assertIn("dimension-report:valid", page)
        self.assertNotIn("dimension-report:cross-security", page)
        self.assertNotIn("dimension-report:mixed-security", page)
        self.assertIn("适用证券", page)
        self.assertIn("US:MRVL", page)
        self.assertIn("US:AAPL", page)

    def test_macro_market_and_shared_report_render_from_saved_artifacts(self):
        run = self.base / "frozen-run"
        report_dir = run / "research" / "reports" / "macro"
        report_dir.mkdir(parents=True)
        (run / "run_manifest.json").write_text("{}")
        macro = {
            "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": "2026-09-01T00:00:00Z", "excluded": [], "gaps": [], "events": [],
            "policy_version": "v1", "policy_hash": "a" * 64,
            "evidence": [
                {"semantic_field": "us_cpi_all_items", "value": "324.1", "unit": "index_1982_84_100", "as_of": "2026-07-31T00:00:00Z"},
                {"semantic_field": "us_unemployment_rate", "value": "4.2", "unit": "percent", "as_of": "2026-07-31T00:00:00Z"},
                {"semantic_field": "us_treasury_10y_yield", "value": "4.1", "unit": "percent", "as_of": "2026-08-31T00:00:00Z"},
            ],
        }
        macro["snapshot_hash"] = canonical_hash(macro)
        (run / "official-macro-snapshot.json").write_text(json.dumps(macro))
        benchmark = {
            "schema_version": "benchmark-research-snapshot/1.0.0", "status": "FROZEN",
            "benchmark_id": "US:ETF:SPY", "benchmark_ticker": "SPY", "gaps": [],
            "evidence": [
                {"semantic_field": "historical_close_price", "value": "500", "as_of": "2026-08-30T20:00:00Z", "metadata": {"trading_date": "2026-08-30"}},
                {"semantic_field": "historical_close_price", "value": "505", "as_of": "2026-08-31T20:00:00Z", "metadata": {"trading_date": "2026-08-31"}},
            ],
        }
        benchmark["snapshot_hash"] = canonical_hash(benchmark)
        (run / "benchmark-snapshot.json").write_text(json.dumps(benchmark))
        calculation = {
            "schema_version": "market-state-calculation/1.0.0", "artifact_id": "market:spy",
            "market_id": "US:ETF:SPY", "as_of": "2026-08-31T20:00:00Z", "price_basis": "adjusted_close",
            "windows": [{"window_sessions": 20, "status": "INSUFFICIENT_HISTORY", "available_sessions": 2, "metrics": None, "reason": "需要至少 21 个交易日。"}],
            "evidence_fact_ids": [],
        }
        calculation["artifact_hash"] = canonical_hash(calculation)
        precomputed = run / "research" / "precomputed" / "market"
        precomputed.mkdir(parents=True)
        (precomputed / "market-state-calculation.json").write_text(json.dumps(calculation))
        report = dimension_report()
        (report_dir / "dimension-report.json").write_text(json.dumps(report))
        later_run = self.base / "frozen-run-later"
        later_run.mkdir()
        (later_run / "run_manifest.json").write_text("{}")
        later_macro = dict(macro, decision_cutoff="2026-09-02T00:00:00Z", evidence=[
            {"semantic_field": "us_cpi_all_items", "value": "325.0", "unit": "index_1982_84_100", "as_of": "2026-08-31T00:00:00Z"},
        ])
        later_macro["snapshot_hash"] = canonical_hash({
            key: value for key, value in later_macro.items() if key != "snapshot_hash"
        })
        (later_run / "official-macro-snapshot.json").write_text(json.dumps(later_macro))
        catalog = ArtifactCatalog(run_dirs=[run, later_run])
        app = ResearchBrowser(self.reader(), catalog)
        macro_page = app.dispatch("GET", "/macro", {"Host": "localhost"}).body.decode()
        market_page = app.dispatch("GET", "/market", {"Host": "localhost"}).body.decode()
        self.assertIn("CPI 指数", macro_page)
        self.assertIn("325.0", macro_page)
        old_macro = next(item for item in catalog.by_kind("macro_snapshot") if item["value"]["decision_cutoff"] == "2026-09-01T00:00:00Z")
        old_page = app.dispatch(
            "GET", f'/macro?version={old_macro["content_hash"]}', {"Host": "localhost"},
        ).body.decode()
        self.assertIn("324.1", old_page)
        self.assertNotIn("325.0", old_page)
        self.assertIn("SPY 日线", market_page)
        self.assertIn("需要至少 21 个交易日", market_page)
        self.assertNotIn("dimension-report:macro-market", macro_page)
        self.assertIn("dimension-report:macro-market", old_page)
        self.assertIn("dimension-report:macro-market", market_page)
        self.assertIn("LEGACY_COMBINED_COVERAGE", old_page)
        self.assertIn("LEGACY_COMBINED_COVERAGE", market_page)

    def test_same_basename_runs_do_not_cross_bind_reports(self):
        left = self.base / "left" / "same-run"
        right = self.base / "right" / "same-run"
        (left / "research" / "reports" / "macro").mkdir(parents=True)
        right.mkdir(parents=True)
        (left / "run_manifest.json").write_text("{}")
        (right / "run_manifest.json").write_text("{}")
        snapshots = []
        for run, cutoff, cpi in (
            (left, "2026-09-01T00:00:00Z", "324.1"),
            (right, "2026-09-02T00:00:00Z", "325.0"),
        ):
            value = {
                "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
                "decision_cutoff": cutoff, "excluded": [], "gaps": [], "events": [],
                "policy_version": "v1", "policy_hash": "a" * 64,
                "evidence": [{"semantic_field": "us_cpi_all_items", "value": cpi, "as_of": cutoff}],
            }
            value["snapshot_hash"] = canonical_hash(value)
            (run / "official-macro-snapshot.json").write_text(json.dumps(value))
            snapshots.append(value)
        (left / "research" / "reports" / "macro" / "dimension-report.json").write_text(
            json.dumps(dimension_report(decision_cutoff="2026-09-01T00:00:00Z"))
        )
        catalog = ArtifactCatalog(run_dirs=[left, right])
        left_item = next(item for item in catalog.by_kind("macro_snapshot") if item["value"]["decision_cutoff"] == "2026-09-01T00:00:00Z")
        right_item = next(item for item in catalog.by_kind("macro_snapshot") if item["value"]["decision_cutoff"] == "2026-09-02T00:00:00Z")
        self.assertEqual(1, len(catalog.macro(left_item["content_hash"])["reports"]))
        self.assertFalse(catalog.macro(right_item["content_hash"])["reports"])
        self.assertNotEqual(left_item["source_ids"], right_item["source_ids"])

    def test_macro_market_reject_mismatched_bindings_and_evidence(self):
        run = self.base / "binding-run"
        report_dir = run / "research" / "reports" / "macro"
        precomputed = run / "research" / "precomputed" / "market"
        report_dir.mkdir(parents=True)
        precomputed.mkdir(parents=True)
        (run / "run_manifest.json").write_text("{}")
        macro = {
            "schema_version": "official-macro-snapshot/1.0.0", "status": "FROZEN",
            "decision_cutoff": "2026-09-01T00:00:00Z", "excluded": [], "gaps": [],
            "events": [], "policy_version": "v1", "policy_hash": "a" * 64, "evidence": [],
        }
        macro["snapshot_hash"] = canonical_hash(macro)
        (run / "official-macro-snapshot.json").write_text(json.dumps(macro))
        benchmark = {
            "schema_version": "benchmark-research-snapshot/1.0.0", "status": "FROZEN",
            "benchmark_id": "US:ETF:SPY", "benchmark_ticker": "SPY", "gaps": [],
            "evidence": [{
                "evidence_id": "bench-1", "semantic_field": "historical_close_price",
                "value": "500", "as_of": "2026-08-31T20:00:00Z",
                "metadata": {"trading_date": "2026-08-31"},
            }],
        }
        benchmark["snapshot_hash"] = canonical_hash(benchmark)
        (run / "benchmark-snapshot.json").write_text(json.dumps(benchmark))
        calculation = {
            "schema_version": "market-state-calculation/1.0.0", "artifact_id": "market:spy",
            "market_id": "US:ETF:SPY", "as_of": "2026-08-31T20:00:00Z",
            "price_basis": "adjusted_close", "windows": [], "evidence_fact_ids": ["wrong-benchmark-fact"],
        }
        calculation["artifact_hash"] = canonical_hash(calculation)
        (precomputed / "market-state-calculation.json").write_text(json.dumps(calculation))
        (report_dir / "dimension-report.json").write_text(json.dumps(
            dimension_report(decision_cutoff="2026-09-02T00:00:00Z")
        ))
        catalog = ArtifactCatalog(run_dirs=[run])
        self.assertFalse(catalog.macro()["reports"])
        market = catalog.market()
        self.assertFalse(market["calculations"])
        self.assertFalse(market["reports"])
        self.assertTrue(any(item["code"] == "ARTIFACT_BINDING_MISMATCH" for item in market["issues"]))

    def test_company_uses_only_exact_view_cutoff_frozen_visual_attachment(self):
        run = self.base / "frozen-company-run"
        attachment_dir = run / "research" / "equity-attachments"
        attachment_dir.mkdir(parents=True)
        (run / "run_manifest.json").write_text("{}")
        prices = [
            {
                "date": "2026-02-27", "open": "99", "high": "102", "low": "98",
                "close": "100", "adjusted_close": "100", "volume": "1000",
                "evidence_refs": ["ev-price-1"],
            },
            {
                "date": "2026-03-02", "open": "100", "high": "104", "low": "99",
                "close": "103", "adjusted_close": "103", "volume": "1200",
                "evidence_refs": ["ev-price-2"],
            },
        ]
        visual = build_visual_bundle(
            bundle_id="visual-mrvl", report_id="report-mrvl", run_id="run-1",
            security_id="US:MRVL", decision_cutoff="2026-03-02T00:00:00Z",
            daily_prices=prices,
            benchmark_prices=[dict(item, evidence_refs=[f"ev-benchmark-{index}"]) for index, item in enumerate(prices)],
            financial_periods=[], valuation_history=None,
        )
        package = build_equity_research_package(
            package_id="package-mrvl", run_id="run-1", security_id="US:MRVL",
            decision_cutoff="2026-03-02T00:00:00Z", gate_bundle_hash="a" * 64,
            artifacts={"visual_bundle": visual},
        )
        (attachment_dir / "mrvl.json").write_text(json.dumps(package))
        catalog = ArtifactCatalog(run_dirs=[run])
        selected = catalog.company_visuals("US:MRVL", "2026-03-02T00:00:00Z", "run-1")
        self.assertEqual("AVAILABLE", selected["status"])
        self.assertEqual("visual-mrvl", selected["bundle_id"])
        self.assertIsNone(catalog.company_visuals("US:MRVL", "2026-03-03T00:00:00Z", "run-1"))
        self.assertIsNone(catalog.company_visuals("US:MRVL", "2026-03-02T00:00:00Z", "other-run"))
        page = ResearchBrowser(self.reader(), catalog).dispatch(
            "GET", "/companies/US%3AMRVL", {"Host": "localhost"},
        ).body.decode()
        self.assertIn("已校验并采用", page)
        self.assertIn("日 K、成交量与均线", page)

    def test_application_rejects_host_and_escapes_source_text(self):
        application = ResearchBrowser(self.reader(), ArtifactCatalog())
        rejected = application.dispatch("GET", "/", {"Host": "evil.example"})
        self.assertEqual(403, rejected.status)
        page = application.dispatch("GET", "/companies?q=%3Cscript%3Ealert%281%29%3C%2Fscript%3E", {"Host": "127.0.0.1:8765"})
        text = page.body.decode()
        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        traversal = application.dispatch("GET", "/companies/..%2F..%2Fetc%2Fpasswd", {"Host": "localhost"})
        self.assertEqual(404, traversal.status)

    def test_http_server_security_headers_and_rescan(self):
        application = ResearchBrowser(self.reader(), ArtifactCatalog())
        self.assertEqual(303, application.dispatch(
            "POST", "/rescan",
            {"Host": "localhost", "Origin": "null", "Sec-Fetch-Site": "same-origin"},
        ).status)
        self.assertEqual(403, application.dispatch(
            "POST", "/rescan",
            {"Host": "localhost", "Origin": "null", "Sec-Fetch-Site": "cross-site"},
        ).status)
        server = build_server(application, port=0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
            self.assertEqual("READY", json.loads(response.read())["status"])
            connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
            connection.request("POST", "/rescan", headers={"Origin": "https://evil.example"})
            response = connection.getresponse()
            self.assertEqual(403, response.status)
            response.read()
            connection.close()
            with mock.patch.object(
                application.artifacts, "rescan", wraps=application.artifacts.rescan,
            ) as rescan:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=3,
                )
                connection.request(
                    "POST", "/rescan",
                    headers={"Origin": f"http://127.0.0.1:{server.server_address[1]}"},
                )
                response = connection.getresponse()
                self.assertEqual(303, response.status)
                self.assertEqual("/", response.headers["Location"])
                response.read()
                connection.close()
                rescan.assert_called_once_with()
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    def test_browsing_and_local_rescan_do_not_modify_memory_or_run(self):
        def tree_hash(root: Path) -> str:
            digest = hashlib.sha256()
            # SQLite 的只读 WAL 打开可能创建空 -wal/-shm 协调文件；持久化数据库与对象必须不变。
            for path in sorted(
                item for item in root.rglob("*")
                if item.is_file()
                and not item.name.endswith((".sqlite3-shm", ".sqlite3-wal"))
            ):
                digest.update(str(path.relative_to(root)).encode())
                digest.update(path.read_bytes())
            return digest.hexdigest()

        run = self.base / "read-only-coverage-run"
        (run / "audit").mkdir(parents=True)
        cutoff = "2026-03-02T00:00:00Z"
        (run / "run_manifest.json").write_text(json.dumps({
            "run_id": "run-1", "decision_cutoff": cutoff,
        }))
        (run / "audit" / "provider-coverage.json").write_text(json.dumps(
            provider_coverage_fixture(decision_cutoff=cutoff)
        ))
        memory_before, run_before = tree_hash(self.root), tree_hash(run)
        application = ResearchBrowser(self.reader(), ArtifactCatalog(run_dirs=[run]))
        for path in ("/", "/macro", "/market", "/companies", "/companies/US%3AMRVL"):
            self.assertEqual(200, application.dispatch("GET", path, {"Host": "localhost"}).status)
        self.assertEqual(303, application.dispatch(
            "POST", "/rescan", {"Host": "localhost", "Origin": "http://localhost:8765"},
        ).status)
        self.assertEqual(memory_before, tree_hash(self.root))
        self.assertEqual(run_before, tree_hash(run))

    def test_concurrent_writer_commits_complete_transaction(self):
        reader = self.reader()
        added = self.fact(
            evidence_id="ev-second", semantic_field="assets", value="200",
            retrieved_at="2026-03-04T00:00:00Z", published_at="2026-03-03T00:00:00Z",
            raw_content_hash="c" * 64, metadata={"period_end": "2026-01-31"},
        )

        def write() -> None:
            plan = self.writer.plan("US:MRVL", "sec", "sec_companyfacts", planning_as_of="2026-03-04T00:00:00Z")
            self.writer.ingest_dataset(plan=plan, facts=[added], status="FETCHED_INCREMENTAL", completed_at="2026-03-04T00:00:00Z")

        with ThreadPoolExecutor(max_workers=2) as pool:
            reads = pool.submit(lambda: [reader.list_companies(), reader.company("US:MRVL")])
            write_result = pool.submit(write)
            reads.result(timeout=5)
            write_result.result(timeout=5)
        with self.writer.session() as connection:
            self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM fact_versions").fetchone()[0])
        # 最新 View 仍绑定旧版本；浏览器不会把尚未保存到 View 的事实混进去。
        self.assertEqual(1, len(reader.company("US:MRVL", view_hash=None)["facts"]))

    def test_new_security_appears_without_browser_configuration_change(self):
        fact = self.fact(
            evidence_id="ev-test", security_id="US:TEST", value="42",
            retrieved_at="2026-03-05T00:00:00Z", published_at="2026-03-05T00:00:00Z",
            raw_content_hash="d" * 64,
        )
        plan = self.writer.plan("US:TEST", "sec", "sec_companyfacts", planning_as_of="2026-03-05T00:00:00Z")
        self.writer.ingest_dataset(plan=plan, facts=[fact], status="FETCHED_BOOTSTRAP", completed_at="2026-03-05T00:00:00Z")
        self.writer.save_view(run_id="run-test", security_id="US:TEST", decision_cutoff="2026-03-05T00:00:00Z", facts=[fact], gaps=[], conflicts=[])
        result = self.reader().list_companies(query="TEST")
        self.assertEqual(1, result["total"])
        self.assertEqual("TEST", result["items"][0]["ticker"])

    def test_offline_reference_repair_is_backed_up_audited_and_idempotent(self):
        root = self.base / "repair-memory"
        root.mkdir()
        writer = ResearchMemory(root)
        portfolio = {
            "schema_version": "live-portfolio/1.0.0", "base_currency": "USD",
            "portfolio_complete": True, "synthetic_portfolio": True,
            "source_id": "synthetic-input", "as_of": "2026-09-10T00:00:00Z",
            "retrieved_at": "2026-09-10T00:00:00Z", "cash": 100,
            "holding_horizon": "6 months", "research_question": "test",
            "mandate": {"version": "synthetic/1", "max_position_weight": 0.6, "minimum_cash_weight": 0.1},
            "positions": [{"security_id": "TEST", "ticker": "TEST", "exchange": "XNAS", "share_class": "common", "quantity": 10, "cost_basis": 1}],
            "focus_security_id": "TEST",
        }
        access = {
            "schema_version": "live-source-access/1.0.0", "provider": "yahoo",
            "client_version": "synthetic/1", "adapter_version": "synthetic/1",
            "status": "AUTHORIZED", "purpose": "personal-research",
            "terms_url": "synthetic-test-only", "checked_at": "2026-09-10T00:00:00Z",
            "free_features": ["synthetic"], "limitations": ["synthetic"],
            "domains": ["example.invalid"], "request_budget": 1,
        }
        raw = {
            "schema_version": "live-fact/1.0.0", "evidence_id": "price",
            "security_id": "TEST", "semantic_field": "close_price", "value": "20",
            "unit": "USD", "currency": "USD", "source_id": "synthetic-market",
            "source_type": "yahoo", "source_locator": "synthetic",
            "source_version": "synthetic/1", "as_of": "2026-09-09T20:00:00Z",
            "published_at": "2026-09-09T20:00:00Z", "published_at_policy": "synthetic-close",
            "retrieved_at": "2026-09-10T00:00:00Z", "raw_content_hash": "a" * 64,
            "kind": "price", "usage": "current",
            "metadata": {"price_basis": "provider_close", "calendar_version": "synthetic-calendar/1", "calendar_hash": "c" * 64},
            "parent_ids": [], "parent_hashes": [],
        }
        snapshot = freeze_snapshot(
            snapshot_id="synthetic", portfolio=portfolio,
            request_started_at="2026-09-10T00:00:00Z",
            decision_cutoff="2026-09-10T01:00:00Z", facts=[raw],
            source_access=[access], raw_records=[], collection_events=[], gaps=[],
        )
        plan = writer.plan("TEST", "market", "current_snapshot", planning_as_of="2026-09-10T01:00:00Z")
        writer.ingest_dataset(
            plan=plan, facts=[raw], status="FETCHED_BOOTSTRAP",
            completed_at="2026-09-10T01:00:00Z",
        )
        writer.store_snapshot_bundle(
            security_id="TEST", portfolio=portfolio, snapshot=snapshot,
            calendar={"version": "synthetic-calendar/1", "content_hash": "c" * 64},
        )
        delivered = dict(raw, freshness_status="FRESH", freshness_policy_version="live-freshness/1.0.0")
        old = {
            "schema_version": "company-research-view/1.0.0", "view_id": "research-view:old:TEST",
            "run_id": "run-old", "security_id": "TEST", "decision_cutoff": "2026-09-10T01:00:00Z",
            "selected_fact_versions": [fact_content_hash(delivered)],
            "checkpoint_revisions": {"current_snapshot": 1}, "coverage": ["current_snapshot"],
            "gaps": [], "conflicts": [], "policy_version": "company-research-dataset-policy/1.0.0",
        }
        old["view_manifest_hash"] = canonical_hash(old)
        with writer.session() as connection:
            connection.execute(
                "INSERT INTO research_views VALUES(?,?,?,?,?)",
                (old["view_manifest_hash"], old["run_id"], old["security_id"], old["decision_cutoff"], json.dumps(old, sort_keys=True, separators=(",", ":"))),
            )
            checkpoint_before = connection.execute("SELECT revision FROM dataset_state WHERE security_id='TEST'").fetchone()[0]
        inspected = inspect_view_references(root, security_id="TEST")
        self.assertEqual(1, inspected["incomplete_view_count"])
        self.assertTrue(inspected["views"][0]["repairable"])
        backup = self.base / "repair-backup"
        repaired = apply_view_reference_repairs(root, security_id="TEST", backup_root=backup)
        self.assertEqual("REPAIRED", repaired["status"])
        self.assertTrue((backup / "research-memory.sqlite3").is_file())
        self.assertTrue(any((root / "repairs").iterdir()))
        with writer.session() as connection:
            checkpoint_after = connection.execute("SELECT revision FROM dataset_state WHERE security_id='TEST'").fetchone()[0]
            view_count = connection.execute("SELECT COUNT(*) FROM research_views").fetchone()[0]
        self.assertEqual(checkpoint_before, checkpoint_after)
        self.assertEqual(2, view_count)
        second = apply_view_reference_repairs(root, security_id="TEST", backup_root=self.base / "unused-backup")
        self.assertEqual("NO_CHANGES", second["status"])
        with writer.session() as connection:
            self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM research_views").fetchone()[0])

        transaction_root = self.base / "repair-transaction-failure"
        shutil.copytree(backup, transaction_root)
        with mock.patch(
            "product.runtime.research_memory_repair._count_bound_versions", return_value=0,
        ):
            with self.assertRaisesRegex(ValueError, "RESEARCH_MEMORY_REPAIR_REFERENCES_CHANGED"):
                apply_view_reference_repairs(
                    transaction_root, security_id="TEST",
                    backup_root=self.base / "repair-transaction-failure-backup",
                )
        with sqlite3.connect(transaction_root / "research-memory.sqlite3") as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM research_views").fetchone()[0])

        receipt_root = self.base / "repair-receipt-failure"
        shutil.copytree(backup, receipt_root)
        with mock.patch(
            "product.runtime.research_memory_repair.os.replace",
            side_effect=OSError("synthetic receipt failure"),
        ):
            with self.assertRaisesRegex(OSError, "synthetic receipt failure"):
                apply_view_reference_repairs(
                    receipt_root, security_id="TEST",
                    backup_root=self.base / "repair-receipt-failure-backup",
                )
        with sqlite3.connect(receipt_root / "research-memory.sqlite3") as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM research_views").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
