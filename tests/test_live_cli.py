"""冻结数据准备入口的零网络/零模型接缝；不证明真实采集或研究。"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.cli import build_parser, main


ROOT = Path(__file__).resolve().parents[1]


class LiveCLITests(unittest.TestCase):
    def test_documentation_example_is_synthetic_and_schema_valid(self):
        from product.mcp.live.contracts import validate_contract
        example = json.loads((ROOT / "docs/product/examples/live-portfolio.synthetic.json").read_text())
        validate_contract("portfolio", example)
        self.assertIs(example["synthetic_portfolio"], True)
        self.assertNotIn("@", json.dumps(example))
        sources = json.loads((ROOT / "docs/product/examples/live-source-access-v3.synthetic.json").read_text())
        self.assertEqual({s["provider"] for s in sources}, {"nasdaq", "yahoo", "eastmoney", "sec"})
        for source in sources:
            validate_contract("source-access", source)
            self.assertEqual(source["status"], "UNCONFIRMED")
            self.assertNotIn("@", json.dumps(source))

    def arguments(self, directory):
        return ["prepare-live", "--repo", str(ROOT), "--profile", "live-us-equity",
                "--portfolio", str(directory / "portfolio.json"),
                "--snapshot", str(directory / "snapshot.json"),
                "--cache-root", str(directory / "cache"),
                "--calendar-lock", str(directory / "calendar.json"),
                "--run-dir", str(directory / "run"), "--run-id", "cli-offline",
                "--model", "test-only", "--focus-security-id", "TEST"]

    def test_prepare_forwards_frozen_inputs_without_launching_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve()
            record = {"synthetic": True}
            (directory / "calendar.json").write_text(json.dumps(record))
            calendar = object()
            with patch("product.mcp.live.market.load_locked_calendar", return_value=calendar) as load, \
                    patch("product.runtime.cli.prepare_live_run", return_value={"next_state": "DISPATCH_REQUIRED"}) as prepare, \
                    patch("product.runtime.cli.launch_nested_codex", side_effect=AssertionError("隐式模型启动")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.arguments(directory)), 0)
            load.assert_called_once_with(record)
            self.assertEqual(prepare.call_args.kwargs["calendar"], calendar)
            self.assertEqual(prepare.call_args.kwargs["focus_security_id"], "TEST")
            self.assertNotIn("authenticity_required", prepare.call_args.kwargs)

    def test_invalid_calendar_fails_before_prepare(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with patch("product.runtime.cli.prepare_live_run", side_effect=AssertionError("错误输入进入 prepare")), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(main(self.arguments(Path(tmp))), 2)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["llm_calls"], 0)

    def test_failed_validation_exit_is_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve()
            (directory / "calendar.json").write_text("{}")
            with patch("product.mcp.live.market.load_locked_calendar"), \
                    patch("product.runtime.cli.prepare_live_run", return_value={"next_state": "FAILED_VALIDATION"}), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.arguments(directory)), 2)

    def test_unknown_profile_and_test_authenticity_flag_are_rejected(self):
        for change in ("unknown", "--allow-test-artifacts"):
            arguments = self.arguments(Path("/private/tmp/example"))
            if change == "unknown":
                arguments[arguments.index("live-us-equity")] = change
            else:
                arguments.append(change)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                build_parser().parse_args(arguments)

    def test_self_check_cannot_dispatch_live_prepare(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/council-dev.py"),
                                 "self-check", "prepare-live"], cwd="/private/tmp",
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertIn("SELF_CHECK_COMMAND_NOT_ALLOWED", result.stdout)


if __name__ == "__main__":
    unittest.main()
