from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from product.trading_journal.reflection import (
    PHASES, ReflectionError, assemble_report, compare_episodes,
    counterfactual_hold, prepare_counterfactuals, prepare_reflection, save_packet,
    render_markdown, save_report, validate_packet, validate_report,
)
from product.trading_journal.common import canonical_hash
from product.trading_journal.analysis import analyze_records
from product.trading_journal.presentation import build_reader_labels, readable_text


CUTOFF = "2026-09-30T23:00:00Z"
RETRIEVED = "2026-09-30T20:00:00Z"
WIN_ID = "episode-" + canonical_hash({"opening_record_id": "buy-win", "closing_record_id": "sell-win", "quantity": "1", "direction": "LONG", "opening_revision": None, "closing_revision": None})
LOSS_ID = "episode-" + canonical_hash({"opening_record_id": "buy-loss", "closing_record_id": "sell-loss", "quantity": "1", "direction": "LONG", "opening_revision": None, "closing_revision": None})


def record(identifier, occurred, **changes):
    result = {"record_id": identifier, "activity_type": "FILL", "source_id": "synthetic:statement", "as_of": occurred, "retrieved_at": RETRIEVED, "occurred_at": occurred, "time_precision": "SECOND", "instrument": {"key": "US:AAPL:USD", "symbol": "AAPL", "asset_type": "STOCK", "market": "US", "currency": "USD", "exchange_timezone": "America/New_York"}, "quantity": "1", "price": "100", "fees": "1", "fees_complete": True, "side": "BUY", "currency": "USD"}
    result.update(changes)
    return result


def snapshot():
    rows = [record("buy-win", "2026-01-05T14:30:00Z"), record("sell-win", "2026-01-06T16:00:00Z", side="SELL", price="110"), record("buy-loss", "2026-01-07T14:30:00Z"), record("sell-loss", "2026-01-08T16:00:00Z", side="SELL", price="90"), record("option-open", "2026-01-09T16:00:00Z", instrument={"key": "US:AAPL:260116C100", "asset_type": "OPTION", "symbol": "AAPL260116C100", "market": "US", "currency": "USD", "underlying": "AAPL", "exchange_timezone": "America/New_York", "multiplier": "10"})]
    opening = {"US:AAPL:USD": {"quantity": "0", "source_id": "synthetic:opening-zero", "as_of": "2026-01-01T00:00:00Z", "retrieved_at": RETRIEVED}}
    analysis = analyze_records(rows, opening_positions=opening)
    result = {"kind": "TradeJournalSnapshot", "schema_version": "1.0.0", "snapshot_id": "snapshot-test", "account_ref": "local-random-account-ref", "source_id": "synthetic:journal", "as_of": CUTOFF, "retrieved_at": RETRIEVED, "records": rows, "context_records": [], "opening_positions": opening, "coverage": {"status": "PARTIAL", "gaps": ["开户起点未知"]}, "analysis": analysis, "market": []}
    result["input_hash"] = canonical_hash({key: result[key] for key in ("records", "coverage", "analysis", "market", "context_records", "opening_positions")})
    return result


def evidence(identifier, available, **changes):
    result = {"evidence_id": identifier, "kind": "COMPANY_EVENT", "source_id": "synthetic:public", "as_of": "2026-01-05T00:00:00Z", "retrieved_at": RETRIEVED, "available_at": available, "availability_basis": "官方发布时刻", "publication_precision": "SECOND", "record_refs": ["buy-win"]}
    result.update(changes)
    return result


def packet(**kwargs):
    return prepare_reflection(snapshot(), chart_refs=["chart:frozen-snapshot-test"], **kwargs)


