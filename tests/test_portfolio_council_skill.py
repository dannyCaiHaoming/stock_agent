import json
import os
import subprocess
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
            self.assertIn("同一个 assistant 工具调用批次中并行发出", prompt)
            self.assertIn("禁止先等待第一条工具调用返回", prompt)
            self.assertIn("两个 `SubagentStart` 都早于任一 `SubagentStop`", prompt)
            self.assertIn("先完成 Analyst、再启动 Skeptic", prompt)

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

    def test_ablation_smoke_prompt_uses_declared_topology_and_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for profile, expected in (
                ("cio-only", []),
                ("analyst-cio", ["runtime_company_analyst"]),
                ("full-council", ["runtime_company_analyst", "runtime_skeptic"]),
            ):
                run_dir = root / profile
                prepare_run(
                    ROOT,
                    fixture_path=ROOT / "evals" / "fixtures" / "codex-native" / "normal-research.json",
                    run_dir=run_dir,
                    run_id=f"smoke-{profile}",
                    model="gpt-5.6-terra",
                    research_question="评估拓扑。",
                    authenticity_required=True,
                    run_mode="EVAL_ABLATION",
                    ablation_profile=profile,
                    trigger_reason=f"ablation:{profile}",
                )
                prompt = build_smoke_prompt(run_dir, repository_root=ROOT)
                self.assertIn("EVAL_ABLATION", prompt)
                self.assertIn("不可作为产品建议发布", prompt)
                self.assertIn(f"cd {ROOT}", prompt)
                for agent in expected:
                    self.assertIn(agent, prompt)
                if not expected:
                    self.assertIn("不启动 Specialist", prompt)
                else:
                    self.assertIn("禁止子 Agent 调用 file_change", prompt)
                    self.assertIn("mcp__fixture_runtime__query", prompt)

    def test_ablation_pre_agent_safe_termination_never_dispatches_or_uses_product_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "stale-ablation"
            result = prepare_run(
                ROOT,
                fixture_path=ROOT / "evals" / "fixtures" / "codex-native" / "future-or-stale.json",
                run_dir=run_dir,
                run_id="smoke-stale-ablation",
                model="gpt-5.6-terra",
                research_question="评估无可用 Evidence 的实验拓扑。",
                authenticity_required=True,
                run_mode="EVAL_ABLATION",
                ablation_profile="full-council",
                trigger_reason="ablation:mandatory-no-trade",
            )
            self.assertEqual(result["next_state"], "SAFE_NO_TRADE")
            prompt = build_smoke_prompt(run_dir, repository_root=ROOT)
            self.assertIn("PRE_AGENT_SAFE_TERMINATION", prompt)
            self.assertIn("禁止启动子 Agent", prompt)
            self.assertIn("不得运行产品 `check-run`", prompt)
            self.assertNotIn("spawn_agent", prompt)

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

    def test_plugin_mcp_starts_from_plugin_root_without_product_directory_name(self):
        config = json.loads((ROOT / "product" / ".mcp.json").read_text())
        server = config["mcpServers"]["fixture_runtime"]
        self.assertEqual(server["cwd"], ".")
        self.assertEqual(
            server["args"], ["-m", "runtime.fixture_mcp", "--stateless"]
        )
        self.assertNotIn("cd ..", " ".join(server["args"]))

        request = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        ) + "\n"
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [server["command"], *server["args"]],
            cwd=ROOT / "product",
            input=request,
            text=True,
            capture_output=True,
            env=env,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(
            [tool["name"] for tool in response["result"]["tools"]],
            ["query", "calculate"],
        )


if __name__ == "__main__":
    unittest.main()
