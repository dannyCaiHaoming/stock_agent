from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RuntimeEvalSkillTests(unittest.TestCase):
    def test_skill_frontmatter_and_dev_eval_binding_are_valid(self):
        path = ROOT / ".agents" / "skills" / "runtime-eval-grading" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertRegex(frontmatter, r"(?m)^name: runtime-eval-grading$")
        self.assertRegex(frontmatter, r'(?m)^  version: "1\.0\.0"$')
        self.assertNotRegex(text, r"(?i)\[?TODO|placeholder|replace with")
        self.assertIn("不补充外部事实", text)
        self.assertIn("不修改 Thesis、动作", text)

        config = tomllib.loads((ROOT / ".codex" / "agents" / "dev_eval.toml").read_text(encoding="utf-8"))
        skills = config["skills"]["config"]
        self.assertEqual(skills, [{"path": ".agents/skills/runtime-eval-grading", "enabled": True}])
        root_config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual("agents/dev_eval.toml", root_config["agents"]["dev_eval"]["config_file"])


if __name__ == "__main__":
    unittest.main()
