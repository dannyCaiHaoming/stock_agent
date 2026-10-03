"""交易图表与行情的离线语义边界；全部行情由桩提供。"""
from datetime import UTC, datetime, timedelta
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.trading_journal.charts import chart_payload, render_chart
from product.trading_journal.common import JournalError
from product.trading_journal.market import fetch_market, yahoo_get


NOW = "2026-10-01T02:00:00Z"
PROOF = {"source_id": "synthetic-unadjusted-daily", "as_of": "2026-09-30", "retrieved_at": NOW}


def instrument(asset_type="STOCK", symbol="ACME", **overrides):
    value = {"key": "US:USD:" + symbol, "symbol": symbol, "asset_type": asset_type,
             "market": "US", "currency": "USD", "exchange_timezone": "America/New_York",
             "underlying": "ACME" if asset_type == "OPTION" else None,
             "expiry": "2026-10-16" if asset_type == "OPTION" else None,
             "strike": "100" if asset_type == "OPTION" else None,
             "right": "CALL" if asset_type == "OPTION" else None,
             "multiplier": "100" if asset_type == "OPTION" else None,
             "adjustment_status": "STANDARD"}
    value.update(overrides)
    return value


def record(record_id="fill-1", asset_type="STOCK", symbol="ACME", **overrides):
    value = {"record_id": record_id, "activity_type": "FILL", "instrument": instrument(asset_type, symbol),
             "side": "BUY", "quantity": "10", "price": "100", "fees": "1.20", "position_effect": None,
             "occurred_at": "2026-09-01T15:10:00Z", "time_precision": "SECOND",
             "source_id": "synthetic-broker-export", "as_of": "2026-09-01T15:10:00Z", "retrieved_at": NOW}
    value.update(overrides)
    return value


def candle(day="2026-09-01"):
    return {"date": day, "open": "99", "high": "104", "low": "98", "close": "103", "volume": "2000",
            "source_id": "synthetic-unadjusted-daily", "as_of": day + "T20:00:00Z", "retrieved_at": NOW,
            "available_at": day + "T20:00:00Z"}


def market(**overrides):
    value = {"instrument_key": "US:USD:ACME", "symbol": "ACME", "market": "US", "currency": "USD",
             "exchange_timezone": "America/New_York", "price_basis": "UNADJUSTED", "price_basis_evidence": PROOF,
             "candles": [candle()], "events": [], "gaps": [], "adjustment_factors": [], "session_calendar": None,
             "source_id": "synthetic-unadjusted-daily", "as_of": "2026-09-01", "retrieved_at": NOW}
    value.update(overrides)
    return value


def snapshot(records=None, markets=None):
    return {"kind": "TradeJournalSnapshot", "schema_version": "1.0.0", "snapshot_id": "synthetic-snapshot",
            "account_ref": "private-account-reference", "source_id": "synthetic-journal", "as_of": NOW,
            "retrieved_at": NOW, "input_hash": "synthetic-hash", "records": records if records is not None else [record()],
            "market": markets if markets is not None else [market()],
            "coverage": {"status": "PARTIAL", "account_start": None, "gaps": [{"reason": "NO_OPTIONS_RECONCILIATION"}]},
            "analysis": {"status": "NOT_CALCULABLE"}}


def chart_lesson_event(identifier, day, record_refs, *, anchor_role="AVAILABLE_AT", **overrides):
    event = {"evidence_id": identifier, "title": "合成事件 " + identifier,
             "content": "冻结合成内容，不证明真实研究质量", "anchor_role": anchor_role,
             "anchor_at": day + "T14:00:00Z", "publication_precision": "SECOND",
             "record_refs": list(record_refs), "dates_by_record": {reference: day for reference in record_refs},
             "layers": [{"record_id": reference, "layer": "OUTCOME", "reason": "合成逐笔信息层"} for reference in record_refs],
             "source_id": "synthetic-lesson-event:" + identifier, "as_of": day + "T14:00:00Z", "retrieved_at": NOW}
    event.update(overrides)
    return event


