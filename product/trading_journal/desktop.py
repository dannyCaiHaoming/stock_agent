"""Fixed, local-process Tiger desktop collection; no general UI automation API.

The native bridge filters layout labels before returning them, and only reads
financial cells after version, window, history page and table identity checks.
An unverified client stays blocked; discovery is not collection acceptance.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
import platform
import re
import stat
import subprocess
import tempfile
import time
from typing import Callable, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import JournalError, canonical_hash, canonical_json, iso_datetime, utc_now

BUNDLE_ID = "com.itiger.TigerTrade-Mac"
COLLECTION_ACTIONS = frozenset({"open_app", "read_history_view", "set_history_window", "read_next_page", "export_history"})
DISCOVERY_ACTIONS = frozenset({"probe", "inspect_layout"})
NAVIGATION_ACTIONS = frozenset({"navigate_history"})
NAVIGATION_TARGETS = frozenset({"account_nav", "history", "statement_nav"})
CONTROL_TOKENS = frozenset({"account_nav", "history", "statement_nav", "start_date", "end_date", "all_history", "query", "next_page", "export", "login", "danger"})
ROW_FIELDS = frozenset({"occurred_at", "symbol", "side", "quantity", "price", "commission", "fee", "total_fees", "currency", "asset_class", "execution_id", "order_id", "market", "underlying", "expiry", "strike", "option_right", "multiplier", "position_effect"})
REQUIRED_FIELDS = frozenset({"occurred_at", "symbol", "side", "quantity", "price"})
_SAFE_CODES = re.compile(r"^[A-Z][A-Z0-9_]{0,64}$")
_NAVIGATION_STAGES = frozenset({"REQUEST_VALIDATED", "OBSERVED_IDENTITY_VERIFIED", "APP_ACTIVATION_CHECK",
    "REFRESHED_IDENTITY_VERIFIED", "SIDEBAR_GEOMETRY_CHECK", "SIDEBAR_HIT_CHECK", "FINAL_IDENTITY_CHECK",
    "NAVIGATION_ACTION_ISSUED", "POST_LAYOUT_READ", "COMPLETE"})


def _safe_navigation_audit(value: dict) -> dict:
    fields = {"stage", "app_activation_requested", "navigation_action_issued"}
    if (not isinstance(value, dict) or set(value) != fields or not isinstance(value["stage"], str)
            or value["stage"] not in _NAVIGATION_STAGES
            or type(value["app_activation_requested"]) is not bool or type(value["navigation_action_issued"]) is not bool):
        raise JournalError("INVALID_BRIDGE_RESPONSE", "导航执行阶段证据不符合固定白名单。")
    if value["navigation_action_issued"] and value["stage"] not in {"NAVIGATION_ACTION_ISSUED", "POST_LAYOUT_READ", "COMPLETE"}:
        raise JournalError("INVALID_BRIDGE_RESPONSE", "导航执行阶段与动作证据不一致。")
    return {key: value[key] for key in sorted(fields)}


class DesktopTransport(Protocol):
    def call(self, request: dict) -> dict: ...


class NativeAXTransport:
    """One JSON request per isolated native process; no shell or caller script."""
    def __init__(self, *, timeout_seconds: float = 20):
        if not 1 <= timeout_seconds <= 60:
            raise JournalError("INVALID_ACTION_BUDGET", "单次本地动作预算必须为 1 至 60 秒。")
        self.timeout_seconds = timeout_seconds
        self._executable: Path | None = None

    def _compile(self) -> Path:
        if platform.system() != "Darwin":
            raise JournalError("MAC_REQUIRED", "桌面采集仅支持 macOS。")
        source = Path(__file__).with_name("native") / "TigerReadOnly.swift"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        # A new private temporary directory prevents a predictable-path executable
        # substitution. The native helper contains no brokerage credential APIs.
        cache = Path(tempfile.mkdtemp(prefix="tiger-journal-ax-"))
        os.chmod(cache, 0o700)
        executable = cache / ("bridge-" + digest[:16])
        try:
            result = subprocess.run(["/usr/bin/swiftc", str(source), "-o", str(executable)],
                                    capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise JournalError("NATIVE_COMPILER_UNAVAILABLE", "本机 Swift 编译器不可用；未安装软件或修改权限。") from exc
        if result.returncode != 0:
            # Compiler output is never mixed with brokerage responses.
            raise JournalError("NATIVE_COMPILE_FAILED", "本地只读桥编译失败。")
        os.chmod(executable, 0o700)
        return executable

    def call(self, request: dict) -> dict:
        _validate_request(request)
        if request["action"] in {"read_history_view", "read_next_page", "set_history_window", "export_history"}:
            # The process boundary independently rechecks current isolation on every
            # financial action, even when callers bypass capture().
            from .privacy import assert_real_write_ready
            private = Path(request["private_root"])
            actual = assert_real_write_ready(private.parents[2])
            if Path(actual) != private:
                raise JournalError("PRIVATE_ROOT_REJECTED", "本地隔离校验与请求私人目录不一致。")
        if self._executable is None:
            self._executable = self._compile()
        try:
            result = subprocess.run([str(self._executable)], input=canonical_json(request).encode(),
                                    capture_output=True, timeout=self.timeout_seconds, check=False)
        except subprocess.TimeoutExpired as exc:
            raise JournalError("ACTION_TIMEOUT", "本地动作超时，采集已停止。") from exc
        except OSError as exc:
            raise JournalError("NATIVE_BRIDGE_UNAVAILABLE", "本地只读桥无法启动。") from exc
        # Stderr is not returned: native/UI messages may contain private material.
        if len(result.stdout) > 8_000_000:
            raise JournalError("BRIDGE_OUTPUT_LIMIT", "单页数据超过限制，采集已停止。")
        try:
            response = json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError) as exc:
            raise JournalError("INVALID_BRIDGE_RESPONSE", "本地只读桥返回无效结构。") from exc
        if not isinstance(response, dict) or response.get("ok") is not True:
            code = response.get("code", "NATIVE_BRIDGE_FAILED") if isinstance(response, dict) else "NATIVE_BRIDGE_FAILED"
            code = code if isinstance(code, str) and _SAFE_CODES.fullmatch(code) else "NATIVE_BRIDGE_FAILED"
            details = None
            if request["action"] == "navigate_history" and isinstance(response, dict) and "nav_audit" in response:
                details = {"nav_audit": _safe_navigation_audit(response["nav_audit"])}
            raise JournalError(code, "本地只读采集停止；需核验应用、权限或历史控件。", details=details)
        if result.returncode != 0 or not isinstance(response.get("result"), dict):
            raise JournalError("INVALID_BRIDGE_RESPONSE", "本地只读桥结果与进程状态不一致。")
        payload = response["result"]
        if request["action"] == "navigate_history" and "nav_audit" in payload:
            payload = {**payload, "nav_audit": _safe_navigation_audit(payload["nav_audit"])}
        return payload


def _validate_request(request: dict) -> None:
    if not isinstance(request, dict) or request.get("action") not in COLLECTION_ACTIONS | DISCOVERY_ACTIONS | NAVIGATION_ACTIONS:
        raise JournalError("ACTION_NOT_ALLOWED", "该动作不属于固定只读采集接口。")
    if set(request) - {"action", "profile", "window", "destination", "private_root", "guard_receipt", "page_proof", "target", "nav_proof"}:
        raise JournalError("ARGUMENT_NOT_ALLOWED", "接口不接受坐标、键盘、脚本、selector 或任意参数。")
    action = request["action"]
    permitted = {
        "probe": {"action"}, "inspect_layout": {"action"}, "open_app": {"action"},
        "navigate_history": {"action", "target", "nav_proof"},
        "read_history_view": {"action", "profile", "window", "private_root", "guard_receipt", "page_proof"},
        "read_next_page": {"action", "profile", "window", "private_root", "guard_receipt", "page_proof"},
        "set_history_window": {"action", "profile", "window", "private_root", "guard_receipt"},
        "export_history": {"action", "profile", "window", "destination", "private_root", "guard_receipt", "page_proof"},
    }[action]
    if set(request) != permitted:
        raise JournalError("ARGUMENT_NOT_ALLOWED", "动作参数不符合固定接口。")
    if action == "navigate_history":
        if not isinstance(request["target"], str) or request["target"] not in NAVIGATION_TARGETS:
            raise JournalError("NAVIGATION_TARGET_REJECTED", "导航仅允许已观察的账户、历史或账单入口。")
        validate_navigation_proof(request["nav_proof"])
    if action in {"read_history_view", "read_next_page", "set_history_window", "export_history"}:
        validate_profile(request["profile"])
        _validate_window(request["window"])
        if request["window"] != _client_window(request["window"], request["profile"]):
            raise JournalError("CLIENT_WINDOW_BOUNDARY_MISMATCH", "客户端查询日期与已核验显示时区不一致。")
        _receipt_hash(Path(request["private_root"]), expected=request["guard_receipt"])
    if action in {"read_history_view", "read_next_page", "export_history"}:
        _validate_page_proof(request["page_proof"], request["window"], request["profile"])
    if action == "export_history":
        root = Path(request["private_root"])
        destination = Path(request["destination"])
        if not root.is_absolute() or destination.parent != root / "sources" or not re.fullmatch(r"export-[a-f0-9]{32}\.csv", destination.name):
            raise JournalError("EXPORT_PATH_REJECTED", "正式导出只能写入已验证私人 sources 目录。")


def validate_navigation_proof(proof: dict) -> None:
    if not isinstance(proof, dict) or set(proof) != {"bundle_id", "version", "build", "identity_hash"}:
        raise JournalError("NAVIGATION_PROOF_INVALID", "导航证明仅允许安装身份、版本与已观察控件身份。")
    if proof.get("bundle_id") != BUNDLE_ID:
        raise JournalError("NAVIGATION_PROOF_INVALID", "导航应用身份不匹配。")
    for key in ("version", "build"):
        if not isinstance(proof[key], str) or not re.fullmatch(r"[A-Za-z0-9.+_-]{1,80}", proof[key]):
            raise JournalError("NAVIGATION_PROOF_INVALID", "导航证明缺少有限格式的应用版本。")
    if not isinstance(proof["identity_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", proof["identity_hash"]):
        raise JournalError("NAVIGATION_PROOF_INVALID", "导航证明缺少已观察的控件身份。")


def validate_profile(profile: dict) -> None:
    fields = {"bundle_id", "version", "build", "verified", "page_signature", "actions", "observed_layout_hash", "source_id", "as_of", "retrieved_at", "language", "region", "control_identity_hashes", "source_timezone"}
    if not isinstance(profile, dict) or set(profile) - fields:
        raise JournalError("DESKTOP_PROFILE_UNVERIFIED", "客户端配置含有未知字段。")
    if profile.get("bundle_id") != BUNDLE_ID or profile.get("verified") is not True:
        raise JournalError("DESKTOP_PROFILE_UNVERIFIED", "客户端只读配置尚未实机核验。")
    for field in ("version", "build", "source_id", "as_of", "retrieved_at"):
        if not isinstance(profile.get(field), str) or not profile[field]:
            raise JournalError("DESKTOP_PROFILE_UNVERIFIED", "客户端配置缺少版本或核验来源。")
    iso_datetime(profile["as_of"])
    iso_datetime(profile["retrieved_at"])
    signature = profile.get("page_signature")
    recognized = {"control:" + key for key in CONTROL_TOKENS - {"login", "danger"}} | {"field:" + key for key in ROW_FIELDS}
    recognized |= {token + "@" + role for token in tuple(recognized) for role in ("AXButton", "AXMenuItem", "AXRadioButton", "AXColumn", "AXStaticText", "AXTextField")}
    if not isinstance(signature, list) or not signature or any(token not in recognized for token in signature) or len(signature) != len(set(signature)):
        raise JournalError("DESKTOP_PROFILE_UNVERIFIED", "页面身份只能使用已观察的只读标签类别。")
    actions = profile.get("actions")
    if not isinstance(actions, list) or not actions or set(actions) - (COLLECTION_ACTIONS - {"open_app"}):
        raise JournalError("ACTION_NOT_ALLOWED", "客户端配置包含不允许的动作。")
    if not re.fullmatch(r"[a-f0-9]{64}", profile.get("observed_layout_hash", "")):
        raise JournalError("DESKTOP_PROFILE_UNVERIFIED", "客户端配置缺少脱敏布局核验 hash。")
    identities = profile.get("control_identity_hashes", {})
    if not isinstance(identities, dict) or set(identities) - {"account_nav", "history", "statement_nav"} or any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in identities.values()):
        raise JournalError("DESKTOP_PROFILE_UNVERIFIED", "固定控件身份仅允许本地已核验导航类别及其 hash。")
    if profile.get("language", "UNKNOWN") not in {"zh-Hans", "zh-Hant", "en", "UNKNOWN"} or profile.get("region", "UNKNOWN") not in {"HK", "SG", "AU", "US", "NZ", "UNKNOWN"}:
        raise JournalError("DESKTOP_PROFILE_UNVERIFIED", "客户端语言和地区只允许已核验的有限值。")
    if profile.get("source_timezone") is not None:
        try:
            ZoneInfo(profile["source_timezone"])
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise JournalError("INVALID_TIMEZONE", "客户端来源显示时区无效。") from exc


def _receipt_hash(private: Path, *, expected: str | None = None) -> str:
    if not private.is_absolute() or tuple(private.parts[-3:]) != ("product", ".private", "trading-journal") or private.is_symlink() or private.resolve() != private:
        raise JournalError("PRIVATE_ROOT_REJECTED", "金融动作必须绑定固定私人目录。")
    repo = private.parents[2]
    receipt = repo / ".codex-local/trading-journal-isolation.json"
    if receipt.is_symlink() or receipt.resolve() != receipt:
        raise JournalError("PRIVATE_ROOT_REJECTED", "隔离证明路径不能使用链接。")
    try:
        raw = receipt.read_bytes()
        proof = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise JournalError("ISOLATION_RECEIPT_REQUIRED", "金融动作缺少已验证本地隔离证明。") from exc
    if len(raw) > 65536 or not isinstance(proof, dict) or proof.get("status") != "VERIFIED" or proof.get("repository_root") != str(repo):
        raise JournalError("ISOLATION_RECEIPT_REQUIRED", "本地隔离证明与项目绑定不匹配。")
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected:
        raise JournalError("ISOLATION_RECEIPT_CHANGED", "本地隔离证明在动作前发生变化。")
    return digest


def _validate_window(window: dict | None) -> None:
    if not isinstance(window, dict) or window.get("preset") not in {"week", "month", "half_year", "year", "lifetime", "custom"}:
        raise JournalError("WINDOW_CHOICE_REQUIRED", "读取前请选择一周、一个月、半年、一年、开户至今或自定义日期。")
    if not isinstance(window.get("end"), str):
        raise JournalError("WINDOW_CHOICE_REQUIRED", "时间范围缺少明确截止时刻。")
    end = iso_datetime(window["end"])
    if window.get("start") is not None and iso_datetime(window["start"]) > end:
        raise JournalError("INVALID_WINDOW", "开始时刻晚于截止时刻。")
    for key in ("query_start_date", "query_end_date"):
        if key == "query_start_date" and window.get("preset") == "lifetime" and window.get(key) is None:
            continue  # native requires the exact, explicit All Time control
        if not isinstance(window.get(key), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", window[key]):
            # An unknown lifetime start cannot be guessed from the earliest trade.
            raise JournalError("CLIENT_WINDOW_UNSUPPORTED", "客户端需要可核验起点；开户日期未知时不能猜测查询起点。")


def _check_page(page: dict) -> None:
    rows = page.get("rows")
    if not isinstance(rows, list) or len(rows) > 5000 or page.get("row_count") != len(rows):
        raise JournalError("UNKNOWN_HISTORY_FORMAT", "成交页行数或结构无法核验。")
    for row in rows:
        if not isinstance(row, dict) or set(row) - ROW_FIELDS or not REQUIRED_FIELDS.issubset(row):
            raise JournalError("UNKNOWN_HISTORY_FORMAT", "成交页字段不属于已核验成交明细格式。")
        if any(not isinstance(value, str) or len(value) > 120 or "\n" in value for value in row.values()):
            raise JournalError("UNKNOWN_HISTORY_FORMAT", "成交页包含不可交付字段。")
    if not isinstance(page.get("page_hash"), str) or not re.fullmatch(r"[a-f0-9]{64}", page["page_hash"]):
        raise JournalError("UNKNOWN_HISTORY_FORMAT", "成交页缺少稳定内容 hash。")


def _validate_page_proof(proof: dict, window: dict, profile: dict) -> None:
    expected = {"window_hash", "profile_hash", "page_hash", "query_refresh_verified", "scope_verified"}
    if not isinstance(proof, dict) or set(proof) != expected:
        raise JournalError("PAGE_PROOF_UNVERIFIED", "缺少绑定查询范围与已刷新页面的证明。")
    if proof["window_hash"] != canonical_hash(window) or proof["profile_hash"] != canonical_hash(profile):
        raise JournalError("PAGE_PROOF_UNVERIFIED", "查询证明与当前期间或客户端配置不匹配。")
    if proof["query_refresh_verified"] is not True or proof["scope_verified"] is not True or not re.fullmatch(r"[a-f0-9]{64}", proof.get("page_hash", "")):
        raise JournalError("PAGE_PROOF_UNVERIFIED", "无法证明查询完成、日期范围及页面内容已刷新。")


def _client_window(window: dict, profile: dict) -> dict:
    timezone_name = profile.get("source_timezone")
    if not timezone_name:
        raise JournalError("SOURCE_TIMEZONE_UNVERIFIED", "客户端显示时区尚未核验，不能猜测日期查询边界。")
    tz = ZoneInfo(timezone_name)
    return {**window, "query_start_date": iso_datetime(window["start"]).astimezone(tz).date().isoformat() if window.get("start") else None,
            "query_end_date": iso_datetime(window["end"]).astimezone(tz).date().isoformat()}


def _window_row(row: dict, window: dict, source_timezone: str) -> tuple[bool, bool]:
    """Return inclusion and date-boundary uncertainty. Never fabricate a time."""
    text = row["occurred_at"].replace("/", "-")
    zone = ZoneInfo(source_timezone)
    start = iso_datetime(window["start"]) if window.get("start") else None
    end = iso_datetime(window["end"])
    try:
        if len(text) == 10:
            local_day = date.fromisoformat(text)
            lower = datetime.combine(local_day, datetime.min.time(), zone).astimezone(end.tzinfo)
            upper = datetime.combine(local_day + timedelta(days=1), datetime.min.time(), zone).astimezone(end.tzinfo)
            if start is not None and upper <= start:
                return False, False
            if lower > end:
                return False, False
            return True, (start is not None and lower < start) or upper > end
        occurred = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=zone)
        return (start is None or occurred >= start) and occurred <= end, False
    except (ValueError, TypeError) as exc:
        raise JournalError("UNKNOWN_HISTORY_FORMAT", "逐笔成交业务时间不能安全转换。") from exc


def _immutable_private(path: Path, payload: dict) -> None:
    text = canonical_json(payload)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600 or path.read_text(encoding="utf-8") != text:
            raise JournalError("PRIVATE_SOURCE_CONFLICT", "已有来源文件链接、权限或内容与冻结采集不一致。")
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


class TigerDesktopCollector:
    def __init__(self, *, transport: DesktopTransport | None = None,
                 write_guard: Callable[[Path], Path] | None = None):
        self.transport = transport or NativeAXTransport()
        self.write_guard = write_guard

    def _call(self, action: str, **parameters) -> dict:
        request = {"action": action, **parameters}
        _validate_request(request)  # including fake transports: reject before execution
        return self.transport.call(request)

    def probe(self) -> dict:
        """Installed version/permission metadata only. Does not open the application."""
        return self._discovery("probe")

    def _discovery(self, action: str) -> dict:
        result = self._call(action)
        now = utc_now()
        return {**result, "source_id": "tiger-desktop-layout:" + canonical_hash(result),
                "as_of": now, "retrieved_at": now}

    def inspect_layout(self) -> dict:
        """Known-label categories and AX role counts; never financial values."""
        return self._discovery("inspect_layout")

    def open_app(self) -> dict:
        """Fixed Tiger application only; does not navigate or read financial cells."""
        return self._discovery("open_app")

    def navigate_history(self, target: str, nav_proof: dict) -> dict:
        """One verified navigation step, without dates, financial rows or storage."""
        result = self._call("navigate_history", target=target, nav_proof=nav_proof)
        now = utc_now()
        return {**result, "source_id": "tiger-desktop-navigation:" + canonical_hash(result),
                "as_of": now, "retrieved_at": now}

    def _private_root(self, repository_root: Path) -> Path:
        if self.write_guard is None:
            from .privacy import assert_real_write_ready
            root = assert_real_write_ready(repository_root)
        else:
            root = self.write_guard(repository_root)
        expected = repository_root / "product" / ".private" / "trading-journal"
        if Path(root) != expected or not Path(root).is_absolute() or Path(root).is_symlink():
            raise JournalError("PRIVATE_ROOT_REJECTED", "采集器私人根目录不符合已绑定项目。")
        if not root.is_dir() or root.resolve() != root or stat.S_IMODE(root.stat().st_mode) != 0o700:
            raise JournalError("PRIVATE_ROOT_REJECTED", "私人目录必须存在、无链接且权限为 0700。")
        sources = root / "sources"
        if not sources.is_dir() or sources.is_symlink() or sources.resolve() != sources or stat.S_IMODE(sources.stat().st_mode) != 0o700:
            raise JournalError("PRIVATE_ROOT_REJECTED", "私人来源目录必须存在、无链接且权限为 0700。")
        return Path(root)

    def capture(self, *, repository_root: Path, window: dict | None, profile: dict,
                max_pages: int = 100, max_seconds: float = 120, prefer_export: bool = True) -> dict:
        """Collect bounded execution-detail pages after the real-write isolation guard.

        Returns sanitized rows and source hashes. Raw exported material is retained
        only in the private source directory. Missing end evidence always stays PARTIAL.
        """
        _validate_window(window)
        validate_profile(profile)
        if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 500 or not 1 <= max_seconds <= 600:
            raise JournalError("INVALID_ACTION_BUDGET", "分页与时间预算无效。")
        root = self._private_root(Path(repository_root))
        guard_receipt = _receipt_hash(root)
        actions, gaps, pages, rows, seen = [], [], [], [], set()
        deadline = time.monotonic() + max_seconds
        retrieved = utc_now()
        client_window = None
        query_proof = None

        def finish(result: dict) -> dict:
            self._private_root(Path(repository_root))
            _receipt_hash(root, expected=guard_receipt)
            receipt_id = "capture-" + uuid4().hex
            receipt = {
                "receipt_id": receipt_id, "source_id": result["source_id"], "as_of": window["end"],
                "retrieved_at": retrieved, "source_hash": result["source_hash"], "mode": result["mode"],
                "requested_window": window, "client_window": client_window,
                "source_timezone": profile.get("source_timezone"), "profile_hash": canonical_hash(profile),
                "actions": actions, "pages": pages, "gaps": gaps, "query_proof": query_proof,
                "raw_source_path": result.get("raw_source_path") or result.get("export", {}).get("path"),
                "fee_semantics": {"commission": "COMMISSION_COMPONENT", "fee": "UNCLASSIFIED_POSSIBLE_AGGREGATE",
                                  "total_fees": "SOURCE_EXPLICIT_TOTAL_FEES"},
                "collection_status": "PARTIAL" if gaps else "SCOPED_PAGES_CAPTURED",
            }
            receipt_hash = canonical_hash(receipt)
            path = root / "sources" / (receipt_id + ".json")
            _immutable_private(path, receipt)
            return {**result, "receipt_id": receipt_id, "receipt_hash": receipt_hash, "receipt_path": str(path),
                    "source_timezone": profile.get("source_timezone"), "profile_hash": canonical_hash(profile),
                    "client_window": client_window, "collection_status": receipt["collection_status"]}

        def act(action: str, **parameters) -> dict:
            if time.monotonic() >= deadline:
                raise JournalError("COLLECTION_TIME_LIMIT", "本次采集时间预算耗尽。")
            entry = {"action": action, "at": utc_now(), "status": "ATTEMPTED"}
            actions.append(entry)
            try:
                result = self._call(action, window=client_window, private_root=str(root), guard_receipt=guard_receipt, **parameters)
            except JournalError as exc:
                entry.update(status="STOPPED", code=exc.code)
                raise
            entry["status"] = "SUCCEEDED"
            return result

        # Set dates before collecting rows. After a selected window and isolation
        # proof, native refresh verification hashes the old verified table locally;
        # those pre-query rows are neither returned nor saved.
        try:
            client_window = _client_window(window, profile)
            setting = act("set_history_window", profile=profile)
            query_proof = setting.get("page_proof")
            _validate_page_proof(query_proof, client_window, profile)
            if window["preset"] == "lifetime" and window.get("start") is None:
                gaps.append({"code": "ACCOUNT_OPEN_DATE_UNKNOWN", "description": "已请求来源全部可见历史；开户日期未经官方勾稽，不能声明生命周期完整。"})
            if prefer_export and "export_history" in profile["actions"]:
                destination = root / "sources" / ("export-" + uuid4().hex + ".csv")
                try:
                    exported = act("export_history", profile=profile, destination=str(destination), page_proof=query_proof)
                    return finish({"source_id": "tiger-desktop:" + exported["source_hash"], "source_hash": exported["source_hash"], "as_of": window["end"],
                            "retrieved_at": retrieved, "window": window, "mode": "AUTOMATIC_DESKTOP_EXPORT",
                            "export": exported, "rows": [], "pages": [], "actions": actions,
                            "gaps": [*gaps, *exported.get("gaps", [])], "coverage": "PARTIAL"})
                except JournalError as exc:
                    if exc.code != "EXPORT_DESTINATION_NOT_VERIFIED":
                        raise
                    gaps.append({"code": exc.code, "description": "正式导出目的地尚未实机核验；使用已核验成交明细页。"})
            page = act("read_history_view", profile=profile, page_proof=query_proof)
            for index in range(max_pages):
                if index > 0 and page.get("terminal_without_page") is True:
                    _validate_page_proof(page.get("page_proof"), client_window, profile)
                    if not pages or page["page_proof"]["page_hash"] != pages[-1]["page_hash"] or page.get("end_proven") is not True:
                        raise JournalError("PAGE_PROOF_CHANGED", "分页终止证明不指向上一成功页。")
                    pages[-1]["end_proven"] = True
                    break
                _check_page(page)
                _validate_page_proof(page.get("page_proof"), client_window, profile)
                digest = page["page_hash"]
                if page["page_proof"]["page_hash"] != digest or (index == 0 and digest != query_proof["page_hash"]):
                    raise JournalError("PAGE_PROOF_CHANGED", "读取页与已完成查询的内容 hash 不一致。")
                if digest in seen:
                    gaps.append({"code": "REPEATED_PAGE", "description": "分页内容重复，已停止；保留之前成功页。"})
                    break
                seen.add(digest)
                page_meta = {"page_index": index + 1, "page_hash": digest, "row_count": len(page["rows"]),
                             "end_proven": page.get("end_proven") is True, "scope_verified": True,
                             "excluded_outside_window": 0, "uncertain_date_rows": 0}
                pages.append(page_meta)
                for row_index, row in enumerate(page["rows"], 1):
                    include, uncertain = _window_row(row, window, profile["source_timezone"])
                    if include:
                        rows.append({**row, "source_page": index + 1, "source_row": row_index})
                        page_meta["uncertain_date_rows"] += int(uncertain)
                    else:
                        page_meta["excluded_outside_window"] += 1
                if page_meta["excluded_outside_window"]:
                    gaps.append({"code": "OUTSIDE_WINDOW_ROWS_EXCLUDED", "page_index": index + 1, "count": page_meta["excluded_outside_window"],
                                 "description": "客户端日期查询多取的明确窗口外成交已在本地排除。"})
                if page_meta["uncertain_date_rows"]:
                    gaps.append({"code": "DATE_BOUNDARY_UNCERTAIN", "page_index": index + 1, "count": page_meta["uncertain_date_rows"],
                                 "description": "来源只有日期，边界日是否属于精确时刻范围无法确认。"})
                if page.get("end_proven") is True:
                    break
                if index + 1 == max_pages:
                    gaps.append({"code": "PAGE_LIMIT", "description": "页数预算耗尽，未证明历史终点。"})
                    break
                page = act("read_next_page", profile=profile, page_proof=page["page_proof"])
        except JournalError as exc:
            gaps.append({"code": exc.code, "description": "只读采集停止；未执行额外导航或交易动作。"})
            actions.append({"action": "capture", "at": utc_now(), "status": "STOPPED", "code": exc.code})
        source_payload = {"rows": rows, "pages": pages, "window": window, "client_window": client_window,
                          "source_timezone": profile.get("source_timezone"), "profile_hash": canonical_hash(profile)}
        digest = canonical_hash(source_payload)
        raw_source_path = None
        if rows:
            # Recheck after UI work, before the first private financial byte is
            # written. A changed proof cannot be treated as permission to save.
            self._private_root(Path(repository_root))
            _receipt_hash(root, expected=guard_receipt)
            # AX sources contain only the validated financial columns; account labels
            # were never read. Still apply restrictive file permissions for real trades.
            path = root / "sources" / ("ax-" + digest + ".json")
            _immutable_private(path, source_payload)
            raw_source_path = str(path)
        return finish({"source_id": "tiger-desktop:" + digest, "as_of": window["end"], "retrieved_at": retrieved,
                "source_hash": digest, "window": window, "mode": "AUTOMATIC_DESKTOP_AX" if pages else "DATA_BLOCKED",
                "raw_source_path": raw_source_path,
                "rows": rows, "pages": pages, "actions": actions, "gaps": gaps,
                "coverage": "PARTIAL", "pagination_end_proven": bool(pages and pages[-1]["end_proven"]),
                "asset_coverage": {"STOCK": "UNKNOWN", "ETF": "UNKNOWN", "OPTION": "UNKNOWN"}})
