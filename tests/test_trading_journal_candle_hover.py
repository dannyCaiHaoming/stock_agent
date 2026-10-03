"""执行实际图表脚本，检验完全虚构蜡烛与图内面板的日期/阅读状态。"""
from datetime import date, timedelta
import json
import shutil
import unittest

from product.trading_journal.charts import render_chart
from tests.test_trading_journal_charts import (
    _execute_chart_script, candle, chart_lesson_event, instrument, market, record, snapshot,
)


def timeline():
    days = [(date(2026, 9, 1) + timedelta(days=index)).isoformat() for index in range(20)]
    fixture = snapshot([record("record-first", occurred_at=days[0]+"T15:10:00Z"),
                        record("record-last", occurred_at=days[-1]+"T15:10:00Z", side="SELL")],
                       [market(candles=[candle(day) for day in days])])
    return fixture, days


@unittest.skipUnless(shutil.which("node"), "需要Node执行真实生成的图表脚本")
class CandleHoverTests(unittest.TestCase):
    def test_hover_preview_leave_pin_and_other_day_preview_keep_distinct_selections(self):
        fixture, days = timeline()
        result = _execute_chart_script(fixture, r'''
const body=day=>$("chart").children.find(row=>row.attributes["data-candle-date"]===day);
const state=()=>({hover:hoverDate,pin:pinnedDate,selected:selectedDate,date:$("candle-panel").dataset.date,hidden:$("candle-panel").hidden,text:$("candle-state").textContent});
const outcome={initial:state()};body("2026-09-01").listeners.pointerenter();outcome.preview=state();$("chart-wrap").listeners.pointerleave();outcome.left=state();body("2026-09-01").listeners.click();outcome.pin=state();body("2026-09-20").listeners.pointerenter();outcome.other=state();$("chart-wrap").listeners.pointerleave();outcome.returned=state();outcome.tableOpen=!!$("trade-table").open;
''')
        self.assertTrue(result["initial"]["hidden"])
        self.assertEqual(result["preview"]["hover"], days[0])
        self.assertEqual(result["preview"]["selected"], "")
        self.assertEqual(result["preview"]["pin"], "")
        self.assertTrue(result["left"]["hidden"])
        self.assertEqual(result["pin"]["selected"], days[0])
        self.assertEqual(result["pin"]["pin"], days[0])
        self.assertEqual(result["other"]["date"], days[-1])
        self.assertEqual(result["other"]["selected"], days[0])
        self.assertEqual(result["returned"]["date"], days[0])
        self.assertIn("已固定", result["returned"]["text"])
        self.assertFalse(result["tableOpen"])

    def test_leaving_actual_candle_for_empty_plot_clears_ephemeral_preview(self):
        result = _execute_chart_script(snapshot(), r'''
const body=$("chart").children.find(row=>row.attributes["data-candle-date"]);body.listeners.pointerenter();const outcome={visible:!$("candle-panel").hidden};body.listeners.pointerleave({relatedTarget:$("chart")});outcome.after={hover:hoverDate,hidden:$("candle-panel").hidden};jrPinCandle("2026-09-01");body.listeners.pointerenter();body.listeners.pointerleave({relatedTarget:$("chart")});outcome.fixed={hover:hoverDate,pin:pinnedDate,hidden:$("candle-panel").hidden};''')
        self.assertTrue(result["visible"])
        self.assertEqual(result["after"], {"hover": "", "hidden": True})
        self.assertEqual(result["fixed"], {"hover": "", "pin": "2026-09-01", "hidden": False})

    def test_fixed_page_and_selected_record_survive_other_day_preview_zoom_and_table_page(self):
        fixture, days = timeline()
        fixture["records"][:0] = [record(f"record-fixed-{index}", quantity=str(index+1)) for index in range(45)]
        result = _execute_chart_script(fixture, r'''
jrPinCandle("2026-09-01");$("candle-next").listeners.click();$("candle-rows").children[3].children[0].listeners.click();$("candle-event-details").open=true;
const state=()=>({date:$("candle-panel").dataset.date,page:candlePageIndex,chosen:candleSelectedRecord,text:$("candle-selected").textContent,refs:$("candle-rows").children.map(row=>row.dataset.record),selected:selectedDate,open:$("candle-event-details").open});
const outcome={before:state()};jrPreviewCandle("2026-09-20");outcome.preview=state();$("chart-wrap").listeners.pointerleave();outcome.returned=state();jrZoomViewport(.6,0);outcome.zoom=state();$("next-page").listeners.click();outcome.tablePage=state();
''')
        self.assertEqual(result["before"]["page"], 1)
        self.assertEqual(result["before"]["chosen"], "record-fixed-23")
        self.assertEqual(result["preview"]["page"], 0)
        self.assertEqual(result["preview"]["chosen"], "")
        self.assertEqual(result["preview"]["selected"], days[0])
        for stage in ("returned", "zoom", "tablePage"):
            self.assertEqual(result[stage], result["before"], stage)

    def test_panel_pagination_exposes_every_same_day_fact_without_changing_viewport_or_long_table(self):
        fixture = snapshot([record(f"record-dense-{index}", quantity=str(index+1), side="BUY" if index % 2 else "SELL") for index in range(450)])
        result = _execute_chart_script(fixture, r'''
const before={...chartViewport};jrPinCandle("2026-09-01");const refs=[],statuses=[];do{refs.push(...$("candle-rows").children.map(row=>row.dataset.record));statuses.push($("candle-page-status").textContent);if($("candle-next").disabled)break;$("candle-next").listeners.click()}while(statuses.length<30);
const outcome={refs,statuses,lastCount:$("candle-rows").children.length,page:candlePageIndex,previous:$("candle-previous").disabled,next:$("candle-next").disabled,viewport:{...chartViewport},before,longPage:pageIndex,tableOpen:!!$("trade-table").open,records:DATA.records.length};
''')
        self.assertEqual(result["refs"], [f"record-dense-{index}" for index in range(450)])
        self.assertEqual(len(result["statuses"]), 23)
        self.assertTrue(all("全部 450 条" in line for line in result["statuses"]))
        self.assertEqual(result["lastCount"], 10)
        self.assertEqual(result["page"], 22)
        self.assertTrue(result["next"])
        self.assertFalse(result["previous"])
        self.assertEqual(result["viewport"], result["before"])
        self.assertEqual(result["longPage"], 0)
        self.assertFalse(result["tableOpen"])
        self.assertEqual(result["records"], 450)

    def test_programmatic_record_focus_locates_its_panel_page_and_preserves_full_contract(self):
        fixture = snapshot([record(f"record-call-{index}", "OPTION", "ACME-CALL", quantity=str(index+1), price="2.3") for index in range(45)])
        result = _execute_chart_script(fixture, r'''
const outcome={pinned:jrPinCandle("2026-09-01","record-call-42"),page:candlePageIndex,record:candleSelectedRecord,refs:$("candle-rows").children.map(row=>row.dataset.record),text:$("candle-selected").textContent,limit:$("candle-local").textContent};
''')
        self.assertTrue(result["pinned"])
        self.assertEqual(result["page"], 2)
        self.assertEqual(result["record"], "record-call-42")
        self.assertIn("record-call-42", result["refs"])
        for text in ("2026-10-16 100 看涨 ×100", "数量 43", "权利金 2.3 USD", "费用 1.20", "精确到秒"):
            self.assertIn(text, result["text"])
        self.assertIn("权利金不是标的股价", result["limit"])

    def test_keyboard_focus_preview_enter_space_pin_escape_close_without_opening_long_table(self):
        result = _execute_chart_script(snapshot(), r'''
const body=$("chart").children.find(row=>row.attributes["data-candle-date"]);const outcome={};body.listeners.focus();outcome.focus={hover:hoverDate,pin:pinnedDate,selected:selectedDate};let prevents=0;body.listeners.keydown({key:"Enter",preventDefault(){prevents++}});outcome.enter={hover:hoverDate,pin:pinnedDate,selected:selectedDate};body.listeners.keydown({key:"Escape",preventDefault(){prevents++}});outcome.closed={hover:hoverDate,pin:pinnedDate,selected:selectedDate,hidden:$("candle-panel").hidden};$("chart").children.find(row=>row.attributes["data-candle-date"]).listeners.keydown({key:" ",preventDefault(){prevents++}});outcome.space={pin:pinnedDate,tableOpen:!!$("trade-table").open};$("candle-panel").listeners.keydown({key:"Escape",preventDefault(){prevents++}});outcome.finalHidden=$("candle-panel").hidden;outcome.prevents=prevents;
''')
        self.assertEqual(result["focus"], {"hover": "2026-09-01", "pin": "", "selected": ""})
        self.assertEqual(result["enter"], {"hover": "", "pin": "2026-09-01", "selected": "2026-09-01"})
        self.assertEqual(result["closed"], {"hover": "", "pin": "", "selected": "", "hidden": True})
        self.assertEqual(result["space"], {"pin": "2026-09-01", "tableOpen": False})
        self.assertTrue(result["finalHidden"])
        self.assertEqual(result["prevents"], 4)

    def test_no_fill_candle_preview_has_ohlcv_and_clearly_no_saved_fills(self):
        fixture, _ = timeline()
        result = _execute_chart_script(fixture, r'''
jrPreviewCandle("2026-09-10");const outcome={text:$("candle-ohlcv").textContent,notice:$("candle-local").textContent,rows:$("candle-rows").children.length,selected:selectedDate};
''')
        self.assertIn("开 99 · 高 104 · 低 98 · 收 103 · 成交量 2000", result["text"])
        self.assertIn("当天无已保存成交", result["notice"])
        self.assertEqual(result["rows"], 0)
        self.assertEqual(result["selected"], "")

    def test_pinned_day_outside_viewport_hides_panel_return_restores_same_pin_and_record(self):
        fixture, days = timeline()
        result = _execute_chart_script(fixture, r'''
jrPinCandle("2026-09-01","record-first");const before=JSON.stringify(DATA);jrZoomViewport(.25,1);
const outcome={outside:{pin:pinnedDate,selected:selectedDate,hidden:$("candle-panel").hidden,returnHidden:$("candle-return").hidden,status:$("candle-return-status").textContent,span:chartViewport.end-chartViewport.start}};$("candle-return-button").listeners.click();outcome.back={pin:pinnedDate,selected:selectedDate,hidden:$("candle-panel").hidden,returnHidden:$("candle-return").hidden,record:candleSelectedRecord,date:$("candle-panel").dataset.date,span:chartViewport.end-chartViewport.start};outcome.unchanged=before===JSON.stringify(DATA);
''')
        self.assertEqual(result["outside"]["pin"], days[0])
        self.assertTrue(result["outside"]["hidden"])
        self.assertFalse(result["outside"]["returnHidden"])
        self.assertIn("暂在当前图窗之外", result["outside"]["status"])
        self.assertFalse(result["back"]["hidden"])
        self.assertTrue(result["back"]["returnHidden"])
        self.assertEqual(result["back"]["record"], "record-first")
        self.assertEqual(result["back"]["date"], days[0])
        self.assertEqual(result["back"]["span"], result["outside"]["span"])
        self.assertTrue(result["unchanged"])

    def test_drag_delays_capture_and_does_not_pin_then_next_deliberate_click_works(self):
        fixture, _ = timeline()
        result = _execute_chart_script(fixture, r'''
$("chart").getBoundingClientRect=()=>({left:0,width:1120});const captures=[];$("chart").setPointerCapture=id=>captures.push(id);jrZoomViewport(.5);jrPinCandle("2026-09-20");const oldPin=pinnedDate;
$("chart").listeners.pointerdown({clientX:600,pointerId:7,button:0});const outcome={beforeCapture:[...captures]};$("chart").listeners.pointermove({clientX:680,pointerId:7});$("chart").listeners.pointerup();outcome.after={captures:[...captures],pin:pinnedDate,suppressed:suppressChartClick};
$("chart").listeners.click();outcome.trailingClick={pin:pinnedDate,suppressed:suppressChartClick};const visible=$("chart").children.find(row=>row.attributes["data-candle-date"]);visible.listeners.click();outcome.deliberate={pin:pinnedDate,date:visible.attributes["data-candle-date"]};outcome.oldPin=oldPin;
''')
        self.assertEqual(result["beforeCapture"], [])
        self.assertEqual(result["after"]["captures"], [7])
        self.assertEqual(result["after"]["pin"], result["oldPin"])
        self.assertTrue(result["after"]["suppressed"])
        self.assertEqual(result["trailingClick"]["pin"], result["oldPin"])
        self.assertFalse(result["trailingClick"]["suppressed"])
        self.assertEqual(result["deliberate"]["pin"], result["deliberate"]["date"])

    def test_asset_contract_dates_and_symbol_filters_clear_invalid_panel_state(self):
        fixture, _ = timeline()
        fixture["records"].append(record("record-option", "OPTION", "ACME-CALL"))
        fixture["records"].append(record("record-beta", symbol="BETA"))
        fixture["market"].append(market(symbol="BETA", instrument_key="US:USD:BETA"))
        result = _execute_chart_script(fixture, r'''
const outcome={checks:[]};for(const filter of ["asset","contract","start","end","segment"]){jrPinCandle("2026-09-01");if(filter==="asset")$(filter).value="OPTION";if(filter==="contract")$(filter).value=DATA.records.find(row=>row.record_id==="record-option").instrument.key;if(filter==="start")$(filter).value="2026-09-02";if(filter==="end")$(filter).value="2026-09-19";if(filter==="segment")$(filter).value="2026";$(filter).listeners.change();outcome.checks.push({filter,pin:pinnedDate,hover:hoverDate,selected:selectedDate,hidden:$("candle-panel").hidden});$("reset").listeners.click()}
jrPinCandle("2026-09-01");$("symbol").value=DATA.groups.find(group=>group.symbol==="BETA").id;$("symbol").listeners.change();outcome.symbol={pin:pinnedDate,hidden:$("candle-panel").hidden};
''')
        for item in result["checks"]:
            self.assertEqual(item["pin"], "", item["filter"])
            self.assertEqual(item["hover"], "", item["filter"])
            self.assertEqual(item["selected"], "", item["filter"])
            self.assertTrue(item["hidden"], item["filter"])
        self.assertEqual(result["symbol"], {"pin": "", "hidden": True})

    def test_contract_options_match_option_only_viewer_boundary_and_reset_on_stock_filter(self):
        fixture = snapshot([record("record-stock"), record("record-etf", "ETF", "ACME"),
                            record("record-call", "OPTION", "ACME-CALL"),
                            record("record-put", "OPTION", "ACME-PUT", instrument=instrument("OPTION", "ACME-PUT", right="PUT"))])
        result = _execute_chart_script(fixture, r'''
const values=()=>$("contract").children.map(row=>row.value);const outcome={initial:values()};$("asset").value="OPTION";$("asset").listeners.change();$("contract").value=DATA.records.find(row=>row.record_id==="record-put").instrument.key;$("contract").listeners.change();outcome.option={values:values(),selected:$("contract").value,count:Number($("count").textContent)};$("asset").value="STOCK";$("asset").listeners.change();outcome.stock={values:values(),selected:$("contract").value,count:Number($("count").textContent)};$("asset").value="ETF";$("asset").listeners.change();outcome.etf={values:values(),selected:$("contract").value,count:Number($("count").textContent)};$("reset").listeners.click();outcome.reset=values();''')
        self.assertEqual(result["initial"], ["ALL", "US:USD:ACME-CALL", "US:USD:ACME-PUT"])
        self.assertEqual(result["option"]["selected"], "US:USD:ACME-PUT")
        self.assertEqual(result["option"]["count"], 1)
        for asset in ("stock", "etf"):
            self.assertEqual(result[asset], {"values": ["ALL"], "selected": "ALL", "count": 1})
        self.assertEqual(result["reset"], result["initial"])

    def test_uncertain_record_cannot_programmatically_pin_same_named_candle(self):
        fixture = snapshot([record("record-uncertain", occurred_at="2026-09-01", time_precision="DATE", source_timezone="Asia/Shanghai")])
        result = _execute_chart_script(fixture, r'''
const outcome={matched:jrPinCandle("2026-09-01","record-uncertain"),pin:pinnedDate,selected:selectedDate,hidden:$("candle-panel").hidden};showDate("2026-09-01","record-uncertain");outcome.detail=$("detail").textContent;
''')
        self.assertFalse(result["matched"])
        self.assertEqual(result["pin"], "")
        self.assertTrue(result["hidden"])
        self.assertIn("交易所日期未确定", result["detail"])

    def test_event_pit_source_and_company_action_are_readable_in_panel_with_safe_links(self):
        event = chart_lesson_event("evidence-source", "2026-09-01", ["fill-1"], title="央行合成公告",
                                   source_url="https://example.test/published", availability_basis="VERIFIED_PUBLICATION_TIME", vintage_status="ORIGINAL_RELEASE")
        action = {"date": "2026-09-01", "event_type": "SPLIT", "numerator": "2", "denominator": "1", "amount": None,
                  "source_id": "source-private-action", "as_of": "2026-09-01", "retrieved_at": "2026-10-01T00:00:00Z"}
        fixture = snapshot(markets=[market(events=[action])])
        scenario = "chartLessonEvents=" + json.dumps([event]) + r''';render();jrPinCandle("2026-09-01");const before=$("candle-events").textContent;
const outcome={count:$("candle-event-count").textContent,text:before,links:$("candle-events").children.flatMap(entry=>entry.children.filter(child=>child.tagName==="a").map(child=>child.attributes.href)),icons:$("chart").children.filter(row=>row.attributes["data-event"]||row.attributes["data-event-count"]).length};chartLessonEvents[0].source_url="https://name:secret@example.test/unsafe";render();outcome.unsafeLinks=$("candle-events").children.flatMap(entry=>entry.children.filter(child=>child.tagName==="a").map(child=>child.attributes.href));$("events").checked=false;$("events").listeners.change();outcome.hidden=$("candle-event-details").hidden;outcome.retained=chartLessonEvents.length;
'''
        result = _execute_chart_script(fixture, scenario)
        self.assertEqual(result["count"], "当天事件 2 项")
        self.assertEqual(result["links"], ["https://example.test/published"])
        self.assertEqual(result["unsafeLinks"], [])
        self.assertEqual(result["icons"], 0)
        for label in ("资料可用时刻", "事后结果", "来源", "拆股 2 : 1"):
            self.assertIn(label, result["text"])
        for hidden in ("evidence-source", "source-private-action", "OUTCOME", "AVAILABLE_AT", "fill-1", "ORIGINAL_RELEASE", "VERIFIED_PUBLICATION_TIME"):
            self.assertNotIn(hidden, result["text"])
        self.assertTrue(result["hidden"])
        self.assertEqual(result["retained"], 1)

    def test_wide_panel_avoids_current_candle_and_can_preview_opposite_side(self):
        fixture, _ = timeline()
        result = _execute_chart_script(fixture, r'''
$("chart").getBoundingClientRect=()=>({left:50,width:1320});render();jrPreviewCandle("2026-09-20");const outcome={right:jrCandlePanelPlacement("2026-09-20"),rightStyle:$("candle-panel").attributes.style};$("chart").children.find(row=>row.attributes["data-candle-date"]==="2026-09-20").listeners.click();outcome.pinned=pinnedDate;jrPreviewCandle("2026-09-01");outcome.left=jrCandlePanelPlacement("2026-09-01");outcome.leftStyle=$("candle-panel").attributes.style;outcome.preview=hoverDate;outcome.retainedPin=pinnedDate;''')
        self.assertEqual(result["right"]["side"], "left")
        self.assertFalse(result["right"]["overlap"])
        self.assertGreater(result["right"]["activeX"], result["right"]["right"] + 4)
        self.assertIn("left:8px;right:auto", result["rightStyle"])
        self.assertEqual(result["left"]["side"], "right")
        self.assertFalse(result["left"]["overlap"])
        self.assertLess(result["left"]["activeX"], result["left"]["left"] - 4)
        self.assertIn("left:auto;right:8px", result["leftStyle"])
        self.assertEqual(result["pinned"], "2026-09-20")
        self.assertEqual(result["preview"], "2026-09-01")
        self.assertEqual(result["retainedPin"], result["pinned"])

    def test_tiny_chart_has_equivalent_direct_pin_and_bounded_inside_panel(self):
        fixture, _ = timeline()
        result = _execute_chart_script(fixture, r'''
$("chart").getBoundingClientRect=()=>({left:10,width:300});render();jrPreviewCandle("2026-09-10");const outcome={placement:jrCandlePanelPlacement("2026-09-10"),preview:hoverDate,before:selectedDate,buttonDisabled:$("candle-pin").disabled};$("candle-pin").listeners.click();outcome.fixed={date:pinnedDate,selected:selectedDate,disabled:$("candle-pin").disabled,state:$("candle-state").textContent};''')
        self.assertTrue(result["placement"]["overlap"])
        self.assertGreaterEqual(result["placement"]["left"], 8)
        self.assertLessEqual(result["placement"]["right"], 292)
        self.assertEqual(result["before"], "")
        self.assertFalse(result["buttonDisabled"])
        self.assertEqual(result["fixed"]["date"], "2026-09-10")
        self.assertEqual(result["fixed"]["selected"], "2026-09-10")
        self.assertTrue(result["fixed"]["disabled"])
        self.assertIn("已固定", result["fixed"]["state"])

    def test_responsive_geometry_resize_keeps_viewport_pin_page_and_readable_screen_text(self):
        fixture, _ = timeline()
        fixture["records"][:0] = [record(f"record-responsive-{index}") for index in range(45)]
        result = _execute_chart_script(fixture, r'''
let width=1320;$("chart").getBoundingClientRect=()=>({left:10,width});window.listeners.resize();jrPinCandle("2026-09-01");$("candle-next").listeners.click();$("candle-rows").children[3].children[0].listeners.click();$("candle-event-details").open=true;jrZoomViewport(.7,0);
const view=()=>({viewport:{...chartViewport},pin:pinnedDate,date:$("candle-panel").dataset.date,page:candlePageIndex,record:candleSelectedRecord,open:$("candle-event-details").open});const outcome={before:view()};width=430;window.listeners.resize();outcome.after=view();outcome.geometry={...chartGeometry};outcome.viewBox=$("chart").attributes.viewBox;outcome.glyphs=$("chart").children.filter(row=>row.attributes["data-bst"]).map(row=>({font:Number(row.attributes["font-size"]),x:Number(row.attributes.x),day:row.attributes["data-date"]}));outcome.axis=$("chart").children.filter(row=>row.tagName==="text"&&row.attributes["data-price-tick"]==="true").map(row=>Number(row.attributes["font-size"]));outcome.dateTicks=$("chart").children.filter(row=>row.tagName==="text"&&/^2026-/.test(row.textContent)&&!row.attributes["data-bst"]).map(row=>({x:Number(row.attributes.x),font:Number(row.attributes["font-size"]),anchor:row.attributes["text-anchor"]}));const middle=chartGeometry.left+chartGeometry.plotWidth*.5;outcome.pointer=jrChartX({clientX:10+middle});outcome.middle=middle;''')
        self.assertEqual(result["before"], result["after"])
        self.assertEqual(result["after"]["page"], 1)
        self.assertEqual(result["after"]["record"], "record-responsive-23")
        self.assertEqual(result["viewBox"], "0 0 430 240")
        self.assertEqual(result["geometry"]["plotWidth"], 354)
        self.assertTrue(result["glyphs"])
        self.assertTrue(all(row["font"] >= 12 for row in result["glyphs"]))
        self.assertTrue(all(result["geometry"]["left"] <= row["x"] <= 412 for row in result["glyphs"]))
        self.assertTrue(all(font == 11 for font in result["axis"]))
        self.assertEqual(len(result["dateTicks"]), 3)
        self.assertEqual(result["dateTicks"][0]["anchor"], "start")
        self.assertEqual(result["dateTicks"][-1]["anchor"], "end")
        self.assertAlmostEqual(result["pointer"], result["middle"])

    def test_panel_lives_inside_chart_with_bounded_scroll_and_default_folded_data(self):
        # Layout assertion is limited to the generated containment/CSS contract;
        # actual narrow-screen pixels are checked separately by the parent in Chrome.
        html = render_chart(snapshot())
        start = html.index('<div id="chart-wrap"')
        end = html.index('<div id="candle-return"', start)
        self.assertIn('<section id="candle-panel"', html[start:end])
        self.assertIn('max-width:calc(100% - 16px)', html)
        self.assertIn('max-height:calc(100% - 16px);overflow:auto', html)
        self.assertIn('<details id="source-details">', html)
        self.assertNotIn('<details id="source-details" open', html)
        self.assertNotIn('独立时间注释栏', html)
        self.assertNotIn('data-marker-leader', html)


if __name__ == "__main__":
    unittest.main()
