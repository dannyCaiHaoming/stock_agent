from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import unittest

from product.trading_journal.common import JournalError, canonical_hash
from product.trading_journal.desktop import NativeAXTransport, TigerDesktopCollector, _client_window, _receipt_hash, _validate_request, validate_profile
from product.trading_journal.windows import resolve_window

NOW = "2026-10-01T12:00:00+08:00"


def verified_profile():
    return {"bundle_id": "com.itiger.TigerTrade-Mac", "version": "9.27.2", "build": "synthetic-build",
            "verified": True, "page_signature": ["control:history"],
            "actions": ["set_history_window", "read_history_view", "read_next_page"],
            "observed_layout_hash": "a" * 64, "source_id": "synthetic-verified-layout", "as_of": NOW,
            "retrieved_at": NOW, "language": "zh-Hans", "region": "UNKNOWN", "source_timezone": "America/New_York"}


def page(execution_id="fill-1", *, terminal=False):
    rows = [{"occurred_at": "2026-09-25 11:30:00", "symbol": "AAPL", "side": "BUY",
             "quantity": "2", "price": "100.5", "currency": "USD", "asset_class": "STOCK",
             "execution_id": execution_id}]
    return {"rows": rows, "row_count": len(rows), "page_hash": canonical_hash(rows), "end_proven": terminal}


