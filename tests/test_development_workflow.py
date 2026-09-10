"""开发文档与配置的静态接缝；不证明模型加载或真实执行行为。"""

import copy
import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("AGENTS.md", "docs/development/workflow.md", "docs/development/environment.md")
FORBIDDEN = {"filesystem-write", "investment-decision", "broker-write", "production-promotion"}


def reviewer_contract(config):
    """仅检查配置结构和关键权限标记，不将文字当作权限执行证明。"""
    if config.get("name") != "dev-reviewer" or config.get("sandbox_mode") != "read-only":
        raise ValueError("REVIEWER_READ_ONLY_REQUIRED")
    instructions = config.get("developer_instructions", "")
    if not isinstance(instructions, str) or not FORBIDDEN <= set(re.findall(r"[a-z]+(?:-[a-z]+)+", instructions)):
        raise ValueError("REVIEWER_BOUNDARY_MARKERS_MISSING")
    if "model" in config and (not isinstance(config["model"], str) or not config["model"].strip()):
        raise ValueError("MODEL_CONFIG_INVALID")


class DevelopmentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root_config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
        registration = self.root_config["agents"]["dev_reviewer"]
        self.reviewer = tomllib.loads((ROOT / ".codex" / registration["config_file"]).read_text())

    def test_local_document_links_resolve(self):
        checked = 0
        for name in DOCUMENTS:
            document = ROOT / name
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text()):
                if "://" in target or target.startswith("#"):
                    continue
                with self.subTest(document=name, target=target):
                    self.assertTrue((document.parent / target.split("#", 1)[0]).resolve().is_file())
                checked += 1
        self.assertGreater(checked, 0)

    def test_registered_development_agents_parse(self):
        for name, registration in self.root_config["agents"].items():
            if not isinstance(registration, dict):
                continue
            with self.subTest(agent=name):
                path = (ROOT / ".codex" / registration["config_file"]).resolve()
                self.assertTrue(path.is_relative_to(ROOT / ".codex/agents"))
                config = tomllib.loads(path.read_text())
                self.assertIsInstance(config["developer_instructions"], str)

    def test_reviewer_registration_and_readonly_contract(self):
        self.assertEqual(self.root_config["agents"]["dev_reviewer"]["description"], self.reviewer["description"])
        reviewer_contract(self.reviewer)

    def test_write_enabled_reviewer_is_rejected(self):
        for mode in ("workspace-write", "danger-full-access", None):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "REVIEWER_READ_ONLY_REQUIRED"):
                reviewer_contract({**self.reviewer, "sandbox_mode": mode})

    def test_each_missing_boundary_marker_is_rejected(self):
        for marker in FORBIDDEN:
            config = copy.deepcopy(self.reviewer)
            config["developer_instructions"] = config["developer_instructions"].replace(marker, "")
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, "REVIEWER_BOUNDARY_MARKERS_MISSING"):
                reviewer_contract(config)

    def test_optional_reviewer_model_is_not_bound_to_parent_or_product(self):
        config = copy.deepcopy(self.reviewer)
        config.pop("model", None)
        reviewer_contract(config)
        for model in ("gpt-5.6-sol", "gpt-6-astra"):
            reviewer_contract({**config, "model": model})
        # 配置结构接受不同值，不代表改变生效模型或证明账户可用性。
        for model in ("", 1, None):
            with self.subTest(model=model), self.assertRaisesRegex(ValueError, "MODEL_CONFIG_INVALID"):
                reviewer_contract({**config, "model": model})


if __name__ == "__main__":
    unittest.main()
