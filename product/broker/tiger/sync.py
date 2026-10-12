"""Bounded, explicit Tiger history synchronization into PrivateBrokerLedger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import time
from typing import Any, Callable, Iterable
from uuid import uuid4

from .contracts import finalize_contract
from .normalization import (
    next_page_token,
    normalize_asset_point,
    normalize_charges,
    normalize_execution,
    normalize_fund_detail,
    normalize_funding,
    normalize_order,
    rows,
)


SDK_VERSION = "3.8.0"
MAX_WINDOW_DAYS = 90
PAGE_SIZE = 100
MAX_PAGES_PER_WINDOW = 1000
MAX_REQUESTS_PER_SYNC = 10_000


class TigerSyncError(ValueError):
    """Stable synchronization error without response payloads."""


@dataclass
class RequestBudget:
    remaining: int = MAX_REQUESTS_PER_SYNC

    def consume(self) -> None:
        if self.remaining <= 0:
            raise TigerSyncError("TIGER_SYNC_REQUEST_BUDGET_EXHAUSTED")
        self.remaining -= 1


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise TigerSyncError("TIGER_SYNC_DATE_INVALID") from exc


def date_windows(start: str, end: str, *, max_days: int = MAX_WINDOW_DAYS) -> list[tuple[str, str]]:
    first = _date(start)
    last = _date(end)
    if last < first:
        raise TigerSyncError("TIGER_SYNC_WINDOW_INVALID")
    result = []
    cursor = first
    while cursor <= last:
        window_end = min(cursor + timedelta(days=max_days - 1), last)
        result.append((cursor.isoformat(), window_end.isoformat()))
        cursor = window_end + timedelta(days=1)
    return result


def _epoch_millis(value: str, *, end_of_day: bool = False) -> int:
    parsed = datetime.combine(_date(value), datetime.max.time() if end_of_day else datetime.min.time(), tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _error_code(exc: Exception) -> tuple[str, bool]:
    message = str(exc).casefold()
    if any(token in message for token in ("429", "rate", "frequency", "too many")):
        return "TIGER_SYNC_RATE_LIMITED", True
    if any(token in message for token in ("timeout", "timed out", "temporarily")):
        return "TIGER_SYNC_TIMEOUT", True
    if isinstance(exc, TigerSyncError):
        return str(exc), False
    return "TIGER_SYNC_PROVIDER_FAILURE", False


def _call_with_retry(
    function: Callable[..., Any],
    *,
    budget: RequestBudget,
    sleeper: Callable[[float], None],
    attempts: int = 3,
    **kwargs: Any,
) -> Any:
    last: Exception | None = None
    for attempt in range(attempts):
        budget.consume()
        try:
            return function(**kwargs)
        except Exception as exc:  # provider exception types stay behind the adapter boundary
            last = exc
            code, retryable = _error_code(exc)
            if not retryable or attempt + 1 == attempts:
                raise TigerSyncError(code) from exc
            sleeper(0.25 * (2 ** attempt))
    raise TigerSyncError("TIGER_SYNC_PROVIDER_FAILURE") from last


def _token_pages(
    function: Callable[..., Any],
    *,
    budget: RequestBudget,
    sleeper: Callable[[float], None],
    kwargs: dict[str, Any],
) -> tuple[list[Any], int, bool]:
    collected: list[Any] = []
    token = ""  # official SDK returns the response wrapper only when page_token is not None
    seen: set[str] = set()
    next_seen = False
    for page_count in range(1, MAX_PAGES_PER_WINDOW + 1):
        response = _call_with_retry(function, budget=budget, sleeper=sleeper, page_token=token, **kwargs)
        collected.extend(rows(response))
        candidate = next_page_token(response)
        if not candidate:
            return collected, page_count, next_seen
        next_seen = True
        if candidate in seen or candidate == token:
            raise TigerSyncError("TIGER_SYNC_REPEATED_CURSOR")
        seen.add(candidate)
        token = candidate
    raise TigerSyncError("TIGER_SYNC_PAGE_BUDGET_EXHAUSTED")


def _append_records(ledger: object, records: Iterable[dict[str, Any]]) -> tuple[dict[str, int], int, int]:
    counts: dict[str, int] = {}
    duplicates = revisions = 0
    for record in records:
        result = ledger.append_activity(record)
        counts[record["activity_type"]] = counts.get(record["activity_type"], 0) + 1
        duplicates += result.status == "OBSERVED"
        revisions += result.status == "REVISED"
    return counts, duplicates, revisions


def _window_receipt(
    *, category: str, start: str, end: str, status: str, page_count: int,
    record_count: int, next_token_seen: bool,
) -> dict[str, Any]:
    return {
        "category": category,
        "start": start,
        "end": end,
        "status": status,
        "page_count": page_count,
        "record_count": record_count,
        "next_token_seen": next_token_seen,
    }


def _record_window(
    ledger: object, *, account_ref: str, category: str, start: str, end: str,
    status: str, history_start: str, history_start_accuracy: str, retrieved_at: str,
    page_count: int = 0, record_count: int = 0, duplicates: int = 0,
    revisions: int = 0, gap_code: str | None = None,
) -> None:
    ledger.record_sync_window({
        "account_ref": account_ref,
        "category": category,
        "window_start": start,
        "window_end": end,
        "status": status,
        "history_start": history_start,
        "history_start_accuracy": history_start_accuracy,
        "page_count": page_count,
        "record_count": record_count,
        "duplicate_count": duplicates,
        "revision_count": revisions,
        "gap_code": gap_code,
        "retrieved_at": retrieved_at,
    })


def sync_history(
    adapter: object,
    ledger: object,
    *,
    account_ref: str,
    history_start: str,
    history_start_accuracy: str,
    window_end: str,
    retrieved_at: str,
    sleeper: Callable[[float], None] = time.sleep,
    budget_limit: int = MAX_REQUESTS_PER_SYNC,
) -> dict[str, Any]:
    if history_start_accuracy not in {"EXACT", "APPROXIMATE"}:
        raise TigerSyncError("TIGER_SYNC_HISTORY_ACCURACY_INVALID")
    budget = RequestBudget(budget_limit)
    batch_id = f"tiger-sync:{uuid4().hex}"
    receipts: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    duplicate_total = revision_total = 0

    for start, end in date_windows(history_start, window_end):
        category = "ORDERS_EXECUTIONS_CHARGES"
        page_count = 0
        next_seen = False
        try:
            orders, order_pages, order_next = _token_pages(
                adapter.orders, budget=budget, sleeper=sleeper,
                # Official get_orders treats end_time as exclusive.  Receipts use
                # inclusive calendar windows, so query through the following day.
                kwargs={
                    "start_time": start,
                    "end_time": (_date(end) + timedelta(days=1)).isoformat(),
                    "limit": PAGE_SIZE,
                },
            )
            page_count += order_pages
            next_seen |= order_next
            normalized: list[dict[str, Any]] = []
            for order in orders:
                order_record = normalize_order(order, account_ref=account_ref, retrieved_at=retrieved_at, batch_id=batch_id)
                normalized.append(order_record)
                if float(order_record.get("filled_quantity") or 0) > 0:
                    order_id = order_record.get("order_id")
                    if not order_id:
                        raise TigerSyncError("TIGER_SYNC_FILLED_ORDER_ID_MISSING")
                    transactions, transaction_pages, transaction_next = _token_pages(
                        adapter.transactions, budget=budget, sleeper=sleeper,
                        kwargs={
                            "start_time": _epoch_millis(start),
                            "end_time": _epoch_millis(end, end_of_day=True),
                            "order_id": int(order_id),
                            "limit": PAGE_SIZE,
                        },
                    )
                    page_count += transaction_pages
                    next_seen |= transaction_next
                    normalized.extend(
                        normalize_execution(item, account_ref=account_ref, retrieved_at=retrieved_at, batch_id=batch_id, order_id=order_id)
                        for item in transactions
                    )
                    detail = _call_with_retry(
                        adapter.order_with_charges, budget=budget, sleeper=sleeper, order_id=int(order_id),
                    )
                    normalized.extend(normalize_charges(detail, account_ref=account_ref, retrieved_at=retrieved_at, batch_id=batch_id))
            counts, duplicates, revisions = _append_records(ledger, normalized)
            for name, count in counts.items():
                totals[name] = totals.get(name, 0) + count
            duplicate_total += duplicates
            revision_total += revisions
            receipt = _window_receipt(
                category=category, start=start, end=end, status="COMPLETE", page_count=page_count,
                record_count=len(normalized), next_token_seen=next_seen,
            )
            receipts.append(receipt)
            _record_window(
                ledger, account_ref=account_ref, category=category, start=start, end=end,
                status="COMPLETE", history_start=history_start,
                history_start_accuracy=history_start_accuracy, retrieved_at=retrieved_at,
                page_count=page_count, record_count=len(normalized), duplicates=duplicates, revisions=revisions,
            )
        except Exception as exc:
            code, retryable = _error_code(exc)
            receipts.append(_window_receipt(
                category=category, start=start, end=end, status="FAILED", page_count=page_count,
                record_count=0, next_token_seen=next_seen,
            ))
            gaps.append({"category": category, "start": start, "end": end, "error_code": code, "retryable": retryable})
            _record_window(
                ledger, account_ref=account_ref, category=category, start=start, end=end,
                status="FAILED", history_start=history_start,
                history_start_accuracy=history_start_accuracy, retrieved_at=retrieved_at, gap_code=code,
            )

    for start, end in date_windows(history_start, window_end):
        category = "ASSET_POINTS"
        try:
            response = _call_with_retry(
                adapter.analytics_asset, budget=budget, sleeper=sleeper,
                start_date=start, end_date=end, currency="USD",
            )
            points = [
                normalize_asset_point(item, account_ref=account_ref, retrieved_at=retrieved_at, batch_id=batch_id)
                for item in rows(response)
            ]
            duplicates = revisions = 0
            for point in points:
                result = ledger.append_asset_point(point)
                duplicates += result.status == "OBSERVED"
                revisions += result.status == "REVISED"
            totals["ASSET_POINT"] = totals.get("ASSET_POINT", 0) + len(points)
            duplicate_total += duplicates
            revision_total += revisions
            receipts.append(_window_receipt(category=category, start=start, end=end, status="COMPLETE", page_count=1, record_count=len(points), next_token_seen=False))
            _record_window(
                ledger, account_ref=account_ref, category=category, start=start, end=end,
                status="COMPLETE", history_start=history_start, history_start_accuracy=history_start_accuracy,
                retrieved_at=retrieved_at, page_count=1, record_count=len(points),
                duplicates=duplicates, revisions=revisions,
            )
        except Exception as exc:
            code, retryable = _error_code(exc)
            receipts.append(_window_receipt(category=category, start=start, end=end, status="FAILED", page_count=0, record_count=0, next_token_seen=False))
            gaps.append({"category": category, "start": start, "end": end, "error_code": code, "retryable": retryable})
            _record_window(
                ledger, account_ref=account_ref, category=category, start=start, end=end,
                status="FAILED", history_start=history_start, history_start_accuracy=history_start_accuracy,
                retrieved_at=retrieved_at, gap_code=code,
            )

    for category, loader, normalizer in (
        ("FUND_DETAILS", "fund_details", normalize_fund_detail),
        ("FUNDING_HISTORY", "funding_history", normalize_funding),
    ):
        try:
            raw: list[Any] = []
            page_count = 0
            if loader == "fund_details":
                for page in range(MAX_PAGES_PER_WINDOW):
                    response = _call_with_retry(
                        adapter.fund_details, budget=budget, sleeper=sleeper,
                        start=page * PAGE_SIZE, limit=PAGE_SIZE,
                        start_date=history_start, end_date=window_end,
                    )
                    page_rows = rows(response)
                    raw.extend(page_rows)
                    page_count += 1
                    if len(page_rows) < PAGE_SIZE:
                        break
                else:
                    raise TigerSyncError("TIGER_SYNC_PAGE_BUDGET_EXHAUSTED")
            else:
                raw = rows(_call_with_retry(adapter.funding_history, budget=budget, sleeper=sleeper))
                page_count = 1
            normalized = [
                normalizer(item, account_ref=account_ref, retrieved_at=retrieved_at, batch_id=batch_id)
                for item in raw
            ]
            counts, duplicates, revisions = _append_records(ledger, normalized)
            for name, count in counts.items():
                totals[name] = totals.get(name, 0) + count
            duplicate_total += duplicates
            revision_total += revisions
            receipts.append(_window_receipt(category=category, start=history_start, end=window_end, status="COMPLETE", page_count=page_count, record_count=len(normalized), next_token_seen=False))
            _record_window(
                ledger, account_ref=account_ref, category=category, start=history_start, end=window_end,
                status="COMPLETE", history_start=history_start, history_start_accuracy=history_start_accuracy,
                retrieved_at=retrieved_at, page_count=page_count, record_count=len(normalized),
                duplicates=duplicates, revisions=revisions,
            )
        except Exception as exc:
            code, retryable = _error_code(exc)
            receipts.append(_window_receipt(category=category, start=history_start, end=window_end, status="FAILED", page_count=0, record_count=0, next_token_seen=False))
            gaps.append({"category": category, "start": history_start, "end": window_end, "error_code": code, "retryable": retryable})
            _record_window(
                ledger, account_ref=account_ref, category=category, start=history_start, end=window_end,
                status="FAILED", history_start=history_start, history_start_accuracy=history_start_accuracy,
                retrieved_at=retrieved_at, gap_code=code,
            )

    coverage = "PARTIAL" if gaps else "API_COMPLETE_WITHIN_DECLARED_WINDOW"
    limitations = ["覆盖仅相对声明窗口和官方 API 可见历史成立，不代表账户生命周期或结单勾稽完整。"]
    if history_start_accuracy == "APPROXIMATE":
        limitations.append("历史起点为估算值，不能证明更早时期没有活动。")
    return finalize_contract({
        "schema_version": "broker-sync-manifest/1.0.0",
        "sync_id": batch_id,
        "account_ref": account_ref,
        "source_id": "tiger:tbhk:history-sync",
        "as_of": f"{window_end}T23:59:59Z",
        "retrieved_at": retrieved_at,
        "provider": "TIGER_TBHK",
        "sdk_version": SDK_VERSION,
        "history_start": history_start,
        "history_start_accuracy": history_start_accuracy,
        "window_start": history_start,
        "window_end": window_end,
        "coverage_status": coverage,
        "category_counts": [{"category": name, "count": count} for name, count in sorted(totals.items())],
        "windows": receipts,
        "duplicate_count": duplicate_total,
        "revision_count": revision_total,
        "gaps": gaps,
        "limitations": limitations,
    })
