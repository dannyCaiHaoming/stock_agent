import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.council import (
    CouncilPlanningError,
    build_council_request,
    build_research_plan,
    validate_council_request,
    validate_research_plan,
)
from product.intake import (
    IntakeValidationError,
    apply_corrections,
    build_draft,
    build_handoff,
    build_manual_draft,
    render_draft_summary,
    validate_draft,
    validate_draft_v2,
    validate_handoff,
    validate_handoff_v2,
)
from product.intake.cli import main as intake_main
from product.intake.service import build_draft as build_draft_v2
from product.intake.service import build_handoff as build_handoff_v2
from product.runtime.hashing import canonical_hash, file_hash


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals/fixtures/portfolio-intake/synthetic-multi-asset-manual.json"


def load_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def source_item(source_id="source-correction", source_type="USER_CORRECTION"):
    return {
        "source_id": source_id,
        "source_type": source_type,
        "as_of": "2026-09-11T20:00:00+08:00",
        "retrieved_at": "2026-09-11T20:04:00+08:00",
        "content_hash": canonical_hash({"source_id": source_id}),
        "external_ref": None,
        "synthetic": True,
        "coverage_status": "COMPLETE",
    }


def confirmed(payload=None):
    draft = build_manual_draft(payload or load_payload())
    return draft, build_handoff(
        draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00"
    )


def request_for(handoff, request_id="request-one", question="为什么继续持有或暂不操作？"):
    return build_council_request(
        handoff,
        request_id=request_id,
        research_question=question,
        holding_horizon="6-12 months",
        benchmark_id="SP500",
        mandate_artifact_id="mandate:advisory-only-v1",
    )


