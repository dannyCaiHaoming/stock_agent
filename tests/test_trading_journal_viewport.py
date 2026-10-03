"""Execute the shipped SVG reader against fictional frozen facts, without a browser or network."""
from datetime import date, timedelta
import json
import shutil
import unittest

from tests.test_trading_journal_charts import (
    _execute_chart_script, candle, chart_lesson_event, market, record, snapshot,
)


def viewport_fixture():
    days = [(date(2025, 12, 23) + timedelta(days=i)).isoformat() for i in range(20)]
    candles = [candle(day) for day in days]
    candles[0].update(open="999", high="1005", low="995", close="1001")
    records = [record("viewport-stock-0", occurred_at=days[0] + "T15:10:00Z", price="1000"),
               record("viewport-stock-10", occurred_at=days[10] + "T15:10:00Z"),
               record("viewport-stock-19", occurred_at=days[19] + "T15:10:00Z"),
               record("viewport-option", "OPTION", "ACME-CALL", occurred_at=days[10] + "T15:10:00Z", price="2")]
    split = {"date": days[10], "event_type": "SPLIT", "numerator": "2", "denominator": "1", "amount": None,
             "source_id": "source-split-hidden", "as_of": days[10], "retrieved_at": "2026-02-01T00:00:00Z"}
    return snapshot(records, [market(candles=candles, events=[split])]), days


_GEOMETRY = r'''
function viewportGeometry(){
 const children=$("chart").children,candles=children.filter(row=>row.attributes["data-candle-date"]),markers=children.filter(row=>row.attributes["data-record-count"]);
 return {viewport:{...chartViewport},bounds:{...chartViewportBounds},retained:DATA.records.length,rows:$("rows").children.map(row=>row.dataset.record),
  candles:candles.map(row=>({date:row.attributes["data-candle-date"],x:Number(row.attributes.x)+Number(row.attributes.width)/2,clip:row.attributes["clip-path"]})),
  markers:markers.map(row=>({date:row.attributes["data-date"],axis:row.attributes["data-marker-axis"],x:Number(row.attributes["data-anchor-x"]),clip:row.attributes["clip-path"],focused:row.attributes["data-focus"]})),
  events:children.filter(row=>row.attributes["data-event-date"]).map(row=>({date:row.attributes["data-event-date"],x:Number(row.attributes.x),clip:row.attributes["clip-path"]})),
  corporate:children.filter(row=>row.attributes["data-event"]).map(row=>({x:Number(row.attributes.x)-3,clip:row.attributes["clip-path"]})),
  focus:children.filter(row=>row.attributes["data-focus-window"]).map(row=>({x:Number(row.attributes.x),width:Number(row.attributes.width),clip:row.attributes["clip-path"]})),
  ticks:children.filter(row=>row.tagName==="text"&&row.attributes["data-price-tick"]==="true").map(row=>row.textContent),bars:Number($("bars").textContent),status:$("viewport-status").textContent};
}
'''


