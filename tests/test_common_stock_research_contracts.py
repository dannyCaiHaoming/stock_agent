import copy
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
import tomllib
import tempfile
from unittest.mock import patch

from product.council import (
    BoundedResearchDispatch,
    CommonStockResearchError,
    build_holding_research_requests,
    build_cio_equity_research_input,
    build_initial_research_coverage,
    build_retry_request,
    CouncilPlanningError,
    build_common_stock_council_request,
    build_multidimensional_holding_research_request,
    build_independent_counter_thesis_research_request,
    build_council_request,
    validate_council_request,
    validate_equity_research_report,
    validate_research_coverage,
    envelope_equity_research_draft,
    parallel_intervals_overlap,
    persist_equity_research_report,
    prepare_common_stock_research_stage,
    render_equity_research_markdown,
    render_research_progress,
    validate_persisted_equity_research_pair,
)
from product.intake import build_handoff, build_manual_draft
from product.deterministic.equity_valuation import build_fundamental_supplement
from product.runtime.hashing import canonical_hash
from product.runtime.validation import validate_company_report
from product.runtime.invocation import validate_skeptic_first_pass_input
from product.runtime.common_stock_eval import (
    CommonStockEvalError,
    DIMENSIONS as EVAL_DIMENSIONS,
    EVAL_RUNTIME_VERSION,
    build_common_stock_eval_dispatch_message,
    build_common_stock_eval_packet,
    build_common_stock_eval_prompt,
    finalize_common_stock_eval_job,
    prepare_common_stock_eval_job,
    validate_common_stock_eval_result,
)
from product.runtime.common_stock_stage import (
    COMMON_STOCK_START_CONTEXT_MAX_BYTES,
    CommonStockStageError,
    CURRENT_SOURCE_REUSE_DATASETS,
    STAGE_VERSION,
    _bound_common_stock_dispatch_packet,
    _current_source_reuse_status,
    _report_package_calculation_ids,
    _run_bounded_process_group,
    _build_common_stock_dispatch_packet,
    build_common_stock_dispatch_message,
    build_common_stock_dispatch_packet,
    current_research_bindings,
    finalize_common_stock_stage_run,
    _validate_common_stock_stage_run_package,
    launch_common_stock_stage,
    persist_common_stock_report_package,
    prepare_common_stock_stage_run,
    serialize_common_stock_dispatch_context,
    validate_delivered_research_references,
)
from product.runtime.common_stock_data import (
    CommonStockDataError,
    _collection_failure_code,
    assemble_common_stock_evidence,
    build_common_stock_collection_portfolio,
    collect_common_stock_data_from_handoff,
    validate_common_stock_source_bundle,
)
from product.runtime.model_routing import select_product_runtime_model
from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError, serve_stdio
from product.runtime.equity_research_package import build_equity_research_package
from product.runtime.research_memory import ResearchMemory


ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_FIXTURE = ROOT / "evals/fixtures/portfolio-intake/synthetic-multi-asset-manual.json"


def flattened_evidence_catalog(packet):
    return [
        item
        for group in packet["evidence_catalog"]
        for item in group["items"]
    ]


def confirmed_handoff():
    payload = json.loads(PORTFOLIO_FIXTURE.read_text(encoding="utf-8"))
    draft = build_manual_draft(payload)
    return build_handoff(
        draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00"
    )


def stock_handoff(count=4):
    fixture = ROOT / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["draft_id"] = f"draft-stock-{count}"
    payload["positions"] = payload["positions"][:count]
    draft = build_manual_draft(payload)
    return build_handoff(
        draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00"
    )


class CommonStockCouncilRequestTests(unittest.TestCase):
    def test_independent_counter_thesis_stage_is_explicit(self):
        handoff = confirmed_handoff()
        request = build_independent_counter_thesis_research_request(
            handoff, request_id="counter-request-1",
            research_question="完成正向研究及独立反证。", benchmark_id="US:SPY",
        )
        self.assertEqual("INDEPENDENT_COUNTER_THESIS_RESEARCH", request["stage"])
        self.assertEqual(
            sorted(item["security_id"] for item in handoff["portfolio"]["positions"]),
            request["research_security_ids"],
        )
        validate_council_request(request, handoff=handoff)
        request["stage"] = "UNKNOWN_COUNTER_STAGE"
        request["request_hash"] = canonical_hash({
            key: value for key, value in request.items() if key != "request_hash"
        })
        with self.assertRaises(CouncilPlanningError):
            validate_council_request(request, handoff=handoff)

    def test_multidimensional_stage_is_explicit_and_preserves_all_positions(self):
        handoff = confirmed_handoff()
        request = build_multidimensional_holding_research_request(
            handoff,
            request_id="multi-request-1",
            research_question="为确认持仓准备多维研究资料包。",
            benchmark_id="US:SPY",
        )
        self.assertEqual("MULTI_DIMENSIONAL_HOLDING_RESEARCH", request["stage"])
        self.assertEqual(
            sorted(item["security_id"] for item in handoff["portfolio"]["positions"]),
            request["research_security_ids"],
        )
        self.assertNotIn("action", request)
        validate_council_request(request, handoff=handoff)

    def test_research_stage_accepts_unknown_portfolio_fields(self):
        handoff = confirmed_handoff()
        request = build_common_stock_council_request(
            handoff,
            request_id="research-request-1",
            research_question="分析已确认的普通股持仓。",
        )
        self.assertEqual("council-request/2.0.0", request["schema_version"])
        self.assertEqual("COMMON_STOCK_RESEARCH", request["stage"])
        self.assertIsNone(request["holding_horizon"])
        self.assertIsNone(request["benchmark_id"])
        self.assertIsNone(request["mandate_artifact_id"])
        validate_council_request(request, handoff=handoff)

    def test_research_stage_rejects_missing_binding(self):
        handoff = confirmed_handoff()
        request = build_common_stock_council_request(
            handoff, request_id="research-request-2", research_question="研究持仓"
        )
        request["portfolio_hash"] = "0" * 64
        request["request_hash"] = canonical_hash(
            {key: value for key, value in request.items() if key != "request_hash"}
        )
        with self.assertRaisesRegex(CouncilPlanningError, "BINDING_INVALID"):
            validate_council_request(request, handoff=handoff)

    def test_full_stage_cannot_use_nullable_research_exception(self):
        handoff = confirmed_handoff()
        request = build_common_stock_council_request(
            handoff, request_id="research-request-3", research_question="研究持仓"
        )
        request["stage"] = "FULL_COUNCIL"
        request["request_hash"] = canonical_hash(
            {key: value for key, value in request.items() if key != "request_hash"}
        )
        with self.assertRaisesRegex(CouncilPlanningError, "FULL_STAGE_FIELD_REQUIRED"):
            validate_council_request(request, handoff=handoff)

    def test_historical_request_contract_remains_unchanged(self):
        handoff = confirmed_handoff()
        request = build_council_request(
            handoff,
            request_id="historical-request",
            research_question="完整组合研究",
            holding_horizon="6 months",
            benchmark_id="SP500",
            mandate_artifact_id="mandate:advisory-only-v1",
        )
        self.assertEqual("council-request/1.0.0", request["schema_version"])
        broken = copy.deepcopy(request)
        broken["holding_horizon"] = None
        broken["request_hash"] = canonical_hash(
            {key: value for key, value in broken.items() if key != "request_hash"}
        )
        with self.assertRaisesRegex(CouncilPlanningError, "SCHEMA_INVALID"):
            validate_council_request(broken, handoff=handoff)


def gate_for(handoff, run_id=None):
    facts = []
    for position in handoff["portfolio"]["positions"]:
        if position["asset_type"] == "COMMON_STOCK":
            for suffix, field, value in (
                ("revenue", "revenue", "100"),
                ("cash", "operating_cash_flow", "20"),
            ):
                facts.append({
                    "evidence_id": f"ev-{position['display_symbol'].lower()}-{suffix}",
                    "security_id": position["security_id"],
                    "semantic_field": field,
                    "value": value,
                    "source_id": "synthetic-sec",
                    "as_of": "2026-06-30T00:00:00Z",
                    "retrieved_at": "2026-07-01T00:00:00Z",
                })
    gate = {
        "decision_cutoff": "2026-09-11T12:00:00Z",
        "input_evidence_ids": sorted(item["evidence_id"] for item in facts),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in facts),
        "excluded_evidence_ids": [],
        "allowed_evidence": facts,
        "excluded": [],
    }
    if run_id is not None:
        gate["run_id"] = run_id
    gate["bundle_hash"] = canonical_hash(gate)
    return gate


