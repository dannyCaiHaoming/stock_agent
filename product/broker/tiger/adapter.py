"""Hard allow-listed wrapper around the official Tiger OpenAPI client."""

from __future__ import annotations

from copy import deepcopy
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from .config import preflight_config


MANIFEST_PATH = Path(__file__).with_name("capability-manifest.json")
ALL_ORDER_STATES = (
    "PendingNew", "Initial", "Submitted", "PartiallyFilled", "Filled",
    "Cancelled", "PendingCancel", "Inactive", "Invalid",
)


class TigerAdapterError(ValueError):
    """Stable read-only adapter contract error."""


def load_capability_manifest() -> dict[str, Any]:
    value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if value.get("sdk_version") != "3.8.0":
        raise TigerAdapterError("TIGER_SDK_VERSION_MANIFEST_INVALID")
    capabilities = value.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        raise TigerAdapterError("TIGER_CAPABILITY_MANIFEST_INVALID")
    methods = {item.get("sdk_method") for item in capabilities if isinstance(item, Mapping)}
    forbidden = set(value.get("forbidden_sdk_methods") or [])
    if None in methods or methods & forbidden:
        raise TigerAdapterError("TIGER_CAPABILITY_ALLOWLIST_INVALID")
    if not all(item.get("read_only") is True for item in capabilities):
        raise TigerAdapterError("TIGER_CAPABILITY_NOT_READ_ONLY")
    return value


class TigerReadOnlyAdapter:
    """Expose only approved reads; never expose a generic SDK call or client getter."""

    def __init__(self, client: object, *, sdk_version: str, manifest: Mapping[str, Any] | None = None):
        self.__client = client
        self.sdk_version = sdk_version
        self.manifest = deepcopy(dict(manifest or load_capability_manifest()))
        if sdk_version != self.manifest["sdk_version"]:
            raise TigerAdapterError("TIGER_SDK_VERSION_MISMATCH")
        self.calls: list[dict[str, Any]] = []

    @classmethod
    def from_config(cls, config_dir: Path, *, repository_root: Path) -> "TigerReadOnlyAdapter":
        result = preflight_config(config_dir, repository_root=repository_root)
        if result.status != "READY":
            raise TigerAdapterError(result.code)
        credential_environment = {
            "TIGEROPEN_TIGER_ID", "TIGEROPEN_ACCOUNT", "TIGEROPEN_SECRET_KEY",
            "TIGEROPEN_PRIVATE_KEY", "TIGEROPEN_LICENSE", "TIGEROPEN_TOKEN",
            "TIGEROPEN_PROPS_PATH",
        }
        if any(os.environ.get(name) for name in credential_environment):
            raise TigerAdapterError("TIGER_ENV_CREDENTIALS_REJECTED")
        try:
            version = importlib.metadata.version("tigeropen")
        except importlib.metadata.PackageNotFoundError as exc:
            raise TigerAdapterError("TIGER_SDK_NOT_INSTALLED") from exc
        if version != "3.8.0":
            raise TigerAdapterError("TIGER_SDK_VERSION_MISMATCH")
        config_module = importlib.import_module("tigeropen.tiger_open_config")
        trade_module = importlib.import_module("tigeropen.trade.trade_client")
        config = config_module.TigerOpenClientConfig(
            props_path=str(Path(config_dir).resolve()), enable_dynamic_domain=False,
        )
        config.token_refresh_duration = 0
        return cls(trade_module.TradeClient(config), sdk_version=version)

    @staticmethod
    def _count(value: object) -> int | None:
        if value is None:
            return 0
        try:
            return len(value)  # type: ignore[arg-type]
        except TypeError:
            result = getattr(value, "result", None)
            try:
                return len(result) if result is not None else 1
            except TypeError:
                return 1

    def _read(self, operation: str, sdk_method: str, **kwargs: Any) -> Any:
        allowed = {
            item["operation"]: item["sdk_method"]
            for item in self.manifest["capabilities"]
        }
        if allowed.get(operation) != sdk_method:
            raise TigerAdapterError("TIGER_METHOD_NOT_ALLOWED")
        method = getattr(self.__client, sdk_method, None)
        if not callable(method):
            raise TigerAdapterError("TIGER_SDK_METHOD_MISSING")
        value = method(**kwargs)
        self.calls.append({
            "operation": operation,
            "parameter_names": sorted(kwargs),
            "result_count": self._count(value),
        })
        return value

    def managed_accounts(self) -> Any:
        return self._read("managed_accounts", "get_managed_accounts")

    def prime_assets(self, *, base_currency: str = "USD", consolidated: bool = True) -> Any:
        return self._read(
            "prime_assets", "get_prime_assets",
            base_currency=base_currency, consolidated=consolidated,
        )

    def positions(self, *, sec_type: str, currency: str = "ALL", market: str = "ALL") -> Any:
        return self._read(
            "positions", "get_positions",
            sec_type=sec_type, currency=currency, market=market,
        )

    def analytics_asset(self, *, start_date: str, end_date: str, currency: str = "USD") -> Any:
        return self._read(
            "analytics_asset", "get_analytics_asset",
            start_date=start_date, end_date=end_date, seg_type="SEC", currency=currency,
        )

    def orders(self, *, start_time: str, end_time: str, page_token: str | None = None, limit: int = 100) -> Any:
        return self._read(
            "orders", "get_orders",
            start_time=start_time, end_time=end_time, limit=limit, is_brief=False,
            states=list(ALL_ORDER_STATES), seg_type="SEC", page_token=page_token,
        )

    def order_with_charges(self, *, order_id: int) -> Any:
        return self._read(
            "order_with_charges", "get_order",
            id=order_id, is_brief=False, show_charges=True,
        )

    def transactions(
        self, *, start_time: int, end_time: int, page_token: str | None = None,
        order_id: int | None = None, limit: int = 100,
    ) -> Any:
        return self._read(
            "transactions", "get_transactions",
            start_time=start_time, end_time=end_time, page_token=page_token,
            order_id=order_id, limit=limit,
        )

    def fund_details(
        self, *, start: int = 0, limit: int = 100,
        start_date: str | None = None, end_date: str | None = None,
    ) -> Any:
        return self._read(
            "fund_details", "get_fund_details",
            seg_types=["SEC"], start=start, limit=limit,
            start_date=start_date, end_date=end_date,
        )

    def funding_history(self) -> Any:
        return self._read("funding_history", "get_funding_history", seg_type="SEC")

    def call(self, *_args: object, **_kwargs: object) -> None:
        raise TigerAdapterError("TIGER_METHOD_NOT_ALLOWED")