@unittest.skipUnless(shutil.which("node"), "需要 Node 执行真实生成的图表脚本")
class ViewportTests(unittest.TestCase):
    def test_default_dates_span_years_and_optional_year_can_restore_full_range(self):
        fixture, days = viewport_fixture()
        observed = _execute_chart_script(fixture, _GEOMETRY + r'''
const outcome={initial:viewportGeometry(),start:$("start").value,end:$("end").value,years:$("segment").children.map(row=>row.value),minimum:$("start").min,maximum:$("end").max};
$("segment").value="2026";$("segment").listeners.change();outcome.year=viewportGeometry();outcome.yearDates={start:$("start").value,end:$("end").value,count:Number($("count").textContent)};
$("segment").value="";$("segment").listeners.change();outcome.restored=viewportGeometry();
$("start").value="2026-01-02";$("end").value="2025-12-31";$("end").listeners.change();outcome.reversed={rows:$("rows").children.length,candles:viewportGeometry().candles.length,notice:$("gaps").textContent,status:$("viewport-status").textContent};''')
        self.assertEqual(observed["start"], days[0])
        self.assertEqual(observed["end"], days[-1])
        self.assertEqual(observed["years"], ["", "2025", "2026"])
        self.assertEqual(len(observed["initial"]["rows"]), 4)
        self.assertEqual(observed["initial"]["viewport"], observed["restored"]["viewport"])
        self.assertEqual(len(observed["year"]["rows"]), 3)
        self.assertEqual(observed["yearDates"], {"start": "2026-01-01", "end": days[-1], "count": 3})
        self.assertEqual(observed["reversed"]["rows"], 0)
        self.assertEqual(observed["reversed"]["candles"], 0)
        self.assertIn("起日晚于止日", observed["reversed"]["notice"])
        self.assertIn("图窗", observed["initial"]["status"])
        self.assertIn("报告依据", observed["initial"]["status"])

    def test_zoom_transforms_all_facts_and_rescales_price_without_dropping_records(self):
        fixture, days = viewport_fixture()
        event = chart_lesson_event("evidence-viewport", days[10], ["viewport-stock-10", "viewport-option"])
        scenario = "chartLessonEvents=" + json.dumps([event]) + ";\n" + _GEOMETRY + r'''
chartFocusWindow={start:"2025-12-31",end:"2026-01-04"};chartFocusIds=new Set(["viewport-stock-10"]);render();
const outcome={before:viewportGeometry()};jrZoomViewport(.4,.525);outcome.zoomed=viewportGeometry();
$("fit-window").listeners.click();outcome.reset=viewportGeometry();'''
        observed = _execute_chart_script(fixture, scenario)
        self.assertGreater(len(observed["before"]["candles"]), len(observed["zoomed"]["candles"]))
        self.assertEqual(observed["zoomed"]["retained"], 4)
        self.assertEqual(len(observed["zoomed"]["rows"]), 4)
        self.assertEqual(observed["reset"]["viewport"], observed["before"]["viewport"])
        self.assertGreater(max(map(float, observed["before"]["ticks"])), 1000)
        self.assertLess(max(map(float, observed["zoomed"]["ticks"])), 200)
        zoomed = observed["zoomed"]
        center = next(row["x"] for row in zoomed["candles"] if row["date"] == days[10])
        self.assertTrue(all(abs(row["x"] - center) < 1e-8 for row in zoomed["markers"]))
        self.assertEqual({row["axis"] for row in zoomed["markers"]}, {"CANDLE_DATE"})
        self.assertEqual(zoomed["events"], [])
        self.assertEqual(zoomed["corporate"], [])
        self.assertTrue(any(row["focused"] == "true" for row in zoomed["markers"]))
        for collection in ("candles", "markers", "focus"):
            self.assertTrue(zoomed[collection], collection)
            self.assertTrue(all(row["clip"] == "url(#journal-plot)" for row in zoomed[collection]), collection)
        focus = zoomed["focus"][0]
        self.assertGreaterEqual(focus["x"], 76)
        self.assertLessEqual(focus["x"] + focus["width"], 1084)

    def test_pointer_wheel_anchor_drag_edges_minimum_and_paging_state(self):
        fixture, days = viewport_fixture()
        # Add enough same-day fills to exercise a real page transition while zoomed.
        fixture["records"].extend(record(f"record-extra-{i}", occurred_at=days[10]+"T15:10:00Z") for i in range(230))
        observed = _execute_chart_script(fixture, _GEOMETRY + r'''
const outcome={initial:viewportGeometry()};$("chart").getBoundingClientRect=()=>({left:20,width:560});
const captures=[];$("chart").setPointerCapture=id=>captures.push(id);
const anchor=.525,pointer=20+(76+1008*anchor)/2;let prevented=false;
$("chart").listeners.wheel({clientX:pointer,deltaY:-400,deltaX:0,deltaMode:0,preventDefault(){prevented=true}});outcome.prevented=prevented;outcome.wheel=viewportGeometry();
showDate("2026-01-02","viewport-stock-10");outcome.beforePage={viewport:{...chartViewport},selectedDate,detail:$("detail").dataset.record};
$("next-page").listeners.click();outcome.afterPage={viewport:{...chartViewport},selectedDate,detail:$("detail").dataset.record,page:pageIndex};
const beforeDrag={...chartViewport};$("chart").listeners.pointerdown({clientX:300,pointerId:7,button:0});outcome.captureBeforeDrag=[...captures];$("chart").listeners.pointermove({clientX:350,pointerId:7});$("chart").listeners.pointerup();outcome.drag={before:beforeDrag,after:{...chartViewport},suppressed:suppressChartClick,selectedDate,detail:$("detail").dataset.record,captures};
for(let i=0;i<30;i++)$("zoom-in").listeners.click();outcome.minimum={span:chartViewport.end-chartViewport.start,disabled:$("zoom-in").disabled};
for(let i=0;i<100;i++)$("pan-left").listeners.click();outcome.left={viewport:{...chartViewport},bounds:{...chartViewportBounds},disabled:$("pan-left").disabled};
for(let i=0;i<100;i++)$("pan-right").listeners.click();outcome.right={viewport:{...chartViewport},bounds:{...chartViewportBounds},disabled:$("pan-right").disabled};
$("fit-window").listeners.click();outcome.reset=viewportGeometry();''')
        self.assertTrue(observed["prevented"])
        first, second = observed["initial"]["viewport"], observed["wheel"]["viewport"]
        self.assertLess(second["end"]-second["start"], first["end"]-first["start"])
        self.assertAlmostEqual(first["start"]+(first["end"]-first["start"])*.525,
                               second["start"]+(second["end"]-second["start"])*.525, places=3)
        self.assertEqual(observed["beforePage"]["viewport"], observed["afterPage"]["viewport"])
        self.assertEqual(observed["afterPage"]["page"], 1)
        self.assertEqual(observed["afterPage"]["selectedDate"], days[10])
        self.assertEqual(observed["afterPage"]["detail"], "viewport-stock-10")
        self.assertLess(observed["drag"]["after"]["start"], observed["drag"]["before"]["start"])
        # Capturing on pointerdown would retarget ordinary marker clicks to the SVG.
        self.assertEqual(observed["captureBeforeDrag"], [])
        self.assertEqual(observed["drag"]["captures"], [7])
        self.assertTrue(observed["drag"]["suppressed"])
        self.assertEqual(observed["drag"]["selectedDate"], days[10])
        self.assertEqual(observed["drag"]["detail"], "viewport-stock-10")
        self.assertEqual(observed["minimum"], {"span": 86400000, "disabled": True})
        self.assertEqual(observed["left"]["viewport"]["start"], observed["left"]["bounds"]["start"])
        self.assertTrue(observed["left"]["disabled"])
        self.assertEqual(observed["right"]["viewport"]["end"], observed["right"]["bounds"]["end"])
        self.assertTrue(observed["right"]["disabled"])
        self.assertEqual(len(observed["reset"]["markers"]), 3)
        self.assertEqual(observed["reset"]["retained"], 234)

    def test_unverified_market_keeps_reliable_date_badges_and_readable_every_surface(self):
        fixture, _ = viewport_fixture()
        fixture["market"][0]["price_basis"] = "PROVIDER_UNVERIFIED"
        fixture["market"][0]["gaps"] = [{"reason": "NO_RELIABLE_MARKET_DATA", "detail": "source-hidden 专用资料 /Users/someone/.private/secret.csv"}]
        fixture["input_hash"] = "hash-secret-hidden"
        fixture["analysis"] = {"by_currency": [{"currency": "USD", "available_episodes": 0, "unavailable_episodes": 4}],
                               "limitations": [{"code": "FEES_INCOMPLETE", "detail": "hash-secret-hidden /private/secret.json", "source_id": "source-hidden"}]}
        fixture["coverage"]["gaps"] = [{"reason": "FEES_INCOMPLETE", "detail": "record-unresolved /Users/someone/file.csv", "input_hash": "hash-secret-hidden"}]
        observed = _execute_chart_script(fixture, r'''
const texts=()=>["coverage","statistics","saved-scope","gaps","viewport-status","title","basis","rows","cluster-list","detail","chart","contract","segment","candle-rows","candle-events","candle-local"].map(id=>$(id).textContent).join(String.fromCharCode(10));
const before=texts(),details=[];for(const row of DATA.records){showDate(row.display_date,row.record_id);details.push(texts())}
jrPinCandle("2026-01-02");
const outcome={text:before+String.fromCharCode(10)+details.join(String.fromCharCode(10))+String.fromCharCode(10)+texts(),hidden:DATA.records.map(row=>row.record_id),markers:$("chart").children.filter(row=>row.attributes["data-record-count"]).map(row=>row.attributes["data-marker-axis"])};''')
        self.assertIn("费用不完整", observed["text"])
        self.assertIn("买入", observed["text"])
        self.assertIn("精确到秒", observed["text"])
        self.assertIn("拆股", observed["text"])
        for forbidden in ("viewport-stock", "viewport-option", "source-split-hidden", "synthetic-broker-export", "source-hidden", "hash-secret-hidden", "/Users/", "/private/", "PROVIDER_UNVERIFIED", "FEES_INCOMPLETE", "input_hash", "source_id", "as_of", "retrieved_at", "SECOND", "STANDARD", '"reason":'):
            self.assertNotIn(forbidden, observed["text"], forbidden)
        self.assertEqual(set(observed["markers"]), {"CANDLE_DATE"})
        self.assertEqual(len(observed["hidden"]), 4)

    def test_missing_market_retains_facts_without_candle_badges_and_with_financial_activity_labels(self):
        fixture, days = viewport_fixture()
        fixture["market"] = []
        fixture["records"].extend([
            record("record-cash", activity_type="CASH", occurred_at=days[10]+"T15:10:00Z"),
            record("record-tax", activity_type="TAX", occurred_at=days[10]+"T15:10:00Z"),
        ])
        observed = _execute_chart_script(fixture, r'''
const rows=$("rows").textContent,marks=$("chart").children.filter(row=>row.attributes["data-record-count"]),outcome={bars:Number($("bars").textContent),retained:DATA.records.length,represented:marks.reduce((n,row)=>n+Number(row.attributes["data-record-count"]),0),axes:marks.map(row=>row.attributes["data-marker-axis"]),fills:Number($("count").textContent),other:Number($("other").textContent),rows,gap:$("gaps").textContent};
$("zoom-in").listeners.click();$("pan-left").listeners.click();$("fit-window").listeners.click();outcome.after=DATA.records.length;''')
        self.assertEqual(observed["bars"], 0)
        self.assertEqual(observed["retained"], 6)
        self.assertEqual(observed["represented"], 0)
        self.assertEqual(observed["after"], 6)
        self.assertEqual(observed["axes"], [])
        self.assertEqual(observed["fills"], 4)
        self.assertEqual(observed["other"], 2)
        self.assertIn("没有可核验的历史行情", observed["gap"])
        self.assertIn("资金活动", observed["rows"])
        self.assertIn("税费", observed["rows"])
        self.assertNotIn("CASH", observed["rows"])
        self.assertNotIn("TAX", observed["rows"])


if __name__ == "__main__":
    unittest.main()
