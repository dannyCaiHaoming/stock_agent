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
    evidence_id: str = "ev-market-1",
) -> dict:
    company_capabilities = {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT"}
    value = {
        "schema_version": schema_version,
        "report_id": report_id or f"dimension-report:{capability.casefold().replace('_', '-')}", "run_id": run_id,
        "invocation_id": "inv-1", "capability": capability,
        "scope": "PER_SECURITY", "security_ids": ["US:MRVL"],
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
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

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
