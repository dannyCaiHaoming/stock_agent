import json
import unittest
from pathlib import Path


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
        ):
            self.assertIn(invariant, text)

    def test_plugin_manifest_is_safe_and_complete(self):
        path = ROOT / "product" / ".codex-plugin" / "plugin.json"
        manifest = json.loads(path.read_text())
        self.assertEqual(path.parents[1].name, manifest["name"])
        self.assertEqual("0.1.0", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("apps", manifest)
        self.assertNotIn("mcpServers", manifest)
        self.assertIn("Portfolio Council", manifest["interface"]["displayName"])
        self.assertIsInstance(manifest["interface"]["defaultPrompt"], list)
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)


if __name__ == "__main__":
    unittest.main()