def report(value=None):
    value = value or packet()
    findings = [{"finding_id": "finding-1", "pattern": "原始计划资料不足", "record_refs": ["buy-win", "sell-win"], "episode_refs": [WIN_ID], "chart_refs": ["chart:frozen-snapshot-test"], "calculation_refs": [f"episode:{WIN_ID}"], "process_observation": "能核验入场和退出，但没有当时计划。", "result_observation": "确定性结果见对应片段。", "interpretation": "需要记录计划才能检验执行过程。", "confidence_limits": "无法由盈利反推原始动机或过程质量。", "alternative_explanations": [{"text": "亏损片段可能有合理过程；资料不足以认定纪律问题。", "record_refs": ["buy-loss", "sell-loss"], "episode_refs": [LOSS_ID], "evidence_refs": []}], "financial_claims": [{"calculation_ref": f"episode:{WIN_ID}", "metric": "net_pnl", "value": "8"}]}]
    plan = [{"improvement_id": "practice-1", "finding_refs": ["finding-1"], "record_refs": ["buy-win"], "evidence_refs": [], "exercise": "交易前记录 Thesis 与失效条件", "next_inputs": ["计划记录时刻", "预期持有期"], "verification": "复查记录是否早于成交、退出理由是否与原计划一致", "review_window": "后续四周", "status": "PROPOSED"}]
    return assemble_report(value, findings=findings, improvement_plan=plan, model_version="test-model-no-call", skill_version="1.0.0", phase_coverage={phase: {"status": "DATA_LIMITED", "reason": "合成样例，不证明实际推理质量"} for phase in PHASES}, report_as_of="2026-10-01T00:00:00Z", analyzed_episode_ids=[WIN_ID])


def counterfactual_input():
    value = snapshot()
    for item in value["records"]:
        item["activity_type"] = "FILL"
        item["currency"] = "USD"
        item["fees_complete"] = True
    value["records"][1]["price"] = "110"
    value["analysis"]["episodes"][0].update(direction="LONG", instrument_key="US:AAPL:USD")
    quote = {"date": "2026-01-12", "open": "119", "high": "121", "low": "118", "close": "120", "volume": "1000", "source_id": "synthetic:ohlcv", "as_of": "2026-01-12", "retrieved_at": RETRIEVED, "available_at": "2026-01-12T21:10:00Z"}
    market = {"kind": "TradeJournalMarket", "schema_version": "1.0.0", "instrument_key": "US:AAPL:USD", "currency": "USD", "exchange_timezone": "America/New_York", "source_id": "synthetic:market", "as_of": "2026-01-12", "retrieved_at": RETRIEVED, "requested_range": {"start": "2026-01-01", "end": "2026-01-12"}, "price_basis": "UNADJUSTED", "price_basis_evidence": {"source_id": "synthetic:market-methodology", "as_of": "2026-01-12", "retrieved_at": RETRIEVED, "corporate_actions_complete": True, "identity_continuity_verified": True, "daily_bars_final_verified": True}, "candles": [quote], "events": [], "gaps": []}
    market["content_hash"] = canonical_hash(market)
    value["market"] = [market]
    value["input_hash"] = canonical_hash({key: value[key] for key in ("records", "coverage", "analysis", "market", "context_records", "opening_positions")})
    return value


def assumed_costs():
    return {"source_id": "synthetic:user-assumptions", "as_of": CUTOFF, "retrieved_at": RETRIEVED, "currency": "USD", "complete": True, "assumptions": "假设延期退出费用为1，无其他持有成本和现金分配；不改变其他交易。", "exit_fees": "1", "holding_costs": "0", "cash_distributions": "0"}


def rehash_snapshot(value):
    for market in value["market"]:
        market.pop("content_hash", None)
        market["content_hash"] = canonical_hash(market)
    fields = ["records", "coverage", "analysis", "market"] + [key for key in ("context_records", "opening_positions") if key in value]
    value["input_hash"] = canonical_hash({key: value[key] for key in fields})
    return value


