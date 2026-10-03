"""Explicit persistent loopback workbench with narrowly scoped updates.

The current facts and each frozen reflection remain separate, validated rails.
No route serves a file, talks to an account, or starts a model.  This module
does not change browser-tool access rules for private information.
"""

from __future__ import annotations

from copy import deepcopy
import base64
import binascii
from dataclasses import dataclass, field
from datetime import date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import socket
import stat
import threading
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .charts import chart_payload
from .common import JournalError, canonical_hash, canonical_json, iso_datetime, utc_now
from .ledger import Ledger
from .privacy import private_root
from .review import load_review
from .viewer import ReviewProjection


MAX_BODY_BYTES = 6 * 1024 * 1024
MAX_CSV_BYTES = 4 * 1024 * 1024
RANGE_TIMEZONES = frozenset({"Asia/Hong_Kong", "America/New_York", "UTC"})
SOURCE_TIMEZONES = RANGE_TIMEZONES | {"PER_ROW"}
_REPORT_ID = re.compile(r"reflection-[0-9a-f]{32}")
_REPORT_ROUTE = re.compile(r"/reports/(reflection-[0-9a-f]{32})/(view|summary)")
_INPUT_FIELDS = ("records", "context_records", "opening_positions", "coverage", "analysis", "market")


@dataclass(frozen=True)
class JournalState:
    """One atomic, immutable-in-use generation of facts and report projections."""

    snapshot: dict
    projections: dict[str, ReviewProjection]
    public: dict


def _safe_report_names(root: Path) -> list[str]:
    """Discover only identities. Strict load_review performs fd-bound reads."""
    directory = root / "artifacts" / "reflections"
    for parent in (directory.parent, directory):
        if not parent.exists():
            return []
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
            raise JournalError("REPORT_DIRECTORY_INVALID", "保存的复盘目录未通过私人路径检查。")
    return sorted(item.name for item in directory.iterdir() if _REPORT_ID.fullmatch(item.name))


def _pending_count(snapshot: dict, projection: ReviewProjection, packet: dict) -> int:
    covered = set(projection.review["scope"]["record_ids"])
    original = {row["record_id"]: row for row in packet["snapshot"]["records"]}
    def frozen_facts(row):
        # The deterministic read-time duplicate hint may change after another
        # source is saved. It does not revise the original economic activity.
        return {key: value for key, value in (row or {}).items() if key != "duplicate_candidate"}
    return sum(row["record_id"] not in covered or canonical_json(frozen_facts(original.get(row["record_id"]))) != canonical_json(frozen_facts(row))
               for row in snapshot["records"])


def load_journal_state(repo: Path, account_ref: str, updates: Any, *, revision: int = 1, strict_reports: bool = False) -> JournalState:
    """Read all current facts and validate every discovered report binding.

    Every invocation opens its own read-only Ledger. A failed refresh never
    commits this candidate, so its prior generation remains available.
    """
    root = private_root(repo, create=False, real=False)
    snapshot = deepcopy(updates.read_timeline())
    if snapshot.get("account_ref") != account_ref or snapshot.get("input_hash") != canonical_hash({key: snapshot.get(key) for key in _INPUT_FIELDS}):
        raise JournalError("TIMELINE_BINDING_INVALID", "最新时间线的账户或内容绑定校验失败。")
    chart = chart_payload(snapshot)
    projections, reports, invalid_reports = {}, [], 0
    with Ledger(root, read_only=True) as ledger:
        if account_ref not in ledger.accounts():
            raise JournalError("ACCOUNT_NOT_FOUND", "指定的本地账户尚无交易记录。")
        for identifier in _safe_report_names(root):
            try:
                report, packet = load_review(root, identifier, load_snapshot=ledger.load_snapshot)
            except (ValueError, OSError) as exc:
                if strict_reports:
                    raise JournalError("REPORT_BINDING_INVALID", "新发现的复盘版本未通过绑定检查。") from exc
                invalid_reports += 1
                continue
            if packet["snapshot"].get("account_ref") != account_ref:
                continue
            projection = ReviewProjection(report, packet)
            pending = _pending_count(snapshot, projection, packet)
            projections[identifier] = projection
            reports.append({"report_id": identifier, "cutoff": report["cutoff"], "report_as_of": report["report_as_of"],
                            "label": f"资料截止 {report['cutoff']} · 保存 {report['report_as_of']}",
                            "record_count": len(report["scope"]["record_ids"]), "case_count": len(report["findings"]),
                            "pending_record_count": pending})
    # Business timestamps and validated identity define selection, never mtime.
    reports.sort(key=lambda row: (iso_datetime(row["cutoff"]), iso_datetime(row["report_as_of"]), row["report_id"]), reverse=True)
    market_days = [candle["date"] for group in chart["groups"] for candle in (group.get("market") or {}).get("candles", []) if candle.get("date")]
    checked = utc_now()
    public = {"source_id": "journal-app:local-state", "as_of": snapshot["as_of"], "retrieved_at": checked,
              "revision": revision, "last_checked": checked, "message": "",
              "warnings": ["部分保存的复盘未通过绑定检查，继续展示有效版本。"] if invalid_reports else [],
              "timeline": {"record_count": len(snapshot["records"]), "snapshot_id": snapshot["snapshot_id"],
                           "trade_through": max((row["occurred_at"] for row in snapshot["records"]), default=None),
                           "market_through": max(market_days, default=None),
                           "groups": [{"id": row["id"], "symbol": row["symbol"], "market": row["market_name"], "currency": row["currency"]} for row in chart["groups"]]},
              "reports": reports, "selected_report_id": reports[0]["report_id"] if reports else "",
              "pending_record_count": reports[0]["pending_record_count"] if reports else len(snapshot["records"])}
    return JournalState(snapshot, projections, public)


