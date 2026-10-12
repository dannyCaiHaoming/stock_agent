import json
import os
import subprocess
import sys
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
            "默认不自动进入CIO",
            "source_id/as_of/retrieved_at",
            "原生独立上下文",
            "最多一次原作者修订",
            "原硬Risk否决不可覆盖",
            "advisory_only=true",
            "禁止订单创建/预览/路由/修改/取消",
            "业务VALIDATED",
            "首稿REVISE_REQUIRED",
            "历史产物只读",
            "SINGLE_STOCK_RESEARCH",
            "normalize_single_stock_intent",
            "resolve_single_stock_identity",
            "collect_single_stock_research_data",
            "collect_single_stock_snapshot",
            "freeze_latest_research_request",
            "research_prepare_single_stock",
            "research_authorize_single_stock",
            "anthropic/requiresUserInteraction",
            "company_authorization",
            "AUTHORIZATION_REQUIRED",
            "authorization_action",
            "expected_request_hash/expected_gate_hash",
            "research_prepare_task",
            "preparation_token",
            "prepare bind",
            "task_ref",
            "task_token",
        ):
            self.assertIn(invariant, text)


    def test_plugin_manifest_is_safe_and_complete(self):
        path = ROOT / "product" / ".codex-plugin" / "plugin.json"
        manifest = json.loads(path.read_text())
        self.assertEqual(path.parents[1].name, manifest["name"])
        self.assertRegex(manifest["version"], r"^0\.3\.0\+codex\.[A-Za-z0-9.-]+$")
        self.assertEqual("./skills/", manifest["skills"])
        self.assertNotIn("apps", manifest)
        self.assertEqual("./.mcp.json", manifest["mcpServers"])
        self.assertIn("Portfolio Council", manifest["interface"]["displayName"])
        self.assertIsInstance(manifest["interface"]["defaultPrompt"], list)
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)

    def test_product_default_has_no_legacy_research_connection(self):
        # 本机派生文件不是发布源；存在时也不得默认启用旧fixture/live服务。
        path = ROOT / "product/.mcp.json"
        if path.exists():
            self.assertFalse({"fixture_runtime", "live_runtime"} & set(json.loads(path.read_text())["mcpServers"]))

    def test_explicit_fixture_transport_starts_from_product_root_without_launcher(self):
        request = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        ) + "\n"
        env = {
            key: value for key, value in os.environ.items()
            if not key.startswith("STOCK_AGENT_")
        }
        env.update(
            PYTHONDONTWRITEBYTECODE="1",
            STOCK_AGENT_FIXTURE_MCP_PYTHON=sys.executable,
            STOCK_AGENT_FIXTURE_MCP_PYTHONPATH=os.pathsep.join(
                dict.fromkeys([str(ROOT), str(ROOT / "product"), *(
                    value for value in sys.path if Path(value).is_absolute()
                )])
            ),
        )
        result = subprocess.run(
            ["/bin/sh", "runtime/launch_fixture_mcp.sh", "--stateless"],
            cwd=ROOT / "product", input=request, text=True,
            capture_output=True, env=env, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(
            [tool["name"] for tool in response["result"]["tools"]],
            ["query", "calculate", "research_search", "research_fetch"],
        )


if __name__ == "__main__":
    unittest.main()