class PortfolioIntakeV3ContractTests(unittest.TestCase):
    def test_default_is_v3_and_historical_v2_files_are_unchanged(self):
        draft, handoff = confirmed()
        self.assertEqual("portfolio-draft/3.0.0", draft["schema_version"])
        self.assertEqual("portfolio-handoff/3.0.0", handoff["schema_version"])
        self.assertEqual(
            "30cb9695c76fb289a4068ac67543830609b0d03f8f93250229d315499f1d6c34",
            file_hash(ROOT / "product/schemas/intake/portfolio-draft.schema.json"),
        )
        self.assertEqual(
            "339f6b8961858e4ea42c10eb69234560e954c0e3a984d92e727a916fdb9135b5",
            file_hash(ROOT / "product/schemas/intake/portfolio-handoff.schema.json"),
        )

    def test_explicit_v2_validation_remains_available_without_migration(self):
        payload = {
            "draft_id": "legacy", "portfolio_scope": "USER_DEFINED_PORTFOLIO",
            "portfolio_complete": True, "account_ref": None,
            "source_items": [source_item("source-manual", "MANUAL")],
            "portfolio_as_of": {"value": "2026-09-11T20:00:00+08:00", "status": "USER_SUPPLIED", "source_refs": ["source-manual"], "candidates": [], "note": None},
            "base_currency": {"value": "USD", "status": "USER_SUPPLIED", "source_refs": ["source-manual"], "candidates": [], "note": None},
            "cash": {"value": 0.0, "status": "USER_SUPPLIED", "source_refs": ["source-manual"], "candidates": [], "note": None},
            "positions": [{
                "position_id": "legacy-aapl",
                "ticker": {"value": "AAPL", "status": "USER_SUPPLIED", "source_refs": ["source-manual"], "candidates": [], "note": None},
                "market": {"value": "US", "status": "USER_SUPPLIED", "source_refs": ["source-manual"], "candidates": [], "note": None},
                "asset_type": {"value": "COMMON_STOCK", "status": "USER_SUPPLIED", "source_refs": ["source-manual"], "candidates": [], "note": None},
                "quantity": {"value": 1.0, "status": "USER_SUPPLIED", "source_refs": ["source-manual"], "candidates": [], "note": None},
                "cost_basis": {"value": None, "status": "MISSING", "source_refs": [], "candidates": [], "note": None},
                "option_contract": None,
            }],
            "unsupported_assets": [],
        }
        legacy = build_draft_v2(payload)
        old_hash = legacy["draft_hash"]
        validate_draft_v2(legacy)
        self.assertEqual("portfolio-draft/2.0.0", legacy["schema_version"])
        self.assertEqual(old_hash, legacy["draft_hash"])
        with self.assertRaisesRegex(IntakeValidationError, "VERSION_INVALID"):
            build_draft(legacy)

        legacy_handoff = build_handoff_v2(
            legacy, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00",
            holding_horizon="12 months", research_question="legacy review",
            benchmark_id="SP500", mandate_artifact_id="legacy-mandate",
        )
        legacy_handoff_hash = legacy_handoff["handoff_hash"]
        validate_handoff_v2(legacy_handoff, source_draft=legacy)
        self.assertEqual(legacy_handoff_hash, legacy_handoff["handoff_hash"])
        with tempfile.TemporaryDirectory() as temp_value:
            path = Path(temp_value)
            handoff_path, draft_path = path / "handoff.json", path / "draft.json"
            handoff_path.write_text(json.dumps(legacy_handoff), encoding="utf-8")
            draft_path.write_text(json.dumps(legacy), encoding="utf-8")
            self.assertEqual(0, intake_main([
                "validate-handoff", "--schema-version", "v2", "--handoff", str(handoff_path),
                "--draft", str(draft_path),
            ]))

    def test_account_fields_keep_zero_negative_unknown_and_distinct_meanings(self):
        payload = load_payload()
        account = payload["account_snapshot"]
        account["cash_balance"] = -25.0
        account["available_funds"] = 0.0
        account["buying_power"] = 100.0
        account["net_liquidation_value"] = None
        draft = build_manual_draft(payload)
        handoff = build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")
        self.assertEqual(-25.0, handoff["account_snapshot"]["cash_balance"])
        self.assertEqual(0.0, handoff["account_snapshot"]["available_funds"])
        self.assertEqual(100.0, handoff["account_snapshot"]["buying_power"])
        self.assertIn("net_liquidation_value", handoff["account_snapshot"]["unknown_fields"])
        self.assertEqual("NOT_EVALUATED", handoff["reconciliation"]["status"])

    def test_conflicting_optional_account_value_keeps_candidates_without_overwrite(self):
        draft = build_manual_draft(load_payload())
        draft["source_items"].append(source_item("source-second", "MANUAL"))
        draft["account_snapshot"]["buying_power"] = {
            "value": None, "status": "CONFLICTING",
            "source_refs": ["source-manual", "source-second"],
            "candidates": [17000.0, 18000.0], "note": "两个来源不一致",
        }
        draft.pop("draft_hash")
        rebuilt = build_draft(draft)
        self.assertEqual([17000.0, 18000.0], rebuilt["account_snapshot"]["buying_power"]["candidates"])
        self.assertNotIn("account_snapshot.buying_power", rebuilt["unresolved_fields"])

    def test_units_and_signed_short_option_value_are_unambiguous(self):
        _, handoff = confirmed()
        option = next(item for item in handoff["portfolio"]["positions"] if item["asset_type"] == "OPTION")
        self.assertEqual((-1, "CONTRACT"), (option["quantity"], option["quantity_unit"]))
        self.assertEqual((0.66, "PER_UNDERLYING_UNIT", 100, -66.0), (
            option["quote_price"], option["quote_unit"],
            option["option_contract"]["contract_multiplier"], option["market_value"],
        ))
        self.assertEqual(109.0, option["unrealized_pnl_amount"])
        self.assertEqual(62.29, option["unrealized_pnl_percent"])

    def test_long_option_uses_contract_and_underlying_quote_units(self):
        payload = load_payload()
        payload["account_snapshot"]["net_liquidation_value"] = None
        payload["positions"].append({
            "position_id": "option-aapl-call-long", "display_symbol": "AAPL", "display_name": "AAPL CALL",
            "asset_type": "OPTION", "identity_status": "USER_CONFIRMED", "quantity": 1,
            "quantity_unit": "CONTRACT", "available_quantity": 1, "average_cost_price": 3.0,
            "quote_price": 3.2, "quote_unit": "PER_UNDERLYING_UNIT", "market_value": 320.0,
            "unrealized_pnl_amount": 20.0, "unrealized_pnl_percent": 6.67, "currency": "USD",
            "option_contract": {
                "underlying_symbol": "AAPL", "option_type": "CALL", "expiration_date": "2026-12-18",
                "strike": 220.0, "contract_multiplier": 100, "raw_contract_symbol": None,
                "adjustment_status": "STANDARD",
            },
        })
        draft = build_manual_draft(payload)
        handoff = build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")
        option = next(item for item in handoff["portfolio"]["positions"] if item["security_id"].startswith("US:OPTION:AAPL"))
        self.assertEqual((1, "CONTRACT", "PER_UNDERLYING_UNIT", 320.0), (
            option["quantity"], option["quantity_unit"], option["quote_unit"], option["market_value"],
        ))

    def test_wrong_units_zero_quantity_and_market_value_sign_fail_closed(self):
        for mutation, code in (
            (("quantity_unit", "SHARE"), "QUANTITY_UNIT_INVALID"),
            (("quantity", 0), "QUANTITY_ZERO"),
            (("market_value", 66.0), "MARKET_VALUE_SIGN_MISMATCH"),
        ):
            payload = load_payload()
            option = next(item for item in payload["positions"] if item["asset_type"] == "OPTION")
            option[mutation[0]] = mutation[1]
            with self.subTest(mutation=mutation), self.assertRaisesRegex(IntakeValidationError, code):
                build_manual_draft(payload)

    def test_adjustment_ambiguity_and_identity_ambiguity_block_handoff(self):
        for kind in ("adjustment", "identity"):
            payload = load_payload()
            option = next(item for item in payload["positions"] if item["asset_type"] == "OPTION")
            if kind == "adjustment":
                option["option_contract"]["adjustment_status"] = "UNKNOWN"
            else:
                option["identity_status"] = "AMBIGUOUS"
                option["identity_candidates"] = ["candidate-a", "candidate-b"]
            draft = build_manual_draft(payload)
            self.assertTrue(draft["unresolved_fields"])
            with self.assertRaisesRegex(IntakeValidationError, "NOT_CONFIRMABLE"):
                build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")

    def test_field_level_lineage_distinguishes_screenshot_and_correction(self):
        draft = build_manual_draft(load_payload())
        corrected = apply_corrections(
            draft,
            correction_source=source_item(),
            corrections=[{
                "path": "positions.option-soxl-put-short.option_contract.contract_multiplier",
                "value": 100,
                "note": "用户确认",
            }],
        )
        handoff = build_handoff(corrected, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")
        lineage = {item["field_path"]: item["source_refs"] for item in handoff["field_lineage"]}
        self.assertEqual(
            ["source-manual", "source-correction"],
            lineage["portfolio.positions.option-soxl-put-short.option_contract.contract_multiplier"],
        )
        self.assertEqual(["source-manual"], lineage["portfolio.positions.option-soxl-put-short.quantity"])

    def test_derived_lineage_requires_formula_parents_and_real_sources(self):
        payload = load_payload()
        payload["account_snapshot"]["margin_used"] = 2360.0
        payload["account_snapshot"]["margin_utilization_ratio"] = 0.2
        payload["derived_lineage"] = [{
            "field_path": "account_snapshot.margin_utilization_ratio",
            "formula_id": "MARGIN_USED_OVER_NET_LIQUIDATION",
            "formula_version": "1.0.0",
            "parent_fields": ["account_snapshot.margin_used", "account_snapshot.net_liquidation_value"],
            "source_refs": ["source-manual"],
        }]
        draft = build_manual_draft(payload)
        handoff = build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")
        self.assertEqual("MARGIN_USED_OVER_NET_LIQUIDATION", handoff["derived_lineage"][0]["formula_id"])
        broken = copy.deepcopy(payload)
        broken["derived_lineage"][0]["parent_fields"] = ["account_snapshot.not_present"]
        with self.assertRaisesRegex(IntakeValidationError, "DERIVED_PARENT_MISSING"):
            build_manual_draft(broken)

    def test_dangling_field_lineage_fails_closed(self):
        _, handoff = confirmed()
        handoff["field_lineage"][0]["source_refs"] = ["missing-source"]
        handoff["handoff_hash"] = canonical_hash({k: v for k, v in handoff.items() if k != "handoff_hash"})
        with self.assertRaisesRegex(IntakeValidationError, "LINEAGE_DANGLING"):
            validate_handoff(handoff)

    def test_broker_label_is_preserved_without_semantic_guess(self):
        draft = build_manual_draft(load_payload())
        raw = draft["account_snapshot"]["broker_reported_fields"][0]
        self.assertEqual("保证金水平", raw["label"])
        self.assertIsNone(raw["normalized_meaning"])
        self.assertIsNone(draft["account_snapshot"]["margin_utilization_ratio"]["value"])

    def test_reserved_broker_source_type_does_not_connect_to_a_broker(self):
        payload = load_payload()
        draft = build_manual_draft(payload)
        draft["source_items"][0]["source_type"] = "BROKER_READ_ONLY_API"
        draft["draft_hash"] = canonical_hash({k: v for k, v in draft.items() if k != "draft_hash"})
        validate_draft(draft)
        self.assertNotIn("credential", json.dumps(draft).lower())


class PortfolioIntakeRowsAndConfirmationTests(unittest.TestCase):
    def test_total_subtotal_cash_and_position_rows_do_not_duplicate_positions(self):
        draft = build_manual_draft(load_payload())
        self.assertEqual(4, len(draft["positions"]))
        self.assertEqual(3, len(draft["reported_totals"]))
        self.assertEqual(4, sum(row["row_type"] == "POSITION" for row in draft["rows"]))
        self.assertEqual("RECONCILED", draft["reconciliation"]["status"])

    def test_unclassified_row_is_retained_and_blocks_confirmation(self):
        payload = load_payload()
        payload["reported_rows"].append({
            "row_id": "unknown-row", "row_type": None, "label": "无法确定的行",
            "reported_field": None, "reported_value": None, "currency": None,
        })
        draft = build_manual_draft(payload)
        self.assertIn("rows.unknown-row.row_type", draft["unresolved_fields"])
        with self.assertRaisesRegex(IntakeValidationError, "NOT_CONFIRMABLE"):
            build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")

    def test_unreconciled_total_is_reported_without_adjusting_positions(self):
        payload = load_payload()
        payload["account_snapshot"]["net_liquidation_value"] = 12000.0
        draft = build_manual_draft(payload)
        self.assertEqual("UNRECONCILED", draft["reconciliation"]["status"])
        self.assertEqual(200.0, draft["reconciliation"]["difference"])
        self.assertEqual(-66.0, next(p for p in draft["positions"] if p["identity"]["asset_type"]["value"] == "OPTION")["market_value"]["value"])

    def test_optional_margin_quote_and_pnl_fields_do_not_block_confirmation(self):
        payload = load_payload()
        for field in ("available_funds", "buying_power", "margin_used"):
            payload["account_snapshot"][field] = None
        for position in payload["positions"]:
            position["quote_price"] = None
            position["quote_unit"] = None
            position["unrealized_pnl_amount"] = None
            position["unrealized_pnl_percent"] = None
        draft = build_manual_draft(payload)
        handoff = build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")
        self.assertEqual(4, len(handoff["portfolio"]["positions"]))

    def test_unknown_cash_and_plain_continue_block_confirmation(self):
        payload = load_payload()
        payload["account_snapshot"]["cash_balance"] = None
        draft = build_manual_draft(payload)
        with self.assertRaisesRegex(IntakeValidationError, "NOT_CONFIRMABLE"):
            build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")
        valid = build_manual_draft(load_payload())
        with self.assertRaisesRegex(IntakeValidationError, "EXPLICIT_CONFIRMATION_REQUIRED"):
            build_handoff(valid, confirmed=False, confirmed_at="2026-09-11T20:05:00+08:00")

    def test_handoff_is_neutral_and_rejects_old_task_fields(self):
        _, handoff = confirmed()
        serialized = json.dumps(handoff, sort_keys=True)
        for field in (
            "research_question", "holding_horizon", "research_scope", "benchmark_id",
            "mandate_artifact_id", "required_capability", "capability_gaps",
            "council_readiness", "research_plan",
        ):
            self.assertNotIn(f'"{field}"', serialized)
        broken = copy.deepcopy(handoff)
        broken["research_question"] = "should not be here"
        broken["handoff_hash"] = canonical_hash({k: v for k, v in broken.items() if k != "handoff_hash"})
        with self.assertRaisesRegex(IntakeValidationError, "TASK_FIELD_FORBIDDEN"):
            validate_handoff(broken)

    def test_correction_changes_hash_and_invalidates_old_confirmation(self):
        draft, old_handoff = confirmed()
        corrected = apply_corrections(
            draft, correction_source=source_item(),
            corrections=[{"path": "positions.stock-aapl.quantity", "value": 6}],
        )
        self.assertNotEqual(draft["draft_hash"], corrected["draft_hash"])
        with self.assertRaisesRegex(IntakeValidationError, "STALE_DRAFT"):
            validate_handoff(old_handoff, source_draft=corrected)

    def test_summary_shows_account_reconciliation_and_all_positions(self):
        summary = render_draft_summary(build_manual_draft(load_payload()))
        self.assertIn("账户净值", summary)
        self.assertIn("购买力", summary)
        self.assertIn("勾稽状态：RECONCILED", summary)
        self.assertIn("全部持仓数量：4（无上限、不截断）", summary)
        self.assertIn("普通“继续”不视为确认", summary)


class CouncilRequestPlanningTests(unittest.TestCase):
    def test_ten_positions_are_not_truncated_by_handoff_request_or_plan(self):
        payload = json.loads(
            (ROOT / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json").read_text(encoding="utf-8")
        )
        draft = build_manual_draft(payload)
        handoff = build_handoff(draft, confirmed=True, confirmed_at="2026-09-11T20:05:00+08:00")
        request = request_for(handoff, "request-ten")
        plan = build_research_plan(handoff, request, batch_size=3)
        self.assertEqual((10, 10, 10), (
            len(handoff["portfolio"]["positions"]), len(request["research_security_ids"]), plan["total"],
        ))

    def test_two_requests_do_not_change_handoff_or_portfolio_hash(self):
        _, handoff = confirmed()
        before = copy.deepcopy(handoff)
        first = request_for(handoff, "request-one", "为什么继续持有？")
        second = request_for(handoff, "request-two", "未来三个月的主要风险？")
        self.assertNotEqual(first["request_hash"], second["request_hash"])
        self.assertEqual(before, handoff)
        self.assertEqual(first["handoff_hash"], second["handoff_hash"])
        self.assertEqual(first["portfolio_hash"], second["portfolio_hash"])

    def test_checked_in_request_examples_bind_to_current_synthetic_handoff(self):
        _, handoff = confirmed()
        examples = json.loads(
            (ROOT / "evals/fixtures/portfolio-intake/synthetic-council-requests.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(examples["synthetic_only"])
        self.assertEqual(handoff["handoff_hash"], examples["handoff_hash"])
        self.assertEqual(handoff["portfolio_hash"], examples["portfolio_hash"])
        for request in examples["requests"]:
            validate_council_request(request, handoff=handoff)
        self.assertNotEqual(
            examples["requests"][0]["request_hash"], examples["requests"][1]["request_hash"]
        )

    def test_missing_horizon_and_wrong_binding_fail_before_planning(self):
        _, handoff = confirmed()
        with self.assertRaisesRegex(CouncilPlanningError, "holding_horizon"):
            build_council_request(
                handoff, request_id="r", research_question="q", holding_horizon="",
                benchmark_id="SP500", mandate_artifact_id="m",
            )
        request = request_for(handoff)
        request["handoff_hash"] = "0" * 64
        request["request_hash"] = canonical_hash({k: v for k, v in request.items() if k != "request_hash"})
        with self.assertRaisesRegex(CouncilPlanningError, "BINDING_INVALID"):
            validate_council_request(request, handoff=handoff)

    def test_all_positions_are_planned_by_council_with_capability_gaps(self):
        _, handoff = confirmed()
        request = request_for(handoff)
        plan = build_research_plan(handoff, request, batch_size=2)
        self.assertTrue(plan["planning_only"])
        self.assertEqual(4, plan["total"])
        self.assertEqual(4, plan["pending"])
        self.assertEqual("ALL_INPUT_POSITIONS", plan["coverage_status"])
        self.assertEqual(["etf-research", "options-research"], plan["capability_gaps"])
        self.assertEqual(0, plan["agent_invocations"])
        self.assertEqual(0, plan["llm_invocations"])
        self.assertNotIn("thesis", json.dumps(plan).lower())
        self.assertNotIn("action", json.dumps(plan).lower())

    def test_request_cannot_omit_a_position_and_plan_cannot_claim_execution(self):
        _, handoff = confirmed()
        request = request_for(handoff)
        request["research_security_ids"].pop()
        request["request_hash"] = canonical_hash({k: v for k, v in request.items() if k != "request_hash"})
        with self.assertRaisesRegex(CouncilPlanningError, "COVERAGE_INVALID"):
            validate_council_request(request, handoff=handoff)
        valid_request = request_for(handoff)
        plan = build_research_plan(handoff, valid_request)
        plan["llm_invocations"] = 1
        plan["plan_hash"] = canonical_hash({k: v for k, v in plan.items() if k != "plan_hash"})
        with self.assertRaisesRegex(CouncilPlanningError, "SCHEMA_INVALID|EXECUTION_FORBIDDEN"):
            validate_research_plan(plan, handoff=handoff, request=valid_request)


class PortfolioIntakeCliAndBoundaryTests(unittest.TestCase):
    def test_cli_v3_confirm_request_and_plan(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            paths = {name: temp / f"{name}.json" for name in ("input", "draft", "handoff", "request", "plan")}
            paths["input"].write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual(0, intake_main(["manual-draft", "--input", str(paths["input"]), "--output", str(paths["draft"])]))
            self.assertEqual(0, intake_main(["confirm", "--draft", str(paths["draft"]), "--output", str(paths["handoff"]), "--confirmed-at", "2026-09-11T20:05:00+08:00", "--explicit-confirmation", "CONFIRM_PORTFOLIO"]))
            self.assertEqual(0, intake_main(["council-request", "--handoff", str(paths["handoff"]), "--output", str(paths["request"]), "--request-id", "request-cli", "--research-question", "研究全部持仓", "--holding-horizon", "6 months"]))
            self.assertEqual(0, intake_main(["council-plan", "--handoff", str(paths["handoff"]), "--request", str(paths["request"]), "--output", str(paths["plan"])]))
            self.assertEqual(4, json.loads(paths["plan"].read_text())["total"])

    def test_private_artifact_cannot_be_written_in_repository(self):
        payload = load_payload()
        payload["synthetic"] = False
        with tempfile.TemporaryDirectory() as temp_value:
            source = Path(temp_value) / "input.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            forbidden = ROOT / "private-portfolio-should-not-exist.json"
            self.assertFalse(forbidden.exists())
            self.assertEqual(2, intake_main(["manual-draft", "--input", str(source), "--output", str(forbidden)]))
            self.assertFalse(forbidden.exists())

    def test_skill_is_one_input_skill_and_contains_no_runtime_intake_agent(self):
        skill = (ROOT / "product/skills/portfolio-intake/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: portfolio-intake", skill)
        self.assertIn("CouncilRequest", skill)
        self.assertIn("字段级 lineage", skill)
        self.assertIn("不得自动调用 `portfolio-council`", skill)
        agent_files = list((ROOT / "product/.codex/agents").glob("*intake*.toml"))
        self.assertEqual([], agent_files)


if __name__ == "__main__":
    unittest.main()
