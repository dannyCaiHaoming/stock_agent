import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GovernanceTests(unittest.TestCase):
    def test_development_control_plane_has_no_runtime_authority(self):
        text = (ROOT / "AGENTS.md").read_text()
        self.assertIn("不继承产品运行时 CIO 权限", text)
        self.assertIn("禁止增加券商接入", text)

    def test_runtime_plane_is_advisory_and_read_only(self):
        text = (ROOT / "product" / "AGENTS.md").read_text()
        self.assertIn("只读", text)
        self.assertIn("NO_TRADE", text)
        self.assertIn("advisory_only: true", text)
        self.assertIn("禁止创建、路由、修改或取消订单", text)
        self.assertIn("禁止在运行时任务中编辑产品 Skill", text)

    def test_dev_agents_are_least_privilege(self):
        paths = sorted((ROOT / ".codex" / "agents").glob("dev_*.toml"))
        self.assertEqual(4, len(paths))
        for path in paths:
            config = tomllib.loads(path.read_text())
            self.assertTrue(config["name"].startswith("dev-"))
            self.assertIn("investment-decision", config["developer_instructions"])
            self.assertIn("broker-write", config["developer_instructions"])
        reviewer = tomllib.loads((ROOT / ".codex" / "agents" / "dev_reviewer.toml").read_text())
        self.assertEqual("read-only", reviewer["sandbox_mode"])

    def test_capability_template_has_five_required_sections(self):
        template = (ROOT / "reviews" / "capability-contract-template.md").read_text()
        for heading in ("## Input", "## Tool / Data", "## Skill / Reasoning", "## Structured Output", "## Eval"):
            self.assertIn(heading, template)
        example = (ROOT / "reviews" / "examples" / "company-research-capability.md").read_text()
        self.assertNotIn("<name>", example)

    def test_version_manifest_is_complete(self):
        manifest = json.loads((ROOT / "product" / "version-manifest.json").read_text())
        required = {
            "manifest_version",
            "candidate_version",
            "codex_runtime",
            "model",
            "runtime_profile",
            "resource_hashes",
            "skills",
            "agents",
            "schemas",
            "mcp_adapters",
            "risk_policy",
            "data_snapshot",
        }
        self.assertEqual(required, set(manifest))
        for key in required:
            self.assertTrue(manifest[key])


if __name__ == "__main__":
    unittest.main()
