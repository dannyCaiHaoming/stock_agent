"""Local workspace UI, built from bounded projections rather than old HTML."""
from __future__ import annotations

from copy import deepcopy
import re

from .charts import render_chart
from .common import canonical_json
from .reflection import ReflectionError
from .review import render_review_payload


def _encoded(value) -> str:
    return canonical_json(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _script(page: str, script: str) -> str:
    return page.replace("</script></body></html>", script + "\n</script></body></html>", 1)


def render_landing(state: dict, csrf: str) -> str:
    return _LANDING.replace("__BOOT__", _encoded({"state": state, "csrf": csrf}))


def render_timeline(snapshot: dict) -> str:
    page = render_chart(snapshot)
    page = page.replace("个人交易账本 · 冻结图表", "个人交易账本 · 最新时间线", 1)
    page = page.replace("选择一个标的或复盘案例，查看冻结的日 K 与成交事实。", "选择标的查看全部已保存成交；刷新后保留当前图窗。", 1)
    return _script(page, _TIMELINE_BRIDGE)


def render_report(projection, kind: str, identifier: str, report_id: str) -> str:
    if not re.fullmatch(r"reflection-[0-9a-f]{32}", report_id):
        raise ReflectionError("复盘版本无效")
    chart, review = projection.select(kind, identifier)
    if kind == "summary":
        # Names only: no whole frozen candles, trades or evidence in the summary.
        chart["groups"] = [{"id": row["id"], "symbol": row["symbol"], "market_name": row["market_name"], "currency": row["currency"], "market": None} for row in projection.groups.values()]
    page = render_review_payload(chart, review)
    prefix = "/reports/" + report_id
    page = page.replace('fetch("/summary?"', 'fetch("' + prefix + '/summary?"')
    page = page.replace('window.location.assign("/view?"', 'window.location.assign("' + prefix + '/view?"')
    if kind == "summary":
        page = page.replace("</style>", _SUMMARY_CSS + "</style>", 1)
        groups = {}
        global_days = set()
        for gid, group in projection.groups.items():
            rows = [row for row in projection.records.values() if row["group_id"] == gid]
            days = {row["display_date"] for row in rows if row.get("display_date")}
            days.update(row["date"] for row in (group.get("market") or {}).get("candles", []) if row.get("date"))
            global_days.update(days)
            groups[gid] = {"days": sorted(days), "contracts": sorted({row["instrument"]["key"] for row in rows if row["instrument"]["asset_type"] == "OPTION"})}
        metadata = {"groups": groups, "start": min(global_days, default=""), "end": max(global_days, default="")}
        page = _script(page, "const JOURNAL_REPORT_SCOPE=" + _encoded(metadata) + ";\n" + _SUMMARY_BRIDGE)
    else:
        page = page.replace("</style>", "main{padding-top:12px}" + "</style>", 1)
        page = page.replace("</main>", '<p class="foot">以上图表和讲解使用这版复盘当时的冻结资料。</p></main>', 1)
    return page


_TIMELINE_BRIDGE = r'''
window.journalExportState=()=>({group:$('symbol').value,asset:$('asset').value,contract:$('contract').value,start:$('start').value,end:$('end').value,segment:$('segment').value,viewport:chartViewport?{...chartViewport}:null,pin:pinnedDate,selected:selectedDate,page:pageIndex,candlePage:candlePageIndex,candleRecord:candleSelectedRecord,table:!!$('trade-table').open,events:!!$('events').checked});
window.journalRestoreState=s=>{
 if(!s||typeof s!=='object')return {restored:false,message:''};
 if(s.group&&!DATA.groups.some(g=>g.id===s.group))return {restored:false,message:'原标的不在本次资料中，请重新选择。'};
 $('symbol').value=s.group||'';$('asset').value=['ALL','STOCK','ETF','OPTION'].includes(s.asset)?s.asset:'ALL';resetContracts();
 const hasContract=Array.from($('contract').children).some(el=>el.value===s.contract);$('contract').value=hasContract?s.contract:'ALL';
 for(const key of['start','end'])$(key).value=typeof s[key]==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(s[key])?s[key]:'';
 $('segment').value='';jrClearYearShortcut();jrResetViewport();render();
 if(s.segment&&Array.from($('segment').children).some(el=>el.value===s.segment)){$('segment').value=s.segment;jrChooseYear();render()}
 if(s.viewport&&Number.isFinite(s.viewport.start)&&Number.isFinite(s.viewport.end)&&s.viewport.start<s.viewport.end&&chartViewportBounds){chartViewport=jrClampViewport(s.viewport.start,s.viewport.end);render()}
 $('events').checked=s.events!==false;
 if(s.pin&&candleFacts.has(s.pin)){jrPinCandle(s.pin);candlePageIndex=Number.isInteger(s.candlePage)?Math.max(0,s.candlePage):0;candleSelectedRecord=(candleDayRows.get(s.pin)||[]).some(r=>r.record_id===s.candleRecord)?s.candleRecord:'';jrRenderCandlePanel()}
 pageIndex=Number.isInteger(s.page)?Math.max(0,s.page):0;$('trade-table').open=!!s.table;
 if(s.selected&&segmentRows.some(r=>r.display_date===s.selected))selectedDate=s.selected;render();
 return {restored:true,message:hasContract?'':'原合约不在本次资料中，已切换为全部合约。'};
};
window.journalSelection=()=>({group_id:$('symbol').value,date:pinnedDate||'',asset:$('asset').value,contract:$('contract').value,start:$('start').value,end:$('end').value});
if(typeof parent!=='undefined'&&parent!==window){const notify=()=>parent.postMessage({type:'journal-selection'},window.location.origin);for(const id of['symbol','asset','contract','start','end','segment','clear-selection','reset','candle-pin','candle-close','chart'])$(id).addEventListener(['symbol','asset','contract','start','end','segment'].includes(id)?'change':'click',notify);for(const id of['chart','candle-panel'])$(id).addEventListener('keydown',event=>{if(['Enter',' ','Escape'].includes(event.key))notify()})}
'''

_SUMMARY_CSS = r'''
main>.eyebrow,main>h1,main>.lead,main>.card:not(#reflection-review){display:none!important}
main{padding:0 0 16px;max-width:none}#reflection-review{margin-top:0}#jr-directory{margin-top:18px}
'''

_SUMMARY_BRIDGE = r'''
let journalExternalSelection={group_id:'',date:'',asset:'ALL',contract:'ALL',start:'',end:''};
jrSummarySelection=()=>journalExternalSelection;jrSummaryCurrentRecords=()=>null;
window.journalApplySelection=async s=>{
 const next={group_id:s?.group_id||'',date:s?.date||'',asset:s?.asset||'ALL',contract:s?.contract||'ALL',start:s?.start||'',end:s?.end||''},group=JOURNAL_REPORT_SCOPE.groups[next.group_id];
 let missing=!!next.group_id&&!group||!!next.date&&(!group||!group.days.includes(next.date))||next.contract!=='ALL'&&(!group||!group.contracts.includes(next.contract));
 if(next.start&&next.end){const start=next.start>JOURNAL_REPORT_SCOPE.start?next.start:JOURNAL_REPORT_SCOPE.start,end=next.end<JOURNAL_REPORT_SCOPE.end?next.end:JOURNAL_REPORT_SCOPE.end;if(start>end)missing=true;next.start=start;next.end=end}
 if(!next.group_id){next.date='';next.start='';next.end='';next.contract='ALL';next.asset='ALL'}
 journalExternalSelection=next;
 if(missing){jrSummaryRequest++;jrSummaryKey=jrSummarySelectionKey(next);jrSummary={findings:[],improvement_plan:[],reference_records:[],reference_labels:{},selection:next,pagination:{page:0,page_size:12,total_count:0,total_pages:1}};jrPlans=[];jrSummaryPage=0;jrRender();$('jr-notice').textContent='当前选择尚未包含在这版复盘中。可查看全部已保存要点，或在 Codex 生成新复盘。';return false}
 $('jr-notice').textContent='';return jrLoadSummary(0,next);
};
'''

_LANDING = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>我的交易与复盘</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f3f7f7;color:#163440;font:15px/1.6 -apple-system,BlinkMacSystemFont,sans-serif}main{max-width:1400px;margin:auto;padding:24px 28px}h1{margin:0;font-size:28px}h2{font-size:20px;margin:0}.subtle{color:#617480;font-size:13px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:16px 0}button,input,select{font:inherit;color:#163440;border:1px solid #c8d7db;background:white;border-radius:7px;padding:8px 12px}button{cursor:pointer;background:#eaf3f1}button:disabled{opacity:.55;cursor:wait}.status{white-space:pre-line;color:#617480;margin:8px 0;overflow-wrap:anywhere}.error{color:#a02b3b}label{display:inline-grid;gap:5px;font-size:13px;margin:6px 14px 6px 0}details{background:#fff;border:1px solid #d9e3e5;border-radius:10px;padding:12px 16px;margin:12px 0}summary{cursor:pointer}iframe{width:100%;border:0;display:block;height:600px}.section-title{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:18px}.section-title select{max-width:650px}#review-meta{margin:6px 0}#empty-review{background:white;border-radius:10px;padding:20px}#all-research{background:white}#source-timezone{max-width:300px}[hidden]{display:none!important}@media(max-width:650px){main{padding:16px 10px}h1{font-size:24px}.section-title select{max-width:95vw}label{display:grid;margin-right:0}input{max-width:95vw}}
</style></head><body><main><h1>我的交易与复盘</h1><p class="subtle">全部已保存操作，在图里回看。</p><div class="toolbar"><button id="refresh">刷新时间线</button><button id="market">更新 K 线</button><button id="import-toggle">导入新交易</button><button id="reflection-help">生成新复盘</button></div><p id="timeline-meta" class="subtle"></p><p id="update-status" class="status" role="status" aria-live="polite"></p><details id="import-panel"><summary>导入官方 CSV</summary><p class="subtle">在老虎证券导出逐笔成交 CSV，选择文件的完整起止日期及显示时区。相同文件可重复导入；缺少稳定成交编号的重叠期间需要重新选择。</p><label>开始日期<input id="import-start" type="date" required></label><label>截止日期<input id="import-end" type="date" required></label><label>导出日期范围时区<select id="range-timezone"><option value="Asia/Hong_Kong">中国香港时间</option><option value="America/New_York">美国东部时间</option><option value="UTC">UTC</option></select></label><label>CSV 成交时区<select id="source-timezone"><option value="PER_ROW">按账单逐行明确时区</option><option value="Asia/Hong_Kong">中国香港时间（须与导出一致）</option><option value="America/New_York">美国东部时间</option><option value="UTC">UTC</option></select></label><label>官方成交 CSV<input id="csv-file" type="file" accept=".csv,text/csv"></label><button id="import-submit">保存新交易</button></details><details id="reflection-instructions"><summary>更新交易和复盘的方法</summary><p>读取新的老虎交易：在 Codex 调用“老虎交易账本”，告诉它开始日期和截止日期；或者在这里导入官方逐笔成交 CSV。</p><p>生成新复盘：在 Codex 调用“个人交易反思”，分析全部已保存操作。保存完成后点击“刷新时间线”，即可选择新版本。</p><p class="subtle">更新 K 线读取公开行情并保存新版本。已有复盘保留原来的交易、行情和事件依据。</p></details><iframe id="timeline" src="/timeline" title="最新完整交易时间线"></iframe><div class="section-title"><h2>已保存的复盘</h2><label>复盘版本<select id="report-version"></select></label><button id="all-research">查看全部要点</button></div><p id="review-meta" class="subtle"></p><p id="empty-review" hidden>还没有已保存的复盘。在 Codex 调用“个人交易反思”生成后，刷新即可查看。</p><iframe id="report" title="原文复盘和改进练习" hidden></iframe><script id="journal-boot" type="application/json">__BOOT__</script><script>
const boot=JSON.parse(document.getElementById('journal-boot').textContent),$=id=>document.getElementById(id);let state=boot.state,busy=false,selectedReport='',retained=null,lastSelectionKey='',globalResearch=false;
const friendlyTime=t=>t?String(t).replace('T',' ').replace(/\.\d+(?=Z|[+-])/,'').replace(/Z$/,' UTC'):'尚未取得';
function status(text,error=false){$('update-status').textContent=text;$('update-status').className=error?'status error':'status'}
function reportMeta(){const row=state.reports.find(r=>r.report_id===selectedReport);$('review-meta').textContent=row?`这版复盘资料截止 ${friendlyTime(row.cutoff)} · ${row.case_count} 项要点${row.pending_record_count?` · ${row.pending_record_count} 条操作尚未纳入这版复盘`:''}`:''}
function reportSource(){return '/reports/'+selectedReport+'/view?'+new URLSearchParams({kind:'summary',id:'0'})}
function showReport(){lastSelectionKey='';$('report').hidden=!selectedReport;$('empty-review').hidden=!!selectedReport;if(selectedReport)$('report').src=reportSource();reportMeta()}
function paint(next){const previous=selectedReport;state=next;selectedReport=state.reports.some(r=>r.report_id===previous)?previous:state.selected_report_id;$('report-version').replaceChildren();for(const r of state.reports){const o=document.createElement('option');o.value=r.report_id;o.textContent=`资料截止 ${friendlyTime(r.cutoff)} · 保存 ${friendlyTime(r.report_as_of)}`;$('report-version').appendChild(o)}$('report-version').value=selectedReport;$('report-version').disabled=!selectedReport;$('all-research').disabled=!selectedReport;$('timeline-meta').textContent=`已保存 ${state.timeline.record_count} 条操作 · 最近交易 ${friendlyTime(state.timeline.trade_through)} · K 线截至 ${friendlyTime(state.timeline.market_through)}`;reportMeta();return previous!==selectedReport}
function fit(frame){try{const size=frame.contentDocument?.querySelector('main')?.getBoundingClientRect().height;if(size){const height=Math.max(220,Math.ceil(size)+12)+'px';if(frame.style.height!==height)frame.style.height=height}}catch{}}
function watch(frame){fit(frame);try{const observer=new ResizeObserver(()=>fit(frame));observer.observe(frame.contentDocument.body)}catch{}}
function selection(){try{return $('timeline').contentWindow.journalSelection()}catch{return {group_id:'',date:'',asset:'ALL',contract:'ALL',start:'',end:''}}}
async function syncSummary(force=false,navigate=false){if(!selectedReport||globalResearch)return;const s=selection(),key=JSON.stringify(s);if(!force&&key===lastSelectionKey)return;try{const apply=$('report').contentWindow.journalApplySelection;if(typeof apply==='function'){lastSelectionKey=key;await apply(s);fit($('report'))}else if(navigate){$('report').src=reportSource()}}catch{}}
$('timeline').addEventListener('load',()=>{if(retained){try{const result=$('timeline').contentWindow.journalRestoreState(retained);if(result.message)status(result.message)}catch{status('图窗恢复未完成，请重新选择标的。',true)}retained=null}watch($('timeline'));syncSummary(true)});
$('report').addEventListener('load',()=>{watch($('report'));syncSummary(true)});
window.addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==$('timeline').contentWindow||event.data?.type!=='journal-selection')return;globalResearch=false;syncSummary(false,true);fit($('timeline'))});
async function update(path,body){if(busy)return;busy=true;for(const id of['refresh','market','import-submit'])$(id).disabled=true;status(path==='/api/market'?'正在更新公开行情…':'正在读取保存资料…');try{try{retained=$('timeline').contentWindow.journalExportState()}catch{retained=null}const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-Journal-CSRF':boot.csrf},body:JSON.stringify(body)}),result=await response.json();if(!response.ok||!result.state)throw Error(result.message||'更新失败，保留上次有效页面。');const changed=paint(result.state);lastSelectionKey='';$('timeline').src='/timeline';if(changed)showReport();else syncSummary(true);status(result.message+(result.counts&&'inserted' in result.counts?` 新增 ${result.counts.inserted||0} 条，修订 ${result.counts.revised||0} 条。`:result.counts&&'updated_symbols' in result.counts?` 更新 ${result.counts.updated_symbols} 个标的，${result.counts.failed_symbols} 个未能完整更新。`:'')+(state.warnings?.length?' '+state.warnings.join(' '):''));}catch(error){retained=null;status(error.message||'更新失败，保留上次有效页面。',true)}finally{busy=false;for(const id of['refresh','market','import-submit'])$(id).disabled=false}}
$('refresh').addEventListener('click',()=>update('/api/refresh',{}));$('market').addEventListener('click',()=>update('/api/market',{}));$('import-toggle').addEventListener('click',()=>{$('import-panel').open=!$('import-panel').open});$('reflection-help').addEventListener('click',()=>{$('reflection-instructions').open=true;$('reflection-instructions').scrollIntoView({block:'nearest'})});
$('import-submit').addEventListener('click',async()=>{const file=$('csv-file').files[0],start=$('import-start').value,end=$('import-end').value;if(!file||!start||!end||start>end){status('请选择官方 CSV，并填写完整、有序的起止日期。',true);return}if(file.size>4*1024*1024){status('CSV 超过 4MiB，请缩短单次导出期间。',true);return}try{const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));await update('/api/import',{csv_base64:btoa(binary),start,end,source_timezone:$('source-timezone').value,range_timezone:$('range-timezone').value})}catch{status('无法读取所选 CSV。',true)}});
$('report-version').addEventListener('change',()=>{selectedReport=$('report-version').value;globalResearch=false;showReport()});$('all-research').addEventListener('click',()=>{globalResearch=true;showReport()});paint(state);showReport();if(state.warnings?.length)status(state.warnings.join(' '));
</script></main></body></html>'''
