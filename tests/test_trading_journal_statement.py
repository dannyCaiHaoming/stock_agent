"""Verified statement contract, using synthetic identities and transactions only."""

import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from product.trading_journal.common import JournalError
from product.trading_journal.ledger import Ledger
from product.trading_journal.normalization import parse_csv
from product.trading_journal.statement import is_statement, parse_statement


AS_OF = "2026-10-01T01:00:00Z"
REFS = {"account_ref": "account-synthetic-one", "source_id": "source-synthetic-statement",
        "as_of": AS_OF, "retrieved_at": AS_OF}
# These are the observed official source columns, including both distinct
# 交易费用 components. Test data does not reuse the implementation's constants.
FEE_COLUMNS = [
    "交易费用", "其他代收", "结算费", "证监会费", "期权监管费", "印花税", "交易征费", "清算费",
    "交易活动费", "交易所费用", "期货监管费", "佣金", "平台费", "期权交收费", "申购费用",
    "赎回费用", "转换费用", "菲律宾股票交易税", "税收服务费", "会计及财汇局交易征费",
    "交易系统使用费", "交易费用", "佣金费用", "经手费", "证管费", "过户费(中国结算)",
    "过户费(香港结算)", "借券印花税", "综合审计追踪费", "处理费", "清结算指令费",
    "DVP指令附加费", "IPO-中签交易费", "IPO-中签手续费", "IPO账户结算费", "IPO-手续费",
]
PRODUCT_HEADER = ["金融产品信息", "", "", "", "代码", "发行人", "描述", "倍数", "期限", "行权价", "类型"]


def header(asset="股票"):
    result = ["交易明细", "", "", "", "代码", "市场", "交易所", "交易类型", "数量", "交易价格", "成交额"]
    if asset != "期权":
        result.append("成交应计利息")
    return result + FEE_COLUMNS + ["消费税", "已实现的损益", "说明", "成交时间", "交收日期", "币种"]


def detail(*, code="", asset="股票", qty="1", price="10", amount="10", fees=None, tax="0",
           trade_type="开仓", timestamp="2026-07-01 09:47:28, US/Eastern", market="US", currency="USD",
           role="DATA", description="", interest="0"):
    result = ["交易明细", asset, "", role, code, market, "NASDAQ", trade_type, qty, price, amount]
    if asset != "期权":
        result.append(interest)
    components = ["0"] * len(FEE_COLUMNS)
    for index, value in (fees or {}).items():
        components[index] = value
    return result + components + [tax, "0", description, timestamp, "2026-07-02", currency]


def single_group(**kwargs):
    asset = kwargs.get("asset", "股票")
    code = "示例ETF (EXMP 20260717 PUT 60.0)" if asset == "期权" else "示例公司 (EXMP)"
    return [header(asset), detail(code=code, **kwargs), detail(**kwargs)]


def product(*, expiry="2026-07-17", strike="60", right="PUT", multiplier="25", underlying="EXMP"):
    return ["金融产品信息", "期权", "", "DATA", underlying, "PRIVATE ISSUER", "PRIVATE PRODUCT DESCRIPTION",
            multiplier, expiry, strike, right]


def encode(rows):
    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


class StatementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "synthetic-statement.csv"

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, rows, *, direct=False, **kwargs):
        self.path.write_bytes(encode(rows))
        parser = parse_statement if direct else parse_csv
        return parser(self.path, **REFS, **kwargs)

    def reject(self, rows, code):
        with self.assertRaises(JournalError) as caught:
            self.parse(rows)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn("PRIVATE", str(caught.exception))
        self.assertNotIn("99887766", str(caught.exception))

    def test_full_header_detection_not_preamble_keyword(self):
        rows = [["账户信息", "PRIVATE NAME", "99887766", "交易明细"], ["Symbol", "Side", "Quantity", "Price", "Trade Date"]]
        self.assertFalse(is_statement(encode(rows)))
        valid = single_group()
        self.assertTrue(is_statement(encode(rows + valid)))
        malformed = single_group()
        malformed[0][-1] = "未知币种列"
        self.assertFalse(is_statement(encode(malformed)))
        self.assertFalse(is_statement(encode(valid).decode("utf-8-sig").encode("utf-16")))
        self.assertFalse(is_statement("交易明细"))

    def test_parent_and_total_excluded_same_second_children_survive(self):
        rows = [header(), detail(code="示例公司 (EXMP)", qty="2", amount="20", fees={11: "-1"}),
                detail(fees={11: "-0.5"}), detail(fees={11: "-0.5"}), ["交易明细", "股票", "", "TOTAL"]]
        records = self.parse(rows, direct=True)
        self.assertEqual(len(records), 2)
        self.assertEqual([item["quantity"] for item in records], ["1", "1"])
        self.assertNotEqual(records[0]["record_id"], records[1]["record_id"])
        self.assertEqual([item["source_location"] for item in records], [
            {"row": 3, "parent_row": 2, "section": "交易明细"}, {"row": 4, "parent_row": 2, "section": "交易明细"}])
        self.assertEqual(records[0]["identity_status"], "FILE_ROW_ONLY")
        self.assertIsNone(records[0]["source_record_id"])
        self.assertEqual(records[0]["fees"], "0.5")
        self.assertFalse(records[0]["fees_complete"])

    def test_partial_fills_preserve_individual_prices_and_signed_quantity(self):
        rows = [header(), detail(code="示例公司 (EXMP)", qty="-3", price="12", amount="-36", fees={11: "-1.2"}, trade_type="平仓"),
                detail(qty="-1", price="10", amount="-10", fees={11: "-0.4"}, trade_type="平仓"),
                detail(qty="-2", price="13", amount="-26", fees={11: "-0.8"}, trade_type="平仓")]
        records = self.parse(rows)
        self.assertEqual([item["side"] for item in records], ["SELL", "SELL"])
        self.assertEqual([item["quantity"] for item in records], ["1", "2"])
        self.assertEqual([item["price"] for item in records], ["10", "13"])
        self.assertEqual([item["fees"] for item in records], ["0.4", "0.8"])
        self.assertEqual([item["amount"] for item in records], ["-10", "-26"])
        self.assertEqual([item["position_effect"] for item in records], ["CLOSE", "CLOSE"])

    def test_statement_records_pass_existing_ledger_allowlist_and_repeat_import(self):
        rows = [header(), detail(code="示例公司 (EXMP)", qty="2", amount="20"), detail(), detail()]
        records = self.parse(rows)
        with Ledger(Path(self.temp.name)) as ledger:
            first = ledger.import_records(records)
            second = ledger.import_records(records)
            snapshot = ledger.freeze_snapshot(REFS["account_ref"])
        self.assertEqual(first["inserted"], 2)
        self.assertEqual(second["unchanged"], 2)
        self.assertEqual(len(snapshot["records"]), 2)
        self.assertEqual(snapshot["coverage"]["status"], "PARTIAL")

    def test_all_fee_components_including_duplicate_positions_and_tax(self):
        records = self.parse(single_group(fees={0: "-0.1", 11: "-0.3", 21: "-0.2", 35: "-0.4"}, tax="-0.05"))
        self.assertEqual(records[0]["fees"], "1.05")
        self.assertFalse(records[0]["fees_complete"])

    def test_blank_tax_is_unknown_and_never_published_as_zero_fee(self):
        rows = [header(), detail(code="示例公司 (EXMP)", qty="2", amount="20", fees={11: "-1"}, tax=""),
                detail(fees={11: "-0.5"}, tax=""), detail(fees={11: "-0.5"}, tax="")]
        records = self.parse(rows)
        self.assertEqual([item["fees"] for item in records], [None, None])
        self.assertTrue(all(item["fees_complete"] is False for item in records))
        for parent_tax, child_tax in (("", "0"), ("0", "")):
            with self.subTest(parent_tax=parent_tax):
                self.reject([header(), detail(code="示例公司 (EXMP)", tax=parent_tax), detail(tax=child_tax)], "STATEMENT_RECONCILIATION_FAILED")
        self.reject([header(), detail(code="示例公司 (EXMP)", qty="2", amount="20", tax=""),
                     detail(tax=""), detail(tax="0")], "STATEMENT_RECONCILIATION_FAILED")
        self.reject(single_group(fees={11: ""}), "INCOMPLETE_STATEMENT_DETAIL")

    def test_actual_price_amount_check_uses_source_sign_and_currency_rounding(self):
        self.assertEqual(self.parse(single_group(price="10.005", amount="10"))[0]["price"], "10.005")
        self.assertEqual(self.parse(single_group(price="10", amount="10.01"))[0]["amount"], "10.01")
        self.reject(single_group(price="999"), "STATEMENT_PRICE_AMOUNT_CONFLICT")
        self.reject(single_group(amount="-10"), "STATEMENT_PRICE_AMOUNT_CONFLICT")
        self.reject(single_group(amount="10.011"), "STATEMENT_PRICE_AMOUNT_CONFLICT")
        self.reject(single_group(price="0.005", amount="-0.005"), "STATEMENT_PRICE_AMOUNT_CONFLICT")
        self.assertEqual(self.parse(single_group(price="0.005", amount="0"))[0]["amount"], "0")
        self.reject(single_group(asset="期权", amount="-10"), "STATEMENT_PRICE_AMOUNT_CONFLICT")
        self.reject(single_group(currency="EUR"), "STATEMENT_AMOUNT_PRECISION_UNKNOWN")
        self.reject([PRODUCT_HEADER, product(multiplier="25")] + single_group(asset="期权", price="2", amount="200"), "STATEMENT_PRICE_AMOUNT_CONFLICT")

    def test_reconciliation_rejects_quantity_amount_fee_and_interest_conflicts(self):
        child = detail()
        cases = [
            (detail(code="示例公司 (EXMP)", qty="2"), child),
            (detail(code="示例公司 (EXMP)", amount="11"), child),
            (detail(code="示例公司 (EXMP)", fees={11: "-1"}), child),
            (detail(code="示例公司 (EXMP)", fees={0: "-1"}), detail(fees={21: "-1"})),
            (detail(code="示例公司 (EXMP)", interest="-1"), child),
        ]
        for parent, subrow in cases:
            with self.subTest(parent=parent[8:11]):
                self.reject([header(), parent, subrow], "STATEMENT_RECONCILIATION_FAILED")

    def test_orphan_missing_child_and_wrong_role_rejected(self):
        self.reject([header(), detail()], "STATEMENT_ORPHAN_DETAIL")
        self.reject([header(), detail(code="示例公司 (EXMP)")], "STATEMENT_DETAIL_REQUIRED")
        self.reject([header(), detail(code="示例公司 (EXMP)", role="PRIVATE")], "UNKNOWN_STATEMENT_FORMAT")

    def test_unknown_header_after_valid_header_rejected(self):
        rows = single_group()
        unknown = header()
        unknown[11] = "未经核验费用"
        self.reject(rows + [unknown, detail(code="示例公司 (EXMP)"), detail()], "UNKNOWN_STATEMENT_FORMAT")
        rows = single_group()
        rows[-1].append("PRIVATE ACCOUNT NUMBER")
        self.reject(rows, "UNKNOWN_STATEMENT_FORMAT")

    def test_child_security_context_inherited_but_conflicts_rejected(self):
        rows = [header(), detail(code="示例公司 (EXMP)"), detail(market="", currency="", trade_type="")]
        item = self.parse(rows)[0]
        self.assertEqual((item["instrument"]["market"], item["currency"], item["position_effect"]), ("US", "USD", "OPEN"))
        for kwargs in ({"market": "HK"}, {"currency": "HKD"}):
            with self.subTest(kwargs=kwargs):
                self.reject([header(), detail(code="示例公司 (EXMP)"), detail(**kwargs)], "STATEMENT_IDENTITY_CONFLICT")
        self.reject([header(), detail(code="示例公司 (EXMP)"), detail(trade_type="平仓")], "POSITION_EFFECT_CONFLICT")

    def test_source_time_suffix_per_row_and_canonical_iana_zone(self):
        rows = single_group()
        rows += [header(), detail(code="示例港股 (01191)", timestamp="2026-06-16 15:18:21, GMT+8", market="HK", currency="HKD"),
                 detail(timestamp="2026-06-16 15:18:21, GMT+8", market="HK", currency="HKD")]
        records = self.parse(rows, source_timezone="PER_ROW")
        self.assertEqual(records[0]["occurred_at"], "2026-07-01T13:47:28Z")
        self.assertEqual(records[0]["source_timezone"], "America/New_York")
        self.assertEqual(records[1]["occurred_at"], "2026-06-16T07:18:21Z")
        self.assertEqual(records[1]["source_timezone"], "Etc/GMT-8")
        self.assertEqual(records[1]["instrument"]["symbol"], "01191")
        self.assertEqual(records[1]["instrument"]["exchange_timezone"], "Asia/Hong_Kong")

    def test_official_quoted_multiline_time_preserves_physical_row_location(self):
        rows = single_group(timestamp="2026-07-01\n09:47:28, US/Eastern")
        rows += [header(), detail(code="示例港股 (01191)", timestamp="2026-06-16\r\n15:18:21, GMT+8", market="HK", currency="HKD"),
                 detail(timestamp="2026-06-16\r\n15:18:21, GMT+8", market="HK", currency="HKD")]
        records = self.parse(rows, source_timezone="PER_ROW")
        self.assertEqual([item["occurred_at"] for item in records], ["2026-07-01T13:47:28Z", "2026-06-16T07:18:21Z"])
        self.assertEqual([item["source_location"] for item in records], [
            {"row": 4, "parent_row": 2, "section": "交易明细"}, {"row": 9, "parent_row": 7, "section": "交易明细"}])
        for separator in ("\n\n", "\t"):
            with self.subTest(separator=separator):
                self.reject(single_group(timestamp=f"2026-07-01{separator}09:47:28, US/Eastern"), "UNKNOWN_TIME_FORMAT")

    def test_naive_invalid_or_dst_ambiguous_timestamp_not_guessed(self):
        for timestamp, code in (
            ("2026-07-01 09:47:28", "UNKNOWN_TIME_FORMAT"),
            ("2026-07-01 09:47:28, PRIVATE/Zone", "INVALID_TIMEZONE"),
            ("2026-11-01 01:30:00, US/Eastern", "AMBIGUOUS_LOCAL_TIME"),
            ("2026-03-08 02:30:00, US/Eastern", "AMBIGUOUS_LOCAL_TIME"),
            ("2026-99-01 09:47:28, US/Eastern", "UNKNOWN_TIME_FORMAT"),
        ):
            with self.subTest(timestamp=timestamp):
                self.reject(single_group(timestamp=timestamp), code)
        with self.assertRaises(JournalError) as caught:
            self.parse(single_group(), source_timezone="Asia/Shanghai")
        self.assertEqual(caught.exception.code, "SOURCE_TIMEZONE_CONFLICT")

    def test_option_multiplier_exact_identity_multiple_expiries_and_unknown_adjustment(self):
        rows = [PRODUCT_HEADER, product(), product(expiry="2026-08-21", multiplier="10")]
        rows += single_group(asset="期权", price="2", amount="50")
        rows += [header("期权"), detail(code="示例ETF (EXMP 20260821 PUT 60.0)", asset="期权", price="2", amount="20"),
                 detail(asset="期权", price="2", amount="20")]
        records = self.parse(rows)
        first, second = [item["instrument"] for item in records]
        self.assertEqual(first["symbol"], "EXMP_20260717_PUT_60")
        self.assertEqual((first["underlying"], first["expiry"], first["right"], first["strike"]), ("EXMP", "2026-07-17", "PUT", "60"))
        self.assertEqual([first["multiplier"], second["multiplier"]], ["25", "10"])
        self.assertEqual(first["adjustment_status"], "UNKNOWN")
        self.assertIn("adjustment_status", first["unknown_fields"])
        self.assertNotEqual(first["key"], second["key"])
        self.assertNotIn("PRIVATE", json.dumps(records))

    def test_option_missing_metadata_never_defaults_100(self):
        item = self.parse(single_group(asset="期权"))[0]["instrument"]
        self.assertIsNone(item["multiplier"])
        self.assertEqual(item["adjustment_status"], "UNKNOWN")
        self.assertIn("multiplier", item["unknown_fields"])
        rows = [PRODUCT_HEADER, product(strike="61")] + single_group(asset="期权")
        self.assertIsNone(self.parse(rows)[0]["instrument"]["multiplier"])

    def test_conflicting_or_invalid_multiplier_metadata_rejected(self):
        self.reject([PRODUCT_HEADER, product(), product(multiplier="100")] + single_group(asset="期权"), "OPTION_MULTIPLIER_CONFLICT")
        self.reject([PRODUCT_HEADER, product(multiplier="0")] + single_group(asset="期权"), "INVALID_MULTIPLIER")
        invalid = PRODUCT_HEADER.copy()
        invalid[7] = "未知倍数"
        self.reject([invalid, product()] + single_group(asset="期权"), "UNKNOWN_STATEMENT_FORMAT")

    def test_security_display_format_unknown_contract_not_passed_to_generic_instrument(self):
        rows = single_group()
        rows[1][4] = "EXMP"
        self.reject(rows, "INVALID_SYMBOL")
        rows = single_group(asset="期权")
        rows[1][4] = "PRIVATE NAME (EXMP 20260717 UNKNOWN 60)"
        self.reject(rows, "INVALID_OPTION_IDENTITY")

    def test_explicit_etf_self_label_and_non_requested_sections(self):
        rows = [header(), ["交易明细", "FUND", "", "DATA", "PRIVATE FUND", "PRIVATE CASH"],
                ["交易明细", "外汇", "", "DATA", "PRIVATE FX"]]
        rows += [header(), detail(code="示例ETF (EXMP)"), detail()]
        records = self.parse(rows)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["instrument"]["asset_type"], "ETF")
        self.assertNotIn("PRIVATE", json.dumps(records))
        self.reject([header(), ["交易明细", "FUND", "", "DATA", "PRIVATE FUND"]], "EMPTY_EXPORT_UNPROVEN")
        self.reject(single_group(asset="UNKNOWN"), "UNKNOWN_STATEMENT_ASSET")
        for unknown_label in ("股票非ETF", "股票NOT ETF", "股票ETF"):
            with self.subTest(label=unknown_label):
                self.reject(single_group(asset=unknown_label), "UNKNOWN_STATEMENT_ASSET")
        for source_name in ("示例不是ETF", "示例非 ETF", "示例不是 ETF", "Example NOT ETF", "Example NOT AN ETF"):
            with self.subTest(source_name=source_name):
                rows = [header(), detail(code=f"{source_name} (EXMP)"), detail()]
                self.assertEqual(self.parse(rows)[0]["instrument"]["asset_type"], "STOCK")

    def test_private_preamble_cash_and_multiline_descriptions_never_leak(self):
        rows = [["账户信息", "PRIVATE NAME", "99887766", "PRIVATE ADDRESS"],
                ["现金报告", "USD", "", "DATA", "PRIVATE CASH BALANCE"]]
        rows += single_group(description="PRIVATE DESCRIPTION\nPRIVATE SECOND LINE")
        rows += [["地址", "PRIVATE ADDRESS", "99887766"], ["现金报告", "USD", "", "DATA", "PRIVATE CASH BALANCE"]]
        records = self.parse(rows)
        serialized = json.dumps(records, ensure_ascii=False)
        self.assertNotIn("PRIVATE", serialized)
        self.assertNotIn("99887766", serialized)
        self.assertNotIn("示例公司", serialized)
        self.assertEqual(records[0]["source_location"], {"row": 6, "parent_row": 4, "section": "交易明细"})
        self.assertEqual(records[0]["source_hash"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(records, self.parse(rows))
        other_account = parse_csv(self.path, **{**REFS, "account_ref": "account-synthetic-two"})
        self.assertNotEqual(records[0]["record_id"], other_account[0]["record_id"])

    def test_trade_type_direction_and_fee_sign_fail_closed(self):
        self.reject(single_group(trade_type="PRIVATE UNKNOWN"), "UNKNOWN_STATEMENT_TRADE_TYPE")
        self.reject(single_group(trade_type="开仓做空"), "POSITION_EFFECT_CONFLICT")
        item = self.parse(single_group(trade_type="开仓做空", qty="-1", amount="-10"))[0]
        self.assertEqual((item["side"], item["position_effect"]), ("SELL", "OPEN"))
        self.reject(single_group(fees={11: "1"}), "UNKNOWN_STATEMENT_FEE_SIGN")
        self.reject([header(), detail(code="示例公司 (EXMP)"), detail(qty="-1", amount="-10")], "STATEMENT_DIRECTION_CONFLICT")

    def test_generic_csv_behavior_and_per_row_not_accepted_without_statement(self):
        self.path.write_text("Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Trade Time,Total Fees\nEXMP,STOCK,US,USD,BUY,2,10,2026-07-01T13:47:28Z,1\n", encoding="utf-8")
        item = parse_csv(self.path, **REFS)[0]
        self.assertEqual((item["quantity"], item["fees"], item["fees_complete"]), ("2", "1", True))
        with self.assertRaises(JournalError) as caught:
            parse_csv(self.path, **REFS, source_timezone="PER_ROW")
        self.assertEqual(caught.exception.code, "INVALID_TIMEZONE")
        with self.assertRaises(JournalError) as caught:
            parse_statement(self.path, **REFS)
        self.assertEqual(caught.exception.code, "UNKNOWN_STATEMENT_FORMAT")
        with self.assertRaises(JournalError) as caught:
            self.parse(single_group(), activity_type="ORDER")
        self.assertEqual(caught.exception.code, "ACTIVITY_TYPE_CONFLICT")


if __name__ == "__main__":
    unittest.main()
