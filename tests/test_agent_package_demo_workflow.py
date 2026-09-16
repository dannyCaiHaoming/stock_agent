from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentPackageDemoWorkflowTests(unittest.TestCase):
    def test_demo_is_explicit_milestone_and_real_product_priority_follows(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        product = (ROOT / "PRODUCT.md").read_text(encoding="utf-8")
        workflow = (ROOT / "docs/development/workflow.md").read_text(encoding="utf-8")
        self.assertIn("scripts/council-dev.py demo run", agents)
        self.assertIn("不属于真实产品 Smoke", agents)
        self.assertLess(product.index("Milestone 0"), product.index("真实股票"))
        self.assertIn("Demo PASS 只证明装配和契约", workflow)

    def test_advanced_assurance_remains_explicit_and_is_not_a_demo_followup(self):
        documents = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in (
                "AGENTS.md",
                "docs/development/workflow.md",
                "docs/product/agent-package-demo.md",
            )
        )
        self.assertIn("不得隐式启动", documents)
        self.assertIn("不执行 Runtime Eval", documents)
        for path in (
            "product/runtime/runtime_eval.py",
            "product/runtime/execution_replay.py",
            "evals/regression/runner.py",
            "evals/ablation/runtime.py",
            "evals/promotion/runtime_gate.py",
        ):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_self_check_does_not_accept_demo_or_advanced_commands(self):
        source = (ROOT / "scripts/council-dev.py").read_text(encoding="utf-8")
        match = re.search(r'allowed = \{([^}]+)\}', source)
        self.assertIsNotNone(match)
        allowed = match.group(1)
        self.assertIn("check-run", allowed)
        self.assertIn("trace-check", allowed)
        for forbidden in ("demo", "regression", "ablation", "promotion", "eval"):
            self.assertNotIn(f'"{forbidden}"', allowed)
        self.assertIn('arguments[0] == "demo"', source)
        self.assertIn('"product.demo.cli"', source)

    def test_apply_and_final_approval_boundaries_are_both_present(self):
        text = (ROOT / "docs/development/workflow.md").read_text(encoding="utf-8")
        self.assertIn("apply 获批后", text)
        self.assertIn("持续推进", text)
        self.assertIn("最终归档和推送仍需要一次明确人工完成批准", text)

    def test_demo_document_links_and_commands_use_repository_paths(self):
        path = ROOT / "docs/product/agent-package-demo.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("evals/fixtures/agent-package-demo/mvp-demo.json", text)
        self.assertIn("--agent runtime_company_analyst", text)
        self.assertIn("--agent runtime_skeptic", text)
        self.assertIn("--agent runtime_cio", text)
        self.assertNotIn("/Users/", text)

    def test_paused_live_change_state_is_not_rewritten(self):
        tasks = (
            ROOT / "openspec/changes/us-equity-live-advisory-slice/tasks.md"
        ).read_text(encoding="utf-8")
        for task in ("5.3", "5.4", "5.5"):
            self.assertRegex(tasks, rf"- \[ \] {task} ")
        permanent = (
            ROOT / "openspec/specs/three-plane-governance/spec.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("us-equity-live-advisory-slice", permanent)


if __name__ == "__main__":
    unittest.main()