class CommonStockDataPreparationTests(unittest.TestCase):
    def test_collection_failure_codes_are_canonical_and_sanitized(self):
        for code in (
            "SEC_HTTP_403", "YAHOO_TRANSPORT_FAILURE",
            "NASDAQ_HTTP_429", "EASTMONEY_RESPONSE_INVALID",
            "MOOMOO_OPEND_UNREACHABLE",
        ):
            with self.subTest(code=code):
                self.assertEqual(code, _collection_failure_code(ValueError(code)))

        for unsafe in (
            "SEC_HTTP_403\ncontact=user@example.com cookie=secret",
            "YAHOO TRANSPORT FAILURE",
            "NASDAQ_" + "A" * 101,
            "EASTMONEY_failure",
            "MOOMOO_/tmp/private-token",
        ):
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    "COMMON_STOCK_SECURITY_COLLECTION_FAILED",
                    _collection_failure_code(ValueError(unsafe)),
                )

    @staticmethod
    def collector_for(handoff, *, future_security_id=None, failed_security_id=None):
        positions = {
            item["security_id"]: item for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "COMMON_STOCK"
        }

        def collect(position):
            security_id = position["security_id"]
            if security_id == failed_security_id:
                raise CommonStockDataError("COMMON_STOCK_SECURITY_IDENTITY_UNVERIFIED")
            cutoff = (
                "2026-09-11T11:00:00Z"
                if security_id == next(iter(positions))
                else "2026-09-11T12:00:00Z"
            )
            retrieved_at = (
                "2026-09-11T11:30:00Z"
                if security_id == future_security_id
                else "2026-09-11T10:30:00Z"
            )
            return {
                "security_id": security_id,
                "identity_status": "VERIFIED",
                "decision_cutoff": cutoff,
                "facts": [{
                    "evidence_id": f"ev-{position['display_symbol'].lower()}-filing",
                    "security_id": security_id,
                    "semantic_field": "revenue",
                    "value": "100",
                    "source_id": "synthetic-sec",
                    "as_of": "2026-06-30T00:00:00Z",
                    "published_at": "2026-08-01T00:00:00Z",
                    "retrieved_at": retrieved_at,
                }],
                "data_gaps": [],
            }

        return collect

    def test_shared_configuration_fails_before_any_security_collection(self):
        handoff = stock_handoff(2)
        calls = []

        def collect(position):
            calls.append(position)
            return {}

        with self.assertRaisesRegex(CommonStockDataError, "SHARED_CONFIGURATION_INVALID"):
            assemble_common_stock_evidence(
                handoff,
                run_id="data-run",
                collect_security=collect,
                validate_shared_configuration=lambda: (_ for _ in ()).throw(ValueError("bad")),
            )
        self.assertEqual([], calls)

    def test_confirmed_handoff_becomes_minimal_collection_input_without_portfolio_judgment(self):
        handoff = confirmed_handoff()
        value = build_common_stock_collection_portfolio(handoff)
        self.assertEqual("live-portfolio/2.0.0", value["schema_version"])
        self.assertEqual("COMMON_STOCK_DATA_COLLECTION", value["purpose"])
        self.assertEqual(
            {"AAPL", "MSFT"}, {item["ticker"] for item in value["positions"]}
        )
        serialized = json.dumps(value, ensure_ascii=False)
        for forbidden in ("average_cost_price", "unrealized_pnl", "cash_balance", "mandate", "holding_horizon"):
            self.assertNotIn(forbidden, serialized)

    def test_more_than_three_common_stocks_all_enter_collection_plan(self):
        from product.mcp.live.contracts import validate_contract

        handoff = stock_handoff(7)
        value = build_common_stock_collection_portfolio(handoff)
        validate_contract("portfolio", value)
        expected = {
            item["security_id"]
            for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "COMMON_STOCK"
        }
        self.assertGreater(len(expected), 3)
        self.assertEqual(expected, {item["security_id"] for item in value["positions"]})

    def test_user_entry_automatically_persists_gate_and_data_preparation(self):
        handoff = confirmed_handoff()
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root = Path(temp)
            handoff_path = root / "handoff.json"
            access_path = root / "access.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            access_path.write_text("[]", encoding="utf-8")

            def fake_collect(portfolio_path, **kwargs):
                value = json.loads(Path(portfolio_path).read_text())
                self.assertEqual("COMMON_STOCK_DATA_COLLECTION", value["purpose"])
                source = Path(kwargs["output_dir"])
                source.mkdir()
                security_id = value["positions"][0]["security_id"]
                result = self.collector_for(handoff)(next(
                    item for item in handoff["portfolio"]["positions"]
                    if item["security_id"] == security_id
                ))
                snapshot = {
                    "snapshot_id": f"snapshot-{security_id}",
                    "snapshot_hash": canonical_hash(security_id),
                    "request_started_at": "2026-09-11T10:00:00Z",
                    "decision_cutoff": "2099-09-12T12:00:00Z",
                    "facts": result["facts"], "source_access": [],
                    "raw_records": [], "collection_events": [
                        {"url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json", "status": "fetched", "request_number": 1},
                        {"url": "https://data.sec.gov/submissions/CIK0000000001.json", "status": "fetched", "request_number": 2},
                        {"url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/report.htm", "status": "fetched", "request_number": 3},
                        {"endpoint": "https://query1.finance.yahoo.com/v8/finance/chart/TEST", "status": "fetched", "request_number": 1},
                    ], "gaps": [],
                    "source_selections": [{
                        "security_id": security_id,
                        "selection_hash": canonical_hash(f"selection:{security_id}"),
                    }],
                }
                (source / "portfolio.json").write_text(json.dumps(value), encoding="utf-8")
                (source / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
                (source / "calendar.json").write_text("{}", encoding="utf-8")
                return {
                    "portfolio_path": str(source / "portfolio.json"),
                    "snapshot_path": str(source / "snapshot.json"),
                    "calendar_lock": str(source / "calendar.json"),
                }

            collect_security = self.collector_for(handoff)
            original_positions = {
                item["security_id"]: item for item in handoff["portfolio"]["positions"]
            }
            def fake_security_result(position, **kwargs):
                value = dict(collect_security(original_positions[position["security_id"]]))
                value.update(
                    input_evidence_ids=[item["evidence_id"] for item in value["facts"]],
                    excluded=[], conflicts=[],
                )
                return value
            from product.mcp.live.research_supplement_collection import (
                build_research_supplements as real_build_research_supplements,
            )

            def fake_build_research_supplements(positions, *, gate, **kwargs):
                supplement_gate = copy.deepcopy(gate)
                supplement_gate["allowed_evidence"] = []
                supplement_gate["allowed_evidence_ids"] = []
                return real_build_research_supplements(
                    positions, gate=supplement_gate, **kwargs,
                )

            with patch("product.mcp.live.collection.validate_live_collection_configuration", return_value=[]), patch(
                "product.mcp.live.collection.collect_live_snapshot", side_effect=fake_collect
            ) as live_collect, patch(
                "product.runtime.common_stock_data._security_live_result",
                side_effect=fake_security_result,
            ), patch(
                "product.mcp.live.research_supplement_collection.capture_external_research_results",
                return_value={},
            ) as supplement_capture, patch(
                "product.mcp.live.research_supplement_collection.capture_shared_research_results",
                return_value=[],
            ) as shared_capture, patch(
                "product.mcp.live.research_supplement_collection.build_research_supplements",
                side_effect=fake_build_research_supplements,
            ):
                # load_locked_calendar is imported inside the function; patch the source module instead.
                with patch("product.mcp.live.market.load_locked_calendar", return_value=object()):
                    result = collect_common_stock_data_from_handoff(
                        handoff_path, access_path=access_path,
                        output_dir=root / "data", cache_root=root / "cache",
                        repository_root=Path(__file__).resolve().parents[1],
                        memory_root=root / "research-memory",
                        sec_user_agent="synthetic contact", run_id="auto-data-run",
                        collect_research_supplements=True,
                        planning_now=lambda: datetime(2026, 9, 12, tzinfo=UTC),
                    )
                    first_memory = ResearchMemory(root / "research-memory")
                    for position in build_common_stock_collection_portfolio(handoff)["positions"]:
                        profile_checkpoint = first_memory.checkpoint(
                            position["security_id"], "public", "company_profile",
                        )
                        self.assertIsNotNone(profile_checkpoint)
                        self.assertTrue(profile_checkpoint["state"].get("object_ref"))
                        persisted_profile = json.loads(first_memory.read_object(
                            profile_checkpoint["state"]["object_ref"],
                            profile_checkpoint["state"]["object_hash"],
                        ))
                        self.assertEqual(
                            "research-supplement-external-results/1.0.0",
                            persisted_profile["schema_version"],
                        )
                        self.assertEqual(position["security_id"], persisted_profile["security_id"])
                        self.assertEqual([], persisted_profile["results"])
                        self.assertEqual(
                            "SKIP_FRESH",
                            first_memory.plan(
                                position["security_id"], "public", "company_profile",
                                planning_as_of="2026-09-12T00:00:00Z",
                            )["mode"],
                            msg=profile_checkpoint,
                        )
                    restarted = collect_common_stock_data_from_handoff(
                        handoff_path, access_path=access_path,
                        output_dir=root / "data-restarted", cache_root=root / "cache",
                        repository_root=Path(__file__).resolve().parents[1],
                        memory_root=root / "research-memory",
                        sec_user_agent="synthetic contact",
                        run_id="auto-data-restarted",
                        collect_research_supplements=True,
                        planning_now=lambda: datetime(2026, 9, 12, tzinfo=UTC),
                    )
            self.assertEqual("FROZEN", result["status"])
            self.assertTrue((root / "data/gate.json").is_file())
            data = json.loads((root / "data/data-preparation.json").read_text())
            self.assertEqual("portfolio-handoff-v3", data["authoritative_portfolio_source"])
            bundle = json.loads((root / "data/source-bundle.json").read_text())
            self.assertEqual(2, len(bundle["items"]))
            self.assertEqual(
                {"FROZEN"}, {item["status"] for item in bundle["items"]}, msg=bundle,
            )
            self.assertEqual(2, live_collect.call_count)
            self.assertEqual(2, supplement_capture.call_count)
            self.assertEqual(2, shared_capture.call_count)
            restarted_memory = json.loads(
                (root / "data-restarted/research-memory/manifest.json").read_text()
            )
            self.assertEqual(
                {"CACHE_HIT"},
                {item["mode"] for item in restarted_memory["results"]},
            )
            self.assertEqual(
                {"SKIPPED_FRESH"},
                {
                    item["dataset_outcomes"]["company_profile"]["status"]
                    for item in restarted_memory["results"]
                },
            )
            self.assertEqual("FROZEN", restarted["status"])

    def test_real_handoff_collection_path_isolates_one_security_failure(self):
        handoff = stock_handoff(2)
        failed = handoff["portfolio"]["positions"][0]["security_id"]
        collector = self.collector_for(handoff)
        original_positions = {
            item["security_id"]: item for item in handoff["portfolio"]["positions"]
        }
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root = Path(temp)
            handoff_path = root / "handoff.json"
            access_path = root / "access.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            access_path.write_text("[]", encoding="utf-8")
            calls = []

            def fake_collect(portfolio_path, **kwargs):
                portfolio = json.loads(Path(portfolio_path).read_text())
                security_id = portfolio["positions"][0]["security_id"]
                calls.append(security_id)
                source = Path(kwargs["output_dir"])
                source.mkdir()
                if security_id == failed:
                    error = {"status": "FAILED", "failure_code": "SEC_HTTP_403"}
                    (source / "collection-error.json").write_text(json.dumps(error), encoding="utf-8")
                    raise ValueError("SEC_HTTP_403:see collection-error.json")
                selection = {
                    "security_id": security_id,
                    "selection_hash": canonical_hash(f"selection:{security_id}"),
                }
                result = collector(original_positions[security_id])
                snapshot = {
                    "snapshot_id": f"snapshot-{security_id}",
                    "snapshot_hash": canonical_hash(security_id),
                    "request_started_at": "2026-09-11T10:00:00Z",
                    "decision_cutoff": "2026-09-12T12:00:00Z",
                    "facts": result["facts"], "source_access": [],
                    "raw_records": [], "collection_events": [], "gaps": [],
                    "source_selections": [selection],
                }
                (source / "portfolio.json").write_text(json.dumps(portfolio), encoding="utf-8")
                (source / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
                (source / "calendar.json").write_text("{}", encoding="utf-8")
                return {
                    "portfolio_path": str(source / "portfolio.json"),
                    "snapshot_path": str(source / "snapshot.json"),
                    "calendar_lock": str(source / "calendar.json"),
                }

            def fake_security_result(position, **kwargs):
                value = dict(collector(original_positions[position["security_id"]]))
                value.update(
                    input_evidence_ids=[item["evidence_id"] for item in value["facts"]],
                    excluded=[], conflicts=[],
                )
                return value

            with patch("product.mcp.live.collection.validate_live_collection_configuration", return_value=[]), patch(
                "product.mcp.live.collection.collect_live_snapshot", side_effect=fake_collect
            ), patch("product.mcp.live.market.load_locked_calendar", return_value=object()), patch(
                "product.runtime.common_stock_data._security_live_result", side_effect=fake_security_result
            ), patch(
                "product.mcp.live.research_supplement_collection.capture_external_research_results",
                return_value={},
            ), patch(
                "product.mcp.live.research_supplement_collection.capture_shared_research_results",
                return_value=[],
            ) as shared_capture, patch(
                "product.mcp.live.research_supplement_collection.build_research_supplements",
                return_value=[],
            ) as supplement_builder:
                result = collect_common_stock_data_from_handoff(
                    handoff_path, access_path=access_path, output_dir=root / "data",
                    cache_root=root / "cache", sec_user_agent="synthetic contact",
                    repository_root=Path(__file__).resolve().parents[1],
                    memory_root=root / "research-memory",
                    run_id="isolated-data-run", collect_research_supplements=True,
                )
            self.assertEqual(1, shared_capture.call_count)
            supplement_positions = supplement_builder.call_args.args[0]
            self.assertEqual(
                [
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                    if item["security_id"] != failed
                ],
                [item["security_id"] for item in supplement_positions],
            )
            self.assertEqual(
                {item["security_id"] for item in handoff["portfolio"]["positions"]}, set(calls)
            )
            preparation = json.loads(Path(result["data_preparation"]).read_text())
            states = {item["security_id"]: item["status"] for item in preparation["items"]}
            self.assertEqual("FAILED", states[failed])
            self.assertIn("READY", states.values())
            bundle = json.loads(Path(result["source_bundle"]).read_text())
            self.assertEqual({"FAILED", "FROZEN"}, {item["status"] for item in bundle["items"]})
            failed_bundle_item = next(
                item for item in bundle["items"] if item["security_id"] == failed
            )
            self.assertEqual("SEC_HTTP_403", failed_bundle_item["failure_code"])
            with ResearchMemory(root / "research-memory").session() as connection:
                attempts = [
                    (row[0], json.loads(row[1])) for row in connection.execute(
                        "SELECT dataset, details_json FROM attempts WHERE security_id=?",
                        (failed,),
                    )
                ]
            self.assertTrue(attempts)
            self.assertIn("company_profile", {dataset for dataset, _ in attempts})
            self.assertEqual(
                {"SEC_HTTP_403"},
                {
                    details["failure_code"]
                    for _, details in attempts
                    if "failure_code" in details
                },
            )
            gate = json.loads(Path(result["gate"]).read_text())
            preparation = json.loads(Path(result["data_preparation"]).read_text())
            with patch("product.mcp.live.contracts.validate_contract"), patch(
                "product.mcp.live.market.load_locked_calendar", return_value=object()
            ), patch(
                "product.runtime.common_stock_data._security_live_result",
                side_effect=fake_security_result,
            ):
                validate_common_stock_source_bundle(
                    handoff, gate=gate, preparation=preparation,
                    source_bundle_path=Path(result["source_bundle"]),
                )
                tampered_preparation = copy.deepcopy(preparation)
                failed_row = next(
                    item for item in tampered_preparation["items"]
                    if item["security_id"] == failed
                )
                failed_row["failure_code"] = "COMMON_STOCK_INVENTED_FAILURE"
                tampered_preparation["preparation_hash"] = canonical_hash({
                    key: value for key, value in tampered_preparation.items()
                    if key != "preparation_hash"
                })
                with self.assertRaisesRegex(CommonStockDataError, "SOURCE_FAILURE_BINDING_INVALID"):
                    validate_common_stock_source_bundle(
                        handoff, gate=gate, preparation=tampered_preparation,
                        source_bundle_path=Path(result["source_bundle"]),
                    )

                failed_item = next(item for item in bundle["items"] if item["security_id"] == failed)
                error_path = Path(result["source_bundle"]).parent / failed_item["collection_error_ref"]
                error_record = json.loads(error_path.read_text())
                error_record["failure_code"] = "LIVE_INVENTED_FAILURE"
                error_path.write_text(json.dumps(error_record))
                with self.assertRaisesRegex(CommonStockDataError, "COLLECTION_ERROR_HASH_MISMATCH"):
                    validate_common_stock_source_bundle(
                        handoff, gate=gate, preparation=preparation,
                        source_bundle_path=Path(result["source_bundle"]),
                    )

                unsigned_error = json.loads(error_path.read_text())
                unsigned_error.pop("failure_code")
                error_path.write_text(json.dumps(unsigned_error))
                resigned_bundle = copy.deepcopy(bundle)
                resigned_failed = next(
                    item for item in resigned_bundle["items"] if item["security_id"] == failed
                )
                resigned_failed["collection_error_hash"] = canonical_hash(unsigned_error)
                resigned_bundle["bundle_hash"] = canonical_hash({
                    key: value for key, value in resigned_bundle.items() if key != "bundle_hash"
                })
                Path(result["source_bundle"]).write_text(json.dumps(resigned_bundle))
                resigned_gate = copy.deepcopy(gate)
                resigned_gate["source_bundle_hash"] = resigned_bundle["bundle_hash"]
                resigned_gate["bundle_hash"] = canonical_hash({
                    key: value for key, value in resigned_gate.items() if key != "bundle_hash"
                })
                resigned_preparation = copy.deepcopy(preparation)
                resigned_preparation["source_bundle_hash"] = resigned_bundle["bundle_hash"]
                resigned_preparation["preparation_hash"] = canonical_hash({
                    key: value for key, value in resigned_preparation.items()
                    if key != "preparation_hash"
                })
                with self.assertRaisesRegex(CommonStockDataError, "COLLECTION_ERROR_BINDING_INVALID"):
                    validate_common_stock_source_bundle(
                        handoff, gate=resigned_gate, preparation=resigned_preparation,
                        source_bundle_path=Path(result["source_bundle"]),
                    )

    def test_identity_failure_isolated_and_other_security_remains_ready(self):
        handoff = stock_handoff(2)
        failed = handoff["portfolio"]["positions"][0]["security_id"]
        result = assemble_common_stock_evidence(
            handoff,
            run_id="data-run",
            collect_security=self.collector_for(handoff, failed_security_id=failed),
        )
        states = {item["security_id"]: item for item in result["preparation"]["items"]}
        self.assertEqual("FAILED", states[failed]["status"])
        self.assertEqual("READY", next(value for key, value in states.items() if key != failed)["status"])
        self.assertEqual(1, len(result["gate"]["allowed_evidence"]))
        self.assertEqual(0, result["preparation"]["model_calls"])

    def test_sqlite_write_failure_isolated_and_shared_failure_stops_batch(self):
        handoff = stock_handoff(2)
        failed = handoff["portfolio"]["positions"][0]["security_id"]
        collector = self.collector_for(handoff)
        original_positions = {
            item["security_id"]: item for item in handoff["portfolio"]["positions"]
        }

        def run_case(
            root: Path, *, shared_failure: bool,
            local_error: type[sqlite3.Error] = sqlite3.OperationalError,
        ):
            handoff_path = root / "handoff.json"
            access_path = root / "access.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            access_path.write_text("[]", encoding="utf-8")

            def fake_collect(portfolio_path, **kwargs):
                portfolio = json.loads(Path(portfolio_path).read_text())
                security_id = portfolio["positions"][0]["security_id"]
                source = Path(kwargs["output_dir"])
                source.mkdir()
                result = collector(original_positions[security_id])
                selection = {
                    "security_id": security_id,
                    "selection_hash": canonical_hash(f"selection:{security_id}"),
                }
                snapshot = {
                    "snapshot_id": f"snapshot-{security_id}",
                    "snapshot_hash": canonical_hash(security_id),
                    "request_started_at": "2026-09-11T10:00:00Z",
                    "decision_cutoff": "2026-09-11T12:00:00Z",
                    "facts": result["facts"], "source_access": [],
                    "raw_records": [], "collection_events": [], "gaps": [],
                    "source_selections": [selection],
                }
                (source / "portfolio.json").write_text(json.dumps(portfolio))
                (source / "snapshot.json").write_text(json.dumps(snapshot))
                (source / "calendar.json").write_text("{}")
                return {
                    "portfolio_path": str(source / "portfolio.json"),
                    "snapshot_path": str(source / "snapshot.json"),
                    "calendar_lock": str(source / "calendar.json"),
                }

            def fake_security_result(position, **kwargs):
                value = dict(collector(original_positions[position["security_id"]]))
                value.update(
                    input_evidence_ids=[item["evidence_id"] for item in value["facts"]],
                    excluded=[], conflicts=[],
                )
                return value

            original_ingest = ResearchMemory.ingest_dataset

            def injected_ingest(memory, *, plan, **kwargs):
                if plan["security_id"] == failed:
                    raise local_error("synthetic security-local write failure")
                return original_ingest(memory, plan=plan, **kwargs)

            patches = [
                patch("product.mcp.live.collection.validate_live_collection_configuration", return_value=[]),
                patch("product.mcp.live.collection.collect_live_snapshot", side_effect=fake_collect),
                patch("product.mcp.live.market.load_locked_calendar", return_value=object()),
                patch("product.runtime.common_stock_data._security_live_result", side_effect=fake_security_result),
                patch.object(ResearchMemory, "ingest_dataset", new=injected_ingest),
            ]
            if shared_failure:
                original_check = ResearchMemory.lightweight_check
                check_calls = 0

                def injected_check(memory, connection):
                    nonlocal check_calls
                    check_calls += 1
                    if check_calls > 1:
                        raise sqlite3.IntegrityError("synthetic shared corruption")
                    return original_check(connection)

                patches.append(patch.object(
                    ResearchMemory, "lightweight_check",
                    new=injected_check,
                ))
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                if shared_failure:
                    with patches[5], self.assertRaisesRegex(
                        CommonStockDataError, "RESEARCH_MEMORY_SHARED_FAILURE",
                    ):
                        collect_common_stock_data_from_handoff(
                            handoff_path, access_path=access_path,
                            output_dir=root / "data", cache_root=root / "cache",
                            repository_root=ROOT, memory_root=root / "research-memory",
                            sec_user_agent="synthetic contact", run_id="sqlite-shared",
                            planning_now=lambda: datetime(2026, 9, 11, 10, tzinfo=UTC),
                        )
                    return None
                return collect_common_stock_data_from_handoff(
                    handoff_path, access_path=access_path,
                    output_dir=root / "data", cache_root=root / "cache",
                    repository_root=ROOT, memory_root=root / "research-memory",
                    sec_user_agent="synthetic contact", run_id="sqlite-isolated",
                    planning_now=lambda: datetime(2026, 9, 11, 10, tzinfo=UTC),
                )

        for local_error in (sqlite3.OperationalError, sqlite3.IntegrityError):
            with self.subTest(local_error=local_error.__name__), tempfile.TemporaryDirectory(
                dir="/private/tmp",
            ) as temp:
                result = run_case(
                    Path(temp), shared_failure=False, local_error=local_error,
                )
                bundle = json.loads(Path(result["source_bundle"]).read_text())
                by_security = {item["security_id"]: item for item in bundle["items"]}
                self.assertEqual("FAILED", by_security[failed]["status"])
                self.assertEqual(
                    "RESEARCH_MEMORY_PERSISTENCE_FAILED",
                    by_security[failed]["failure_code"],
                )
                self.assertEqual(
                    "FROZEN",
                    next(value for key, value in by_security.items() if key != failed)["status"],
                )
                diagnostic = (
                    Path(result["source_bundle"]).parent
                    / by_security[failed]["collection_error_ref"]
                )
                self.assertEqual(
                    "RESEARCH_MEMORY_PERSISTENCE_FAILED",
                    json.loads(diagnostic.read_text())["failure_code"],
                )
                gate = json.loads(Path(result["gate"]).read_text())
                self.assertNotIn(
                    failed, {item["security_id"] for item in gate["allowed_evidence"]},
                )

        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            run_case(Path(temp), shared_failure=True)

    def test_security_local_cutoff_excludes_future_retrieval_and_keeps_common_cutoff(self):
        handoff = stock_handoff(2)
        first = handoff["portfolio"]["positions"][0]["security_id"]
        result = assemble_common_stock_evidence(
            handoff,
            run_id="data-run",
            collect_security=self.collector_for(handoff, future_security_id=first),
        )
        self.assertEqual("2026-09-11T12:00:00Z", result["preparation"]["common_cutoff"])
        self.assertEqual(
            [f"ev-{handoff['portfolio']['positions'][0]['display_symbol'].lower()}-filing"],
            result["gate"]["excluded_evidence_ids"],
        )
        first_row = next(item for item in result["preparation"]["items"] if item["security_id"] == first)
        self.assertEqual("INSUFFICIENT_EVIDENCE", first_row["status"])

    def test_account_time_is_separate_and_retrieval_time_is_not_rewritten(self):
        handoff = stock_handoff(2)
        result = assemble_common_stock_evidence(
            handoff,
            run_id="data-run",
            collect_security=self.collector_for(handoff),
        )
        self.assertEqual(
            handoff["account_snapshot"]["as_of"], result["preparation"]["account_source_as_of"]
        )
        self.assertEqual(
            {"2026-09-11T10:30:00Z"},
            {item["retrieved_at"] for item in result["gate"]["allowed_evidence"]},
        )
        serialized = json.dumps(result["gate"], ensure_ascii=False)
        self.assertNotIn("average_cost_price", serialized)
        self.assertNotIn("cash_balance", serialized)

    def test_data_failure_is_not_dispatched_but_full_portfolio_is_retained(self):
        handoff = stock_handoff(2)
        failed = handoff["portfolio"]["positions"][0]["security_id"]
        data = assemble_common_stock_evidence(
            handoff,
            run_id="data-run",
            collect_security=self.collector_for(handoff, failed_security_id=failed),
        )
        request = build_common_stock_council_request(
            handoff, request_id="data-request", research_question="分析普通股持仓"
        )
        agent, skills = bindings()
        stage = prepare_common_stock_research_stage(
            handoff, request, data["gate"], run_id="data-run", batch_id="data-batch",
            agent_binding=agent, skill_bindings=skills, data_preparation=data["preparation"],
        )
        self.assertEqual(1, len(stage["holding_requests"]))
        self.assertEqual(2, len(stage["coverage"]["items"]))
        failed_coverage = next(
            item for item in stage["coverage"]["items"] if item["security_id"] == failed
        )
        self.assertEqual("FAILED", failed_coverage["execution_status"])
        self.assertEqual("COMMON_STOCK_SECURITY_IDENTITY_UNVERIFIED", failed_coverage["failure_code"])


def bindings():
    skills = [
        {"name": name, "version": "1.0.0", "content_hash": canonical_hash(name)}
        for name in ("evidence-grounding", "company-research", "valuation", "catalyst-analysis")
    ]
    agent = {
        "name": "runtime_company_analyst",
        "version": "3.0.0",
        "content_hash": canonical_hash("runtime_company_analyst"),
    }
    return agent, skills


def research_request():
    handoff = confirmed_handoff()
    council_request = build_common_stock_council_request(
        handoff, request_id="research-request", research_question="分析普通股持仓"
    )
    agent, skills = bindings()
    requests = build_holding_research_requests(
        handoff, council_request, gate_for(handoff, "research-run"), run_id="research-run",
        agent_binding=agent, skill_bindings=skills,
    )
    return handoff, council_request, requests[0]


def valid_report(request, evidence_refs=None):
    evidence_refs = list(evidence_refs or request["allowed_evidence_ids"][:1])
    claims = [{
        "claim_id": "claim-core", "statement": "收入事实支持当前商业规模判断。",
        "kind": "INTERPRETATION", "evidence_refs": evidence_refs,
        "assumption_ids": ["assumption-demand"], "calculation_refs": [],
        "counter_claim_refs": ["claim-counter"],
        "invalidation_condition_ids": ["condition-demand"],
    }, {
        "claim_id": "claim-counter", "statement": "现金转化仍可能弱于收入增长。",
        "kind": "INTERPRETATION", "evidence_refs": evidence_refs,
        "assumption_ids": [], "calculation_refs": [], "counter_claim_refs": [],
        "invalidation_condition_ids": ["condition-demand"],
    }]
    sections = {
        name: {
            "status": "ANALYZED", "narrative": f"{name} 的公司专属分析。",
            "claim_refs": ["claim-core"], "data_gap_ids": [],
        }
        for name in (
            "company_and_core_questions", "business_competition_financials",
            "thesis_and_valuation", "catalysts_and_counterevidence",
            "invalidation_and_monitoring", "gaps_and_confidence",
        )
    }
    return {
        "schema_version": "equity-research-report/1.0.0",
        "run_id": request["run_id"], "invocation_id": request["invocation_id"],
        "report_id": "equity-report-1", "status": "COMPLETE",
        "agent": "runtime_company_analyst",
        "bindings": {
            "handoff_id": request["handoff_id"], "handoff_hash": request["handoff_hash"],
            "portfolio_hash": request["portfolio_hash"],
            "council_request_id": request["council_request_id"],
            "council_request_hash": request["council_request_hash"],
            "holding_research_request_id": request["request_id"],
            "holding_research_request_hash": request["request_hash"],
            "decision_cutoff": request["decision_cutoff"],
        },
        "security": {key: request["security"][key] for key in (
            "security_id", "display_symbol", "display_name", "market", "asset_type"
        )},
        "research_scope": "SINGLE_COMMON_STOCK_HOLDING",
        "research_summary": {
            "summary": "核心经济逻辑有依据，但现金转化是主要反证。",
            "claim_refs": ["claim-core", "claim-counter"],
            "primary_invalidation_condition_ids": ["condition-demand"],
        },
        "sections": sections,
        "claims": claims,
        "assumptions": [{
            "assumption_id": "assumption-demand", "statement": "需求保持稳定。",
            "rationale": "用于检验收入持续性。", "evidence_refs": evidence_refs,
        }],
        "counter_evidence_refs": evidence_refs,
        "invalidation_conditions": [{
            "condition_id": "condition-demand", "description": "收入连续两个可比期间下降。",
            "monitoring_signal": "季度收入同比变化", "claim_refs": ["claim-core"],
            "evidence_refs": evidence_refs,
        }],
        "reevaluation_triggers": [{
            "trigger_id": "trigger-filing", "description": "下一份定期报告发布后重评。",
            "claim_refs": ["claim-core"], "evidence_refs": evidence_refs,
        }],
        "monitoring_indicators": [{
            "indicator_id": "indicator-cash", "description": "经营现金流",
            "why_it_matters": "检验盈利质量。", "baseline": "100",
            "unit": "USD", "comparison_period": "最近披露期间",
            "reevaluation_rule": "下一可比期间与该基线比较。",
            "evidence_refs": evidence_refs,
        }],
        "data_gaps": [], "confidence": 0.68,
        "confidence_rationale": "置信度表示当前资料对研究判断的支持程度，不是上涨概率。",
        "skill_execution": [{
            "skill_name": item["name"], "version": item["version"],
            "invocation_hash": canonical_hash(item["name"] + request["invocation_id"]),
        } for item in request["skill_bindings"]],
        "artifact_refs": [],
    }


class HoldingResearchContractTests(unittest.TestCase):
    def test_requests_only_include_common_stocks_and_minimize_portfolio_context(self):
        handoff = confirmed_handoff()
        council_request = build_common_stock_council_request(
            handoff, request_id="research-request", research_question="分析普通股持仓"
        )
        agent, skills = bindings()
        requests = build_holding_research_requests(
            handoff, council_request, gate_for(handoff, "research-run"), run_id="research-run",
            agent_binding=agent, skill_bindings=skills,
        )
        common_ids = {
            item["security_id"] for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "COMMON_STOCK"
        }
        self.assertEqual(common_ids, {item["security"]["security_id"] for item in requests})
        serialized = json.dumps(requests, ensure_ascii=False)
        self.assertNotIn("average_cost_price", serialized)
        self.assertNotIn("unrealized_pnl", serialized)
        self.assertNotIn("cash_balance", serialized)

    def test_future_fact_is_rejected_before_request_reaches_agent(self):
        handoff = confirmed_handoff()
        council_request = build_common_stock_council_request(
            handoff, request_id="research-request", research_question="分析普通股持仓"
        )
        gate = gate_for(handoff, "research-run")
        gate["allowed_evidence"][0]["as_of"] = "2026-09-12T12:00:00Z"
        gate["bundle_hash"] = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        agent, skills = bindings()
        with self.assertRaisesRegex(CommonStockResearchError, "PIT_LEAKAGE"):
            build_holding_research_requests(
                handoff, council_request, gate, run_id="research-run",
                agent_binding=agent, skill_bindings=skills,
            )

    def test_gap_reason_and_monitoring_context_are_typed_but_old_reports_remain_readable(self):
        _, _, request = research_request()
        report = valid_report(request)
        report["data_gaps"] = [{
            "gap_id": "gap-capex", "reason_code": "NOT_FETCHED",
            "description": "未获取资本开支事实。", "impact": "无法计算自由现金流。",
        }]
        report["sections"]["gaps_and_confidence"]["data_gap_ids"] = ["gap-capex"]
        validate_equity_research_report(report, request=request)
        report["data_gaps"][0]["reason_code"] = "MODEL_GUESS"
        with self.assertRaisesRegex(CommonStockResearchError, "GAP_REASON_INVALID"):
            validate_equity_research_report(report, request=request)

        historical = valid_report(request)
        for key in ("baseline", "unit", "comparison_period", "reevaluation_rule"):
            historical["monitoring_indicators"][0].pop(key)
        validate_equity_research_report(historical, request=request)

    def test_canonical_evidence_ids_pass_and_decorated_or_unknown_ids_fail(self):
        _, _, request = research_request()
        valid = valid_report(request)
        validate_equity_research_report(valid, request=request)
        for suffix in ("|fixture-market-primary", "|as_of=2026-06-30", "-missing"):
            broken = copy.deepcopy(valid)
            broken["claims"][0]["evidence_refs"] = [request["allowed_evidence_ids"][0] + suffix]
            with self.subTest(suffix=suffix), self.assertRaisesRegex(
                CommonStockResearchError, "CANONICAL_ID_INVALID|EVIDENCE_CLOSURE_FAILED"
            ):
                validate_equity_research_report(broken, request=request)

    def test_multiple_valid_evidence_ids_pass(self):
        _, _, request = research_request()
        report = valid_report(request, request["allowed_evidence_ids"])
        validate_equity_research_report(report, request=request)

    def test_ungrounded_claim_feedback_identifies_claim(self):
        _, _, request = research_request()
        report = valid_report(request)
        claim_id = report["claims"][0]["claim_id"]
        report["claims"][0]["evidence_refs"] = []
        report["claims"][0]["assumption_ids"] = []
        report["claims"][0]["calculation_refs"] = []
        with self.assertRaisesRegex(
            CommonStockResearchError,
            rf"EQUITY_RESEARCH_SCHEMA_INVALID:.*\$\.claims\[0\].*:claim_id={claim_id}",
        ):
            validate_equity_research_report(report, request=request)

    def test_calculation_claim_requires_exact_top_level_artifact_ref(self):
        _, _, request = research_request()
        report = valid_report(request)
        calculation_id = "capex_to_ocf_fy27_h1"
        report["claims"][0]["calculation_refs"] = [calculation_id]
        report["artifact_refs"] = ["capex_to_ocf_fy27"]
        with self.assertRaisesRegex(
            CommonStockResearchError, "EQUITY_RESEARCH_CALCULATION_REFERENCE_DANGLING",
        ):
            validate_equity_research_report(
                report, request=request, calculation_artifact_ids=[calculation_id],
            )
        report["artifact_refs"] = [calculation_id]
        validate_equity_research_report(
            report, request=request, calculation_artifact_ids=[calculation_id],
        )

    def test_wrong_binding_action_field_and_dangling_internal_ref_fail(self):
        _, _, request = research_request()
        report = valid_report(request)
        cases = []
        wrong_binding = copy.deepcopy(report)
        wrong_binding["bindings"]["portfolio_hash"] = "0" * 64
        cases.append((wrong_binding, "SOURCE_BINDING"))
        action = copy.deepcopy(report)
        action["action"] = "HOLD"
        cases.append((action, "SCHEMA_INVALID|ACTION_FIELD_FORBIDDEN"))
        dangling = copy.deepcopy(report)
        dangling["research_summary"]["claim_refs"] = ["claim-missing"]
        cases.append((dangling, "SUMMARY_REFERENCE_DANGLING"))
        for value, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(CommonStockResearchError, code):
                validate_equity_research_report(value, request=request)

    def test_mixed_asset_coverage_keeps_every_position_and_gap(self):
        handoff = confirmed_handoff()
        council_request = build_common_stock_council_request(
            handoff, request_id="research-request", research_question="分析普通股持仓"
        )
        coverage = build_initial_research_coverage(
            handoff, council_request, batch_id="research-batch"
        )
        self.assertEqual(len(handoff["portfolio"]["positions"]), len(coverage["items"]))
        self.assertEqual("PARTIAL_RESEARCH", coverage["stage_status"])
        self.assertEqual(
            {"ETF", "OPTION"},
            {item["asset_type"] for item in coverage["items"] if item["coverage_status"] == "CAPABILITY_GAP"},
        )
        validate_research_coverage(coverage, handoff=handoff, council_request=council_request)

    def test_historical_agent_report_validator_still_accepts_old_contract(self):
        manifest = {
            "invocation_id": "legacy-invocation", "evidence_ids": ["legacy-evidence"],
            "skill_execution": [{
                "skill_name": "company-research", "version": "2.0.0",
                "invocation_hash": "b" * 64,
            }],
        }
        report = {
            "schema_version": "agent-research-report/2.0.0", "run_id": "legacy-run",
            "invocation_id": "legacy-invocation", "status": "COMPLETE",
            "agent": "runtime_company_analyst", "scope": "legacy",
            "claims": [{"claim_id": "legacy-claim", "statement": "历史事实。", "kind": "FACT", "evidence_refs": ["legacy-evidence"], "assumption_ids": []}],
            "assumptions": [], "counter_evidence_refs": [], "uncertainties": [],
            "data_gaps": [], "invalidation_conditions": ["事实变化时失效。"],
            "confidence": 0.5, "confidence_rationale": "历史报告语义。",
            "skill_execution": manifest["skill_execution"], "artifact_refs": [],
        }
        self.assertEqual(
            {"legacy-evidence"},
            validate_company_report(report, run_id="legacy-run", manifest=manifest),
        )


class CompanyAnalystCapabilityTests(unittest.TestCase):
    def test_one_agent_loads_common_stock_skills_and_explicit_report_mode(self):
        with (ROOT / "product/.codex/agents/runtime_company_analyst.toml").open("rb") as stream:
            config = tomllib.load(stream)
        configured = {Path(item["path"]).name for item in config["skills"]["config"]}
        self.assertTrue(
            {"evidence-grounding", "company-research", "valuation", "catalyst-analysis"}
            <= configured
        )
        self.assertIn("research-report-analysis", configured)
        instructions = config["developer_instructions"]
        self.assertIn("事实→假设→业务影响→推翻条件", instructions)
        self.assertIn("confidence 只表示资料对研究判断的支持程度", instructions)
        self.assertIn("没有合格公司事件时", instructions)
        self.assertIn("最重要的未决问题", instructions)
        self.assertIn("局部缺口", instructions)
        self.assertIn("即使只差一天", instructions)
        self.assertIn("只有起止日完全相同", instructions)
        self.assertIn("evidence_catalog", instructions)
        self.assertIn("按每个实际采用的指标逐项自检", instructions)
        self.assertIn("不能只写旧年度基线", instructions)
        self.assertIn("10-K、FY 标签本身不构成证明", instructions)
        self.assertIn("不得写成年度、财年、全年、TTM P/E", instructions)
        self.assertIn("$1.8 billion 确定性换算为 18 亿美元", instructions)
        self.assertIn("风险清单", instructions)
        self.assertIn("向好与向坏条件", instructions)
        self.assertIn("accounting_basis_status", instructions)
        self.assertIn("期间均为91天", instructions)
        self.assertIn("只能分别呈现两期原值", instructions)
        self.assertIn("大幅百分比变化", instructions)
        self.assertIn("完整字符串核对", instructions)
        self.assertIn("不得仅写", instructions)
        self.assertIn("不粘贴 evidence_id", instructions)
        self.assertIn(
            "equity_research_attachments.query` 实际返回附件正文中的冻结 calculation_ref",
            instructions,
        )
        self.assertIn("FY + current YTD - prior YTD", instructions)
        self.assertNotIn("新增 Catalyst Agent", instructions)

    def test_same_agent_definition_creates_independent_stock_invocations(self):
        handoff = confirmed_handoff()
        council_request = build_common_stock_council_request(
            handoff, request_id="research-request", research_question="分析普通股持仓"
        )
        agent, skills = bindings()
        requests = build_holding_research_requests(
            handoff, council_request, gate_for(handoff, "research-run"), run_id="research-run",
            agent_binding=agent, skill_bindings=skills,
        )
        self.assertGreaterEqual(len(requests), 2)
        self.assertEqual({"runtime_company_analyst"}, {item["agent_binding"]["name"] for item in requests})
        self.assertEqual(len(requests), len({item["invocation_id"] for item in requests}))

    def test_skill_methods_cover_mature_loss_making_and_first_research(self):
        company = (ROOT / "product/skills/company-research/SKILL.md").read_text(encoding="utf-8")
        valuation = (ROOT / "product/skills/valuation/SKILL.md").read_text(encoding="utf-8")
        catalyst = (ROOT / "product/skills/catalyst-analysis/SKILL.md").read_text(encoding="utf-8")
        for phrase in ("成熟盈利公司", "亏损成长公司", "首次研究", "经营现金流", "股份稀释", "最重要的未决问题", "即使只差一天"):
            self.assertIn(phrase, company)
        self.assertIn("条件性隐含预期", valuation)
        self.assertIn("不强制 DCF", valuation)
        self.assertIn("decision_cutoff", catalyst)
        self.assertIn("data_gap", catalyst)


class CommonStockDispatchTests(unittest.TestCase):
    def prepared(self, count=4, *, effective=3, reason=None):
        handoff = stock_handoff(count)
        council_request = build_common_stock_council_request(
            handoff, request_id="research-request", research_question="分析普通股持仓"
        )
        agent, skills = bindings()
        requests = build_holding_research_requests(
            handoff, council_request, gate_for(handoff, "dispatch-run"), run_id="dispatch-run",
            agent_binding=agent, skill_bindings=skills,
        )
        coverage = build_initial_research_coverage(
            handoff, council_request, batch_id="dispatch-batch",
            effective_concurrency=effective, execution_mode_reason=reason,
        )
        return handoff, council_request, requests, coverage

    @staticmethod
    def draft(report):
        return {
            key: copy.deepcopy(value)
            for key, value in report.items()
            if key in {
                "status", "research_summary", "sections", "claims", "assumptions",
                "counter_evidence_refs", "invalidation_conditions", "reevaluation_triggers",
                "monitoring_indicators", "data_gaps", "confidence", "confidence_rationale",
                "artifact_refs",
            }
        }

    def test_runtime_envelopes_technical_bindings_without_repairing_content(self):
        _, _, requests, _ = self.prepared(1)
        request = requests[0]
        report = valid_report(request)
        enveloped = envelope_equity_research_draft(
            self.draft(report), request=request, skill_execution=report["skill_execution"],
            report_id="equity-report-envelope",
        )
        self.assertEqual(request["request_hash"], enveloped["bindings"]["holding_research_request_hash"])
        broken = self.draft(report)
        broken["bindings"] = {"portfolio_hash": "0" * 64}
        with self.assertRaisesRegex(CommonStockResearchError, "DRAFT_KEYS_INVALID"):
            envelope_equity_research_draft(
                broken, request=request, skill_execution=report["skill_execution"],
                report_id="bad",
            )

    def test_three_slots_refill_and_results_bind_by_security_not_return_order(self):
        _, _, requests, coverage = self.prepared(4)
        by_id = {item["security"]["security_id"]: item for item in requests}
        dispatch = BoundedResearchDispatch(by_id, coverage)
        first = dispatch.next_dispatches()
        self.assertEqual(3, len(first))
        for index, request in enumerate(first):
            dispatch.record_started(
                request["security"]["security_id"], child_session_id=f"session-{index}",
                started_at=f"2026-09-11T12:00:0{index}Z",
            )
        second_security = first[1]["security"]["security_id"]
        dispatch.record_completed(
            second_security, report=valid_report(by_id[second_security]),
            report_ref=f"reports/{second_security}/equity-research.json",
            completed_at="2026-09-11T12:01:00Z",
        )
        refill = dispatch.next_dispatches()
        self.assertEqual(1, len(refill))
        fourth = refill[0]["security"]["security_id"]
        dispatch.record_started(
            fourth, child_session_id="session-4", started_at="2026-09-11T12:01:01Z"
        )
        for offset, security_id in enumerate((first[2]["security"]["security_id"], first[0]["security"]["security_id"], fourth), 2):
            dispatch.record_completed(
                security_id, report=valid_report(by_id[security_id]),
                report_ref=f"reports/{security_id}/equity-research.json",
                completed_at=f"2026-09-11T12:0{offset}:00Z",
            )
        final = dispatch.finalize()
        self.assertEqual("RESEARCH_COMPLETE", final["stage_status"])
        self.assertTrue(parallel_intervals_overlap(dispatch.events))
        self.assertEqual(set(by_id), {item["security_id"] for item in final["items"]})

    def test_single_failure_does_not_remove_other_results(self):
        _, _, requests, coverage = self.prepared(2)
        by_id = {item["security"]["security_id"]: item for item in requests}
        dispatch = BoundedResearchDispatch(by_id, coverage)
        for index, request in enumerate(dispatch.next_dispatches()):
            dispatch.record_started(
                request["security"]["security_id"], child_session_id=f"session-{index}",
                started_at=f"2026-09-11T12:00:0{index}Z",
            )
        failed, passed = list(by_id)
        bad = valid_report(by_id[failed])
        bad["claims"][0]["evidence_refs"] = ["unknown-evidence"]
        with self.assertRaisesRegex(CommonStockResearchError, "EVIDENCE_CLOSURE"):
            dispatch.record_completed(
                failed, report=bad, report_ref="bad.json", completed_at="2026-09-11T12:01:00Z"
            )
        dispatch.record_failed(failed, failure_code="REPORT_VALIDATION_FAILED", completed_at="2026-09-11T12:01:01Z")
        dispatch.record_completed(
            passed, report=valid_report(by_id[passed]), report_ref="good.json",
            completed_at="2026-09-11T12:01:02Z",
        )
        final = dispatch.finalize()
        self.assertEqual("PARTIAL_RESEARCH", final["stage_status"])
        self.assertEqual({"FAILED", "RESEARCHED"}, {item["coverage_status"] for item in final["items"]})

    def test_serial_mode_is_reported_and_explicit_retry_keeps_old_invocation(self):
        _, _, requests, coverage = self.prepared(2, effective=1, reason="环境仅允许一个活跃 Subagent")
        self.assertEqual("SERIAL", coverage["execution_mode"])
        self.assertEqual("环境仅允许一个活跃 Subagent", coverage["execution_mode_reason"])
        retry = build_retry_request(requests[0], retry_sequence=1)
        self.assertNotEqual(requests[0]["invocation_id"], retry["invocation_id"])
        self.assertNotEqual(requests[0]["request_hash"], retry["request_hash"])

    def test_item_timeout_releases_slot_and_batch_budget_stops_remaining_work(self):
        _, _, requests, coverage = self.prepared(2, effective=1, reason="测试超时")
        coverage["per_item_timeout_seconds"] = 10
        coverage["batch_budget_seconds"] = 60
        coverage["coverage_hash"] = canonical_hash({
            key: value for key, value in coverage.items() if key != "coverage_hash"
        })
        by_id = {item["security"]["security_id"]: item for item in requests}
        dispatch = BoundedResearchDispatch(by_id, coverage)
        first = dispatch.next_dispatches()[0]
        dispatch.record_started(
            first["security"]["security_id"], child_session_id="timeout-session",
            started_at="2026-09-11T12:00:00Z",
        )
        dispatch.expire(observed_at="2026-09-11T12:00:11Z")
        self.assertEqual("TIMEOUT", dispatch.coverage["items"][0]["execution_status"])
        self.assertEqual(1, len(dispatch.next_dispatches()))
        second = dispatch.next_dispatches()[0]
        dispatch.record_started(
            second["security"]["security_id"], child_session_id="budget-session",
            started_at="2026-09-11T12:00:12Z",
        )
        dispatch.expire(observed_at="2026-09-11T12:01:01Z")
        self.assertEqual("RESEARCH_BATCH_BUDGET_EXHAUSTED", dispatch.coverage["items"][1]["failure_code"])

    def test_cancel_preserves_completed_report_and_stops_new_dispatch(self):
        _, _, requests, coverage = self.prepared(2, effective=1, reason="测试串行取消")
        by_id = {item["security"]["security_id"]: item for item in requests}
        dispatch = BoundedResearchDispatch(by_id, coverage)
        first = dispatch.next_dispatches()[0]
        security_id = first["security"]["security_id"]
        dispatch.record_started(security_id, child_session_id="session-1", started_at="2026-09-11T12:00:00Z")
        dispatch.record_completed(
            security_id, report=valid_report(by_id[security_id]), report_ref="first.json",
            completed_at="2026-09-11T12:01:00Z",
        )
        dispatch.cancel(cancelled_at="2026-09-11T12:01:01Z")
        self.assertEqual([], dispatch.next_dispatches())
        final = dispatch.finalize()
        self.assertEqual("CANCELLED", final["stage_status"])
        self.assertIn("RESEARCHED", {item["coverage_status"] for item in final["items"]})

    def test_skeptic_isolation_and_cio_receives_complete_validated_report(self):
        _, _, requests, _ = self.prepared(1)
        request = requests[0]
        report = valid_report(request)
        skeptic = {
            "agent": "runtime_skeptic", "mode": "INDEPENDENT_FIRST_PASS",
            "security_id": request["security"]["security_id"],
            "allowed_evidence_ids": request["allowed_evidence_ids"],
        }
        validate_skeptic_first_pass_input(skeptic)
        polluted = copy.deepcopy(skeptic)
        polluted["equity_research_report"] = report
        with self.assertRaisesRegex(ValueError, "CONTEXT_ISOLATION_VIOLATION"):
            validate_skeptic_first_pass_input(polluted)
        cio_input = build_cio_equity_research_input(
            [report], requests={request["security"]["security_id"]: request}
        )
        self.assertIn("sections", cio_input["reports"][0])
        self.assertIn("claims", cio_input["reports"][0])

    def test_chinese_report_is_same_source_and_legal_source_words_are_not_rejected(self):
        handoff, _, request = research_request()
        report = valid_report(request)
        report["claims"][0]["statement"] = "来源文件标题含 BUY/HOLD，但本句不构成交易建议。"
        gate = gate_for(handoff)
        evidence = [item for item in gate["allowed_evidence"] if item["evidence_id"] in request["allowed_evidence_ids"]]
        markdown = render_equity_research_markdown(report, request=request, evidence=evidence)
        self.assertIn(report["research_summary"]["summary"], markdown)
        self.assertIn(report["claims"][0]["statement"], markdown)
        self.assertIn("source_id=`synthetic-sec`", markdown)
        self.assertIn("不是上涨或盈利概率", markdown)
        with tempfile.TemporaryDirectory() as temp:
            paths = persist_equity_research_report(
                Path(temp), report=report, request=request, evidence=evidence
            )
            self.assertTrue(Path(paths["json"]).is_file())
            self.assertTrue(Path(paths["markdown"]).is_file())
            self.assertEqual(report, json.loads(Path(paths["json"]).read_text(encoding="utf-8")))
            Path(paths["markdown"]).write_text("被篡改的展示文件\n", encoding="utf-8")
            with self.assertRaisesRegex(CommonStockResearchError, "MARKDOWN_MISMATCH"):
                validate_persisted_equity_research_pair(
                    json_path=Path(paths["json"]), markdown_path=Path(paths["markdown"]),
                    request=request, evidence=evidence,
                )

    def test_runtime_model_selection_defaults_accepts_supported_and_rejects_unknown(self):
        product_root = ROOT / "product"
        self.assertEqual(
            "gpt-5.6-terra",
            select_product_runtime_model(product_root, requested_model=None),
        )
        self.assertEqual(
            "gpt-5.6-terra",
            select_product_runtime_model(product_root, requested_model="gpt-5.6-terra"),
        )
        with self.assertRaisesRegex(ValueError, "PRODUCT_RUNTIME_MODEL_UNSUPPORTED"):
            select_product_runtime_model(product_root, requested_model="unknown-model")

    def test_render_preserves_assumptions_types_and_all_claims_without_repetition(self):
        handoff, _, request = research_request()
        report = valid_report(request)
        report["claims"][0]["kind"] = "FACT"
        original = copy.deepcopy(report)
        markdown = render_equity_research_markdown(
            report, request=request, evidence=gate_for(handoff)["allowed_evidence"]
        )
        for claim in report["claims"]:
            self.assertEqual(1, markdown.count(claim["statement"]))
            self.assertIn(f"`{claim['kind']}`", markdown)
        for assumption in report["assumptions"]:
            self.assertIn(assumption["statement"], markdown)
            self.assertIn(assumption["rationale"], markdown)
        self.assertEqual(original, report)

    def test_render_preserves_partial_period_source_unit_and_publication(self):
        handoff, _, request = research_request()
        report = valid_report(request)
        evidence = gate_for(handoff)["allowed_evidence"]
        fact = next(item for item in evidence if item["evidence_id"] == report["claims"][0]["evidence_refs"][0])
        fact["metadata"] = {
            "period_start": "2025-10-01", "period_end": "2026-06-30",
            "context_type": "duration", "fiscal_period": "FY", "form": "10-K",
            "unit": "USD", "published_at": "2026-08-10T12:00:00Z",
            "source_locator": "https://example.org/filing(1).json",
        }
        markdown = render_equity_research_markdown(report, request=request, evidence=evidence)
        for value in ("2025-10-01", "2026-06-30", "duration", "USD", "2026-08-10T12:00:00Z"):
            self.assertIn(value, markdown)
        self.assertIn("https://example.org/filing%281%29.json", markdown)
        self.assertEqual("FY", fact["metadata"]["fiscal_period"])

    def test_fact_with_same_duration_period_does_not_require_duplicate_period_text(self):
        handoff, _, request = research_request()
        report = valid_report(request, evidence_refs=request["allowed_evidence_ids"])
        report["claims"][0].update(
            kind="FACT",
            statement="两项财务事实来自同一个可比期间。",
        )
        evidence = gate_for(handoff)["allowed_evidence"]
        for item in evidence:
            item["metadata"] = {
                "context_type": "duration",
                "period_start": "2025-10-01",
                "period_end": "2026-06-30",
            }
        markdown = render_equity_research_markdown(
            report, request=request, evidence=evidence
        )
        self.assertIn(report["claims"][0]["statement"], markdown)

    def test_fact_with_different_duration_periods_rejects_omitted_date(self):
        handoff, _, request = research_request()
        report = valid_report(request, evidence_refs=request["allowed_evidence_ids"])
        report["claims"][0].update(
            kind="FACT",
            statement="收入与现金流均对应 2025-09-30 至 2026-06-30。",
        )
        evidence = gate_for(handoff)["allowed_evidence"]
        starts = dict(zip(
            request["allowed_evidence_ids"], ("2025-09-30", "2025-10-01"), strict=True
        ))
        for item in evidence:
            if item["evidence_id"] not in starts:
                continue
            item["metadata"] = {
                "context_type": "duration",
                "period_start": starts[item["evidence_id"]],
                "period_end": "2026-06-30",
            }
        with self.assertRaisesRegex(
            CommonStockResearchError,
            "EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE:claim-core:2025-10-01",
        ):
            render_equity_research_markdown(
                report, request=request, evidence=evidence
            )

    def test_fact_with_different_duration_periods_accepts_every_actual_date(self):
        handoff, _, request = research_request()
        report = valid_report(request, evidence_refs=request["allowed_evidence_ids"])
        report["claims"][0].update(
            kind="FACT",
            statement=(
                "收入期间为 2025年9月30日至2026年6月30日；"
                "现金流期间为 2025年10月1日至2026年6月30日。"
            ),
        )
        evidence = gate_for(handoff)["allowed_evidence"]
        starts = dict(zip(
            request["allowed_evidence_ids"], ("2025-09-30", "2025-10-01"), strict=True
        ))
        for item in evidence:
            if item["evidence_id"] not in starts:
                continue
            item["metadata"] = {
                "context_type": "duration",
                "period_start": starts[item["evidence_id"]],
                "period_end": "2026-06-30",
            }
        markdown = render_equity_research_markdown(
            report, request=request, evidence=evidence
        )
        self.assertIn("2025年10月1日", markdown)

    def test_interpretation_with_multiple_periods_is_left_to_semantic_eval(self):
        handoff, _, request = research_request()
        report = valid_report(request, evidence_refs=request["allowed_evidence_ids"])
        evidence = gate_for(handoff)["allowed_evidence"]
        starts = dict(zip(
            request["allowed_evidence_ids"], ("2025-09-30", "2025-10-01"), strict=True
        ))
        for item in evidence:
            if item["evidence_id"] not in starts:
                continue
            item["metadata"] = {
                "context_type": "duration",
                "period_start": starts[item["evidence_id"]],
                "period_end": "2026-06-30",
            }
        markdown = render_equity_research_markdown(
            report, request=request, evidence=evidence
        )
        self.assertIn(report["claims"][0]["statement"], markdown)

    def test_render_keeps_per_condition_trigger_and_indicator_references(self):
        handoff, _, request = research_request()
        report = valid_report(request)
        report["reevaluation_triggers"][0]["claim_refs"] = ["claim-counter"]
        markdown = render_equity_research_markdown(
            report, request=request, evidence=gate_for(handoff)["allowed_evidence"]
        )
        for collection, identity in (
            ("invalidation_conditions", "condition_id"),
            ("reevaluation_triggers", "trigger_id"),
            ("monitoring_indicators", "indicator_id"),
        ):
            for item in report[collection]:
                block = markdown.split(f"- **{item[identity]}**：", 1)[1].split("\n\n", 1)[0]
                for ref in item.get("claim_refs", []):
                    self.assertIn(f"`{ref}`", block)
                if item["evidence_refs"]:
                    self.assertIn("Evidence：[E", block)
                    for ref in item["evidence_refs"]:
                        self.assertNotIn(f"`{ref}`", block)

    def test_render_uses_short_body_references_and_complete_same_source_appendix(self):
        handoff, _, request = research_request()
        report = valid_report(request)
        markdown = render_equity_research_markdown(
            report, request=request, evidence=gate_for(handoff)["allowed_evidence"]
        )
        body, appendix = markdown.split("## Evidence 来源与时间", 1)
        referenced = {
            ref
            for claim in report["claims"]
            for ref in claim["evidence_refs"]
        }
        self.assertIn("Evidence：[E", body)
        for evidence_id in referenced:
            self.assertNotIn(evidence_id, body)
            self.assertIn(evidence_id, appendix)
        self.assertIn("source_id=`synthetic-sec`", appendix)
        self.assertIn("retrieved_at=", appendix)

    def test_render_unknown_period_does_not_invent_dates_or_active_source_links(self):
        handoff, _, request = research_request()
        report = valid_report(request)
        evidence = gate_for(handoff)["allowed_evidence"]
        for locator in (None, "javascript:alert(1)", "https://[broken"):
            with self.subTest(locator=locator):
                for fact in evidence:
                    fact["source_locator"] = locator
                markdown = render_equity_research_markdown(report, request=request, evidence=evidence)
                self.assertNotIn("[原始资料](", markdown)
                self.assertIn("期间开始：未知", markdown)
                self.assertIn("期间结束：未知", markdown)
                self.assertNotIn("javascript:", markdown)

    def test_progress_keeps_execution_research_eval_and_coverage_separate(self):
        _, _, _, coverage = self.prepared(2)
        rendered = render_research_progress(coverage)
        for phrase in ("执行状态", "研究状态", "Eval 状态", "覆盖状态", "不代表完整组合决策"):
            self.assertIn(phrase, rendered)

    def test_stage_keeps_full_mixed_portfolio_and_stops_before_downstream_decision(self):
        handoff = confirmed_handoff()
        council_request = build_common_stock_council_request(
            handoff, request_id="research-stage", research_question="分析普通股持仓"
        )
        agent, skills = bindings()
        with patch(
            "product.runtime.live_input.value_portfolio",
            side_effect=AssertionError("普通股研究不得调用完整组合估值"),
        ):
            stage = prepare_common_stock_research_stage(
                handoff, council_request, gate_for(handoff, "stage-run"), run_id="stage-run",
                batch_id="stage-batch", agent_binding=agent, skill_bindings=skills,
            )
        self.assertEqual(len(handoff["portfolio"]["positions"]), stage["planning"]["total"])
        self.assertEqual(handoff["portfolio_hash"], stage["coverage"]["portfolio_hash"])
        self.assertEqual([], stage["downstream_stages_started"])
        self.assertFalse(stage["complete_portfolio_decision"])
        self.assertEqual("PARTIAL_RESEARCH", stage["coverage"]["stage_status"])
        self.assertNotIn("decision", {key for key in stage if key != "complete_portfolio_decision"})
        self.assertNotIn("risk", json.dumps(stage, ensure_ascii=False).lower())

    def test_stage_rejects_wrong_portfolio_hash_before_dispatch(self):
        handoff = confirmed_handoff()
        council_request = build_common_stock_council_request(
            handoff, request_id="research-stage", research_question="分析普通股持仓"
        )
        council_request["portfolio_hash"] = "0" * 64
        council_request["request_hash"] = canonical_hash({
            key: value for key, value in council_request.items() if key != "request_hash"
        })
        agent, skills = bindings()
        with self.assertRaisesRegex(CouncilPlanningError, "BINDING_INVALID"):
            prepare_common_stock_research_stage(
                handoff, council_request, gate_for(handoff, "stage-run"), run_id="stage-run",
                batch_id="stage-batch", agent_binding=agent, skill_bindings=skills,
            )

    def test_company_preparation_may_be_subset_of_same_frozen_gate(self):
        handoff = stock_handoff(1)
        security_id = handoff["portfolio"]["positions"][0]["security_id"]
        gate = gate_for(handoff, "stage-run")
        base_ids = list(gate["allowed_evidence_ids"])
        supplemental = {
            "evidence_id": "ev-official-macro-extra", "security_id": "US:MARKET",
            "semantic_field": "official_macro_context", "value": "测试补充事实",
            "source_id": "official-macro-test", "as_of": "2026-06-30T00:00:00Z",
            "retrieved_at": "2026-07-01T00:00:00Z",
        }
        gate["allowed_evidence"].append(supplemental)
        gate["allowed_evidence_ids"] = sorted([*base_ids, supplemental["evidence_id"]])
        gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
        gate["bundle_hash"] = canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
        request = build_common_stock_council_request(
            handoff, request_id="research-stage", research_question="分析普通股持仓",
        )
        preparation = {
            "run_id": "stage-run", "handoff_id": handoff["handoff_id"],
            "handoff_hash": handoff["handoff_hash"], "portfolio_hash": handoff["portfolio_hash"],
            "common_cutoff": gate["decision_cutoff"],
            "items": [{"security_id": security_id, "status": "READY", "evidence_ids": base_ids}],
        }
        preparation["preparation_hash"] = canonical_hash(preparation)
        agent, skills = bindings()
        stage = prepare_common_stock_research_stage(
            handoff, request, gate, run_id="stage-run", batch_id="stage-batch",
            agent_binding=agent, skill_bindings=skills, data_preparation=preparation,
        )
        self.assertEqual(1, len(stage["holding_requests"]))
        self.assertIn(supplemental["evidence_id"], stage["holding_requests"][0]["allowed_evidence_ids"])
        invalid = copy.deepcopy(preparation)
        invalid["items"][0]["evidence_ids"] = sorted([*base_ids, "ev-not-in-gate"])
        invalid["preparation_hash"] = canonical_hash({key: value for key, value in invalid.items() if key != "preparation_hash"})
        with self.assertRaisesRegex(CommonStockResearchError, "RESEARCH_DATA_PREPARATION_EVIDENCE_MISMATCH"):
            prepare_common_stock_research_stage(
                handoff, request, gate, run_id="stage-run", batch_id="stage-batch",
                agent_binding=agent, skill_bindings=skills, data_preparation=invalid,
            )

    def test_missing_etf_option_prices_and_margin_do_not_block_stock_research(self):
        handoff = confirmed_handoff()
        council_request = build_common_stock_council_request(
            handoff, request_id="research-stage", research_question="分析普通股持仓"
        )
        agent, skills = bindings()
        stage = prepare_common_stock_research_stage(
            handoff, council_request, gate_for(handoff, "stage-run"), run_id="stage-run",
            batch_id="stage-batch", agent_binding=agent, skill_bindings=skills,
        )
        serialized_requests = json.dumps(stage["holding_requests"], ensure_ascii=False)
        self.assertNotIn("margin", serialized_requests.lower())
        self.assertNotIn("quote_price", serialized_requests)
        self.assertGreaterEqual(len(stage["holding_requests"]), 2)
        self.assertEqual(
            {"ETF", "OPTION"},
            {
                item["asset_type"] for item in stage["coverage"]["items"]
                if item["coverage_status"] == "CAPABILITY_GAP"
            },
        )

    def test_no_common_stock_produces_no_dispatch_but_retains_asset(self):
        payload = json.loads(PORTFOLIO_FIXTURE.read_text(encoding="utf-8"))
        payload["draft_id"] = "draft-etf-only"
        payload["positions"] = [
            item for item in payload["positions"] if item["asset_type"] == "ETF"
        ]
        handoff = build_handoff(
            build_manual_draft(payload), confirmed=True,
            confirmed_at="2026-09-11T20:05:00+08:00",
        )
        council_request = build_common_stock_council_request(
            handoff, request_id="research-stage", research_question="分析普通股持仓"
        )
        agent, skills = bindings()
        empty_gate = {
            "run_id": "stage-run",
            "decision_cutoff": "2026-09-11T12:00:00Z",
            "input_evidence_ids": [], "allowed_evidence_ids": [],
            "excluded_evidence_ids": [], "allowed_evidence": [], "excluded": [],
        }
        empty_gate["bundle_hash"] = canonical_hash(empty_gate)
        stage = prepare_common_stock_research_stage(
            handoff, council_request, empty_gate, run_id="stage-run",
            batch_id="stage-batch", agent_binding=agent, skill_bindings=skills,
        )
        self.assertEqual([], stage["holding_requests"])
        self.assertEqual("NO_COMMON_STOCKS", stage["coverage"]["stage_status"])
        self.assertEqual("CAPABILITY_GAP", stage["coverage"]["items"][0]["coverage_status"])


class CommonStockFocusedEvalTests(unittest.TestCase):
    def test_rubric_checks_amount_recency_counterevidence_and_conditional_scenarios(self):
        rubric = json.loads(
            (ROOT / "evals/grading/common-stock-research-rubric-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            "common-stock-research-semantic/1.7.0", rubric["rubric_id"]
        )
        manifest = json.loads(
            (ROOT / "product/version-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            rubric["rubric_id"],
            manifest["assurance"]["common-stock-research-rubric"],
        )
        from product.runtime.hashing import file_hash
        self.assertEqual(
            file_hash(ROOT / "evals/grading/common-stock-research-rubric-v1.json"),
            manifest["assurance"]["common-stock-research-rubric-sha256"],
        )
        combined = "\n".join(rubric["dimensions"].values())
        for phrase in (
            "$1.8 billion 必须等价于18亿美元",
            "较新且适用的重要事实",
            "不可比期间金额变化",
            "fresh-start",
            "两期原值和绝对变化",
            "优先保留实际数值",
            "向好/向坏",
        ):
            self.assertIn(phrase, combined)

    def prepare_job(self, temp: str, *, report=None):
        handoff, _, request = research_request()
        report = report or valid_report(request)
        root = Path(temp)
        report_path = root / "equity-research.json"
        request_path = root / "holding-request.json"
        gate_path = root / "gate.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        request_path.write_text(json.dumps(request), encoding="utf-8")
        gate = gate_for(handoff)
        gate_path.write_text(json.dumps(gate), encoding="utf-8")
        report_path.with_suffix(".md").write_text(
            render_equity_research_markdown(
                report,
                request=request,
                evidence=gate["allowed_evidence"],
            ),
            encoding="utf-8",
        )
        job = prepare_common_stock_eval_job(
            report_path=report_path,
            request_path=request_path,
            gate_path=gate_path,
            rubric_path=ROOT / "evals/grading/common-stock-research-rubric-v1.json",
            output_dir=root / "eval-job", eval_id="eval-common-stock-1",
        )
        return request, report, root / "eval-job", job

    def test_eval_job_binds_same_source_chinese_markdown_when_available(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, _, job = self.prepare_job(temp)
            self.assertEqual(
                "common-stock-research-eval-job/1.1.0", job["schema_version"]
            )
            self.assertIn("report_markdown", job)
            self.assertIn("置信度含义", job["report_markdown"])
            self.assertIn("report_markdown", job["source_hashes"])

    def test_eval_job_rejects_markdown_not_rendered_from_report(self):
        with tempfile.TemporaryDirectory() as temp:
            handoff, _, request = research_request()
            report = valid_report(request)
            root = Path(temp)
            report_path = root / "equity-research.json"
            request_path = root / "holding-request.json"
            gate_path = root / "gate.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            report_path.with_suffix(".md").write_text("不同源内容", encoding="utf-8")
            request_path.write_text(json.dumps(request), encoding="utf-8")
            gate_path.write_text(json.dumps(gate_for(handoff)), encoding="utf-8")
            with self.assertRaisesRegex(
                CommonStockResearchError, "RESEARCH_OUTPUT_MARKDOWN_MISMATCH"
            ):
                prepare_common_stock_eval_job(
                    report_path=report_path,
                    request_path=request_path,
                    gate_path=gate_path,
                    rubric_path=ROOT / "evals/grading/common-stock-research-rubric-v1.json",
                    output_dir=root / "eval-job",
                    eval_id="eval-markdown-mismatch",
                )

    @staticmethod
    def semantic_result(job, *, failing=(), model="gpt-test-evaluator"):
        dimensions = {}
        for name in EVAL_DIMENSIONS:
            failed = name in set(failing)
            dimensions[name] = {
                "status": "FAIL" if failed else "PASS",
                "grade": 1 if failed else 2,
                "claim_refs": ["claim-core"],
                "evidence_refs": [job["report"]["claims"][0]["evidence_refs"][0]],
                "rationale": "公司专属内容和引用满足要求。" if not failed else "内容空泛或缺少依据。",
            }
        value = {
            "schema_version": "common-stock-research-eval-result/1.0.0",
            "eval_id": job["eval_id"], "run_id": job["run_id"],
            "invocation_id": job["invocation_id"], "security_id": job["security_id"],
            "input_hash": job["input_hash"], "rubric_id": job["rubric_id"],
            "model": model,
            "status": "FAIL" if failing else "PASS", "dimensions": dimensions,
        }
        value["result_hash"] = canonical_hash(value)
        return value

    def test_eval_reads_actual_report_and_produces_bound_result_and_chinese_report(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, eval_dir, job = self.prepare_job(temp)
            prompt = build_common_stock_eval_prompt(eval_dir)
            self.assertIn(job["input_hash"], prompt)
            self.assertIn("不得补充外部事实", prompt)
            raw = Path(temp) / "semantic.json"
            raw.write_text(json.dumps(self.semantic_result(job)), encoding="utf-8")
            result = finalize_common_stock_eval_job(eval_dir=eval_dir, semantic_result_path=raw)
            self.assertEqual("PASS", result["status"])
            self.assertTrue((eval_dir / "eval/result.json").is_file())
            self.assertIn("普通股研究 Eval", (eval_dir / "eval/report.md").read_text(encoding="utf-8"))

    def test_eval_revalidates_calculation_refs_from_actual_mcp_events(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            handoff, _, request = research_request()
            report = valid_report(request)
            report["claims"][0]["calculation_refs"] = ["calc-one"]
            report["artifact_refs"] = ["calc-one"]
            root = Path(temp)
            report_path, request_path, gate_path = (
                root / "report.json", root / "request.json", root / "gate.json"
            )
            report_path.write_text(json.dumps(report), encoding="utf-8")
            request_path.write_text(json.dumps(request), encoding="utf-8")
            gate_path.write_text(json.dumps(gate_for(handoff)), encoding="utf-8")
            event_path = root / "events.jsonl"
            event_path.write_text(json.dumps({
                "event_type": "mcp_tool_result",
                "tool": "fixture_math.calculate",
                "invocation_id": report["invocation_id"],
                "calculation_id": "calc-one",
            }) + "\n", encoding="utf-8")
            job = prepare_common_stock_eval_job(
                report_path=report_path, request_path=request_path, gate_path=gate_path,
                rubric_path=ROOT / "evals/grading/common-stock-research-rubric-v1.json",
                output_dir=root / "eval-ok", eval_id="eval-calculation",
                mcp_events_path=event_path,
            )
            self.assertIn("mcp_events", job["source_hashes"])

            event_path.write_text(json.dumps({
                "event_type": "mcp_tool_result",
                "tool": "fixture_math.calculate",
                "invocation_id": "another-invocation",
                "calculation_id": "calc-one",
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(CommonStockResearchError, "CALCULATION_REFERENCE_DANGLING"):
                prepare_common_stock_eval_job(
                    report_path=report_path, request_path=request_path, gate_path=gate_path,
                    rubric_path=ROOT / "evals/grading/common-stock-research-rubric-v1.json",
                    output_dir=root / "eval-bad", eval_id="eval-calculation-bad",
                    mcp_events_path=event_path,
                )

    def test_empty_or_ungrounded_semantic_dimensions_cannot_pass_quality_eval(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, eval_dir, job = self.prepare_job(temp)
            raw = Path(temp) / "semantic.json"
            invalid = self.semantic_result(job, failing={
                "business_understanding", "comparable_financial_analysis",
                "thesis_causal_chain", "valuation_grounding",
            })
            invalid["status"] = "PASS"
            invalid["result_hash"] = canonical_hash({
                key: value for key, value in invalid.items() if key != "result_hash"
            })
            raw.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaisesRegex(CommonStockEvalError, "AGGREGATE_INVALID"):
                finalize_common_stock_eval_job(eval_dir=eval_dir, semantic_result_path=raw)

    def test_report_with_action_or_dangling_evidence_never_reaches_semantic_eval(self):
        _, _, request = research_request()
        for mutation in ("action", "evidence"):
            report = valid_report(request)
            if mutation == "action":
                report["trade_action"] = "HOLD"
            else:
                report["claims"][0]["evidence_refs"] = ["missing-evidence"]
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(CommonStockResearchError):
                    self.prepare_job(temp, report=report)

    def test_valuation_failure_is_visible_even_when_other_dimensions_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, eval_dir, job = self.prepare_job(temp)
            raw = Path(temp) / "semantic.json"
            result = self.semantic_result(job, failing={"valuation_grounding"})
            raw.write_text(json.dumps(result), encoding="utf-8")
            finalized = finalize_common_stock_eval_job(eval_dir=eval_dir, semantic_result_path=raw)
            self.assertEqual("FAIL", finalized["status"])
            self.assertEqual("FAIL", finalized["dimensions"]["valuation_grounding"]["status"])

    def test_eval_references_must_close_over_the_frozen_report_and_evidence(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            _, _, eval_dir, job = self.prepare_job(temp)
            for field, bad_value, code in (
                ("claim_refs", ["missing-claim"], "COMMON_STOCK_EVAL_CLAIM_REF_INVALID"),
                ("evidence_refs", ["missing-evidence"], "COMMON_STOCK_EVAL_EVIDENCE_REF_INVALID"),
            ):
                result = self.semantic_result(job)
                result["dimensions"]["business_understanding"][field] = bad_value
                result["result_hash"] = canonical_hash({
                    key: value for key, value in result.items() if key != "result_hash"
                })
                raw = Path(temp) / f"{field}.json"
                raw.write_text(json.dumps(result), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(
                    CommonStockEvalError, code
                ):
                    finalize_common_stock_eval_job(
                        eval_dir=eval_dir, semantic_result_path=raw
                    )

    def test_eval_hook_injects_sealed_packet_and_persists_exact_dev_eval_result(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            _, _, eval_dir, job = self.prepare_job(temp)
            invocation = eval_dir / "invocation"
            invocation.mkdir()
            environment = {
                "STOCK_AGENT_RUN_DIR": str(eval_dir),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation / "subagent-events.jsonl"),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation / "subagent-dispatches.jsonl"),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "dev_eval",
                "STOCK_AGENT_COMMON_STOCK_EVAL": EVAL_RUNTIME_VERSION,
                "STOCK_AGENT_COMMON_STOCK_EVAL_MODEL": "gpt-5.6-terra",
            }
            dispatch = {
                "hook_event_name": "PreToolUse", "session_id": "eval-parent",
                "turn_id": "eval-turn", "tool_name": "collaborationspawn_agent",
                "tool_use_id": "eval-tool", "cwd": str(ROOT),
                "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                "tool_input": {
                    "agent_type": "dev_eval", "task_name": "grade_common_stock_report",
                    "fork_turns": "none",
                    "message": build_common_stock_eval_dispatch_message(eval_dir),
                },
            }
            dispatch_record, _ = handle_hook_event(dispatch, environ=environment)
            self.assertEqual("ALLOW", dispatch_record["decision"])
            self.assertFalse(
                dispatch_record["dispatch_binding"]["parent_message_authoritative"]
            )
            start = {
                "hook_event_name": "SubagentStart", "session_id": "eval-parent",
                "turn_id": "eval-turn", "agent_id": "eval-child",
                "agent_type": "dev_eval", "model": "gpt-5.6-terra",
                "cwd": str(ROOT), "permission_mode": "workspace-write",
            }
            start_record, response = handle_hook_event(start, environ=environment)
            packet = json.loads(response["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(job["input_hash"], packet["input_manifest"]["input_hash"])
            self.assertEqual(
                canonical_hash(build_common_stock_eval_packet(
                    eval_dir, expected_model="gpt-5.6-terra"
                )),
                start_record["context_binding"]["packet_hash"],
            )
            result = self.semantic_result(job, model="gpt-5.6-terra")
            message = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            stop = {
                **start, "hook_event_name": "SubagentStop",
                "last_assistant_message": message, "stop_hook_active": False,
            }
            stop_record, _ = handle_hook_event(stop, environ=environment)
            self.assertEqual("SAVED", stop_record["output_capture"]["status"])
            self.assertEqual(
                result,
                json.loads((eval_dir / "eval/result.json").read_text(encoding="utf-8")),
            )
            validate_common_stock_eval_result(
                json.loads((eval_dir / "eval/result.json").read_text(encoding="utf-8")),
                manifest=job,
            )
            self.assertEqual(
                message,
                (invocation / "semantic-result.json").read_text(encoding="utf-8").strip(),
            )


class CommonStockNativeStageTests(unittest.TestCase):
    def test_company_stage_restores_full_profile_and_fails_closed(self):
        stage_agent, stage_skills = current_research_bindings(ROOT)
        self.assertEqual("runtime_company_analyst", stage_agent["name"])
        self.assertEqual(
            ["evidence-grounding", "company-research", "valuation", "catalyst-analysis"],
            [item["name"] for item in stage_skills],
        )
        from product.runtime.multidimensional_stage import _agent_binding
        other_mode = _agent_binding(ROOT / "product", "runtime_company_analyst")
        self.assertEqual("runtime_company_analyst", other_mode["name"])
        self.assertEqual(stage_agent, other_mode)
        self.assertEqual("3.0.20", other_mode["version"])
        with tempfile.TemporaryDirectory() as temp:
            product = Path(temp) / "product"
            profile = product / ".codex/agents/runtime_company_analyst.toml"
            profile.parent.mkdir(parents=True)
            shutil.copy2(ROOT / "product/.codex/agents/runtime_company_analyst.toml", profile)
            # 未验收的实验文件即使存在也不能成为默认或失败后的回退配置。
            experimental = profile.with_name("runtime_company_analyst_common_stock.toml")
            experimental.write_text("invalid experimental config", encoding="utf-8")
            for item in stage_skills:
                skill = product / "skills" / item["name"] / "SKILL.md"
                skill.parent.mkdir(parents=True)
                shutil.copy2(ROOT / "product/skills" / item["name"] / "SKILL.md", skill)
            self.assertEqual(stage_agent, current_research_bindings(Path(temp))[0])
            original = profile.read_text(encoding="utf-8")
            for altered in (original.replace('name = "runtime_company_analyst"', 'name = "wrong"', 1),
                            original.replace('sandbox_mode = "read-only"', 'sandbox_mode = "workspace-write"', 1),
                            original.replace('path = "skills/company-research"', 'path = "skills/research-report-analysis"', 1)):
                profile.write_text(altered, encoding="utf-8")
                with self.assertRaises(CommonStockStageError):
                    current_research_bindings(Path(temp))
            profile.unlink()
            with self.assertRaisesRegex(CommonStockStageError, "COMMON_STOCK_AGENT_PROFILE_INVALID"):
                current_research_bindings(Path(temp))

    def test_dispatch_without_attachment_does_not_advertise_attachment_query(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            packet = build_common_stock_dispatch_packet(ROOT, run, task["task_name"])
            invocation = json.loads((run / task["invocation_path"]).read_text())
        self.assertIsNone(packet["equity_research_attachments"])
        self.assertNotIn("attachment_query_tool", packet["tool_context"])
        self.assertNotIn("equity_research_attachments.query", packet["instruction"])
        self.assertNotIn("equity_research_attachments.query", invocation["tool_permissions"])
        self.assertEqual(invocation["tool_permissions"], packet["tool_context"]["logical_permissions"])
        self.assertIn("fixture_runtime.query", packet["tool_context"]["query_tool"])

    def test_stage_reconstructs_dispatch_with_equity_attachment_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            run_id = "attachment-stage-run"
            gate = gate_for(handoff, run_id)
            security_id = handoff["portfolio"]["positions"][0]["security_id"]
            evidence_ref = gate["allowed_evidence_ids"][0]
            item = {
                "item_id": "attachment-item",
                "claim_status": "VERIFIED_FACT",
                "source_id": "synthetic-sec",
                "as_of": "2026-06-30T00:00:00Z",
                "retrieved_at": "2026-07-01T00:00:00Z",
                "published_at": "2026-07-01T00:00:00Z",
                "period": "2026Q2",
                "definition": "synthetic acceptance fact",
                "unit": "USD",
                "evidence_refs": [evidence_ref],
                "calculation_ref": None,
            }
            groups = {
                name: {
                    "status": "PARTIAL",
                    "coverage": "synthetic attachment reconstruction",
                    "reason": None,
                    "items": [copy.deepcopy(item) | {"item_id": name}],
                }
                for name in (
                    "guidance", "earnings_quality", "debt_liquidity",
                    "operating_kpis", "governance", "earnings_expectations",
                    "financial_ratios",
                )
            }
            supplement = build_fundamental_supplement(
                supplement_id="attachment-supplement",
                security_id=security_id,
                decision_cutoff=gate["decision_cutoff"],
                groups=groups,
            )
            package = build_equity_research_package(
                package_id="attachment-package",
                run_id=run_id,
                security_id=security_id,
                decision_cutoff=gate["decision_cutoff"],
                gate_bundle_hash=gate["bundle_hash"],
                artifacts={"fundamental_supplement": supplement},
            )
            handoff_path = root / "handoff.json"
            gate_path = root / "gate.json"
            package_path = root / "equity-package.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            package_path.write_text(json.dumps(package), encoding="utf-8")

            prepare_common_stock_stage_run(
                ROOT,
                handoff_path=handoff_path,
                gate_path=gate_path,
                run_dir=root / "run",
                run_id=run_id,
                model="gpt-5.6-terra",
                equity_research_package_paths=[package_path],
            )
            _validate_common_stock_stage_run_package(ROOT, root / "run")
            task = json.loads(
                (root / "run/research/dispatch-index.json").read_text(
                    encoding="utf-8"
                )
            )["tasks"][0]
            self.assertEqual(
                package["package_hash"], task["equity_research_package_hash"]
            )
            packet = build_common_stock_dispatch_packet(
                ROOT, root / "run", task["task_name"]
            )
            self.assertIn(
                "tool_context.attachment_query_tool 读取正文",
                packet["instruction"],
            )
            self.assertEqual(
                "fixture_runtime.equity_research_attachments.query",
                packet["tool_context"]["attachment_query_tool"],
            )
            self.assertIn(
                "calculation_ref 与全部 input evidence_refs",
                packet["instruction"],
            )
            self.assertIn(
                "FY + current YTD - prior YTD",
                packet["instruction"],
            )
            invocation = json.loads(
                (root / "run" / task["invocation_path"]).read_text(encoding="utf-8")
            )
            self.assertIn(
                "equity_research_attachments.query", invocation["tool_permissions"],
            )
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {
                        "name": "equity_research_attachments.query",
                        "arguments": {
                            "run_id": run_id,
                            "agent": "runtime_company_analyst",
                            "invocation_id": invocation["invocation_id"],
                            "security_id": security_id,
                            "decision_cutoff": gate["decision_cutoff"],
                            "kinds": ["fundamental_supplement"],
                        },
                    },
                },
            ]
            stdin = io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n")
            stdout = io.StringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                serve_stdio(
                    stateless=True, default_run_dir=root / "run",
                )
            responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
            listed = {item["name"] for item in responses[0]["result"]["tools"]}
            self.assertIn("equity_research_attachments.query", listed)
            self.assertEqual(
                {"fundamental_supplement"},
                set(responses[1]["result"]["structuredContent"]["artifacts"]),
            )
            event = json.loads(
                (root / "run/events/mcp/events.jsonl").read_text(encoding="utf-8").strip()
            )
            self.assertEqual("equity_research_attachments.query", event["tool"])

    def test_stage_rejects_tampered_gate_instead_of_resigning_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff, "tampered-stage-run")
            gate["decision_cutoff"] = "2026-09-12T12:00:00Z"
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            with self.assertRaisesRegex(CommonStockResearchError, "GATE_HASH_MISMATCH"):
                prepare_common_stock_stage_run(
                    ROOT, handoff_path=handoff_path, gate_path=gate_path,
                    run_dir=root / "run", run_id="tampered-stage-run",
                    model="gpt-5.6-terra",
                )

    def test_stage_rejects_tampered_data_preparation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            data = assemble_common_stock_evidence(
                handoff, run_id="tampered-preparation-run",
                collect_security=CommonStockDataPreparationTests.collector_for(handoff),
            )
            data["preparation"]["model_calls"] = 1
            paths = root / "handoff.json", root / "gate.json", root / "preparation.json"
            for path, value in zip(paths, (handoff, data["gate"], data["preparation"]), strict=True):
                path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(CommonStockResearchError, "PREPARATION_HASH_MISMATCH"):
                prepare_common_stock_stage_run(
                    ROOT, handoff_path=paths[0], gate_path=paths[1],
                    data_preparation_path=paths[2], run_dir=root / "run",
                    run_id="tampered-preparation-run", model="gpt-5.6-terra",
                )

    def test_live_gate_requires_complete_frozen_source_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            data = assemble_common_stock_evidence(
                handoff, run_id="live-package-run",
                collect_security=CommonStockDataPreparationTests.collector_for(handoff),
            )
            data["gate"].update(
                source_mode="live-read-only", source_bundle_id="source:live-package-run",
                source_bundle_hash="b" * 64,
            )
            data["gate"]["bundle_hash"] = canonical_hash({
                key: value for key, value in data["gate"].items() if key != "bundle_hash"
            })
            data["preparation"].update(
                source_mode="live-read-only", source_bundle_id="source:live-package-run",
                source_bundle_hash="b" * 64,
            )
            data["preparation"]["preparation_hash"] = canonical_hash({
                key: value for key, value in data["preparation"].items()
                if key != "preparation_hash"
            })
            paths = root / "handoff.json", root / "gate.json", root / "preparation.json"
            for path, value in zip(paths, (handoff, data["gate"], data["preparation"]), strict=True):
                path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(CommonStockStageError, "LIVE_DATA_PACKAGE_INCOMPLETE"):
                prepare_common_stock_stage_run(
                    ROOT, handoff_path=paths[0], gate_path=paths[1],
                    data_preparation_path=paths[2], run_dir=root / "run",
                    run_id="live-package-run", model="gpt-5.6-terra",
                )

    def test_validated_live_source_bundle_is_consumed_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            run_id = "validated-live-package-run"
            collector = CommonStockDataPreparationTests.collector_for(handoff)
            result = dict(collector(handoff["portfolio"]["positions"][0]))
            result.update(
                input_evidence_ids=[item["evidence_id"] for item in result["facts"]],
                excluded=[], conflicts=[],
            )
            data = assemble_common_stock_evidence(
                handoff, run_id=run_id, collect_security=lambda _: result,
            )
            package = root / "package"
            item_root = package / "source-snapshots/item/snapshot"
            item_root.mkdir(parents=True)
            collection_input = build_common_stock_collection_portfolio(handoff)
            scoped_portfolio = dict(collection_input, positions=[collection_input["positions"][0]])
            selection = {
                "security_id": result["security_id"],
                "selection_hash": canonical_hash("validated-selection"),
            }
            snapshot = {
                "snapshot_id": "validated-snapshot",
                "snapshot_hash": canonical_hash("validated-snapshot"),
                "source_access": [], "source_selections": [selection],
            }
            calendar = {"version": "synthetic", "content_hash": "c" * 64}
            (package / "collection-input.json").write_text(json.dumps(collection_input))
            (item_root / "portfolio.json").write_text(json.dumps(scoped_portfolio))
            (item_root / "snapshot.json").write_text(json.dumps(snapshot))
            (item_root / "calendar.json").write_text(json.dumps(calendar))
            source_bundle = {
                "schema_version": "common-stock-source-bundle/1.0.0",
                "bundle_id": f"common-stock-source:{run_id}", "run_id": run_id,
                "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
                "portfolio_hash": handoff["portfolio_hash"],
                "collection_input_hash": canonical_hash(collection_input),
                "source_access": [],
                "source_access_hash": canonical_hash([]),
                "decision_cutoff": data["preparation"]["common_cutoff"],
                "items": [{
                    "security_id": result["security_id"], "status": "FROZEN",
                    "collection_input_ref": "source-snapshots/item/collection-input.json",
                    "collection_input_hash": canonical_hash(scoped_portfolio),
                    "portfolio_ref": "source-snapshots/item/snapshot/portfolio.json",
                    "portfolio_hash": canonical_hash(scoped_portfolio),
                    "snapshot_ref": "source-snapshots/item/snapshot/snapshot.json",
                    "snapshot_id": snapshot["snapshot_id"], "snapshot_hash": snapshot["snapshot_hash"],
                    "calendar_ref": "source-snapshots/item/snapshot/calendar.json",
                    "calendar_hash": canonical_hash(calendar),
                    "source_selection": selection,
                    "source_selection_hash": selection["selection_hash"], "failure_code": None,
                }],
            }
            (package / "source-snapshots/item/collection-input.json").write_text(
                json.dumps(scoped_portfolio)
            )
            source_bundle["bundle_hash"] = canonical_hash(source_bundle)
            source_bundle_path = package / "source-bundle.json"
            source_bundle_path.write_text(json.dumps(source_bundle))
            data["gate"].update(
                source_mode="live-read-only", source_bundle_id=source_bundle["bundle_id"],
                source_bundle_hash=source_bundle["bundle_hash"],
                input_evidence_ids=result["input_evidence_ids"],
            )
            data["gate"]["bundle_hash"] = canonical_hash({
                key: value for key, value in data["gate"].items() if key != "bundle_hash"
            })
            data["preparation"].update(
                source_mode="live-read-only", source_bundle_id=source_bundle["bundle_id"],
                source_bundle_hash=source_bundle["bundle_hash"],
                collection_input_hash=canonical_hash(collection_input),
                source_bundle_ref="source-bundle.json",
                collection_input_schema="live-portfolio/2.0.0",
                collection_input_ref="collection-input.json",
                authoritative_portfolio_source="portfolio-handoff-v3",
                collection_only_fields_not_for_research=[],
                peer_candidate_pool={
                    "status": "SOURCE_LIMITED",
                    "reason": "SNAPSHOT_UNIVERSE_MISSING",
                    "selection_authority": "LLM_REQUIRED",
                },
            )
            data["preparation"]["preparation_hash"] = canonical_hash({
                key: value for key, value in data["preparation"].items()
                if key != "preparation_hash"
            })
            paths = root / "handoff.json", root / "gate.json", root / "preparation.json"
            for path, value in zip(paths, (handoff, data["gate"], data["preparation"]), strict=True):
                path.write_text(json.dumps(value))
            with patch("product.mcp.live.contracts.validate_contract"), patch(
                "product.mcp.live.market.load_locked_calendar", return_value=object()
            ), patch("product.runtime.common_stock_data._security_live_result", return_value=result):
                prepared = prepare_common_stock_stage_run(
                    ROOT, handoff_path=paths[0], gate_path=paths[1],
                    data_preparation_path=paths[2], source_bundle_path=source_bundle_path,
                    run_dir=root / "run", run_id=run_id, model="gpt-5.6-terra",
                )
                self.assertEqual("PREPARED", prepared["status"])
                self.assertTrue((root / "run/evidence/source-bundle.json").is_file())
                self.assertTrue((root / "run/evidence/source-package/source-bundle.json").is_file())
                _validate_common_stock_stage_run_package(ROOT, root / "run")

                def cloned_run(name):
                    destination = root / name
                    shutil.copytree(root / "run", destination)
                    manifest_path = destination / "run_manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    manifest["output_dir"] = str(destination)
                    manifest["manifest_hash"] = canonical_hash({
                        key: value for key, value in manifest.items() if key != "manifest_hash"
                    })
                    manifest_path.write_text(json.dumps(manifest))
                    return destination

                def resign_manifest(destination):
                    manifest_path = destination / "run_manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    manifest["manifest_hash"] = canonical_hash({
                        key: value for key, value in manifest.items() if key != "manifest_hash"
                    })
                    manifest_path.write_text(json.dumps(manifest))

                conflict_run = cloned_run("tampered-conflict")
                gate_path = conflict_run / "evidence/gate.json"
                tampered_gate = json.loads(gate_path.read_text())
                tampered_gate["conflicts"] = [{
                    "conflict_key": "invented", "reason_code": "INVENTED_CONFLICT",
                    "evidence_ids": result["input_evidence_ids"],
                }]
                tampered_gate["bundle_hash"] = canonical_hash({
                    key: value for key, value in tampered_gate.items() if key != "bundle_hash"
                })
                gate_path.write_text(json.dumps(tampered_gate))
                manifest_path = conflict_run / "run_manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest["gate_hash"] = tampered_gate["bundle_hash"]
                manifest_path.write_text(json.dumps(manifest))
                resign_manifest(conflict_run)
                with self.assertRaisesRegex(CommonStockDataError, "GATE_RECONSTRUCTION_MISMATCH"):
                    validate_common_stock_source_bundle(
                        json.loads((conflict_run / "audit/portfolio-handoff.json").read_text()),
                        gate=tampered_gate,
                        preparation=json.loads(
                            (conflict_run / "evidence/data-preparation.json").read_text()
                        ),
                        source_bundle_path=(
                            conflict_run / "evidence/source-package/source-bundle.json"
                        ),
                    )

                gap_run = cloned_run("tampered-gap")
                preparation_path = gap_run / "evidence/data-preparation.json"
                tampered_preparation = json.loads(preparation_path.read_text())
                tampered_preparation["items"][0]["data_gaps"] = ["invented gap"]
                tampered_preparation["preparation_hash"] = canonical_hash({
                    key: value for key, value in tampered_preparation.items()
                    if key != "preparation_hash"
                })
                preparation_path.write_text(json.dumps(tampered_preparation))
                manifest_path = gap_run / "run_manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest["data_preparation_hash"] = tampered_preparation["preparation_hash"]
                manifest_path.write_text(json.dumps(manifest))
                resign_manifest(gap_run)
                with self.assertRaisesRegex(CommonStockDataError, "PREPARATION_EVIDENCE_MISMATCH"):
                    validate_common_stock_source_bundle(
                        json.loads((gap_run / "audit/portfolio-handoff.json").read_text()),
                        gate=json.loads((gap_run / "evidence/gate.json").read_text()),
                        preparation=tampered_preparation,
                        source_bundle_path=gap_run / "evidence/source-package/source-bundle.json",
                    )

                model_run = cloned_run("tampered-model-calls")
                preparation_path = model_run / "evidence/data-preparation.json"
                tampered_preparation = json.loads(preparation_path.read_text())
                tampered_preparation["model_calls"] = 1
                tampered_preparation["preparation_hash"] = canonical_hash({
                    key: value for key, value in tampered_preparation.items()
                    if key != "preparation_hash"
                })
                preparation_path.write_text(json.dumps(tampered_preparation))
                with self.assertRaisesRegex(CommonStockDataError, "PREPARATION_RECONSTRUCTION_MISMATCH"):
                    validate_common_stock_source_bundle(
                        json.loads((model_run / "audit/portfolio-handoff.json").read_text()),
                        gate=json.loads((model_run / "evidence/gate.json").read_text()),
                        preparation=tampered_preparation,
                        source_bundle_path=model_run / "evidence/source-package/source-bundle.json",
                    )

                snapshot_run = cloned_run("tampered-snapshot-id")
                bundle_path = snapshot_run / "evidence/source-package/source-bundle.json"
                tampered_bundle = json.loads(bundle_path.read_text())
                tampered_bundle["items"][0]["snapshot_id"] = "invented-snapshot"
                tampered_bundle["bundle_hash"] = canonical_hash({
                    key: value for key, value in tampered_bundle.items() if key != "bundle_hash"
                })
                bundle_path.write_text(json.dumps(tampered_bundle))
                for relative, hash_field, content_field in (
                    ("evidence/gate.json", "bundle_hash", "source_bundle_hash"),
                    ("evidence/data-preparation.json", "preparation_hash", "source_bundle_hash"),
                ):
                    path = snapshot_run / relative
                    value = json.loads(path.read_text())
                    value[content_field] = tampered_bundle["bundle_hash"]
                    value[hash_field] = canonical_hash({
                        key: item for key, item in value.items() if key != hash_field
                    })
                    path.write_text(json.dumps(value))
                manifest_path = snapshot_run / "run_manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest["source_bundle_hash"] = tampered_bundle["bundle_hash"]
                manifest["gate_hash"] = json.loads(
                    (snapshot_run / "evidence/gate.json").read_text()
                )["bundle_hash"]
                manifest["data_preparation_hash"] = json.loads(
                    (snapshot_run / "evidence/data-preparation.json").read_text()
                )["preparation_hash"]
                manifest_path.write_text(json.dumps(manifest))
                resign_manifest(snapshot_run)
                with self.assertRaisesRegex(CommonStockDataError, "SOURCE_ARTIFACT_HASH_MISMATCH"):
                    validate_common_stock_source_bundle(
                        json.loads((snapshot_run / "audit/portfolio-handoff.json").read_text()),
                        gate=json.loads((snapshot_run / "evidence/gate.json").read_text()),
                        preparation=json.loads(
                            (snapshot_run / "evidence/data-preparation.json").read_text()
                        ),
                        source_bundle_path=bundle_path,
                    )

                manifest_run = cloned_run("tampered-manifest")
                manifest_path = manifest_run / "run_manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest["target_concurrency"] = 99
                manifest_path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(CommonStockStageError, "MANIFEST_HASH_MISMATCH"):
                    _validate_common_stock_stage_run_package(ROOT, manifest_run)

    def test_dispatch_retains_partial_period_metadata_without_annualizing(self):
        handoff = stock_handoff(2)
        gate = gate_for(handoff, "native-stage-run")
        metadata = {
            "period_start": "2025-10-01", "period_end": "2026-06-30",
            "context_type": "duration", "fiscal_period": "FY", "form": "10-K",
            "unit": "USD", "source_locator": "https://example.org/partial-year.json",
        }
        for fact in gate["allowed_evidence"]:
            fact["metadata"] = copy.deepcopy(metadata)
        gate["bundle_hash"] = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        with tempfile.TemporaryDirectory() as temp, patch(__name__ + ".gate_for", return_value=gate):
            run, _ = self.prepare_stage(temp)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            packet = build_common_stock_dispatch_packet(ROOT, run, index["tasks"][0]["task_name"])
            for item in flattened_evidence_catalog(packet):
                for field, value in metadata.items():
                    if field == "source_locator":
                        continue
                    self.assertEqual(value, item[field])
            self.assertTrue(packet["evidence_catalog"])
            indexed_ids = [
                item["evidence_id"]
                for group in packet["evidence_catalog"]
                for item in group["items"]
            ]
            self.assertEqual(
                {item["evidence_id"] for item in flattened_evidence_catalog(packet)},
                set(indexed_ids),
            )
            self.assertIn("不代表自动可比", packet["catalog_policy"]["period_selection_rule"])
            self.assertEqual(index["tasks"][0]["packet_hash"], canonical_hash(packet))

    def test_dispatch_context_uses_exact_hook_bytes_and_fails_closed_when_oversized(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            packet = build_common_stock_dispatch_packet(ROOT, run, task["task_name"])
        context = serialize_common_stock_dispatch_context(packet)
        actual_bytes = len(context.encode("utf-8"))
        self.assertEqual(packet["context_budget"]["actual_bytes"], actual_bytes)
        self.assertLessEqual(actual_bytes, COMMON_STOCK_START_CONTEXT_MAX_BYTES)
        self.assertIn("evidence_catalog", packet["context_budget"]["section_bytes"])
        with self.assertRaisesRegex(
            CommonStockStageError, "COMMON_STOCK_START_CONTEXT_BUDGET_EXCEEDED.*largest=",
        ):
            _bound_common_stock_dispatch_packet({"oversized_section": "大" * 100_000})

    def test_attachment_and_live_calculation_references_require_successful_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            events = run / "events/mcp/events.jsonl"
            events.parent.mkdir(parents=True)
            records = [
                {
                    "event_type": "mcp_tool_result", "invocation_id": "inv-1",
                    "tool": "equity_research_attachments.query",
                    "evidence_ids": ["ev-frozen"],
                    "calculation_ids": ["calc:frozen"],
                },
                {
                    "event_type": "mcp_tool_result", "invocation_id": "inv-1",
                    "tool": "fixture_math.calculate", "calculation_id": "calc:live",
                },
            ]
            events.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            report = {
                "claims": [{
                    "evidence_refs": ["ev-frozen"],
                    "calculation_refs": ["calc:frozen", "calc:live"],
                }]
            }
            validate_delivered_research_references(
                report, run_dir=run, invocation_id="inv-1",
            )
            broken = copy.deepcopy(report)
            broken["claims"][0]["evidence_refs"].append("ev-never-returned")
            with self.assertRaisesRegex(
                CommonStockStageError, "COMMON_STOCK_EVIDENCE_NOT_DELIVERED",
            ):
                validate_delivered_research_references(
                    broken, run_dir=run, invocation_id="inv-1",
                )
            broken = copy.deepcopy(report)
            broken["claims"][0]["calculation_refs"].append("calc:never-returned")
            with self.assertRaisesRegex(
                CommonStockStageError, "COMMON_STOCK_CALCULATION_NOT_DELIVERED",
            ):
                validate_delivered_research_references(
                    broken, run_dir=run, invocation_id="inv-1",
                )

    def test_dispatch_catalog_keeps_specialized_supplement_in_gate_but_out_of_company_context(self):
        handoff = stock_handoff(1)
        gate = gate_for(handoff, "native-stage-run")
        fact = gate["allowed_evidence"][0]
        fact.update({
            "dataset": "vendor_money_flow", "source_family": "moomoo_sg",
            "source_type": "VENDOR_CALCULATED_FLOW", "batch_id": "batch-supplement",
        })
        gate["bundle_hash"] = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        with tempfile.TemporaryDirectory() as temp, patch(
            __name__ + ".gate_for", return_value=gate,
        ):
            run, _ = self.prepare_stage(temp, count=1)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            packet = _build_common_stock_dispatch_packet(ROOT, run, task)
        self.assertIn(fact["evidence_id"], gate["allowed_evidence_ids"])
        self.assertNotIn(
            fact["evidence_id"],
            {item["evidence_id"] for item in flattened_evidence_catalog(packet)},
        )
        self.assertIn("vendor_money_flow", packet["catalog_policy"]["excluded_datasets"])
        self.assertEqual(
            1,
            packet["catalog_policy"]["request_allowed_evidence_count"]
            - packet["catalog_policy"]["company_research_evidence_count"],
        )
        self.assertIn("fixture_runtime.query", packet["catalog_policy"]["provenance_rule"])

    def test_dispatch_excludes_daily_technical_market_series_from_company_research(self):
        handoff = stock_handoff(1)
        gate = gate_for(handoff, "native-stage-run")
        technical = copy.deepcopy(gate["allowed_evidence"][0])
        technical.update(
            evidence_id="ev-daily-adjusted-close",
            semantic_field="adjusted_close_price",
            dataset="historical_prices",
        )
        gate["allowed_evidence"].append(technical)
        gate["allowed_evidence_ids"].append(technical["evidence_id"])
        gate["input_evidence_ids"].append(technical["evidence_id"])
        gate["bundle_hash"] = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        with tempfile.TemporaryDirectory() as temp, patch(__name__ + ".gate_for", return_value=gate):
            run, _ = self.prepare_stage(temp, count=1)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            packet = _build_common_stock_dispatch_packet(ROOT, run, task)
        self.assertNotIn(
            technical["evidence_id"],
            {item["evidence_id"] for item in flattened_evidence_catalog(packet)},
        )
        self.assertNotIn(
            "allowed_evidence_ids", packet["holding_research_request"]
        )
        self.assertNotIn("allowed_evidence_ids", packet)
        self.assertEqual(
            1, packet["catalog_policy"]["request_allowed_evidence_count"]
            - packet["catalog_policy"]["company_research_evidence_count"],
        )

    def test_period_index_preserves_newer_and_comparable_periods_without_selecting_for_agent(self):
        handoff = stock_handoff(1)
        gate = gate_for(handoff, "native-stage-run")
        original = copy.deepcopy(gate["allowed_evidence"][0])
        original["evidence_id"] = original["evidence_id"] + "-later"
        original["metadata"] = {
            "period_start": "2026-01-01", "period_end": "2026-09-30",
            "context_type": "duration", "form": "10-Q", "unit": "USD",
        }
        original["as_of"] = "2026-09-30T00:00:00Z"
        original["retrieved_at"] = "2026-10-01T00:00:00Z"
        gate["decision_cutoff"] = "2026-10-02T00:00:00Z"
        gate["allowed_evidence"].append(original)
        gate["allowed_evidence_ids"].append(original["evidence_id"])
        gate["input_evidence_ids"].append(original["evidence_id"])
        gate["bundle_hash"] = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        with tempfile.TemporaryDirectory() as temp, patch(__name__ + ".gate_for", return_value=gate):
            run, _ = self.prepare_stage(temp, count=1)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            packet = _build_common_stock_dispatch_packet(ROOT, run, task)
        revenue = next(
            group for group in packet["evidence_catalog"]
            if group["semantic_field"] == "revenue"
        )
        self.assertEqual(2, len(revenue["items"]))
        self.assertIn(original["evidence_id"], {item["evidence_id"] for item in revenue["items"]})
        self.assertNotIn("selected_evidence_id", revenue)
        self.assertIn("不代表自动可比", packet["catalog_policy"]["period_selection_rule"])

    def test_dispatch_exposes_derived_comparison_scope_without_claiming_accounting_comparability(self):
        handoff = stock_handoff(1)
        gate = gate_for(handoff, "native-stage-run")
        derived = copy.deepcopy(gate["allowed_evidence"][0])
        derived.update(
            evidence_id="ev-derived-comparison",
            kind="derived",
            semantic_field="year_over_year_comparison",
        )
        derived["metadata"] = {
            "comparison_policy": "same-filing/nonoverlapping-fiscal-weeks/1.0.0",
            "comparability_scope": "MATCHED_METRIC_UNIT_AND_PERIOD_STRUCTURE_ONLY",
            "accounting_basis_status": "UNVERIFIED",
            "share_denominator_status": "UNVERIFIED",
            "trend_interpretation_status": "REQUIRES_EVIDENCE_REVIEW",
            "periods": [
                {"period_start": "2025-12-29", "period_end": "2026-03-29"},
                {"period_start": "2024-12-30", "period_end": "2025-03-30"},
            ],
            "comparison_limitation": "Arithmetic change only.",
        }
        gate["allowed_evidence"].append(derived)
        gate["allowed_evidence_ids"].append(derived["evidence_id"])
        gate["input_evidence_ids"].append(derived["evidence_id"])
        gate["bundle_hash"] = canonical_hash({
            key: value for key, value in gate.items() if key != "bundle_hash"
        })
        with tempfile.TemporaryDirectory() as temp, patch(__name__ + ".gate_for", return_value=gate):
            run, _ = self.prepare_stage(temp, count=1)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            packet = _build_common_stock_dispatch_packet(ROOT, run, task)
        catalog = next(
            item for item in flattened_evidence_catalog(packet)
            if item["evidence_id"] == "ev-derived-comparison"
        )
        for field in (
            "accounting_basis_status", "share_denominator_status",
            "trend_interpretation_status", "comparison_limitation",
        ):
            self.assertNotIn(field, catalog)
        self.assertEqual("UNVERIFIED", derived["metadata"]["accounting_basis_status"])
        self.assertEqual("Arithmetic change only.", derived["metadata"]["comparison_limitation"])
        self.assertIn("完整 provenance", packet["catalog_policy"]["provenance_rule"])

    def prepare_stage(self, temp: str, count: int = 2):
        root = Path(temp)
        handoff = stock_handoff(count)
        gate = gate_for(handoff, "native-stage-run")
        handoff_path, gate_path = root / "handoff.json", root / "gate.json"
        handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
        gate_path.write_text(json.dumps(gate), encoding="utf-8")
        run = root / "run"
        prepare_common_stock_stage_run(
            ROOT, handoff_path=handoff_path, gate_path=gate_path, run_dir=run,
            run_id="native-stage-run", model="gpt-5.6-terra",
        )
        return run, handoff

    def test_launch_rejects_resigned_manifest_binding_before_codex_process(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            manifest_path = run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["gate_hash"] = "f" * 64
            manifest["manifest_hash"] = canonical_hash({
                key: value for key, value in manifest.items() if key != "manifest_hash"
            })
            manifest_path.write_text(json.dumps(manifest))
            with patch("product.runtime.common_stock_stage._run_bounded_process_group") as process:
                with self.assertRaisesRegex(CommonStockStageError, "MANIFEST_BINDING_INVALID"):
                    launch_common_stock_stage(ROOT, run_dir=run)
                process.assert_not_called()

    def test_launcher_installs_parent_stop_barrier_and_documents_wait_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            with patch("product.runtime.common_stock_stage._run_bounded_process_group") as process:
                process.return_value = {
                    "stdout": "", "stderr": "expected test failure",
                    "process_exit_code": 1, "timed_out": False,
                    "local_process_group": {
                        "pid": 123, "term_sent": False, "kill_sent": False,
                        "cleanup_complete": True,
                    },
                    "remote_cancellation_status": "NOT_APPLICABLE",
                }
                result, code = launch_common_stock_stage(ROOT, run_dir=run)
            self.assertEqual("FAILED", result["status"])
            self.assertEqual(7, code)
            command = process.call_args.args[0]
            environment = process.call_args.kwargs["environment"]
            self.assertEqual(1, command.count("--ignore-user-config"))
            self.assertTrue(any(item.startswith("hooks.Stop=") for item in command))
            profile_overrides = [
                item for item in command
                if item.startswith("agents.runtime_company_analyst={")
            ]
            self.assertEqual(1, len(profile_overrides))
            self.assertNotIn("runtime_common_stock_analyst", " ".join(command))
            self.assertEqual(
                str((run / "invocation/parent-stop-events.jsonl").resolve()),
                environment["STOCK_AGENT_PARENT_STOP_LOG"],
            )
            manifest = json.loads(
                (run / "invocation/environment-manifest.json").read_text(encoding="utf-8")
            )
            selected_profile = Path(manifest["selected_company_agent_profile"])
            self.assertFalse(selected_profile.exists())  # 隔离源码在调用结束后按原契约销毁。
            self.assertIn(str(selected_profile), profile_overrides[0])
            self.assertEqual(
                hashlib.sha256((ROOT / "product/.codex/agents/runtime_company_analyst.toml").read_bytes()).hexdigest(),
                manifest["selected_company_agent_profile_hash"],
            )
            self.assertEqual(
                json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))["agent_binding"]["content_hash"],
                manifest["selected_company_agent_profile_hash"],
            )
            self.assertEqual(
                str((run / "invocation/parent-stop-events.jsonl").resolve()),
                manifest["parent_stop_log"],
            )
            prompt = (run / "invocation/prompt.txt").read_text(encoding="utf-8")
            self.assertIn("`wait_agent` 必须显式使用 `timeout_ms=600000`", prompt)
            self.assertIn("空 `receiver_thread_ids`", prompt)
            packet = build_common_stock_dispatch_packet(ROOT, run, "company_research_1")
            self.assertIn("`YYYY-MM-DD` ASCII", packet["instruction"])
            self.assertIn("不得以“上述两期/两个季度”代替期间", packet["instruction"])
            self.assertIn("不得以固定 wait 次数", prompt)
            self.assertIn("不得发送 follow-up 或反复 list", prompt)

    def test_launcher_timeout_and_nonzero_paths_finalize_all_state_views(self):
        outcomes = (
            ({
                "stdout": "", "stderr": "timeout", "process_exit_code": 124,
                "timed_out": True,
                "local_process_group": {
                    "pid": 123, "term_sent": True, "kill_sent": True,
                    "cleanup_complete": True,
                },
                "remote_cancellation_status": "UNKNOWN",
            }, "TIMEOUT", "COMMON_STOCK_STAGE_TIMEOUT"),
            ({
                "stdout": "", "stderr": "failed", "process_exit_code": 9,
                "timed_out": False,
                "local_process_group": {
                    "pid": 124, "term_sent": False, "kill_sent": False,
                    "cleanup_complete": True,
                },
                "remote_cancellation_status": "NOT_APPLICABLE",
            }, "FAILED", "COMMON_STOCK_CODEX_PROCESS_FAILED"),
        )
        for outcome, execution_status, failure_code in outcomes:
            with self.subTest(execution_status=execution_status), tempfile.TemporaryDirectory() as temp:
                run, _ = self.prepare_stage(temp, count=1)
                with patch(
                    "product.runtime.common_stock_stage._run_bounded_process_group",
                    return_value=outcome,
                ):
                    result, code = launch_common_stock_stage(ROOT, run_dir=run)
                self.assertEqual(7, code)
                self.assertEqual("FAILED", result["status"])
                coverage = json.loads((run / "research/coverage.json").read_text())
                stage = json.loads((run / "research/stage.json").read_text())
                process = json.loads((run / "invocation/process-result.json").read_text())
                item = coverage["items"][0]
                self.assertEqual(execution_status, item["execution_status"])
                self.assertEqual("FAILED", item["research_status"])
                self.assertEqual("FAILED", item["coverage_status"])
                self.assertEqual(failure_code, item["failure_code"])
                self.assertEqual("FAILED", coverage["stage_status"])
                self.assertEqual(coverage, stage["coverage"])
                self.assertEqual("FAILED", process["process_status"])
                self.assertEqual("FAILED", process["stage_status"])
                self.assertEqual(failure_code, process["failure_code"])

    def test_launcher_missing_final_or_stop_does_not_leave_queued(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)

            def successful_process_without_stop(command, **_kwargs):
                final_path = Path(command[command.index("--output-last-message") + 1])
                final_path.write_text(json.dumps({
                    "stage": "COMMON_STOCK_RESEARCH",
                    "run_id": "native-stage-run", "dispatched": 1,
                }), encoding="utf-8")
                return {
                    "stdout": "", "stderr": "", "process_exit_code": 0,
                    "timed_out": False,
                    "local_process_group": {
                        "pid": 125, "term_sent": False, "kill_sent": False,
                        "cleanup_complete": True,
                    },
                    "remote_cancellation_status": "NOT_APPLICABLE",
                }

            with patch(
                "product.runtime.common_stock_stage._run_bounded_process_group",
                side_effect=successful_process_without_stop,
            ):
                result, code = launch_common_stock_stage(ROOT, run_dir=run)
            self.assertEqual(7, code)
            self.assertEqual("COMMON_STOCK_DISPATCH_PROOF_INCOMPLETE", result["failure_code"])
            coverage = json.loads((run / "research/coverage.json").read_text())
            self.assertEqual("FAILED", coverage["items"][0]["execution_status"])

    def test_bounded_process_group_terminates_hanging_child_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            result = _run_bounded_process_group(
                [
                    sys.executable, "-c",
                    (
                        "import subprocess,sys,time;"
                        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
                        "print(p.pid,flush=True);time.sleep(60)"
                    ),
                ],
                prompt="", cwd=Path(temp), environment=os.environ,
                timeout_seconds=0.1, termination_grace_seconds=0.2,
            )
            self.assertTrue(result["timed_out"])
            self.assertTrue(result["local_process_group"]["term_sent"])
            self.assertTrue(result["local_process_group"]["cleanup_complete"])
            child_pid = int(result["stdout"].strip().splitlines()[0])
            child_gone = False
            for _ in range(20):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    child_gone = True
                    break
                time.sleep(0.05)
            self.assertTrue(child_gone)

    def test_model_source_write_isolated_and_discarded_without_touching_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            active_before = (ROOT / "product/runtime/common_stock_stage.py").read_bytes()

            def mutate_isolated_source(_command, **kwargs):
                sentinel = Path(kwargs["cwd"]) / "runtime/common_stock_stage.py"
                sentinel.write_text(
                    sentinel.read_text(encoding="utf-8") + "\n# model-write-sentinel\n",
                    encoding="utf-8",
                )
                return {
                    "stdout": "", "stderr": "failed after sentinel",
                    "process_exit_code": 1, "timed_out": False,
                    "local_process_group": {
                        "pid": 126, "term_sent": False, "kill_sent": False,
                        "cleanup_complete": True,
                    },
                    "remote_cancellation_status": "NOT_APPLICABLE",
                }

            with patch(
                "product.runtime.common_stock_stage._run_bounded_process_group",
                side_effect=mutate_isolated_source,
            ):
                _result, code = launch_common_stock_stage(ROOT, run_dir=run)
            self.assertEqual(7, code)
            process = json.loads((run / "invocation/process-result.json").read_text())
            self.assertTrue(process["source_integrity_unchanged"])
            self.assertFalse(process["isolated_source_integrity_unchanged"])
            self.assertTrue(process["isolated_source_discarded"])
            self.assertEqual(
                active_before,
                (ROOT / "product/runtime/common_stock_stage.py").read_bytes(),
            )

    def test_launch_rejects_consistently_resigned_stage_and_invocation_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            base_run, _ = self.prepare_stage(temp, count=1)

            coverage_run = Path(temp) / "coverage-drift"
            shutil.copytree(base_run, coverage_run)
            coverage_path = coverage_run / "research/coverage.json"
            coverage = json.loads(coverage_path.read_text())
            coverage["per_item_timeout_seconds"] = 901
            coverage["coverage_hash"] = canonical_hash({
                key: value for key, value in coverage.items() if key != "coverage_hash"
            })
            coverage_path.write_text(json.dumps(coverage))
            stage_path = coverage_run / "research/stage.json"
            stage = json.loads(stage_path.read_text())
            stage["coverage"] = coverage
            stage["stage_hash"] = canonical_hash({
                key: value for key, value in stage.items() if key != "stage_hash"
            })
            stage_path.write_text(json.dumps(stage))
            manifest_path = coverage_run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["output_dir"] = str(coverage_run)
            manifest["stage_hash"] = stage["stage_hash"]
            manifest["manifest_hash"] = canonical_hash({
                key: value for key, value in manifest.items() if key != "manifest_hash"
            })
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(CommonStockStageError, "STAGE_RECONSTRUCTION_MISMATCH"):
                _validate_common_stock_stage_run_package(ROOT, coverage_run)

            invocation_run = Path(temp) / "invocation-drift"
            shutil.copytree(base_run, invocation_run)
            manifest_path = invocation_run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["output_dir"] = str(invocation_run)
            index_path = invocation_run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            task = index["tasks"][0]
            invocation_path = invocation_run / task["invocation_path"]
            invocation = json.loads(invocation_path.read_text())
            invocation["tool_permissions"].append("provider.network")
            invocation["manifest_hash"] = canonical_hash({
                key: value for key, value in invocation.items() if key != "manifest_hash"
            })
            invocation_path.write_text(json.dumps(invocation))
            packet = _build_common_stock_dispatch_packet(ROOT, invocation_run, task)
            packet_path = invocation_run / task["packet_path"]
            packet_path.write_text(json.dumps(packet))
            task["packet_hash"] = canonical_hash(packet)
            index["index_hash"] = canonical_hash({
                key: value for key, value in index.items() if key != "index_hash"
            })
            index_path.write_text(json.dumps(index))
            manifest["dispatch_index_hash"] = index["index_hash"]
            manifest["manifest_hash"] = canonical_hash({
                key: value for key, value in manifest.items() if key != "manifest_hash"
            })
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(CommonStockStageError, "DISPATCH_RECONSTRUCTION_MISMATCH"):
                _validate_common_stock_stage_run_package(ROOT, invocation_run)

    def test_focused_run_keeps_full_portfolio_and_dispatches_only_selected_stock(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            focus = handoff["portfolio"]["positions"][1]["security_id"]
            handoff_path, gate_path = root / "handoff.json", root / "gate.json"
            handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
            gate_path.write_text(json.dumps(gate_for(handoff, "focused-stage-run")), encoding="utf-8")
            run = root / "run"
            prepare_common_stock_stage_run(
                ROOT, handoff_path=handoff_path, gate_path=gate_path,
                run_dir=run, run_id="focused-stage-run", model="gpt-5.6-terra",
                focus_security_id=focus,
            )
            manifest = json.loads((run / "run_manifest.json").read_text())
            index = json.loads((run / "research/dispatch-index.json").read_text())
            coverage = json.loads((run / "research/coverage.json").read_text())
            self.assertEqual(handoff["portfolio_hash"], manifest["portfolio_hash"])
            self.assertEqual(focus, manifest["focus_security_id"])
            self.assertEqual([focus], [item["security_id"] for item in index["tasks"]])
            not_selected = next(
                item for item in coverage["items"]
                if item["asset_type"] == "COMMON_STOCK" and item["security_id"] != focus
            )
            self.assertEqual("NOT_STARTED", not_selected["execution_status"])
            self.assertEqual("NOT_RESEARCHED", not_selected["coverage_status"])

    @staticmethod
    def dispatch_payload(run, task, *, parent="parent-session", number=0):
        return {
            "hook_event_name": "PreToolUse", "session_id": parent,
            "turn_id": "parent-turn", "tool_name": "collaborationspawn_agent",
            "tool_use_id": f"tool-{number}", "cwd": str(ROOT / "product"),
            "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
            "tool_input": {
                "agent_type": "runtime_company_analyst", "task_name": task["task_name"],
                "fork_turns": "none",
                "message": build_common_stock_dispatch_message(ROOT, run, task["task_name"]),
            },
        }

    @staticmethod
    def hook_environment(run):
        invocation = run / "invocation"
        invocation.mkdir(exist_ok=True)
        return {
            "STOCK_AGENT_RUN_DIR": str(run),
            "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(invocation / "subagent-events.jsonl"),
            "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(invocation / "subagent-dispatches.jsonl"),
            "STOCK_AGENT_PARENT_STOP_LOG": str(invocation / "parent-stop-events.jsonl"),
            "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst",
            "STOCK_AGENT_COMMON_STOCK_STAGE": STAGE_VERSION,
        }

    @staticmethod
    def event(event_name, *, parent, child, turn, message=None):
        value = {
            "hook_event_name": event_name, "session_id": parent, "turn_id": turn,
            "agent_id": child, "agent_type": "runtime_company_analyst",
            "model": "gpt-5.6-terra", "cwd": str(ROOT / "product"),
            "permission_mode": "workspace-write", "stop_hook_active": False,
        }
        if message is not None:
            value["last_assistant_message"] = message
        return value

    def test_stage_package_supports_two_independent_same_agent_dispatches_and_mcp(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            manifest = json.loads((run / "run_manifest.json").read_text())
            self.assertEqual("gpt-5.6-terra", manifest["parent_model"])
            self.assertEqual("gpt-5.6-terra", manifest["analyst_model"])
            self.assertEqual(2, len(index["tasks"]))
            messages = [
                build_common_stock_dispatch_message(ROOT, run, item["task_name"])
                for item in index["tasks"]
            ]
            self.assertNotEqual(messages[0], messages[1])
            self.assertTrue(all(len(item.encode("utf-8")) < 2048 for item in messages))
            self.assertTrue(all("Evidence" not in item for item in messages))
            packet = build_common_stock_dispatch_packet(
                ROOT, run, index["tasks"][0]["task_name"]
            )
            self.assertEqual("frozen-gate", packet["tool_context"]["source_mode"])
            self.assertIn("evidence_conflicts", packet)
            self.assertEqual("fixture_runtime.query", packet["tool_context"]["query_tool"])
            self.assertEqual(
                packet["identity"]["invocation_id"],
                packet["tool_context"]["required_identity_arguments"]["invocation_id"],
            )
            self.assertNotIn(
                "run_dir", packet["tool_context"]["required_identity_arguments"]
            )
            self.assertEqual(
                "LAUNCHER_ENVIRONMENT", packet["tool_context"]["run_directory_binding"]
            )
            self.assertEqual(
                ["fixture_evidence.query", "fixture_math.calculate"],
                packet["tool_context"]["logical_permissions"],
            )
            self.assertNotEqual(
                packet["holding_research_request"]["invocation_id"],
                build_common_stock_dispatch_packet(
                    ROOT, run, index["tasks"][1]["task_name"]
                )["holding_research_request"]["invocation_id"],
            )
            self.assertEqual(index["tasks"][0]["packet_hash"], canonical_hash(packet))
            tools = StatelessFixtureTools()
            identity = packet["identity"]
            catalog_evidence_id = flattened_evidence_catalog(packet)[0]["evidence_id"]
            queried = tools.query(
                run_dir=str(run), run_id=identity["run_id"], agent=identity["agent"],
                invocation_id=identity["invocation_id"],
                evidence_ids=[catalog_evidence_id],
            )
            self.assertEqual(catalog_evidence_id, queried["evidence"][0]["evidence_id"])

            bound_tools = StatelessFixtureTools(default_run_dir=run)
            query_schema = next(
                item for item in bound_tools.available_tools() if item["name"] == "query"
            )["inputSchema"]
            self.assertNotIn("run_dir", query_schema["properties"])
            self.assertIn("semantic_field", query_schema["properties"])
            bound = bound_tools.query(
                run_id=identity["run_id"], agent=identity["agent"],
                invocation_id=identity["invocation_id"],
                evidence_ids=[catalog_evidence_id],
            )
            self.assertEqual(catalog_evidence_id, bound["evidence"][0]["evidence_id"])
            with self.assertRaisesRegex(ToolAccessError, "RUN_DIRECTORY_OVERRIDE_REJECTED"):
                bound_tools.query(
                    run_dir=str(Path(temp) / "other"), run_id=identity["run_id"],
                    agent=identity["agent"], invocation_id=identity["invocation_id"],
                    evidence_ids=[catalog_evidence_id],
                )

    def test_common_stock_field_query_uses_only_current_security_and_delivered_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            first = index["tasks"][0]
            packet = build_common_stock_dispatch_packet(ROOT, run, first["task_name"])
            identity = packet["identity"]
            tools = StatelessFixtureTools(default_run_dir=run)
            result = tools.query(
                run_id=identity["run_id"], agent=identity["agent"],
                invocation_id=identity["invocation_id"], semantic_field="revenue",
            )
            expected = [
                item["evidence_id"] for item in json.loads((run / "evidence/gate.json").read_text())["allowed_evidence"]
                if item["security_id"] == identity["security_id"]
                and item["semantic_field"] == "revenue"
            ]
            self.assertEqual(expected, [item["evidence_id"] for item in result["evidence"]])
            self.assertEqual(expected, tools.events[-1]["evidence_ids"])
            self.assertEqual("fixture-gate-scoped/2.4.0", result["adapter_version"])
            self.assertEqual(result["result_hash"], canonical_hash(result["evidence"]))
            event_path = run / "events/mcp/events.jsonl"
            event_path.parent.mkdir(parents=True, exist_ok=True)
            event_path.write_text(json.dumps(tools.events[-1]) + "\n", encoding="utf-8")
            validate_delivered_research_references(
                {"claims": [{"evidence_refs": expected}]},
                run_dir=run, invocation_id=identity["invocation_id"],
            )
            with self.assertRaisesRegex(CommonStockStageError, "COMMON_STOCK_EVIDENCE_NOT_DELIVERED"):
                validate_delivered_research_references(
                    {"claims": [{"evidence_refs": ["ev-not-delivered"]}]},
                    run_dir=run, invocation_id=identity["invocation_id"],
                )
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "query", "arguments": {
                        "run_id": identity["run_id"], "agent": identity["agent"],
                        "invocation_id": identity["invocation_id"],
                        "semantic_field": "revenue",
                    },
                }},
            ]
            stdin = io.StringIO("\n".join(json.dumps(item) for item in requests) + "\n")
            stdout = io.StringIO()
            with patch("sys.stdin", stdin), patch("sys.stdout", stdout):
                serve_stdio(stateless=True, default_run_dir=run)
            responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
            tool_schema = next(
                item for item in responses[0]["result"]["tools"]
                if item["name"] == "query"
            )["inputSchema"]
            self.assertIn("semantic_field", tool_schema["properties"])
            self.assertEqual(
                expected,
                [item["evidence_id"] for item in responses[1]["result"]["structuredContent"]["evidence"]],
            )
            self.assertEqual([], tools.query(
                run_id=identity["run_id"], agent=identity["agent"],
                invocation_id=identity["invocation_id"], semantic_field="absent-field",
            )["evidence"])
            with self.assertRaisesRegex(ToolAccessError, "EVIDENCE_QUERY_SELECTOR_INVALID"):
                tools.query(
                    run_id=identity["run_id"], agent=identity["agent"],
                    invocation_id=identity["invocation_id"],
                    semantic_field="revenue", evidence_ids=expected,
                )
            with self.assertRaisesRegex(ToolAccessError, "RUN_PACKAGE_BINDING_MISSING"):
                tools.query(
                    run_id=identity["run_id"], agent=identity["agent"],
                    invocation_id="unknown-invocation", semantic_field="revenue",
                )

    def test_dispatch_passes_relevant_gate_conflicts_without_selecting_winner(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = index["tasks"][0]
            request = json.loads((run / task["request_path"]).read_text())
            gate_path = run / "evidence/gate.json"
            gate = json.loads(gate_path.read_text())
            evidence_ids = request["allowed_evidence_ids"][:2]
            gate["conflicts"] = [{
                "conflict_key": "conflict-test",
                "reason_code": "INCOMPATIBLE_NORMALIZED_VALUES",
                "evidence_ids": evidence_ids,
            }]
            gate["bundle_hash"] = canonical_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            packet = _build_common_stock_dispatch_packet(ROOT, run, task)
            self.assertEqual(evidence_ids, packet["evidence_conflicts"][0]["evidence_ids"])
            self.assertNotIn("winner", packet["evidence_conflicts"][0])
            self.assertIn("禁止静默选", packet["instruction"])

    def test_hook_does_not_trust_parent_message_and_rejects_oversized_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp)
            env = self.hook_environment(run)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            payload = self.dispatch_payload(run, task)
            payload["tool_input"]["message"] = "父线程的自然语言只负责触发；研究上下文由 Hook 提供。"
            accepted, _ = handle_hook_event(payload, environ=env)
            self.assertEqual("ALLOW", accepted["decision"])
            self.assertFalse(accepted["dispatch_binding"]["parent_message_authoritative"])
            self.assertEqual(task["packet_hash"], accepted["dispatch_binding"]["packet_hash"])

        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp)
            env = self.hook_environment(run)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            payload = self.dispatch_payload(run, task)
            payload["tool_input"]["message"] = "x" * 4097
            rejected, response = handle_hook_event(payload, environ=env)
            self.assertEqual("DENY_DISPATCH_CONTRACT", rejected["decision"])
            self.assertEqual("deny", response["hookSpecificOutput"]["permissionDecision"])

    def test_hook_enforces_three_slots_then_allows_refill_after_bound_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=4)
            env = self.hook_environment(run)
            tasks = json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
            parent = "parent-session"
            for number, task in enumerate(tasks[:3]):
                record, _ = handle_hook_event(
                    self.dispatch_payload(run, task, parent=parent, number=number), environ=env
                )
                self.assertEqual("ALLOW", record["decision"])
            denied, response = handle_hook_event(
                self.dispatch_payload(run, tasks[3], parent=parent, number=3), environ=env
            )
            self.assertEqual("DENY_CONCURRENCY_LIMIT", denied["decision"])
            self.assertEqual("deny", response["hookSpecificOutput"]["permissionDecision"])

            first = tasks[0]
            request = json.loads((run / first["request_path"]).read_text())
            native = {
                "run_id": request["run_id"], "invocation_id": request["invocation_id"],
                "agent": "runtime_company_analyst",
                **CommonStockDispatchTests.draft(valid_report(request)),
            }
            handle_hook_event(
                self.event("SubagentStart", parent=parent, child="child-0", turn="turn-0"),
                environ=env,
            )
            stopped, _ = handle_hook_event(
                self.event(
                    "SubagentStop", parent=parent, child="child-0", turn="turn-0",
                    message=json.dumps(native, ensure_ascii=False),
                ),
                environ=env,
            )
            self.assertEqual("SubagentStop", stopped["hook_event_name"])
            allowed, _ = handle_hook_event(
                self.dispatch_payload(run, tasks[3], parent=parent, number=4), environ=env
            )
            self.assertEqual("ALLOW", allowed["decision"])

    def test_hook_requires_wait_while_research_task_is_active(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            env = self.hook_environment(run)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            parent = "parent-session"
            record, _ = handle_hook_event(
                self.dispatch_payload(run, task, parent=parent), environ=env,
            )
            self.assertEqual("ALLOW", record["decision"])

            for number, tool_name in enumerate((
                "collaborationlist_agents",
                "collaborationfollowup_task",
                "collaborationinterrupt_agent",
            )):
                blocked, response = handle_hook_event({
                    "hook_event_name": "PreToolUse", "session_id": parent,
                    "turn_id": "parent-turn", "tool_name": tool_name,
                    "tool_use_id": f"control-{number}", "cwd": str(ROOT / "product"),
                    "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                    "tool_input": {"target": "company_research_1"},
                }, environ=env)
                self.assertEqual("DENY_ACTIVE_RESEARCH_CONTROL", blocked["decision"])
                self.assertEqual("deny", response["hookSpecificOutput"]["permissionDecision"])

            allowed, response = handle_hook_event({
                "hook_event_name": "PreToolUse", "session_id": parent,
                "turn_id": "parent-turn", "tool_name": "collaborationwait_agent",
                "tool_use_id": "wait-1", "cwd": str(ROOT / "product"),
                "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                "tool_input": {"timeout_ms": 300000},
            }, environ=env)
            self.assertEqual("IGNORE_NON_AGENT_TOOL", allowed["decision"])
            self.assertEqual({}, response)

            blocked, response = handle_hook_event({
                "hook_event_name": "PreToolUse", "session_id": parent,
                "turn_id": "parent-turn", "tool_name": "collaborationwait_agent",
                "tool_use_id": "wait-short", "cwd": str(ROOT / "product"),
                "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                "tool_input": {},
            }, environ=env)
            self.assertEqual("DENY_SHORT_RESEARCH_WAIT", blocked["decision"])
            self.assertEqual("deny", response["hookSpecificOutput"]["permissionDecision"])

    def test_invalid_native_report_is_retained_only_as_rejected_output(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            env = self.hook_environment(run)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            parent = "parent-session"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(run, task, parent=parent), environ=env
            )
            self.assertEqual("ALLOW", allowed["decision"])
            handle_hook_event(
                self.event("SubagentStart", parent=parent, child="child-invalid", turn="turn-invalid"),
                environ=env,
            )
            request = json.loads((run / task["request_path"]).read_text())
            full = valid_report(request)
            full["claims"][0]["evidence_refs"] = []
            full["claims"][0]["assumption_ids"] = []
            full["claims"][0]["calculation_refs"] = []
            native = {
                "run_id": request["run_id"], "invocation_id": request["invocation_id"],
                "agent": "runtime_company_analyst", **CommonStockDispatchTests.draft(full),
            }
            stopped, _ = handle_hook_event(
                self.event(
                    "SubagentStop", parent=parent, child="child-invalid", turn="turn-invalid",
                    message=json.dumps(native, ensure_ascii=False),
                ),
                environ=env,
            )
            self.assertEqual("FAILED", stopped["output_capture"]["status"])
            rejected = run / stopped["output_capture"]["rejected_path"]
            self.assertTrue(rejected.is_file())
            self.assertFalse((run / "research/reports").exists())
            result = finalize_common_stock_stage_run(ROOT, run)
            self.assertEqual("FAILED", result["status"])
            self.assertEqual(0, result["completed"])
            proof = json.loads((run / "research/execution-proof.json").read_text())
            self.assertFalse(proof["all_reports_valid"])
            coverage = json.loads((run / "research/coverage.json").read_text())
            self.assertEqual("REPORT_MISSING", coverage["items"][0]["failure_code"])

    def test_parent_stop_requires_same_session_and_frozen_invocation_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            run, _ = self.prepare_stage(temp, count=1)
            env = self.hook_environment(run)
            task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
            parent = "parent-session"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(run, task, parent=parent), environ=env
            )
            self.assertEqual("ALLOW", allowed["decision"])

            parent_stop = {
                "hook_event_name": "Stop",
                "session_id": parent,
                "turn_id": "parent-turn",
                "cwd": str(ROOT / "product"),
                "stop_hook_active": False,
                "last_assistant_message": json.dumps({"dispatched": 1}),
            }
            record, response = handle_hook_event(parent_stop, environ=env)
            self.assertEqual("BLOCK", record["decision"])
            self.assertEqual([task["task_name"]], record["missing_task_names"])
            self.assertEqual("block", response["decision"])

            child = "child-one"
            handle_hook_event(
                self.event("SubagentStart", parent=parent, child=child, turn="child-turn"),
                environ=env,
            )
            record, response = handle_hook_event(parent_stop, environ=env)
            self.assertEqual("BLOCK", record["decision"])
            self.assertEqual("block", response["decision"])

            request = json.loads((run / task["request_path"]).read_text())
            native = {
                "run_id": request["run_id"],
                "invocation_id": request["invocation_id"],
                "agent": "runtime_company_analyst",
                **CommonStockDispatchTests.draft(valid_report(request)),
            }
            wrong = dict(native)
            wrong["invocation_id"] = "wrong-invocation"
            handle_hook_event(
                self.event(
                    "SubagentStop", parent="other-parent", child=child, turn="other-turn",
                    message=json.dumps(native, ensure_ascii=False),
                ),
                environ=env,
            )
            record, _ = handle_hook_event(parent_stop, environ=env)
            self.assertEqual("BLOCK", record["decision"])

            stopped, _ = handle_hook_event(
                self.event(
                    "SubagentStop", parent=parent, child=child, turn="child-turn",
                    message=json.dumps(wrong, ensure_ascii=False),
                ),
                environ=env,
            )
            self.assertEqual("FAILED", stopped["output_capture"]["status"])
            self.assertIn(
                "RESEARCH_OUTPUT_IDENTITY_CONFLICT",
                stopped["output_capture"]["failure_code"],
            )
            record, response = handle_hook_event(parent_stop, environ=env)
            self.assertEqual("ALLOW", record["decision"])
            self.assertEqual([task["task_name"]], record["completed_task_names"])
            self.assertEqual({}, response)

            audit_text = (run / "invocation/parent-stop-events.jsonl").read_text(
                encoding="utf-8"
            )
            audit = json.loads(audit_text.splitlines()[-1])
            self.assertNotIn("last_assistant_message", audit)
            self.assertNotIn("prompt", audit)
            self.assertNotIn("transcript", audit_text)

    def test_hook_allows_distinct_tasks_denies_duplicate_and_finalizes_bound_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            run, handoff = self.prepare_stage(temp)
            env = self.hook_environment(run)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            parent = "parent-session"
            for number, task in enumerate(index["tasks"]):
                message = build_common_stock_dispatch_message(ROOT, run, task["task_name"])
                payload = {
                    "hook_event_name": "PreToolUse", "session_id": parent,
                    "turn_id": "parent-turn", "tool_name": "collaborationspawn_agent",
                    "tool_use_id": f"tool-{number}", "cwd": str(ROOT / "product"),
                    "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                    "tool_input": {"agent_type": "runtime_company_analyst", "task_name": task["task_name"],
                                   "fork_turns": "none", "message": message},
                }
                record, response = handle_hook_event(payload, environ=env)
                self.assertEqual("ALLOW", record["decision"])
                self.assertEqual({}, response)
            duplicate = copy.deepcopy(payload)
            duplicate["tool_use_id"] = "tool-duplicate"
            record, response = handle_hook_event(duplicate, environ=env)
            self.assertEqual("DENY_DUPLICATE_AGENT", record["decision"])
            self.assertEqual("deny", response["hookSpecificOutput"]["permissionDecision"])

            children = []
            for number, task in enumerate(index["tasks"]):
                child, turn = f"child-{number}", f"child-turn-{number}"
                children.append((child, turn, task))
                start, response = handle_hook_event(
                    self.event("SubagentStart", parent=parent, child=child, turn=turn),
                    environ=env,
                )
                context = json.loads(response["hookSpecificOutput"]["additionalContext"])
                raw_context = response["hookSpecificOutput"]["additionalContext"]
                self.assertEqual(task["task_name"], start["context_binding"]["task_name"])
                self.assertEqual(task["packet_hash"], start["context_binding"]["packet_hash"])
                self.assertEqual(task["invocation_id"], context["identity"]["invocation_id"])
                self.assertEqual(
                    context["context_budget"]["actual_bytes"],
                    len(raw_context.encode("utf-8")),
                )
            mcp_path = run / "events/mcp/events.jsonl"
            mcp_path.parent.mkdir(parents=True)
            mcp_path.write_text(json.dumps({
                "event_type": "mcp_tool_result",
                "invocation_id": children[0][2]["invocation_id"],
                "tool": "fixture_math.calculate",
                "calculation_id": "calc-valuation-one",
            }) + "\n", encoding="utf-8")
            for position, (child, turn, task) in enumerate(children):
                request = json.loads((run / task["request_path"]).read_text())
                full = valid_report(request)
                if position == 0:
                    full["claims"][0]["calculation_refs"] = ["calc-valuation-one"]
                    full["artifact_refs"] = ["calc-valuation-one"]
                if position == 1:
                    full["status"] = "LOW_CONFIDENCE"
                draft = CommonStockDispatchTests.draft(full)
                native = {
                    "run_id": request["run_id"], "invocation_id": request["invocation_id"],
                    "agent": "runtime_company_analyst", **draft,
                }
                record, _ = handle_hook_event(
                    self.event("SubagentStop", parent=parent, child=child, turn=turn,
                               message=json.dumps(native, ensure_ascii=False)),
                    environ=env,
                )
                self.assertEqual("SAVED", record["output_capture"]["status"])
            result = finalize_common_stock_stage_run(ROOT, run)
            self.assertEqual("PASSED", result["status"])
            self.assertEqual(2, result["completed"])
            coverage = json.loads((run / "research/coverage.json").read_text())
            self.assertEqual(
                {item["security_id"] for item in handoff["portfolio"]["positions"]},
                {item["security_id"] for item in coverage["items"]},
            )
            low_confidence = next(
                item for item in coverage["items"]
                if item["security_id"] == index["tasks"][1]["security_id"]
            )
            self.assertEqual("LOW_CONFIDENCE", low_confidence["research_status"])
            self.assertEqual("RESEARCHED", low_confidence["coverage_status"])
            eval_task = index["tasks"][1]
            eval_dir = run / "research/evals" / eval_task["security_id"].replace(":", "_")
            job = prepare_common_stock_eval_job(
                report_path=run / "research/reports" / eval_task["security_id"].replace(":", "_") / "equity-research.json",
                request_path=run / eval_task["request_path"],
                gate_path=run / "evidence/gate.json",
                rubric_path=ROOT / "evals/grading/common-stock-research-rubric-v1.json",
                output_dir=eval_dir, eval_id="bound-eval-1",
            )
            semantic = CommonStockFocusedEvalTests.semantic_result(job)
            semantic_path = Path(temp) / "semantic-result.json"
            semantic_path.write_text(json.dumps(semantic), encoding="utf-8")
            finalize_common_stock_eval_job(
                eval_dir=eval_dir, semantic_result_path=semantic_path
            )
            updated = json.loads((run / "research/coverage.json").read_text())
            evaluated = next(
                item for item in updated["items"]
                if item["security_id"] == eval_task["security_id"]
            )
            self.assertEqual("PASS", evaluated["eval_status"])
            self.assertEqual(semantic["result_hash"], evaluated["eval_result_hash"])
            self.assertEqual(evaluated["report_hash"], evaluated["evaluated_report_hash"])
            self.assertTrue((run / evaluated["eval_ref"]).is_file())

    def test_persisted_package_recovers_attachment_calculation_identities(self):
        package = {
            "calculations": [{"calculation_id": "calc-runtime"}],
            "attachment": {
                "artifacts": [
                    {"calculation_refs": ["calc-valuation", "calc-runtime"]},
                    {
                        "artifact": {
                            "calculation_id": "calc-peer",
                            "nested": {"calculation_refs": ["calc-nested"]},
                        },
                    },
                ],
            },
        }
        self.assertEqual(
            ["calc-nested", "calc-peer", "calc-runtime", "calc-valuation"],
            _report_package_calculation_ids(package),
        )

    def test_changed_cutoff_reuse_requires_current_successful_source_manifest(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root = Path(temp)
            memory_root = root / "memory"
            memory = ResearchMemory(memory_root)
            security_id = "US:COMMON_STOCK:MRVL"
            run_id = "freshness-run"
            cutoff = "2026-09-12T12:00:00Z"
            plans = {
                dataset: memory.plan(
                    security_id, provider, dataset,
                    planning_as_of="2026-09-12T11:59:00Z",
                )
                for dataset, provider in CURRENT_SOURCE_REUSE_DATASETS.items()
            }
            fact = {
                "evidence_id": "ev-mrvl-revenue",
                "security_id": security_id,
                "source_id": "sec-companyfacts-0001835632",
                "source_locator": "https://data.sec.gov/example",
                "semantic_field": "revenue",
                "value": "100",
                "unit": "USD",
                "currency": "USD",
                "as_of": "2026-06-30T00:00:00Z",
                "published_at": "2026-09-10T00:00:00Z",
                "retrieved_at": "2026-09-12T11:58:00Z",
                "raw_content_hash": "a" * 64,
                "metadata": {"tag": "Revenues"},
            }
            outcomes = {}
            for dataset, plan in plans.items():
                outcomes[dataset] = memory.ingest_dataset(
                    plan=plan,
                    facts=[fact] if dataset == "sec_companyfacts" else [],
                    status="FETCHED_BOOTSTRAP",
                    completed_at=cutoff,
                )
            view = memory.save_view(
                run_id=run_id, security_id=security_id,
                decision_cutoff=cutoff, facts=[fact], gaps=[], conflicts=[],
            )
            artifact_root = root / "source/research-memory"
            artifact_root.mkdir(parents=True)
            (artifact_root / "mrvl-view.json").write_text(
                json.dumps(view), encoding="utf-8"
            )
            manifest = {
                "schema_version": "company-research-memory-run/1.0.0",
                "run_id": run_id,
                "memory_root": str(memory_root),
                "results": [{
                    "security_id": security_id,
                    "mode": "CHECKED_NO_CHANGE",
                    "plans": plans,
                    "dataset_outcomes": outcomes,
                }],
                "view_hashes": [view["view_manifest_hash"]],
            }
            manifest["manifest_hash"] = canonical_hash(manifest)
            manifest_path = artifact_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            gate = {
                "run_id": run_id,
                "source_mode": "live-read-only",
                "decision_cutoff": cutoff,
                "allowed_evidence": [fact],
            }
            current_request = {"decision_cutoff": cutoff}
            original_request = {"decision_cutoff": "2026-09-11T12:00:00Z"}
            self.assertEqual(
                "CURRENT_SOURCE_CHECKED",
                _current_source_reuse_status(
                    current_request=current_request,
                    original_request=original_request,
                    gate=gate,
                    source_memory=manifest,
                    source_memory_manifest=manifest_path,
                    security_id=security_id,
                    resolved_memory_root=memory_root,
                    preparation={},
                ),
            )

            failed = copy.deepcopy(manifest)
            failed["results"][0]["dataset_outcomes"]["sec_documents"][
                "status"
            ] = "SOURCE_LIMITED"
            failed["manifest_hash"] = canonical_hash({
                key: value for key, value in failed.items()
                if key != "manifest_hash"
            })
            self.assertIsNone(
                _current_source_reuse_status(
                    current_request=current_request,
                    original_request=original_request,
                    gate=gate,
                    source_memory=failed,
                    source_memory_manifest=manifest_path,
                    security_id=security_id,
                    resolved_memory_root=memory_root,
                    preparation={},
                )
            )

            missing_pending = copy.deepcopy(manifest)
            del missing_pending["results"][0]["dataset_outcomes"][
                "sec_documents"
            ]["pending_count"]
            missing_pending["manifest_hash"] = canonical_hash({
                key: value for key, value in missing_pending.items()
                if key != "manifest_hash"
            })
            self.assertIsNone(_current_source_reuse_status(
                current_request=current_request,
                original_request=original_request,
                gate=gate,
                source_memory=missing_pending,
                source_memory_manifest=manifest_path,
                security_id=security_id,
                resolved_memory_root=memory_root,
                preparation={},
            ))

            wrong_revision = copy.deepcopy(manifest)
            wrong_revision["results"][0]["dataset_outcomes"][
                "sec_documents"
            ]["checkpoint_revision"] += 1
            wrong_revision["manifest_hash"] = canonical_hash({
                key: value for key, value in wrong_revision.items()
                if key != "manifest_hash"
            })
            self.assertIsNone(_current_source_reuse_status(
                current_request=current_request,
                original_request=original_request,
                gate=gate,
                source_memory=wrong_revision,
                source_memory_manifest=manifest_path,
                security_id=security_id,
                resolved_memory_root=memory_root,
                preparation={},
            ))

            mismatched_gate = copy.deepcopy(gate)
            mismatched_gate["allowed_evidence"][0]["value"] = "101"
            self.assertIsNone(_current_source_reuse_status(
                current_request=current_request,
                original_request=original_request,
                gate=mismatched_gate,
                source_memory=manifest,
                source_memory_manifest=manifest_path,
                security_id=security_id,
                resolved_memory_root=memory_root,
                preparation={},
            ))

            # The core collector currently has no company-profile boundary.
            # Its explicit zero-request NOT_ATTEMPTED outcome is acceptable
            # only when the View likewise contains no profile checkpoint.
            optional_profile_manifest = copy.deepcopy(manifest)
            profile_outcome = optional_profile_manifest["results"][0][
                "dataset_outcomes"
            ]["company_profile"]
            profile_outcome.update(
                status="NOT_ATTEMPTED", inserted_versions=0, observations=0,
                request_count=0, repair_request_count=0, pending_count=0,
                checkpoint_revision_before=0, checkpoint_revision=0,
            )
            optional_profile_view = copy.deepcopy(view)
            optional_profile_view["checkpoint_revisions"].pop("company_profile")
            optional_profile_view["view_manifest_hash"] = canonical_hash({
                key: value for key, value in optional_profile_view.items()
                if key != "view_manifest_hash"
            })
            (artifact_root / "mrvl-view.json").write_text(
                json.dumps(optional_profile_view), encoding="utf-8"
            )
            optional_profile_manifest["view_hashes"] = [
                optional_profile_view["view_manifest_hash"]
            ]
            optional_profile_manifest["manifest_hash"] = canonical_hash({
                key: value for key, value in optional_profile_manifest.items()
                if key != "manifest_hash"
            })
            self.assertEqual(
                "CURRENT_SOURCE_CHECKED",
                _current_source_reuse_status(
                    current_request=current_request,
                    original_request=original_request,
                    gate=gate,
                    source_memory=optional_profile_manifest,
                    source_memory_manifest=manifest_path,
                    security_id=security_id,
                    resolved_memory_root=memory_root,
                    preparation={},
                ),
            )

            wrong_view = copy.deepcopy(view)
            wrong_view["decision_cutoff"] = "2026-09-11T12:00:00Z"
            wrong_view["view_manifest_hash"] = canonical_hash({
                key: value for key, value in wrong_view.items()
                if key != "view_manifest_hash"
            })
            (artifact_root / "mrvl-view.json").write_text(
                json.dumps(wrong_view), encoding="utf-8"
            )
            wrong_view_manifest = copy.deepcopy(manifest)
            wrong_view_manifest["view_hashes"] = [
                wrong_view["view_manifest_hash"]
            ]
            wrong_view_manifest["manifest_hash"] = canonical_hash({
                key: value for key, value in wrong_view_manifest.items()
                if key != "manifest_hash"
            })
            self.assertIsNone(_current_source_reuse_status(
                current_request=current_request,
                original_request=original_request,
                gate=gate,
                source_memory=wrong_view_manifest,
                source_memory_manifest=manifest_path,
                security_id=security_id,
                resolved_memory_root=memory_root,
                preparation={},
            ))

    def test_persisted_report_restarts_and_finishes_with_zero_model_calls(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root = Path(temp)
            memory_root = root / "research-memory"
            handoff = stock_handoff(1)

            def prepare(
                run_id, directory, *, force_rerun=False,
                research_question="分析已确认的普通股持仓。",
                decision_cutoff=None,
            ):
                handoff_path = root / f"{run_id}-handoff.json"
                gate_path = root / f"{run_id}-gate.json"
                handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
                gate = gate_for(handoff, run_id)
                if decision_cutoff is not None:
                    gate["decision_cutoff"] = decision_cutoff
                    gate["bundle_hash"] = canonical_hash({
                        key: value for key, value in gate.items()
                        if key != "bundle_hash"
                    })
                gate_path.write_text(
                    json.dumps(gate), encoding="utf-8"
                )
                return prepare_common_stock_stage_run(
                    ROOT, handoff_path=handoff_path, gate_path=gate_path,
                    run_dir=directory, run_id=run_id, model="gpt-5.6-terra",
                    memory_root=memory_root, force_rerun=force_rerun,
                    research_question=research_question,
                )

            first = root / "first-run"
            prepared = prepare("persistent-first", first)
            self.assertEqual(1, prepared["task_count"])
            task = json.loads(
                (first / "research/dispatch-index.json").read_text()
            )["tasks"][0]
            env = self.hook_environment(first)
            parent = "persistent-parent"
            allowed, _ = handle_hook_event(
                self.dispatch_payload(first, task, parent=parent), environ=env,
            )
            self.assertEqual("ALLOW", allowed["decision"])
            handle_hook_event(
                self.event(
                    "SubagentStart", parent=parent,
                    child="persistent-child", turn="persistent-turn",
                ),
                environ=env,
            )
            request = json.loads((first / task["request_path"]).read_text())
            native = {
                "run_id": request["run_id"],
                "invocation_id": request["invocation_id"],
                "agent": "runtime_company_analyst",
                **CommonStockDispatchTests.draft(valid_report(request)),
            }
            stopped, _ = handle_hook_event(
                self.event(
                    "SubagentStop", parent=parent,
                    child="persistent-child", turn="persistent-turn",
                    message=json.dumps(native, ensure_ascii=False),
                ),
                environ=env,
            )
            self.assertEqual("SAVED", stopped["output_capture"]["status"])
            with patch(
                "product.runtime.common_stock_stage._persist_validated_report_package",
                side_effect=OSError("synthetic memory write failure"),
            ):
                self.assertEqual(
                    "PASSED", finalize_common_stock_stage_run(ROOT, first)["status"]
                )
            first_coverage = json.loads(
                (first / "research/coverage.json").read_text()
            )
            self.assertEqual(
                "FAILED",
                first_coverage["items"][0]["report_persistence_status"],
            )
            self.assertEqual(
                "synthetic memory write failure",
                first_coverage["items"][0]["report_persistence_failure_code"],
            )
            self.assertTrue(
                (first / first_coverage["items"][0]["report_ref"]).is_file()
            )
            for _ in range(2):
                backfill = persist_common_stock_report_package(
                    ROOT, first, security_id=task["security_id"],
                )
                self.assertEqual(0, backfill["llm_calls"])
                self.assertEqual(0, backfill["provider_calls"])
            recovered_coverage = json.loads(
                (first / "research/coverage.json").read_text()
            )
            self.assertEqual(
                "PERSISTED",
                recovered_coverage["items"][0]["report_persistence_status"],
            )
            shutil.rmtree(first)

            second = root / "second-run"
            prepared = prepare("persistent-second", second)
            self.assertEqual(0, prepared["task_count"])
            self.assertEqual(1, prepared["reused_count"])
            with patch(
                "product.runtime.common_stock_stage._run_bounded_process_group"
            ) as process:
                result, code = launch_common_stock_stage(ROOT, run_dir=second)
            process.assert_not_called()
            self.assertEqual(0, code)
            self.assertEqual("PASSED", result["status"])
            coverage = json.loads(
                (second / "research/coverage.json").read_text()
            )
            self.assertEqual("REUSED", coverage["items"][0]["research_execution_status"])
            self.assertEqual(
                gate_for(handoff, "persistent-first")["decision_cutoff"],
                coverage["items"][0]["original_report_cutoff"],
            )
            process_result = json.loads(
                (second / "invocation/process-result.json").read_text()
            )
            self.assertFalse(process_result["model_started"])

            changed_cutoff = prepare(
                "persistent-new-cutoff", root / "new-cutoff-run",
                decision_cutoff="2026-09-12T12:00:00Z",
            )
            self.assertEqual(1, changed_cutoff["task_count"])
            self.assertEqual(0, changed_cutoff["reused_count"])
            changed_task = json.loads(
                (root / "new-cutoff-run/research/dispatch-index.json").read_text()
            )["tasks"][0]
            self.assertEqual(
                "CURRENT_SOURCE_FRESHNESS_UNPROVEN",
                changed_task["reuse_bypass_reason"],
            )
            _validate_common_stock_stage_run_package(
                ROOT, root / "new-cutoff-run"
            )

            multidimensional = root / "multidimensional-from-reuse"
            prepare_multidimensional_stage_run(
                ROOT,
                handoff_path=root / "persistent-second-handoff.json",
                gate_path=root / "persistent-second-gate.json",
                run_dir=multidimensional, run_id="persistent-second",
                model="gpt-5.6-terra", company_research_run_path=second,
            )
            imported = json.loads(
                (multidimensional / "research/imported-company-research/import-manifest.json").read_text()
            )
            self.assertEqual(1, len(imported["reports"]))
            self.assertEqual(
                gate_for(handoff, "persistent-first")["decision_cutoff"],
                imported["reports"][0]["source_decision_cutoff"],
            )

            forced = prepare(
                "persistent-forced", root / "forced-run", force_rerun=True,
            )
            self.assertEqual(1, forced["task_count"])
            self.assertEqual(0, forced["reused_count"])
            forced_task = json.loads(
                (root / "forced-run/research/dispatch-index.json").read_text()
            )["tasks"][0]
            forced_request = json.loads(
                (root / "forced-run" / forced_task["request_path"]).read_text()
            )
            self.assertNotIn("historical_report", forced_request)
            self.assertNotIn("original_report_cutoff", forced_request)

            changed_question = prepare(
                "persistent-question-change", root / "question-change-run",
                research_question="重点评估未来三年的定价权。",
            )
            self.assertEqual(1, changed_question["task_count"])
            self.assertEqual(0, changed_question["reused_count"])

            mixed_handoff = stock_handoff(2)
            mixed_handoff_path = root / "mixed-handoff.json"
            mixed_gate_path = root / "mixed-gate.json"
            mixed_handoff_path.write_text(
                json.dumps(mixed_handoff), encoding="utf-8"
            )
            mixed_gate_path.write_text(
                json.dumps(gate_for(mixed_handoff, "persistent-mixed")),
                encoding="utf-8",
            )
            mixed_run = root / "mixed-run"
            mixed = prepare_common_stock_stage_run(
                ROOT, handoff_path=mixed_handoff_path, gate_path=mixed_gate_path,
                run_dir=mixed_run, run_id="persistent-mixed",
                model="gpt-5.6-terra", memory_root=memory_root,
            )
            self.assertEqual(1, mixed["task_count"])
            self.assertEqual(1, mixed["reused_count"])
            mixed_task = json.loads(
                (mixed_run / "research/dispatch-index.json").read_text()
            )["tasks"][0]
            self.assertEqual("company_research_2", mixed_task["task_name"])
            failed_process = {
                "stdout": "", "stderr": "synthetic failure",
                "process_exit_code": 9, "timed_out": False,
                "local_process_group": {
                    "pid": 999, "term_sent": False, "kill_sent": False,
                    "cleanup_complete": True,
                },
                "remote_cancellation_status": "NOT_APPLICABLE",
            }
            with patch(
                "product.runtime.common_stock_stage._run_bounded_process_group",
                return_value=failed_process,
            ):
                result, code = launch_common_stock_stage(ROOT, run_dir=mixed_run)
            self.assertEqual(7, code)
            self.assertEqual("PARTIAL_RESEARCH", result["stage_status"])
            mixed_coverage = json.loads(
                (mixed_run / "research/coverage.json").read_text()
            )
            self.assertEqual(
                {"REUSED", "RUN"},
                {
                    item["research_execution_status"]
                    for item in mixed_coverage["items"]
                },
            )
            reuse_item = json.loads(
                (second / "research/reuse-index.json").read_text()
            )["items"][0]
            reference = json.loads(
                (second / reuse_item["reference_path"]).read_text()
            )
            (memory_root / reference["package_ref"]).write_text(
                "corrupt", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ValueError, "RESEARCH_MEMORY_OBJECT_HASH_MISMATCH",
            ):
                prepare("persistent-corrupt", root / "corrupt-run")


if __name__ == "__main__":
    unittest.main()
