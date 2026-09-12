import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.intake import (
    IntakeValidationError,
    apply_corrections,
    build_council_portfolio_input,
    build_draft,
    build_handoff,
    build_manual_draft,
    build_risk_input,
    render_draft_summary,
    validate_draft,
    validate_handoff,
)
from product.intake.cli import main as intake_main
from product.runtime.hashing import canonical_hash, file_hash


ROOT = Path(__file__).resolve().parents[1]


def fact(value, source="source-manual", *, status="USER_SUPPLIED", candidates=None, note=None):
    return {
        "value": value,
        "status": status,
        "source_refs": [] if status == "MISSING" else [source],
        "candidates": [] if candidates is None else candidates,
        "note": note,
    }


def source_item(
    source_id="source-manual",
    *,
    source_type="MANUAL",
    coverage_status="COMPLETE",
    synthetic=True,
    external_ref=None,
    content_hash=None,
):
    return {
        "source_id": source_id,
        "source_type": source_type,
        "as_of": "2026-09-11T20:00:00+08:00",
        "retrieved_at": "2026-09-11T20:01:00+08:00",
        "content_hash": content_hash or canonical_hash({"source_id": source_id}),
        "external_ref": external_ref,
        "synthetic": synthetic,
        "coverage_status": coverage_status,
    }


def position(index, ticker=None, *, source="source-manual", cost_basis=100.0):
    ticker = ticker or f"T{index:02d}"
    return {
        "position_id": f"position-{index}",
        "ticker": fact(ticker, source),
        "market": fact("US", source),
        "asset_type": fact("COMMON_STOCK", source),
        "quantity": fact(float(index + 1), source),
        "cost_basis": fact(cost_basis, source) if cost_basis is not None else fact(None, status="MISSING"),
        "option_contract": None,
    }


def option_position(
    index,
    *,
    ticker="SOXL",
    quantity=-1.0,
    expiration="2026-09-18",
    strike=98.0,
    option_type="PUT",
    multiplier=100,
):
    item = position(index, ticker)
    item["asset_type"] = fact("OPTION")
    item["quantity"] = fact(quantity)
    item["option_contract"] = {
        "underlying_ticker": fact(ticker),
        "option_type": fact(option_type),
        "expiration_date": fact(expiration),
        "strike": fact(strike),
        "contract_multiplier": fact(multiplier),
        "contract_symbol": fact(None, status="MISSING"),
    }
    return item


def draft_payload(count=3, *, scope="BROKER_ACCOUNT", complete=True, cash=500.0):
    return {
        "draft_id": "draft-test",
        "portfolio_scope": scope,
        "portfolio_complete": complete,
        "account_ref": "Tiger-****1234" if scope == "BROKER_ACCOUNT" else None,
        "source_items": [source_item()],
        "portfolio_as_of": fact("2026-09-11T20:00:00+08:00"),
        "base_currency": fact("USD"),
        "cash": fact(cash) if cash is not None else fact(None, status="MISSING"),
        "positions": [position(index) for index in range(count)],
        "unsupported_assets": [],
    }


def confirmed_handoff(draft, *, batch_size=5):
    return build_handoff(
        draft,
        confirmed=True,
        confirmed_at="2026-09-11T20:05:00+08:00",
        holding_horizon="12-24 months",
        research_question="解释全部持仓应继续持有、减仓或暂不操作的依据",
        benchmark_id="SP500",
        mandate_artifact_id="mandate:us-equity-long-only-v1",
        batch_size=batch_size,
    )


