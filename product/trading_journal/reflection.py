"""Frozen, point-in-time inputs and immutable outputs for personal reflection.

No network or model is called here. This module validates transport and citations;
the current conversation's LLM owns interpretation and selection of evidence.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = "1.0.0"
LESSON_REPORT_VERSION = "1.1.0"
PHASES = ("ENTRY", "ADJUSTMENT", "EXIT", "HOLDING", "RISK_EXPOSURE")
_IDENTITY = re.compile(r"^[A-Za-z0-9_.:-]{1,200}$")
_FINANCIAL_FIELDS = ("quantity", "gross_pnl", "fees", "net_pnl", "holding_seconds")


class ReflectionError(ValueError):
    pass


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ReflectionError("反思输入必须为有限值 JSON") from exc


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _time(value: str, field: str) -> datetime:
    if not isinstance(value, str) or len(value) <= 10:
        raise ReflectionError(f"{field} 需要含时区的精确时刻")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReflectionError(f"{field} 不是 ISO 时刻") from exc
    if result.tzinfo is None:
        raise ReflectionError(f"{field} 缺少时区")
    return result.astimezone(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _provenance(value: Mapping[str, Any], label: str) -> None:
    for key in ("source_id", "as_of", "retrieved_at"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ReflectionError(f"{label} 缺少 {key}")
    if len(value["as_of"]) == 10:
        try:
            date.fromisoformat(value["as_of"])
        except ValueError as exc:
            raise ReflectionError(f"{label}.as_of 日期无效") from exc
    else:
        _time(value["as_of"], f"{label}.as_of")
    _time(value["retrieved_at"], f"{label}.retrieved_at")


def _unique(items: Iterable[Mapping[str, Any]], field: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise ReflectionError(f"{label} 需要对象")
        identifier = item.get(field)
        if not isinstance(identifier, str) or not _IDENTITY.fullmatch(identifier):
            raise ReflectionError(f"{label} 的 {field} 无效")
        if identifier in result:
            raise ReflectionError(f"{label} 的 {field} 重复")
        result[identifier] = deepcopy(dict(item))
    return result


def _evidence_layer(evidence: Mapping[str, Any], record: Mapping[str, Any]) -> tuple[str, str]:
    available = evidence.get("available_at", evidence.get("published_at"))
    basis = evidence.get("availability_basis", evidence.get("available_at_basis"))
    if not basis or not isinstance(available, str) or len(available) <= 10:
        return "uncertain", "未证明日内可用时刻"
    if evidence.get("publication_precision", "SECOND") not in {"SECOND", "MINUTE"} or record.get("time_precision") == "DATE":
        return "uncertain", "仅日期精度，无法确定交易时可用性"
    try:
        released = _time(available, "available_at")
        traded = _time(record["occurred_at"], "occurred_at")
    except ReflectionError:
        return "uncertain", "可用时刻或成交时刻不能精确恢复"
    if released > traded:
        return "outcome", "资料在成交后可用"
    if evidence.get("kind", "").upper() in {"MACRO", "MACRO_OBSERVATION", "ECONOMIC_SERIES"}:
        if evidence.get("vintage_status") not in {"ORIGINAL_RELEASE", "PIT_VERIFIED"}:
            return "uncertain", "宏观历史发布版本未知或已修订"
        vintage_at = evidence.get("vintage_available_at")
        if not vintage_at:
            return "uncertain", "缺少历史发布版本的可用时刻"
        try:
            if _time(vintage_at, "vintage_available_at") > traded:
                return "outcome", "宏观版本在成交后发布"
        except ReflectionError:
            return "uncertain", "宏观版本时刻不确定"
    if evidence.get("revised", False):
        return "uncertain", "不能把修订值作为原始观察"
    if evidence.get("kind", "").upper() in {"DAILY_OHLCV", "DAILY_CLOSE"}:
        session_close = evidence.get("session_close_at")
        if not session_close:
            return "uncertain", "日 K 缺少完整交易时段收盘时刻"
        try:
            if _time(session_close, "session_close_at") > traded:
                return "outcome", "成交时当日日 K 尚未完成"
        except ReflectionError:
            return "uncertain", "收盘时刻不确定"
    return "contemporaneous", "可用时刻和历史版本不晚于成交"


def _financial_class(episode: Mapping[str, Any]) -> str:
    if episode.get("status") != "AVAILABLE" or episode.get("net_pnl") is None:
        return "BOUNDARY"
    try:
        pnl = Decimal(str(episode["net_pnl"]))
    except InvalidOperation as exc:
        raise ReflectionError("确定性 episode 的 net_pnl 非数值") from exc
    if not pnl.is_finite():
        raise ReflectionError("确定性 episode 的 net_pnl 非有限值")
    return "POSITIVE_RESULT" if pnl > 0 else "NEGATIVE_RESULT" if pnl < 0 else "BOUNDARY"


def _validate_snapshot_analysis(snapshot: Mapping[str, Any]) -> None:
    """Reproduce financial output from its frozen records, not a caller hash."""
    from .analysis import FORMULA_VERSION, analyze_records

    analysis = snapshot.get("analysis")
    if not isinstance(analysis, Mapping) or analysis.get("formula_version") != FORMULA_VERSION:
        raise ReflectionError("快照需要受支持的确定性金融计算")
    scope = analysis.get("scope")
    if not isinstance(scope, Mapping):
        raise ReflectionError("确定性计算缺少实际输入范围")
    window = snapshot.get("coverage", {}).get("requested_window")
    if scope.get("window") != window:
        raise ReflectionError("确定性计算窗口与快照覆盖不一致")
    try:
        expected = analyze_records(
            list(snapshot.get("records", [])) + list(snapshot.get("context_records", [])),
            window=window, opening_positions=snapshot.get("opening_positions", {}),
            history_complete=snapshot.get("coverage", {}).get("status") == "LIFETIME_RECONCILED",
        )
    except ValueError as exc:
        raise ReflectionError("冻结事实不能复现确定性金融计算") from exc
    # retrieved_at is calculation execution time; every substantive field,
    # source/record identity, episode, exclusion and limitation must reproduce.
    comparable = lambda value: {key: item for key, item in value.items() if key != "retrieved_at"}
    if comparable(expected) != comparable(analysis):
        raise ReflectionError("快照金融计算不能由冻结事实复现")


def prepare_reflection(
    snapshot: Mapping[str, Any], *, evidence: Iterable[Mapping[str, Any]] = (),
    diary: Iterable[Mapping[str, Any]] = (), cutoff: str | None = None,
    selected_record_ids: Iterable[str] | None = None, batch_size: int = 20,
    analyzed_episode_ids: Iterable[str] = (), selection_reasons: Mapping[str, str] | None = None,
    chart_refs: Iterable[str] = (),
) -> dict[str, Any]:
    """Freeze all available facts; explicit subsets and unfinished units stay visible."""
    if snapshot.get("kind") != "TradeJournalSnapshot" or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ReflectionError("不是受支持的 TradeJournalSnapshot")
    if not snapshot.get("snapshot_id") or not snapshot.get("input_hash"):
        raise ReflectionError("快照缺少 snapshot_id/input_hash")
    input_fields = ["records", "coverage", "analysis", "market"] + [key for key in ("context_records", "opening_positions") if key in snapshot]
    if snapshot["input_hash"] != _hash({key: snapshot.get(key) for key in input_fields}):
        raise ReflectionError("账本 input_hash 与实际输入不一致")
    _validate_snapshot_analysis(snapshot)
    _provenance(snapshot, "snapshot")
    cutoff = cutoff or snapshot["as_of"]
    cutoff_time = _time(cutoff, "cutoff")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ReflectionError("batch_size 必须为正整数")
    records = _unique(snapshot.get("records", []), "record_id", "records")
    context_records = _unique(snapshot.get("context_records", []), "record_id", "context_records")
    if set(records) & set(context_records):
        raise ReflectionError("样本和上下文记录 ID 重复")
    all_records = {**context_records, **records}
    if not records:
        raise ReflectionError("没有已保存交易，请先采集")
    for record in all_records.values():
        _provenance(record, "record")
        if record.get("time_precision") not in {"SECOND", "MINUTE", "DATE"}:
            raise ReflectionError("成交时间精度缺失或未知")
        if record.get("time_precision") != "DATE" and _time(record["occurred_at"], "occurred_at") > cutoff_time:
            raise ReflectionError("快照包含 cutoff 后成交")
        if record.get("time_precision") == "DATE":
            try:
                local_day = cutoff_time.astimezone(ZoneInfo(record.get("source_timezone") or record.get("instrument", {}).get("exchange_timezone", "UTC"))).date()
                if date.fromisoformat(record["occurred_at"]) > local_day:
                    raise ReflectionError("快照包含 cutoff 后日期记录")
            except (ValueError, ZoneInfoNotFoundError) as exc:
                raise ReflectionError("日期记录或来源时区无效") from exc
    chosen = set(records) if selected_record_ids is None else set(selected_record_ids)
    if not chosen or not chosen <= set(records):
        raise ReflectionError("交易子集为空或引用不存在")
    public = _unique(evidence, "evidence_id", "evidence")
    journals = _unique(diary, "diary_id", "diary")
    for material in public.values():
        _provenance(material, "evidence")
        if _time(material["retrieved_at"], "evidence.retrieved_at") > cutoff_time:
            raise ReflectionError("公开资料检索时刻超过复盘 cutoff")
        if "record_refs" in material:
            _refs(material["record_refs"], set(all_records), "evidence.record_refs")
        available = material.get("available_at", material.get("published_at"))
        if isinstance(available, str) and len(available) > 10:
            try:
                available_time = _time(available, "evidence.available_at")
            except ReflectionError:
                available_time = None
            if available_time is not None and available_time > cutoff_time:
                raise ReflectionError("公开资料发布超过冻结 cutoff")
    for item in journals.values():
        _provenance(item, "diary")
        if _time(item.get("recorded_at"), "diary.recorded_at") > cutoff_time or _time(item["retrieved_at"], "diary.retrieved_at") > cutoff_time:
            raise ReflectionError("交易日记超出冻结 cutoff")
        if not set(item.get("record_refs", [])) <= set(all_records):
            raise ReflectionError("日记引用未知交易")
    layers: dict[str, Any] = {}
    for identifier in sorted(chosen):
        record = records[identifier]
        partition: dict[str, Any] = {"contemporaneous": [], "outcome": [], "uncertain": [], "diary_at_time": [], "diary_retrospective": [], "diary_uncertain": []}
        for evidence_id, material in public.items():
            applicable = material.get("record_refs")
            if applicable is not None and identifier not in applicable:
                continue
            layer, reason = _evidence_layer(material, record)
            partition[layer].append({"evidence_id": evidence_id, "reason": reason})
        for diary_id, item in journals.items():
            if identifier not in item.get("record_refs", []):
                continue
            if record.get("time_precision") == "DATE":
                partition["diary_uncertain"].append(diary_id)
            elif _time(item["recorded_at"], "diary.recorded_at") <= _time(record["occurred_at"], "occurred_at"):
                partition["diary_at_time"].append(diary_id)
            else:
                partition["diary_retrospective"].append(diary_id)
        partition["original_intent_status"] = "RECORDED_AT_TIME" if partition["diary_at_time"] else "UNKNOWN"
        layers[identifier] = partition
    analysis = deepcopy(dict(snapshot.get("analysis") or {}))
    if analysis:
        _provenance(analysis, "analysis")
    episodes = _unique(analysis.get("episodes", []), "episode_id", "episodes")
    selected_episodes: dict[str, Any] = {}
    consumed: set[str] = set()
    for identifier, episode in episodes.items():
        refs = {episode.get("opening_record_id"), episode.get("closing_record_id")} - {None}
        if refs & chosen:
            episode["record_refs"] = sorted(refs)
            episode["missing_context_record_ids"] = sorted(refs - set(all_records))
            episode["selection_class"] = _financial_class(episode)
            episode["crosses_scope"] = not refs <= chosen
            selected_episodes[identifier] = episode
            consumed.update(refs & chosen)
    # Unpaired fills and lifecycle facts are review units too; no silent removal.
    for identifier in sorted(chosen - consumed):
        selected_episodes[f"activity:{identifier}"] = {"episode_id": f"activity:{identifier}", "record_refs": [identifier], "selection_class": "BOUNDARY", "status": "UNAVAILABLE", "reasons": ["非闭合交易片段或独立活动，不能由盈亏归类"]}
    unit_ids = sorted(selected_episodes)
    completed = set(analyzed_episode_ids)
    if not completed <= set(unit_ids):
        raise ReflectionError("分析进度引用未知 episode")
    reasons = dict(selection_reasons or {})
    if not set(reasons) <= set(unit_ids) or any(not isinstance(v, str) or not v.strip() for v in reasons.values()):
        raise ReflectionError("案例选择需要有效 episode 和明确理由")
    charts = list(chart_refs)
    if any(not isinstance(ref, str) or not ref.strip() for ref in charts):
        raise ReflectionError("图表引用必须是冻结产物标识")
    pending = [item for item in unit_ids if item not in completed]
    categories = {label: [identifier for identifier, ep in selected_episodes.items() if ep["selection_class"] == label] for label in ("POSITIVE_RESULT", "NEGATIVE_RESULT", "BOUNDARY")}
    calculations = {}
    for identifier, episode in selected_episodes.items():
        calculations[f"episode:{identifier}"] = {"kind": "DETERMINISTIC_EPISODE", "episode_id": identifier, "formula_version": analysis.get("formula_version"), "metrics": {field: episode.get(field) for field in _FINANCIAL_FIELDS}, "currency": episode.get("currency"), "status": episode.get("status"), "source_id": analysis.get("source_id", snapshot["source_id"]), "as_of": analysis.get("as_of", snapshot["as_of"]), "retrieved_at": analysis.get("retrieved_at", snapshot["retrieved_at"])}
    for index, summary in enumerate(analysis.get("by_currency", [])):
        calculations[f"summary:{index}"] = {"kind": "DETERMINISTIC_CURRENCY_SUMMARY", "metrics": deepcopy(summary), "formula_version": analysis.get("formula_version"), "source_id": analysis["source_id"], "as_of": analysis["as_of"], "retrieved_at": analysis["retrieved_at"]}
    snapshot_window = snapshot.get("coverage", {}).get("requested_window") or analysis.get("scope", {}).get("window")
    packet = {
        "kind": "TradingReflectionInput", "schema_version": SCHEMA_VERSION,
        "source_id": "trading-reflection:local-freeze", "as_of": cutoff, "retrieved_at": _now(),
        "snapshot_id": snapshot["snapshot_id"], "input_hash": snapshot["input_hash"], "snapshot_hash": _hash(snapshot),
        "cutoff": cutoff, "snapshot": deepcopy(dict(snapshot)), "evidence": list(public.values()), "diary": list(journals.values()),
        "scope": {"mode": "EXPLICIT_SUBSET" if selected_record_ids is not None else "SNAPSHOT_WINDOW" if snapshot_window else "ALL_AVAILABLE", "record_ids": sorted(chosen), "context_record_ids": sorted(context_records), "excluded_record_ids": sorted(set(records) - chosen), "coverage": deepcopy(snapshot.get("coverage", {})), "asset_types": sorted({record.get("instrument", {}).get("asset_type", "UNKNOWN") for record in records.values() if record["record_id"] in chosen}), "limitations": deepcopy(analysis.get("limitations", []))},
        "record_layers": layers, "episodes": list(selected_episodes.values()), "calculations": calculations, "chart_refs": charts,
        "preparation": {"selected_record_ids": None if selected_record_ids is None else sorted(chosen), "batch_size": batch_size, "analyzed_episode_ids": sorted(completed), "selection_reasons": reasons}, "counterfactual_requests": [],
        "whole_history_statistics": None if snapshot_window else deepcopy(analysis), "snapshot_statistics": deepcopy(analysis),
        "case_selection": {"available_by_result": categories, "selected_reasons": reasons, "omitted_classes": [label for label, ids in categories.items() if ids and not set(ids) & set(reasons)]},
        "progress": {"total_units": len(unit_ids), "analyzed_episode_ids": sorted(completed), "pending_episode_ids": pending, "batches": [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)], "status": "COMPLETE" if not pending else "PARTIAL"},
        "limitations": ["原始交易意图仅来自当时记录，事后补写保持独立。", "盈亏分类只描述确定性结果，不评定能力或过程质量。", "当时资料与事后资料分别引用；未知发布时间和宏观版本不作当时依据。", "工具契约校验不证明 LLM 内容质量。"],
    }
    packet["packet_hash"] = _hash(packet)
    return packet


def validate_packet(packet: Mapping[str, Any]) -> None:
    if packet.get("kind") != "TradingReflectionInput" or packet.get("schema_version") != SCHEMA_VERSION:
        raise ReflectionError("不支持的复盘输入")
    body = dict(packet)
    claimed = body.pop("packet_hash", None)
    if claimed != _hash(body):
        raise ReflectionError("复盘输入 packet_hash 不匹配")
    snapshot = packet["snapshot"]
    if _hash(snapshot) != packet["snapshot_hash"] or snapshot["input_hash"] != packet["input_hash"] or snapshot["snapshot_id"] != packet["snapshot_id"]:
        raise ReflectionError("复盘输入与冻结快照不一致")
    parameters = packet.get("preparation")
    if not isinstance(parameters, Mapping) or set(parameters) != {"selected_record_ids", "batch_size", "analyzed_episode_ids", "selection_reasons"}:
        raise ReflectionError("复盘输入缺少明确冻结参数")
    expected = prepare_reflection(
        snapshot, evidence=packet.get("evidence", []), diary=packet.get("diary", []),
        cutoff=packet.get("cutoff"), chart_refs=packet.get("chart_refs", []), **dict(parameters),
    )
    requests = packet.get("counterfactual_requests")
    if not isinstance(requests, list):
        raise ReflectionError("反事实输入请求必须为列表")
    expected["counterfactual_requests"] = deepcopy(requests)
    for request in requests:
        if not isinstance(request, Mapping) or set(request) != {"episode_id", "exit_date", "costs"}:
            raise ReflectionError("反事实请求字段无效")
        result = _counterfactual_hold(expected, **dict(request))
        expected["calculations"][result["calculation_ref"]] = result
    actual = deepcopy(dict(packet))
    expected.pop("packet_hash", None)
    actual.pop("packet_hash", None)
    expected.pop("retrieved_at", None)
    actual.pop("retrieved_at", None)
    parent_hash = actual.pop("parent_packet_hash", None)
    if parent_hash is not None and (not isinstance(parent_hash, str) or not re.fullmatch("[a-f0-9]{64}", parent_hash)):
        raise ReflectionError("父输入版本引用无效")
    for collection in (actual["calculations"], expected["calculations"]):
        for calculation in collection.values():
            if calculation.get("kind") == "DETERMINISTIC_COUNTERFACTUAL_HOLD":
                _time(calculation.get("retrieved_at"), "counterfactual.retrieved_at")
                calculation.pop("retrieved_at", None)
    if actual != expected:
        raise ReflectionError("复盘分层、统计或进度不能由冻结输入复现")


def compare_episodes(packet: Mapping[str, Any], episode_ids: Iterable[str]) -> dict[str, Any]:
    """Return sourced calculations side by side, without subjective scoring."""
    validate_packet(packet)
    ids = list(episode_ids)
    if len(set(ids)) != len(ids):
        raise ReflectionError("比较 episode 重复")
    calculations = packet["calculations"]
    if not ids or any(f"episode:{identifier}" not in calculations for identifier in ids):
        raise ReflectionError("比较引用未知 episode")
    return {"kind": "TradingEpisodeComparison", "schema_version": SCHEMA_VERSION, "input_hash": packet["input_hash"], "packet_hash": packet["packet_hash"], "source_id": "trading-reflection:deterministic-comparison", "as_of": packet["cutoff"], "retrieved_at": _now(), "items": [{"calculation_ref": f"episode:{identifier}", **deepcopy(calculations[f"episode:{identifier}"])} for identifier in ids], "limitations": ["按原币种展示，不跨币种加总；这是交易片段比较，不是反事实回测或因果证明。"]}


def _number(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise ReflectionError(f"{field} 必须为 Decimal 字符串")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ReflectionError(f"{field} 缺少有效数值") from exc
    if not result.is_finite() or result < 0 or positive and result <= 0:
        raise ReflectionError(f"{field} 需要有限且非负数值")
    return result


def _decimal_string(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def counterfactual_hold(
    packet: Mapping[str, Any], episode_id: str, *, exit_date: str, costs: Mapping[str, Any],
) -> dict[str, Any]:
    """Price one explicit hypothetical delayed exit from frozen stock/ETF facts.

    Completeness and price-basis proofs are mandatory. This is a per-fragment
    scenario with declared costs, never a strategy backtest or causal estimate.
    """
    validate_packet(packet)
    return _counterfactual_hold(packet, episode_id, exit_date=exit_date, costs=costs)


def _counterfactual_hold(
    packet: Mapping[str, Any], episode_id: str, *, exit_date: str, costs: Mapping[str, Any],
) -> dict[str, Any]:
    episodes = {episode["episode_id"]: episode for episode in packet["episodes"]}
    episode = episodes.get(episode_id)
    if not episode or episode.get("status") != "AVAILABLE" or episode.get("missing_context_record_ids"):
        raise ReflectionError("延期退出只支持来源完整、可计算的闭合片段")
    snapshot = packet["snapshot"]
    records = {record["record_id"]: record for record in snapshot["records"] + snapshot.get("context_records", [])}
    opening = records.get(episode.get("opening_record_id"))
    closing = records.get(episode.get("closing_record_id"))
    if not opening or not closing or opening.get("activity_type", opening.get("kind")) != "FILL" or closing.get("activity_type", closing.get("kind")) != "FILL":
        raise ReflectionError("延期退出缺少真实开仓/平仓成交，不能把期初仓位当作成交")
    instrument = opening.get("instrument", {})
    if instrument.get("asset_type") not in {"STOCK", "ETF"}:
        raise ReflectionError("期权不能用 underlying K 线做延期估值")
    if instrument.get("key") != closing.get("instrument", {}).get("key") or episode.get("instrument_key") != instrument.get("key"):
        raise ReflectionError("延期退出证券身份不一致")
    if opening.get("time_precision") == "DATE" or closing.get("time_precision") == "DATE":
        raise ReflectionError("延期退出缺少精确成交时刻")
    if opening.get("fees_complete") is not True or closing.get("fees_complete") is not True:
        raise ReflectionError("延期退出不能假设未知实际费用为零")
    currency = episode.get("currency")
    if not currency or currency != instrument.get("currency") or currency != closing.get("currency", closing.get("instrument", {}).get("currency")):
        raise ReflectionError("延期退出缺少一致的原币种")
    try:
        exit_day = date.fromisoformat(exit_date)
        zone = ZoneInfo(instrument["exchange_timezone"])
    except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError) as exc:
        raise ReflectionError("延期退出需要明确日期和交易所时区") from exc
    open_day = _time(opening["occurred_at"], "opening.occurred_at").astimezone(zone).date()
    close_day = _time(closing["occurred_at"], "closing.occurred_at").astimezone(zone).date()
    cutoff_time = _time(packet["cutoff"], "cutoff")
    if exit_day <= close_day or exit_day > cutoff_time.astimezone(zone).date():
        raise ReflectionError("延期日期必须晚于实际平仓日，且不晚于已知 cutoff")
    _provenance(costs, "counterfactual.costs")
    if set(costs) != {"source_id", "as_of", "retrieved_at", "currency", "complete", "assumptions", "exit_fees", "holding_costs", "cash_distributions"}:
        raise ReflectionError("成本假设字段不在固定允许范围")
    if costs.get("currency") != currency or costs.get("complete") is not True or not isinstance(costs.get("assumptions"), str) or not costs["assumptions"].strip():
        raise ReflectionError("延期退出需要同币种、完整且明确的成本/分配假设")
    if _time(costs["retrieved_at"], "counterfactual.costs.retrieved_at") > cutoff_time:
        raise ReflectionError("成本假设超出冻结 cutoff")
    packages = [market for market in snapshot.get("market", []) if market.get("instrument_key") == instrument["key"] and market.get("currency") == currency]
    if len(packages) != 1:
        raise ReflectionError("延期退出需要唯一且同币种的冻结行情")
    market = packages[0]
    _provenance(market, "counterfactual.market")
    if _time(market["retrieved_at"], "market.retrieved_at") > cutoff_time:
        raise ReflectionError("冻结行情检索超过 cutoff")
    market_hash = market.get("content_hash")
    if market_hash != _hash({key: value for key, value in market.items() if key != "content_hash"}):
        raise ReflectionError("冻结行情 content_hash 不匹配")
    proof = market.get("price_basis_evidence")
    if not isinstance(proof, Mapping):
        raise ReflectionError("延期退出缺少行情价格口径证明")
    _provenance(proof, "counterfactual.price_basis")
    if _time(proof["retrieved_at"], "price_basis.retrieved_at") > cutoff_time:
        raise ReflectionError("价格口径证明检索超过 cutoff")
    if proof.get("corporate_actions_complete") is not True or proof.get("identity_continuity_verified") is not True or proof.get("daily_bars_final_verified") is not True:
        raise ReflectionError("公司行动覆盖或证券身份连续性未知，不能延期强算")
    if market.get("price_basis") not in {"UNADJUSTED", "ADJUSTED_WITH_FACTORS"} or market.get("exchange_timezone") != instrument.get("exchange_timezone"):
        raise ReflectionError("行情价格口径或交易所时区不可靠")
    requested = market.get("requested_range", {})
    if requested.get("start", "9999") > open_day.isoformat() or requested.get("end", "0000") < exit_date:
        raise ReflectionError("冻结行情未覆盖完整反事实窗口")
    for gap in market.get("gaps", []):
        if not isinstance(gap, Mapping):
            raise ReflectionError("行情缺口格式未知")
        if gap.get("reason") == "CONTEXT_SHORT":
            continue
        if not gap.get("start") or not gap.get("end") or gap["start"] <= exit_date and gap["end"] >= open_day.isoformat():
            raise ReflectionError("反事实窗口存在行情或公司行动覆盖缺口")
    for activity in records.values():
        if activity.get("instrument", {}).get("key") != instrument["key"]:
            continue
        kind = activity.get("activity_type", activity.get("kind"))
        if kind in {"CORPORATE_ACTION", "TRANSFER", "EXERCISE", "ASSIGNMENT"}:
            occurred = activity["occurred_at"][:10] if activity.get("time_precision") == "DATE" else _time(activity["occurred_at"], "lifecycle.occurred_at").astimezone(zone).date().isoformat()
            if open_day.isoformat() <= occurred <= exit_date:
                raise ReflectionError("反事实窗口存在未建模的仓位/公司行动变化")
    for event in market.get("events", []):
        kind = str(event.get("type", event.get("kind", event.get("event_type", "")))).upper()
        if open_day.isoformat() <= str(event.get("date", "")) <= exit_date and kind not in {"DIVIDEND", "DIVIDENDS", "DISTRIBUTION", "CASH_DIVIDEND"}:
            raise ReflectionError("反事实窗口存在拆股、代码变化或未知公司行动")
    candles = [candle for candle in market.get("candles", []) if candle.get("date") == exit_date]
    if len(candles) != 1:
        raise ReflectionError("延期日期没有唯一可靠日 K，不择用相邻日期")
    quote = candles[0]
    _provenance(quote, "counterfactual.quote")
    if _time(quote["retrieved_at"], "quote.retrieved_at") > cutoff_time:
        raise ReflectionError("延期行情检索超过 cutoff")
    if not quote.get("available_at") or _time(quote["available_at"], "quote.available_at") > cutoff_time:
        raise ReflectionError("延期日 K 完整可用时刻不能确定或晚于 cutoff")
    if _time(quote["available_at"], "quote.available_at").astimezone(zone).date() < exit_day:
        raise ReflectionError("延期日 K 不能在行情所属日之前可用")
    with localcontext() as context:
        context.prec = 40
        quantity = _number(episode.get("quantity"), "episode.quantity", positive=True)
        open_price = _number(opening.get("price"), "opening.price", positive=True)
        hypothetical_price = _number(quote.get("close"), "quote.close", positive=True)
        factor = Decimal("1")
        if market["price_basis"] == "ADJUSTED_WITH_FACTORS":
            values = {row.get("date"): _number(row.get("factor"), "adjustment.factor", positive=True) for row in market.get("adjustment_factors", []) if open_day.isoformat() <= str(row.get("date", "")) <= exit_date}
            if open_day.isoformat() not in values or exit_date not in values or len(set(values.values())) != 1:
                raise ReflectionError("复权因子未覆盖且保持一致，不能改变股数假设强算")
            factor = values[exit_date]
            hypothetical_price /= factor
        total_open_quantity = _number(opening.get("quantity"), "opening.quantity", positive=True)
        opening_fees = _number(opening.get("fees"), "opening.fees") * quantity / total_open_quantity
        exit_fees = _number(costs.get("exit_fees"), "assumed.exit_fees")
        holding_costs = _number(costs.get("holding_costs"), "assumed.holding_costs")
        distributions = _number(costs.get("cash_distributions"), "assumed.cash_distributions")
        if episode.get("direction") == "LONG":
            gross = (hypothetical_price - open_price) * quantity
            cash_impact = distributions
        elif episode.get("direction") == "SHORT":
            gross = (open_price - hypothetical_price) * quantity
            cash_impact = -distributions
        else:
            raise ReflectionError("延期退出没有可证明的多空方向")
        net = gross - opening_fees - exit_fees - holding_costs + cash_impact
        try:
            actual_net = Decimal(str(episode["net_pnl"]))
        except (InvalidOperation, KeyError) as exc:
            raise ReflectionError("原片段净盈亏不可计算") from exc
        if not actual_net.is_finite():
            raise ReflectionError("原片段净盈亏不是有限数")
        metrics = {"quantity": _decimal_string(quantity), "opening_price": _decimal_string(open_price), "hypothetical_exit_price": _decimal_string(hypothetical_price), "opening_fees": _decimal_string(opening_fees), "assumed_exit_fees": _decimal_string(exit_fees), "assumed_holding_costs": _decimal_string(holding_costs), "assumed_cash_distributions": _decimal_string(distributions), "hypothetical_gross_pnl": _decimal_string(gross), "hypothetical_net_pnl": _decimal_string(net), "actual_net_pnl": _decimal_string(actual_net), "difference_net_pnl": _decimal_string(net - actual_net)}
    identity = {"snapshot_hash": packet["snapshot_hash"], "episode_id": episode_id, "exit_date": exit_date, "costs": dict(costs), "market_hash": market_hash}
    ref = "counterfactual:" + _hash(identity)
    return {"kind": "DETERMINISTIC_COUNTERFACTUAL_HOLD", "schema_version": SCHEMA_VERSION, "calculation_ref": ref, "source_id": ref, "as_of": packet["cutoff"], "retrieved_at": _now(), "formula_version": "declared-delayed-exit/1.0.0", "status": "AVAILABLE", "currency": currency, "episode_id": episode_id, "instrument_key": instrument["key"], "window": {"opened_at": opening["occurred_at"], "actual_closed_at": closing["occurred_at"], "hypothetical_exit_date": exit_date, "exchange_timezone": instrument["exchange_timezone"]}, "metrics": metrics, "cost_assumptions": deepcopy(dict(costs)), "lineage": {"input_hash": packet["input_hash"], "snapshot_hash": packet["snapshot_hash"], "opening_record_id": opening["record_id"], "closing_record_id": closing["record_id"], "opening_revision": opening.get("revision"), "closing_revision": closing.get("revision"), "market_content_hash": market_hash, "quote_source_id": quote["source_id"], "quote_as_of": quote["as_of"], "quote_retrieved_at": quote["retrieved_at"], "quote_available_at": quote["available_at"], "price_basis_evidence": deepcopy(dict(proof)), "display_adjustment_factor": _decimal_string(factor)}, "limitations": ["明确日期收盘价与声明成本的单片段反事实假设，不是可执行回测或因果证明。", "假定持有对应片段数量不变；不模拟流动性、盘中路径或改变其他交易。", "成本与现金分配是明确假设，并非已发生费用；不会输出交易建议。"]}


def prepare_counterfactuals(packet: Mapping[str, Any], requests: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Create a new frozen packet with tool-produced scenario calculation refs."""
    validate_packet(packet)
    extended = deepcopy(dict(packet))
    for request in requests:
        if not isinstance(request, Mapping) or set(request) != {"episode_id", "exit_date", "costs"}:
            raise ReflectionError("反事实请求仅允许 episode_id/exit_date/costs")
        result = counterfactual_hold(packet, **dict(request))
        extended["calculations"][result["calculation_ref"]] = result
        extended["counterfactual_requests"].append(deepcopy(dict(request)))
    extended["parent_packet_hash"] = packet["packet_hash"]
    extended.pop("packet_hash")
    extended["packet_hash"] = _hash(extended)
    return extended


