"""Explicit, bounded loopback projections of one validated frozen report.

This does not proxy saved HTML and does not authorize browser-tool access.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date as calendar_date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import re
import threading
from typing import Callable, Mapping, Any
from urllib.parse import parse_qs, urlsplit

from .charts import chart_payload
from .common import canonical_json
from .reflection import ReflectionError
from .presentation import reader_script, record_label
from .review import _review_payload, load_review, render_review_payload


class ReviewProjection:
    """Only named selections can leave the process; no file or broker routes."""

    def __init__(self, report: Mapping[str, Any], packet: Mapping[str, Any]):
        self.chart = chart_payload(packet["snapshot"])
        self.review = _review_payload(report, packet)
        self.groups = {row["id"]: row for row in self.chart["groups"]}
        self.findings = {row["finding_id"]: row for row in self.review["findings"]}
        self.records = {row["record_id"]: row for row in self.chart["records"]}
        self.lessons = {row["finding_ref"]: row for row in self.review.get("case_lessons", [])}

    def summary(self, *, page: int = 0, group_id: str = "", date: str = "", asset: str = "ALL", contract: str = "ALL", start: str = "", end: str = "") -> dict:
        """Paginate original prose, selecting each component by its own facts.

        No case evidence, calculations, diary or whole trade facts leave through
        this projection. Cross-security plans keep their original scope.
        """
        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ReflectionError("要点页码无效")
        if group_id and group_id not in self.groups:
            raise ReflectionError("未知标的选择")
        if asset not in {"ALL", "STOCK", "ETF", "OPTION"}:
            raise ReflectionError("资产类别无效")
        if (date or contract != "ALL" or start or end) and not group_id:
            raise ReflectionError("日期及合约筛选须先选择标的")
        group_rows = [row for row in self.records.values() if not group_id or row["group_id"] == group_id]
        option_keys = {row["instrument"]["key"] for row in group_rows if row["instrument"]["asset_type"] == "OPTION"}
        if contract != "ALL" and (contract not in option_keys or asset not in {"ALL", "OPTION"}):
            raise ReflectionError("未知或不匹配的期权合约")
        frozen_days = {row["display_date"] for row in group_rows if row.get("display_date")}
        if group_id:
            frozen_days.update(row["date"] for row in (self.groups[group_id].get("market") or {}).get("candles", []) if row.get("date"))
        global_frozen_days = {row["display_date"] for row in self.records.values() if row.get("display_date")}
        for group in self.groups.values():
            global_frozen_days.update(row["date"] for row in (group.get("market") or {}).get("candles", []) if row.get("date"))
        for value in (date, start, end):
            if value:
                try:
                    if calendar_date.fromisoformat(value).isoformat() != value:
                        raise ValueError("not canonical")
                except (TypeError, ValueError) as exc:
                    raise ReflectionError("日期筛选格式无效") from exc
        if date and date not in frozen_days:
            raise ReflectionError("日期未包含在所选标的冻结材料中")
        if bool(start) != bool(end) or (start and (start > end or not global_frozen_days or start < min(global_frozen_days) or end > max(global_frozen_days))):
            raise ReflectionError("起止日期须完整、有序且处于冻结范围")
        eligible = {row["record_id"] for row in group_rows
                    if (not date or row.get("display_date") == date)
                    and (asset == "ALL" or row["instrument"]["asset_type"] == asset)
                    and (contract == "ALL" or row["instrument"]["key"] == contract)
                    and (not start or row.get("display_date") and start <= row["display_date"] <= end)}
        filtered = bool(group_id or asset != "ALL")
        summaries = []
        for finding in self.findings.values():
            main_matches = not filtered or bool(eligible.intersection(finding["record_refs"]))
            alternatives = [{"text": row["text"], "record_refs": list(row.get("record_refs", []))}
                            for row in finding["alternative_explanations"]
                            if not filtered or eligible.intersection(row.get("record_refs", []))]
            lesson = self.lessons.get(finding["finding_id"])
            practice = lesson.get("practice") if lesson else None
            practice_matches = bool(practice and (not filtered or eligible.intersection(practice.get("record_refs", []))))
            if not (main_matches or alternatives or practice_matches):
                continue
            item = {"finding_id": finding["finding_id"], "pattern": finding["pattern"], "confidence_limits": deepcopy(finding["confidence_limits"]),
                    "record_refs": list(finding["record_refs"]) if main_matches else [], "alternative_explanations": alternatives,
                    "summary_relations": (["main"] if main_matches else []) + (["alternative"] if alternatives else []) + (["practice"] if practice_matches else [])}
            if main_matches:
                for key in ("process_observation", "result_observation", "interpretation"):
                    item[key] = deepcopy(finding[key])
            if practice_matches:
                item["practice"] = {key: deepcopy(practice[key]) for key in ("possible_error", "exercise", "next_inputs", "verification", "record_refs")}
                item["practice_limits"] = deepcopy(lesson["limits"])
            summaries.append(item)
        plans = []
        for plan in self.review["improvement_plan"]:
            if filtered and not eligible.intersection(plan["record_refs"]):
                continue
            item = {key: deepcopy(plan[key]) for key in ("improvement_id", "finding_refs", "record_refs", "exercise", "next_inputs", "verification", "review_window", "status")}
            original_groups = list(dict.fromkeys(self.records[rid]["group_id"] for rid in plan["record_refs"]))
            symbols = [self.groups[gid]["symbol"] for gid in original_groups]
            item["scope_symbols"] = symbols
            item["scope_record_groups"] = original_groups
            item["scope_label"] = ("跨标的已有练习" if len(original_groups) > 1 else "跨案例已有练习" if len(plan["finding_refs"]) > 1 else "已有练习") + (" · " + " / ".join(symbols) if symbols else "")
            plans.append(item)
        page_size = 12
        total_pages = max(1, (len(summaries) + page_size - 1) // page_size)
        if page >= total_pages:
            raise ReflectionError("要点页码超出已保存范围")
        selected = summaries[page * page_size:(page + 1) * page_size]
        refs = set()
        for item in selected:
            refs.update(item["record_refs"])
            for alternative in item["alternative_explanations"]:
                refs.update(alternative["record_refs"])
            refs.update(item.get("practice", {}).get("record_refs", []))
        for plan in plans:
            refs.update(plan["record_refs"])
        reference_records = [{"record_id": rid, "group_id": row["group_id"], "display_date": row.get("display_date"),
                              "instrument": {key: row["instrument"].get(key) for key in ("key", "symbol", "asset_type")}}
                             for rid, row in self.records.items() if rid in refs]
        reference_labels = {rid: record_label(row) for rid, row in self.records.items() if rid in refs}
        named_findings = {row["finding_id"] for row in selected} | {fid for plan in plans for fid in plan["finding_refs"]}
        reference_labels.update({fid: self.findings[fid]["pattern"] for fid in self.findings if fid in named_findings})
        reference_labels.update({plan["improvement_id"]: plan["exercise"] for plan in plans})
        return {"findings": selected, "improvement_plan": plans, "reference_records": reference_records,
                "reference_labels": reference_labels,
                "pagination": {"page": page, "page_size": page_size, "total_count": len(summaries), "total_pages": total_pages},
                "selection": {"group_id": group_id, "date": date, "asset": asset, "contract": contract, "start": start, "end": end}}

    def summary_query(self, query: str) -> dict:
        """The fixed summary route has no arbitrary field, size or file inputs."""
        try:
            values = parse_qs(query, keep_blank_values=True, strict_parsing=True, max_num_fields=7)
            if not set(values) <= {"page", "group", "date", "asset", "contract", "start", "end"} or any(len(items) != 1 for items in values.values()):
                raise ValueError("unknown or duplicated fields")
            page = values.get("page", ["0"])[0]
            if not re.fullmatch(r"0|[1-9][0-9]{0,5}", page):
                raise ValueError("invalid page")
            return self.summary(page=int(page), group_id=values.get("group", [""])[0], date=values.get("date", [""])[0],
                                asset=values.get("asset", ["ALL"])[0], contract=values.get("contract", ["ALL"])[0], start=values.get("start", [""])[0], end=values.get("end", [""])[0])
        except (TypeError, ValueError) as exc:
            raise ReflectionError("要点筛选参数无效") from exc

    def catalog(self) -> dict:
        return {
            "report_id": self.review["report_id"], "cutoff": self.review["cutoff"],
            "record_count": len(self.records), "case_count": len(self.findings),
            "coverage": deepcopy(self.review["scope"]["coverage"]),
            "groups": [{"id": row["id"], "symbol": row["symbol"], "market": row["market_name"], "currency": row["currency"]} for row in self.groups.values()],
            "cases": [{"finding_id": row["finding_id"], "pattern": row["pattern"]} for row in self.findings.values()],
            "original_summary": self.summary(),
        }

    def select(self, kind: str, identifier: str) -> tuple[dict, dict]:
        if kind == "summary":
            if not isinstance(identifier, str) or not re.fullmatch(r"0|[1-9][0-9]{0,5}", identifier):
                raise ReflectionError("要点页码无效")
            original_summary = self.summary(page=int(identifier))
            record_ids, finding_ids, selected_findings, initial_group = set(), set(self.findings), [], ""
        elif kind == "group":
            if identifier not in self.groups:
                raise ReflectionError("未知标的选择")
            record_ids = {rid for rid, row in self.records.items() if row["group_id"] == identifier}
            finding_ids = set()
            for fid, row in self.findings.items():
                related = set(row["record_refs"])
                for alternate in row["alternative_explanations"]:
                    related.update(alternate.get("record_refs", []))
                if related & record_ids:
                    finding_ids.add(fid)
            selected_findings = []
            initial_group = identifier
            original_summary = self.summary(group_id=identifier)
        elif kind == "case":
            if identifier not in self.findings:
                raise ReflectionError("未知案例选择")
            finding = self.findings[identifier]
            record_ids = set(finding["record_refs"])
            for alternate in finding["alternative_explanations"]:
                record_ids.update(alternate.get("record_refs", []))
            lesson = next((row for row in self.review.get("case_lessons", []) if row["finding_ref"] == identifier), None)
            focus = lesson["focus_record_ref"] if lesson else finding["record_refs"][0]
            initial_group = self.records[focus]["group_id"]
            finding_ids, selected_findings = {identifier}, [deepcopy(finding)]
            original_summary = self.summary(group_id=initial_group)
        else:
            raise ReflectionError("选择类别无效")
        plans = [deepcopy(row) for row in self.review["improvement_plan"] if kind == "case" and set(row["finding_refs"]) & finding_ids]
        # A saved exercise can compare records and findings beyond its selected
        # case. Preserve those references and include their required chart facts,
        # while leaving the other finding bodies for a separate selection.
        directory_ids = set(finding_ids)
        for plan in plans:
            record_ids.update(plan["record_refs"])
            directory_ids.update(plan["finding_refs"])
        group_ids = {self.records[rid]["group_id"] for rid in record_ids}
        data = {key: deepcopy(self.chart[key]) for key in ("kind", "schema_version", "snapshot_id", "input_hash", "source_id", "as_of", "retrieved_at", "statistics_scope")}
        data.update(groups=[deepcopy(row) for key, row in self.groups.items() if key in group_ids], records=[deepcopy(row) for rid, row in self.records.items() if rid in record_ids],
                    initial_group_id=initial_group, analysis={}, coverage=deepcopy(self.review["scope"]["coverage"]))
        review = {key: deepcopy(self.review[key]) for key in ("report_id", "source_id", "as_of", "retrieved_at", "report_as_of", "cutoff", "snapshot_id", "input_hash", "packet_hash", "model_version", "skill_version", "limitations", "phase_coverage", "report_basis")}
        lessons = [deepcopy(row) for row in self.review.get("case_lessons", []) if kind == "case" and row["finding_ref"] in finding_ids]
        needed_evidence, needed_calculations = set(), set()
        for finding in selected_findings:
            for field in ("decision_evidence_refs", "outcome_evidence_refs", "uncertain_evidence_refs"):
                needed_evidence.update(finding.get(field, []))
            needed_calculations.update(finding.get("calculation_refs", []))
            needed_calculations.update(row["calculation_ref"] for row in finding.get("financial_claims", []))
            for alternate in finding["alternative_explanations"]:
                needed_evidence.update(alternate.get("evidence_refs", []))
        for plan in plans:
            needed_evidence.update(plan.get("evidence_refs", []))
        for lesson in lessons:
            for layer in ("beginner", "practice", "advanced"):
                needed_evidence.update(lesson[layer]["evidence_refs"])
            needed_evidence.update(row["evidence_ref"] for row in lesson["event_links"])
        events_by_case = self.review.get("lesson_events", {})
        if isinstance(events_by_case, dict):
            events = {fid: deepcopy(events_by_case[fid]) for fid in finding_ids if kind == "case" and fid in events_by_case}
        else:
            events = [deepcopy(row) for row in events_by_case if kind == "case" and row.get("finding_ref") in finding_ids]
        review.update(scope={"mode": self.review["scope"]["mode"], "record_ids": sorted(record_ids), "context_record_ids": [], "excluded_record_ids": [], "asset_types": sorted({self.records[rid]["instrument"]["asset_type"] for rid in record_ids}), "limitations": self.review["scope"]["limitations"], "coverage": deepcopy(self.review["scope"]["coverage"])},
                      progress={"status": self.review["progress"]["status"], "total_units": self.review["progress"]["total_units"], "analyzed_count": len(self.review["progress"]["analyzed_episode_ids"]), "pending_count": len(self.review["progress"]["pending_episode_ids"]), "analyzed_episode_ids": [], "pending_episode_ids": []},
                      case_selection={}, directory=[{"finding_id": fid, "pattern": self.findings[fid]["pattern"], "record_refs": sorted((set(self.findings[fid]["record_refs"]) | {rid for alt in self.findings[fid]["alternative_explanations"] for rid in alt.get("record_refs", [])}) & record_ids)} for fid in self.findings if fid in directory_ids],
                      findings=selected_findings, improvement_plan=plans, case_lessons=lessons, lesson_events=events,
                      evidence=[deepcopy(row) for row in self.review["evidence"] if row["evidence_id"] in needed_evidence], calculations={key: deepcopy(value) for key, value in self.review["calculations"].items() if key in needed_calculations})
        review["viewer_selection"] = True
        review["original_summary"] = original_summary
        if kind == "case":
            review["initial_finding_id"] = identifier
        return data, review


def _landing(catalog: dict) -> str:
    # The initial response contains a bounded original-prose page and plans,
    # never full trade facts, case evidence/calculations or the frozen packet.
    encoded = canonical_json(catalog).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    labels = {row["finding_id"]: row.get("pattern") or "复盘案例" for row in catalog.get("cases", [])}
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>交易图表与复盘</title><style>body{margin:0;background:#f3f7f7;color:#163440;font:15px/1.6 -apple-system,sans-serif}main{max-width:1360px;margin:auto;padding:22px}h1{font-size:25px;margin:0}p{color:#617480;white-space:pre-line}label{display:inline-flex;gap:8px;margin:8px 16px 8px 0}select{font:inherit;max-width:420px;padding:8px;border:1px solid #c8d7db;border-radius:7px}iframe{width:100%;height:1200px;border:0;display:block;margin-top:12px}@media(max-width:700px){main{padding:12px}label{display:flex}select{max-width:75vw}}</style></head><body><main><h1>交易图表与复盘</h1><label>标的<select id="group"><option value="">选择标的</option></select></label><details><summary>按需查看完整案例目录</summary><label>案例<select id="case"><option value="">选择复盘案例</option></select></label></details><iframe id="work" src="/view?kind=summary&amp;id=0" title="图表与已保存复盘"></iframe><details><summary>数据说明与覆盖</summary><p id="scope"></p></details><script id="catalog" type="application/json">''' + encoded + '''</script><script>''' + reader_script(labels) + '''const catalog=JSON.parse(document.getElementById('catalog').textContent);document.getElementById('scope').textContent=`已保存 ${catalog.record_count} 笔 · ${catalog.groups.length} 标的 · ${catalog.case_count} 案例 · 资料截止 ${jrReadable(catalog.cutoff)} · 覆盖 ${jrCode(catalog.coverage.status)}\n请求区间：${jrReadable(catalog.coverage.requested_window||"未指定区间，依据全部已保存记录")}\n来源返回范围：${jrReadable(catalog.coverage.actual_start)} 至 ${jrReadable(catalog.coverage.actual_end)}\n覆盖缺口：${jrReadable(catalog.coverage.gaps||[])}`;for(const g of catalog.groups){const o=new Option(jrReadable(`${g.symbol} · ${g.market} · ${g.currency}`),g.id);document.getElementById('group').add(o)}for(const c of catalog.cases)document.getElementById('case').add(new Option(jrReadable(c.pattern),c.finding_id));for(const kind of ['group','case'])document.getElementById(kind).addEventListener('change',e=>{document.getElementById(kind==='group'?'case':'group').value='';const work=document.getElementById('work');work.src='/view?'+new URLSearchParams(e.target.value?{kind,id:e.target.value}:{kind:'summary',id:'0'});work.hidden=false});</script></main></body></html>'''


@dataclass
class ReviewSession:
    server: ThreadingHTTPServer
    thread: threading.Thread
    timer: threading.Timer
    url: str
    _closed: bool = False
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.timer.cancel()
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
            self.server.projection = None
            self._closed = True


def start_review(validated_root: Path, report_id: str, *, load_snapshot: Callable, port: int = 0, lifetime_seconds: int = 900) -> ReviewSession:
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ReflectionError("查看端口无效")
    if isinstance(lifetime_seconds, bool) or not isinstance(lifetime_seconds, int) or not 1 <= lifetime_seconds <= 3600:
        raise ReflectionError("查看时长须为1至3600秒")
    report, packet = load_review(validated_root, report_id, load_snapshot=load_snapshot)
    projection = ReviewProjection(report, packet)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _respond(self, status, data=b"", content_type="text/plain; charset=utf-8", *, initial=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-src 'self'; frame-ancestors 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
            if initial:
                self.send_header("Set-Cookie", f"journal_view={token}; Path=/; HttpOnly; SameSite=Strict")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _read(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get_all("Host", []) != [origin.split("//", 1)[1]]:
                return self._respond(403)
            url = urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment or not url.path.startswith("/"):
                return self._respond(400)
            if url.path == "/" and not url.query:
                supplied_origin = self.headers.get("Origin")
                if supplied_origin and supplied_origin != origin:
                    return self._respond(403)
                return self._respond(200, _landing(self.server.projection.catalog()).encode(), "text/html; charset=utf-8", initial=True)
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except Exception:
                return self._respond(403)
            supplied_origin = self.headers.get("Origin")
            referer = urlsplit(self.headers.get("Referer", ""))
            same_origin = supplied_origin == origin if supplied_origin else (self.headers.get("Sec-Fetch-Site") == "same-origin" and f"{referer.scheme}://{referer.netloc}" == origin)
            if "journal_view" not in cookie or not secrets.compare_digest(cookie["journal_view"].value, token) or not same_origin:
                return self._respond(403)
            if url.path == "/catalog" and not url.query:
                return self._respond(200, canonical_json(self.server.projection.catalog()).encode(), "application/json; charset=utf-8")
            if url.path == "/summary":
                try:
                    original_summary = self.server.projection.summary_query(url.query)
                except ReflectionError:
                    return self._respond(400)
                return self._respond(200, canonical_json({"original_summary": original_summary}).encode(), "application/json; charset=utf-8")
            if url.path not in {"/view", "/selection"}:
                return self._respond(404)
            try:
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
                if set(query) != {"kind", "id"} or any(len(v) != 1 or not v[0] for v in query.values()):
                    raise ValueError("invalid selection")
                data, review = self.server.projection.select(query["kind"][0], query["id"][0])
            except (ValueError, ReflectionError):
                return self._respond(400)
            if url.path == "/selection":
                return self._respond(200, canonical_json({"chart": data, "review": review}).encode(), "application/json; charset=utf-8")
            return self._respond(200, render_review_payload(data, review).encode(), "text/html; charset=utf-8")

        do_GET = _read
        do_HEAD = _read

        def _reject(self):
            self._respond(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_CONNECT = do_TRACE = _reject

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.projection = projection
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    timer = threading.Timer(lifetime_seconds, lambda: session.close())
    timer.daemon = True
    session = ReviewSession(server, thread, timer, f"http://127.0.0.1:{server.server_port}/")
    thread.start()
    timer.start()
    return session


def serve_review(validated_root: Path, report_id: str, *, load_snapshot: Callable, port: int = 0, lifetime_seconds: int = 900) -> dict:
    session = start_review(validated_root, report_id, load_snapshot=load_snapshot, port=port, lifetime_seconds=lifetime_seconds)
    print(json.dumps({"status": "VIEWER_STARTED", "url": session.url, "lifetime_seconds": lifetime_seconds, "report_id": report_id}), flush=True)
    try:
        session.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return {"status": "VIEWER_STOPPED", "report_id": report_id}
