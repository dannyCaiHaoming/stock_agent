"""Read-only projection of the private broker ledger for the local browser."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from product.broker.tiger.contracts import validate_contract
from product.broker.tiger.ledger import PrivateBrokerLedger, PrivateBrokerLedgerError

from .read_only import BrowserDataError


PAGE_SIZE = 50
ALLOWED_FILTERS = frozenset({"date_from", "date_to", "symbol", "market", "currency", "direction", "category", "status"})


class ReadOnlyTradeLedger:
    def __init__(self, root: Path, *, repository_root: Path):
        try:
            self._ledger = PrivateBrokerLedger(root, repository_root=repository_root, create=False, timeout=0.1)
            self._account_ref = self._ledger.account_ref()
            diagnostic = self._ledger.diagnostic()
        except PrivateBrokerLedgerError as exc:
            raise BrowserDataError(str(exc)) from exc
        self._diagnostic = {
            "status": diagnostic["status"],
            "schema_version": diagnostic["schema_version"],
            "analysis_count": diagnostic["counts"].get("analysis_packages", 0),
            "activity_revision_count": diagnostic["counts"].get("activity_revisions", 0),
        }

    def diagnostic(self) -> dict[str, Any]:
        return dict(self._diagnostic)

    @staticmethod
    def _page(value: Any) -> int:
        try:
            return max(1, min(100_000, int(value)))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _filters(query: Mapping[str, str]) -> dict[str, str]:
        result = {}
        for key in ALLOWED_FILTERS:
            observed = str(query.get(key) or "").strip()
            if observed:
                result[key] = observed[:128]
        return result

    @staticmethod
    def _matches(item: Mapping[str, Any], filters: Mapping[str, str]) -> bool:
        date_value = str(item.get("market_date") or "")
        if filters.get("date_from") and date_value < filters["date_from"]:
            return False
        if filters.get("date_to") and date_value > filters["date_to"]:
            return False
        exact = {
            "symbol": "display_symbol", "market": "market", "currency": "currency",
            "direction": "direction", "category": "activity_type", "status": "status",
        }
        return all(
            str(item.get(field) or "").casefold() == filters[key].casefold()
            for key, field in exact.items() if key in filters
        )

    @staticmethod
    def _project(item: Mapping[str, Any]) -> dict[str, Any]:
        ledger = item.get("_ledger") if isinstance(item.get("_ledger"), Mapping) else {}
        return {
            "record_id": ledger.get("record_id"),
            "revision": ledger.get("revision"),
            "date": item.get("market_date"),
            "time": item.get("occurred_at_utc"),
            "category": item.get("activity_type"),
            "symbol": item.get("display_symbol"),
            "market": item.get("market"),
            "currency": item.get("currency"),
            "direction": item.get("direction"),
            "status": item.get("status"),
            "quantity": item.get("quantity"),
            "price": item.get("price"),
            "amount": item.get("amount"),
            "order_id": item.get("order_id"),
        }

    def page(self, *, query: Mapping[str, str]) -> dict[str, Any]:
        try:
            account_ref = self._account_ref
            requested_id = str(query.get("analysis") or "")
            analysis = self._ledger.analysis(account_ref=account_ref, analysis_id=requested_id) if requested_id else self._ledger.latest_analysis(account_ref=account_ref)
            versions = self._ledger.list_analyses(account_ref=account_ref)
            if analysis is None:
                return {"status": "NO_ANALYSIS", "versions": versions, "filters": self._filters(query), "items": [], "total": 0, "page": 1, "pages": 0}
            validate_contract(analysis)
            filters = self._filters(query)
            activities = self._ledger.read_current_activities(account_ref=account_ref, cutoff=analysis["as_of"])
            matched = [item for item in activities if self._matches(item, filters)]
            matched.sort(key=lambda item: (item.get("occurred_at_utc") or item.get("as_of") or "", item.get("activity_type") or "", (item.get("_ledger") or {}).get("record_id") or ""), reverse=True)
            page = self._page(query.get("page"))
            start = (page - 1) * PAGE_SIZE
            items = [self._project(item) for item in matched[start:start + PAGE_SIZE]]
            return {
                "status": "READY",
                "account_ref": account_ref,
                "analysis": analysis,
                "versions": versions,
                "filters": filters,
                "items": items,
                "total": len(matched),
                "page": page,
                "pages": (len(matched) + PAGE_SIZE - 1) // PAGE_SIZE,
                "per_page": PAGE_SIZE,
            }
        except (PrivateBrokerLedgerError, ValueError) as exc:
            code = str(exc)
            if not code.startswith(("BROKER_LEDGER_", "TIGER_CONTRACT_", "SCHEMA_")):
                code = "BROKER_LEDGER_READ_FAILED"
            raise BrowserDataError(code) from exc
