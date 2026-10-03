"""Explicit requested windows; calendar subtraction does not use 30-day months."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError, iso_datetime, utc_now

_PRESETS = {
    "一周": "week", "1w": "week", "week": "week", "one_week": "week",
    "一个月": "month", "1m": "month", "month": "month", "one_month": "month",
    "半年": "half_year", "6m": "half_year", "half_year": "half_year", "six_months": "half_year",
    "一年": "year", "1y": "year", "year": "year", "one_year": "year",
    "开户至今": "lifetime", "lifetime": "lifetime", "since_open": "lifetime",
    "自定义": "custom", "custom": "custom",
}


def _months_before(value: datetime, months: int) -> datetime:
    year, zero_month = divmod(value.year * 12 + value.month - 1 - months, 12)
    month = zero_month + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def _bound(value: str, tz: ZoneInfo, *, is_end: bool) -> datetime:
    if len(value) == 10:
        try:
            local_date = date.fromisoformat(value)
        except ValueError as exc:
            raise JournalError("INVALID_WINDOW", "日期范围格式无效。") from exc
        # Date selections include the whole local day; end is inclusive.
        return datetime.combine(local_date, time.max if is_end else time.min, tz)
    return iso_datetime(value).astimezone(tz)


def resolve_window(preset: str, *, now: str | datetime | None = None,
                   timezone_name: str = "Asia/Shanghai", start: str | None = None,
                   end: str | None = None, account_opened_at: str | None = None) -> dict:
    """Return an inclusive frozen interval; lifetime start may remain unknown."""
    if preset not in _PRESETS:
        raise JournalError("WINDOW_CHOICE_REQUIRED", "请指定开始和截止日期，也可选择一周、一个月、半年或一年。")
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise JournalError("INVALID_TIMEZONE", "用户时区无效。") from exc
    resolved_now = now or utc_now()
    cutoff = iso_datetime(resolved_now) if isinstance(resolved_now, str) else resolved_now
    if cutoff.tzinfo is None:
        raise JournalError("TIMEZONE_REQUIRED", "截止时间缺少时区。")
    cutoff = cutoff.astimezone(tz)
    choice = _PRESETS[preset]
    until = _bound(end, tz, is_end=True) if end else cutoff
    if until > cutoff:
        until = cutoff
    opened_known = False
    if choice == "custom":
        if not start or not end:
            raise JournalError("WINDOW_BOUNDS_REQUIRED", "自定义范围需要起止日期。")
        since = _bound(start, tz, is_end=False)
    elif choice == "lifetime":
        since = _bound(account_opened_at, tz, is_end=False) if account_opened_at else None
        opened_known = account_opened_at is not None
    elif choice == "week":
        since = until - timedelta(days=7)
    else:
        since = _months_before(until, {"month": 1, "half_year": 6, "year": 12}[choice])
    if since is not None and since > until:
        raise JournalError("INVALID_WINDOW", "开始日期晚于截止日期。")
    return {
        "preset": choice, "start": since.isoformat() if since else None,
        "end": until.isoformat(), "timezone": timezone_name,
        "boundary": "INCLUSIVE", "account_opened_at_known": opened_known,
        "query_start_date": since.date().isoformat() if since else None,
        "query_end_date": until.date().isoformat(),
        "start_unknown_reason": "账户起点未经官方核验" if choice == "lifetime" and since is None else None,
    }


def record_in_window(record: dict, window: dict | None) -> bool:
    if not window:
        return True
    occurred = record.get("occurred_at")
    if not occurred:
        return False
    start, end = window.get("start"), window.get("end")
    if record.get("time_precision") == "DATE" or len(occurred) == 10:
        # Date-only records cannot establish inclusion at intraday boundaries.
        # Retain the boundary day as explicitly uncertain, rather than discard it.
        tz = ZoneInfo(record.get("source_timezone") or record.get("instrument", {}).get("exchange_timezone") or window.get("timezone") or "Asia/Shanghai")
        local_day = date.fromisoformat(occurred)
        return ((not start or local_day >= iso_datetime(start).astimezone(tz).date())
                and (not end or local_day <= iso_datetime(end).astimezone(tz).date()))
    instant = iso_datetime(occurred)
    return (not start or instant >= iso_datetime(start)) and (not end or instant <= iso_datetime(end))


def window_membership(record: dict, window: dict | None) -> str:
    if not record_in_window(record, window):
        return "EXCLUDED"
    if not window or record.get("time_precision") != "DATE":
        return "INCLUDED"
    zone_name = record.get("source_timezone") or record.get("instrument", {}).get("exchange_timezone") or window.get("timezone") or "Asia/Shanghai"
    zone = ZoneInfo(zone_name)
    observed_day = date.fromisoformat(record["occurred_at"])
    for bound, edge in ((window.get("start"), "start"), (window.get("end"), "end")):
        if not bound:
            continue
        local = iso_datetime(bound).astimezone(zone)
        if local.date() == observed_day:
            precise_boundary = local.timetz().replace(tzinfo=None)
            if (edge == "start" and precise_boundary != time.min) or (edge == "end" and precise_boundary != time.max):
                return "BOUNDARY_UNCERTAIN"
    return "INCLUDED"