class PortfolioDraftTests(unittest.TestCase):
    def test_multi_asset_fixture_keeps_stock_etf_long_and_short_options(self):
        payload = json.loads(
            (ROOT / "evals/fixtures/portfolio-intake/synthetic-multi-asset-manual.json").read_text(
                encoding="utf-8"
            )
        )
        draft = build_manual_draft(payload)
        handoff = confirmed_handoff(draft)
        self.assertEqual(4, len(handoff["portfolio"]["positions"]))
        option_quantities = sorted(
            item["quantity"]
            for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "OPTION"
        )
        self.assertEqual([-1, 1], option_quantities)
        self.assertEqual(["etf-research", "options-research"], handoff["capability_gaps"])

    def test_compact_manual_input_accepts_ten_positions(self):
        payload = json.loads(
            (ROOT / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json").read_text(
                encoding="utf-8"
            )
        )
        draft = build_manual_draft(payload)
        self.assertEqual(10, len(draft["positions"]))
        self.assertEqual([], draft["unresolved_fields"])

    def test_compact_manual_input_does_not_guess_missing_currency(self):
        payload = json.loads(
            (ROOT / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json").read_text(
                encoding="utf-8"
            )
        )
        payload.pop("base_currency")
        draft = build_manual_draft(payload)
        self.assertIsNone(draft["base_currency"]["value"])
        self.assertIn("base_currency", draft["unresolved_fields"])

    def test_synthetic_screenshot_fixture_keeps_cash_missing(self):
        payload = json.loads(
            (ROOT / "evals/fixtures/portfolio-intake/synthetic-screenshot-observation.json").read_text(
                encoding="utf-8"
            )
        )
        draft = build_draft(payload)
        self.assertIsNone(draft["cash"]["value"])
        self.assertEqual("MISSING", draft["cash"]["status"])
        self.assertIn("cash", draft["unresolved_fields"])
        self.assertEqual(file_hash(ROOT / payload["source_items"][0]["external_ref"]), payload["source_items"][0]["content_hash"])

    def test_draft_hash_is_stable_and_schema_has_no_position_limit(self):
        draft = build_draft(draft_payload(10))
        self.assertEqual(draft, build_draft(draft_payload(10)))
        schema = json.loads(
            (ROOT / "product/schemas/intake/portfolio-draft.schema.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("maxItems", json.dumps(schema))
        self.assertEqual(10, len(draft["positions"]))

    def test_unknown_cash_is_not_zero_and_blocks_confirmation(self):
        draft = build_draft(draft_payload(cash=None))
        self.assertIsNone(draft["cash"]["value"])
        self.assertIn("cash", draft["unresolved_fields"])
        with self.assertRaisesRegex(IntakeValidationError, "NOT_CONFIRMABLE"):
            confirmed_handoff(draft)

    def test_explicit_zero_cash_is_valid_and_missing_cost_basis_is_optional(self):
        payload = draft_payload(cash=0.0)
        payload["positions"][0]["cost_basis"] = fact(None, status="MISSING")
        draft = build_draft(payload)
        self.assertNotIn("cash", draft["unresolved_fields"])
        self.assertNotIn("positions[0].cost_basis", draft["unresolved_fields"])
        self.assertEqual(0.0, confirmed_handoff(draft)["portfolio"]["cash"])

    def test_duplicate_security_fails_closed(self):
        payload = draft_payload(2)
        payload["positions"][1]["ticker"] = fact(payload["positions"][0]["ticker"]["value"])
        with self.assertRaisesRegex(IntakeValidationError, "SECURITY_DUPLICATE"):
            build_draft(payload)

    def test_etf_and_short_option_are_structured_without_loss(self):
        payload = draft_payload(1)
        etf = position(10, "SOXL")
        etf["asset_type"] = fact("ETF")
        payload["positions"].extend([etf, option_position(11)])
        draft = build_draft(payload)
        handoff = confirmed_handoff(draft)
        by_type = {item["asset_type"]: item for item in handoff["portfolio"]["positions"]}
        self.assertEqual(-1.0, by_type["OPTION"]["quantity"])
        self.assertEqual("SOXL", by_type["OPTION"]["option_contract"]["underlying_ticker"])
        self.assertEqual("US:ETF:SOXL", by_type["ETF"]["security_id"])
        self.assertEqual("US:OPTION:SOXL:2026-09-18:98:PUT", by_type["OPTION"]["security_id"])

    def test_zero_quantity_is_rejected_but_negative_quantity_is_valid(self):
        payload = draft_payload(1)
        payload["positions"][0]["quantity"] = fact(-2.0)
        self.assertEqual(-2.0, build_draft(payload)["positions"][0]["quantity"]["value"])
        payload["positions"][0]["quantity"] = fact(0.0)
        with self.assertRaisesRegex(IntakeValidationError, "QUANTITY_ZERO"):
            build_draft(payload)

    def test_incomplete_option_identity_blocks_handoff_without_guessing(self):
        payload = draft_payload(1)
        payload["positions"] = [option_position(1)]
        payload["positions"][0]["option_contract"]["strike"] = fact(
            None, status="MISSING", note="截图只显示 98…，不可推断完整行权价"
        )
        draft = build_draft(payload)
        self.assertIn("positions[0].option_contract.strike", draft["unresolved_fields"])
        with self.assertRaisesRegex(IntakeValidationError, "NOT_CONFIRMABLE"):
            confirmed_handoff(draft)

    def test_duplicate_option_contract_is_rejected(self):
        payload = draft_payload(1)
        payload["positions"] = [option_position(1), option_position(2)]
        with self.assertRaisesRegex(IntakeValidationError, "SECURITY_DUPLICATE"):
            build_draft(payload)

    def test_option_underlying_mismatch_is_rejected(self):
        payload = draft_payload(1)
        payload["positions"] = [option_position(1)]
        payload["positions"][0]["option_contract"]["underlying_ticker"] = fact("TQQQ")
        with self.assertRaisesRegex(IntakeValidationError, "OPTION_UNDERLYING_MISMATCH"):
            build_draft(payload)

    def test_option_correction_uses_nested_path_and_preserves_lineage(self):
        payload = draft_payload(1)
        payload["positions"] = [option_position(1)]
        payload["positions"][0]["option_contract"]["strike"] = fact(None, status="MISSING")
        draft = build_draft(payload)
        corrected = apply_corrections(
            draft,
            correction_source=source_item("source-correction", source_type="USER_CORRECTION"),
            corrections=[{"path": "positions.position-1.option_contract.strike", "value": 98.0}],
        )
        self.assertEqual(98.0, corrected["positions"][0]["option_contract"]["strike"]["value"])
        self.assertNotIn("positions[0].option_contract.strike", corrected["unresolved_fields"])

    def test_dangling_source_reference_fails_closed(self):
        payload = draft_payload()
        payload["positions"][0]["quantity"]["source_refs"] = ["not-present"]
        with self.assertRaisesRegex(IntakeValidationError, "SOURCE_REF_DANGLING"):
            build_draft(payload)

    def test_broker_partial_coverage_cannot_claim_complete(self):
        payload = draft_payload()
        payload["source_items"][0]["coverage_status"] = "PARTIAL"
        with self.assertRaisesRegex(IntakeValidationError, "BROKER_COVERAGE_NOT_COMPLETE"):
            build_draft(payload)

    def test_user_defined_portfolio_can_confirm_declared_set(self):
        payload = draft_payload(scope="USER_DEFINED_PORTFOLIO")
        payload["source_items"][0]["coverage_status"] = "PARTIAL"
        handoff = confirmed_handoff(build_draft(payload))
        self.assertEqual("USER_DEFINED_PORTFOLIO", handoff["portfolio_scope"])

    def test_unsupported_asset_is_visible_and_blocks_confirmation(self):
        payload = draft_payload()
        payload["unsupported_assets"] = [
            {"label": "SPY Call", "reason": "首版不支持期权", "source_refs": ["source-manual"]}
        ]
        draft = build_draft(payload)
        self.assertIn("unsupported_assets", draft["unresolved_fields"])
        with self.assertRaisesRegex(IntakeValidationError, "NOT_CONFIRMABLE"):
            confirmed_handoff(draft)

    def test_conflicting_field_preserves_candidates_and_sources(self):
        payload = draft_payload()
        payload["source_items"].append(source_item("source-second"))
        payload["cash"] = {
            "value": None,
            "status": "CONFLICTING",
            "source_refs": ["source-manual", "source-second"],
            "candidates": [500.0, 800.0],
            "note": "两张截图现金不同",
        }
        draft = build_draft(payload)
        self.assertEqual([500.0, 800.0], draft["cash"]["candidates"])
        self.assertIn("cash", draft["unresolved_fields"])

    def test_private_screenshot_inside_repository_is_rejected(self):
        payload = draft_payload()
        path = ROOT / "tests/test_portfolio_intake.py"
        payload["source_items"] = [
            source_item(
                source_type="SCREENSHOT",
                synthetic=False,
                external_ref=str(path),
                content_hash=file_hash(path),
            )
        ]
        with self.assertRaisesRegex(IntakeValidationError, "PRIVATE_SOURCE_INSIDE_REPO"):
            build_draft(payload)

    def test_unmasked_account_number_is_rejected(self):
        payload = draft_payload()
        payload["account_ref"] = "".join(("1234", "5678", "90"))
        with self.assertRaisesRegex(IntakeValidationError, "ACCOUNT_REF_NOT_MASKED"):
            build_draft(payload)

    def test_correction_changes_hash_preserves_lineage_and_invalidates_old_handoff(self):
        original = build_draft(draft_payload())
        old_handoff = confirmed_handoff(original)
        corrected = apply_corrections(
            original,
            correction_source=source_item("source-correction", source_type="USER_CORRECTION"),
            corrections=[{"path": "positions.position-0.quantity", "value": 99.0}],
        )
        self.assertNotEqual(original["draft_hash"], corrected["draft_hash"])
        self.assertEqual(
            ["source-manual", "source-correction"],
            corrected["positions"][0]["quantity"]["source_refs"],
        )
        with self.assertRaisesRegex(IntakeValidationError, "STALE_DRAFT"):
            validate_handoff(old_handoff, source_draft=corrected)

    def test_plain_continue_cannot_be_used_as_confirmation(self):
        draft = build_draft(draft_payload())
        with self.assertRaisesRegex(IntakeValidationError, "EXPLICIT_CONFIRMATION_REQUIRED"):
            build_handoff(
                draft,
                confirmed=False,
                confirmed_at="2026-09-11T20:05:00+08:00",
                holding_horizon="12 months",
                research_question="review",
                benchmark_id="SP500",
                mandate_artifact_id="mandate:us-equity-long-only-v1",
            )


class PortfolioHandoffTests(unittest.TestCase):
    def test_ten_positions_are_all_in_handoff_plan_and_risk_input(self):
        draft = build_draft(draft_payload(10))
        handoff = confirmed_handoff(draft, batch_size=3)
        expected = {item["security_id"] for item in handoff["portfolio"]["positions"]}
        planned = {item["security_id"] for item in handoff["research_plan"]["items"]}
        self.assertEqual(expected, planned)
        self.assertEqual(10, handoff["research_plan"]["total"])
        self.assertEqual(10, handoff["research_plan"]["pending"])
        self.assertEqual(4, max(item["batch_index"] for item in handoff["research_plan"]["items"]))
        risk_input = build_risk_input(handoff)
        self.assertEqual(handoff["portfolio_hash"], risk_input["portfolio_hash"])
        self.assertEqual(10, len(risk_input["portfolio"]["positions"]))
        council_input = build_council_portfolio_input(handoff)
        self.assertEqual(10, len(council_input["portfolio"]["positions"]))
        self.assertEqual(
            {item["security_id"] for item in handoff["portfolio"]["positions"]},
            {item["security_id"] for item in council_input["portfolio"]["positions"]},
        )
        serialized = json.dumps(handoff, ensure_ascii=False, sort_keys=True)
        for forbidden_key in ('"evidence"', '"thesis"', '"action"', '"order"'):
            self.assertNotIn(forbidden_key, serialized)

    def test_missing_duplicate_or_extra_plan_security_fails(self):
        handoff = confirmed_handoff(build_draft(draft_payload()))
        for mutation in ("missing", "duplicate", "extra"):
            broken = copy.deepcopy(handoff)
            if mutation == "missing":
                broken["research_plan"]["items"].pop()
            elif mutation == "duplicate":
                broken["research_plan"]["items"][1]["security_id"] = broken["research_plan"]["items"][0]["security_id"]
            else:
                broken["research_plan"]["items"].append(
                    {
                        "security_id": "US:COMMON_STOCK:EXTRA",
                        "required_capability": "company-research",
                        "status": "PENDING",
                        "batch_index": 1,
                    }
                )
            broken["research_plan"]["total"] = len(broken["research_plan"]["items"])
            broken["research_plan"]["pending"] = len(broken["research_plan"]["items"])
            broken["handoff_hash"] = canonical_hash({key: value for key, value in broken.items() if key != "handoff_hash"})
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                IntakeValidationError, "RESEARCH_PLAN_COVERAGE_INVALID"
            ):
                validate_handoff(broken)

    def test_partial_future_batch_status_is_auditable(self):
        handoff = confirmed_handoff(build_draft(draft_payload(6)), batch_size=3)
        for item in handoff["research_plan"]["items"][:3]:
            item["status"] = "COMPLETED"
        handoff["research_plan"].update({"completed": 3, "pending": 3, "failed": 0})
        handoff["handoff_hash"] = canonical_hash(
            {key: value for key, value in handoff.items() if key != "handoff_hash"}
        )
        validate_handoff(handoff)
        self.assertEqual(6, handoff["research_plan"]["total"])

        handoff["research_plan"]["items"][-1]["batch_index"] = 1
        handoff["handoff_hash"] = canonical_hash(
            {key: value for key, value in handoff.items() if key != "handoff_hash"}
        )
        with self.assertRaisesRegex(IntakeValidationError, "RESEARCH_PLAN_BATCH_INVALID"):
            validate_handoff(handoff)

    def test_plan_status_counts_support_partial_future_batches(self):
        handoff = confirmed_handoff(build_draft(draft_payload(5)), batch_size=2)
        handoff["research_plan"]["items"][0]["status"] = "COMPLETED"
        handoff["research_plan"]["items"][1]["status"] = "FAILED"
        handoff["research_plan"]["completed"] = 1
        handoff["research_plan"]["failed"] = 1
        handoff["research_plan"]["pending"] = 3
        handoff["handoff_hash"] = canonical_hash(
            {key: value for key, value in handoff.items() if key != "handoff_hash"}
        )
        validate_handoff(handoff)
        broken = copy.deepcopy(handoff)
        broken["research_plan"]["pending"] = 4
        broken["handoff_hash"] = canonical_hash(
            {key: value for key, value in broken.items() if key != "handoff_hash"}
        )
        with self.assertRaisesRegex(IntakeValidationError, "RESEARCH_PLAN_COUNTS_INVALID"):
            validate_handoff(broken)

    def test_summary_is_chinese_and_states_all_positions(self):
        summary = render_draft_summary(build_draft(draft_payload(5)))
        self.assertIn("已结构化持仓数量：5（股票、ETF、期权均完整保留）", summary)
        self.assertIn("输入项目总数：5", summary)
        self.assertIn("普通“继续”不视为确认", summary)

    def test_summary_expands_unsupported_assets_instead_of_hiding_them(self):
        payload = draft_payload()
        payload["unsupported_assets"] = [
            {"label": "SOXL", "reason": "当前不支持 ETF", "source_refs": ["source-manual"]},
            {"label": "SOXL PUT", "reason": "当前不支持期权", "source_refs": ["source-manual"]},
        ]
        summary = render_draft_summary(build_draft(payload))
        self.assertIn("输入项目总数：5", summary)
        self.assertIn("未识别资产（未丢弃）", summary)
        self.assertIn("SOXL：当前不支持 ETF", summary)
        self.assertIn("SOXL PUT：当前不支持期权", summary)

    def test_multi_asset_handoff_declares_capability_gaps_without_dropping_positions(self):
        payload = draft_payload(1)
        etf = position(10, "SOXL")
        etf["asset_type"] = fact("ETF")
        payload["positions"].extend([etf, option_position(11)])
        handoff = confirmed_handoff(build_draft(payload))
        self.assertEqual("CAPABILITY_GAP", handoff["council_readiness"])
        self.assertEqual(["etf-research", "options-research"], handoff["capability_gaps"])
        self.assertEqual(3, len(handoff["research_plan"]["items"]))
        statuses = {item["required_capability"]: item["status"] for item in handoff["research_plan"]["items"]}
        self.assertEqual("PENDING", statuses["company-research"])
        self.assertEqual("PENDING_CAPABILITY", statuses["etf-research"])
        self.assertEqual("PENDING_CAPABILITY", statuses["options-research"])
        risk_input = build_risk_input(handoff)
        self.assertEqual("REQUIRES_MULTI_ASSET_POLICY", risk_input["risk_readiness"])
        self.assertEqual(3, len(risk_input["portfolio"]["positions"]))
        council_input = build_council_portfolio_input(handoff)
        self.assertEqual("CAPABILITY_GAP", council_input["council_readiness"])
        self.assertEqual(3, len(council_input["portfolio"]["positions"]))

    def test_unavailable_capability_cannot_be_marked_completed(self):
        payload = draft_payload(1)
        etf = position(10, "SOXL")
        etf["asset_type"] = fact("ETF")
        payload["positions"].append(etf)
        handoff = confirmed_handoff(build_draft(payload))
        etf_plan = next(
            item for item in handoff["research_plan"]["items"]
            if item["required_capability"] == "etf-research"
        )
        etf_plan["status"] = "COMPLETED"
        handoff["research_plan"].update({"completed": 1, "pending": 1, "failed": 0})
        handoff["handoff_hash"] = canonical_hash(
            {key: value for key, value in handoff.items() if key != "handoff_hash"}
        )
        with self.assertRaisesRegex(IntakeValidationError, "RESEARCH_PLAN_READINESS_INVALID"):
            validate_handoff(handoff)


class PortfolioIntakeCliTests(unittest.TestCase):
    def test_private_artifact_cannot_be_written_inside_repository(self):
        payload = draft_payload()
        payload["source_items"][0]["synthetic"] = False
        with tempfile.TemporaryDirectory() as temp_value:
            input_path = Path(temp_value) / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            forbidden = ROOT / "private-portfolio-should-not-exist.json"
            self.assertFalse(forbidden.exists())
            self.assertEqual(
                2,
                intake_main(["draft", "--input", str(input_path), "--output", str(forbidden)]),
            )
            self.assertFalse(forbidden.exists())

    def test_cli_draft_confirm_validate_and_risk_input(self):
        with tempfile.TemporaryDirectory() as temp_value:
            temp = Path(temp_value)
            payload_path = temp / "payload.json"
            draft_path = temp / "draft.json"
            handoff_path = temp / "handoff.json"
            risk_path = temp / "risk.json"
            council_path = temp / "council.json"
            payload_path.write_text(json.dumps(draft_payload(4)), encoding="utf-8")
            self.assertEqual(0, intake_main(["draft", "--input", str(payload_path), "--output", str(draft_path)]))
            self.assertEqual(
                0,
                intake_main(
                    [
                        "confirm", "--draft", str(draft_path), "--output", str(handoff_path),
                        "--confirmed-at", "2026-09-11T20:05:00+08:00",
                        "--holding-horizon", "12 months", "--research-question", "review all",
                        "--explicit-confirmation", "CONFIRM_PORTFOLIO",
                    ]
                ),
            )
            self.assertEqual(0, intake_main(["validate-handoff", "--handoff", str(handoff_path), "--draft", str(draft_path)]))
            self.assertEqual(0, intake_main(["risk-input", "--handoff", str(handoff_path), "--output", str(risk_path)]))
            self.assertEqual(4, len(json.loads(risk_path.read_text())["portfolio"]["positions"]))
            self.assertEqual(0, intake_main(["council-input", "--handoff", str(handoff_path), "--output", str(council_path)]))
            self.assertEqual(4, len(json.loads(council_path.read_text())["portfolio"]["positions"]))


class PortfolioIntakeSkillTests(unittest.TestCase):
    def test_skill_is_discoverable_and_keeps_intake_boundary(self):
        skill = ROOT / "product/skills/portfolio-intake/SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text(encoding="utf-8")
        self.assertIn("name: portfolio-intake", text)
        self.assertIn("Codex 原生图片理解", text)
        self.assertIn("ALL_INPUT_POSITIONS", text)
        self.assertIn("不得自动调用 `portfolio-council`", text)
        self.assertIn("禁止调用 Python OCR", text)


if __name__ == "__main__":
    unittest.main()