def _json_body(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("nonfinite")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise JournalError("INVALID_REQUEST", "请求内容无效。") from exc
    if not isinstance(value, dict):
        raise JournalError("INVALID_REQUEST", "请求内容须为固定字段对象。")
    return value


def _import_args(body: dict) -> tuple[bytes, dict]:
    if set(body) != {"csv_base64", "start", "end", "source_timezone", "range_timezone"} or any(not isinstance(body[key], str) for key in body):
        raise JournalError("INVALID_REQUEST", "导入需要CSV、完整日期及已核验的来源时区。")
    if body["source_timezone"] not in SOURCE_TIMEZONES or body["range_timezone"] not in RANGE_TIMEZONES:
        raise JournalError("INVALID_REQUEST", "来源时区不在允许选项中。")
    try:
        if any(date.fromisoformat(body[key]).isoformat() != body[key] for key in ("start", "end")) or body["start"] > body["end"]:
            raise ValueError("range")
    except ValueError as exc:
        raise JournalError("INVALID_REQUEST", "起止日期须完整、有序并使用年-月-日。") from exc
    try:
        raw = base64.b64decode(body["csv_base64"], validate=True)
    except (ValueError, binascii.Error):
        raise JournalError("INVALID_REQUEST", "CSV 文件编码无效。") from None
    if not raw or len(raw) > MAX_CSV_BYTES:
        raise JournalError("CSV_SIZE_LIMIT", "CSV为空或超过4MiB限制。")
    return raw, {key: body[key] for key in ("start", "end", "source_timezone")} | {"timezone": body["range_timezone"]}


@dataclass
class JournalSession:
    server: ThreadingHTTPServer
    thread: threading.Thread
    url: str
    _closed: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
            self.server.state = None
            self._closed = True


def start_journal(repo: Path | str, account_ref: str, *, port: int = 8765, real: bool = True,
                  updates: Any = None, market_fetch: Any = None) -> JournalSession:
    """Start only on explicit invocation. No timer, auto-start or write on GET."""
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise JournalError("INVALID_PORT", "本机端口无效。")
    if not isinstance(account_ref, str) or not re.fullmatch(r"account-[A-Za-z0-9_.:-]{1,72}", account_ref):
        raise JournalError("OPAQUE_ACCOUNT_REF_REQUIRED", "需要已有的本地随机账户引用。")
    repo = Path(repo)
    if updates is None:
        from .updates import JournalUpdates
        updates = JournalUpdates(repo, account_ref, real=real, market_fetch=market_fetch)
    state = load_journal_state(repo, account_ref, updates)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _respond(self, status: int, data: bytes = b"", content_type: str = "application/json; charset=utf-8", *, initial=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-src 'self'; frame-ancestors 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
            if initial:
                self.send_header("Set-Cookie", f"journal_app={token}; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _json(self, status: int, value: dict):
            return self._respond(status, canonical_json(value).encode())

        def _error(self, status: int, code: str, message: str):
            return self._json(status, {"status": "ERROR", "code": code, "message": message})

        def _target(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get_all("Host", []) != [origin.removeprefix("http://")]:
                return None, self._error(403, "SESSION_REQUIRED", "请求未通过本机会话检查。")
            try:
                url = urlsplit(self.path)
            except ValueError:
                return None, self._error(400, "INVALID_REQUEST", "请求地址无效。")
            if url.scheme or url.netloc or url.fragment or not url.path.startswith("/") or len(self.path) > 4096:
                return None, self._error(400, "INVALID_REQUEST", "请求地址无效。")
            return url, origin

        def _proof(self, origin: str, *, write=False) -> bool:
            origins = self.headers.get_all("Origin", [])
            if len(origins) > 1:
                return False
            supplied = origins[0] if origins else None
            try:
                referer = urlsplit(self.headers.get("Referer", ""))
                same = supplied == origin if supplied is not None else (self.headers.get("Sec-Fetch-Site") == "same-origin" and f"{referer.scheme}://{referer.netloc}" == origin)
                cookies = self.headers.get_all("Cookie", [])
                if len(cookies) != 1:
                    return False
                cookie = SimpleCookie()
                cookie.load(cookies[0])
                authenticated = "journal_app" in cookie and secrets.compare_digest(cookie["journal_app"].value, token)
                if write:
                    proofs = self.headers.get_all("X-Journal-CSRF", [])
                    return authenticated and supplied == origin and proofs == [csrf]
                return authenticated and same
            except (ValueError, TypeError):
                return False

        def _read(self):
            url, origin = self._target()
            if url is None:
                return
            if url.path == "/health" and not url.query:
                return self._json(200, {"status": "RUNNING", "service": "trading-journal"})
            if url.path == "/" and not url.query:
                origins = self.headers.get_all("Origin", [])
                if origins not in ([], [origin]) or self.headers.get("Sec-Fetch-Site") in {"cross-site", "same-site"}:
                    return self._error(403, "SESSION_REQUIRED", "请求未通过本机会话检查。")
                from .app_ui import render_landing
                return self._respond(200, render_landing(deepcopy(self.server.state.public), csrf).encode(), "text/html; charset=utf-8", initial=True)
            if not self._proof(origin):
                return self._error(403, "SESSION_REQUIRED", "请求未通过本机会话检查。")
            # The generation is swapped atomically only after full validation.
            selected = self.server.state
            if url.path == "/api/state" and not url.query:
                return self._json(200, deepcopy(selected.public))
            if url.path == "/timeline" and not url.query:
                from .app_ui import render_timeline
                return self._respond(200, render_timeline(deepcopy(selected.snapshot)).encode(), "text/html; charset=utf-8")
            route = _REPORT_ROUTE.fullmatch(url.path)
            if route is None:
                return self._error(404, "NOT_FOUND", "未找到允许的查看入口。")
            report_id, action = route.groups()
            projection = selected.projections.get(report_id)
            if projection is None:
                return self._error(404, "NOT_FOUND", "复盘版本未通过当前绑定检查。")
            try:
                if action == "summary":
                    return self._json(200, {"original_summary": projection.summary_query(url.query)})
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
                if set(query) != {"kind", "id"} or any(len(values) != 1 or not values[0] for values in query.values()):
                    raise ValueError("selection")
                from .app_ui import render_report
                html = render_report(projection, query["kind"][0], query["id"][0], report_id)
                return self._respond(200, html.encode(), "text/html; charset=utf-8")
            except (ValueError, JournalError):
                return self._error(400, "INVALID_SELECTION", "筛选未包含在所选复盘的冻结材料中。")

        do_GET = _read
        do_HEAD = _read

        def do_POST(self):
            url, origin = self._target()
            if url is None:
                return
            if not self._proof(origin, write=True):
                return self._error(403, "SESSION_REQUIRED", "更新需要同源会话及页面操作证明。")
            if url.query or url.path not in {"/api/refresh", "/api/market", "/api/import"}:
                return self._error(404, "NOT_FOUND", "未找到允许的更新入口。")
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get_all("Transfer-Encoding", []) or len(lengths) != 1 or not re.fullmatch(r"0|[1-9][0-9]{0,8}", lengths[0]):
                return self._error(400, "INVALID_REQUEST", "更新需要有界的完整请求内容。")
            size = int(lengths[0])
            if size > MAX_BODY_BYTES:
                return self._error(413, "BODY_SIZE_LIMIT", "请求超过6MiB限制。")
            if self.headers.get_all("Content-Type", []) != ["application/json"]:
                return self._error(415, "INVALID_REQUEST", "更新只接受JSON固定字段。")
            # Busy requests are rejected before reading a body or calling any
            # update adapter. There is no queued second write operation.
            if not self.server.action_lock.acquire(blocking=False):
                return self._error(409, "UPDATE_BUSY", "已有更新正在进行，请等待完成。")
            try:
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise JournalError("INVALID_REQUEST", "更新请求不完整。")
                body = _json_body(raw)
                kwargs = None
                if url.path == "/api/import":
                    csv, kwargs = _import_args(body)
                elif body:
                    raise JournalError("INVALID_REQUEST", "这个更新动作不接受其他参数。")
                previous = self.server.state
                result = {"status": "REFRESHED"}
                if url.path == "/api/market":
                    result = updates.update_market(snapshot_id=previous.snapshot["snapshot_id"])
                elif url.path == "/api/import":
                    result = updates.import_csv(csv, **kwargs)
                candidate = load_journal_state(repo, account_ref, updates, revision=previous.public["revision"] + 1, strict_reports=True)
                self.server.state = candidate
                status = result.get("status", "UPDATED")
                if status not in {"REFRESHED", "UPDATED", "PARTIAL", "UNCHANGED", "SAVED"}:
                    status = "UPDATED"
                response = {"status": status, "message": "已重新加载保存资料。" if url.path == "/api/refresh" else "更新已完成，原复盘依据保持原版本。", "state": deepcopy(candidate.public)}
                if url.path == "/api/market":
                    response["counts"] = {key: len(result[key]) for key in ("updated_symbols", "failed_symbols", "retained_symbols") if isinstance(result.get(key), list)}
                    if status == "PARTIAL":
                        response["message"] = "部分行情未能更新，保留对应旧行情；原复盘依据保持原版本。"
                    elif status == "UNCHANGED":
                        response["message"] = "没有新增有效行情，继续显示已保存行情。"
                elif url.path == "/api/import" and status == "UNCHANGED":
                    response["message"] = "该来源已保存，没有重复增加成交。"
                if url.path == "/api/import":
                    receipt = result.get("receipt") or {}
                    response["counts"] = {key: receipt[key] for key in ("inserted", "revised", "unchanged") if isinstance(receipt.get(key), int) and not isinstance(receipt[key], bool)}
                return self._json(200, response)
            except (JournalError, ValueError, OSError, socket.timeout) as exc:
                code = getattr(exc, "code", "UPDATE_FAILED")
                if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", code):
                    code = "UPDATE_FAILED"
                status = 400 if code in {"INVALID_REQUEST", "CSV_SIZE_LIMIT"} else 422
                message = "更新未完成，保留上次有效页面。请检查官方CSV日期、来源时区或已保存资料。"
                if "OVERLAP" in code:
                    message = "导出期间与已有无稳定成交编号的记录重叠，请选择不重叠日期或可证明成交身份的官方来源。"
                return self._error(status, code, message)
            finally:
                self.server.action_lock.release()

        def _reject(self):
            return self._error(405, "METHOD_NOT_ALLOWED", "请求方式不在允许范围中。")

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_CONNECT = do_TRACE = _reject

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        def handle_error(self, request, client_address):
            # Do not emit request details or exception text to service logs.
            pass
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            return connection, address

    try:
        server = Server(("127.0.0.1", port), Handler)
    except OSError as exc:
        raise JournalError("PORT_UNAVAILABLE", "本机端口已被使用或无法启动，请停止原服务或选择明确端口。") from exc
    server.state, server.action_lock = state, threading.Lock()
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    session = JournalSession(server, thread, f"http://127.0.0.1:{server.server_port}/")
    thread.start()
    return session


def serve_journal(repo: Path | str, account_ref: str, *, port: int = 8765, real: bool = True, **kwargs) -> dict:
    session = start_journal(repo, account_ref, port=port, real=real, **kwargs)
    print(json.dumps({"status": "JOURNAL_STARTED", "url": session.url}), flush=True)
    try:
        session.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return {"status": "JOURNAL_STOPPED"}
