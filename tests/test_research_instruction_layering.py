"""角色配置和两条实际交付视图的接缝；不启动模型或产品批次。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from product.runtime.multidimensional_stage import (
    build_multidimensional_dispatch_packet,
    serialize_multidimensional_initial_context,
    serialize_multidimensional_model_context,
)
from product.runtime.research_submission import BOUNDED_REVISION_VERSION
from tests import test_research_submission as fixtures
from tests import test_live_cio_final_response as live_fixtures
from product.runtime import smoke_prompt

ROOT = Path(__file__).resolve().parents[1]


class NoTextRewrite(str):
    def replace(self, *args, **kwargs):
        raise AssertionError("task instruction must not be rewritten by substring replacement")


class ResearchInstructionLayeringTests(unittest.TestCase):
    def test_product_roles_load_registered_skills_and_keep_profile_permissions(self):
        profile = json.loads((ROOT / "product/runtime-profile.json").read_text())
        manifest = json.loads((ROOT / "product/version-manifest.json").read_text())
        for role in ("runtime_company_analyst", "runtime_company_analyst_common_stock",
                     "runtime_market_catalyst", "runtime_skeptic", "runtime_cio"):
            agent = tomllib.loads((ROOT / "product/.codex/agents" / f"{role}.toml").read_text())
            self.assertEqual(agent["name"], "runtime_company_analyst" if role.endswith("_common_stock") else role)
            self.assertEqual(agent["sandbox_mode"], "workspace-write" if role == "runtime_cio" else "read-only")
            self.assertEqual(agent["approval_policy"], "never")
            self.assertFalse(agent["tools"]["web_search"])
            self.assertFalse(agent["apps"]["_default"]["enabled"])
            for entry in agent["skills"]["config"]:
                self.assertTrue(entry["enabled"])
                resource = ROOT / "product" / entry["path"] / "SKILL.md"
                self.assertTrue(resource.is_file())
                # 版本仍来自现有 manifest；分层不另建一套版本权威。
                name = resource.parent.name
                self.assertIn(name, manifest["skills"])
            if role in profile["agents"]:
                self.assertEqual(agent["sandbox_mode"], profile["agents"][role]["sandbox_mode"])
        self.assertEqual(profile["common_stock_research_stage"]["stops_before"], [
            "runtime_skeptic", "runtime_cio", "deterministic_risk_engine",
        ])

    def test_live_prompt_composition_does_not_rewrite_generated_text_or_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _ = live_fixtures.LiveCioFinalResponseTests().prepared(directory)
            build = smoke_prompt._build_smoke_prompt
            dispatch = smoke_prompt._dispatch_messages(ROOT, run, ["runtime_company_analyst", "runtime_skeptic"])
            with patch.object(smoke_prompt, "_build_smoke_prompt", side_effect=lambda *args, **kwargs:
                              NoTextRewrite(build(*args, **kwargs))):
                prompt = smoke_prompt.build_smoke_prompt(run, repository_root=ROOT, defer_deterministic_finalize=True)
            self.assertIn(dispatch, prompt)
            self.assertIn("mcp__live_runtime__query", prompt)
            self.assertNotIn("mcp__fixture_runtime__query", prompt.split(dispatch)[0])
            snapshot = run / "audit/live/snapshot.json"
            self.assertIn(str(snapshot), prompt)
            self.assertEqual(json.loads((run / "run_manifest.json").read_text())["source_mode"], "live")

    def test_development_registration_models_permissions_and_skill_links_remain_effective(self):
        config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
        for name in ("dev_architect", "dev_contracts", "dev_reviewer", "dev_eval"):
            path = ROOT / ".codex" / config["agents"][name]["config_file"]
            agent = tomllib.loads(path.read_text())
            self.assertEqual(agent["sandbox_mode"], "read-only" if name == "dev_reviewer" else "workspace-write")
            self.assertIsInstance(agent["developer_instructions"], str)
            self.assertTrue(agent["developer_instructions"].strip())
            if name == "dev_eval":
                self.assertEqual(agent["model"], "gpt-5.6-terra")
                self.assertEqual(agent["tools"], {"web_search": False, "view_image": False})
                self.assertEqual(agent["apps"]["_default"], {
                    "enabled": False, "destructive_enabled": False, "open_world_enabled": False,
                })
                for skill in agent["skills"]["config"]:
                    self.assertTrue(skill["enabled"])
                    self.assertTrue((ROOT / skill["path"] / "SKILL.md").is_file())
            else:
                self.assertNotIn("model", agent)  # 保留原职责配置，不伪承诺跟随主线程。

    def test_both_delivery_views_preserve_task_text_and_derive_identical_draft_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = fixtures.ResearchSubmissionTests()
            _, run, task, _, _ = helper.submit_and_start(
                Path(directory), version=BOUNDED_REVISION_VERSION,
            )
            packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
            packet["instruction"] = NoTextRewrite(packet["instruction"])
            before = copy.deepcopy(packet)
            contexts = [json.loads(builder(packet)) for builder in (
                serialize_multidimensional_initial_context, serialize_multidimensional_model_context,
            )]
            self.assertEqual(packet, before)
            for context in contexts:
                self.assertTrue(context["instruction"].startswith(packet["instruction"]))
                self.assertEqual(context["minimum_questions"], packet["minimum_questions"])
                contract = context["submission_contract"]
                self.assertEqual(contract["version"], BOUNDED_REVISION_VERSION)
                self.assertEqual(contract["maximum_submissions"], 2)
                self.assertEqual(contract["tool"], "research_report_submit")
                self.assertEqual(contract["submission_token"], packet["submission_access"]["token"])
                schema = contract["draft_format_guide"]
                self.assertNotIn("agent", schema["properties"])
                self.assertIn("calculation_selections", schema["properties"])
                self.assertIn("document_selections", schema["properties"])
                self.assertNotIn("calculations", schema["properties"])
            self.assertEqual(contexts[0]["submission_contract"], contexts[1]["submission_contract"])
            self.assertEqual(contexts[0]["calculation_selection_contract"], contexts[1]["calculation_selection_contract"])


if __name__ == "__main__":
    unittest.main()