def assemble_report(
    packet: Mapping[str, Any], *, findings: list[dict[str, Any]], improvement_plan: list[dict[str, Any]],
    model_version: str, skill_version: str, phase_coverage: Mapping[str, Any],
    report_as_of: str | None = None, analyzed_episode_ids: Iterable[str] | None = None,
    limitations: Iterable[str] = (),
    case_lessons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The LLM submits research fields; deterministic code assembles identity."""
    validate_packet(packet)
    episode_ids = {item["episode_id"] for item in packet["episodes"]}
    done = set(packet["progress"]["analyzed_episode_ids"] if analyzed_episode_ids is None else analyzed_episode_ids)
    if not done <= episode_ids:
        raise ReflectionError("报告进度引用未知 episode")
    timestamp = report_as_of or _now()
    report = {"kind": "TradingReflectionReport", "schema_version": SCHEMA_VERSION, "report_id": f"reflection-{uuid.uuid4().hex}", "source_id": "trading-reflection:local-report", "as_of": timestamp, "retrieved_at": timestamp, "report_as_of": timestamp, "cutoff": packet["cutoff"], "snapshot_id": packet["snapshot_id"], "input_hash": packet["input_hash"], "packet_hash": packet["packet_hash"], "model_version": model_version, "skill_version": skill_version, "scope": deepcopy(packet["scope"]), "limitations": list(packet["limitations"]) + list(limitations), "phase_coverage": deepcopy(dict(phase_coverage)), "findings": deepcopy(findings), "improvement_plan": deepcopy(improvement_plan), "case_selection": deepcopy(packet["case_selection"]), "progress": {"total_units": len(episode_ids), "analyzed_episode_ids": sorted(done), "pending_episode_ids": sorted(episode_ids - done), "status": "COMPLETE" if episode_ids == done else "PARTIAL"}}
    if case_lessons is not None:
        report["schema_version"] = LESSON_REPORT_VERSION
        report["case_lessons"] = deepcopy(case_lessons)
    validate_report(report, packet)
    return report


def _refs(value: Any, allowed: set[str], label: str, *, required: bool = False) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value) or not set(value) <= allowed:
        raise ReflectionError(f"{label} 引用无效")
    if required and not value:
        raise ReflectionError(f"{label} 不可为空")


def validate_report(report: Mapping[str, Any], packet: Mapping[str, Any]) -> None:
    validate_packet(packet)
    if report.get("kind") != "TradingReflectionReport" or report.get("schema_version") not in {SCHEMA_VERSION, LESSON_REPORT_VERSION}:
        raise ReflectionError("不支持的报告 Schema")
    allowed_fields = {"kind", "schema_version", "report_id", "source_id", "as_of", "retrieved_at", "report_as_of", "cutoff", "snapshot_id", "input_hash", "packet_hash", "model_version", "skill_version", "scope", "limitations", "phase_coverage", "findings", "improvement_plan", "case_selection", "progress"}
    if report["schema_version"] == LESSON_REPORT_VERSION:
        allowed_fields.add("case_lessons")
    if set(report) != allowed_fields:
        raise ReflectionError("报告包含未知字段或缺少必需字段")
    _provenance(report, "report")
    for key in ("input_hash", "packet_hash", "snapshot_id", "cutoff"):
        if report.get(key) != packet[key]:
            raise ReflectionError(f"报告 {key} 与冻结输入不一致")
    if not isinstance(report.get("report_id"), str) or not _IDENTITY.fullmatch(report["report_id"]):
        raise ReflectionError("报告身份无效")
    for key in ("model_version", "skill_version", "report_as_of"):
        if not isinstance(report.get(key), str) or not report[key].strip():
            raise ReflectionError(f"报告缺少 {key}")
    if _time(report["report_as_of"], "report_as_of") < _time(packet["cutoff"], "cutoff"):
        raise ReflectionError("报告时刻早于输入 cutoff")
    if report["as_of"] != report["report_as_of"] or report["retrieved_at"] != report["report_as_of"]:
        raise ReflectionError("报告技术时间字段必须与装配时刻一致")
    if report.get("scope") != packet["scope"] or report.get("case_selection") != packet["case_selection"]:
        raise ReflectionError("报告不得改写范围或案例选择")
    if not isinstance(report.get("limitations"), list) or not report["limitations"]:
        raise ReflectionError("报告必须披露限制")
    coverage = report.get("phase_coverage", {})
    if set(coverage) != set(PHASES):
        raise ReflectionError("报告须说明入场、调整、退出、持有和风险暴露覆盖")
    for phase, value in coverage.items():
        if not isinstance(value, Mapping) or value.get("status") not in {"ANALYZED", "DATA_LIMITED", "NOT_APPLICABLE", "PENDING"} or not value.get("reason"):
            raise ReflectionError(f"{phase} 覆盖须有状态和解释")
    records = set(packet["scope"]["record_ids"])
    episodes = {item["episode_id"] for item in packet["episodes"]}
    evidence = {item["evidence_id"] for item in packet["evidence"]}
    calculations = set(packet["calculations"])
    diaries = {item["diary_id"] for item in packet["diary"]}
    findings = _unique(report.get("findings", []), "finding_id", "findings")
    if not findings:
        raise ReflectionError("报告至少需要一个有依据的发现")
    explained_episodes: set[str] = set()
    for finding in findings.values():
        for field in ("pattern", "process_observation", "result_observation", "interpretation", "confidence_limits"):
            if not finding.get(field):
                raise ReflectionError(f"发现缺少 {field}")
        _refs(finding.get("record_refs"), records, "finding.record_refs", required=True)
        _refs(finding.get("episode_refs"), episodes, "finding.episode_refs", required=True)
        explained_episodes.update(finding["episode_refs"])
        _refs(finding.get("calculation_refs", []), calculations, "finding.calculation_refs")
        _refs(finding.get("diary_refs", []), diaries, "finding.diary_refs")
        _refs(finding.get("chart_refs"), set(packet.get("chart_refs", [])), "finding.chart_refs", required=True)
        _refs(finding.get("decision_evidence_refs", []), evidence, "finding.decision_evidence_refs")
        _refs(finding.get("outcome_evidence_refs", []), evidence, "finding.outcome_evidence_refs")
        _refs(finding.get("uncertain_evidence_refs", []), evidence, "finding.uncertain_evidence_refs")
        for evidence_id in finding.get("decision_evidence_refs", []):
            if not all(evidence_id in {item["evidence_id"] for item in packet["record_layers"][record_id]["contemporaneous"]} for record_id in finding["record_refs"]):
                raise ReflectionError("当时背景引用包含事后或不确定资料")
        for claim in finding.get("intent_claims", []):
            if not isinstance(claim, Mapping) or claim.get("record_id") not in finding["record_refs"] or claim.get("diary_id") not in finding.get("diary_refs", []):
                raise ReflectionError("交易意图声明缺少成交/日记引用")
            layer = claim.get("layer")
            if layer not in {"AT_TIME", "RETROSPECTIVE", "UNCERTAIN"}:
                raise ReflectionError("交易意图声明需要当时/事后/不确定层")
            field = {"AT_TIME": "diary_at_time", "RETROSPECTIVE": "diary_retrospective", "UNCERTAIN": "diary_uncertain"}[layer]
            if claim["diary_id"] not in packet["record_layers"][claim["record_id"]][field]:
                raise ReflectionError("事后日记不能冒充当时意图")
        alternatives = finding.get("alternative_explanations", [])
        if not isinstance(alternatives, list) or not alternatives:
            raise ReflectionError("每个发现需要反例或替代解释")
        for alternative in alternatives:
            if not isinstance(alternative, Mapping) or not alternative.get("text"):
                raise ReflectionError("替代解释缺少文字")
            _refs(alternative.get("record_refs", []), records, "alternative.record_refs")
            _refs(alternative.get("episode_refs", []), episodes, "alternative.episode_refs")
            explained_episodes.update(alternative.get("episode_refs", []))
            _refs(alternative.get("evidence_refs", []), evidence, "alternative.evidence_refs")
        for claim in finding.get("financial_claims", []):
            if not isinstance(claim, Mapping) or claim.get("calculation_ref") not in calculations:
                raise ReflectionError("金融数值需要确定性计算引用")
            calculation = packet["calculations"][claim["calculation_ref"]]
            if claim.get("metric") not in calculation["metrics"] or claim.get("value") != calculation["metrics"][claim["metric"]]:
                raise ReflectionError("金融数值与确定性工具结果不一致")
    plans = _unique(report.get("improvement_plan", []), "improvement_id", "improvement_plan")
    if not plans:
        raise ReflectionError("报告需要可跟踪改进练习")
    for plan in plans.values():
        _refs(plan.get("finding_refs"), set(findings), "improvement.finding_refs", required=True)
        _refs(plan.get("evidence_refs", []), evidence, "improvement.evidence_refs")
        _refs(plan.get("record_refs", []), records, "improvement.record_refs", required=True)
        for field in ("exercise", "next_inputs", "verification", "review_window"):
            if not plan.get(field):
                raise ReflectionError(f"改进练习缺少 {field}")
        if plan.get("status") not in {"PROPOSED", "IN_PROGRESS", "REVIEWED", "DEFERRED"}:
            raise ReflectionError("改进计划状态无效")
    progress = report.get("progress", {})
    done, pending = progress.get("analyzed_episode_ids"), progress.get("pending_episode_ids")
    _refs(done, episodes, "progress.analyzed_episode_ids")
    _refs(pending, episodes, "progress.pending_episode_ids")
    if set(done) & set(pending) or set(done) | set(pending) != episodes or progress.get("total_units") != len(episodes):
        raise ReflectionError("分批进度遗漏或重复 episode")
    if not set(done) <= explained_episodes:
        raise ReflectionError("不能把没有发现或反例引用的 episode 标为已分析")
    if progress.get("status") != ("COMPLETE" if not pending else "PARTIAL"):
        raise ReflectionError("分批状态与待分析范围不一致")
    if report["schema_version"] == LESSON_REPORT_VERSION:
        _validate_case_lessons(report, packet, findings)


def _lesson_text(value: Any, label: str) -> None:
    if isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value):
        return
    if not isinstance(value, str) or not value.strip():
        raise ReflectionError(f"图表讲解 {label} 需要非空文字")


def _lesson_anchor(evidence: Mapping[str, Any], role: str, timezone_name: str | None) -> tuple[str | None, str | None]:
    if not isinstance(role, str):
        raise ReflectionError("事件锚点角色无效")
    if role == "UNPLACED":
        return None, None
    field = {"AVAILABLE_AT": "available_at", "EVENT_AT": "event_at"}.get(role)
    if field is None:
        raise ReflectionError("事件锚点角色无效")
    anchor = evidence.get(field)
    basis = evidence.get("availability_basis", evidence.get("available_at_basis")) if role == "AVAILABLE_AT" else evidence.get("event_time_basis", evidence.get("availability_basis"))
    if not isinstance(anchor, str) or not basis:
        raise ReflectionError("事件缺少可信来源锚点，必须保留 UNPLACED")
    try:
        if len(anchor) == 10:
            if evidence.get("publication_precision") != "DATE":
                raise ReflectionError("日期锚点须保留 DATE 精度")
            return date.fromisoformat(anchor).isoformat(), anchor
        instant = _time(anchor, field)
        if not timezone_name:
            return None, anchor
        return instant.astimezone(ZoneInfo(timezone_name)).date().isoformat(), anchor
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ReflectionError("事件锚点或图表时区无效") from exc


def _validate_case_lessons(report: Mapping[str, Any], packet: Mapping[str, Any], findings: Mapping[str, Any]) -> None:
    values = report.get("case_lessons")
    if not isinstance(values, list):
        raise ReflectionError("新版报告需要完整 case_lessons")
    lessons = _unique(values, "finding_ref", "case_lessons")
    if set(lessons) != set(findings):
        raise ReflectionError("图表讲解须完整覆盖每项发现且不得重复")
    records = {item["record_id"]: item for item in packet["snapshot"]["records"]}
    evidence = {item["evidence_id"]: item for item in packet["evidence"]}
    cutoff = _time(packet["cutoff"], "cutoff")
    for identifier, lesson in lessons.items():
        if set(lesson) != {"finding_ref", "focus_record_ref", "chart_window", "beginner", "practice", "advanced", "event_links", "limits"}:
            raise ReflectionError("图表讲解包含未知字段或缺少必需字段")
        finding = findings[identifier]
        focus = lesson["focus_record_ref"]
        if not isinstance(focus, str) or focus not in finding["record_refs"]:
            raise ReflectionError("图表焦点须为该发现的真实主样本成交")
        related_records = set(finding["record_refs"])
        related_evidence = set()
        for field in ("decision_evidence_refs", "outcome_evidence_refs", "uncertain_evidence_refs"):
            related_evidence.update(finding.get(field, []))
        for alternative in finding["alternative_explanations"]:
            related_records.update(alternative.get("record_refs", []))
            related_evidence.update(alternative.get("evidence_refs", []))
        window = lesson["chart_window"]
        if not isinstance(window, Mapping) or set(window) != {"start", "end", "record_refs", "focus_instrument_key"}:
            raise ReflectionError("图表窗口字段无效")
        instrument = records[focus]["instrument"]
        if window["focus_instrument_key"] != instrument["key"]:
            raise ReflectionError("图表焦点证券身份不符")
        try:
            start, end = date.fromisoformat(window["start"]), date.fromisoformat(window["end"])
            raw = records[focus]
            if raw.get("time_precision") == "DATE":
                day = date.fromisoformat(raw["occurred_at"])
                # Keep the source calendar date without synthesizing an instant.
                # Match the frozen input's conservative cutoff calendar; this
                # fallback does not change DATE precision or its uncertain PIT.
                zone = ZoneInfo(raw.get("source_timezone") or instrument.get("exchange_timezone", "UTC"))
            else:
                zone = ZoneInfo(instrument["exchange_timezone"])
                day = _time(raw["occurred_at"], "focus.occurred_at").astimezone(zone).date()
            if not start <= day <= end <= cutoff.astimezone(zone).date():
                raise ReflectionError("图表窗口须包含焦点且不超出冻结截止")
        except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError) as exc:
            raise ReflectionError("图表窗口日期或时区无效") from exc
        _refs(window["record_refs"], related_records, "chart_window.record_refs", required=True)
        if focus not in window["record_refs"]:
            raise ReflectionError("图表窗口未引用焦点成交")
        for layer, fields in {"beginner": {"read_chart", "why_it_matters", "terms"}, "practice": {"possible_error", "exercise", "next_inputs", "verification"}, "advanced": {"alternative_explanation", "falsifier", "additional_evidence"}}.items():
            body = lesson[layer]
            if not isinstance(body, Mapping) or set(body) != fields | {"record_refs", "evidence_refs"}:
                raise ReflectionError(f"图表讲解 {layer} 字段无效")
            for field in fields - {"terms"}:
                _lesson_text(body[field], f"{layer}.{field}")
            _refs(body["record_refs"], related_records, f"{layer}.record_refs", required=True)
            _refs(body["evidence_refs"], related_evidence, f"{layer}.evidence_refs")
        terms = lesson["beginner"]["terms"]
        if not isinstance(terms, list) or not terms:
            raise ReflectionError("初学讲解须包含术语解释")
        for term in terms:
            if not isinstance(term, Mapping) or set(term) != {"term", "meaning", "case_application"}:
                raise ReflectionError("术语字段无效")
            for field in term:
                _lesson_text(term[field], f"term.{field}")
        _lesson_text(lesson["limits"], "limits")
        if not isinstance(lesson["limits"], list) or not isinstance(lesson["event_links"], list):
            raise ReflectionError("限制和事件链接须为列表")
        seen_links = set()
        for link in lesson["event_links"]:
            if not isinstance(link, Mapping) or set(link) != {"evidence_ref", "record_refs", "anchor_role", "relevance_note"}:
                raise ReflectionError("事件关联包含未知字段，时间必须由来源派生")
            eid = link["evidence_ref"]
            if not isinstance(eid, str) or eid not in related_evidence:
                raise ReflectionError("事件关联须为本案证据引用")
            _refs(link["record_refs"], related_records, "event.record_refs", required=True)
            _lesson_anchor(evidence[eid], link["anchor_role"], instrument.get("exchange_timezone"))
            link_key = (eid, link["anchor_role"], tuple(sorted(link["record_refs"])))
            if link_key in seen_links:
                raise ReflectionError("事件关联记录集合与角色重复")
            seen_links.add(link_key)
            _lesson_text(link["relevance_note"], "event.relevance_note")


def lesson_events(report: Mapping[str, Any], packet: Mapping[str, Any], lesson: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project source clocks and per-fill information layers; never infer relevance."""
    evidence = {item["evidence_id"]: item for item in packet["evidence"]}
    records = {item["record_id"]: item for item in packet["snapshot"]["records"]}
    focus = records[lesson["focus_record_ref"]]
    zone = focus["instrument"].get("exchange_timezone")
    events = []
    for link in lesson["event_links"]:
        item = evidence[link["evidence_ref"]]
        day, anchor = _lesson_anchor(item, link["anchor_role"], zone)
        layers = []
        for rid in link["record_refs"]:
            layer, reason = "uncertain", "冻结资料未绑定本笔成交的信息层"
            for name in ("contemporaneous", "outcome", "uncertain"):
                matched = next((entry for entry in packet["record_layers"][rid][name] if entry["evidence_id"] == item["evidence_id"]), None)
                if matched:
                    layer, reason = name, matched["reason"]
                    break
            layers.append({"record_id": rid, "layer": layer, "reason": reason})
        projected = {key: deepcopy(item.get(key)) for key in ("evidence_id", "source_id", "as_of", "retrieved_at", "title", "content", "source_url", "publication_precision", "availability_basis", "vintage_status")}
        projected.update(anchor_role=link["anchor_role"], anchor_at=anchor, date=day, record_refs=list(link["record_refs"]), layers=layers, relevance_note=link["relevance_note"])
        projected["dates_by_record"] = {rid: _lesson_anchor(item, link["anchor_role"], records[rid]["instrument"].get("exchange_timezone"))[0] for rid in link["record_refs"]}
        events.append(projected)
    return events


def _display(value: Any) -> str:
    if isinstance(value, list):
        return "；".join(_display(item) for item in value) or "无"
    if value is None:
        return "未知"
    if isinstance(value, Mapping):
        return _canonical(value)
    return str(value)


def _table_cell(value: Any) -> str:
    return _display(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _references(values: Iterable[str]) -> str:
    return ", ".join(values) or "无"


def render_markdown(report: Mapping[str, Any], packet: Mapping[str, Any] | None = None) -> str:
    """Project frozen research into readable Chinese; never alter its semantics."""
    from .presentation import build_reader_labels, readable_text

    labels = build_reader_labels(packet=packet, report=report)
    text = lambda value: readable_text(value, labels)
    refs = lambda values: text([labels.get(value, "引用资料暂不可展示") for value in values])
    cell = lambda value: text(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")
    scope, coverage = report["scope"], report["scope"]["coverage"]
    lines = ["# 个人交易反思", "", f"报告时刻：{text(report['report_as_of'])}", f"资料截止：{text(report['cutoff'])}", f"分析范围：{text(scope['mode'])}", "", "## 范围与限制", "", f"资产类别：{text(scope['asset_types'])}", f"实际覆盖状态：{text(coverage.get('status', 'UNKNOWN'))}", f"分析成交：{len(scope['record_ids'])}笔", f"配对上下文：{len(scope.get('context_record_ids', []))}笔", f"区间外成交：{len(scope['excluded_record_ids'])}笔", f"请求窗口：{text(coverage.get('requested_window'))}", ""]
    for observation in coverage.get("observations", []):
        lines.append(f"- 来源覆盖：{text(observation.get('actual_start'))} 至 {text(observation.get('actual_end'))}；{text(observation.get('status', 'UNKNOWN'))}；{text(observation.get('collection_mode', 'UNKNOWN'))}")
    for gap in coverage.get("gaps", []):
        lines.append(f"- 覆盖缺口：{text(gap)}")
    lines.extend(f"- {text(item)}" for item in scope.get("limitations", []))
    lines.extend(f"- {text(item)}" for item in report["limitations"])
    lines.extend(["", "## 过程覆盖", "", "| 阶段 | 状态 | 具体覆盖与限制 |", "| --- | --- | --- |"])
    for phase in PHASES:
        value = report["phase_coverage"][phase]
        lines.append(f"| {cell(phase)} | {cell(value['status'])} | {cell(value['reason'])} |")
    progress = report["progress"]
    lines.extend(["", "## 分析进度与案例选择", "", f"总分析单元：{progress['total_units']}", f"进度状态：{text(progress['status'])}", f"已分析：{len(progress['analyzed_episode_ids'])}个单元", f"待分析：{len(progress['pending_episode_ids'])}个单元", ""])
    if progress["pending_episode_ids"]:
        lines.append("待分析片段：" + refs(progress["pending_episode_ids"]))
    selection = report["case_selection"]
    for category, identifiers in selection["available_by_result"].items():
        lines.append(f"- {text(category)}：{len(identifiers)}个单元")
    for episode_id, reason in selection["selected_reasons"].items():
        lines.append(f"- 选择 {refs([episode_id])}：{text(reason)}")
    lines.extend([f"尚未选取的结果类别：{text(selection['omitted_classes'])}", "", "## 观察与反例", ""])
    lessons = {item["finding_ref"]: item for item in report.get("case_lessons", [])}
    for finding in report["findings"]:
        lines.extend([f"### {text(finding['pattern'])}", "", f"过程观察：{text(finding['process_observation'])}", f"结果观察：{text(finding['result_observation'])}", f"候选解释：{text(finding['interpretation'])}", f"置信限制：{text(finding['confidence_limits'])}", f"成交引用：{refs(finding['record_refs'])}", f"交易片段：{refs(finding['episode_refs'])}", f"图表引用：{refs(finding['chart_refs'])}", f"当时证据：{refs(finding.get('decision_evidence_refs', []))}", f"事后证据：{refs(finding.get('outcome_evidence_refs', []))}", f"不确定证据：{refs(finding.get('uncertain_evidence_refs', []))}", f"交易日记：{refs(finding.get('diary_refs', []))}", f"确定性计算：{refs(finding.get('calculation_refs', []))}", ""])
        for claim in finding.get("intent_claims", []):
            lines.append(f"- 意图记录：{refs([claim['record_id']])}；{refs([claim['diary_id']])}；{text(claim['layer'])}")
        if finding.get("financial_claims"):
            lines.extend(["", "| 金融指标 | 工具原值 | 原币种 | 计算依据 |", "| --- | --- | --- | --- |"])
            for claim in finding["financial_claims"]:
                calculation = packet.get("calculations", {}).get(claim["calculation_ref"], {}) if packet else {}
                lines.append(f"| {cell(claim['metric'])} | {cell(claim['value'])} | {cell(calculation.get('currency', '未知'))} | {cell(refs([claim['calculation_ref']]))} |")
        lines.append("")
        for alternative in finding["alternative_explanations"]:
            lines.extend([f"- 反例或替代解释：{text(alternative['text'])}", f"  成交引用：{refs(alternative.get('record_refs', []))}", f"  交易片段：{refs(alternative.get('episode_refs', []))}", f"  证据引用：{refs(alternative.get('evidence_refs', []))}"])
        lines.append("")
        lesson = lessons.get(finding["finding_id"])
        if lesson:
            window = lesson["chart_window"]
            lines.extend(["#### 图表讲解", "", f"焦点成交：{refs([lesson['focus_record_ref']])}", f"图窗：{text(window['start'])} 至 {text(window['end'])}；证券：{labels.get(window['focus_instrument_key'], '证券资料暂不可展示')}", f"图窗成交：{refs(window['record_refs'])}", ""])
            for label, name, fields in (("读图", "beginner", ("read_chart", "why_it_matters")), ("改错练习", "practice", ("possible_error", "exercise", "next_inputs", "verification")), ("深入反证", "advanced", ("alternative_explanation", "falsifier", "additional_evidence"))):
                body = lesson[name]
                lines.append(f"**{label}**")
                lines.extend(f"- {text(field)}：{text(body[field])}" for field in fields)
                lines.extend([f"- 成交引用：{refs(body['record_refs'])}", f"- 证据引用：{refs(body['evidence_refs'])}", ""])
            for term in lesson["beginner"]["terms"]:
                lines.append(f"- {text(term['term'])}：{text(term['meaning'])}；本案：{text(term['case_application'])}")
            lines.extend(f"- 讲解限制：{text(value)}" for value in lesson["limits"])
            if packet:
                for event in lesson_events(report, packet, lesson):
                    layers = "；".join(f"{refs([item['record_id']])}：{text(item['layer'])}（{text(item['reason'])}）" for item in event["layers"])
                    lines.append(f"- 事件 {refs([event['evidence_id']])}：{text(event['anchor_at'])}；{text(event['publication_precision'])}；{text(event['relevance_note'])}；逐笔资料时点：{layers}")
            lines.append("")
    lines.extend(["## 改进练习", ""])
    for plan in report["improvement_plan"]:
        lines.extend([f"### {text(plan.get('title') or plan['exercise'])}", "", f"对应发现：{refs(plan['finding_refs'])}", f"成交引用：{refs(plan['record_refs'])}", f"证据引用：{refs(plan.get('evidence_refs', []))}", f"练习：{text(plan['exercise'])}", f"下次记录：{text(plan['next_inputs'])}", f"验证方式：{text(plan['verification'])}", f"复查窗口：{text(plan['review_window'])}", f"状态：{text(plan['status'])}", ""])
    if packet:
        used_evidence = set()
        for finding in report["findings"]:
            for field in ("decision_evidence_refs", "outcome_evidence_refs", "uncertain_evidence_refs"):
                used_evidence.update(finding.get(field, []))
            for alternative in finding["alternative_explanations"]:
                used_evidence.update(alternative.get("evidence_refs", []))
        for plan in report["improvement_plan"]:
            used_evidence.update(plan.get("evidence_refs", []))
        for lesson in report.get("case_lessons", []):
            for name in ("beginner", "practice", "advanced"):
                used_evidence.update(lesson[name]["evidence_refs"])
            used_evidence.update(link["evidence_ref"] for link in lesson["event_links"])
        lines.extend(["## 公开资料出处与时点", ""])
        for item in packet.get("evidence", []):
            if item["evidence_id"] not in used_evidence:
                continue
            lines.extend([f"### {refs([item['evidence_id']])}", "", f"标题：{text(item.get('title') or '未提供标题')}", f"来源：{labels.get(item['source_id'], '已保存公开资料')}", f"出处：{text(item.get('source_url') or '未提供公开链接')}", f"事实截止：{text(item['as_of'])}", f"检索时刻：{text(item['retrieved_at'])}", f"可用时刻：{text(item.get('available_at', item.get('published_at')))}", f"可用时刻依据：{text(item.get('availability_basis', item.get('available_at_basis')))}", f"发布精度：{text(item.get('publication_precision'))}", f"历史资料状态：{text(item.get('vintage_status'))}；可用时刻：{text(item.get('vintage_available_at'))}", ""])
    lines.extend(["报告与冻结事实已一同保存；本页仅调整阅读展示，不产生新的研究结论。", ""])
    return "\n".join(lines)


def _private_directory(root: Path, relative: str) -> Path:
    root = Path(root).absolute()
    if not root.is_dir() or any(path.is_symlink() for path in (root, *root.parents)):
        raise ReflectionError("保存目录必须是已验证且存在的私人 root")
    if root.stat().st_mode & 0o077:
        raise ReflectionError("私人 root 权限必须为 0700")
    current = root
    for component in relative.split("/"):
        current = current / component
        if current.is_symlink():
            raise ReflectionError("私人产物路径不能为符号链接")
        if not current.exists():
            current.mkdir(mode=0o700)
        if not current.is_dir() or current.stat().st_mode & 0o077:
            raise ReflectionError("私人产物目录权限必须为 0700")
    return current


def _write_exclusive(path: Path, value: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def save_packet(validated_root: Path, packet: Mapping[str, Any]) -> Path:
    validate_packet(packet)
    directory = _private_directory(validated_root, "artifacts/reflection-inputs")
    path = directory / f"{packet['packet_hash']}.json"
    encoded = _canonical(packet) + "\n"
    if path.exists():
        if path.is_symlink() or path.stat().st_mode & 0o077 or path.read_text(encoding="utf-8") != encoded:
            raise ReflectionError("既存输入版本不一致或不安全，拒绝覆盖")
        return path
    _write_exclusive(path, encoded)
    return path


def save_report(validated_root: Path, report: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, str]:
    """Persist one immutable report version under an already validated private root."""
    validate_report(report, packet)
    directory = _private_directory(validated_root, "artifacts/reflections")
    destination = directory / report["report_id"]
    # Exclusive directory creation rejects even identical retries and old versions.
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ReflectionError("报告版本已存在，必须创建新版本") from exc
    paths = {"json_path": destination / "report.json", "markdown_path": destination / "report.md", "packet_path": destination / "input.json"}
    _write_exclusive(paths["packet_path"], _canonical(packet) + "\n")
    _write_exclusive(paths["json_path"], _canonical(report) + "\n")
    _write_exclusive(paths["markdown_path"], render_markdown(report, packet))
    return {"report_id": report["report_id"], **{key: str(value) for key, value in paths.items()}}
