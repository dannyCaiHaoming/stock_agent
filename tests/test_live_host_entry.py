"""宿主分流接缝使用替身命令，不请求代理、Provider 或模型。"""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LiveHostEntryTests(unittest.TestCase):
    def test_retired_live_profile_is_rejected_before_any_command(self):
        result = subprocess.run(["/bin/bash", str(ROOT / "scripts/run-product-smoke.sh"), "--profile", "live-us-equity",
            "--portfolio", "/private/tmp/unused", "/private/tmp/unused-out"], capture_output=True, text=True,
            env={"PATH": "/nonexistent"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("LIVE_COUNCIL_ENTRY_RETIRED", result.stderr)
        self.assertIn("--stage common-stock-research --handoff", result.stderr)

    def test_help_only_advertises_handoff_research_entry(self):
        result = subprocess.run(
            ["/bin/bash", str(ROOT / "scripts/run-product-smoke.sh"), "--help"],
            capture_output=True,
            text=True,
            env={"PATH": "/nonexistent"},
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--stage common-stock-research --handoff", result.stdout)
        self.assertNotIn("--profile live-us-equity", result.stdout)

    def test_external_common_stock_gate_requires_complete_data_package(self):
        result = subprocess.run(
            [
                "/bin/bash", str(ROOT / "scripts/run-product-smoke.sh"),
                "--stage", "common-stock-research", "--handoff", "/private/tmp/handoff.json",
                "--gate", "/private/tmp/gate.json", "/private/tmp/output",
            ],
            capture_output=True, text=True, env={"PATH": "/nonexistent"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("COMMON_STOCK_DATA_PACKAGE_REQUIRED", result.stderr)


if __name__ == "__main__":
    unittest.main()
