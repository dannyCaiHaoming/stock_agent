"""Business labels for journal readers; structured facts remain unchanged.

The same narrow projection is used by Python Markdown and browser text. Only
declared identities and recognisable internal-reference syntax are replaced;
financial numbers, ordinary words and public links are never scrubbed by a
generic hash or hexadecimal pattern.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit


_CODES = {
    "UNKNOWN": "未知", "AVAILABLE": "可计算", "UNAVAILABLE": "不可计算", "DATA_LIMITED": "资料有限", "ANALYZED": "已分析", "NOT_ANALYZED": "未分析", "COMPLETE": "已完成", "PARTIAL": "部分覆盖", "SOURCE_COMPLETE_FOR_WINDOW": "来源已完整覆盖所选区间", "LIFETIME_RECONCILED": "历史材料已核对完整",
    "ALL_AVAILABLE": "全部已保存记录", "LEDGER_HISTORY": "全部已保存记录", "SNAPSHOT_WINDOW": "冻结区间", "EXPLICIT_SUBSET": "指定成交", "RECORD_SUBSET": "指定成交", "AVAILABLE_EPISODES_ONLY": "仅可计算片段",
    "STOCK": "股票", "ETF": "ETF", "OPTION": "期权", "BUY": "买入", "SELL": "卖出", "FILL": "成交", "OPEN": "开仓", "CLOSE": "平仓", "LONG": "多头", "SHORT": "空头", "CALL": "看涨", "PUT": "看跌", "STANDARD": "标准合约", "ADJUSTED": "调整合约", "EXERCISE": "行权", "ASSIGNMENT": "指派", "EXPIRY": "到期", "TRANSFER": "转仓", "CORPORATE_ACTION": "公司行动", "FEE": "费用",
    "CASH": "资金活动", "TAX": "税费", "ORDER": "委托", "NON_STANDARD": "非标准合约",
    "ACCOUNT_START_UNKNOWN": "开户起点尚未核实",
    "US": "美国", "USA": "美国", "HK": "香港", "HONG_KONG": "香港", "HKEX": "香港交易所", "NYSE": "纽约证券交易所", "NASDAQ": "纳斯达克",
    "custom": "自选日期", "week": "一周", "month": "一个月", "half_year": "半年", "year": "一年", "lifetime": "原历史请求区间",
    "ENTRY": "入场", "ADJUSTMENT": "加减仓", "EXIT": "退出", "HOLDING": "持有", "RISK_EXPOSURE": "可见风险暴露", "POSITIVE_RESULT": "盈利片段", "NEGATIVE_RESULT": "亏损片段", "BOUNDARY": "资料边界片段", "PROPOSED": "待实践", "IN_PROGRESS": "实践中", "COMPLETED": "已实践", "REVIEWED": "已复查",
    "SECOND": "精确到秒", "MINUTE": "精确到分钟", "DATE": "仅日期", "DATE_ONLY": "仅日期", "UNDETERMINED": "日期尚未确定", "DETERMINED": "已确定交易所日期", "SOURCE_DATE_UNCERTAIN": "来源日期，交易所日期不确定", "SOURCE_DATE": "来源日期", "EXCHANGE_DATE": "交易所日期", "REGULAR": "常规交易时段", "PRE_MARKET": "盘前", "AFTER_HOURS": "盘后", "SESSION_UNVERIFIED": "交易时段未核验", "TIME_ONLY": "仅时间定位", "SOURCE_DATE_TIME_ONLY": "按来源日期定位", "UNDERLYING_TIME_ONLY": "在标的图上仅作时间定位", "ORIGINAL_PRICE": "券商原始成交价", "UNADJUSTED": "不复权", "ADJUSTED_PRICE": "复权价格", "ADJUSTED_WITH_FACTORS": "按已核验因子复权", "RAW": "原始价格", "SPLIT": "拆股", "DIVIDEND": "现金分配", "SYMBOL_CHANGE": "代码变更",
    "contemporaneous": "当时可知", "outcome": "事后资料", "uncertain": "时点不确定", "AT_TIME": "当时记录", "RETROSPECTIVE": "事后补写", "RECORDED_AT_TIME": "有当时记录", "ACTUAL_USER_INTENT": "用户记录的原始意图", "INFERRED": "推测，未获当时记录支持", "AVAILABLE_AT": "资料可用时刻", "EVENT_AT": "事件发生时刻", "UNPLACED": "缺少可靠定位时刻",
    "ORIGINAL_RELEASE": "原始发布版本", "PIT_VERIFIED": "已核验当时版本", "REVISED": "修订版本", "SEARCH_INDEX_ONLY": "仅搜索索引，原文尚未核验", "COMPANY_EVENT": "公司事件", "MACRO": "宏观资料", "MACRO_OBSERVATION": "宏观资料", "ECONOMIC_SERIES": "经济序列", "DAILY_OHLCV": "日线行情", "DAILY_CLOSE": "日线收盘", "INDEX": "指数资料", "PRODUCT_TERMS": "产品条款", "OPTION_EDUCATION": "期权资料", "OPTIONS_EDUCATION": "期权资料", "COMPANY_ACTION": "公司行动", "DETERMINISTIC_EPISODE": "交易片段计算", "DETERMINISTIC_CURRENCY_SUMMARY": "原币种汇总", "COUNTERFACTUAL_HOLD": "延期退出情景计算",
    "COMPUTER_USE_EXPORT": "通过官方界面导出", "VERIFIED_DESKTOP": "已核验客户端读取", "USER_IMPORT": "用户提供文件", "SYNTHETIC": "虚构检查材料", "GUI_EXPORT": "客户端导出", "MANUAL_IMPORT": "用户提供文件",
    "OPENING_POSITION_UNKNOWN": "期初仓位未知", "OPENING_COST_UNKNOWN": "期初成本未知", "OPENING_TIME_UNKNOWN": "期初时刻未知", "TIME_PRECISION_INSUFFICIENT": "时间精度不足", "FEES_INCOMPLETE": "费用不完整", "FEES_UNRECONCILED": "费用尚未核对", "OPTION_LIFECYCLE_UNDERLYING_POSITION_UNCERTAIN": "期权生命周期影响的标的仓位不确定", "LIFECYCLE_OR_POSITION_CHANGE_UNRECONCILED": "生命周期或仓位变动尚未核对", "NOT_AN_EXECUTION": "不是成交", "INCOMPLETE_EXECUTION": "成交字段不完整", "CURRENCY_UNKNOWN": "币种未知", "INSTRUMENT_IDENTITY_INCOMPLETE": "证券身份不完整", "MULTIPLIER_UNKNOWN": "乘数未知", "OPTION_IDENTITY_INCOMPLETE": "期权合约信息不完整", "OPTION_ADJUSTMENT_UNKNOWN": "期权调整状态未知", "DUPLICATE_IDENTITY_UNCERTAIN": "是否重复成交尚未确定", "SAME_TIME_SEQUENCE_UNCERTAIN": "同一时刻的成交顺序不确定", "POSITION_EFFECT_CONFLICT": "开平仓信息冲突", "WINDOW_BOUNDARY_TIME_UNCERTAIN": "区间边界成交时刻不确定", "CLOSE_EXCEEDS_KNOWN_POSITION": "平仓数量超出已知仓位", "SELL_NOT_PROVEN_SHORT_OPEN": "无法证明卖出属于开空仓", "ACCOUNT_OPEN_DATE_UNKNOWN": "开户起点未知", "OPENING_DATE_UNKNOWN": "开户起点未知", "LIFETIME_START_UNKNOWN": "开户起点未知", "SOURCE_WINDOW_CLIPPED": "来源返回范围小于请求范围", "SOURCE_RANGE_INCOMPLETE": "来源范围不完整", "NO_MARKET_DATA": "没有可靠行情", "NO_RELIABLE_MARKET_DATA": "没有可靠行情", "MARKET_DATA_UNAVAILABLE": "行情不可得", "MISSING_OHLCV": "缺少日线行情", "UNSUPPORTED_MARKET": "行情来源不支持此市场", "HISTORY_START_UNKNOWN": "历史起点未知", "OPTION_LIFECYCLE_INCOMPLETE": "期权生命周期材料不完整",
    "PUBLICATION_DATE_ONLY_NOT_INTRADAY_VERIFIED": "仅有发布日期，日内发布时刻未核验",
    "ORIGINAL_PUBLICATION_TIME_UNKNOWN": "原始发布时刻未知",
    "OFFICIAL_PAGE_EXPLICIT_RELEASE_TIMESTAMP": "官方页面明确提供发布时刻",
    "SEARCH_INDEX_ONLY_BODY_UNAVAILABLE_NO_RELEASE_TIME": "仅取得搜索索引，原文不可得且发布时刻未知",
    "OFFICIAL_BODY_DATE_ONLY_RELEASE_TIME_UNKNOWN": "官方原文仅提供日期，发布时刻未知",
    "CURRENT_OFFICIAL_CALENDAR_EVENT_TIME_IS_NOT_PUBLICATION_TIME": "现有官方日历给出事件时刻，不能作为资料发布时刻",
    "CURRENT_OFFICIAL_RETROSPECTIVE_PAGE_PUBLICATION_UNKNOWN": "现有官方回顾页面的发布时间未知",
    "DOCUMENT_DATE_ONLY_PRECISE_PUBLIC_AVAILABILITY_NOT_VERIFIED": "文档仅提供日期，精确公开可用时刻未核验",
    "PRODUCT_DEFINITION": "产品定义",
    "CURRENT_PAGE_HISTORICAL_VERSION_NOT_VERIFIED": "当前页面对应的历史版本未核验",
    "HISTORICAL_DAILY_BAR_AVAILABILITY_NOT_VERIFIED": "历史日线当时的可用时刻未核验",
    "PRICE_BASIS_UNVERIFIED": "价格是否复权尚未核验",
    "SESSION_CALENDAR_UNAVAILABLE": "交易时段日历不可得",
    "DAILY_BAR_AVAILABILITY_UNKNOWN": "日线资料可用时刻未知",
    "FETCHED": "已取得",
    "CONTEXT_SHORT": "前置行情不足",
}

_FIELDS = {
    "status": "状态", "mode": "范围", "kind": "类别", "reason": "原因", "reasons": "原因", "message": "说明", "detail": "说明", "limitations": "限制", "gaps": "缺口", "code": "缺口", "start": "开始", "end": "截止", "actual_start": "实际开始", "actual_end": "实际截止", "requested_window": "请求区间", "requested_range": "请求区间", "requested": "请求范围", "available": "实际可得", "asset_type": "资产类别", "asset_types": "资产类别", "timezone": "时区", "boundary": "日期边界", "end_at": "截止时刻", "start_at": "开始时刻", "date": "日期", "cutoff": "资料截止", "report_as_of": "报告时刻", "as_of": "资料截止", "retrieved_at": "取得时刻", "available_at": "可用时刻", "published_at": "发布时间", "event_at": "事件时刻", "anchor_at": "定位时刻", "anchor_role": "定位依据", "layer": "资料时点", "precision": "精度", "publication_precision": "发布精度", "time_precision": "成交精度", "availability_basis": "可用时刻依据", "vintage_status": "历史资料状态", "vintage_available_at": "历史资料可用时刻", "title": "标题", "content": "内容", "source_url": "公开出处", "observations": "来源覆盖", "collection_mode": "取得方式", "total_units": "分析单元数", "quantity": "数量", "closed_quantity": "闭合数量", "price": "成交价", "fees": "费用", "gross_pnl": "毛盈亏", "net_pnl": "净盈亏", "holding_seconds": "持有秒数", "hypothetical_net_pnl": "情景净盈亏", "difference_net_pnl": "情景净盈亏差额", "currency": "原币种", "available_episodes": "可计算片段", "unavailable_episodes": "不可计算片段", "aggregation_scope": "汇总范围", "metrics": "计算结果", "by_currency": "按原币种统计", "assumptions": "计算假设", "method": "资料方法", "read_chart": "怎样读图", "why_it_matters": "为何值得关注", "possible_error": "可能的问题", "exercise": "练习", "next_inputs": "下次记录", "verification": "复查方式", "alternative_explanation": "替代解释", "falsifier": "推翻条件", "additional_evidence": "需要补充的证据", "review_window": "复查窗口", "term": "术语", "meaning": "含义", "case_application": "本案含义", "numerator": "变更后份数", "denominator": "变更前份数", "amount": "金额", "event_type": "公司行动", "side": "买卖", "occurred_at": "成交时刻", "symbol": "证券", "underlying": "标的", "strike": "行权价", "expiry": "到期日", "right": "期权类别", "multiplier": "乘数", "adjustment_status": "合约调整", "position_effect": "开平仓", "record_refs": "成交", "record_id": "成交", "episode_refs": "交易片段", "episode_id": "交易片段", "evidence_refs": "资料", "evidence_id": "资料", "finding_refs": "案例", "finding_ref": "案例", "calculation_ref": "计算", "relevance_note": "本案关联", "layers": "逐笔资料时点", "window": "区间", "period": "期间", "requested_at": "请求时刻", "open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量", "price_basis": "价格口径",
}

_HIDDEN_KEYS = {"account", "account_ref", "account_id", "account_number", "account_name", "raw", "raw_row", "raw_content", "source_path", "credentials", "cookies", "token", "password", "client", "source_id", "schema_version", "model_version", "skill_version", "formula_version", "snapshot_id", "report_id", "packet_hash", "input_hash", "snapshot_hash", "content_hash", "revision", "id", "key", "instrument_key", "focus_instrument_key", "journal_path", "json_path", "packet_path", "markdown_path", "review_path"}
_UNKNOWN_REFERENCE = r"(?<![A-Za-z0-9_.:-])(?:(?:episode:)?episode-[A-Za-z0-9_.:-]+|(?:activity|chart|summary|counterfactual):[A-Za-z0-9_.:/-]+|(?:record|trade|reflection|snapshot|evidence|finding|practice|improvement|source|packet|calculation|calc)-[A-Za-z0-9_.:-]+)(?![A-Za-z0-9_.:-])"
_PRIVATE_PATH = r"(?:file://[^\s<>，；、）)\]]+|/(?:Users|home|tmp|private|var)/[^\s<>，；、）)\]]+|(?:product/)?\.private/[^\s<>，；、）)\]]+)"
_PUBLIC_URL = re.compile(r"https?://[^\s<>，；、）)\]]+")


def _code(value: Any) -> str:
    text = str(value)
    if text in _CODES:
        return _CODES[text]
    if re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+", text):
        return "资料说明暂未提供"
    return text


def _symbol(record: Mapping[str, Any]) -> str:
    instrument = record.get("instrument") or {}
    return str(instrument.get("symbol") or instrument.get("underlying") or "证券信息未提供")


def record_label(record: Mapping[str, Any]) -> str:
    """A stable business caption, without using the record's technical identity."""
    clock = record.get("local_time") or record.get("occurred_at") or record.get("display_date") or "时刻未知"
    clock = str(clock).replace("T", " ")
    side = _code(record.get("side") or record.get("activity_type") or "UNKNOWN")
    quantity = record.get("quantity")
    return " · ".join([_symbol(record), clock, side] + ([f"{quantity}份"] if quantity is not None else []))


