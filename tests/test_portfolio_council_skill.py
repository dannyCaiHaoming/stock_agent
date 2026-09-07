import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.run_package import prepare_run
from product.runtime.smoke_prompt import build_smoke_prompt


ROOT = Path(__file__).resolve().parents[1]


class PortfolioCouncilSkillTests(unittest.TestCase):
    def test_skill_has_valid_minimal_frontmatter(self):
        text = (ROOT / "product" / "skills" / "portfolio-council" / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---\n", 2)[1]
        self.assertIn("name: portfolio-council", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertNotIn("TODO", text)

    def test_skill_encodes_bounded_council_protocol(self):
        text = (ROOT / "product" / "skills" / "portfolio-council" / "SKILL.md").read_text()
        for invariant in (
            "默认不得调用所有 runtime Agent",
            "source_id",
            "隔离上下文",
            "最多修订一次",
            "禁止覆盖 `REJECTED`",
            "advisory_only: true",
            "禁止创建、路由、修改或取消订单",
            "canonical decision contract",
            "failed_stage",
            "check-run",
        ):
            self.assertIn(invariant, text)

    def test_smoke_prompt_requires_artifact_based_release_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "smoke"
            prepare_run(
                ROOT,
                fixture_path=ROOT
                / "evals"
                / "fixtures"
                / "codex-native"
                / "normal-research.json",
                run_dir=run_dir,
                run_id="smoke-prompt-gate",
                model="gpt-5.6-terra",
                research_question="验证 Smoke Release Gate。",
            )
            prompt = build_smoke_prompt(run_dir, repository_root=ROOT)
            self.assertIn("product.runtime.cli check-run", prompt)
            self.assertIn("不得仅依据 `codex exec`", prompt)
            self.assertIn("canonical decision contract", prompt)
            self.assertIn("禁止传 `operands`、`expression` 或 `divide`", prompt)

    def test_smoke_prompt_respects_pre_agent_safe_termination(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "stale"
            result = prepare_run(
                ROOT,
                fixture_path=ROOT
                / "evals"
                / "fixtures"
                / "codex-native"
                / "future-or-stale.json",
                run_dir=run_dir,
                run_id="smoke-prompt-stale",
                model="gpt-5.6-terra",
                research_question="验证时点不足安全终止。",
            )
            self.assertEqual("SAFE_NO_TRADE", result["next_state"])
            prompt = build_smoke_prompt(run_dir, repository_root=ROOT)
            self.assertIn("PRE_AGENT_SAFE_TERMINATION", prompt)
            self.assertIn("禁止启动子 Agent", prompt)
            self.assertIn("product.runtime.cli eval", prompt)
            self.assertIn("product.runtime.cli check-run", prompt)
            self.assertNotIn("spawn_agent", prompt)
            self.assertNotIn("prepare-cio", prompt)

    def test_plugin_manifest_is_safe_and_complete(self):
        path = ROOT / "product" / ".codex-plugin" / "plugin.json"
        manifest = json.loads(path.read_text())
        self.assertEqual(path.parents[1].name, manifest["name"])
        self.assertRegex(manifest["version"], r"^0\.2\.4\+codex\.[A-Za-z0-9.-]+$")
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("apps", manifest)
        self.assertEqual("./.mcp.json", manifest["mcpServers"])
        self.assertIn("Portfolio Council", manifest["interface"]["displayName"])
        self.assertIsInstance(manifest["interface"]["defaultPrompt"], list)
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)


if __name__ == "__main__":
    unittest.main()
