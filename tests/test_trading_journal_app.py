"""Fictional loopback service checks; no real ledger, browser or network data."""

from copy import deepcopy
import base64
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
from urllib.parse import urlencode, urlsplit

from product.trading_journal.app import MAX_BODY_BYTES, MAX_CSV_BYTES, _import_args, load_journal_state, start_journal
from product.trading_journal.analysis import analyze_records
from product.trading_journal.charts import chart_payload
from product.trading_journal.common import JournalError, canonical_hash, canonical_json
from product.trading_journal.ledger import Ledger
from product.trading_journal.privacy import private_root
from product.trading_journal.reflection import prepare_reflection, save_report
from tests.test_trading_journal_reflection import record, report, snapshot


ACCOUNT = "account-fictional-test"


def rehash(value):
    value["input_hash"] = canonical_hash({key: value[key] for key in ("records", "context_records", "opening_positions", "coverage", "analysis", "market")})
    return value


class FakeUpdates:
    def __init__(self, value):
        self.snapshot = deepcopy(value)
        self.calls = []
        self.threads = []
        self.fail = False
        self.block = None

    def read_timeline(self):
        self.threads.append(threading.get_ident())
        if self.fail:
            raise JournalError("SYNTHETIC_LOAD_FAILURE", "PRIVATE_ERROR_MUST_NOT_LEAVE")
        return deepcopy(self.snapshot)

    def update_market(self, *, snapshot_id):
        self.calls.append(("market", snapshot_id))
        if self.block:
            self.block[0].set()
            self.block[1].wait(5)
        return {"status": "PARTIAL", "snapshot": deepcopy(self.snapshot), "credentials": "PRIVATE_RESULT_MUST_NOT_LEAVE"}

    def import_csv(self, raw, **kwargs):
        self.calls.append(("import", raw, kwargs))
        return {"status": "SAVED", "receipt": {"inserted": 1, "unchanged": 0, "revised": 0, "account_ref": ACCOUNT, "source_path": "/PRIVATE_RESULT_MUST_NOT_LEAVE"}}


def fake_render_report(projection, kind, identifier, report_id):
    chart, review = projection.select(kind, identifier)
    return canonical_json({"chart": chart, "review": review, "report_route": f"/reports/{report_id}/summary"})


class JournalAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve() / "repository"
        self.repo.mkdir()
        (self.repo / "product").mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / ".gitignore").write_text("/product/.private/\n")
        self.root = private_root(self.repo, create=True)
        self.snapshot = snapshot()
        self.snapshot["account_ref"] = ACCOUNT
        for row in self.snapshot["records"]:
            row["account_ref"] = ACCOUNT
        self.snapshot["analysis"] = analyze_records(self.snapshot["records"], opening_positions=self.snapshot["opening_positions"])
        rehash(self.snapshot)
        with Ledger(self.root) as ledger:
            ledger.import_records(self.snapshot["records"], mode="SYNTHETIC")
            # An exact fictional frozen version, independently bound by the
            # ordinary load_snapshot hash verifier in service request threads.
            ledger._db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?)", (self.snapshot["snapshot_id"], ACCOUNT, self.snapshot["input_hash"], self.snapshot["retrieved_at"], canonical_json(self.snapshot)))
            ledger._db.commit()
        self.packet = prepare_reflection(self.snapshot, chart_refs=["chart:frozen-snapshot-test"])
        self.report = report(self.packet)
        save_report(self.root, self.report, self.packet)
        self.updates = FakeUpdates(self.snapshot)
        self.ui_patch = patch.dict(sys.modules, {"product.trading_journal.app_ui": types.SimpleNamespace(
            render_landing=lambda state, csrf: canonical_json({"state": state, "csrf": csrf}),
            render_timeline=lambda snap: canonical_json(chart_payload(snap)), render_report=fake_render_report)})
        self.ui_patch.start()
        self.addCleanup(self.ui_patch.stop)
        self.session = start_journal(self.repo, ACCOUNT, port=0, real=False, updates=self.updates)
        self.addCleanup(self.session.close)
        self.origin = self.session.url.removesuffix("/")
        self.port = urlsplit(self.session.url).port
        status, headers, raw = self.request("GET", "/", authorized=False)
        self.assertEqual(status, 200)
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.csrf = json.loads(raw)["csrf"]

    def request(self, method, path, *, body=None, authorized=True, headers=None):
        content = canonical_json(body).encode() if isinstance(body, dict) else body
        outgoing = {}
        if authorized:
            outgoing.update({"Cookie": self.cookie, "Origin": self.origin})
            if method == "POST":
                outgoing.update({"X-Journal-CSRF": self.csrf, "Content-Type": "application/json"})
        if headers:
            outgoing.update(headers)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=content, headers=outgoing)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def fingerprints(self):
        return {str(path.relative_to(self.root)): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns, path.stat().st_mode)
                for path in self.root.rglob("*") if path.is_file()}

    def test_initial_and_all_gets_are_read_only_bounded_projections(self):
        before = self.fingerprints()
        self.assertEqual(self.session.server.server_address[0], "127.0.0.1")
        for path in ("/api/state", "/timeline", f"/reports/{self.report['report_id']}/view?kind=summary&id=0", f"/reports/{self.report['report_id']}/summary?page=0"):
            status, headers, raw = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])
            self.assertNotIn(ACCOUNT.encode(), raw)
            self.assertNotIn(str(self.root).encode(), raw)
        status, _, raw = self.request("HEAD", "/timeline")
        self.assertEqual((status, raw), (200, b""))
        self.assertEqual(before, self.fingerprints())
        self.assertEqual(self.updates.calls, [])

    def test_health_is_public_without_account_facts_or_session_secrets(self):
        status, headers, raw = self.request("GET", "/health", authorized=False)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"status": "RUNNING", "service": "trading-journal"})
        self.assertNotIn("Set-Cookie", headers)
        self.assertNotIn(ACCOUNT.encode(), raw)

    def test_host_origin_cookie_and_csrf_fail_before_update(self):
        for extra in ({"Host": "evil.invalid"}, {"Origin": "https://evil.invalid"}, {"Origin": "null"}, {"Cookie": "journal_app=wrong"}, {"X-Journal-CSRF": "wrong"}, {"X-Journal-CSRF": ""}):
            status, _, raw = self.request("POST", "/api/market", body={}, headers=extra)
            self.assertEqual(status, 403)
            self.assertNotIn(ACCOUNT.encode(), raw)
        self.assertEqual(self.request("POST", "/api/market", body={}, authorized=False)[0], 403)
        for extra in ({"Origin": ""}, {"Origin": "https://evil.invalid"}, {"Cookie": "journal_app=wrong"}):
            self.assertEqual(self.request("GET", "/api/state", headers=extra)[0], 403)
        self.assertEqual(self.updates.calls, [])

    def test_same_origin_referer_proof_for_frame_and_top_level_cross_site_rejection(self):
        self.assertEqual(self.request("GET", "/timeline", headers={"Origin": "", "Sec-Fetch-Site": "same-origin", "Referer": self.session.url})[0], 403)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", "/timeline", headers={"Cookie": self.cookie, "Sec-Fetch-Site": "same-origin", "Referer": self.session.url})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
        finally:
            connection.close()
        self.assertEqual(self.request("GET", "/", authorized=False, headers={"Sec-Fetch-Site": "cross-site"})[0], 403)

    def test_unknown_routes_queries_methods_and_parameter_actions_are_rejected(self):
        for path in ("/files/report.json", "/api/state?account=x", "/timeline?path=x", "/reports/reflection-" + "f" * 32 + "/summary?page=0"):
            self.assertEqual(self.request("GET", path)[0], 404)
        for path in ("/api/model", "/api/market?url=https://evil.invalid"):
            self.assertEqual(self.request("POST", path, body={})[0], 404)
        for field in ("path", "account", "url", "sql", "shell", "model", "start"):
            self.assertEqual(self.request("POST", "/api/market", body={field: "PRIVATE_INPUT"})[0], 400)
        self.assertEqual(self.request("PUT", "/api/market", body={})[0], 405)
        self.assertEqual(self.updates.calls, [])

    def test_body_and_upload_are_finite_strict_and_limited_before_side_effects(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'"text"', b'\xff'):
            self.assertEqual(self.request("POST", "/api/market", body=raw)[0], 400)
        self.assertEqual(self.request("POST", "/api/market", body=b"", headers={"Content-Length": str(MAX_BODY_BYTES + 1)})[0], 413)
        self.assertEqual(self.request("POST", "/api/market", body={}, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/market", body={}, headers={"Transfer-Encoding": "chunked"})[0], 400)
        good = {"csv_base64": base64.b64encode(b"fictional,csv").decode(), "start": "2026-01-01", "end": "2026-01-31", "source_timezone": "Asia/Hong_Kong", "range_timezone": "Asia/Hong_Kong"}
        for values in ({"start": "2026-02-01"}, {"end": "2026-1-2"}, {"source_timezone": "file:///private"}, {"range_timezone": "PER_ROW"}, {"range_timezone": "file:///private"}, {"csv_base64": ""}, {"csv_base64": base64.b64encode(b"a" * (MAX_CSV_BYTES + 1)).decode()}, {"name": "/private.csv"}):
            self.assertEqual(self.request("POST", "/api/import", body=good | values)[0], 400)
        self.assertEqual(self.updates.calls, [])

    def test_import_uses_startup_account_and_safe_response_counts_only(self):
        body = {"csv_base64": base64.b64encode(b"fictional,csv\n").decode(), "start": "2026-01-01", "end": "2026-01-31", "source_timezone": "America/New_York", "range_timezone": "America/New_York"}
        status, _, raw = self.request("POST", "/api/import", body=body)
        self.assertEqual(status, 200)
        self.assertEqual(self.updates.calls[0], ("import", base64.b64decode(body["csv_base64"]), {key: body[key] for key in ("start", "end", "source_timezone")} | {"timezone": "America/New_York"}))
        response = json.loads(raw)
        self.assertEqual(response["counts"], {"inserted": 1, "revised": 0, "unchanged": 0})
        self.assertNotIn(ACCOUNT.encode(), raw)
        self.assertNotIn(b"PRIVATE_RESULT", raw)

    def test_original_file_bytes_survive_upload_including_bom_and_non_utf8(self):
        for original in (b"\xef\xbb\xbf" + b"fictional,csv\n", "虚构成交,日期\n".encode("utf-16"), "虚构成交,日期\n".encode("gb18030")):
            body = {"csv_base64": base64.b64encode(original).decode("ascii"), "start": "2026-01-01", "end": "2026-01-31", "source_timezone": "PER_ROW", "range_timezone": "Asia/Hong_Kong"}
            status, _, raw = self.request("POST", "/api/import", body=body)
            self.assertEqual(status, 200)
            self.assertEqual(self.updates.calls[-1][1], original)
            self.assertEqual(self.updates.calls[-1][2]["source_timezone"], "PER_ROW")
        invalid = body | {"csv_base64": "not base64!"}
        with self.assertRaises(JournalError):
            _import_args(invalid)

    def test_market_and_refresh_keep_frozen_report_and_new_facts_separate(self):
        before = self.fingerprints()
        extra = record("added-activity", "2026-10-02T15:00:00Z", account_ref=ACCOUNT)
        self.updates.snapshot["records"].append(extra)
        rehash(self.updates.snapshot)
        status, _, raw = self.request("POST", "/api/refresh", body={})
        self.assertEqual(status, 200)
        state = json.loads(raw)["state"]
        self.assertEqual(state["timeline"]["record_count"], 6)
        self.assertEqual(state["pending_record_count"], 1)
        self.assertEqual(state["reports"][0]["record_count"], 5)
        self.assertEqual(state["reports"][0]["cutoff"], self.report["cutoff"])
        self.assertEqual(self.updates.calls, [])
        old = self.request("GET", f"/reports/{self.report['report_id']}/view?kind=case&id=finding-1")[2]
        self.assertNotIn(extra["record_id"].encode(), old)
        status, _, raw = self.request("POST", "/api/market", body={})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["status"], "PARTIAL")
        self.assertEqual(self.updates.calls, [("market", self.snapshot["snapshot_id"])])
        self.assertNotIn(b"PRIVATE_RESULT", raw)
        self.assertEqual(before, self.fingerprints())

    def test_failed_refresh_keeps_same_generation_and_redacts_errors(self):
        previous = self.session.server.state
        self.updates.fail = True
        status, _, raw = self.request("POST", "/api/refresh", body={})
        self.assertEqual(status, 422)
        self.assertIs(self.session.server.state, previous)
        self.assertNotIn(b"PRIVATE_ERROR", raw)
        self.assertEqual(self.request("GET", "/api/state")[0], 200)

    def test_duplicate_hints_do_not_masquerade_as_new_facts_but_revisions_do(self):
        for row in self.updates.snapshot["records"]:
            row["duplicate_candidate"] = True
        rehash(self.updates.snapshot)
        status, _, raw = self.request("POST", "/api/refresh", body={})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["state"]["pending_record_count"], 0)
        self.updates.snapshot["records"][0].update(fees="2", revision=2)
        rehash(self.updates.snapshot)
        status, _, raw = self.request("POST", "/api/refresh", body={})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["state"]["pending_record_count"], 1)

    def test_new_invalid_report_never_rebinds_or_replaces_valid_state(self):
        previous = self.session.server.state
        bad = deepcopy(self.report)
        bad["report_id"] = "reflection-" + "f" * 32
        save_report(self.root, bad, self.packet)
        path = self.root / "artifacts/reflections" / bad["report_id"] / "input.json"
        data = json.loads(path.read_text())
        data["snapshot"]["records"][0]["price"] = "999"
        path.write_text(canonical_json(data))
        status, _, raw = self.request("POST", "/api/refresh", body={})
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(raw)["code"], "REPORT_BINDING_INVALID")
        self.assertIs(self.session.server.state, previous)
        initial = load_journal_state(self.repo, ACCOUNT, self.updates)
        self.assertEqual(list(initial.projections), [self.report["report_id"]])
        self.assertTrue(initial.public["warnings"])

    def test_report_selection_uses_business_time_not_filesystem_mtime(self):
        newer = deepcopy(self.report)
        newer["report_id"] = "reflection-" + "e" * 32
        newer["report_as_of"] = newer["as_of"] = newer["retrieved_at"] = "2026-10-02T00:00:00Z"
        save_report(self.root, newer, self.packet)
        older_path = self.root / "artifacts/reflections" / self.report["report_id"]
        os.utime(older_path, (2100000000, 2100000000))
        status, _, raw = self.request("POST", "/api/refresh", body={})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["state"]["selected_report_id"], newer["report_id"])
        self.assertEqual(self.request("GET", f"/reports/{self.report['report_id']}/summary?page=0")[0], 200)

    def test_unknown_or_duplicated_report_selection_parameters_are_rejected(self):
        prefix = f"/reports/{self.report['report_id']}"
        for suffix in ("/view?kind=summary&id=0&id=1", "/view?kind=summary&id=0&url=x", "/view?kind=case&id=missing", "/summary?group=missing", "/summary?page=999999", "/summary?page=0&page=1", "/summary?path=x"):
            self.assertEqual(self.request("GET", prefix + suffix)[0], 400)

    def test_busy_update_rejected_before_body_read_or_adapter_and_gets_stay_live(self):
        entered, release = threading.Event(), threading.Event()
        self.updates.block = entered, release
        outcome = []
        thread = threading.Thread(target=lambda: outcome.append(self.request("POST", "/api/market", body={})[0]))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            status, _, raw = self.request("POST", "/api/refresh", body=b"", headers={"Content-Length": "99999"})
            self.assertEqual(status, 409)
            self.assertEqual(json.loads(raw)["code"], "UPDATE_BUSY")
            self.assertEqual(self.request("GET", "/api/state")[0], 200)
            self.assertEqual(len(self.updates.calls), 1)
        finally:
            release.set()
            thread.join(timeout=3)
        self.assertEqual(outcome, [200])

    def test_request_loads_use_their_own_thread_connections_and_session_has_no_timer(self):
        main = threading.get_ident()
        self.assertEqual(self.request("POST", "/api/refresh", body={})[0], 200)
        self.assertIn(main, self.updates.threads)
        self.assertTrue(any(identifier != main for identifier in self.updates.threads))
        self.assertFalse(hasattr(self.session, "timer"))
        self.assertTrue(self.session.thread.is_alive())
        self.session.close()
        self.session.close()
        self.assertFalse(self.session.thread.is_alive())
        self.assertIsNone(self.session.server.state)

    def test_port_conflict_and_noninteger_port_fail_explicitly(self):
        for value in (True, -1, 65536, "8765"):
            with self.assertRaises(JournalError) as caught:
                start_journal(self.repo, ACCOUNT, port=value, real=False, updates=self.updates)
            self.assertEqual(caught.exception.code, "INVALID_PORT")
        with self.assertRaises(JournalError) as caught:
            start_journal(self.repo, ACCOUNT, port=self.port, real=False, updates=self.updates)
        self.assertEqual(caught.exception.code, "PORT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
