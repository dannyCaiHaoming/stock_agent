"""只监听本机的 Research Browser HTTP 应用。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

from product.web.read_only import ArtifactCatalog, BrowserDataError, ReadOnlyResearchMemory
from product.web import rendering


SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


@dataclass(frozen=True)
class WebResponse:
    status: int
    body: bytes
    content_type: str = "text/html; charset=utf-8"
    headers: Mapping[str, str] | None = None


def _first(query: Mapping[str, list[str]], name: str, default: str = "") -> str:
    values = query.get(name, [])
    return values[0] if values else default


def _host_name(value: str) -> str:
    text = value.strip().casefold()
    if text.startswith("["):
        return text.split("]", 1)[0] + "]"
    return text.rsplit(":", 1)[0] if ":" in text else text


class ResearchBrowser:
    def __init__(self, memory: ReadOnlyResearchMemory | None, artifacts: ArtifactCatalog, *, memory_error: str | None = None):
        self.memory = memory
        self.artifacts = artifacts
        self.memory_error = memory_error

    @staticmethod
    def _html(value: str, status: int = 200, headers: Mapping[str, str] | None = None) -> WebResponse:
        return WebResponse(status, value.encode("utf-8"), headers=headers)

    @staticmethod
    def _json(value: Mapping[str, Any], status: int = 200) -> WebResponse:
        return WebResponse(status, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, code: str, status: int) -> WebResponse:
        return self._html(rendering.error_page(code, status), status)

    def dispatch(self, method: str, target: str, headers: Mapping[str, str]) -> WebResponse:
        host = _host_name(headers.get("Host", ""))
        if host not in ALLOWED_HOSTS:
            return self._error("BROWSER_HOST_REJECTED", HTTPStatus.FORBIDDEN)
        parsed = urlsplit(target)
        query = parse_qs(parsed.query, keep_blank_values=True)
        path = parsed.path
        if method == "POST":
            if path != "/rescan":
                return self._error("BROWSER_METHOD_NOT_ALLOWED", HTTPStatus.METHOD_NOT_ALLOWED)
            origin = headers.get("Origin")
            if origin:
                origin_parts = urlsplit(origin)
                if origin_parts.scheme not in {"http", "https"} or _host_name(origin_parts.netloc) not in ALLOWED_HOSTS:
                    return self._error("BROWSER_ORIGIN_REJECTED", HTTPStatus.FORBIDDEN)
            self.artifacts.rescan()
            return WebResponse(HTTPStatus.SEE_OTHER, b"", headers={"Location": "/"})
        if method != "GET":
            return self._error("BROWSER_METHOD_NOT_ALLOWED", HTTPStatus.METHOD_NOT_ALLOWED)
        try:
            if path == "/healthz":
                return self._json({
                    "status": "READY" if self.memory is not None else "PARTIAL",
                    "memory": self.memory.diagnostic() if self.memory else {"status": "UNAVAILABLE", "code": self.memory_error},
                    "artifacts": self.artifacts.diagnostic(),
                })
            if path == "/":
                return self._html(rendering.overview(self.memory.diagnostic() if self.memory else None, self.artifacts.diagnostic(), memory_error=self.memory_error))
            if path == "/macro":
                return self._html(rendering.macro_page(self.artifacts.macro(_first(query, "version") or None)))
            if path == "/market":
                return self._html(rendering.market_page(self.artifacts.market(_first(query, "version") or None)))
            if path == "/companies":
                if self.memory is None:
                    raise BrowserDataError(self.memory_error or "BROWSER_MEMORY_UNAVAILABLE")
                q, status = _first(query, "q"), _first(query, "status")
                result = self.memory.list_companies(query=q, status=status, page=_first(query, "page", "1"))
                return self._html(rendering.companies_page(result, query=q, status=status))
            if path.startswith("/companies/"):
                if self.memory is None:
                    raise BrowserDataError(self.memory_error or "BROWSER_MEMORY_UNAVAILABLE")
                parts = path.split("/")
                if len(parts) not in {3, 4} or not parts[2]:
                    return self._error("BROWSER_NOT_FOUND", HTTPStatus.NOT_FOUND)
                security_id = unquote(parts[2])
                if len(security_id) > 256 or any(char in security_id for char in ("/", "\\", "\x00")):
                    return self._error("BROWSER_NOT_FOUND", HTTPStatus.NOT_FOUND)
                if len(parts) == 3:
                    model = self.memory.company(security_id, view_hash=_first(query, "view") or None)
                    selected_view = model.get("selected_view") or {}
                    attachment = self.artifacts.company_visuals(
                        security_id,
                        selected_view.get("decision_cutoff"),
                        selected_view.get("run_id"),
                    )
                    if attachment and attachment.get("status") == "AVAILABLE":
                        model["charts"] = attachment["charts"]
                    model["external_attachment"] = attachment
                    model["dimension_research"] = self.artifacts.company_reports(
                        security_id,
                        selected_view.get("decision_cutoff"),
                        selected_view.get("run_id"),
                        sorted({
                            str(item.get("evidence_id"))
                            for item in model.get("facts", [])
                            if isinstance(item, Mapping) and item.get("evidence_id")
                        }),
                    )
                    return self._html(rendering.company_page(model))
                if parts[3] == "facts":
                    model = self.memory.facts_page(
                        security_id, view_hash=_first(query, "view") or None,
                        group=_first(query, "group"), field=_first(query, "field"),
                        page=_first(query, "page", "1"),
                    )
                    return self._html(rendering.facts_page(model))
                if parts[3] == "compare":
                    model = self.memory.compare_views(security_id, _first(query, "left"), _first(query, "right"))
                    return self._html(rendering.compare_page(model, show_all=_first(query, "show") == "all"))
                if parts[3] == "report":
                    left = self.memory.report(security_id, _first(query, "entry"))
                    right_id = _first(query, "right")
                    right = self.memory.report(security_id, right_id) if right_id else None
                    return self._html(rendering.report_page(left, right))
            return self._error("BROWSER_NOT_FOUND", HTTPStatus.NOT_FOUND)
        except BrowserDataError as exc:
            code = str(exc) or "BROWSER_DATA_UNAVAILABLE"
            status = HTTPStatus.NOT_FOUND if code.endswith("NOT_FOUND") else HTTPStatus.SERVICE_UNAVAILABLE
            return self._error(code, status)


def make_handler(application: ResearchBrowser) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "StockAgentResearchBrowser/1"

        def do_GET(self) -> None:  # noqa: N802
            try:
                response = application.dispatch("GET", self.path, self.headers)
            except Exception:
                response = application._error("BROWSER_INTERNAL_ERROR", HTTPStatus.INTERNAL_SERVER_ERROR)
            self._respond(response)

        def do_POST(self) -> None:  # noqa: N802
            length = min(4096, max(0, int(self.headers.get("Content-Length", "0") or 0)))
            if length:
                self.rfile.read(length)
            try:
                response = application.dispatch("POST", self.path, self.headers)
            except Exception:
                response = application._error("BROWSER_INTERNAL_ERROR", HTTPStatus.INTERNAL_SERVER_ERROR)
            self._respond(response)

        def _respond(self, response: WebResponse) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            for key, value in SECURITY_HEADERS.items():
                self.send_header(key, value)
            for key, value in (response.headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


class LocalResearchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def build_server(application: ResearchBrowser, *, port: int) -> LocalResearchServer:
    return LocalResearchServer(("127.0.0.1", port), make_handler(application))
