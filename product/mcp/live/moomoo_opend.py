"""Moomoo Singapore 官方 OpenD Quote API 的只读、fail-closed 边界。

本模块只连接 loopback OpenD，只暴露版本化清单中的 Quote API。账号登录、
问卷和协议完全由用户在 OpenD 中管理；模块不接受 Cookie、Token、密码、
交易解锁信息，也不构造任何 Trade Context。
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import importlib
import importlib.metadata
import ipaddress
import json
import math
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


QUOTE_MANIFEST_VERSION = "moomoo-opend-quote-manifest/1.0.0"
ADAPTER_VERSION = "moomoo-opend-quote-adapter/2.0.0"
SDK_DISTRIBUTION = "moomoo-api"
DEFAULT_MANIFEST = Path(__file__).with_name("moomoo-opend-quote-manifest.json")

_US_CODE = re.compile(r"^US\.[A-Z0-9.\-]{1,24}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SECRET_KEY = re.compile(
    r"^(?:cookie|authorization|password|passwd|token|secret|session|device_id|"
    r"account_id|access_token|refresh_token|auth_token|trade_password|unlock_password|email|phone)$",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(
    r"(?:bearer\s+[A-Za-z0-9._~-]+|(?:cookie|token|session|password)\s*[:=]\s*[^\s,;]+)",
    re.IGNORECASE,
)


class MoomooOpenDError(ValueError):
    """稳定错误码，不携带 SDK 返回的私人或认证内容。"""


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value)
    if not parts:
        raise ValueError("MOOMOO_VERSION_INVALID")
    return tuple(int(item) for item in parts)


def validate_quote_manifest(manifest: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "manifest_id", "region", "status", "sdk_distribution",
        "sdk_version", "minimum_opend_server_version", "approved_at", "capabilities",
        "manifest_hash",
    }
    if set(manifest) != required or manifest.get("schema_version") != QUOTE_MANIFEST_VERSION:
        raise ValueError("MOOMOO_OPEND_MANIFEST_SHAPE_INVALID")
    if manifest["region"] != "SG" or manifest["status"] != "APPROVED":
        raise ValueError("MOOMOO_OPEND_MANIFEST_STATUS_INVALID")
    if manifest["sdk_distribution"] != SDK_DISTRIBUTION:
        raise ValueError("MOOMOO_OPEND_SDK_DISTRIBUTION_INVALID")
    _version_tuple(manifest["sdk_version"])
    _version_tuple(manifest["minimum_opend_server_version"])
    parse_timestamp(manifest["approved_at"])
    capabilities = manifest["capabilities"]
    if not isinstance(capabilities, list) or not capabilities:
        raise ValueError("MOOMOO_OPEND_CAPABILITIES_EMPTY")
    seen: set[str] = set()
    for capability in capabilities:
        expected = {
            "capability_id", "dataset", "method", "parameter_names",
            "required_parameters", "response_kind", "response_fields", "read_only",
            "max_requests", "max_rows", "max_response_bytes", "timeout_seconds",
        }
        if not isinstance(capability, Mapping) or set(capability) != expected:
            raise ValueError("MOOMOO_OPEND_CAPABILITY_SHAPE_INVALID")
        capability_id = capability["capability_id"]
        if not isinstance(capability_id, str) or not capability_id or capability_id in seen:
            raise ValueError("MOOMOO_OPEND_CAPABILITY_ID_INVALID")
        seen.add(capability_id)
        method = capability["method"]
        if method not in _METHOD_CALLS or capability["read_only"] is not True:
            raise ValueError("MOOMOO_OPEND_METHOD_NOT_ALLOWED")
        names = capability["parameter_names"]
        required_names = capability["required_parameters"]
        if not isinstance(names, list) or len(names) != len(set(names)) or any(
            name not in _PARAMETER_VALIDATORS for name in names
        ):
            raise ValueError("MOOMOO_OPEND_PARAMETERS_INVALID")
        if not isinstance(required_names, list) or not set(required_names) <= set(names):
            raise ValueError("MOOMOO_OPEND_REQUIRED_PARAMETERS_INVALID")
        if capability["response_kind"] not in {"DICT", "DATAFRAME"}:
            raise ValueError("MOOMOO_OPEND_RESPONSE_KIND_INVALID")
        if not isinstance(capability["response_fields"], list) or not capability["response_fields"]:
            raise ValueError("MOOMOO_OPEND_RESPONSE_FIELDS_INVALID")
        limits = {
            "max_requests": 8,
            "max_rows": 10_000,
            "max_response_bytes": 8_000_000,
            "timeout_seconds": 30,
        }
        if any(
            not isinstance(capability[name], int)
            or not 0 < capability[name] <= maximum
            for name, maximum in limits.items()
        ):
            raise ValueError("MOOMOO_OPEND_BUDGET_INVALID")
    expected_hash = content_hash({key: value for key, value in manifest.items() if key != "manifest_hash"})
    if manifest["manifest_hash"] != expected_hash:
        raise ValueError("MOOMOO_OPEND_MANIFEST_HASH_MISMATCH")


def load_quote_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest = json.loads((Path(path) if path is not None else DEFAULT_MANIFEST).read_text(encoding="utf-8"))
    validate_quote_manifest(manifest)
    return manifest


def build_quote_manifest(
    *, manifest_id: str, sdk_version: str, minimum_opend_server_version: str,
    approved_at: str, capabilities: list[Mapping[str, Any]],
) -> dict[str, Any]:
    manifest = {
        "schema_version": QUOTE_MANIFEST_VERSION,
        "manifest_id": manifest_id,
        "region": "SG",
        "status": "APPROVED",
        "sdk_distribution": SDK_DISTRIBUTION,
        "sdk_version": sdk_version,
        "minimum_opend_server_version": minimum_opend_server_version,
        "approved_at": iso_utc(approved_at),
        "capabilities": [deepcopy(dict(item)) for item in capabilities],
    }
    manifest["manifest_hash"] = content_hash(manifest)
    validate_quote_manifest(manifest)
    return manifest


def _validate_code(value: Any) -> None:
    if not isinstance(value, str) or _US_CODE.fullmatch(value) is None:
        raise ValueError("MOOMOO_OPEND_SECURITY_INVALID")


def _validate_period(value: Any) -> None:
    if value not in {"INTRADAY", "DAY", "WEEK", "MONTH"}:
        raise ValueError("MOOMOO_OPEND_PERIOD_INVALID")


def _validate_date(value: Any) -> None:
    if value is not None and (not isinstance(value, str) or _DATE.fullmatch(value) is None):
        raise ValueError("MOOMOO_OPEND_DATE_INVALID")


def _validate_page_size(value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 50:
        raise ValueError("MOOMOO_OPEND_PAGE_SIZE_INVALID")


def _validate_next_key(value: Any) -> None:
    if value is not None and (
        not isinstance(value, str) or not value or len(value) > 128
    ):
        raise ValueError("MOOMOO_OPEND_NEXT_KEY_INVALID")


def _validate_holder_id(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("MOOMOO_OPEND_HOLDER_ID_INVALID")


def _validate_code_list(value: Any) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 48:
        raise ValueError("MOOMOO_OPEND_CODE_LIST_INVALID")
    for item in value:
        _validate_code(item)
    if len(value) != len(set(value)):
        raise ValueError("MOOMOO_OPEND_CODE_LIST_INVALID")


def _validate_rating_dimension(value: Any) -> None:
    if value not in {1, 2, "INSTITUTION", "ANALYST"}:
        raise ValueError("MOOMOO_OPEND_RATING_DIMENSION_INVALID")


def _validate_indicator_id(value: Any) -> None:
    approved = {
        1003000001, 1003000002, 1003000003, 1003000004,
        1003000010, 1003000007, 1003000006, 1003000026,
    }
    try:
        candidate = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("MOOMOO_OPEND_MACRO_INDICATOR_INVALID") from exc
    if candidate not in approved:
        raise ValueError("MOOMOO_OPEND_MACRO_INDICATOR_INVALID")


def _validate_region(value: Any) -> None:
    if value != "US":
        raise ValueError("MOOMOO_OPEND_REGION_INVALID")


def _validate_max_count(value: Any) -> None:
    if type(value) is not int or not 1 <= value <= 24:
        raise ValueError("MOOMOO_OPEND_MAX_COUNT_INVALID")


def _validate_calendar_count(value: Any) -> None:
    if type(value) is not int or not 1 <= value <= 100:
        raise ValueError("MOOMOO_OPEND_CALENDAR_COUNT_INVALID")


def _validate_option_market(value: Any) -> None:
    if value != "US_SECURITY":
        raise ValueError("MOOMOO_OPEND_OPTION_MARKET_INVALID")


def _validate_statistic_type(value: Any) -> None:
    if value not in {"VOLUME", "OPEN_INTEREST"}:
        raise ValueError("MOOMOO_OPEND_STATISTIC_TYPE_INVALID")
    if isinstance(value, int) and value <= 0:
        raise ValueError("MOOMOO_OPEND_HOLDER_ID_INVALID")
    if isinstance(value, str) and (not value or len(value) > 64):
        raise ValueError("MOOMOO_OPEND_HOLDER_ID_INVALID")


_PARAMETER_VALIDATORS: dict[str, Callable[[Any], None]] = {
    "code": _validate_code,
    "period_type": _validate_period,
    "start": _validate_date,
    "end": _validate_date,
    "num": _validate_page_size,
    "next_key": _validate_next_key,
    "holder_id": _validate_holder_id,
    "code_list": _validate_code_list,
    "rating_dimension_type": _validate_rating_dimension,
    "indicator_id": _validate_indicator_id,
    "region": _validate_region,
    "max_count": _validate_max_count,
    "count": _validate_calendar_count,
    "option_market": _validate_option_market,
    "data_type": _validate_statistic_type,
}


def _call_global_state(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_global_state()


def _call_company_profile(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_company_profile(params["code"])


def _call_capital_flow(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_capital_flow(
        params["code"], period_type=params.get("period_type", "INTRADAY"),
        start=params.get("start"), end=params.get("end"),
    )


def _call_analyst_consensus(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_research_analyst_consensus(params["code"])


def _call_morningstar_report(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_research_morningstar_report(params["code"])


def _call_shareholders_institutional(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_shareholders_institutional(
        params["code"], next_key=params.get("next_key"), num=params.get("num"),
    )


def _call_insider_holder_list(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_insider_holder_list(
        params["code"], next_key=params.get("next_key"), num=params.get("num"),
    )


def _call_insider_trade_list(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_insider_trade_list(
        params["code"], holder_id=params.get("holder_id"),
        num=params.get("num"), next_key=params.get("next_key"),
    )


def _call_option_expiration_date(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_option_expiration_date(params["code"])


def _call_option_chain(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_option_chain(
        params["code"], start=params.get("start"), end=params.get("end"),
    )


def _call_rating_summary(context: Any, params: Mapping[str, Any]) -> Any:
    kwargs = {"num": params.get("num"), "next_key": params.get("next_key")}
    if "rating_dimension_type" in params:
        kwargs["rating_dimension_type"] = params["rating_dimension_type"]
    return context.get_research_rating_summary(params["code"], **kwargs)


def _call_short_interest(context: Any, params: Mapping[str, Any]) -> Any:
    result = context.get_short_interest(
        params["code"], next_key=params.get("next_key"), num=params.get("num"),
    )
    if not isinstance(result, tuple) or len(result) != 3:
        raise ValueError("MOOMOO_OPEND_SHORT_INTEREST_RESPONSE_INVALID")
    ret, us_frame, _hk_frame = result
    return ret, us_frame


def _with_page_key(result: Any, error_code: str) -> Any:
    if not isinstance(result, tuple) or len(result) != 3:
        raise ValueError(error_code)
    ret, frame, page_key = result
    if hasattr(frame, "attrs"):
        frame.attrs["next_key"] = page_key
    return ret, frame


def _call_market_snapshot(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_market_snapshot(params["code_list"])


def _call_capital_distribution(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_capital_distribution(params["code"])


def _call_revenue_breakdown(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_financials_revenue_breakdown(params["code"])


def _call_company_executives(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_company_executives(params["code"])


def _call_rise_fall_distribution(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_rise_fall_distribution(params["region"])


def _call_option_underlying_overview(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_option_underlying_overview(params["code_list"])


def _call_option_underlying_history(context: Any, params: Mapping[str, Any]) -> Any:
    return _with_page_key(context.get_option_underlying_his_statistic(
        params["code"], params.get("start"), params.get("end"),
    ), "MOOMOO_OPEND_OPTION_HISTORY_RESPONSE_INVALID")


def _call_option_underlying_volatility(context: Any, params: Mapping[str, Any]) -> Any:
    return _with_page_key(context.get_option_underlying_his_volatility(
        params["code"], params.get("start"), params.get("end"),
    ), "MOOMOO_OPEND_OPTION_VOLATILITY_RESPONSE_INVALID")


def _call_option_market_statistic(context: Any, params: Mapping[str, Any]) -> Any:
    return _with_page_key(context.get_option_market_statistic(
        params["option_market"], params["data_type"],
        params.get("start"), params.get("end"),
    ), "MOOMOO_OPEND_OPTION_MARKET_RESPONSE_INVALID")


def _call_macro_indicator_list(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_macro_indicator_list(params["region"])


def _call_macro_indicator_history(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_macro_indicator_history(
        int(params["indicator_id"]), max_count=params.get("max_count", 24),
    )


def _call_fedwatch_target_rate(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_fed_watch_target_rate()


def _call_fedwatch_dot_plot(context: Any, params: Mapping[str, Any]) -> Any:
    return context.get_fed_watch_dot_plot()


def _call_economic_calendar(context: Any, params: Mapping[str, Any]) -> Any:
    result = context.get_economic_calendar(
        params.get("start"), params.get("end"), market_list=["US"],
        count=params.get("count", 100),
    )
    if not isinstance(result, tuple) or len(result) != 4:
        raise ValueError("MOOMOO_OPEND_ECONOMIC_CALENDAR_RESPONSE_INVALID")
    ret, frame, next_page, has_more = result
    if hasattr(frame, "attrs"):
        frame.attrs.update({"next_page": next_page, "has_more": bool(has_more)})
    return ret, frame


_METHOD_CALLS: dict[str, Callable[[Any, Mapping[str, Any]], Any]] = {
    "get_global_state": _call_global_state,
    "get_company_profile": _call_company_profile,
    "get_capital_flow": _call_capital_flow,
    "get_research_analyst_consensus": _call_analyst_consensus,
    "get_research_morningstar_report": _call_morningstar_report,
    "get_shareholders_institutional": _call_shareholders_institutional,
    "get_insider_holder_list": _call_insider_holder_list,
    "get_insider_trade_list": _call_insider_trade_list,
    "get_option_expiration_date": _call_option_expiration_date,
    "get_option_chain": _call_option_chain,
    "get_research_rating_summary": _call_rating_summary,
    "get_short_interest": _call_short_interest,
    "get_market_snapshot": _call_market_snapshot,
    "get_capital_distribution": _call_capital_distribution,
    "get_financials_revenue_breakdown": _call_revenue_breakdown,
    "get_company_executives": _call_company_executives,
    "get_rise_fall_distribution": _call_rise_fall_distribution,
    "get_option_underlying_overview": _call_option_underlying_overview,
    "get_option_underlying_his_statistic": _call_option_underlying_history,
    "get_option_underlying_his_volatility": _call_option_underlying_volatility,
    "get_option_market_statistic": _call_option_market_statistic,
    "get_macro_indicator_list": _call_macro_indicator_list,
    "get_macro_indicator_history": _call_macro_indicator_history,
    "get_fed_watch_target_rate": _call_fedwatch_target_rate,
    "get_fed_watch_dot_plot": _call_fedwatch_dot_plot,
    "get_economic_calendar": _call_economic_calendar,
}


def scan_committable_payload(value: Any, *, path: str = "$") -> None:
    """拒绝认证/私人账户材料；公开公司、机构及 SEC 人名不受影响。"""

    if isinstance(value, Mapping):
        for key, item in value.items():
            if _SECRET_KEY.fullmatch(str(key)):
                raise ValueError(f"RESEARCH_SECRET_MATERIAL_REJECTED:{path}.{key}")
            scan_committable_payload(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            scan_committable_payload(item, path=f"{path}[{index}]")
    elif isinstance(value, str) and _SECRET_TEXT.search(value):
        raise ValueError(f"RESEARCH_SECRET_MATERIAL_REJECTED:{path}")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (ValueError, TypeError):
            pass
    return str(value)


def serialize_quote_result(value: Any, *, response_kind: str) -> tuple[dict[str, Any], bytes]:
    if response_kind == "DATAFRAME":
        if not hasattr(value, "columns") or not hasattr(value, "to_dict"):
            raise ValueError("MOOMOO_OPEND_RESPONSE_KIND_MISMATCH")
        payload = {
            "kind": "DATAFRAME",
            "columns": [str(column) for column in value.columns],
            "dtypes": {str(key): str(item) for key, item in value.dtypes.items()},
            "rows": _json_value(value.to_dict(orient="records")),
            "attrs": _json_value(dict(getattr(value, "attrs", {}))),
        }
    elif response_kind == "DICT":
        if not isinstance(value, Mapping):
            raise ValueError("MOOMOO_OPEND_RESPONSE_KIND_MISMATCH")
        payload = {"kind": "DICT", "value": _json_value(value)}
    else:
        raise ValueError("MOOMOO_OPEND_RESPONSE_KIND_INVALID")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return payload, raw


def _payload_row_count(payload: Mapping[str, Any]) -> int:
    if payload.get("kind") == "DATAFRAME":
        return len(payload.get("rows", []))

    def count_lists(value: Any) -> int:
        if isinstance(value, list):
            return len(value) + sum(count_lists(item) for item in value)
        if isinstance(value, Mapping):
            return sum(count_lists(item) for item in value.values())
        return 0

    return max(1, count_lists(payload.get("value")))


def _runtime_sdk_version() -> str:
    return importlib.metadata.version(SDK_DISTRIBUTION)


def _default_context_factory(host: str, port: int) -> Any:
    module = importlib.import_module("moomoo")
    return module.OpenQuoteContext(host=host, port=port)


class MoomooOpenDQuoteClient:
    """严格 Quote-only 客户端；不暴露任意 SDK 方法或 Trade Context。"""

    def __init__(
        self, *, manifest: Mapping[str, Any], host: str = "127.0.0.1", port: int = 11111,
        context_factory: Callable[[str, int], Any] | None = None,
        sdk_version_loader: Callable[[], str] = _runtime_sdk_version,
        cache: Any | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        validate_quote_manifest(manifest)
        if not _is_loopback(host):
            raise ValueError("MOOMOO_OPEND_REMOTE_HOST_REJECTED")
        if not isinstance(port, int) or not 0 < port <= 65535:
            raise ValueError("MOOMOO_OPEND_PORT_INVALID")
        self.manifest = deepcopy(dict(manifest))
        self.host = host
        self.port = port
        self.context_factory = context_factory or _default_context_factory
        self.sdk_version_loader = sdk_version_loader
        self.cache = cache
        self.now = now
        self.requests = {item["capability_id"]: 0 for item in manifest["capabilities"]}
        self.total_requests = 0
        self.open_circuits: set[str] = set()
        self.events: list[dict[str, Any]] = []
        self.server_version: str | None = None
        self._readiness_approved = False

    def _capability(self, capability_id: str) -> Mapping[str, Any]:
        capability = next(
            (item for item in self.manifest["capabilities"] if item["capability_id"] == capability_id),
            None,
        )
        if capability is None:
            raise ValueError("MOOMOO_OPEND_CAPABILITY_UNKNOWN")
        return capability

    def _validate_params(self, capability: Mapping[str, Any], params: Mapping[str, Any]) -> None:
        names = set(capability["parameter_names"])
        if not isinstance(params, Mapping) or set(params) - names \
                or not set(capability["required_parameters"]) <= set(params):
            raise ValueError("MOOMOO_OPEND_REQUEST_PARAMETERS_INVALID")
        for name, value in params.items():
            _PARAMETER_VALIDATORS[name](value)
        if params.get("start") and params.get("end") and params["start"] > params["end"]:
            raise ValueError("MOOMOO_OPEND_DATE_RANGE_INVALID")
        method = capability["method"]
        if method == "get_research_rating_summary" and params.get("num", 20) > 20:
            raise ValueError("MOOMOO_OPEND_RATING_PAGE_SIZE_INVALID")
        if params.get("start") and params.get("end"):
            days = (date.fromisoformat(params["end"]) - date.fromisoformat(params["start"])).days
            limits = {
                "get_option_underlying_his_statistic": 31,
                "get_option_underlying_his_volatility": 31,
                "get_option_market_statistic": 31,
                "get_economic_calendar": 37,
                "get_option_chain": 120,
            }
            if method in limits and days > limits[method]:
                raise ValueError("MOOMOO_OPEND_DATE_WINDOW_EXCEEDED")

    def _sdk_version(self) -> str:
        version = self.sdk_version_loader()
        if version != self.manifest["sdk_version"]:
            raise MoomooOpenDError("MOOMOO_SDK_VERSION_UNSUPPORTED")
        return version

    def _connect(self) -> Any:
        try:
            return self.context_factory(self.host, self.port)
        except (OSError, TimeoutError, ConnectionError) as exc:
            raise MoomooOpenDError("MOOMOO_OPEND_UNREACHABLE") from exc

    def read(self, *, capability_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        capability = self._capability(capability_id)
        if capability_id in self.open_circuits:
            raise MoomooOpenDError("MOOMOO_OPEND_CAPABILITY_CIRCUIT_OPEN")
        self._validate_params(capability, params)
        if self.requests[capability_id] >= capability["max_requests"]:
            raise MoomooOpenDError("MOOMOO_OPEND_REQUEST_BUDGET_EXHAUSTED")
        if self.total_requests >= 25:
            raise MoomooOpenDError("MOOMOO_OPEND_BATCH_REQUEST_BUDGET_EXHAUSTED")
        sdk_version = self._sdk_version()
        if capability_id != "global-state-v1" and not self._readiness_approved:
            raise MoomooOpenDError("MOOMOO_OPEND_READINESS_REQUIRED")
        self.requests[capability_id] += 1
        self.total_requests += 1
        started_dt = self.now()
        context = self._connect()
        try:
            ret, value = _METHOD_CALLS[capability["method"]](context, params)
        except AttributeError as exc:
            self.open_circuits.add(capability_id)
            raise MoomooOpenDError("MOOMOO_OPEND_METHOD_UNAVAILABLE") from exc
        except (OSError, TimeoutError, ConnectionError) as exc:
            self.open_circuits.add(capability_id)
            raise MoomooOpenDError("MOOMOO_OPEND_CALL_FAILED") from exc
        finally:
            try:
                context.close()
            except Exception:
                pass
        completed_dt = self.now()
        elapsed = (completed_dt - started_dt).total_seconds()
        if elapsed > capability["timeout_seconds"]:
            self.open_circuits.add(capability_id)
            raise MoomooOpenDError("MOOMOO_OPEND_TIME_BUDGET_EXCEEDED")
        event = {
            "capability_id": capability_id,
            "method": capability["method"],
            "parameter_names": sorted(params),
            "started_at": iso_utc(started_dt),
            "completed_at": iso_utc(completed_dt),
            "ret_code": ret,
        }
        self.events.append(event)
        if ret != 0:
            event["status"] = "FAILED"
            self.open_circuits.add(capability_id)
            message = str(value).lower()
            if any(word in message for word in ("rate limit", "too many", "frequency")):
                raise MoomooOpenDError("MOOMOO_RATE_LIMITED")
            if any(word in message for word in ("permission", "authority", "right", "entitlement")):
                raise MoomooOpenDError("MOOMOO_ENTITLEMENT_REQUIRED")
            raise MoomooOpenDError("MOOMOO_QUOTE_CALL_FAILED")
        payload, raw = serialize_quote_result(value, response_kind=capability["response_kind"])
        fields = set(payload["columns"] if payload["kind"] == "DATAFRAME" else payload["value"])
        if not set(capability["response_fields"]) <= fields:
            self.open_circuits.add(capability_id)
            raise MoomooOpenDError("MOOMOO_OPEND_RESPONSE_SCHEMA_DRIFT")
        row_count = _payload_row_count(payload)
        if row_count > capability["max_rows"] or len(raw) > capability["max_response_bytes"]:
            self.open_circuits.add(capability_id)
            raise MoomooOpenDError("MOOMOO_OPEND_RESPONSE_BUDGET_EXCEEDED")
        scan_committable_payload(payload)
        security_code = params.get("code")
        security_codes = set(params.get("code_list", []))
        if security_code is not None:
            candidate_codes: set[str] = set()
            if capability["method"] == "get_option_chain":
                candidate_codes.update(
                    str(row["stock_owner"]) for row in payload["rows"]
                    if row.get("stock_owner") is not None
                )
            elif payload["kind"] == "DICT":
                candidate_codes.update(
                    str(payload["value"][key]) for key in ("code", "symbol")
                    if payload["value"].get(key) is not None
                )
            else:
                for row in payload["rows"]:
                    candidate_codes.update(
                        str(row[key]) for key in ("code", "symbol") if row.get(key) is not None
                    )
            if candidate_codes and candidate_codes != {security_code}:
                self.open_circuits.add(capability_id)
                raise MoomooOpenDError("MOOMOO_OPEND_RESPONSE_SECURITY_MISMATCH")
        elif security_codes:
            candidate_codes = {
                str(row.get("stock_owner") or row.get("code"))
                for row in payload.get("rows", [])
                if row.get("stock_owner") or row.get("code")
            }
            if capability["method"] == "get_market_snapshot":
                candidate_codes = {code for code in candidate_codes if code in security_codes}
            if candidate_codes and not candidate_codes <= security_codes:
                self.open_circuits.add(capability_id)
                raise MoomooOpenDError("MOOMOO_OPEND_RESPONSE_SECURITY_MISMATCH")
        raw_hash = hashlib.sha256(raw).hexdigest()
        result = {
            "adapter_version": ADAPTER_VERSION,
            "manifest_hash": self.manifest["manifest_hash"],
            "region": "SG",
            "security_market": "US" if security_code or security_codes else None,
            "security_code": security_code,
            "security_codes": sorted(security_codes),
            "dataset": capability["dataset"],
            "capability_id": capability_id,
            "method": capability["method"],
            "sdk_version": sdk_version,
            "server_version": self.server_version,
            "retrieved_at": iso_utc(completed_dt),
            "raw_content_hash": raw_hash,
            "payload": payload,
        }
        if capability_id == "global-state-v1":
            server_version = str(payload["value"]["server_ver"])
            if _version_tuple(server_version) < _version_tuple(
                self.manifest["minimum_opend_server_version"]
            ):
                raise MoomooOpenDError("MOOMOO_OPEND_VERSION_UNSUPPORTED")
            result["server_version"] = server_version
        if self.cache is not None:
            record = self.cache.store({
                "provider": "moomoo_sg",
                "transport": "opend_loopback",
                "manifest_hash": self.manifest["manifest_hash"],
                "capability_id": capability_id,
                "method": capability["method"],
                "params": dict(params),
            }, raw, retrieved_at=result["retrieved_at"])
            if record["raw_content_hash"] != raw_hash:
                raise MoomooOpenDError("MOOMOO_OPEND_CACHE_HASH_MISMATCH")
            self.cache.read(record)
            result["record"] = record
        event["status"] = "FETCHED"
        event["raw_content_hash"] = raw_hash
        return result

    def readiness(self) -> dict[str, Any]:
        self._readiness_approved = False
        self.server_version = None
        result = self.read(capability_id="global-state-v1", params={})
        state = result["payload"]["value"]
        server_version = str(state["server_ver"])
        if _version_tuple(server_version) < _version_tuple(self.manifest["minimum_opend_server_version"]):
            raise MoomooOpenDError("MOOMOO_OPEND_VERSION_UNSUPPORTED")
        if state.get("program_status_type") != "READY":
            raise MoomooOpenDError("MOOMOO_OPEND_NOT_READY")
        if state.get("qot_logined") is not True:
            raise MoomooOpenDError("MOOMOO_QUOTE_NOT_LOGGED_IN")
        self.server_version = server_version
        self._readiness_approved = True
        return {
            "status": "OPEND_QUOTE_FEASIBLE",
            "region": "SG",
            "host": self.host,
            "port": self.port,
            "server_version": server_version,
            "sdk_version": result["sdk_version"],
            "retrieved_at": result["retrieved_at"],
            "raw_content_hash": result["raw_content_hash"],
        }
