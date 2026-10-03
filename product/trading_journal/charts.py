"""将冻结的脱敏成交与日线渲染成无远程依赖的 HTML/SVG。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError
from .presentation import build_reader_labels, reader_script


def _public_market(market: dict) -> dict:
    fields = ("instrument_key", "symbol", "market", "currency", "exchange_timezone", "price_basis", "source_id", "as_of", "retrieved_at", "requested_range", "session", "content_hash")
    result = {key: market.get(key) for key in fields}
    def select(item, names):
        return {key: item.get(key) for key in names if key in item}
    result["candles"] = [select(row, ("date", "open", "high", "low", "close", "volume", "source_id", "as_of", "retrieved_at", "available_at", "session")) for row in market.get("candles", [])]
    result["events"] = [select(row, ("date", "event_type", "numerator", "denominator", "amount", "source_id", "as_of", "retrieved_at")) for row in market.get("events", [])]
    result["gaps"] = [select(row, ("date", "start", "end", "reason", "detail", "requested", "available")) for row in market.get("gaps", [])]
    result["adjustment_factors"] = [select(row, ("date", "factor")) for row in market.get("adjustment_factors", [])]
    proof = market.get("price_basis_evidence")
    result["price_basis_evidence"] = select(proof, ("source_id", "as_of", "retrieved_at", "method")) if isinstance(proof, dict) else None
    calendar = market.get("session_calendar")
    if isinstance(calendar, dict):
        result["session_calendar"] = {"source_id": calendar.get("source_id"), "sessions": [select(row, ("date", "open", "close")) for row in calendar.get("sessions", [])]}
    elif isinstance(calendar, list):
        result["session_calendar"] = [select(row, ("date", "open", "close")) for row in calendar]
    else:
        result["session_calendar"] = None
    return result


def _analysis(analysis: dict | None) -> dict:
    analysis = analysis if isinstance(analysis, dict) else {}
    fields = ("currency", "closed_quantity", "gross_pnl", "fees", "net_pnl", "available_episodes", "unavailable_episodes", "aggregation_scope")
    return {"by_currency": [{key: row.get(key) for key in fields} for row in analysis.get("by_currency", [])],
            "limitations": analysis.get("limitations", [])}


def _without_private_keys(value):
    excluded = {"account_ref", "account_id", "account_number", "account_name", "account", "raw", "raw_row", "raw_content", "source_path", "credentials", "cookies", "token", "password", "client"}
    if isinstance(value, dict):
        return {key: _without_private_keys(item) for key, item in value.items() if key.lower() not in excluded}
    if isinstance(value, list):
        return [_without_private_keys(item) for item in value]
    return value


def _safe_number(value):
    try:
        number = Decimal(str(value))
        return float(number) if number.is_finite() and abs(number) < Decimal("1e16") else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _projection(record: dict, market: dict | None) -> dict:
    # 不嵌入原始行、账户号、源文件路径或非必要用户身份字段。
    allowed = ("record_id", "activity_type", "side", "quantity", "price", "fees", "position_effect",
               "occurred_at", "time_precision", "source_id", "as_of", "retrieved_at", "source_timezone")
    result = {key: record.get(key) for key in allowed}
    instrument = record.get("instrument") or {}
    fields = ("key", "symbol", "asset_type", "market", "currency", "exchange_timezone", "underlying", "expiry", "strike", "right", "multiplier", "adjustment_status")
    result["instrument"] = {key: instrument.get(key) for key in fields}
    result.update(display_date=None, local_time=None, session_hint="UNKNOWN", marker_price=None,
                  marker_basis="TIME_ONLY", date_basis="UNKNOWN", exchange_date_status="UNDETERMINED")
    raw_time = record.get("occurred_at")
    if isinstance(raw_time, str):
        if record.get("time_precision") == "DATE" or len(raw_time) == 10:
            result["display_date"] = raw_time[:10]
            source_zone, exchange_zone = record.get("source_timezone"), instrument.get("exchange_timezone")
            if source_zone and exchange_zone and source_zone == exchange_zone:
                result.update(session_hint="DATE_ONLY", date_basis="EXCHANGE_DATE", exchange_date_status="DATE_ONLY")
            else:
                result.update(session_hint="SOURCE_DATE_UNCERTAIN", date_basis="SOURCE_DATE",
                              marker_basis="SOURCE_DATE_TIME_ONLY")
        else:
            try:
                stamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                timezone = instrument.get("exchange_timezone") or (market or {}).get("exchange_timezone")
                if stamp.tzinfo is not None and timezone:
                    local = stamp.astimezone(ZoneInfo(timezone))
                    result["display_date"], result["local_time"] = local.date().isoformat(), local.isoformat()
                    result.update(date_basis="EXCHANGE_DATE", exchange_date_status="DETERMINED")
                    result["session_hint"] = "SESSION_UNVERIFIED"
                    calendar = (market or {}).get("session_calendar") or {}
                    sessions = calendar.get("sessions", []) if isinstance(calendar, dict) else calendar
                    session = next((row for row in sessions if row.get("date") == result["display_date"]), None)
                    if session and session.get("open") and session.get("close"):
                        opened, closed = (datetime.fromisoformat(session[key].replace("Z", "+00:00")) for key in ("open", "close"))
                        result["session_hint"] = "PRE_MARKET" if stamp < opened else "AFTER_HOURS" if stamp > closed else "REGULAR"
            except (ValueError, TypeError, ZoneInfoNotFoundError):
                pass
    if result["display_date"] is None and raw_time:
        result["display_date"] = str(raw_time)[:10]
        result["session_hint"] = "TIMEZONE_UNKNOWN"
        result["date_basis"] = "SOURCE_TIMESTAMP_DATE"
    if not market or instrument.get("asset_type") == "OPTION" or record.get("activity_type") != "FILL":
        return result
    if result["exchange_date_status"] == "UNDETERMINED":
        return result
    if instrument.get("currency") and market.get("currency") and instrument["currency"] != market["currency"]:
        result["marker_basis"] = "CURRENCY_MISMATCH"
        return result
    price = _safe_number(record.get("price"))
    basis = market.get("price_basis")
    proof = market.get("price_basis_evidence")
    reliable = isinstance(proof, dict) and all(proof.get(key) for key in ("source_id", "as_of", "retrieved_at"))
    if price is not None and price > 0 and reliable:
        if basis == "UNADJUSTED":
            result["marker_price"], result["marker_basis"] = price, "UNADJUSTED"
        elif basis == "ADJUSTED_WITH_FACTORS":
            factor = next((item.get("factor") for item in market.get("adjustment_factors", []) if item.get("date") == result["display_date"]), None)
            value = _safe_number(factor)
            if value is not None and value > 0:
                result["marker_price"] = float(Decimal(str(record["price"])) * Decimal(str(factor)))
                result["marker_basis"] = "ADJUSTED_WITH_FACTORS"
    return result


def chart_payload(snapshot: dict) -> dict:
    """制作可核验展示包；记录全部保留，图表只按可靠同日蜡烛关联。"""
    if not isinstance(snapshot, dict) or snapshot.get("kind") != "TradeJournalSnapshot":
        raise JournalError("CHART_SNAPSHOT_INVALID", "图表需要冻结 TradeJournalSnapshot")
    markets = snapshot.get("market") or []
    if isinstance(markets, dict):
        markets = list(markets.values())
    groups, records = {}, []
    for raw in snapshot.get("records", []):
        instrument = raw.get("instrument") or {}
        symbol = instrument.get("underlying") if instrument.get("asset_type") == "OPTION" else instrument.get("symbol")
        symbol = symbol or instrument.get("symbol") or "未知标的"
        group_id = json.dumps([instrument.get("market"), instrument.get("currency"), symbol], ensure_ascii=False, separators=(",", ":"))
        market = next((item for item in markets if item.get("instrument_key") == instrument.get("key")), None)
        if market is None:
            market = next((item for item in markets if item.get("symbol") == symbol and item.get("market") == instrument.get("market") and item.get("currency") == instrument.get("currency")), None)
        group = groups.setdefault(group_id, {"id": group_id, "symbol": symbol, "market_name": instrument.get("market"), "currency": instrument.get("currency"), "market": None})
        if market is not None and (group["market"] is None or len(market.get("candles", [])) > len(group["market"].get("candles", []))):
            # 行情层仅公开字段，切断意外夹带 account_ref/raw/source_path 的通道。
            group["market"] = _public_market(market)
        records.append({"group_id": group_id})
    # 期权先遇到、股票后遇到时统一选择标的包再投影，避免顺序影响。
    for index, raw in enumerate(snapshot.get("records", [])):
        group = groups[records[index]["group_id"]]
        projected = _projection(raw, group["market"])
        projected["group_id"] = group["id"]
        records[index] = projected
    coverage = snapshot.get("coverage") or {}
    analysis = snapshot.get("analysis") or {}
    window = coverage.get("requested_window") or (analysis.get("scope") or {}).get("window")
    return {"kind": "TradeJournalChart", "schema_version": "1.0.0", "snapshot_id": snapshot.get("snapshot_id"),
            "input_hash": snapshot.get("input_hash"), "source_id": snapshot.get("source_id"),
            "as_of": snapshot.get("as_of"), "retrieved_at": snapshot.get("retrieved_at"),
            "coverage": _without_private_keys(snapshot.get("coverage")), "analysis": _analysis(snapshot.get("analysis")),
            "statistics_scope": {"mode": "SNAPSHOT_WINDOW" if window else "ALL_AVAILABLE", "window": window,
                                 "cutoff": snapshot.get("as_of"), "follows_display_filters": False},
            "groups": list(groups.values()), "records": records}


def render_chart(snapshot: dict) -> str:
    return render_chart_payload(chart_payload(snapshot))


def render_chart_payload(payload: dict) -> str:
    """Render an already projected selection without reading private inputs."""
    if not isinstance(payload, dict) or payload.get("kind") != "TradeJournalChart":
        raise JournalError("CHART_PAYLOAD_INVALID", "图表需要已投影 TradeJournalChart")
    # script 中不得出现 </script>、HTML标签或Unicode行分隔字符。
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    labels = build_reader_labels(packet={"snapshot": payload})
    for group in payload.get("groups", []):
        market = group.get("market") or {}
        for field in ("source_id", "content_hash"):
            if market.get(field):
                labels[market[field]] = "已保存行情资料"
    replacements = {"__READER__": reader_script(labels), "__DATA__": encoded}
    return re.sub(r"__(?:READER|DATA)__", lambda match: replacements[match[0]], _HTML)


_HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'">
<title>个人交易账本 · 冻结图表</title>
<style>
:root{color-scheme:light;--ink:#163440;--muted:#617480;--buy:#087e77;--sell:#b33f50;--line:#d9e3e5;--paper:#f3f7f7}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1360px;margin:auto;padding:26px 28px 40px}h1{margin:0;font-size:27px}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--muted)}.lead{margin:6px 0 18px;color:var(--muted)}.card{background:white;border:1px solid var(--line);border-radius:14px;padding:18px;margin-top:16px}.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:end}label{display:grid;gap:5px;font-size:12px;color:var(--muted)}select,input,button{font:inherit;color:var(--ink);border:1px solid #c8d7db;background:white;border-radius:7px;padding:8px;max-width:250px}button{cursor:pointer;background:#eff5f4}.check{display:flex;align-items:center;gap:6px;padding-bottom:9px}.metrics{display:flex;gap:25px;flex-wrap:wrap;margin-top:16px}.metric strong{display:block;font-size:23px}.metric span,.legend,.foot,.toolbar-note{font-size:12px;color:var(--muted)}.legend{display:flex;flex-wrap:wrap;gap:16px}.buy{color:var(--buy)}.sell{color:var(--sell)}.chart-wrap{position:relative;overflow:hidden;margin-top:12px;border:1px solid #e1eaec;border-radius:8px}svg{display:block;width:100%;height:auto;min-height:240px;min-width:0;background:white;touch-action:none;cursor:grab}svg.dragging{cursor:grabbing}.viewport-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px}.viewport-controls button{padding:6px 10px}.viewport-status{flex-basis:100%;font-size:12px;color:var(--muted)}@media print{body{background:white}main{max-width:none;padding:0}.controls,.viewport-controls button,.toolbar-note{display:none}.chart-wrap,.scroll-table{overflow:visible}.card{break-inside:avoid}svg{min-width:0}.cluster-list{max-height:none;overflow:visible}}.figure-title{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;align-items:center}h2{font-size:19px;margin:0}.badge{font-size:11px;background:#ecf4f4;padding:4px 8px;border-radius:5px}.notice{font-size:12px;color:#765a27;background:#fff8e9;border:1px solid #eadbb7;padding:10px 12px;border-radius:7px;margin-top:12px;white-space:pre-line}.detail{border-left:3px solid #369188;background:#f0f8f7;margin-top:12px;padding:10px 14px;font-size:13px;white-space:pre-line}.scroll-table{overflow:auto;margin-top:12px}table{border-collapse:collapse;width:100%;font-size:12px;white-space:nowrap}th{text-align:left;color:var(--muted);background:#f6f9f9}th,td{padding:9px;border-bottom:1px solid #e3ebed}tbody tr{cursor:pointer}tbody tr:hover,tbody tr.selected{background:#edf6f4}caption{text-align:left;margin-bottom:8px;color:var(--muted);white-space:normal}.empty{padding:28px 15px;text-align:center;color:var(--muted)}.cluster-panel{margin-top:12px;padding:12px;border:1px solid #c8d7db;border-radius:8px;background:#f6f9f9}.cluster-panel p{margin:0 0 8px;font-size:12px;color:var(--muted)}.cluster-list{display:grid;gap:6px;max-height:220px;overflow:auto}.cluster-list button{max-width:none;width:100%;text-align:left;font-size:12px}.cluster-list button.selected{background:#dceeea}details{margin-top:12px}summary{cursor:pointer;color:#41626b}main,.card,label,.controls,.figure-title>*{min-width:0}.card,.chart-wrap,.scroll-table{max-width:100%}.foot,.notice,.figure-title h2,.cluster-panel p,.cluster-list button{overflow-wrap:anywhere}.candle-panel{position:absolute;top:8px;right:8px;width:370px;max-width:calc(100% - 16px);max-height:calc(100% - 16px);overflow:auto;background:#fffffff5;border:1px solid #a8c6c7;border-radius:9px;padding:12px;box-shadow:0 3px 16px #183e4022;font-size:12px;overscroll-behavior:contain}.candle-panel header{display:flex;justify-content:space-between;gap:6px;align-items:center;flex-wrap:wrap}.candle-panel h3{font-size:14px;margin:0;min-width:0;overflow-wrap:anywhere}.candle-panel button{padding:5px 7px;font-size:12px;max-width:none}.candle-rows{display:grid;gap:7px;margin:8px 0}.candle-row{border-top:1px solid #e0e9eb;padding-top:6px;white-space:pre-line;overflow-wrap:anywhere}.candle-row button{text-align:left;background:#f3f8f7;width:100%;white-space:pre-line}.candle-paging{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.candle-event{border-top:1px solid #e0e9eb;margin-top:8px;padding-top:7px;white-space:pre-line;overflow-wrap:anywhere}.candle-event a{overflow-wrap:anywhere;color:#087e77}.candle-local{white-space:pre-line;color:#765a27}.candle-return{margin:8px 0;font-size:12px}[hidden]{display:none!important}@media(max-width:650px){main{padding:18px 12px}.card{padding:13px}h1{font-size:23px}.controls{gap:9px}select,input{max-width:165px}}
</style></head><body><main>
<div class="eyebrow">个人交易账本 · 已保存资料</div><h1>把每一次操作放回当时的图里</h1><p class="lead">选择一个标的或复盘案例，查看冻结的日 K 与成交事实。</p>
<div class="card"><div class="controls"><label>标的<select id="symbol"><option value="">请选择标的</option></select></label><label>资产类别<select id="asset"><option value="ALL">全部类别</option><option value="STOCK">股票</option><option value="ETF">ETF</option><option value="OPTION">期权</option></select></label><label>完整合约<select id="contract"><option value="ALL">全部合约</option></select></label><label>开始日期<input id="start" type="date"></label><label>截止日期<input id="end" type="date"></label><label>年份快捷选择<select id="segment"></select></label><button id="reset">重置当前标的</button><button id="clear-selection">清空选择</button></div>
<p class="toolbar-note">悬停蜡烛查看当天操作，点击固定；滚轮缩放，横拖移动。T只表示当天同时有买卖。</p><div id="selection-empty" class="empty">尚未选择标的或案例。</div>
<details id="chart-data-counts"><summary>筛选数据说明</summary><div id="metrics" class="metrics" hidden><div class="metric"><strong id="count">0</strong><span>筛选成交</span></div><div class="metric"><strong id="other">0</strong><span>其他活动</span></div><div class="metric"><strong id="bars">0</strong><span>当前图窗日 K</span></div><div class="metric"><strong id="all">0</strong><span>本次保存记录</span></div></div></details></div>
<section id="chart-workspace" class="card" hidden><div class="figure-title"><h2 id="title">交易时间线</h2><span id="basis" class="badge">行情口径待核验</span></div><div class="legend"><span class="buy">B 当天仅买入</span><span class="sell">S 当天仅卖出</span><span>T 当天同时买卖</span></div><div class="viewport-controls"><button id="zoom-in" aria-label="放大时间轴">放大 ＋</button><button id="zoom-out" aria-label="缩小时间轴">缩小 −</button><button id="pan-left" aria-label="向较早日期移动">← 较早</button><button id="pan-right" aria-label="向较晚日期移动">较晚 →</button><button id="fit-window">恢复整个区间</button><span id="viewport-status" class="viewport-status" role="status"></span></div><div id="chart-wrap" class="chart-wrap"><svg id="chart" viewBox="0 0 1120 390" preserveAspectRatio="none" role="group" aria-label="日线K线及同日买卖；可聚焦蜡烛查看当天操作"></svg><section id="candle-panel" class="candle-panel" aria-label="当前蜡烛的当天操作" hidden><header><h3 id="candle-title"></h3><button id="candle-pin">固定当天</button><button id="candle-close" aria-label="关闭当天面板">关闭 ×</button></header><p id="candle-state" class="foot"></p><p id="candle-ohlcv"></p><p id="candle-local" class="candle-local"></p><div id="candle-rows" class="candle-rows"></div><div id="candle-paging" class="candle-paging"><button id="candle-previous">上一页</button><span id="candle-page-status" role="status"></span><button id="candle-next">下一页</button></div><p id="candle-selected" class="candle-local"></p><details id="candle-event-details"><summary id="candle-event-count">当天事件</summary><div id="candle-events"></div></details></section></div><div id="candle-return" class="candle-return" hidden><span id="candle-return-status"></span> <button id="candle-return-button">返回固定日期</button></div><div id="gaps" class="notice"></div><div id="cluster-panel" class="cluster-panel" hidden><p id="cluster-summary"></p><div id="cluster-list" class="cluster-list" aria-label="所选日期逐笔记录"></div></div><div id="detail" class="detail" role="status" hidden></div>
<details id="trade-table"><summary>逐笔成交明细 · 默认折叠</summary><div class="controls" style="margin-top:12px"><button id="all-dates">已选范围全部日期</button><button id="previous-page">上一页</button><label>明细页码<input id="page-number" type="number" min="1" value="1" style="width:85px"></label><button id="next-page">下一页</button><span id="paging-status" class="foot"></span></div><div class="scroll-table"><table><caption id="table-caption">完整图段的分页明细；图上标记不随明细页截断。</caption><thead><tr><th>日期 / 时间</th><th>类型 / 活动</th><th>证券 / 完整合约</th><th>买卖 / 开平仓</th><th>数量</th><th>原价 / 权利金</th><th>费用</th><th>时段 / 精度</th></tr></thead><tbody id="rows"></tbody></table></div></details></section>
<section class="card"><details id="source-details"><summary>数据说明 / 来源与统计</summary><label class="check"><input id="events" type="checkbox" checked>在当天面板读取事件</label><div id="coverage" class="notice"></div><details><summary>已保存统计与计算范围</summary><div id="statistics" class="scroll-table"></div><p id="saved-scope" class="foot"></p><p class="foot">日期筛选、缩放和平移只改变图窗，以上统计保留原分析范围，不随页面操作重新计算。未取得 K 线不补造；净盈亏只展示资料完整、可以闭合的交易片段。</p></details></details></section>
</main><script id="journal-data" type="application/json">__DATA__</script><script>
"use strict";
__READER__
const DATA=JSON.parse(document.getElementById("journal-data").textContent), $=id=>document.getElementById(id),NS="http://www.w3.org/2000/svg";
const value=x=>jrReadable(x),dayMs=86400000,dateMs=d=>Date.parse(d+"T00:00:00Z"),BUY="#087e77",SELL="#b33f50",PAGE_SIZE=200;
let pageIndex=0,selectedDate="",segmentRows=[],chartFocusIds=new Set(),chartFocusWindow=null,chartLessonEvents=[];
const CANDLE_PAGE_SIZE=20;
let hoverDate="",pinnedDate="",candlePageIndex=0,candlePageDate="",candleSelectedRecord="",candlePages=new Map(),candleStateKey="",candleFacts=new Map(),candleDayRows=new Map(),candleDayEvents=new Map(),candleDayActions=new Map();
let chartGeometry={width:1120,height:390,left:76,right:36,top:35,bottom:320,plotWidth:1008};
let chartViewport=null,chartViewportKey="",chartViewportBounds=null,chartDrag=null,suppressChartClick=false,yearShortcutRange=null;
const names={SOURCE_DATE_UNCERTAIN:"来源日期，交易所交易日未确定",STOCK:"股票",ETF:"ETF",OPTION:"期权",FILL:"成交",ORDER:"委托",EXERCISE:"行权",ASSIGNMENT:"指派",EXPIRY:"到期",SPLIT:"拆股",DIVIDEND:"分红",REGULAR:"常规时段",PRE_MARKET:"盘前",AFTER_HOURS:"盘后",DATE_ONLY:"仅日期",UNKNOWN:"未知",SESSION_UNVERIFIED:"时段未核验",TIMEZONE_UNKNOWN:"时区未知",UNADJUSTED:"不复权原价",ADJUSTED_WITH_FACTORS:"可靠因子同口径",PROVIDER_UNVERIFIED:"行情价格口径未核验",PARTIAL:"部分覆盖",SOURCE_COMPLETE_FOR_WINDOW:"来源证实所选窗口完整",LIFETIME_RECONCILED:"开户至今已勾稽"};
const translate=x=>names[x]||jrCode(x);
function option(select,v,label){const el=document.createElement("option");el.value=v;el.textContent=label;select.appendChild(el)}
const marketName=x=>({US:"美国",USA:"美国",HK:"中国香港",HKEX:"中国香港",HONG_KONG:"中国香港",CN:"中国内地",SG:"新加坡"}[x]||value(x));
DATA.groups.forEach(g=>option($("symbol"),g.id,`${value(g.symbol)} · ${marketName(g.market_name)} · ${value(g.currency)}`));
function contractName(i){return i.asset_type==="OPTION"?`${i.symbol} · ${value(i.expiry)} ${value(i.strike)} ${translate(i.right)} ×${value(i.multiplier)} · ${translate(i.adjustment_status)}`:value(i.symbol)}
function resetContracts(){const prior=$("contract").value;$("contract").replaceChildren();option($("contract"),"ALL","全部合约");const seen=new Set();for(const r of DATA.records.filter(r=>r.group_id===$("symbol").value&&r.instrument.asset_type==="OPTION"&&["ALL","OPTION"].includes($("asset").value))){const i=r.instrument;if(!seen.has(i.key)){seen.add(i.key);option($("contract"),i.key,contractName(i))}}if(seen.has(prior))$("contract").value=prior}
function node(tag,attrs={},text){const el=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,String(v));if(text!==undefined)el.textContent=text;$("chart").appendChild(el);return el}
function dateLabel(r){return r.date_basis==="SOURCE_DATE"?`来源日期 ${value(r.occurred_at)}（交易所交易日未确定）`:r.date_basis==="EXCHANGE_DATE"?`交易所 ${value(r.local_time||r.occurred_at)}`:`来源时间 ${value(r.occurred_at)}（交易所日期未确定）`}
function ensureDateBounds(){
 const group=DATA.groups.find(g=>g.id===$("symbol").value),rows=group?DATA.records.filter(r=>r.group_id===group.id):DATA.records,recordDays=rows.map(r=>r.display_date).filter(d=>Number.isFinite(dateMs(d))).sort(),marketDays=(group&&group.market&&group.market.candles||[]).map(c=>c.date).filter(d=>Number.isFinite(dateMs(d))).sort(),days=recordDays.length?recordDays:marketDays;
 const available=[...DATA.records.map(r=>r.display_date),...DATA.groups.flatMap(g=>(g.market&&g.market.candles||[]).map(c=>c.date))].filter(d=>Number.isFinite(dateMs(d))).sort();
 if(available.length)for(const id of["start","end"]){$(id).min=available[0];$(id).max=available.at(-1)}
 if(!$("start").value&&!$("end").value&&days.length){$("start").value=days[0];$("end").value=days.at(-1)}
}
function resetSegments(matches,candles){const prior=$("segment").value,years=new Set([...DATA.records.filter(r=>r.group_id===$("symbol").value).map(r=>r.display_date),...(DATA.groups.find(g=>g.id===$("symbol").value)?.market?.candles||[]).map(c=>c.date)].filter(d=>Number.isFinite(dateMs(d))).map(d=>d.slice(0,4)));$("segment").replaceChildren();option($("segment"),"","整个已选区间");for(const year of [...years].sort())option($("segment"),year,year+" 年");if(years.has(prior))$("segment").value=prior;return $("segment").value}
function jrClearYearShortcut(){yearShortcutRange=null;$("segment").value=""}
function jrChooseYear(){const year=$("segment").value;if(year){if(!yearShortcutRange)yearShortcutRange={start:$("start").value,end:$("end").value};const group=DATA.groups.find(g=>g.id===$("symbol").value),days=[...DATA.records.filter(r=>group&&r.group_id===group.id).map(r=>r.display_date),...(group?.market?.candles||[]).map(c=>c.date)].filter(d=>Number.isFinite(dateMs(d))&&d.slice(0,4)===year).sort();if(days.length){$("start").value=days[0];$("end").value=days.at(-1)}}else if(yearShortcutRange){$("start").value=yearShortcutRange.start;$("end").value=yearShortcutRange.end;yearShortcutRange=null}}
function jrResetViewport(){chartViewport=null;chartViewportKey=""}
function jrClampViewport(start,end){if(!chartViewportBounds)return null;const bounds=chartViewportBounds,span=Math.min(bounds.end-bounds.start,Math.max(Math.min(dayMs,bounds.end-bounds.start),end-start));start=Math.max(bounds.start,Math.min(start,bounds.end-span));return {start,end:start+span}}
function jrZoomViewport(factor,anchor=.5){if(!chartViewport||!chartViewportBounds)return;anchor=Math.max(0,Math.min(1,anchor));const span=chartViewport.end-chartViewport.start,time=chartViewport.start+span*anchor,newSpan=Math.max(Math.min(dayMs,chartViewportBounds.end-chartViewportBounds.start),Math.min(chartViewportBounds.end-chartViewportBounds.start,span*factor));chartViewport=jrClampViewport(time-newSpan*anchor,time+newSpan*(1-anchor));render()}
function jrPanViewport(fraction){if(!chartViewport)return;const shift=(chartViewport.end-chartViewport.start)*fraction;chartViewport=jrClampViewport(chartViewport.start+shift,chartViewport.end+shift);render()}
function jrMeasureChart(){const rect=typeof $("chart").getBoundingClientRect==="function"?$("chart").getBoundingClientRect():{width:1120},width=Math.max(160,Number(rect.width)||1120),narrow=width<650,height=narrow?240:390,left=narrow?58:76,right=narrow?18:36;return {width,height,left,right,top:35,bottom:height-70,plotWidth:width-left-right}}
function jrChartX(event){const rect=typeof $("chart").getBoundingClientRect==="function"?$("chart").getBoundingClientRect():{left:0,width:chartGeometry.width};return (event.clientX-rect.left)/Math.max(1,rect.width)*chartGeometry.width}
function jrVisibleDay(day){const ms=dateMs(day)+dayMs/2;return chartViewport&&Number.isFinite(ms)&&ms>=chartViewport.start&&ms<=chartViewport.end}
function showRecord(r){document.querySelectorAll("tbody tr, #cluster-list button").forEach(row=>row.classList.toggle("selected",row.dataset.record===r.record_id));$("detail").dataset.record=r.record_id;$("detail").hidden=false;const i=r.instrument;$("detail").textContent=`${translate(r.activity_type)} · ${contractName(i)}
${dateLabel(r)} · ${translate(r.session_hint)} · ${translate(r.time_precision)} · ${value(i.exchange_timezone)}
${translate(r.side)} / 开平仓 ${translate(r.position_effect)} · 数量 ${value(r.quantity)} · ${i.asset_type==="OPTION"?"权利金":"券商原价"} ${value(r.price)} ${value(i.currency)} · 费用 ${value(r.fees)}${i.multiplier?" · 乘数 "+value(i.multiplier):""}
日期关联 ${jrTrustedDay(r)?"仅关联可靠的同日蜡烛，成交价格不用于图上定位":"交易所日期未确定；仅保留来源时间明细"}`}
function showDate(day,recordId){selectedDate=day;pageIndex=0;$("detail").dataset.record="";$("trade-table").open=true;render();const chosen=recordId&&segmentRows.find(r=>r.record_id===recordId);if(chosen)showRecord(chosen)}
function activate(el,fn){el.addEventListener("click",()=>{if(suppressChartClick){suppressChartClick=false;return}fn()});el.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();fn()}})}
function lessonEventDate(event,group){if(!group)return null;const referenced=(event.record_refs||[]).map(id=>DATA.records.find(row=>row.record_id===id)).filter(row=>row&&row.group_id===group.id);if(!referenced.length)return null;if(Object.prototype.hasOwnProperty.call(event,"dates_by_record")){const dates=event.dates_by_record;if(!dates||typeof dates!=="object"||Array.isArray(dates))return null;for(const row of referenced){const day=dates[row.record_id];if(typeof day==="string"&&Number.isFinite(dateMs(day)))return day}return null}return event.date||event.anchor_date||null}
function lessonEventGroups(events,group,start,end){const grouped=new Map();if(!group)return [];for(const event of events){if(event.anchor_role==="UNPLACED"||event.group_id&&event.group_id!==group.id)continue;const day=lessonEventDate(event,group);if(!day||!Number.isFinite(dateMs(day))||start&&day<start||end&&day>end)continue;if(!grouped.has(day))grouped.set(day,{date:day,events:[]});grouped.get(day).events.push(event)}return [...grouped.values()]}
// 日期关联与价格口径独立；未知来源日期不吸附到同名日K。
function jrTrustedDay(row){return row.date_basis==="EXCHANGE_DATE"&&["DETERMINED","DATE_ONLY"].includes(row.exchange_date_status)}
function jrDayBadge(rows){const fills=rows.filter(row=>row.activity_type==="FILL"),buy=fills.some(row=>row.side==="BUY"),sell=fills.some(row=>row.side==="SELL");if(buy&&sell)return "T";if(fills.some(row=>!["BUY","SELL"].includes(row.side)))return "";return buy?"B":sell?"S":""}
function jrClearCandleSelection(){hoverDate="";pinnedDate="";selectedDate="";candlePageIndex=0;candlePageDate="";candleSelectedRecord="";candlePages=new Map();$("candle-panel").hidden=true;$("candle-panel").dataset.date="";$("candle-return").hidden=true}
function jrCandleButton(label,fn,parent){const button=document.createElement("button");button.type="button";button.textContent=label;button.addEventListener("click",fn);parent.appendChild(button);return button}
function jrCandleFacts(row){const i=row.instrument;return `${dateLabel(row)} · ${translate(row.session_hint)} · ${translate(row.time_precision)}\n${translate(i.asset_type)} · ${contractName(i)}\n${translate(row.activity_type)} · ${translate(row.side)} / 开平仓 ${translate(row.position_effect)} · 数量 ${value(row.quantity)}\n${i.asset_type==="OPTION"?"权利金":"券商原价"} ${value(row.price)} ${value(i.currency)} · 费用 ${value(row.fees)}${i.multiplier?" · 乘数 "+value(i.multiplier):""}`}
function jrCandleSource(event,parent){
 const evidence=typeof jrEvidenceById!=="undefined"&&jrEvidenceById.get(event.evidence_id),source=evidence||event,parts=[source.source_name||source.publisher||source.title||"已保存事件资料",source.published_at&&"发布时间 "+value(source.published_at),source.available_at&&"资料可用 "+value(source.available_at),"资料截至 "+value(source.as_of),"保存时间 "+value(source.retrieved_at)].filter(Boolean),p=document.createElement("p");p.textContent="来源："+parts.map(value).join(" · ");parent.appendChild(p);const url=source.url||source.source_url;let parsed;try{parsed=new URL(url)}catch(error){}if(parsed&&parsed.protocol==="https:"&&!parsed.username&&!parsed.password){const link=document.createElement("a");link.setAttribute("href",url);link.setAttribute("target","_blank");link.setAttribute("rel","noopener noreferrer");link.textContent="公开原文";parent.appendChild(link)}
}
function jrCandleEvent(event,parent,corporate=false){
 const entry=document.createElement("div");entry.className="candle-event";parent.appendChild(entry);const roles={AVAILABLE_AT:"资料可用时刻",EVENT_AT:"事件发生时刻",UNPLACED:"时间未定位"},layers={decision_time:"当时可知",outcome:"事后结果",uncertain:"时点不确定",DECISION_TIME:"当时可知",OUTCOME:"事后结果",UNCERTAIN:"时点不确定"},p=document.createElement("p");
 if(corporate)p.textContent=`${translate(event.event_type)} · ${value(event.date)}\n拆股 ${value(event.numerator)} : ${value(event.denominator)} · 分红 ${value(event.amount)}`;
 else p.textContent=`${value(event.title)}\n${event.relevance_note||event.relevance?value(event.relevance_note||event.relevance)+"\n":""}${value(event.content)}\n${roles[event.anchor_role]||translate(event.anchor_role)}：${value(event.anchor_at)} · ${translate(event.publication_precision)}${event.availability_basis?" · 可用时刻依据 "+translate(event.availability_basis):""}${event.vintage_status?" · 历史资料 "+translate(event.vintage_status):""}\n`+(event.layers||[]).map(layer=>`${jrRefLabel(layer.record_id)} · ${layers[layer.layer]||translate(layer.layer)} · ${value(layer.reason)}`).join("\n");entry.appendChild(p);jrCandleSource(event,entry);if(!corporate&&typeof jrShowEvent==="function")jrCandleButton("查看事件完整资料",()=>jrShowEvent(event),entry);
}
// Compute placement in actual screen pixels, so the reader stays away from its
// candle after responsive SVG scaling. Narrow charts retain a direct pin button.
function jrCandlePanelPlacement(day){
 const rect=typeof $("chart").getBoundingClientRect==="function"?$("chart").getBoundingClientRect():{width:1120},width=Math.max(1,Number(rect.width)||1120),span=chartViewport?chartViewport.end-chartViewport.start:dayMs,viewX=chartGeometry.left+(dateMs(day)+dayMs/2-(chartViewport?.start||dateMs(day)))/span*chartGeometry.plotWidth,activeX=viewX/chartGeometry.width*width,side=activeX>=width/2?"left":"right",available=side==="left"?activeX-16:width-activeX-16,panelWidth=Math.max(0,Math.min(370,width-16,available>=220?available:width-16)),left=side==="left"?8:width-8-panelWidth;
 return {side,width,panelWidth,left,right:left+panelWidth,activeX,overlap:activeX>=left-4&&activeX<=left+panelWidth+4}
}
function jrPositionCandlePanel(day){const placement=jrCandlePanelPlacement(day);$("candle-panel").setAttribute("style",`left:${placement.side==="left"?"8px":"auto"};right:${placement.side==="right"?"8px":"auto"};width:${placement.panelWidth}px`);$("candle-panel").dataset.side=placement.side;$("candle-panel").dataset.anchorCovered=String(placement.overlap)}
function jrGlyphSize(){const rect=typeof $("chart").getBoundingClientRect==="function"?$("chart").getBoundingClientRect():{width:1120};return 14*chartGeometry.width/Math.max(1,Number(rect.width)||chartGeometry.width)}
function jrRenderCandlePanel(){
 const day=hoverDate||pinnedDate,candle=candleFacts.get(day),visible=!!candle&&jrVisibleDay(day);$("candle-panel").hidden=!visible;$("candle-return").hidden=!(pinnedDate&&candleFacts.has(pinnedDate)&&!jrVisibleDay(pinnedDate));$("candle-return-status").textContent=pinnedDate?`已固定 ${pinnedDate}，暂在当前图窗之外。`:"";if(!visible)return;
 jrPositionCandlePanel(day);$("candle-pin").disabled=day===pinnedDate;$("candle-pin").textContent=day===pinnedDate?"当天已固定":"固定当天";$("candle-panel").dataset.date=day;$("candle-title").textContent=day+" · "+value(DATA.groups.find(group=>group.id===$("symbol").value)?.symbol);$("candle-state").textContent=day===pinnedDate?"已固定 · Escape关闭":"临时预览 · 点击蜡烛或“固定当天”";$("candle-ohlcv").textContent=`开 ${value(candle.open)} · 高 ${value(candle.high)} · 低 ${value(candle.low)} · 收 ${value(candle.close)} · 成交量 ${value(candle.volume)}`;
 const rows=candleDayRows.get(day)||[],fills=rows.filter(row=>row.activity_type==="FILL"),limits=[];if(!fills.length)limits.push("当天无已保存成交。");if(fills.some(row=>!["BUY","SELL"].includes(row.side)))limits.push("存在未知买卖方向；字母只表示能够证明的方向。");if(rows.some(row=>row.instrument.asset_type==="OPTION"))limits.push("期权仅按标的日期关联；权利金不是标的股价。");if(DATA.groups.find(group=>group.id===$("symbol").value)?.market?.price_basis!=="UNADJUSTED")limits.push("保留券商原价；不作跨口径价位比较。");$("candle-local").textContent=limits.join("\n");
 if(candlePageDate!==day){if(candlePageDate)candlePages.set(candlePageDate,{index:candlePageIndex,record:candleSelectedRecord});const prior=candlePages.get(day);candlePageDate=day;candlePageIndex=prior?.index||0;candleSelectedRecord=prior?.record||""}const pages=Math.max(1,Math.ceil(rows.length/CANDLE_PAGE_SIZE));candlePageIndex=Math.max(0,Math.min(pages-1,candlePageIndex));$("candle-page-status").textContent=`当天 ${fills.length} 笔成交 · ${rows.length-fills.length} 条其他操作 · 全部 ${rows.length} 条 · ${candlePageIndex+1}/${pages} 页`;$("candle-paging").hidden=!rows.length;$("candle-previous").disabled=candlePageIndex===0;$("candle-next").disabled=candlePageIndex>=pages-1;$("candle-rows").replaceChildren();
 for(const row of rows.slice(candlePageIndex*CANDLE_PAGE_SIZE,(candlePageIndex+1)*CANDLE_PAGE_SIZE)){const entry=document.createElement("div");entry.className="candle-row";entry.dataset.record=row.record_id;$("candle-rows").appendChild(entry);const button=jrCandleButton(jrCandleFacts(row),()=>{candleSelectedRecord=row.record_id;$("candle-selected").textContent=jrCandleFacts(row);showRecord(row)},entry);button.dataset.record=row.record_id}
 const chosen=rows.find(row=>row.record_id===candleSelectedRecord);$("candle-selected").textContent=chosen?jrCandleFacts(chosen):"";
 const events=$("events").checked?candleDayEvents.get(day)||[]:[],corporate=$("events").checked?candleDayActions.get(day)||[]:[];$("candle-event-count").textContent=`当天事件 ${events.length+corporate.length} 项`;$("candle-event-details").hidden=!events.length&&!corporate.length;$("candle-events").replaceChildren();for(const event of events)jrCandleEvent(event,$("candle-events"));for(const event of corporate)jrCandleEvent(event,$("candle-events"),true);candlePages.set(day,{index:candlePageIndex,record:candleSelectedRecord})
}
function jrPreviewCandle(day){if(chartDrag&&suppressChartClick||!candleFacts.has(day)||!jrVisibleDay(day))return;hoverDate=day;jrRenderCandlePanel()}
function jrPinCandle(day,recordId){if(!candleFacts.has(day)||recordId&&!(candleDayRows.get(day)||[]).some(row=>row.record_id===recordId))return false;hoverDate="";pinnedDate=day;selectedDate=day;if(recordId){const index=(candleDayRows.get(day)||[]).findIndex(row=>row.record_id===recordId);if(index>=0){candlePageDate=day;candlePageIndex=Math.floor(index/CANDLE_PAGE_SIZE);candleSelectedRecord=recordId}}jrRenderCandlePanel();if(typeof jrRender==="function")jrRender();return true}
function jrReturnPinnedCandle(){if(!pinnedDate||!candleFacts.has(pinnedDate)||!chartViewport)return;const span=chartViewport.end-chartViewport.start,center=dateMs(pinnedDate)+dayMs/2;chartViewport=jrClampViewport(center-span/2,center+span/2);hoverDate="";render()}
function jrLeaveCandle(event){if(event?.relatedTarget&&typeof $("candle-panel").contains==="function"&&$("candle-panel").contains(event.relatedTarget))return;hoverDate="";jrRenderCandlePanel()}
function jrBindCandle(el,day){el.addEventListener("pointerenter",()=>jrPreviewCandle(day));el.addEventListener("pointerleave",jrLeaveCandle);el.addEventListener("focus",()=>jrPreviewCandle(day));el.addEventListener("click",()=>{if(suppressChartClick){suppressChartClick=false;return}jrPinCandle(day)});el.addEventListener("keydown",event=>{if(event.key==="Escape"){event.preventDefault();jrClearCandleSelection();render()}else if(event.key==="Enter"||event.key===" "){event.preventDefault();jrPinCandle(day)}})}
function render(){
 ensureDateBounds();const priorDetail=$("detail").dataset.record,group=DATA.groups.find(g=>g.id===$("symbol").value),m=group&&group.market,stateKey=JSON.stringify([group?.id,$("asset").value,$("contract").value,$("start").value,$("end").value]);if(candleStateKey!==stateKey){jrClearCandleSelection();candleStateKey=stateKey}
 $("selection-empty").hidden=!!group;$("metrics").hidden=!group;$("chart-data-counts").hidden=!group;$("chart-workspace").hidden=!group;chartGeometry=jrMeasureChart();$("chart").replaceChildren();$("rows").replaceChildren();$("cluster-list").replaceChildren();$("cluster-panel").hidden=true;$("detail").dataset.record="";$("detail").textContent="";$("detail").hidden=true;$("all").textContent=DATA.records.length;candleFacts=new Map();candleDayRows=new Map();candleDayEvents=new Map();candleDayActions=new Map();
 if(!group){segmentRows=[];$("segment").replaceChildren();$("count").textContent=0;$("other").textContent=0;$("bars").textContent=0;$("paging-status").dataset.matchCount="0";jrRenderCandlePanel();return}
 const matches=DATA.records.filter(r=>r.group_id===group.id&&($("asset").value==="ALL"||r.instrument.asset_type===$("asset").value)&&($("contract").value==="ALL"||r.instrument.key===$("contract").value)&&(!$("start").value||r.display_date>=$("start").value)&&(!$("end").value||r.display_date<=$("end").value));
 $("title").textContent=`${value(group.symbol)} · ${value(group.currency)} 日 K`;$("basis").textContent=m?translate(m.price_basis):"未取得行情";
 let candles=m&&Array.isArray(m.candles)?m.candles.filter(c=>!$("end").value||c.date<=$("end").value):[];
 const year=resetSegments(matches,candles);segmentRows=matches;const start=$("start").value,end=$("end").value,validWindow=(!start||Number.isFinite(dateMs(start)))&&(!end||Number.isFinite(dateMs(end)))&&(!start||!end||start<=end);let contextCandles=[],windowCandles=[];if(validWindow){windowCandles=candles.filter(c=>(!start||c.date>=start)&&(!end||c.date<=end));if(start)contextCandles=candles.filter(c=>c.date<start&&dateMs(c.date)>=dateMs(start)-90*dayMs).slice(-60)}else segmentRows=[];candles=contextCandles.concat(windowCandles);candleFacts=new Map(candles.map(c=>[c.date,c]));
 for(const row of segmentRows){if(!jrTrustedDay(row))continue;if(!candleDayRows.has(row.display_date))candleDayRows.set(row.display_date,[]);candleDayRows.get(row.display_date).push(row)}
 $("count").textContent=segmentRows.filter(r=>r.activity_type==="FILL").length;$("other").textContent=segmentRows.filter(r=>r.activity_type!=="FILL").length;
 if(selectedDate&&!segmentRows.some(r=>r.display_date===selectedDate)&&!candleFacts.has(selectedDate))selectedDate="";const detailRows=selectedDate?segmentRows.filter(r=>r.display_date===selectedDate):segmentRows,pageCount=Math.max(1,Math.ceil(detailRows.length/PAGE_SIZE));pageIndex=Math.max(0,Math.min(pageCount-1,pageIndex));const rows=detailRows.slice(pageIndex*PAGE_SIZE,(pageIndex+1)*PAGE_SIZE);
 $("page-number").value=pageIndex+1;$("page-number").max=pageCount;$("previous-page").disabled=pageIndex===0;$("next-page").disabled=pageIndex>=pageCount-1;$("paging-status").textContent=`${year?year+" 年快捷范围":"连续已选区间"} ${segmentRows.length} 条 · ${selectedDate||"全部日期"} ${detailRows.length} 条 · 明细 ${pageIndex+1}/${pageCount} 页`;$("paging-status").dataset.matchCount=segmentRows.length;$("paging-status").dataset.segmentCount=segmentRows.length;$("table-caption").textContent=(selectedDate?selectedDate+" 当日逐笔事实":"完整图段逐笔事实")+"；每页200条；缩放不删除记录，分页不改变图窗。";
 const reasons=(m&&m.gaps||[]).map(g=>g.detail?value(g.detail):`${translate(g.reason)}${g.date?" · "+g.date:""}${g.start?" · "+g.start+" 至 "+value(g.end):""}`),unmapped=segmentRows.filter(r=>!jrTrustedDay(r)||!candleFacts.has(r.display_date));if(unmapped.length)reasons.unshift(`${unmapped.length} 条操作没有可靠对应日 K，不移到邻日；请从逐笔明细读取。`);if(segmentRows.some(r=>!jrTrustedDay(r)))reasons.unshift("来源日期与交易所日期不能唯一映射；保留来源时间，不认定对应日K。");if(!validWindow)reasons.unshift("起日晚于止日；当前范围不展示行情或成交。");else if(!m||!candles.length)reasons.unshift("没有可核验的历史行情；保留真实交易日期与明细。");else if(!windowCandles.length)reasons.unshift("已选图窗内没有可核验的日 K；只显示已注明的近邻背景，不补造窗口行情。");if(contextCandles.length)reasons.push(`近邻背景：图窗前 ${contextCandles.length} 根冻结日 K，${contextCandles[0].date} 至 ${contextCandles.at(-1).date}；限前90日和60根，不属于成交筛选范围。`);$("gaps").textContent=reasons.join("\n");$("gaps").hidden=!reasons.length;
 const eventGroups=lessonEventGroups(chartLessonEvents,group,start,end);candleDayEvents=new Map(eventGroups.map(entry=>[entry.date,entry.events]));for(const event of m&&m.events||[]){if(!candleDayActions.has(event.date))candleDayActions.set(event.date,[]);candleDayActions.get(event.date).push(event)}
 const W=chartGeometry.width,L=chartGeometry.left,R=chartGeometry.right,T=chartGeometry.top,B=chartGeometry.bottom,dates=[...candles.map(c=>c.date),...segmentRows.map(r=>r.display_date),...eventGroups.map(events=>events.date),...(validWindow?[start,end]:[])].filter(d=>Number.isFinite(dateMs(d)));$("chart").setAttribute("viewBox",`0 0 ${W} ${chartGeometry.height}`);
 if(!dates.length||!validWindow){$("bars").textContent=0;$("viewport-status").textContent=validWindow?"当前区间没有可显示的冻结资料。":"起日晚于止日或日期无效，请调整日期。";chartViewportBounds=null;node("text",{x:W/2,y:200,"text-anchor":"middle",fill:"#617480"},"当前筛选无交易或行情")}else{
 const boundFirst=dates.reduce((a,d)=>Math.min(a,dateMs(d)),Infinity),boundEnd=dates.reduce((a,d)=>Math.max(a,dateMs(d)+dayMs),-Infinity),key=JSON.stringify([group.id,$("asset").value,$("contract").value,start,end,year]);chartViewportBounds={start:boundFirst,end:boundEnd};if(!chartViewport||chartViewportKey!==key){chartViewport={...chartViewportBounds};chartViewportKey=key}else chartViewport=jrClampViewport(chartViewport.start,chartViewport.end);
 const first=chartViewport.start,span=chartViewport.end-chartViewport.start,x=d=>L+(dateMs(d)+dayMs/2-first)/span*(W-L-R),visibleCandles=candles.filter(c=>jrVisibleDay(c.date)),numbers=visibleCandles.flatMap(c=>[c.open,c.high,c.low,c.close].map(Number)).filter(Number.isFinite);let lo=numbers.reduce((a,n)=>Math.min(a,n),Infinity),hi=numbers.reduce((a,n)=>Math.max(a,n),-Infinity);if(!numbers.length){lo=0;hi=1}const pad=Math.max((hi-lo)*.09,Math.abs(hi)*.015,.01);lo-=pad;hi+=pad;const y=p=>B-(p-lo)/(hi-lo)*(B-T);$("bars").textContent=visibleCandles.length;
 $("viewport-status").textContent=`当前图窗：${new Date(first).toISOString().slice(0,10)} 至 ${new Date(chartViewport.end-1).toISOString().slice(0,10)} · 已选记录范围：${start||"最早资料"} 至 ${end||"最新资料"}；图窗操作不改变报告依据。`;
 $("zoom-in").disabled=span<=Math.min(dayMs,boundEnd-boundFirst)+1;$("zoom-out").disabled=span>=boundEnd-boundFirst-1;$("pan-left").disabled=first<=boundFirst+1;$("pan-right").disabled=chartViewport.end>=boundEnd-1;
 const defs=node("defs"),clip=document.createElementNS(NS,"clipPath"),clipRect=document.createElementNS(NS,"rect");clip.setAttribute("id","journal-plot");for(const [key,val]of Object.entries({x:L,y:T-20,width:W-L-R,height:B-T+40}))clipRect.setAttribute(key,String(val));clip.appendChild(clipRect);defs.appendChild(clip);
 if(chartFocusWindow&&(!chartFocusWindow.group_id||chartFocusWindow.group_id===group.id)){const a=Math.max(first,dateMs(chartFocusWindow.start)),b=Math.min(chartViewport.end,dateMs(chartFocusWindow.end)+dayMs);if(a<b)node("rect",{x:L+(a-first)/span*(W-L-R),y:T,width:(b-a)/span*(W-L-R),height:B-T,fill:"#eaf1fb","data-focus-window":"true","clip-path":"url(#journal-plot)"})}
 for(let k=0;k<=4;k++){const yy=T+k*(B-T)/4;node("line",{x1:L,y1:yy,x2:W-R,y2:yy,stroke:"#e5ecee"});node("text",{x:L-10,y:yy+4,"text-anchor":"end","data-price-tick":"true",fill:"#617480","font-size":11},numbers.length?(hi-k*(hi-lo)/4).toFixed(2):"—")}
 const cellWidth=(W-L-R)/Math.max(span/dayMs,1),cw=Math.max(1,Math.min(12,cellWidth*.6)),glyphSize=jrGlyphSize();for(const c of visibleCandles){
  const xx=x(c.date),high=y(Number(c.high)),low=y(Number(c.low)),bodyTop=Math.min(y(Number(c.open)),y(Number(c.close))),bodyHeight=Math.max(1,Math.abs(y(Number(c.close))-y(Number(c.open)))),color=Number(c.close)>=Number(c.open)?BUY:SELL,dayRows=candleDayRows.get(c.date)||[],fills=dayRows.filter(row=>row.activity_type==="FILL"),letter=jrDayBadge(dayRows),focus=fills.some(row=>chartFocusIds.has(row.record_id)),label=`${c.date} 开 ${value(c.open)} 高 ${value(c.high)} 低 ${value(c.low)} 收 ${value(c.close)} · 当天 ${fills.length} 笔成交；点击固定当天面板`;
  const hit=node("rect",{x:xx-Math.max(cw,Math.min(22,cellWidth*.8))/2,y:Math.max(T-20,high-4),width:Math.max(cw,Math.min(22,cellWidth*.8)),height:Math.max(8,low-high+8),fill:"transparent","aria-hidden":"true","data-candle-hit-date":c.date,"clip-path":"url(#journal-plot)"});jrBindCandle(hit,c.date);
  const wick=node("line",{x1:xx,y1:high,x2:xx,y2:low,stroke:color,"data-candle-wick-date":c.date,"clip-path":"url(#journal-plot)"});jrBindCandle(wick,c.date);
  const rect=node("rect",{x:xx-cw/2,y:bodyTop,width:cw,height:bodyHeight,fill:color,opacity:.78,stroke:focus?"#efab25":color,"stroke-width":focus?2:0,tabindex:0,role:"button","aria-label":label,"data-candle-date":c.date,"clip-path":"url(#journal-plot)"}),tip=document.createElementNS(NS,"title");tip.textContent=`${c.date} 开 ${c.open} 高 ${c.high} 低 ${c.low} 收 ${c.close} · 成交量 ${c.volume}`;rect.appendChild(tip);jrBindCandle(rect,c.date);
  if(letter){const ids=fills.map(row=>row.record_id),attrs={x:xx,y:bodyTop+bodyHeight/2,"text-anchor":"middle","dominant-baseline":"central",fill:letter==="B"?BUY:letter==="S"?SELL:"#4d506f",stroke:focus?"#efab25":"white","stroke-width":focus?3:2,"paint-order":"stroke",tabindex:-1,role:"button","font-size":glyphSize,"data-screen-font-size":14,"font-weight":700,"data-bst":letter,"data-date":c.date,"data-record-count":ids.length,"data-records":JSON.stringify(ids),"data-marker-axis":"CANDLE_DATE","data-anchor-x":xx,"data-focus":focus?"true":"false","clip-path":"url(#journal-plot)","aria-label":`${c.date} ${letter==="B"?"仅买入":letter==="S"?"仅卖出":"同时买卖"}；点击查看当天全部操作`};if(ids.length===1)attrs["data-record"]=ids[0];const mark=node("text",attrs,letter);jrBindCandle(mark,c.date)}
 }
 const tickCount=W<650?2:5;for(let k=0;k<=tickCount;k++){const ms=first+k*(span-1)/tickCount;node("text",{x:L+k*(W-L-R)/tickCount,y:chartGeometry.height-25,"text-anchor":k===0?"start":k===tickCount?"end":"middle",fill:"#617480","font-size":11},new Date(ms).toISOString().slice(0,10))}
 }
 for(const r of rows){const tr=document.createElement("tr");tr.dataset.record=r.record_id;const i=r.instrument,cells=[dateLabel(r),`${translate(i.asset_type)} / ${translate(r.activity_type)}`,contractName(i),`${translate(r.side)} / ${translate(r.position_effect)}`,r.quantity,`${value(r.price)} ${value(i.currency)}`,r.fees,`${translate(r.session_hint)} / ${translate(r.time_precision)}`];for(const text of cells){const td=document.createElement("td");td.textContent=value(text);tr.appendChild(td)}tr.addEventListener("click",()=>showRecord(r));$("rows").appendChild(tr)}
 if(selectedDate&&$("trade-table").open){$("cluster-panel").hidden=false;$("cluster-summary").textContent=`${selectedDate} · 当日 ${detailRows.length} 条，当前 ${rows.length} 条；通过下方明细页码读取全部。`;for(const r of rows){const button=document.createElement("button");button.type="button";button.dataset.record=r.record_id;button.textContent=`${dateLabel(r)} · ${contractName(r.instrument)} · 数量 ${value(r.quantity)} · ${r.instrument.asset_type==="OPTION"?"权利金":"原价"} ${value(r.price)} ${value(r.instrument.currency)}`;button.addEventListener("click",()=>showRecord(r));$("cluster-list").appendChild(button)}}
 if(priorDetail){const prior=segmentRows.find(r=>r.record_id===priorDetail);if(prior)showRecord(prior)}jrRenderCandlePanel()
}
function readerRange(window){if(!window)return "已保存资料范围";return `${value(window.start||window.start_at||window.actual_start)} 至 ${value(window.end||window.end_at||window.actual_end)}`}
function describeCoverage(c){if(!c)return"覆盖证明缺失，不能声称所选历史完整。";const lines=[];if(c.status)lines.push(translate(c.status));if(c.requested_window)lines.push("请求区间："+readerRange(c.requested_window));if(c.actual_start||c.actual_end)lines.push(`实际取得：${value(c.actual_start)} 至 ${value(c.actual_end)}`);if(c.account_opened_at===null||c.account_start===null)lines.push("起始账户资料未知；覆盖以实际保存资料为准。");for(const gap of c.gaps||[])lines.push(value(gap));if(c.asset_classes||c.assets)lines.push("类别覆盖："+value(c.asset_classes||c.assets));return lines.length?lines.join("\n"):"覆盖资料暂未提供。"}
function renderStatistics(){const stats=DATA.analysis||{},table=document.createElement("table"),caption=document.createElement("caption"),scope=DATA.statistics_scope||{};caption.textContent=(scope.mode==="SNAPSHOT_WINDOW"?"原统计区间："+readerRange(scope.window):"统计依据：已保存记录可闭合片段")+"；资料截止 "+value(scope.cutoff)+"。页面筛选不重算，按原币种展示，不等同于账户收益。";table.appendChild(caption);const header=document.createElement("tr");for(const label of["原币种","可计算片段","不可计算片段","闭合数量","毛盈亏","费用","净盈亏"]){const th=document.createElement("th");th.textContent=label;header.appendChild(th)}table.appendChild(header);for(const row of stats.by_currency||[]){const tr=document.createElement("tr");for(const v of[row.currency,row.available_episodes,row.unavailable_episodes,row.closed_quantity,row.gross_pnl,row.fees,row.net_pnl]){const td=document.createElement("td");td.textContent=v==null?"不可计算":value(v);tr.appendChild(td)}table.appendChild(tr)}$("statistics").appendChild(table);for(const item of stats.limitations||[]){const text=document.createElement("p");text.className="foot";text.textContent=value(item);$("statistics").appendChild(text)}}
$("coverage").textContent=describeCoverage(DATA.coverage);renderStatistics();$("saved-scope").textContent=`统计资料截止：${value(DATA.as_of)}。保存时间：${value(DATA.retrieved_at)}。`;
function clearChartFocus(){chartFocusIds=new Set();chartFocusWindow=null;chartLessonEvents=[]}
function clearReviewSelection(){if(typeof jrClearSelection==="function")jrClearSelection()}
$("symbol").addEventListener("change",()=>{clearReviewSelection();jrClearCandleSelection();pageIndex=0;selectedDate="";$("segment").value="";$("start").value="";$("end").value="";$("trade-table").open=false;clearChartFocus();jrClearYearShortcut();jrResetViewport();resetContracts();render()});for(const id of["asset","contract","start","end","segment"])$(id).addEventListener("change",()=>{clearReviewSelection();jrClearCandleSelection();clearChartFocus();pageIndex=0;selectedDate="";if(id==="start"||id==="end")jrClearYearShortcut();else if(id==="segment")jrChooseYear();if(id==="asset")resetContracts();$("detail").dataset.record="";jrResetViewport();render()});$("events").addEventListener("change",render);$("previous-page").addEventListener("click",()=>{pageIndex--;render()});$("next-page").addEventListener("click",()=>{pageIndex++;render()});$("page-number").addEventListener("change",()=>{const chosen=Number($("page-number").value);pageIndex=Number.isInteger(chosen)&&chosen>0?chosen-1:0;render()});$("all-dates").addEventListener("click",()=>{selectedDate="";pageIndex=0;render()});$("reset").addEventListener("click",()=>{clearReviewSelection();jrClearCandleSelection();pageIndex=0;selectedDate="";$("asset").value="ALL";$("contract").value="ALL";$("start").value="";$("end").value="";$("segment").value="";clearChartFocus();jrClearYearShortcut();jrResetViewport();resetContracts();render()});$("clear-selection").addEventListener("click",()=>{clearReviewSelection();jrClearCandleSelection();$("symbol").value="";selectedDate="";pageIndex=0;clearChartFocus();jrClearYearShortcut();jrResetViewport();resetContracts();render()});
$("zoom-in").addEventListener("click",()=>jrZoomViewport(.7));$("zoom-out").addEventListener("click",()=>jrZoomViewport(1/.7));$("pan-left").addEventListener("click",()=>jrPanViewport(-.25));$("pan-right").addEventListener("click",()=>jrPanViewport(.25));$("fit-window").addEventListener("click",()=>{jrResetViewport();render()});
$("chart").addEventListener("wheel",event=>{if(!chartViewport)return;event.preventDefault();const multiplier=event.deltaMode===1?16:event.deltaMode===2?470:1;const delta=Number(event.deltaY)||Number(event.deltaX)||0;jrZoomViewport(Math.exp(Math.max(-1,Math.min(1,delta*multiplier*.0015))),(jrChartX(event)-chartGeometry.left)/chartGeometry.plotWidth)},{passive:false});
$("chart").addEventListener("click",()=>{suppressChartClick=false});
$("chart").addEventListener("pointerdown",event=>{if(!chartViewport||event.button!==undefined&&event.button!==0)return;chartDrag={id:event.pointerId,x:jrChartX(event),viewport:{...chartViewport},plotWidth:chartGeometry.plotWidth,captured:false};suppressChartClick=false});
$("chart").addEventListener("pointermove",event=>{if(!chartDrag||event.pointerId!==chartDrag.id)return;const dx=jrChartX(event)-chartDrag.x;if(Math.abs(dx)<3&&!suppressChartClick)return;suppressChartClick=true;if(!chartDrag.captured&&typeof $("chart").setPointerCapture==="function"){$("chart").setPointerCapture(event.pointerId);chartDrag.captured=true}const shift=-dx/chartDrag.plotWidth*(chartDrag.viewport.end-chartDrag.viewport.start);chartViewport=jrClampViewport(chartDrag.viewport.start+shift,chartDrag.viewport.end+shift);$("chart").classList.toggle("dragging",true);render()});
function finishChartDrag(){chartDrag=null;$("chart").classList.toggle("dragging",false)}$("chart").addEventListener("pointerup",finishChartDrag);$("chart").addEventListener("pointercancel",finishChartDrag);$("chart").addEventListener("lostpointercapture",finishChartDrag);
$("trade-table").addEventListener("toggle",()=>{if($("trade-table").open)render()});
$("candle-pin").addEventListener("click",()=>jrPinCandle(hoverDate||pinnedDate));
$("candle-previous").addEventListener("click",()=>{candlePageIndex--;jrRenderCandlePanel()});$("candle-next").addEventListener("click",()=>{candlePageIndex++;jrRenderCandlePanel()});$("candle-close").addEventListener("click",()=>{jrClearCandleSelection();render()});$("candle-return-button").addEventListener("click",jrReturnPinnedCandle);
$("chart-wrap").addEventListener("pointerleave",()=>{hoverDate="";jrRenderCandlePanel()});$("chart-wrap").addEventListener("focusout",event=>{if(typeof $("chart-wrap").contains==="function"&&$("chart-wrap").contains(event.relatedTarget))return;hoverDate="";jrRenderCandlePanel()});$("candle-panel").addEventListener("pointerleave",jrLeaveCandle);$("candle-panel").addEventListener("keydown",event=>{if(event.key==="Escape"){event.preventDefault();jrClearCandleSelection();render()}});
if(typeof window!=="undefined")window.addEventListener("resize",()=>{finishChartDrag();render()});
if(DATA.initial_group_id&&DATA.groups.some(group=>group.id===DATA.initial_group_id))$("symbol").value=DATA.initial_group_id;resetContracts();render();
</script></body></html>'''