class FakeTransport:
    def __init__(self, pages=()):
        self.pages = list(pages)
        self.calls = []
        self.fail_action = None
        self.fail_code = "PAGE_IDENTITY_UNCONFIRMED"

    def call(self, request):
        self.calls.append(copy.deepcopy(request))
        if request["action"] == self.fail_action:
            raise JournalError(self.fail_code, "合成拒绝。")
        if request["action"] in {"probe", "open_app", "inspect_layout"}:
            return {"bundle_id": "com.itiger.TigerTrade-Mac", "version": "9.27.2", "ax_trusted": True,
                    "layout": {"role_counts": {"AXWindow": 1}, "recognized_controls": {}}}
        if request["action"] == "set_history_window":
            return {"window_set": True, "page_proof": self.proof(request, self.pages[0]["page_hash"])}
        if request["action"] in {"read_history_view", "read_next_page"}:
            result = self.pages.pop(0)
            result["page_proof"] = self.proof(request, result["page_hash"])
            return result
        raise AssertionError("Unexpected action in synthetic test")

    @staticmethod
    def proof(request, digest):
        return {"window_hash": canonical_hash(request["window"]), "profile_hash": canonical_hash(request["profile"]),
                "page_hash": digest, "query_refresh_verified": True, "scope_verified": True}


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name).resolve()
        self.root = self.repo / "product/.private/trading-journal"
        self.sources = self.root / "sources"
        self.sources.mkdir(parents=True)
        os.chmod(self.root, 0o700)
        os.chmod(self.sources, 0o700)
        receipt = self.repo / ".codex-local/trading-journal-isolation.json"
        receipt.parent.mkdir(mode=0o700)
        receipt.write_text(json.dumps({"status": "VERIFIED", "repository_root": str(self.repo), "synthetic": True}))
        self.window = resolve_window("month", now=NOW)
        self.profile = verified_profile()

    def tearDown(self):
        self.temp.cleanup()

    def collector(self, transport):
        return TigerDesktopCollector(transport=transport, write_guard=lambda _: self.root)

    def test_probe_and_open_return_only_layout_and_do_not_read_financial_cells(self):
        transport = FakeTransport()
        collector = self.collector(transport)
        collector.probe()
        collector.open_app()
        collector.inspect_layout()
        self.assertEqual([call["action"] for call in transport.calls], ["probe", "open_app", "inspect_layout"])
        self.assertFalse(any("profile" in request for request in transport.calls))

    def test_unselected_window_precedes_guard_and_all_account_operations(self):
        transport = FakeTransport()
        guards = []
        collector = TigerDesktopCollector(transport=transport, write_guard=lambda repo: guards.append(repo))
        with self.assertRaises(JournalError) as failure:
            collector.capture(repository_root=self.repo, window=None, profile=self.profile)
        self.assertEqual(failure.exception.code, "WINDOW_CHOICE_REQUIRED")
        self.assertEqual(transport.calls, [])
        self.assertEqual(guards, [])

    def test_arbitrary_actions_parameters_and_selectors_rejected_before_transport(self):
        transport = FakeTransport()
        collector = self.collector(transport)
        for action in ("click", "type", "evaluate", "buy", "sell", "preview_order", "cancel_order", "exercise", "transfer", "unlock"):
            with self.subTest(action=action), self.assertRaises(JournalError):
                collector._call(action)
        for key in ("x", "coordinates", "keys", "script", "selector", "url", "password"):
            with self.subTest(parameter=key), self.assertRaises(JournalError):
                collector._call("read_history_view", profile=self.profile, **{key: "untrusted"})
        self.assertEqual(transport.calls, [])

    def test_profile_cannot_introduce_write_action_or_arbitrary_label(self):
        for change in ({"actions": ["buy"]}, {"page_signature": ["button:Cancel Order"]},
                       {"verified": False}, {"selector": "arbitrary"},
                       {"control_identity_hashes": {"buy": "a" * 64}}):
            with self.subTest(change=change), self.assertRaises(JournalError):
                validate_profile({**self.profile, **change})

    def test_private_guard_failure_precedes_every_ui_operation(self):
        transport = FakeTransport()
        def blocked(_):
            raise JournalError("ISOLATION_UNVERIFIED", "合成隔离尚未证明。")
        collector = TigerDesktopCollector(transport=transport, write_guard=blocked)
        with self.assertRaises(JournalError):
            collector.capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(transport.calls, [])

    def test_wrong_root_permissions_or_source_symlink_rejected(self):
        transport = FakeTransport()
        os.chmod(self.sources, 0o755)
        with self.assertRaises(JournalError):
            self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(transport.calls, [])
        os.chmod(self.sources, 0o700)
        self.sources.rmdir()
        outside = self.repo / "outside-sources"
        outside.mkdir(mode=0o700)
        self.sources.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(JournalError):
            self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(transport.calls, [])

    def test_set_dates_precedes_read_and_pages_preserve_identical_fill_economics(self):
        transport = FakeTransport([page("fill-1"), page("fill-2", terminal=True)])
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual([call["action"] for call in transport.calls], ["set_history_window", "read_history_view", "read_next_page"])
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual({row["execution_id"] for row in result["rows"]}, {"fill-1", "fill-2"})
        self.assertTrue(result["pagination_end_proven"])
        self.assertEqual(result["coverage"], "PARTIAL")  # pagination alone is not asset/lifetime coverage
        saved = list(self.sources.glob("ax-*.json"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(json.loads(saved[0].read_text())["rows"]), 2)

    def test_duplicate_page_stops_finitely_without_losing_previous_page(self):
        transport = FakeTransport([page(), page(), page("not-read")])
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(len(transport.pages), 1)
        self.assertEqual(result["gaps"][-1]["code"], "REPEATED_PAGE")
        self.assertFalse(result["pagination_end_proven"])

    def test_page_limit_and_missing_next_are_partial_with_source_progress(self):
        transport = FakeTransport([page(), page("not-read")])
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile, max_pages=1)
        self.assertEqual(result["gaps"][-1]["code"], "PAGE_LIMIT")
        self.assertEqual(len(transport.pages), 1)
        transport = FakeTransport([page()])
        transport.fail_action = "read_next_page"
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["gaps"][-1]["code"], "PAGE_IDENTITY_UNCONFIRMED")

    def test_account_or_other_extra_column_blocks_before_private_persistence(self):
        invalid = page()
        invalid["rows"][0]["account_number"] = "synthetic-private-not-a-real-account"
        transport = FakeTransport([invalid])
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["gaps"][-1]["code"], "UNKNOWN_HISTORY_FORMAT")
        self.assertEqual(list(self.sources.glob("ax-*.json")), [])
        self.assertNotIn("synthetic-private", json.dumps(result))

    def test_unknown_gui_stops_before_values_or_navigation(self):
        transport = FakeTransport()
        transport.fail_action = "set_history_window"
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual([request["action"] for request in transport.calls], ["set_history_window"])
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["gaps"][0]["code"], "PAGE_IDENTITY_UNCONFIRMED")

    def test_unverified_query_refresh_does_not_read_or_claim_automatic_success(self):
        transport = FakeTransport([page(terminal=True)])
        original = transport.call
        def no_refresh(request):
            result = original(request)
            if request["action"] == "set_history_window":
                result["page_proof"]["query_refresh_verified"] = False
            return result
        transport.call = no_refresh
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual([request["action"] for request in transport.calls], ["set_history_window"])
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["mode"], "DATA_BLOCKED")
        self.assertEqual(result["gaps"][-1]["code"], "PAGE_PROOF_UNVERIFIED")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["collection_status"], "PARTIAL")

    def test_unknown_source_timezone_blocks_every_financial_action(self):
        transport = FakeTransport([page()])
        profile = {key: value for key, value in self.profile.items() if key != "source_timezone"}
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=profile)
        self.assertEqual(transport.calls, [])
        self.assertEqual(result["mode"], "DATA_BLOCKED")
        self.assertEqual(result["gaps"][0]["code"], "SOURCE_TIMEZONE_UNVERIFIED")

    def test_first_read_changed_after_query_is_blocked_even_with_same_date_controls(self):
        transport = FakeTransport([page(terminal=True)])
        original = transport.call
        def changed_after_query(request):
            result = original(request)
            if request["action"] == "set_history_window":
                transport.pages[0] = page("unexpected-new-page", terminal=True)
            return result
        transport.call = changed_after_query
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["mode"], "DATA_BLOCKED")
        self.assertEqual(result["gaps"][-1]["code"], "PAGE_PROOF_CHANGED")
        self.assertEqual(list(self.sources.glob("ax-*.json")), [])

    def test_client_dates_use_display_timezone_and_explicit_outside_rows_are_removed(self):
        scoped = page(terminal=True)
        outside = {**scoped["rows"][0], "execution_id": "after-cutoff", "occurred_at": "2026-10-01 01:00:00"}
        scoped["rows"].append(outside)
        scoped["row_count"] = 2
        scoped["page_hash"] = canonical_hash(scoped["rows"])
        transport = FakeTransport([scoped])
        result = self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual([row["execution_id"] for row in result["rows"]], ["fill-1"])
        self.assertEqual(result["pages"][0]["excluded_outside_window"], 1)
        self.assertEqual(result["gaps"][-1]["code"], "OUTSIDE_WINDOW_ROWS_EXCLUDED")
        shifted = resolve_window("week", now="2026-10-01T08:00:00+08:00")
        client = _client_window(shifted, self.profile)
        self.assertEqual(client["query_end_date"], "2026-09-30")
        self.assertEqual(client["query_start_date"], "2026-09-23")

    def test_capture_receipt_binds_source_window_profile_and_only_safe_action_metadata(self):
        result = self.collector(FakeTransport([page(terminal=True)])).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        path = Path(result["receipt_path"])
        receipt = json.loads(path.read_text())
        self.assertEqual(receipt["receipt_id"], result["receipt_id"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), result["receipt_hash"])
        self.assertEqual(receipt["requested_window"], self.window)
        self.assertEqual(receipt["profile_hash"], canonical_hash(self.profile))
        self.assertEqual(receipt["source_timezone"], "America/New_York")
        source = Path(receipt["raw_source_path"])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), result["source_hash"])
        self.assertEqual(receipt["actions"], result["actions"])
        self.assertNotIn("rows", receipt)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(receipt["fee_semantics"]["fee"], "UNCLASSIFIED_POSSIBLE_AGGREGATE")

    def test_lifetime_request_keeps_unknown_account_date_instead_of_guessing(self):
        window = resolve_window("lifetime", now=NOW)
        transport = FakeTransport([page(terminal=True)])
        result = self.collector(transport).capture(repository_root=self.repo, window=window, profile=self.profile)
        self.assertIsNone(transport.calls[0]["window"]["query_start_date"])
        self.assertEqual(result["gaps"][0]["code"], "ACCOUNT_OPEN_DATE_UNKNOWN")
        self.assertEqual(result["coverage"], "PARTIAL")

    def test_repeated_source_is_immutable_and_link_conflict_does_not_overwrite(self):
        collector = self.collector(FakeTransport([page(terminal=True)]))
        result = collector.capture(repository_root=self.repo, window=self.window, profile=self.profile)
        saved = self.sources / ("ax-" + result["source_hash"] + ".json")
        before = saved.read_bytes()
        self.collector(FakeTransport([page(terminal=True)])).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(saved.read_bytes(), before)
        saved.unlink()
        outside = self.repo / "outside-source.json"
        outside.write_text("synthetic-existing-file")
        saved.symlink_to(outside)
        with self.assertRaises(JournalError) as failure:
            self.collector(FakeTransport([page(terminal=True)])).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual(failure.exception.code, "PRIVATE_SOURCE_CONFLICT")
        self.assertEqual(outside.read_text(), "synthetic-existing-file")

    def test_receipt_change_between_pages_stops_before_next_transport_call(self):
        transport = FakeTransport([page(), page("not-read")])
        old_call = transport.call
        def changing_receipt(request):
            result = old_call(request)
            if request["action"] == "read_history_view":
                receipt = self.repo / ".codex-local/trading-journal-isolation.json"
                receipt.write_text(receipt.read_text() + "\n")
            return result
        transport.call = changing_receipt
        with self.assertRaises(JournalError) as failure:
            self.collector(transport).capture(repository_root=self.repo, window=self.window, profile=self.profile)
        self.assertEqual([item["action"] for item in transport.calls], ["set_history_window", "read_history_view"])
        self.assertEqual(failure.exception.code, "ISOLATION_RECEIPT_CHANGED")
        self.assertEqual(list(self.sources.iterdir()), [])

    def test_export_destination_cannot_escape_private_source_folder(self):
        export_profile = {**self.profile, "actions": [*self.profile["actions"], "export_history"]}
        window = _client_window(self.window, export_profile)
        for destination in (self.repo / "outside.csv", self.sources / "account.csv", self.sources / "nested" / ("export-" + "0" * 32 + ".csv")):
            with self.subTest(destination=destination), self.assertRaises(JournalError):
                _validate_request({"action": "export_history", "profile": export_profile,
                                   "window": window, "private_root": str(self.root),
                                   "page_proof": FakeTransport.proof({"window": window, "profile": export_profile}, "a" * 64),
                                   "guard_receipt": _receipt_hash(self.root), "destination": str(destination)})

    def test_lowlevel_financial_actions_require_window_and_receipt_before_transport(self):
        transport = FakeTransport()
        collector = self.collector(transport)
        profile = {**self.profile, "actions": [*self.profile["actions"], "export_history"]}
        window = _client_window(self.window, profile)
        parameters = {"profile": profile, "window": window, "private_root": str(self.root),
                      "guard_receipt": _receipt_hash(self.root)}
        for action in ("read_history_view", "read_next_page", "set_history_window", "export_history"):
            complete = {**parameters}
            if action != "set_history_window":
                complete["page_proof"] = FakeTransport.proof(complete, "a" * 64)
            if action == "export_history":
                complete["destination"] = str(self.sources / ("export-" + "0" * 32 + ".csv"))
            for missing in ("window", "private_root", "guard_receipt"):
                with self.subTest(action=action, missing=missing), self.assertRaises(JournalError):
                    collector._call(action, **{key: value for key, value in complete.items() if key != missing})
        self.assertEqual(transport.calls, [])

    @unittest.skipUnless(platform.system() == "Darwin", "Native policy runs on macOS")
    def test_native_process_itself_rejects_nonwhitelist_actions_without_account_access(self):
        # These invalid requests fail in run() before installed metadata or AX access.
        binary = NativeAXTransport()._compile()
        requests = [{"action": action} for action in ("click", "buy", "sell", "preview_order", "cancel_order", "exercise", "transfer", "unlock", "evaluate")]
        requests.append({"action": "open_app", "selector": "arbitrary"})
        requests.extend([
            {"action": "read_history_view", "profile": self.profile},
            {"action": "read_history_view", "profile": self.profile, "window": {},
             "private_root": str(self.root), "guard_receipt": "a" * 64},
            {"action": "read_history_view", "profile": self.profile, "window": self.window,
             "private_root": str(self.root), "guard_receipt": "a" * 64},
            {"action": "set_history_window", "profile": self.profile, "window": _client_window(self.window, self.profile),
             "private_root": str(self.root), "guard_receipt": "a" * 64},
        ])
        for request in requests:
            with self.subTest(request=request):
                result = subprocess.run([str(binary)], input=json.dumps(request).encode(),
                                        capture_output=True, timeout=5)
                response = json.loads(result.stdout)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(response["ok"])
                self.assertIn(response["code"], {"ACTION_NOT_ALLOWED", "ARGUMENT_NOT_ALLOWED", "WINDOW_CHOICE_REQUIRED", "ISOLATION_RECEIPT_CHANGED"})
                self.assertEqual(set(response), {"ok", "code"})

    @unittest.skipUnless(platform.system() == "Darwin", "Native refresh tracker runs on macOS")
    def test_native_refresh_tracker_replays_stale_slow_fluctuating_and_unscoped_pages(self):
        from product.trading_journal import desktop
        source = Path(desktop.__file__).with_name("native") / "TigerReadOnly.swift"
        binary = self.repo / "native-policy-test"
        compiled = subprocess.run(["/usr/bin/swiftc", "-D", "JOURNAL_POLICY_TEST", str(source), "-o", str(binary)],
                                  capture_output=True, timeout=60)
        self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
        process = subprocess.run([str(binary)], capture_output=True, timeout=5)
        outcomes = json.loads(process.stdout)
        self.assertEqual(len(outcomes), 8)
        self.assertTrue(all(outcomes.values()), outcomes)

    @unittest.skipUnless(platform.system() == "Darwin", "Native layout walker runs on macOS")
    def test_native_snapshot_walk_executes_cycles_shared_handles_collisions_windows_and_limits(self):
        from product.trading_journal import desktop
        source = Path(desktop.__file__).with_name("native") / "TigerReadOnly.swift"
        binary = self.repo / "native-layout-test"
        compiled = subprocess.run(["/usr/bin/swiftc", "-D", "JOURNAL_LAYOUT_TEST", str(source), "-o", str(binary)],
                                  capture_output=True, timeout=60)
        self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
        process = subprocess.run([str(binary)], capture_output=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        cases = json.loads(process.stdout)
        expected = {
            "cycle": (["app", "menu"], False),
            "shared": (["root", "left", "shared", "right"], False),
            "windows_first_full_scan": (["app", "window", "history", "menu", "danger", "login"], False),
            "windows_first_bounded": (["app", "window"], True),
            "collisions_and_equal_handles": (["root", "first", "other"], False),
            "duplicate_at_node_budget": (["root", "first", "other"], False),
            "genuine_node_budget": (["root", "first"], True),
            "depth_only_seen_child": ([f"depth-{index}" for index in range(21)], False),
            "genuine_depth_budget": ([f"depth-{index}" for index in range(21)], True),
            "genuine_time_budget": (["root"], True),
        }
        self.assertEqual(set(cases), set(expected))
        for name, (ids, truncated) in expected.items():
            with self.subTest(case=name):
                self.assertEqual(cases[name]["ids"], ids)
                self.assertIs(cases[name]["truncated"], truncated)
        self.assertEqual(cases["cycle"]["role_counts"]["AXApplication"], 1)
        self.assertEqual(cases["shared"]["role_counts"]["AXButton"], 1)
        self.assertEqual(cases["windows_first_full_scan"]["role_counts"]["AXWindow"], 1)
        self.assertEqual(cases["windows_first_full_scan"]["role_counts"]["AXMenuItem"], 1)
        self.assertEqual(cases["collisions_and_equal_handles"]["role_counts"]["AXButton"], 1)
        self.assertEqual(cases["collisions_and_equal_handles"]["role_counts"]["AXMenuItem"], 1)

    @unittest.skipUnless(platform.system() == "Darwin", "Native fixed-window opening policy runs on macOS")
    def test_native_window_open_policy_replays_identity_restore_and_postconditions_without_ui(self):
        from product.trading_journal import desktop
        source = Path(desktop.__file__).with_name("native") / "TigerReadOnly.swift"
        binary = self.repo / "native-window-open-test"
        compiled = subprocess.run(["/usr/bin/swiftc", "-D", "JOURNAL_WINDOW_OPEN_TEST", str(source), "-o", str(binary)],
                                  capture_output=True, timeout=60)
        self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
        process = subprocess.run([str(binary)], capture_output=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        outcomes = json.loads(process.stdout)
        expected = {
            "strict_true_bool", "strict_false_bool", "numeric_not_bool", "string_not_bool",
            "unique_main_window", "foreign_window_pid_rejected", "foreign_parent_pid_rejected",
            "multiple_windows_rejected", "non_window_role_rejected", "incomplete_parent_rejected",
            "unknown_parent_rejected", "unknown_minimized_stops_no_write", "already_unminimized_no_write",
            "writable_minimized_requests_one_false", "unwritable_stops_no_write", "write_failure_rejected",
            "verified_post_restore", "still_minimized_rejected", "unknown_post_minimized_rejected",
            "changed_identity_rejected", "changed_frame_rejected", "offscreen_rejected", "not_frontmost_rejected",
        }
        self.assertEqual(set(outcomes), expected)
        for name, outcome in outcomes.items():
            with self.subTest(case=name):
                self.assertIs(outcome, True)


class NavigationOnlyTests(unittest.TestCase):
    @unittest.skipUnless(platform.system() == "Darwin", "Native navigation policy runs on macOS")
    def test_native_navigation_policy_replays_table_aliases_ancestry_and_sidebar_geometry(self):
        from product.trading_journal import desktop
        source = Path(desktop.__file__).with_name("native") / "TigerReadOnly.swift"
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "native-navigation-policy"
            compiled = subprocess.run(["/usr/bin/swiftc", "-D", "JOURNAL_NAVIGATION_TEST", str(source), "-o", str(binary)],
                                      capture_output=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
            process = subprocess.run([str(binary)], capture_output=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        outcomes = json.loads(process.stdout)
        self.assertEqual(len(outcomes), 32)
        self.assertTrue(all(outcomes.values()), outcomes)

    @unittest.skipUnless(platform.system() == "Darwin", "Native request gate runs on macOS")
    def test_native_request_gate_accepts_fixed_navigation_without_financial_fields(self):
        from product.trading_journal import desktop
        source = Path(desktop.__file__).with_name("native") / "TigerReadOnly.swift"
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "native-request-gate"
            compiled = subprocess.run(["/usr/bin/swiftc", "-D", "JOURNAL_REQUEST_TEST", str(source), "-o", str(binary)],
                                      capture_output=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode())
            for target in ("account_nav", "history", "statement_nav"):
                request = {"action": "navigate_history", "target": target, "nav_proof": self.proof()}
                process = subprocess.run([str(binary)], input=json.dumps(request).encode(), capture_output=True, timeout=5)
                with self.subTest(target=target):
                    self.assertEqual(process.returncode, 0, process.stderr.decode())
                    self.assertEqual(json.loads(process.stdout), {"ok": True, "result": {"validated_action": "navigate_history"}})

    """Navigation has a separate identity proof and never opens financial storage."""

    @staticmethod
    def proof():
        return {"bundle_id": "com.itiger.TigerTrade-Mac", "version": "9.27.2",
                "build": "synthetic-build", "identity_hash": "a" * 64}

    @staticmethod
    def result(target):
        return {"bundle_id": "com.itiger.TigerTrade-Mac", "version": "9.27.2",
                "build": "synthetic-build", "navigation_target": target,
                "layout": {"recognized_controls": {}, "role_counts": {"AXWindow": 1}}}

    def test_navigation_targets_execute_one_step_and_return_fact_metadata_without_guard(self):
        from unittest.mock import Mock

        transport = Mock()
        guard = Mock(side_effect=AssertionError("navigation must not access private storage"))
        collector = TigerDesktopCollector(transport=transport, write_guard=guard)
        for target in ("account_nav", "history", "statement_nav"):
            with self.subTest(target=target):
                transport.call.return_value = self.result(target)
                result = collector.navigate_history(target, self.proof())
                transport.call.assert_called_once_with(
                    {"action": "navigate_history", "target": target, "nav_proof": self.proof()})
                self.assertEqual(result["navigation_target"], target)
                self.assertIsInstance(result["source_id"], str)
                self.assertTrue(result["source_id"])
                self.assertEqual(result["as_of"], result["retrieved_at"])
                from product.trading_journal.common import iso_datetime
                iso_datetime(result["as_of"])
                self.assertNotIn("rows", result)
                self.assertNotIn("window", transport.call.call_args.args[0])
                self.assertNotIn("private_root", transport.call.call_args.args[0])
                transport.call.reset_mock()
        guard.assert_not_called()

    def test_navigation_rejects_invalid_target_and_proof_before_transport(self):
        from unittest.mock import Mock

        transport = Mock()
        collector = TigerDesktopCollector(transport=transport)
        for target in (None, False, [], {}, "query", "next_page", "export", "buy", "danger", "History"):
            with self.subTest(target=target), self.assertRaises(JournalError):
                collector.navigate_history(target, self.proof())
        proof = self.proof()
        invalid_proofs = [None, [], "untrusted", {},
                          {key: value for key, value in proof.items() if key != "version"},
                          {**proof, "bundle_id": "com.example.other"},
                          {**proof, "identity_hash": "A" * 64},
                          {**proof, "identity_hash": "a" * 63},
                          {**proof, "identity_hash": False}]
        for field in ("version", "build"):
            invalid_proofs.extend({**proof, field: value} for value in ("", " ", False, 12, {}, "x" * 4096))
        for value in invalid_proofs:
            with self.subTest(proof=value), self.assertRaises(JournalError):
                collector.navigate_history("history", value)
        transport.call.assert_not_called()

    def test_navigation_rejects_coordinates_keys_scripts_selectors_at_both_parameter_levels(self):
        from unittest.mock import Mock

        transport = Mock()
        collector = TigerDesktopCollector(transport=transport)
        for key, value in (("coordinates", {"x": 1, "y": 2}), ("x", 1), ("keys", ["return"]),
                           ("script", "arbitrary"), ("selector", {"label": "arbitrary"}),
                           ("profile", verified_profile()), ("window", {}), ("private_root", "/tmp")):
            with self.subTest(level="request", key=key), self.assertRaises(JournalError):
                collector._call("navigate_history", target="history", nav_proof=self.proof(), **{key: value})
            with self.subTest(level="proof", key=key), self.assertRaises(JournalError):
                collector.navigate_history("history", {**self.proof(), key: value})
        for field in ("bundle_id", "version", "build", "identity_hash"):
            with self.subTest(nested=field), self.assertRaises(JournalError):
                collector.navigate_history("history", {**self.proof(), field: {"selector": "arbitrary"}})
        transport.call.assert_not_called()

    def test_native_transport_navigation_uses_only_json_process_and_skips_financial_guard(self):
        from unittest.mock import patch

        for target in ("account_nav", "history", "statement_nav"):
            request = {"action": "navigate_history", "target": target, "nav_proof": self.proof()}
            expected = self.result(target)
            completed = subprocess.CompletedProcess(
                args=["synthetic-native-bridge"], returncode=0,
                stdout=json.dumps({"ok": True, "result": expected}).encode(), stderr=b"")
            with self.subTest(target=target), \
                    patch.object(NativeAXTransport, "_compile", return_value=Path("/synthetic-native-bridge")) as compile_bridge, \
                    patch("product.trading_journal.desktop.subprocess.run", return_value=completed) as process, \
                    patch("product.trading_journal.desktop._receipt_hash", side_effect=AssertionError("financial receipt forbidden")) as receipt, \
                    patch("product.trading_journal.privacy.assert_real_write_ready", side_effect=AssertionError("financial guard forbidden")) as guard:
                self.assertEqual(NativeAXTransport().call(request), expected)
            compile_bridge.assert_called_once_with()
            process.assert_called_once()
            call = process.call_args
            self.assertEqual(call.args[0], ["/synthetic-native-bridge"])
            self.assertEqual(json.loads(call.kwargs["input"]), request)
            self.assertNotIn("shell", call.kwargs)
            receipt.assert_not_called()
            guard.assert_not_called()

    def test_native_navigation_failure_preserves_only_fixed_stage_and_action_audit(self):
        from unittest.mock import patch
        request = {"action": "navigate_history", "target": "account_nav", "nav_proof": self.proof()}
        audits = [
            {"stage": "SIDEBAR_GEOMETRY_CHECK", "app_activation_requested": False, "navigation_action_issued": False},
            {"stage": "POST_LAYOUT_READ", "app_activation_requested": True, "navigation_action_issued": True},
        ]
        for audit in audits:
            response = {"ok": False, "code": "NAVIGATION_GEOMETRY_UNCONFIRMED", "nav_audit": audit}
            process = subprocess.CompletedProcess(args=["synthetic-bridge"], returncode=2,
                stdout=json.dumps(response).encode(), stderr=b"untrusted-not-forwarded")
            with self.subTest(audit=audit), patch.object(NativeAXTransport, "_compile", return_value=Path("/synthetic-bridge")), \
                    patch("product.trading_journal.desktop.subprocess.run", return_value=process):
                with self.assertRaises(JournalError) as failure:
                    NativeAXTransport().call(request)
                self.assertEqual(failure.exception.code, "NAVIGATION_GEOMETRY_UNCONFIRMED")
                self.assertEqual(failure.exception.details, {"nav_audit": audit})
                self.assertNotIn("untrusted", str(failure.exception))

    def test_native_navigation_failure_rejects_unknown_or_inconsistent_audit_without_echo(self):
        from unittest.mock import patch
        request = {"action": "navigate_history", "target": "account_nav", "nav_proof": self.proof()}
        audit = {"stage": "SIDEBAR_GEOMETRY_CHECK", "app_activation_requested": False, "navigation_action_issued": False}
        invalid = [None, {}, {**audit, "account_number": "private-not-a-real-account"},
                   {**audit, "stage": "private-not-a-real-account"}, {**audit, "app_activation_requested": 1},
                   {**audit, "navigation_action_issued": True}]
        for value in invalid:
            process = subprocess.CompletedProcess(args=["synthetic-bridge"], returncode=2,
                stdout=json.dumps({"ok": False, "code": "NAVIGATION_GEOMETRY_UNCONFIRMED", "nav_audit": value}).encode(), stderr=b"")
            with self.subTest(audit=value), patch.object(NativeAXTransport, "_compile", return_value=Path("/synthetic-bridge")), \
                    patch("product.trading_journal.desktop.subprocess.run", return_value=process):
                with self.assertRaises(JournalError) as failure:
                    NativeAXTransport().call(request)
                self.assertEqual(failure.exception.code, "INVALID_BRIDGE_RESPONSE")
                self.assertEqual(failure.exception.details, {})
                self.assertNotIn("private-not-a-real-account", str(failure.exception))

    @unittest.skipUnless(platform.system() == "Darwin", "Native navigation policy runs on macOS")
    def test_native_process_rejects_malformed_navigation_before_app_or_ax_access(self):
        binary = NativeAXTransport()._compile()
        request = {"action": "navigate_history", "target": "history", "nav_proof": self.proof()}
        invalid = [
            ({"action": "navigate_history"}, "ARGUMENT_NOT_ALLOWED"),
            ({**request, "target": "buy"}, "NAVIGATION_TARGET_REJECTED"),
            ({**request, "coordinates": {"x": 1, "y": 2}}, "ARGUMENT_NOT_ALLOWED"),
            ({**request, "nav_proof": {**self.proof(), "selector": "arbitrary"}}, "NAVIGATION_PROOF_INVALID"),
            ({**request, "nav_proof": {**self.proof(), "bundle_id": "com.example.other"}}, "NAVIGATION_PROOF_INVALID"),
            ({**request, "nav_proof": {**self.proof(), "identity_hash": "not-a-hash"}}, "NAVIGATION_PROOF_INVALID"),
            ({**request, "nav_proof": {key: value for key, value in self.proof().items() if key != "version"}}, "NAVIGATION_PROOF_INVALID"),
        ]
        for item, expected_code in invalid:
            with self.subTest(request=item):
                result = subprocess.run([str(binary)], input=json.dumps(item).encode(), capture_output=True, timeout=5)
                response = json.loads(result.stdout)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(set(response), {"ok", "code"})
                self.assertFalse(response["ok"])
                self.assertEqual(response["code"], expected_code)


if __name__ == "__main__":
    unittest.main()
