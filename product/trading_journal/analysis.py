"""Decimal FIFO of provable fragments, not account returns or a tax method."""

from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from .common import JournalError, canonical_hash, decimal_string, decimal_value, iso_datetime, utc_now
from .windows import record_in_window, window_membership

FORMULA_VERSION = "decimal-fifo/1.0.0"
_LIFECYCLE = {"EXERCISE", "ASSIGNMENT", "EXPIRY", "TRANSFER", "CORPORATE_ACTION"}
_ZERO = Decimal("0")


def _num(record: dict, key: str) -> Decimal | None:
    try:
        return decimal_value(record.get(key), field=key, nullable=True)
    except JournalError:
        return None


def _period_seconds(opened: dict, closed: dict) -> str | None:
    if opened.get("time_precision") != "SECOND" or closed.get("time_precision") != "SECOND":
        return None
    try:
        delta = iso_datetime(closed["occurred_at"]) - iso_datetime(opened["occurred_at"])
        seconds = Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000
        return decimal_string(seconds) if seconds >= 0 else None
    except (JournalError, KeyError):
        return None


def _time_interval(record: dict) -> tuple[datetime, datetime]:
    """Source precision is an interval; date strings do not sort before trades."""
    precision = record.get("time_precision")
    if precision == "DATE":
        zone_name = record.get("source_timezone") or record.get("instrument", {}).get("exchange_timezone")
        if zone_name:
            zone = ZoneInfo(zone_name)
            local_day = date.fromisoformat(record["occurred_at"])
            begin = datetime.combine(local_day, time.min, zone).astimezone(timezone.utc)
            finish = datetime.combine(local_day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        else:
            # No timezone means even the day boundary is unknown; include the
            # full possible worldwide offset range instead of choosing UTC.
            begin = datetime.combine(date.fromisoformat(record["occurred_at"]), time.min, timezone.utc) - timedelta(hours=14)
            finish = begin + timedelta(days=1, hours=26)
        return begin, finish - timedelta(microseconds=1)
    instant = iso_datetime(record["occurred_at"])
    if precision == "MINUTE":
        begin = instant.replace(second=0, microsecond=0)
        return begin, begin + timedelta(minutes=1) - timedelta(microseconds=1)
    return instant, instant


def _sequence_uncertain_ids(activities: list[dict]) -> set[str]:
    fills = [record for record in activities if record.get("activity_type") == "FILL"]
    intervals = sorted([(*_time_interval(record), record) for record in fills], key=lambda item: (item[0], item[2]["record_id"]))
    uncertain = set()
    group = []
    right_edge = None
    def finish_group():
        economic_orders = {(item.get("side"), item.get("price"), item.get("quantity"), item.get("fees")) for item in group}
        if len(group) > 1 and len(economic_orders) > 1:
            uncertain.update(item["record_id"] for item in group)
    for left, right, record in intervals:
        if right_edge is not None and left > right_edge:
            finish_group()
            group = []
            right_edge = None
        group.append(record)
        right_edge = right if right_edge is None else max(right_edge, right)
    finish_group()
    return uncertain


def _episode(opened: dict, closed: dict, *, quantity: Decimal, gross: Decimal | None,
             fees: Decimal | None, direction: str, reasons: list[str]) -> dict:
    identity = {"opening_record_id": opened.get("record_id"), "closing_record_id": closed["record_id"],
                "quantity": decimal_string(quantity), "direction": direction,
                "opening_revision": opened.get("revision"), "closing_revision": closed.get("revision")}
    holding = _period_seconds(opened, closed)
    holding_reason = ("OPENING_TIME_UNKNOWN" if not opened.get("occurred_at") else "TIME_PRECISION_INSUFFICIENT") if holding is None else None
    return {
        "episode_id": "episode-" + canonical_hash(identity), "instrument_key": closed.get("instrument", {}).get("key"),
        "currency": closed.get("currency"), "direction": direction, **identity,
        "opened_at": opened.get("occurred_at"), "closed_at": closed["occurred_at"],
        "gross_pnl": decimal_string(gross), "fees": decimal_string(fees),
        "net_pnl": decimal_string(gross - fees) if gross is not None and fees is not None and not reasons else None,
        "holding_seconds": holding, "holding_status": "AVAILABLE" if holding is not None else "UNAVAILABLE",
        "holding_reason": holding_reason, "status": "AVAILABLE" if gross is not None and fees is not None and not reasons else "UNAVAILABLE",
        "reasons": sorted(set(reasons)), "source_id": closed["source_id"], "as_of": closed["as_of"], "retrieved_at": closed["retrieved_at"],
    }


def analyze_records(records: list[dict], *, window: dict | None = None,
                    opening_positions: dict | None = None, history_complete: bool = False) -> dict:
    """Use saved context before a selected window to pair its closing trades.

    opening_positions describes the state *before the earliest input activity*,
    not before an arbitrary display window. Values require source_id/as_of/
    retrieved_at and quantity; known zero suffices. Unknown initial inventory
    cannot be transformed into a zero-cost sell or an invented short opening.
    """
    with localcontext() as context:
        context.prec = 40
        return _analyze(records, window=window, opening_positions=opening_positions or {}, history_complete=history_complete)


def _analyze(records: list[dict], *, window: dict | None, opening_positions: dict,
             history_complete: bool) -> dict:
    all_records = sorted(deepcopy(records), key=lambda item: (_time_interval(item)[0], item.get("record_id") or ""))
    ordered = list(all_records)
    if window and window.get("end"):
        ordered = [record for record in ordered if record_in_window(record, {"end": window["end"], "timezone": window.get("timezone", "Asia/Shanghai")})]
    by_key: dict[str, list[dict]] = defaultdict(list)
    for record in ordered:
        by_key[str(record.get("instrument", {}).get("key") or "unknown")].append(record)
    option_position_events = [item for item in ordered if item.get("activity_type") in {"EXERCISE", "ASSIGNMENT"}
                              and item.get("instrument", {}).get("asset_type") == "OPTION"]
    linked_fee_records = set()
    fill_refs: dict[tuple[str, str], set[str]] = defaultdict(set)
    order_refs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for fill in ordered:
        if fill.get("activity_type") != "FILL":
            continue
        for reference in (fill.get("record_id"), fill.get("source_record_id")):
            if reference:
                fill_refs[(fill.get("account_ref"), reference)].add(fill["record_id"])
        if fill.get("order_id"):
            order_refs[(fill.get("account_ref"), fill["order_id"])].add(fill["record_id"])
    fee_record_refs = []
    for fee_event in all_records:
        if fee_event.get("activity_type") != "FEE":
            continue
        related = fee_event.get("related_source_record_id")
        order_id = fee_event.get("order_id")
        # Total fees on a fill may already include this separate event.
        # Without source inclusion/incremental semantics, adding or
        # ignoring it would both be guesses. Preserve gross, block net.
        affected = set()
        if related:
            affected.update(fill_refs.get((fee_event.get("account_ref"), related), set()))
        if order_id:
            affected.update(order_refs.get((fee_event.get("account_ref"), order_id), set()))
        if affected:
            linked_fee_records.update(affected)
            fee_record_refs.append({"fee_record_id": fee_event["record_id"], "affected_record_ids": sorted(affected),
                                    "status": "FEES_UNRECONCILED", "source_id": fee_event["source_id"],
                                    "as_of": fee_event["as_of"], "retrieved_at": fee_event["retrieved_at"]})
    consumed_ids = {record["record_id"] for record in ordered} | {item["fee_record_id"] for item in fee_record_refs}
    consumed_records = [record for record in all_records if record["record_id"] in consumed_ids]
    episodes, excluded, open_positions = [], [], []
    limitations = ["FIFO 是复盘配对约定，非税务口径；统计仅涵盖可证明的闭合片段。", "原币种分别汇总；交易片段盈亏不是账户收益率。"]
    for key, activities in by_key.items():
        lots: deque[dict] = deque()
        proven_position = history_complete
        origin_reason = None if proven_position else "OPENING_POSITION_UNKNOWN"
        representative = activities[0].get("instrument") or {}
        possible_stock_events = [item for item in option_position_events
                                 if representative.get("asset_type") in {"STOCK", "ETF"}
                                 and item.get("instrument", {}).get("underlying") == representative.get("symbol")
                                 and item.get("instrument", {}).get("market") == representative.get("market")
                                 and item.get("currency") == representative.get("currency")]
        consumed_stock_events = set()
        initial = opening_positions.get(key)
        if initial is not None:
            if not isinstance(initial, dict) or any(not initial.get(field) for field in ("source_id", "as_of", "retrieved_at")):
                raise JournalError("OPENING_POSITION_PROVENANCE_REQUIRED", "期初仓位需要来源和双时间。")
            iso_datetime(initial["as_of"])
            iso_datetime(initial["retrieved_at"])
            earliest = min(_time_interval(record)[0] for record in activities)
            if iso_datetime(initial["as_of"]) >= earliest:
                raise JournalError("OPENING_POSITION_TIME_NOT_PRIOR", "期初仓位的 as_of 必须早于最早活动的可确定起点；事后仓位不能作为期初证据。")
            if initial.get("occurred_at"):
                initial_time_record = {**initial, "instrument": representative,
                                       "time_precision": initial.get("time_precision") or ("DATE" if len(initial["occurred_at"]) == 10 else "SECOND")}
                if _time_interval(initial_time_record)[1] >= earliest:
                    raise JournalError("OPENING_POSITION_TIME_NOT_PRIOR", "期初成本来源的原始时间不能晚于或重叠最早活动。")
            initial_qty = decimal_value(initial.get("quantity"), field="opening_quantity")
            proven_position, origin_reason = True, None
            if initial_qty:
                first = activities[0]
                initial_price = _num(initial, "price")
                initial_fee = _num(initial, "fees")
                initial_time = initial.get("occurred_at")
                reasons = []
                if initial_price is None:
                    reasons.append("OPENING_COST_UNKNOWN")
                if initial_fee is None or initial.get("fees_complete") is not True:
                    reasons.append("FEES_INCOMPLETE")
                origin = {"record_id": initial.get("record_id") or "opening-position-" + canonical_hash({"key": key, "initial": initial}),
                          "occurred_at": initial_time, "time_precision": initial.get("time_precision", "DATE"),
                          "source_id": initial["source_id"], "as_of": initial["as_of"], "retrieved_at": initial["retrieved_at"]}
                lots.append({"record": origin, "remaining": abs(initial_qty), "price": initial_price,
                             "remaining_fee": initial_fee if initial_fee is not None and initial.get("fees_complete") is True else None,
                             "fee_per_unit": initial_fee / abs(initial_qty) if initial_fee is not None and not reasons else None,
                             "direction": "LONG" if initial_qty > 0 else "SHORT", "reasons": reasons})
        sequence_uncertain = _sequence_uncertain_ids(activities)
        for record in activities:
            for event in possible_stock_events:
                if event["record_id"] not in consumed_stock_events and event["occurred_at"] <= record["occurred_at"]:
                    # Flag a possible missing stock leg; never create that leg
                    # or pretend an exercise proves a particular stock fill.
                    proven_position, origin_reason = False, "OPTION_LIFECYCLE_UNDERLYING_POSITION_UNCERTAIN"
                    for lot in lots:
                        lot["reasons"].append(origin_reason)
                    consumed_stock_events.add(event["record_id"])
            kind = record.get("activity_type")
            if kind in _LIFECYCLE:
                # Neither zeroing expiring positions nor relating exercised
                # options to stock fills is justified without source linkage.
                proven_position, origin_reason = False, "LIFECYCLE_OR_POSITION_CHANGE_UNRECONCILED"
                for lot in lots:
                    lot["reasons"].append(origin_reason)
                if record_in_window(record, window):
                    excluded.append({"record_id": record["record_id"], "reason": origin_reason})
                continue
            if kind != "FILL":
                if record_in_window(record, window):
                    excluded.append({"record_id": record["record_id"], "reason": "NOT_AN_EXECUTION"})
                continue
            qty, price, fee = (_num(record, name) for name in ("quantity", "price", "fees"))
            instrument = record.get("instrument") or {}
            multiplier = _num(instrument, "multiplier")
            errors = []
            if qty is None or qty <= 0 or price is None or price < 0 or record.get("side") not in {"BUY", "SELL"}:
                errors.append("INCOMPLETE_EXECUTION")
            if not record.get("currency"):
                errors.append("CURRENCY_UNKNOWN")
            if instrument.get("asset_type") not in {"STOCK", "ETF", "OPTION"} or not instrument.get("market"):
                errors.append("INSTRUMENT_IDENTITY_INCOMPLETE")
            if instrument.get("asset_type") in {"STOCK", "ETF"}:
                multiplier = Decimal("1")
            if multiplier is None or multiplier <= 0:
                errors.append("MULTIPLIER_UNKNOWN")
            if instrument.get("asset_type") == "OPTION":
                if any(instrument.get(name) is None for name in ("underlying", "expiry", "strike", "right")):
                    errors.append("OPTION_IDENTITY_INCOMPLETE")
                if instrument.get("adjustment_status") not in {"STANDARD", "ADJUSTED"}:
                    errors.append("OPTION_ADJUSTMENT_UNKNOWN")
            if record.get("duplicate_candidate"):
                errors.append("DUPLICATE_IDENTITY_UNCERTAIN")
            if record["record_id"] in sequence_uncertain:
                errors.append("SAME_TIME_SEQUENCE_UNCERTAIN")
            if errors:
                if record_in_window(record, window):
                    excluded.extend({"record_id": record["record_id"], "reason": reason} for reason in errors)
                proven_position, origin_reason = False, errors[0]
                for lot in lots:
                    lot["reasons"].extend(errors)
                continue
            current_direction = "LONG" if record["side"] == "BUY" else "SHORT"
            closing_direction = "SHORT" if record["side"] == "BUY" else "LONG"
            effect = record.get("position_effect")
            if effect == "OPEN" and lots and lots[0]["direction"] == closing_direction:
                if record_in_window(record, window):
                    excluded.append({"record_id": record["record_id"], "reason": "POSITION_EFFECT_CONFLICT"})
                proven_position, origin_reason = False, "POSITION_EFFECT_CONFLICT"
                for lot in lots:
                    lot["reasons"].append(origin_reason)
                continue
            remaining = qty
            fee_reconciled = record["record_id"] not in linked_fee_records
            remaining_fee = fee if fee is not None and record.get("fees_complete") is True and fee_reconciled else None
            fee_per_unit = fee / qty if fee is not None and record.get("fees_complete") is True and fee_reconciled else None
            while remaining > 0 and lots and lots[0]["direction"] == closing_direction:
                lot = lots[0]
                closed_quantity = min(remaining, lot["remaining"])
                reasons = list(lot["reasons"])
                if window_membership(record, window) == "BOUNDARY_UNCERTAIN":
                    reasons.append("WINDOW_BOUNDARY_TIME_UNCERTAIN")
                if not proven_position:
                    reasons.append(origin_reason or "OPENING_POSITION_UNKNOWN")
                if fee_per_unit is None or lot["fee_per_unit"] is None:
                    reasons.append("FEES_INCOMPLETE")
                if not fee_reconciled:
                    reasons.append("FEES_UNRECONCILED")
                gross = None
                if lot["price"] is not None and proven_position and not any(reason not in {"FEES_INCOMPLETE", "FEES_UNRECONCILED"} for reason in reasons):
                    gross = (price - lot["price"] if closing_direction == "LONG" else lot["price"] - price) * closed_quantity * multiplier
                elif lot["price"] is None:
                    reasons.append("OPENING_COST_UNKNOWN")
                open_fee_part = (lot["remaining_fee"] if closed_quantity == lot["remaining"] else lot["remaining_fee"] * closed_quantity / lot["remaining"]) if lot.get("remaining_fee") is not None else None
                close_fee_part = (remaining_fee if closed_quantity == remaining else remaining_fee * closed_quantity / remaining) if remaining_fee is not None else None
                fees = open_fee_part + close_fee_part if open_fee_part is not None and close_fee_part is not None else None
                if open_fee_part is not None:
                    lot["remaining_fee"] -= open_fee_part
                if close_fee_part is not None:
                    remaining_fee -= close_fee_part
                if record_in_window(record, window):
                    episodes.append(_episode(lot["record"], record, quantity=closed_quantity, gross=gross,
                                             fees=fees, direction=closing_direction, reasons=reasons))
                remaining -= closed_quantity
                lot["remaining"] -= closed_quantity
                if lot["remaining"] == 0:
                    lots.popleft()
            if remaining > 0:
                if effect == "CLOSE":
                    if record_in_window(record, window):
                        episodes.append(_episode({}, record, quantity=remaining, gross=None, fees=None,
                                                 direction=closing_direction, reasons=["CLOSE_EXCEEDS_KNOWN_POSITION", origin_reason or "OPENING_POSITION_UNKNOWN"]))
                    proven_position, origin_reason = False, "CLOSE_EXCEEDS_KNOWN_POSITION"
                    continue
                if not proven_position and record["side"] == "SELL" and not lots and effect != "OPEN":
                    if record_in_window(record, window):
                        episodes.append(_episode({}, record, quantity=remaining, gross=None, fees=None,
                                                 direction="UNKNOWN", reasons=[origin_reason or "OPENING_POSITION_UNKNOWN", "SELL_NOT_PROVEN_SHORT_OPEN"]))
                    # Do not make a fictitious short out of an unpaired sell.
                    continue
                reasons = []
                if not proven_position:
                    reasons.append(origin_reason or "OPENING_POSITION_UNKNOWN")
                if fee_per_unit is None:
                    reasons.append("FEES_INCOMPLETE")
                if not fee_reconciled:
                    reasons.append("FEES_UNRECONCILED")
                lots.append({"record": record, "remaining": remaining, "price": price,
                             "remaining_fee": remaining_fee,
                             "fee_per_unit": fee_per_unit, "direction": current_direction, "reasons": reasons})
        if lots:
            open_positions.append({"instrument_key": key, "currency": activities[-1].get("currency"),
                                   "status": "AVAILABLE" if proven_position else "UNAVAILABLE",
                                   "lots": [{"opening_record_id": lot["record"].get("record_id"), "quantity": decimal_string(lot["remaining"]),
                                             "direction": lot["direction"], "reasons": sorted(set(lot["reasons"]))} for lot in lots]})
    by_currency = []
    currency_groups: dict[str, list[dict]] = defaultdict(list)
    for item in episodes:
        currency_groups[item.get("currency") or "UNKNOWN"].append(item)
    for currency, values in sorted(currency_groups.items()):
        available = [item for item in values if item["status"] == "AVAILABLE"]
        def total(field: str):
            return decimal_string(sum((decimal_value(item[field]) for item in available), _ZERO)) if available else None
        by_currency.append({"currency": currency, "closed_quantity": total("quantity"), "gross_pnl": total("gross_pnl"),
                            "fees": total("fees"), "net_pnl": total("net_pnl"), "available_episodes": len(available),
                            "unavailable_episodes": len(values) - len(available), "aggregation_scope": "AVAILABLE_EPISODES_ONLY"})
    created = utc_now()
    reasons = sorted({reason for item in episodes for reason in item["reasons"]} | {item["reason"] for item in excluded})
    if reasons:
        limitations.append("部分片段不可计算：" + "、".join(reasons))
    return {
        "kind": "TradeJournalAnalysis", "formula_version": FORMULA_VERSION,
        "source_id": "calculation-" + canonical_hash({"records": consumed_records, "window": window, "opening_positions": opening_positions, "history_complete": history_complete}),
        "as_of": window.get("end") if window and window.get("end") else (max((record["as_of"] for record in ordered), default=created)),
        "retrieved_at": created, "records_hash": canonical_hash(consumed_records), "scope": {"window": deepcopy(window), "input_count": len(consumed_records), "history_complete": history_complete},
        "episodes": episodes, "by_currency": by_currency, "open_positions": open_positions,
        "excluded_records": excluded, "fee_record_refs": fee_record_refs, "limitations": limitations,
    }