def build_reader_labels(packet: Mapping[str, Any] | None = None, report: Mapping[str, Any] | None = None, records: Iterable[Mapping[str, Any]] | None = None) -> dict[str, str]:
    """Map declared references to business captions, without modifying sources."""
    packet, report = packet or {}, report or {}
    snapshot = packet.get("snapshot") or {}
    rows = [*(snapshot.get("records") or []), *(snapshot.get("context_records") or []), *(records or [])]
    labels: dict[str, str] = {}

    def add(identifier: Any, label: str) -> None:
        if isinstance(identifier, str) and identifier:
            labels[identifier] = label

    for row in rows:
        add(row.get("record_id"), record_label(row))
        add(row.get("source_id"), "券商成交资料")
        instrument = row.get("instrument") or {}
        add(instrument.get("key"), _symbol(row))
    for episode in packet.get("episodes", []):
        refs = episode.get("record_refs") or [episode.get("opening_record_id"), episode.get("closing_record_id")]
        caption = " → ".join(labels.get(ref, "仓位来源资料待补充") for ref in refs if ref)
        add(episode.get("episode_id"), "交易片段：" + (caption or "配对资料待补充"))
    for identifier, calculation in (packet.get("calculations") or {}).items():
        episode = calculation.get("episode_id")
        add(identifier, (labels.get(episode, "交易片段") + "的计算") if episode else f"{calculation.get('currency') or '原币种'}统计计算")
        add(calculation.get("source_id"), "确定性计算资料")
    for index, item in enumerate(packet.get("evidence", []), 1):
        title = item.get("title") or f"{_code(item.get('kind') or 'UNKNOWN')} {index}"
        add(item.get("evidence_id"), str(title))
        source = item.get("source_url")
        try:
            host = urlsplit(source).hostname if isinstance(source, str) else None
        except ValueError:
            host = None
        add(item.get("source_id"), host or "已保存公开资料")
    for index, item in enumerate(packet.get("diary", []), 1):
        add(item.get("diary_id"), f"交易日记 {index} · {item.get('recorded_at') or '记录时刻未知'}")
        add(item.get("source_id"), "用户交易日记")
    for index, item in enumerate(report.get("findings", []), 1):
        add(item.get("finding_id"), str(item.get("pattern") or f"复盘案例 {index}"))
    for index, item in enumerate(report.get("improvement_plan", []), 1):
        add(item.get("improvement_id"), str(item.get("title") or item.get("exercise") or f"改进练习 {index}"))
    for index, ref in enumerate(packet.get("chart_refs", []), 1):
        add(ref, f"已保存交易图表 {index}")
    # The limited web review contains these references without whole episodes.
    for finding in report.get("findings", []):
        related = " → ".join(labels.get(ref, "成交资料待补充") for ref in finding.get("record_refs", []))
        for field, caption in (("episode_refs", "本案交易片段：" + related), ("chart_refs", "本案交易图表"), ("calculation_refs", "本案片段计算"), ("diary_refs", "当时记录（日记原件未展示）")):
            for ref in finding.get(field, []):
                if ref not in labels:
                    add(ref, caption)
        for alternative in finding.get("alternative_explanations", []):
            related = " → ".join(labels.get(ref, "成交资料待补充") for ref in alternative.get("record_refs", []))
            for ref in alternative.get("episode_refs", []):
                if ref not in labels:
                    add(ref, "反例交易片段：" + related)
    for owner in (snapshot, packet, report):
        for key, value in owner.items():
            if key.endswith("_hash"):
                add(value, "已保存资料")
            elif key in {"snapshot_id", "report_id", "source_id"}:
                add(value, "已保存资料")
            elif key in {"model_version", "skill_version", "formula_version"} and isinstance(value, str) and len(value) > 5:
                add(value, "已保存资料")
    def declared_metadata(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if isinstance(item, str) and item not in labels:
                    if key.endswith("_hash") or key in {"source_id", "account_ref", "snapshot_id", "report_id"}:
                        add(item, "已保存资料")
                    elif key.endswith("_path"):
                        add(item, "本地资料")
                    elif key in {"model_version", "skill_version", "formula_version"} and re.search(r"[A-Za-z]", item):
                        add(item, "已保存核算口径" if key == "formula_version" else "已保存资料")
                if isinstance(item, (Mapping, list)):
                    declared_metadata(item)
        elif isinstance(value, list):
            for item in value:
                declared_metadata(item)
    declared_metadata(packet)
    declared_metadata(report)
    return labels


def readable_text(value: Any, labels: Mapping[str, str] | None = None) -> str:
    """Convert one reader value to prose while preserving business facts."""
    labels = labels or {}
    if value is None:
        return "未知"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple)):
        return "；".join(readable_text(item, labels) for item in value) or "无"
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            if key in _HIDDEN_KEYS or key.endswith("_hash") or key.endswith("_path") or key.endswith("_version"):
                continue
            caption = _FIELDS.get(key) or (key if re.search(r"[\u4e00-\u9fff]", str(key)) else None)
            if caption:
                parts.append(f"{caption}：{readable_text(item, labels)}")
        return "；".join(parts) or "资料说明暂未提供"
    text = str(value)
    urls: list[str] = []
    def protect(match: re.Match) -> str:
        urls.append(match.group())
        return "\x00" + chr(0xE000 + len(urls) - 1) + "\x00"
    text = _PUBLIC_URL.sub(protect, text)
    def known_reference(match: re.Match) -> str:
        token = match.group()
        if re.fullmatch(r"\d+(?:\.\d+)?", token.rstrip(".")):
            return token
        if token in labels:
            return str(labels[token])
        stem = token.rstrip(".")
        return str(labels[stem]) + token[len(stem):] if stem in labels else token
    text = re.sub(r"[A-Za-z0-9_][A-Za-z0-9_.:/-]*", known_reference, text)
    # A business title can itself contain a public URL. Protect those inserted
    # labels as well before matching local paths or protocol terms.
    text = _PUBLIC_URL.sub(protect, text)
    text = re.sub(_PRIVATE_PATH, "本地资料", text)
    text = re.sub(_UNKNOWN_REFERENCE, "引用资料暂不可展示", text)
    # Known field names can occur inside saved research paragraphs as well.
    def translated_token(match: re.Match) -> str:
        token = match.group()
        stem = token.rstrip(".")
        if stem in _CODES or stem in _FIELDS:
            return _CODES.get(stem, _FIELDS.get(stem, stem)) + token[len(stem):]
        if re.fullmatch(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+", stem):
            return "资料说明暂未提供" + token[len(stem):]
        return token
    text = re.sub(r"[A-Za-z0-9_][A-Za-z0-9_.:/-]*", translated_token, text)
    for index, url in enumerate(urls):
        text = text.replace("\x00" + chr(0xE000 + index) + "\x00", url)
    return text


def reader_script(labels: Mapping[str, str] | None = None) -> str:
    """Pure text helpers for the existing native-JavaScript readers."""
    def encoded(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    config = {"labels": dict(labels or {}), "codes": _CODES, "fields": _FIELDS, "hidden": sorted(_HIDDEN_KEYS), "references": _UNKNOWN_REFERENCE, "paths": _PRIVATE_PATH}
    return "const JR_READER=" + encoded(config) + r''';
const jrReaderWords={...JR_READER.codes,...JR_READER.fields};
function jrCode(value){if(value==null)return "未知";const s=String(value);return Object.hasOwn(JR_READER.codes,s)?JR_READER.codes[s]:(/^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/.test(s)?"资料说明暂未提供":s)}
function jrRegisterLabel(id,label){if(typeof id==="string"&&id)Object.defineProperty(JR_READER.labels,id,{value:String(label),writable:true,enumerable:true,configurable:true})}
function jrRecordLabel(record){const i=record.instrument||{},clock=record.local_time||record.occurred_at||record.display_date||"时刻未知";return [i.symbol||i.underlying||"证券信息未提供",String(clock).replace("T"," "),jrCode(record.side||record.activity_type||"UNKNOWN"),...(record.quantity==null?[]:[record.quantity+"份"])].join(" · ")}
function jrRefLabel(id){return jrReadable(JR_READER.labels[id]||"引用资料暂不可展示")}
function jrReadable(value){
 if(value==null)return "未知";
 if(typeof value==="boolean")return value?"是":"否";
 if(Array.isArray(value))return value.map(jrReadable).join("；")||"无";
 if(typeof value==="object"){const parts=[];for(const[k,v]of Object.entries(value)){if(JR_READER.hidden.includes(k)||/_(?:hash|path|version)$/.test(k))continue;const caption=Object.hasOwn(JR_READER.fields,k)?JR_READER.fields[k]:(/[\u4e00-\u9fff]/.test(k)?k:null);if(caption)parts.push(caption+"："+jrReadable(v))}return parts.join("；")||"资料说明暂未提供"}
 const urls=[];let s=String(value).replace(/https?:\/\/[^\s<>，；、）)\]]+/g,u=>{urls.push(u);return "\u0000"+String.fromCodePoint(0xE000+urls.length-1)+"\u0000"});
 s=s.replace(/[A-Za-z0-9_][A-Za-z0-9_.:/-]*/g,token=>{const stem=token.replace(/\.+$/,"");if(/^\d+(?:\.\d+)?$/.test(stem))return token;if(Object.hasOwn(JR_READER.labels,token))return JR_READER.labels[token];return Object.hasOwn(JR_READER.labels,stem)?JR_READER.labels[stem]+token.slice(stem.length):token});
 s=s.replace(/https?:\/\/[^\s<>，；、）)\]]+/g,u=>{urls.push(u);return "\u0000"+String.fromCodePoint(0xE000+urls.length-1)+"\u0000"});
 s=s.replace(new RegExp(JR_READER.paths,"g"),"本地资料").replace(new RegExp(JR_READER.references,"g"),"引用资料暂不可展示");
 s=s.replace(/[A-Za-z0-9_][A-Za-z0-9_.:/-]*/g,word=>{const stem=word.replace(/\.+$/,"");return Object.hasOwn(jrReaderWords,stem)?jrReaderWords[stem]+word.slice(stem.length):/^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/.test(stem)?"资料说明暂未提供"+word.slice(stem.length):word});
 return s.replace(/\u0000([^\u0000])\u0000/gu,(_,i)=>urls[i.codePointAt(0)-0xE000]);
}
'''


def render_markdown(report: Mapping[str, Any], packet: Mapping[str, Any] | None = None) -> str:
    """Reader-facing alias; the immutable report module owns field projection."""
    from .reflection import render_markdown as render
    return render(report, packet)
