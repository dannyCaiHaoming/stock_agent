from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from product.broker.tiger.cli import _error_code, main
from product.broker.tiger.ledger import PrivateBrokerLedger


class TigerCliTests(unittest.TestCase):
    def capture(self, argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(argv)
        return code, json.loads(output.getvalue())

    def test_help_lists_only_explicit_commands(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        for command in ("preflight", "snapshot", "sync", "analyze"):
            self.assertIn(command, output.getvalue())
        for forbidden in ("place-order", "cancel-order", "transfer", "daemon"):
            self.assertNotIn(forbidden, output.getvalue())

    def test_network_commands_require_host_launcher_before_adapter_construction(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "product.broker.tiger.cli.TigerReadOnlyAdapter.from_config"
        ) as constructor:
            code, result = self.capture([
                "snapshot", "--config-dir", "/private/config", "--ledger-root", "/private/ledger",
            ])
        self.assertEqual((code, result["code"]), (2, "TIGER_HOST_LAUNCHER_REQUIRED"))
        constructor.assert_not_called()

    def test_error_output_only_preserves_stable_allowlisted_codes(self):
        self.assertEqual(_error_code(ValueError("TIGER_CONFIG_FILE_MISSING")), "TIGER_CONFIG_FILE_MISSING")
        self.assertEqual(_error_code(ValueError("privateTokenMaterial123")), "TIGER_COMMAND_FAILED")
        self.assertEqual(_error_code(ValueError("provider leaked sensitive detail")), "TIGER_COMMAND_FAILED")

    def test_analyze_is_offline_repeatable_and_outputs_only_status_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = Path(__file__).resolve().parents[1]
            ledger_root = base / "private"
            ledger = PrivateBrokerLedger(ledger_root, repository_root=repository, create=True)
            account_ref = ledger.get_or_create_account_ref()
            cutoff = "2026-09-23T00:00:00Z"
            first_code, first = self.capture([
                "analyze", "--ledger-root", str(ledger_root), "--account-ref", account_ref, "--cutoff", cutoff,
            ])
            second_code, second = self.capture([
                "analyze", "--ledger-root", str(ledger_root), "--account-ref", account_ref, "--cutoff", cutoff,
            ])
            self.assertEqual((first_code, second_code), (0, 0))
            self.assertEqual(first["ledger_hash"], second["ledger_hash"])
            self.assertEqual((first["metric_count"], first["chart_count"]), (20, 6))
            serialized = json.dumps(first)
            self.assertNotIn("activity", serialized)
            self.assertNotIn(str(ledger_root), serialized)

    def test_host_launcher_exposes_preflight_without_starting_normal_smoke(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config"
            config.mkdir(mode=0o700)
            properties = config / "tiger_openapi_config.properties"
            token = config / "tiger_openapi_token.properties"
            properties.write_text("tiger_id=local\naccount=private\nprivate_key=secret\nlicense=TBHK\n")
            token.write_text("token=private-token\n")
            os.chmod(properties, 0o600)
            os.chmod(token, 0o600)
            result = subprocess.run(
                ["bash", "scripts/run-product-smoke.sh", "--tiger-readonly", "preflight", "--config-dir", str(config)],
                cwd=repository, text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual((value["status"], value["license"]), ("READY", "TBHK"))
            self.assertNotIn("private-token", result.stdout)
            self.assertNotIn("secret", result.stdout)

        help_result = subprocess.run(
            ["bash", "scripts/run-product-smoke.sh", "--help"], cwd=repository,
            text=True, capture_output=True, check=False,
        )
        self.assertIn("--tiger-readonly", help_result.stdout)


if __name__ == "__main__":
    unittest.main()
