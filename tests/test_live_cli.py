"""退役 live 创建入口的前置拒绝接缝。"""
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

    def test_prepare_live_rejects_before_data_network_or_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve()
            output = io.StringIO()
            with patch("pathlib.Path.read_text", side_effect=AssertionError("退役入口读取了数据")), \
                    patch("product.runtime.cli.launch_nested_codex", side_effect=AssertionError("退役入口启动了模型")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.arguments(directory)), 2)
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(self.arguments(directory)), 2)
            result = json.loads(output.getvalue())
            self.assertEqual(result["failure_code"], "LIVE_COUNCIL_ENTRY_RETIRED")
            self.assertEqual(result["data_reads"], 0)
            self.assertEqual(result["network_calls"], 0)
            self.assertEqual(result["llm_calls"], 0)

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