class TradingReflectionTests(unittest.TestCase):
    def test_intraday_close_and_evening_event_are_outcome(self):
        value = packet(evidence=[evidence("earlier", "2026-01-04T18:00:00Z"), evidence("evening", "2026-01-05T22:00:00Z"), evidence("daily", "2026-01-05T14:00:00Z", kind="DAILY_OHLCV", session_close_at="2026-01-05T21:00:00Z")])
        partition = value["record_layers"]["buy-win"]
        self.assertEqual([item["evidence_id"] for item in partition["contemporaneous"]], ["earlier"])
        self.assertEqual({item["evidence_id"] for item in partition["outcome"]}, {"evening", "daily"})

    def test_macro_revisions_unknown_vintage_and_date_publication(self):
        value = packet(evidence=[evidence("revised", "2026-01-01T14:00:00Z", kind="MACRO", vintage_status="REVISED"), evidence("vintage-unknown", "2026-01-01T14:00:00Z", kind="MACRO"), evidence("date-only", "2026-01-05", publication_precision="DATE"), evidence("original", "2026-01-01T14:00:00Z", kind="MACRO", vintage_status="ORIGINAL_RELEASE", vintage_available_at="2026-01-01T14:00:00Z")])
        partition = value["record_layers"]["buy-win"]
        self.assertEqual({item["evidence_id"] for item in partition["uncertain"]}, {"revised", "vintage-unknown", "date-only"})
        self.assertEqual([item["evidence_id"] for item in partition["contemporaneous"]], ["original"])

    def test_missing_availability_basis_cannot_enter_decision_layer(self):
        value = packet(evidence=[evidence("no-basis", "2026-01-01T14:00:00Z", availability_basis="")])
        self.assertFalse(value["record_layers"]["buy-win"]["contemporaneous"])
        self.assertEqual(value["record_layers"]["buy-win"]["uncertain"][0]["evidence_id"], "no-basis")

    def test_retrospective_diary_cannot_be_original_intent(self):
        value = packet(diary=[{"diary_id": "later", "record_refs": ["buy-win"], "recorded_at": "2026-01-06T10:00:00Z", "source_id": "synthetic:diary", "as_of": "2026-01-06T10:00:00Z", "retrieved_at": RETRIEVED, "text": "后来补写的买入理由"}])
        self.assertEqual(value["record_layers"]["buy-win"]["original_intent_status"], "UNKNOWN")
        result = report(value)
        result["findings"][0]["diary_refs"] = ["later"]
        result["findings"][0]["intent_claims"] = [{"record_id": "buy-win", "diary_id": "later", "layer": "AT_TIME"}]
        with self.assertRaisesRegex(ReflectionError, "事后日记"):
            validate_report(result, value)
        result["findings"][0]["intent_claims"][0]["layer"] = "RETROSPECTIVE"
        validate_report(result, value)

    def test_entire_history_and_result_classes_are_not_silently_discarded(self):
        value = packet(batch_size=1, selection_reasons={WIN_ID: "检验盈利也可能存在过程缺口"})
        self.assertEqual(value["scope"]["record_ids"], sorted(row["record_id"] for row in snapshot()["records"]))
        self.assertEqual(value["whole_history_statistics"]["by_currency"][0]["net_pnl"], "-4")
        self.assertEqual(value["case_selection"]["available_by_result"], {"POSITIVE_RESULT": [WIN_ID], "NEGATIVE_RESULT": [LOSS_ID], "BOUNDARY": ["activity:option-open"]})
        self.assertEqual(value["case_selection"]["omitted_classes"], ["NEGATIVE_RESULT", "BOUNDARY"])
        self.assertEqual(value["progress"]["total_units"], 3)
        self.assertEqual(len(value["progress"]["batches"]), 3)
        result = report(value)
        self.assertEqual(set(result["progress"]["pending_episode_ids"]), {LOSS_ID, "activity:option-open"})
        self.assertEqual(result["progress"]["status"], "PARTIAL")

    def test_explicit_subset_and_cross_scope_episode_are_visible(self):
        value = packet(selected_record_ids=["buy-win"])
        self.assertEqual(value["scope"]["mode"], "EXPLICIT_SUBSET")
        self.assertEqual(len(value["scope"]["excluded_record_ids"]), 4)
        self.assertTrue(value["episodes"][0]["crosses_scope"])

    def test_comparison_only_returns_tool_numbers_and_refs(self):
        result = compare_episodes(packet(), [WIN_ID, LOSS_ID])
        self.assertEqual([item["metrics"]["net_pnl"] for item in result["items"]], ["8", "-12"])
        self.assertEqual([item["calculation_ref"] for item in result["items"]], [f"episode:{WIN_ID}", f"episode:{LOSS_ID}"])
        with self.assertRaises(ReflectionError):
            compare_episodes(packet(), ["missing"])

    def test_future_or_uncertain_evidence_rejected_as_decision_reference(self):
        value = packet(evidence=[evidence("evening", "2026-01-05T22:00:00Z")])
        result = report(value)
        result["findings"][0]["decision_evidence_refs"] = ["evening"]
        with self.assertRaisesRegex(ReflectionError, "当时背景"):
            validate_report(result, value)
        result["findings"][0]["decision_evidence_refs"] = []
        result["findings"][0]["outcome_evidence_refs"] = ["evening"]
        validate_report(result, value)

    def test_financial_claims_cannot_override_tool_values(self):
        value = packet()
        result = report(value)
        result["findings"][0]["financial_claims"][0]["value"] = "9"
        with self.assertRaisesRegex(ReflectionError, "确定性工具"):
            validate_report(result, value)
        result = report(value)
        result["findings"][0]["chart_refs"] = ["chart:unfrozen"]
        with self.assertRaisesRegex(ReflectionError, "chart_refs"):
            validate_report(result, value)

    def test_reports_require_alternatives_and_trackable_practice(self):
        value = packet()
        result = report(value)
        result["findings"][0]["alternative_explanations"] = []
        with self.assertRaisesRegex(ReflectionError, "反例"):
            validate_report(result, value)
        result = report(value)
        result["improvement_plan"][0].pop("review_window")
        with self.assertRaisesRegex(ReflectionError, "review_window"):
            validate_report(result, value)

    def test_input_and_report_schema_hashes_reject_tampering(self):
        value = packet()
        result = report(value)
        value["snapshot"]["records"][0]["price"] = "777"
        with self.assertRaisesRegex(ReflectionError, "packet_hash"):
            validate_packet(value)
        value = packet()
        for field in ("input_hash", "snapshot_id", "packet_hash", "schema_version"):
            invalid = deepcopy(result)
            invalid[field] = "invalid"
            with self.assertRaises(ReflectionError):
                validate_report(invalid, value)

    def test_input_is_deep_frozen_without_mutating_caller(self):
        original = snapshot()
        value = prepare_reflection(original)
        original["records"][0]["price"] = "777"
        self.assertEqual(value["snapshot"]["records"][0]["price"], "100")
        validate_packet(value)

    def test_progress_cannot_hide_pending_unit(self):
        value = packet()
        result = report(value)
        result["progress"]["pending_episode_ids"] = [LOSS_ID]
        with self.assertRaisesRegex(ReflectionError, "遗漏"):
            validate_report(result, value)

    def test_immutable_save_private_permissions_and_old_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "private"
            root.mkdir(mode=0o700)
            value = packet()
            frozen_path = save_packet(root, value)
            self.assertEqual(save_packet(root, value), frozen_path)
            result = report(value)
            paths = save_report(root, result, value)
            old_content = Path(paths["json_path"]).read_bytes()
            self.assertEqual(Path(paths["json_path"]).stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(paths["json_path"]).parent.stat().st_mode & 0o777, 0o700)
            self.assertIn("改进练习", Path(paths["markdown_path"]).read_text())
            with self.assertRaisesRegex(ReflectionError, "已存在"):
                save_report(root, result, value)
            new_value = packet()
            second = report(new_value)
            self.assertNotEqual(save_report(root, second, new_value)["report_id"], paths["report_id"])
            self.assertEqual(Path(paths["json_path"]).read_bytes(), old_content)
            self.assertEqual(json.loads(Path(paths["packet_path"]).read_text())["snapshot_id"], "snapshot-test")

    def test_save_rejects_symlink_and_unvalidated_public_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            public = base / "public"
            public.mkdir(mode=0o755)
            value = packet()
            with self.assertRaisesRegex(ReflectionError, "0700"):
                save_report(public, report(value), value)
            private = base / "private"
            private.mkdir(mode=0o700)
            (private / "artifacts").symlink_to(public, target_is_directory=True)
            with self.assertRaisesRegex(ReflectionError, "符号链接"):
                save_report(private, report(value), value)
            self.assertFalse((public / "reflections").exists())

    def test_counterfactual_decimal_window_costs_and_report_reference(self):
        value = prepare_reflection(counterfactual_input(), chart_refs=["chart:frozen-snapshot-test"])
        result = counterfactual_hold(value, WIN_ID, exit_date="2026-01-12", costs=assumed_costs())
        self.assertEqual(result["metrics"]["hypothetical_net_pnl"], "18")
        self.assertEqual(result["metrics"]["difference_net_pnl"], "10")
        self.assertEqual(result["lineage"]["quote_as_of"], "2026-01-12")
        self.assertEqual(result["currency"], "USD")
        self.assertIn("反事实", result["limitations"][0])
        extended = prepare_counterfactuals(value, [{"episode_id": WIN_ID, "exit_date": "2026-01-12", "costs": assumed_costs()}])
        validate_packet(extended)
        self.assertNotEqual(extended["packet_hash"], value["packet_hash"])
        outcome = report(extended)
        outcome["findings"][0]["financial_claims"] = [{"calculation_ref": result["calculation_ref"], "metric": "difference_net_pnl", "value": "10"}]
        validate_report(outcome, extended)

    def test_counterfactual_rejects_option_missing_fee_split_and_unknown_basis(self):
        mutations = [
            lambda value: value["records"][0]["instrument"].update(asset_type="OPTION"),
            lambda value: value["records"][0].update(fees_complete=False),
            lambda value: value["market"][0]["events"].append({"type": "SPLIT", "date": "2026-01-10"}),
            lambda value: value["market"][0].update(price_basis="PROVIDER_UNVERIFIED"),
            lambda value: value["market"][0]["price_basis_evidence"].update(corporate_actions_complete=False),
        ]
        for mutate in mutations:
            value = counterfactual_input()
            mutate(value)
            with self.subTest(mutation=mutate), self.assertRaises(ReflectionError):
                counterfactual_hold(prepare_reflection(rehash_snapshot(value)), WIN_ID, exit_date="2026-01-12", costs=assumed_costs())

    def test_counterfactual_requires_exact_quote_date_and_complete_cost_assumptions(self):
        value = prepare_reflection(counterfactual_input())
        with self.assertRaisesRegex(ReflectionError, "唯一可靠日 K"):
            counterfactual_hold(value, WIN_ID, exit_date="2026-01-11", costs=assumed_costs())
        cost = assumed_costs()
        cost.pop("holding_costs")
        with self.assertRaises(ReflectionError):
            counterfactual_hold(value, WIN_ID, exit_date="2026-01-12", costs=cost)
        cost = assumed_costs()
        cost["currency"] = "HKD"
        with self.assertRaises(ReflectionError):
            counterfactual_hold(value, WIN_ID, exit_date="2026-01-12", costs=cost)

    def test_counterfactual_restores_trusted_constant_factor_and_rejects_varying_factor(self):
        value = counterfactual_input()
        value["market"][0].update(price_basis="ADJUSTED_WITH_FACTORS", adjustment_factors=[{"date": "2026-01-05", "factor": "0.5"}, {"date": "2026-01-12", "factor": "0.5"}])
        value["market"][0]["candles"][0]["close"] = "60"
        result = counterfactual_hold(prepare_reflection(rehash_snapshot(value)), WIN_ID, exit_date="2026-01-12", costs=assumed_costs())
        self.assertEqual(result["metrics"]["hypothetical_exit_price"], "120")
        value["market"][0]["adjustment_factors"][1]["factor"] = "1"
        with self.assertRaisesRegex(ReflectionError, "复权因子"):
            counterfactual_hold(prepare_reflection(rehash_snapshot(value)), WIN_ID, exit_date="2026-01-12", costs=assumed_costs())

    def test_context_records_not_claimed_as_sample_and_fake_input_hash_rejected(self):
        value = snapshot()
        value["context_records"] = [value["records"].pop(0)]
        result = prepare_reflection(rehash_snapshot(value))
        self.assertEqual(result["scope"]["context_record_ids"], ["buy-win"])
        self.assertNotIn("buy-win", result["scope"]["record_ids"])
        self.assertEqual(result["episodes"][0]["missing_context_record_ids"], [])
        value["input_hash"] = "invented-hash"
        with self.assertRaisesRegex(ReflectionError, "input_hash"):
            prepare_reflection(value)

    def test_real_ledger_freeze_contract_is_consumed_without_recalculating(self):
        from product.trading_journal.ledger import Ledger
        from tests.test_trading_journal_core import record as ledger_record

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            rows = [ledger_record(1, day="2026-09-01"), ledger_record(2, side="SELL", price="110", day="2026-09-05")]
            with Ledger(root) as ledger:
                ledger.import_records(rows, mode="SYNTHETIC")
                opening = {rows[0]["instrument"]["key"]: {"quantity": "0", "source_id": "synthetic:opening-zero", "as_of": "2026-08-31T00:00:00Z", "retrieved_at": RETRIEVED}}
                frozen = ledger.freeze_snapshot("account-synthetic-one", opening_positions=opening)
                value = prepare_reflection(frozen)
                self.assertEqual(value["input_hash"], frozen["input_hash"])
                self.assertEqual(value["whole_history_statistics"], frozen["analysis"])
                self.assertEqual(value["episodes"][0]["net_pnl"], "98")
                comparison = compare_episodes(value, [value["episodes"][0]["episode_id"]])
                self.assertEqual(comparison["items"][0]["metrics"]["net_pnl"], "98")

    def test_recomputed_outer_hash_cannot_move_late_evidence_to_at_time(self):
        value = packet(evidence=[evidence("late", "2026-01-05T22:00:00Z")])
        value["record_layers"]["buy-win"]["contemporaneous"] = [{"evidence_id": "late", "reason": "caller changed layer"}]
        value["record_layers"]["buy-win"]["outcome"] = []
        value.pop("packet_hash")
        value["packet_hash"] = canonical_hash(value)
        with self.assertRaisesRegex(ReflectionError, "复现"):
            validate_packet(value)

    def test_recomputed_outer_hash_cannot_rewrite_episode_financial_metrics(self):
        value = packet()
        value["calculations"][f"episode:{WIN_ID}"]["metrics"]["net_pnl"] = "999"
        value.pop("packet_hash")
        value["packet_hash"] = canonical_hash(value)
        with self.assertRaisesRegex(ReflectionError, "复现"):
            validate_packet(value)

    def test_forged_snapshot_analysis_cannot_pass_even_when_all_hashes_are_recomputed(self):
        value = snapshot()
        value["analysis"]["episodes"][0]["net_pnl"] = "999"
        value["analysis"]["by_currency"][0]["net_pnl"] = "987"
        with self.assertRaisesRegex(ReflectionError, "冻结事实复现"):
            prepare_reflection(rehash_snapshot(value))

    def test_counterfactual_calculation_recomputed_from_quote_costs_and_original_fills(self):
        value = prepare_reflection(counterfactual_input())
        extended = prepare_counterfactuals(value, [{"episode_id": WIN_ID, "exit_date": "2026-01-12", "costs": assumed_costs()}])
        ref = next(ref for ref in extended["calculations"] if ref.startswith("counterfactual:"))
        extended["calculations"][ref]["metrics"]["difference_net_pnl"] = "999"
        extended.pop("packet_hash")
        extended["packet_hash"] = canonical_hash(extended)
        with self.assertRaisesRegex(ReflectionError, "复现"):
            validate_packet(extended)

    def test_context_lifecycle_fact_required_to_reproduce_window_analysis(self):
        from product.trading_journal.ledger import Ledger
        from tests.test_trading_journal_core import record as ledger_record
        from product.trading_journal.windows import resolve_window

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            rows = [ledger_record(1, day="2026-09-01"), ledger_record(2, activity="CORPORATE_ACTION", day="2026-09-02"), ledger_record(3, side="SELL", price="110", day="2026-09-05")]
            with Ledger(root) as ledger:
                ledger.import_records(rows, mode="SYNTHETIC")
                opening = {rows[0]["instrument"]["key"]: {"quantity": "0", "source_id": "synthetic:opening-zero", "as_of": "2026-08-31T00:00:00Z", "retrieved_at": RETRIEVED}}
                window = resolve_window("custom", start="2026-09-04", end="2026-09-06", now="2026-09-10T00:00:00Z")
                frozen = ledger.freeze_snapshot("account-synthetic-one", window=window, opening_positions=opening)
                value = prepare_reflection(frozen)
                self.assertEqual(value["scope"]["mode"], "SNAPSHOT_WINDOW")
                self.assertIsNone(value["whole_history_statistics"])
                self.assertEqual(value["episodes"][0]["status"], "UNAVAILABLE")
                self.assertEqual(set(value["scope"]["context_record_ids"]), {rows[0]["record_id"], rows[1]["record_id"]})
                incomplete = deepcopy(frozen)
                incomplete["context_records"] = [row for row in incomplete["context_records"] if row["activity_type"] != "CORPORATE_ACTION"]
                with self.assertRaisesRegex(ReflectionError, "复现"):
                    prepare_reflection(rehash_snapshot(incomplete))

    def test_markdown_transports_phase_reason_and_uncertain_vintage_citation(self):
        material = evidence("macro-vintage-unknown", "2026-01-01T14:00:00Z", kind="MACRO", vintage_status="UNKNOWN", title="合成宏观历史值，原发布版本缺失", source_url="https://example.invalid/synthetic-macro")
        value = packet(evidence=[material])
        result = report(value)
        result["phase_coverage"]["HOLDING"] = {"status": "DATA_LIMITED", "reason": "缺少原发布版本与盘中路径，不能评判当时持有条件。"}
        result["findings"][0]["uncertain_evidence_refs"] = [material["evidence_id"]]
        validate_report(result, value)
        markdown = render_markdown(result, value)
        phase_rows = {parts[0]: (parts[1], parts[2]) for line in markdown.splitlines() if line.startswith("| ") and len(parts := [item.strip() for item in line.strip("|").split("|")]) == 3}
        self.assertEqual(phase_rows["持有"], ("资料有限", result["phase_coverage"]["HOLDING"]["reason"]))
        finding_text = markdown.split(f"### {result['findings'][0]['pattern']}\n", 1)[1].split("## 改进练习", 1)[0]
        self.assertIn("不确定证据：" + material["title"] + "\n", finding_text)
        source_text = markdown.split(f"### {material['title']}\n", 1)[1]
        for field, label in (("title", "标题"), ("source_url", "出处"), ("retrieved_at", "检索时刻"), ("available_at", "可用时刻")):
            self.assertIn(f"{label}：{material[field]}\n", source_text)
        self.assertIn("来源：example.invalid\n", source_text)
        self.assertIn("历史资料状态：未知；可用时刻：未知\n", source_text)
        self.assertNotIn(material["evidence_id"], markdown)
        self.assertNotIn(material["source_id"], markdown)
        changed = deepcopy(result)
        changed["phase_coverage"]["HOLDING"]["reason"] = "新增原始计划后，只能检验计划一致性，仍不能凭收益评定过程。"
        changed_markdown = render_markdown(changed, value)
        self.assertIn(changed["phase_coverage"]["HOLDING"]["reason"], changed_markdown)
        self.assertNotIn(result["phase_coverage"]["HOLDING"]["reason"], changed_markdown)

    def test_markdown_keeps_financial_values_alternative_links_scope_and_exercise_refs(self):
        value = packet(selection_reasons={WIN_ID: "盈利案例用于检查结果与过程是否混用"})
        result = report(value)
        markdown = render_markdown(result, value)
        finding = result["findings"][0]
        claim = finding["financial_claims"][0]
        labels = build_reader_labels(value, result)
        row = next(line for line in markdown.splitlines() if line.startswith("| 净盈亏 |"))
        self.assertEqual([item.strip() for item in row.strip("|").split("|")], ["净盈亏", claim["value"], value["calculations"][claim["calculation_ref"]]["currency"], labels[claim["calculation_ref"]]])
        alternative = finding["alternative_explanations"][0]
        self.assertIn(f"- 反例或替代解释：{alternative['text']}\n  成交引用：{readable_text(alternative['record_refs'], labels)}\n  交易片段：{readable_text(alternative['episode_refs'], labels)}\n  证据引用：无", markdown)
        exercise = result["improvement_plan"][0]
        exercise_text = markdown.split(f"### {exercise['exercise']}\n", 1)[1]
        self.assertIn("对应发现：" + readable_text(exercise["finding_refs"], labels), exercise_text)
        self.assertIn("成交引用：" + readable_text(exercise["record_refs"], labels), exercise_text)
        self.assertIn("下次记录：" + "；".join(exercise["next_inputs"]), exercise_text)
        self.assertIn("尚未选取的结果类别：" + readable_text(result["case_selection"]["omitted_classes"], labels), markdown)
        self.assertIn(f"- 选择 {labels[WIN_ID]}：{result['case_selection']['selected_reasons'][WIN_ID]}", markdown)
        self.assertIn("实际覆盖状态：部分覆盖", markdown)
        self.assertNotIn(result["input_hash"], markdown)
        self.assertNotIn(result["model_version"], markdown)
        self.assertNotIn("输入 hash", markdown)

    def test_new_readable_report_version_keeps_previous_saved_content_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            value = packet(evidence=[evidence("macro-vintage-unknown", "2026-01-01T14:00:00Z", kind="MACRO", vintage_status="UNKNOWN")])
            previous = report(value)
            previous_paths = save_report(root, previous, value)
            old_bytes = {name: Path(path).read_bytes() for name, path in previous_paths.items() if name != "report_id"}
            revision = report(value)
            revision["phase_coverage"]["HOLDING"] = {"status": "DATA_LIMITED", "reason": "宏观原版本无法取得，持有解释保持条件性。"}
            revision["findings"][0]["uncertain_evidence_refs"] = ["macro-vintage-unknown"]
            paths = save_report(root, revision, value)
            self.assertNotEqual(paths["report_id"], previous_paths["report_id"])
            markdown = Path(paths["markdown_path"]).read_text()
            self.assertIn("| 持有 | 资料有限 | 宏观原版本无法取得，持有解释保持条件性。 |", markdown)
            self.assertIn("不确定证据：宏观资料 1\n", markdown)
            for name, data in old_bytes.items():
                self.assertEqual(Path(previous_paths[name]).read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
