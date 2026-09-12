import json
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GovernanceTests(unittest.TestCase):
    def test_root_instructions_separate_checks_host_execution_and_review(self):
        text = (ROOT / "AGENTS.md").read_text()
        for expected in (
            "开发自检在当前 Codex 环境", "scripts/council-dev.py self-check",
            "不自动启动产品、模型、网络探针或项目沙箱",
            "真实 Smoke 与 Execution Replay 仅从宿主 Terminal",
            "scripts/run-product-smoke.sh", "--prepared-run",
            "独立复核默认读取差异、规格与已有证据",
            "不绕过宿主入口直接启动模型", "旧 review/probe/preflight 启动入口已退役",
        ):
            self.assertIn(expected, text)
        self.assertNotIn("运行工具入口为", text)
        environment = (ROOT / "docs/development/environment.md").read_text()
        self.assertIn("全进程源码强制只读为 **UNVERIFIED**", environment)
        self.assertIn("environment-preflight、permission-probe 和 --preflight-report", environment)
        self.assertIn("历史产物仅供读取", environment)

    def test_project_config_retains_native_settings_without_unused_profile(self):
        config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
        # 本 Change 基线的有效配置；只移除没有消费者的 project-edit 域名表。
        self.assertEqual(config["model"], "gpt-5.6-sol")
        self.assertEqual(config["sandbox_mode"], "workspace-write")
        self.assertEqual(config["sandbox_workspace_write"], {"network_access": True})
        self.assertEqual(config["agents"]["max_threads"], 4)
        self.assertEqual(
            set(config["agents"]) - {"max_threads"},
            {"dev_architect", "dev_contracts", "dev_eval", "dev_reviewer"},
        )
        for name in set(config["agents"]) - {"max_threads"}:
            registration = config["agents"][name]
            self.assertEqual(registration["config_file"], f"agents/{name}.toml")
            agent = tomllib.loads(
                (ROOT / ".codex" / registration["config_file"]).read_text()
            )
            self.assertTrue(registration["description"].strip())
            self.assertTrue(agent["description"].strip())

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

    def test_development_documents_are_conditional_and_roles_do_not_leak(self):
        root = (ROOT / "AGENTS.md").read_text()
        product = (ROOT / "product" / "AGENTS.md").read_text()
        for relative in (
            "docs/development/workflow.md",
            "docs/development/environment.md",
            "reviews/runtime/runtime-replay-eval-runbook.md",
        ):
            self.assertIn(relative, root)
            self.assertTrue((ROOT / relative).is_file())
        self.assertIn("无关专项文档不必全部加载", root)
        self.assertIn("默认用中文", root)
        self.assertIn("不执行 OpenSpec 归档、Git 提交或推送", product)
        workflow = (ROOT / "docs/development/workflow.md").read_text()
        self.assertIn("NOT_PROMOTABLE", workflow)
        self.assertIn("不默认重复 Calibration、Ablation、Promotion", workflow)
        self.assertIn("疑似敏感信息未处理时停止发布", workflow)

    def test_runbook_uses_existing_launcher_without_claiming_static_loading(self):
        text = (ROOT / "reviews/runtime/runtime-replay-eval-runbook.md").read_text()
        self.assertIn("bash <repository-root>/scripts/run-product-smoke.sh", text)
        self.assertIn("--prepared-run <run-dir> <new-invocation-output-dir>", text)
        self.assertIn("python3 <repository-root>/scripts/council-dev.py prepare-execution-replay", text)
        self.assertNotIn("python3 -m product.runtime.cli prepare-execution-replay", text)
        self.assertIn("host-replay-source.json", text)
        self.assertNotIn("--run-dir <run-dir> |", text)
        self.assertIn("不能只看 shell exit code", text)
        self.assertIn("按 manifest 选择冻结 workspace", text)

    def test_dev_agents_are_least_privilege(self):
        paths = sorted((ROOT / ".codex" / "agents").glob("dev_*.toml"))
        self.assertEqual(4, len(paths))
        for path in paths:
            config = tomllib.loads(path.read_text())
            self.assertTrue(config["name"].replace("_", "-").startswith("dev-"))
            self.assertIn("investment-decision", config["developer_instructions"])
            self.assertIn("broker-write", config["developer_instructions"])
        reviewer = tomllib.loads((ROOT / ".codex" / "agents" / "dev_reviewer.toml").read_text())
        self.assertEqual("read-only", reviewer["sandbox_mode"])

    def test_development_agents_are_registered_for_codex_native_delegation(self):
        config = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            {"dev_architect", "dev_contracts", "dev_eval", "dev_reviewer"},
            set(config["agents"]) - {"max_threads"},
        )
        self.assertEqual("agents/dev_eval.toml", config["agents"]["dev_eval"]["config_file"])

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
            "decision_contract",
            "resource_hashes",
            "skills",
            "agents",
            "schemas",
            "mcp_adapters",
            "risk_policy",
            "data_snapshot",
            "assurance",
            "assurance_hashes",
        }
        self.assertEqual(required, set(manifest))
        for key in required:
            self.assertTrue(manifest[key])


if __name__ == "__main__":
    unittest.main()