class MarketTests(unittest.TestCase):
    def test_transport_receives_only_public_symbol_and_dates_and_bounded_segments(self):
        calls = []
        def send(query):
            calls.append(query)
            return market(candles=[candle(query["start"])])
        result = fetch_market({**instrument(), "account_ref": "NEVER_SEND", "price": "PRIVATE"}, "2024-01-01", "2026-09-30", transport=send, now=NOW)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(set(query) == {"symbol", "start", "end"} for query in calls))
        self.assertTrue(all((datetime.fromisoformat(q["end"]) - datetime.fromisoformat(q["start"])).days <= 365 for q in calls))
        self.assertNotIn("NEVER_SEND", json.dumps(result))
        self.assertEqual(result["price_basis"], "UNADJUSTED")
        self.assertEqual(len(result["segments"]), 4)
        self.assertTrue(result["content_hash"])

    def test_market_failures_preserve_other_segments_and_no_synthetic_candles(self):
        calls = []
        def send(query):
            calls.append(query)
            if len(calls) == 2:
                raise RuntimeError("private arbitrary upstream message must not leak")
            return market(candles=[candle(query["start"])])
        result = fetch_market(instrument(), "2024-01-01", "2026-09-30", transport=send, now=NOW, context_sessions=0)
        self.assertEqual(len(result["candles"]), 2)
        self.assertEqual([row["status"] for row in result["segments"]], ["FETCHED", "FAILED", "FETCHED"])
        self.assertNotIn("private arbitrary", json.dumps(result))
        self.assertTrue(any(gap["reason"] == "MARKET_SEGMENT_FAILED" for gap in result["gaps"]))

    def test_request_budget_stops_without_unbounded_retries(self):
        calls = []
        result = fetch_market(instrument(), "2020-01-01", "2026-09-30", transport=lambda q: calls.append(q) or market(candles=[]), now=NOW, request_budget=2, context_sessions=0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(gap["reason"] == "MARKET_REQUEST_BUDGET_EXHAUSTED" for gap in result["gaps"]))
        self.assertEqual(result["candles"], [])

    def test_yahoo_ohlcv_basis_does_not_claim_unadjusted_and_preserves_actions(self):
        stamp = int(datetime(2026, 9, 1, 13, 30, tzinfo=UTC).timestamp())
        raw = {"provider_result": {"meta": {"exchangeTimezoneName": "America/New_York", "currency": "USD"},
               "timestamp": [stamp], "indicators": {"quote": [{"open": [99], "high": [104], "low": [98], "close": [103], "volume": [2000]}]},
               "events": {"splits": {"1": {"date": stamp, "numerator": 2, "denominator": 1}}}}, "raw_content_hash": "frozen-raw"}
        result = fetch_market(instrument(), "2026-09-01", "2026-09-01", transport=lambda _: raw, now=NOW, context_sessions=0)
        self.assertEqual(result["price_basis"], "PROVIDER_UNVERIFIED")
        self.assertIsNone(result["candles"][0]["available_at"])
        self.assertEqual(result["events"][0]["event_type"], "SPLIT")
        self.assertEqual(result["segments"][0]["raw_content_hash"], "frozen-raw")
        self.assertTrue(any(g["reason"] == "PRICE_BASIS_UNVERIFIED" for g in result["gaps"]))

    def test_unproved_adjustment_claim_downgrades(self):
        result = fetch_market(instrument(), "2026-09-01", "2026-09-01", transport=lambda _: market(price_basis_evidence=None), now=NOW, context_sessions=0)
        self.assertEqual(result["price_basis"], "PROVIDER_UNVERIFIED")

    def test_wrong_currency_or_invalid_ohlc_rejected_as_gap(self):
        for fixture in (market(currency="HKD"), market(symbol="OTHER"), market(exchange_timezone="Asia/Hong_Kong"), market(candles=[{**candle(), "high": "90"}])):
            result = fetch_market(instrument(), "2026-09-01", "2026-09-01", transport=lambda _: fixture, now=NOW, context_sessions=0)
            self.assertEqual(result["candles"], [])
            self.assertEqual(result["segments"][0]["status"], "FAILED")

    def test_invalid_factor_rejects_whole_segment_without_partial_merge(self):
        result = fetch_market(instrument(), "2026-09-01", "2026-09-01", transport=lambda _: market(adjustment_factors=[{"date": "2026-09-01", "factor": "NaN"}]), now=NOW, context_sessions=0)
        self.assertEqual(result["candles"], [])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["segments"][0]["status"], "FAILED")

    def test_known_session_missing_bar_is_gap_not_synthesized(self):
        calendar = {"source_id": "synthetic-calendar", "sessions": [{"date": "2026-09-01"}, {"date": "2026-09-02"}]}
        result = fetch_market(instrument(), "2026-09-01", "2026-09-02", transport=lambda _: market(session_calendar=calendar), now=NOW, context_sessions=0)
        self.assertEqual(len(result["candles"]), 1)
        self.assertTrue(any(gap.get("date") == "2026-09-02" and gap["reason"] == "KNOWN_SESSION_BAR_MISSING" for gap in result["gaps"]))

    def test_unsupported_symbol_has_no_transport_call(self):
        calls = []
        with self.assertRaises(JournalError):
            fetch_market(instrument(symbol="ACME/../private"), "2026-09-01", "2026-09-01", transport=lambda q: calls.append(q))
        self.assertEqual(calls, [])

    def test_default_transport_only_fixed_anonymous_get_with_redirect_block(self):
        requests = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return json.dumps({"chart": {"result": [{"meta": {}}]}}).encode()
        class Opener:
            def open(self, request, timeout):
                requests.append((request, timeout))
                return Response()
        with patch("product.trading_journal.market.build_opener", return_value=Opener()):
            yahoo_get({"symbol": "ACME", "start": "2026-09-01", "end": "2026-09-30"})
        request, timeout = requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.startswith("https://query1.finance.yahoo.com/v8/finance/chart/ACME?"))
        self.assertNotIn("Cookie", request.headers)
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(timeout, 20)
        with self.assertRaises(JournalError):
            yahoo_get({"symbol": "ACME", "start": "2026-09-01", "end": "2026-09-30", "account_ref": "private"})


class ChartTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成的图表脚本")
    def test_template_words_in_source_labels_do_not_expand_render_placeholders(self):
        fixture = snapshot([record(symbol="__DATA__")], [market(symbol="__DATA__", instrument_key="US:USD:__DATA__")])
        observed = _execute_chart_script(fixture, 'const outcome={symbol:DATA.groups[0].symbol,rows:$("rows").children.length};')
        self.assertEqual(observed["symbol"], "__DATA__")
        self.assertEqual(observed["rows"], 1)

    def test_stock_actual_price_and_option_independent_annotation_preserve_all_fills(self):
        fills = [record(), record("fill-2", side="SELL", price="102"), record("option-1", "OPTION", "ACME261016C00100000", price="2", quantity="1")]
        result = chart_payload(snapshot(fills))
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual([r["marker_price"] for r in result["records"]], [100, 102, None])
        self.assertEqual(result["records"][2]["price"], "2")
        self.assertEqual(result["records"][2]["instrument"]["multiplier"], "100")
        self.assertEqual([r["record_id"] for r in result["records"]], ["fill-1", "fill-2", "option-1"])

    def test_no_market_or_unknown_basis_retains_only_time_annotations(self):
        for fixture in (snapshot(markets=[]), snapshot(markets=[market(price_basis="PROVIDER_UNVERIFIED")]), snapshot(markets=[market(price_basis_evidence=None)])):
            result = chart_payload(fixture)
            self.assertEqual(len(result["records"]), 1)
            self.assertIsNone(result["records"][0]["marker_price"])
            self.assertEqual(result["records"][0]["price"], "100")

    def test_adjustment_factors_change_display_only_never_broker_original(self):
        fixture = market(price_basis="ADJUSTED_WITH_FACTORS", adjustment_factors=[{"date": "2026-09-01", "factor": ".5"}], events=[{"date": "2026-09-02", "event_type": "SPLIT", "numerator": "2", "denominator": "1"}])
        row = chart_payload(snapshot(markets=[fixture]))["records"][0]
        self.assertEqual(row["marker_price"], 50)
        self.assertEqual(row["price"], "100")
        fixture["adjustment_factors"] = []
        self.assertIsNone(chart_payload(snapshot(markets=[fixture]))["records"][0]["marker_price"])

    def test_dst_and_after_hours_use_verified_session_not_assumed_us_hours(self):
        sessions = {"source_id": "synthetic-calendar", "sessions": [
            {"date": "2026-03-06", "open": "2026-03-06T14:30:00Z", "close": "2026-03-06T21:00:00Z"},
            {"date": "2026-03-09", "open": "2026-03-09T13:30:00Z", "close": "2026-03-09T20:00:00Z"}]}
        records = [record("winter", occurred_at="2026-03-06T14:35:00Z"), record("summer", occurred_at="2026-03-09T13:35:00Z"), record("late", occurred_at="2026-03-09T21:00:00Z"), record("date", occurred_at="2026-03-09", time_precision="DATE", source_timezone="America/New_York")]
        result = chart_payload(snapshot(records, [market(session_calendar=sessions)]))["records"]
        self.assertTrue(result[0]["local_time"].endswith("-05:00"))
        self.assertTrue(result[1]["local_time"].endswith("-04:00"))
        self.assertIn("09:35", result[0]["local_time"])
        self.assertIn("09:35", result[1]["local_time"])
        self.assertEqual(result[2]["session_hint"], "AFTER_HOURS")
        self.assertEqual(result[3]["session_hint"], "DATE_ONLY")
        self.assertIsNone(result[3]["local_time"])

    def test_order_and_lifecycle_never_get_fill_price_markers(self):
        values = [record("order", activity_type="ORDER"), record("assignment", "OPTION", "ACME261016C00100000", activity_type="ASSIGNMENT")]
        result = chart_payload(snapshot(values))
        self.assertTrue(all(r["marker_price"] is None for r in result["records"]))
        self.assertEqual(len(result["records"]), 2)

    def test_html_escapes_external_text_and_does_not_embed_account_raw_or_remote_resources(self):
        raw = record(symbol="</script><script>alert('x')</script>", account_ref="secret-account", raw={"account": "12345678"}, source_path="/private/export.csv")
        source = snapshot([raw], [])
        source["snapshot_id"] = "<img src=https://evil.test/x>"
        rendered = render_chart(source)
        self.assertNotIn("</script><script>alert", rendered)
        self.assertNotIn("secret-account", rendered)
        self.assertNotIn("private-account-reference", rendered)
        self.assertNotIn("12345678", rendered)
        self.assertNotIn("/private/export.csv", rendered)
        self.assertNotIn('<img src=https://evil', rendered)
        self.assertIn("\\u003c/script\\u003e", rendered)
        self.assertIn("connect-src 'none'", rendered)
        self.assertFalse(re.search(r'<(?:script|link|img)[^>]+(?:src|href)=["\']https?://', rendered))
        data = re.search(r'<script id="journal-data" type="application/json">(.*?)</script>', rendered, re.S)
        self.assertEqual(json.loads(data[1])["records"][0]["instrument"]["symbol"], raw["instrument"]["symbol"])
        self.assertEqual(source["records"][0], raw)

    def test_long_history_all_records_embedded_and_filter_controls_exist(self):
        records = [record(f"fill-{i}") for i in range(1200)]
        rendered = render_chart(snapshot(records))
        data = json.loads(re.search(r'<script id="journal-data" type="application/json">(.*?)</script>', rendered, re.S)[1])
        self.assertEqual(len(data["records"]), 1200)
        self.assertEqual(len({r["record_id"] for r in data["records"]}), 1200)
        for field in ("symbol", "contract", "asset", "start", "end", "events"):
            self.assertIn('id="' + field + '"', rendered)

    def test_market_nested_extra_fields_and_analysis_raw_private_data_not_embedded(self):
        source = snapshot(markets=[market(candles=[{**candle(), "raw_row": "PRIVATE_RAW_CANDLE"}],
                                          price_basis_evidence={**PROOF, "account_ref": "PRIVATE_PROOF"},
                                          session_calendar={"source_id": "calendar", "account_ref": "PRIVATE_CALENDAR", "sessions": []})])
        source["analysis"] = {"raw": "PRIVATE_ANALYSIS", "by_currency": [{"currency": "USD", "closed_quantity": "10", "gross_pnl": "25", "fees": "2", "net_pnl": "23", "available_episodes": 1, "unavailable_episodes": 2, "aggregation_scope": "AVAILABLE_EPISODES_ONLY"}], "limitations": ["期初仓位未验证"]}
        rendered = render_chart(source)
        for value in ("PRIVATE_RAW_CANDLE", "PRIVATE_PROOF", "PRIVATE_CALENDAR", "PRIVATE_ANALYSIS"):
            self.assertNotIn(value, rendered)
        data = chart_payload(source)
        self.assertEqual(data["analysis"]["by_currency"][0]["net_pnl"], "23")
        self.assertEqual(data["analysis"]["by_currency"][0]["unavailable_episodes"], 2)

    def test_window_statistics_have_explicit_scope_and_do_not_follow_display_filters(self):
        source = snapshot()
        source["coverage"]["requested_window"] = {"start": "2026-09-01T00:00:00Z", "end": NOW, "timezone": "Asia/Shanghai"}
        data = chart_payload(source)
        self.assertEqual(data["statistics_scope"]["mode"], "SNAPSHOT_WINDOW")
        self.assertEqual(data["statistics_scope"]["window"], source["coverage"]["requested_window"])
        self.assertFalse(data["statistics_scope"]["follows_display_filters"])
        source["coverage"].pop("requested_window")
        source["analysis"]["scope"] = {"window": {"start": "2026-09-01", "end": "2026-09-30"}}
        self.assertEqual(chart_payload(source)["statistics_scope"]["mode"], "SNAPSHOT_WINDOW")
        source["analysis"].pop("scope")
        self.assertEqual(chart_payload(source)["statistics_scope"]["mode"], "ALL_AVAILABLE")

    def test_date_only_different_or_unknown_source_zone_is_not_exchange_date_or_price_marker(self):
        for source_zone in ("Asia/Shanghai", None):
            raw = record(occurred_at="2026-01-02", time_precision="DATE", source_timezone=source_zone)
            row = chart_payload(snapshot([raw]))["records"][0]
            self.assertEqual(row["display_date"], "2026-01-02")
            self.assertEqual(row["date_basis"], "SOURCE_DATE")
            self.assertEqual(row["exchange_date_status"], "UNDETERMINED")
            self.assertEqual(row["session_hint"], "SOURCE_DATE_UNCERTAIN")
            self.assertIsNone(row["marker_price"])
            self.assertIsNone(row["local_time"])
        known = record(occurred_at="2026-01-02", time_precision="DATE", source_timezone="America/New_York")
        row = chart_payload(snapshot([known]))["records"][0]
        self.assertEqual(row["display_date"], "2026-01-02")
        self.assertEqual(row["date_basis"], "EXCHANGE_DATE")
        self.assertEqual(row["marker_price"], 100)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_initial_selection_and_bst_are_independent_of_detail_pages(self):
        fixture = snapshot([record(f"daily-{index}", side="BUY" if index % 2 else "SELL") for index in range(450)])
        observed = _execute_chart_script(fixture, r'''const outcome={initialSymbol:$("symbol").value,initialHidden:$("chart-workspace").hidden,initialRows:$("rows").children.length,initialMarkers:$("chart").children.length,tableOpen:!!$("trade-table").open};
$("symbol").value=DATA.groups[0].id;$("symbol").listeners.change();
const marked=()=>$("chart").children.filter(row=>row.attributes["data-bst"]).map(row=>({date:row.attributes["data-date"],letter:row.textContent,ids:JSON.parse(row.attributes["data-records"])}));outcome.first=marked();
$("next-page").listeners.click();outcome.next=marked();outcome.pageRows=$("rows").children.length;
$("chart").children.find(row=>row.attributes["data-bst"]).listeners.click();outcome.day=selectedDate;outcome.pinned=pinnedDate;outcome.dayTableOpen=!!$("trade-table").open;outcome.panelTotal=$("candle-page-status").textContent;
$("page-number").value="3";$("page-number").listeners.change();outcome.lastRows=$("rows").children.map(row=>row.dataset.record);outcome.lastMarkers=marked();''', select=False)
        self.assertEqual((observed["initialSymbol"], observed["initialRows"], observed["initialMarkers"]), ("", 0, 0))
        self.assertTrue(observed["initialHidden"])
        self.assertFalse(observed["tableOpen"])
        self.assertFalse(observed["dayTableOpen"])
        self.assertEqual(len(observed["first"]), 1)
        self.assertEqual(observed["first"][0]["letter"], "T")
        self.assertEqual(len(observed["first"][0]["ids"]), 450)
        self.assertEqual(observed["next"], observed["first"])
        self.assertEqual(observed["lastMarkers"], observed["first"])
        self.assertEqual(observed["day"], "2026-09-01")
        self.assertEqual(observed["pinned"], observed["day"])
        self.assertIn("全部 450 条", observed["panelTotal"])
        self.assertEqual(observed["lastRows"], [f"daily-{index}" for index in range(400, 450)])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_same_day_stock_etf_contracts_only_one_badge_and_filter_actual_directions(self):
        fills = [record("buy-stock"), record("sell-etf", "ETF", side="SELL"),
                 record("buy-call", "OPTION", "ACME-CALL", price="2"),
                 record("sell-put", "OPTION", "ACME-PUT", side="SELL", price="1.5",
                        instrument=instrument("OPTION", "ACME-PUT", right="PUT", strike="95"))]
        fixture = snapshot(fills)
        before = json.dumps(fixture, sort_keys=True)
        observed = _execute_chart_script(fixture, r'''
const inspect=()=>$("chart").children.filter(row=>row.attributes["data-bst"]).map(row=>({letter:row.textContent,refs:JSON.parse(row.attributes["data-records"]),x:Number(row.attributes.x)}));
const outcome={all:inspect(),candleCenter:Number($("chart").children.find(row=>row.attributes["data-candle-date"]).attributes.x)+Number($("chart").children.find(row=>row.attributes["data-candle-date"]).attributes.width)/2};
for(const asset of["STOCK","ETF","OPTION"]){$("asset").value=asset;$("asset").listeners.change();outcome[asset]=inspect()}
$("contract").value=DATA.records.find(row=>row.record_id==="sell-put").instrument.key;$("contract").listeners.change();outcome.put=inspect();jrPinCandle("2026-09-01");outcome.detail=$("candle-rows").textContent;
outcome.legacy=$("chart").children.filter(row=>row.tagName==="polygon"||row.attributes["data-cluster"]||row.attributes["data-marker-leader"]||row.attributes["data-event"]||row.attributes["data-event-count"]).length;''')
        self.assertEqual([row["letter"] for row in observed["all"]], ["T"])
        self.assertEqual(observed["all"][0]["refs"], [row["record_id"] for row in fills])
        self.assertEqual(observed["all"][0]["x"], observed["candleCenter"])
        for key, letter in (("STOCK", "B"), ("ETF", "S"), ("OPTION", "T"), ("put", "S")):
            self.assertEqual([row["letter"] for row in observed[key]], [letter], key)
        self.assertIn("权利金 1.5 USD", observed["detail"])
        self.assertIn("2026-10-16 95 看跌 ×100", observed["detail"])
        self.assertEqual(observed["legacy"], 0)
        self.assertEqual(json.dumps(fixture, sort_keys=True), before)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_adjacent_date_letters_keep_exact_candle_centers_and_refs_after_focus(self):
        days = ["2026-09-01", "2026-09-02", "2026-09-03"]
        fills = [record(f"neighbor-{day}-{side}", occurred_at=day+"T15:10:00Z", side=side)
                 for day in days for side in ("BUY", "SELL")]
        observed = _execute_chart_script(snapshot(fills, [market(candles=[candle(day) for day in days])]), r'''
function inspect(){return $("chart").children.filter(row=>row.attributes["data-bst"]).map(row=>{const body=$("chart").children.find(c=>c.attributes["data-candle-date"]===row.attributes["data-date"]);return {date:row.attributes["data-date"],x:Number(row.attributes.x),center:Number(body.attributes.x)+Number(body.attributes.width)/2,refs:JSON.parse(row.attributes["data-records"]),letter:row.textContent,clip:row.attributes["clip-path"],focus:row.attributes["data-focus"]}})}
const outcome={before:inspect()};chartFocusIds=new Set(DATA.records.map(row=>row.record_id));render();outcome.after=inspect();''')
        self.assertEqual(len(observed["before"]), 3)
        for stage in ("before", "after"):
            self.assertEqual([row["date"] for row in observed[stage]], days)
            for row in observed[stage]:
                self.assertAlmostEqual(row["x"], row["center"])
                self.assertEqual(row["clip"], "url(#journal-plot)")
                self.assertEqual(row["letter"], "T")
                self.assertEqual(row["refs"], [f"neighbor-{row['date']}-{side}" for side in ("BUY", "SELL")])
        self.assertTrue(all(row["focus"] == "true" for row in observed["after"]))

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_unknown_direction_does_not_invent_only_buy_or_sell_but_known_both_proves_t(self):
        days = ["2026-09-01", "2026-09-02", "2026-09-03"]
        fills = [record("unknown", side="UNKNOWN"), record("buy-unknown"),
                 record("sell-known", occurred_at=days[1]+"T15:10:00Z", side="SELL"),
                 record("unknown-both", occurred_at=days[2]+"T15:10:00Z", side="UNKNOWN"),
                 record("buy-both", occurred_at=days[2]+"T15:10:00Z"),
                 record("sell-both", occurred_at=days[2]+"T15:10:00Z", side="SELL")]
        observed = _execute_chart_script(snapshot(fills, [market(candles=[candle(day) for day in days])]), r'''
const outcome={badges:$("chart").children.filter(row=>row.attributes["data-bst"]).map(row=>[row.attributes["data-date"],row.textContent])};jrPinCandle("2026-09-01");outcome.unknown={rows:$("candle-rows").children.map(row=>row.dataset.record),notice:$("candle-local").textContent};''')
        self.assertEqual(observed["badges"], [[days[1], "S"], [days[2], "T"]])
        self.assertEqual(observed["unknown"]["rows"], ["unknown", "buy-unknown"])
        self.assertIn("未知买卖方向", observed["unknown"]["notice"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_lifecycle_and_orders_keep_original_facts_in_day_panel_without_buy_sell_badges(self):
        actions = [record(f"operation-{kind}", "OPTION", "ACME-CALL", activity_type=kind, price="2")
                   for kind in ("ORDER", "EXERCISE", "ASSIGNMENT", "EXPIRY")]
        observed = _execute_chart_script(snapshot(actions), r'''
const outcome={badges:$("chart").children.filter(row=>row.attributes["data-bst"]).length};jrPinCandle("2026-09-01");outcome.rows=$("candle-rows").children.map(row=>row.dataset.record);outcome.text=$("candle-rows").textContent;outcome.status=$("candle-page-status").textContent;''')
        self.assertEqual(observed["badges"], 0)
        self.assertEqual(observed["rows"], [row["record_id"] for row in actions])
        self.assertIn("0 笔成交 · 4 条其他操作", observed["status"])
        for label in ("委托", "行权", "指派", "到期", "权利金 2 USD", "乘数 100"):
            self.assertIn(label, observed["text"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_unverified_prices_do_not_block_reliable_candle_date_or_change_ohlc_axis(self):
        fixture = snapshot([record("huge-stock", price="999999"), record("huge-option", "OPTION", "ACME-CALL", price="9999999")], [market(price_basis="PROVIDER_UNVERIFIED", price_basis_evidence=None)])
        observed = _execute_chart_script(fixture, r'''
const outcome={ticks:$("chart").children.filter(row=>row.tagName==="text"&&row.attributes["data-price-tick"]==="true").map(row=>Number(row.textContent)),badges:$("chart").children.filter(row=>row.attributes["data-bst"]).map(row=>row.textContent)};jrPinCandle("2026-09-01");outcome.rows=$("candle-rows").textContent;outcome.limit=$("candle-local").textContent;outcome.raw=DATA.records.map(row=>row.price);''')
        self.assertEqual(observed["badges"], ["B"])
        self.assertGreater(min(observed["ticks"]), 90)
        self.assertLess(max(observed["ticks"]), 110)
        self.assertIn("权利金 9999999 USD", observed["rows"])
        self.assertIn("券商原价 999999 USD", observed["rows"])
        self.assertIn("不作跨口径价位比较", observed["limit"])
        self.assertEqual(observed["raw"], ["999999", "9999999"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_missing_holiday_and_uncertain_date_never_snap_to_neighboring_candle(self):
        facts = [record("good"), record("holiday", occurred_at="2026-09-02T15:10:00Z"),
                 record("source-only", occurred_at="2026-09-01", time_precision="DATE", source_timezone="Asia/Shanghai")]
        observed = _execute_chart_script(snapshot(facts, [market(candles=[candle("2026-08-31"), candle()])]), r'''
const outcome={markers:$("chart").children.filter(row=>row.attributes["data-bst"]).map(row=>({date:row.attributes["data-date"],refs:JSON.parse(row.attributes["data-records"])})),all:DATA.records.map(row=>row.record_id),notice:$("gaps").textContent};jrPinCandle("2026-09-01");outcome.day=$("candle-rows").children.map(row=>row.dataset.record);outcome.missing=jrPinCandle("2026-09-02");showDate("2026-09-02","holiday");outcome.missingDetail=$("detail").dataset.record;showDate("2026-09-01","source-only");outcome.uncertainDetail=$("detail").textContent;''')
        self.assertEqual(observed["markers"], [{"date": "2026-09-01", "refs": ["good"]}])
        self.assertEqual(observed["day"], ["good"])
        self.assertFalse(observed["missing"])
        self.assertEqual(observed["missingDetail"], "holiday")
        self.assertIn("交易所日期未确定", observed["uncertainDetail"])
        self.assertIn("不移到邻日", observed["notice"])
        self.assertEqual(len(observed["all"]), 3)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_same_date_events_in_panel_preserve_each_role_source_and_callback_object(self):
        events = [chart_lesson_event("evidence-shared", "2026-09-01", ["fill-1"], anchor_role=role,
                                     title="合成正式公告", source_url="https://example.test/notice", relevance_note="合成关联")
                  for role in ("AVAILABLE_AT", "EVENT_AT", "AVAILABLE_AT")]
        scenario = "chartLessonEvents=" + json.dumps(events) + r''';const callbacks=[];function jrShowEvent(event){callbacks.push(chartLessonEvents.indexOf(event))}render();jrPinCandle("2026-09-01");
const outcome={icons:$("chart").children.filter(row=>row.attributes["data-event-count"]||row.attributes["data-lesson-event"]||row.attributes["data-event"]).length,count:$("candle-event-count").textContent,text:$("candle-events").textContent,urls:$("candle-events").children.flatMap(row=>row.children.filter(child=>child.tagName==="a").map(child=>child.attributes.href))};for(const entry of $("candle-events").children)entry.children.find(child=>child.tagName==="button").listeners.click();outcome.callbacks=callbacks;'''
        observed = _execute_chart_script(snapshot(), scenario)
        self.assertEqual(observed["icons"], 0)
        self.assertEqual(observed["count"], "当天事件 3 项")
        self.assertEqual(observed["callbacks"], [0, 1, 2])
        self.assertEqual(observed["urls"], ["https://example.test/notice"] * 3)
        for label in ("资料可用时刻", "事件发生时刻", "事后结果", "精确到秒", "资料截至", "保存时间", "来源"):
            self.assertIn(label, observed["text"])
        for technical in ("evidence-shared", "synthetic-lesson-event", "fill-1", "AVAILABLE_AT", "EVENT_AT", "OUTCOME"):
            self.assertNotIn(technical, observed["text"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_legacy_event_mapping_and_no_candle_events_are_not_dropped_or_drawn(self):
        events = [chart_lesson_event("evidence-good", "2026-09-01", ["fill-1"]),
                  chart_lesson_event("evidence-unplaced", "2026-09-01", ["fill-1"], anchor_role="UNPLACED"),
                  chart_lesson_event("evidence-other", "2026-09-01", ["beta"], group_id='["US","USD","BETA"]'),
                  chart_lesson_event("evidence-no-k", "2026-09-02", ["fill-1"]),
                  chart_lesson_event("evidence-outside", "2026-09-30", ["fill-1"]),
                  chart_lesson_event("evidence-null-map", "2026-09-01", ["fill-1"], dates_by_record={"fill-1": None})]
        legacy = chart_lesson_event("evidence-legacy", "2026-09-01", ["fill-1"], date="2026-09-01")
        del legacy["dates_by_record"]
        events.append(legacy)
        fixture = snapshot([record(), record("beta", symbol="BETA")])
        scenario = "chartLessonEvents=" + json.dumps(events) + r''';$("end").value="2026-09-02";render();const outcome={allEvents:chartLessonEvents.length,days:[...candleDayEvents].map(([day,rows])=>[day,rows.map(row=>chartLessonEvents.indexOf(row))])};jrPinCandle("2026-09-01");outcome.panelCount=$("candle-event-count").textContent;outcome.noCandle=jrPinCandle("2026-09-02");outcome.icons=$("chart").children.filter(row=>row.attributes["data-event-date"]).length;'''
        observed = _execute_chart_script(fixture, scenario)
        self.assertEqual(observed["allEvents"], 7)
        self.assertEqual(observed["days"], [["2026-09-01", [0, 6]], ["2026-09-02", [3]]])
        self.assertEqual(observed["panelCount"], "当天事件 2 项")
        self.assertFalse(observed["noCandle"])
        self.assertEqual(observed["icons"], 0)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行完整图表JS离线DOM检查")
    def test_candle_window_keeps_bounded_nearby_context_across_years(self):
        days = ["2024-09-01", "2025-12-31", "2026-01-05", "2026-05-31", "2026-06-04", "2026-08-31", "2026-09-01", "2026-09-03"]
        observed = _execute_chart_script(snapshot(markets=[market(candles=[candle(day) for day in days])]), r'''const candleDays=()=>$("chart").children.filter(row=>row.tagName==="rect"&&row.children.some(child=>child.tagName==="title")).map(row=>row.textContent.slice(0,10));const outcome={};
$("start").value="2026-09-01";$("end").value="2026-09-02";$("start").listeners.change();outcome.window=candleDays();outcome.gaps=$("gaps").textContent;outcome.retained=DATA.groups[0].market.candles.length;
$("start").value="2026-01-01";$("end").value="2026-01-05";$("start").listeners.change();outcome.january=candleDays();
$("start").value="2026-09-02";$("end").value="2026-09-01";$("start").listeners.change();outcome.reversed=candleDays();outcome.reversedNotice=$("gaps").textContent;''')
        self.assertEqual(observed["window"], ["2026-06-04", "2026-08-31", "2026-09-01"])
        self.assertIn("近邻背景", observed["gaps"])
        self.assertIn("不属于成交筛选范围", observed["gaps"])
        self.assertEqual(observed["retained"], len(days))
        self.assertEqual(observed["january"], ["2025-12-31", "2026-01-05"])
        self.assertEqual(observed["reversed"], [])
        self.assertIn("起日晚于止日", observed["reversedNotice"])
        missing = _execute_chart_script(snapshot([record(occurred_at="2026-09-02T15:10:00Z")], [market(candles=[candle("2026-08-31")])]), r'''$("start").value="2026-09-02";$("end").value="2026-09-02";$("start").listeners.change();const outcome={bars:Number($("bars").textContent),gaps:$("gaps").textContent};''')
        self.assertEqual(missing["bars"], 1)
        self.assertIn("已选图窗内没有可核验的日 K", missing["gaps"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行完整图表JS离线DOM检查")
    def test_full_history_switches_symbols_assets_contracts_dates_and_years(self):
        records, markets = [], []
        for group in range(40):
            symbol = f"S{group:02d}"
            markets.append(market(symbol=symbol, instrument_key=f"US:USD:{symbol}",
                                  candles=[candle("2025-09-01"), candle("2026-09-01"), candle("2026-09-02")]))
            for index in range(24 + (group < 7)):
                asset = ("STOCK", "ETF", "OPTION")[index % 3]
                item = instrument(asset, symbol if asset != "OPTION" else symbol + "-CALL",
                                  underlying=symbol if asset == "OPTION" else None)
                records.append(record(f"switch-{group}-{index}", instrument=item,
                                      occurred_at=("2025-09-01" if index == 0 else
                                                   "2026-09-01" if index % 2 else "2026-09-02") + "T15:10:00Z"))
        scenario = r'''const outcome={retained:DATA.records.length,groups:DATA.groups.length,errors:[]};
function check(){const expected=DATA.records.filter(r=>r.group_id===$("symbol").value&&($("asset").value==="ALL"||r.instrument.asset_type===$("asset").value)&&($("contract").value==="ALL"||r.instrument.key===$("contract").value)&&(!$("start").value||r.display_date>=$("start").value)&&(!$("end").value||r.display_date<=$("end").value));const current=expected.filter(r=>!$("segment").value||r.display_date.slice(0,4)===$("segment").value);const actual=$("rows").children.map(r=>r.dataset.record);if(Number($("count").textContent)!==expected.length||JSON.stringify(actual)!==JSON.stringify(current.map(r=>r.record_id)))outcome.errors.push("filter");if(!$("chart").children.some(r=>r.tagName==="rect"))outcome.errors.push("candles");}
for(const group of DATA.groups){$("symbol").value=group.id;$("symbol").listeners.change();check();for(const asset of["STOCK","ETF","OPTION"]){$("asset").value=asset;$("asset").listeners.change();check()}$("asset").value="ALL";$("asset").listeners.change();for(const contract of $("contract").children.slice(1)){$("contract").value=contract.value;$("contract").listeners.change();check()}$("reset").listeners.click();$("start").value="2026-09-02";$("end").value="2026-09-02";$("start").listeners.change();check();$("reset").listeners.click();$("segment").value="2026";$("segment").listeners.change();check();$("start").value="2026-09-03";$("end").value="2026-09-01";$("end").listeners.change();if($("rows").children.some(r=>r.dataset.record)||Number($("count").textContent))outcome.errors.push("reversed");$("reset").listeners.click();check()}
outcome.retainedAfter=DATA.records.length;'''
        observed = _execute_chart_script(snapshot(records, markets), scenario)
        self.assertEqual(observed["retained"], 967)
        self.assertEqual(observed["retainedAfter"], 967)
        self.assertEqual(observed["groups"], 40)
        self.assertEqual(observed["errors"], [])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行完整图表JS离线DOM检查")
    def test_optional_year_and_symbol_switch_match_entire_selected_range(self):
        records = [record("acme-2024", occurred_at="2024-09-01T15:10:00Z"),
                   record("acme-2026", occurred_at="2026-09-01T15:10:00Z"),
                   record("beta-2025", symbol="BETA", occurred_at="2025-09-01T15:10:00Z")]
        markets = [market(candles=[candle("2024-09-01"), candle("2026-09-01")]),
                   market(symbol="BETA", instrument_key="US:USD:BETA", candles=[candle("2025-09-01")])]
        scenario = r'''const outcome={};
const probe=new Element("select");probe.value="2026";outcome.empty_select=probe.value;
option(probe,"","空值选项");option(probe,"2026","2026 年");outcome.first_empty_stays=probe.value;
probe.value=2026;outcome.numeric_matching=probe.value;probe.value="missing";outcome.missing_option=probe.value;
probe.replaceChildren();option(probe,"2025","2025 年");outcome.first_after_replace=probe.value;
probe.replaceChildren();outcome.empty_after_replace=probe.value;
const input=new Element("input");input.value="任意输入";outcome.input_value=input.value;
function view(){return {years:$("segment").children.map(el=>el.value),year:$("segment").value,
rows:$("rows").children.filter(el=>el.dataset.record).map(el=>el.dataset.record),
markers:$("chart").children.filter(el=>el.attributes["data-record"]).map(el=>el.attributes["data-record"]),
candles:$("chart").children.filter(el=>el.tagName==="rect"&&el.children.some(child=>child.tagName==="title")).map(el=>el.textContent.slice(0,10)),
bars:Number($("bars").textContent),count:Number($("count").textContent)}}
outcome.initial=view();$("segment").value="2026";$("segment").listeners.change();outcome.new_year=view();
$("segment").value="2039";outcome.unavailable_year=$("segment").value;
$("segment").listeners.change();outcome.recovered=view();
$("segment").value="2026";$("segment").listeners.change();
$("symbol").value=DATA.groups.find(group=>group.symbol==="BETA").id;$("symbol").listeners.change();outcome.beta=view();
$("rows").children[0].listeners.click();outcome.beta_detail_id=$("detail").dataset.record;outcome.beta_detail=$("detail").textContent;
$("symbol").value=DATA.groups.find(group=>group.symbol==="ACME").id;$("symbol").listeners.change();outcome.returned=view();'''
        observed = _execute_chart_script(snapshot(records, markets), scenario)
        for key in ("empty_select", "first_empty_stays", "missing_option", "empty_after_replace", "unavailable_year"):
            self.assertEqual(observed[key], "", key)
        self.assertEqual(observed["numeric_matching"], "2026")
        self.assertEqual(observed["first_after_replace"], "2025")
        self.assertEqual(observed["input_value"], "任意输入")
        acme_all = {"years": ["", "2024", "2026"], "year": "", "rows": ["acme-2024", "acme-2026"],
                    "markers": ["acme-2024", "acme-2026"], "candles": ["2024-09-01", "2026-09-01"], "bars": 2, "count": 2}
        self.assertEqual(observed["initial"], acme_all)
        self.assertEqual(observed["recovered"], acme_all)
        self.assertEqual(observed["returned"], acme_all)
        self.assertEqual(observed["new_year"], {"years": ["", "2024", "2026"], "year": "2026", "rows": ["acme-2026"],
                                                "markers": ["acme-2026"], "candles": ["2026-09-01"], "bars": 1, "count": 1})
        self.assertEqual(observed["beta"], {"years": ["", "2025"], "year": "", "rows": ["beta-2025"],
                                           "markers": ["beta-2025"], "candles": ["2025-09-01"], "bars": 1, "count": 1})
        self.assertEqual(observed["beta_detail_id"], "beta-2025")
        self.assertIn("2025-09-01", observed["beta_detail"])
        self.assertIn("BETA", observed["beta_detail"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行完整图表JS离线DOM检查")
    def test_two_hundred_thousand_records_execute_bounded_pages_without_dropping_records(self):
        # 执行真正生成的JS，通用DOM替身只提供浏览器元素操作，不另写筛选/分页逻辑。
        fixture = snapshot([record(f"bulk-{i}") for i in range(200_000)])
        with tempfile.TemporaryDirectory(prefix="journal-chart-large-") as temp:
            page = Path(temp) / "chart.html"
            page.write_text(render_chart(fixture))
            runner = Path(temp) / "run.cjs"
            runner.write_text(_DOM_RUNNER.replace("__SCENARIO__", _PAGING_SCENARIO))
            result = subprocess.run([shutil.which("node"), str(runner), str(page)], capture_output=True, text=True, timeout=60, check=True)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["retained"], 200_000)
        self.assertEqual(observed["matched"], "200000")
        self.assertEqual(observed["initial_rows"], 200)
        self.assertEqual(observed["initial_single_markers"], 0)
        self.assertEqual(observed["initial_clusters"], 0)
        self.assertEqual(observed["initial_badges"], 1)
        self.assertEqual(observed["initial_represented_records"], 200_000)
        self.assertEqual(observed["first_initial_id"], "bulk-0")
        self.assertEqual(observed["next_page_first_id"], "bulk-200")
        self.assertEqual(observed["last_page_first_id"], "bulk-199800")
        self.assertEqual(observed["last_page_last_id"], "bulk-199999")
        self.assertEqual(observed["last_page_rows"], 200)
        self.assertTrue(observed["next_disabled"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实图表JS")
    def test_explicit_missing_market_day_detail_keeps_all_rows_and_readable_prices(self):
        fixture = snapshot([record(f"missing-{i}", quantity=str(i + 1)) for i in range(450)], [])
        observed = _execute_chart_script(fixture, r'''showDate("2026-09-01","missing-5");const outcome={badges:$("chart").children.filter(row=>row.attributes["data-bst"]).length,detail:$("detail").textContent,chosen:$("detail").dataset.record,count:$("cluster-summary").textContent};$("page-number").value="3";$("page-number").listeners.change();outcome.last=$("rows").children.map(row=>row.dataset.record);outcome.facts=DATA.records.length;''')
        self.assertEqual(observed["badges"], 0)
        self.assertEqual(observed["chosen"], "missing-5")
        self.assertIn("数量 6", observed["detail"])
        self.assertIn("450 条", observed["count"])
        self.assertEqual(observed["last"], [f"missing-{i}" for i in range(400, 450)])
        self.assertEqual(observed["facts"], 450)


def _execute_chart_script(fixture, scenario, *, select=True):
    if select:
        scenario = '$("symbol").value=DATA.groups[0].id;$("symbol").listeners.change();\n' + scenario
    with tempfile.TemporaryDirectory(prefix="journal-chart-interaction-") as temp:
        page = Path(temp) / "chart.html"
        page.write_text(render_chart(fixture))
        runner = Path(temp) / "run.cjs"
        runner.write_text(_DOM_RUNNER.replace("__SCENARIO__", scenario.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")))
        result = subprocess.run([shutil.which("node"), str(runner), str(page)], capture_output=True, text=True, timeout=60, check=True)
    return json.loads(result.stdout)


_DOM_RUNNER = r'''
const fs=require("node:fs"),html=fs.readFileSync(process.argv[2],"utf8"),ids={};
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.dataset=new Proxy({},{set(object,key,value){object[key]=String(value);return true}});this.attributes={};this.listeners={};this._value="";this._selectedOption=null;this._text="";this.classList={toggle(){}};this.disabled=false;this.checked=false;}
 set value(value){value=String(value);if(this.tagName==="select")this._selectedOption=this.children.find(child=>child.tagName==="option"&&child.value===value)||null;else this._value=value;}
 get value(){return this.tagName==="select"?(this.children.includes(this._selectedOption)?this._selectedOption.value:""):this._value;}
 set textContent(value){this.replaceChildren();this._text=String(value);}
 get textContent(){return this._text+this.children.map(x=>x.textContent).join("");}
 appendChild(child){this.children.push(child);if(this.tagName==="select"&&!this.children.includes(this._selectedOption))this._selectedOption=this.children.find(option=>option.tagName==="option")||null;return child;}
 replaceChildren(){this.children=[];this._text="";this._selectedOption=null;}
 setAttribute(key,value){this.attributes[key]=String(value);}
 addEventListener(kind,fn){this.listeners[kind]=fn;}
}
for(const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"([^>]*)>/g)){ids[match[2]]=new Element(match[1]);ids[match[2]].checked=/\bchecked\b/.test(match[3]);const value=match[3].match(/\bvalue="([^"]*)"/);if(value)ids[match[2]].value=value[1];}
for(const match of html.matchAll(/<select[^>]*\bid="([^"]+)"[^>]*>(.*?)<\/select>/gs)){for(const option of match[2].matchAll(/<option[^>]*value="([^"]*)"[^>]*>(.*?)<\/option>/gs)){const el=new Element("option");el.value=option[1];el.textContent=option[2];ids[match[1]].appendChild(el);}}
ids["journal-data"].textContent=html.match(/<script id="journal-data" type="application\/json">(.*?)<\/script>/s)[1];
const document={getElementById(id){if(!ids[id])throw Error("missing "+id);return ids[id]},createElement(tag){return new Element(tag)},createElementNS(ns,tag){return new Element(tag)},querySelectorAll(){return []}};
const window={listeners:{},addEventListener(kind,fn){this.listeners[kind]=fn}};
const script=html.match(/<script>(.*?)<\/script>/s)[1];
eval(script+`
__SCENARIO__
console.log(JSON.stringify(outcome));`);
'''


_PAGING_SCENARIO = r'''
document.getElementById("symbol").value=DATA.groups[0].id;document.getElementById("symbol").listeners.change();
const outcome={retained:DATA.records.length,matched:document.getElementById("paging-status").dataset.matchCount,initial_rows:document.getElementById("rows").children.length,initial_single_markers:document.getElementById("chart").children.filter(x=>x.tagName==="polygon").length,initial_badges:document.getElementById("chart").children.filter(x=>x.attributes["data-bst"]).length,initial_clusters:document.getElementById("chart").children.filter(x=>x.attributes["data-cluster"]==="true").length,initial_represented_records:document.getElementById("chart").children.reduce((total,x)=>total+(x.attributes["data-record-count"]?Number(x.attributes["data-record-count"]):x.attributes["data-record"]?1:0),0),first_initial_id:document.getElementById("rows").children[0].dataset.record};
document.getElementById("next-page").listeners.click();outcome.next_page_first_id=document.getElementById("rows").children[0].dataset.record;
document.getElementById("page-number").value="1000";document.getElementById("page-number").listeners.change();outcome.last_page_first_id=document.getElementById("rows").children[0].dataset.record;outcome.last_page_last_id=document.getElementById("rows").children.at(-1).dataset.record;outcome.last_page_rows=document.getElementById("rows").children.length;outcome.next_disabled=document.getElementById("next-page").disabled;
'''

if __name__ == "__main__":
    unittest.main()
