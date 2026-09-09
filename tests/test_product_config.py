import json
import re
import tomllib
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "product" / "skills"
AGENTS_ROOT = ROOT / "product" / ".codex" / "agents"
EVALS_ROOT = ROOT / "evals" / "capabilities"

SKILL_NAMES = {
    "portfolio-council",
    "evidence-grounding",
    "company-research",
    "valuation",
    "counter-thesis",
    "catalyst-analysis",
}
AGENT_NAMES = {
    "runtime_cio",
    "runtime_company_analyst",
    "runtime_skeptic",
    "runtime_market_catalyst",
}
FIXTURE_COUNCIL_AGENTS = {
    "runtime_cio",
    "runtime_company_analyst",
    "runtime_skeptic",
}
LEGACY_SPECIALIST_AGENTS = AGENT_NAMES - {"runtime_cio"}
CONTRACT_SECTIONS = {
    "input",
    "tool_data",
    "skill_reasoning",
    "structured_output",
    "eval",
}
EXPECTED_STATUS = {
    "success": "COMPLETE",
    "failure": "FAILED",
    "timeout": "TIMEOUT",
    "missing_evidence": "INSUFFICIENT_EVIDENCE",
    "low_confidence": "LOW_CONFIDENCE",
}
READ_ONLY_TOOL_VERBS = {"lookup", "query", "calculate"}


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class SkillConfigTests(unittest.TestCase):
    def test_expected_skills_have_valid_minimal_frontmatter(self):
        found = {path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md")}
        self.assertTrue(SKILL_NAMES.issubset(found))

        for skill_name in sorted(SKILL_NAMES):
            text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            frontmatter, body = text[4:].split("\n---\n", 1)
            fields = {
                key.strip(): value.strip()
                for line in frontmatter.splitlines()
                if ":" in line
                for key, value in [line.split(":", 1)]
            }
            self.assertEqual(fields.get("name"), skill_name)
            expected_version = (
                "1.0.0"
                if skill_name == "catalyst-analysis"
                else "3.0.0"
                if skill_name == "portfolio-council"
                else "2.0.0"
            )
            self.assertNotRegex(frontmatter, r"(?m)^version:")
            self.assertRegex(
                frontmatter,
                rf"(?m)^metadata:\n  version: [\"']?{re.escape(expected_version)}[\"']?$",
            )
            self.assertTrue(fields.get("description", "").strip())
            self.assertTrue(body.strip())
            self.assertNotRegex(text, r"(?i)TODO|replace with|placeholder")

    def test_skills_preserve_reasoning_and_execution_boundaries(self):
        combined = "\n".join(
            (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
            for name in sorted(SKILL_NAMES)
        )
        for field in ("source_id", "as_of", "retrieved_at"):
            self.assertIn(field, combined)
        self.assertIn("确定性", combined)
        self.assertIn("不得生成组合动作", combined)
        self.assertIn("INDEPENDENT_FIRST_PASS", combined)


class RuntimeAgentConfigTests(unittest.TestCase):
    def setUp(self):
        self.configs = {}
        for path in AGENTS_ROOT.glob("*.toml"):
            with path.open("rb") as handle:
                self.configs[path.stem] = tomllib.load(handle)
        self.profile = load_json(ROOT / "product" / "runtime-profile.json")

    def test_expected_agents_are_valid_least_privilege_codex_configs(self):
        self.assertEqual(set(self.configs), AGENT_NAMES)
        for filename, config in self.configs.items():
            self.assertEqual(config["name"], filename)
            self.assertTrue(config["description"])
            self.assertTrue(config["developer_instructions"])
            expected_sandbox = "workspace-write" if filename == "runtime_cio" else "read-only"
            self.assertEqual(config["sandbox_mode"], expected_sandbox)
            self.assertEqual(config["approval_policy"], "never")
            self.assertFalse(config["tools"]["web_search"])
            self.assertFalse(config["tools"]["view_image"])
            self.assertFalse(config["apps"]["_default"]["enabled"])
            self.assertFalse(config["apps"]["_default"]["destructive_enabled"])
            self.assertFalse(config["apps"]["_default"]["open_world_enabled"])

    def test_agents_enable_only_declared_product_skills(self):
        expected = {
            "runtime_cio": {"portfolio-council"},
            "runtime_company_analyst": {
                "evidence-grounding",
                "company-research",
                "valuation",
            },
            "runtime_skeptic": {"evidence-grounding", "counter-thesis"},
            "runtime_market_catalyst": {
                "evidence-grounding",
                "catalyst-analysis",
            },
        }
        for agent, config in self.configs.items():
            skill_entries = config["skills"]["config"]
            self.assertTrue(all(item["enabled"] for item in skill_entries))
            configured = {Path(item["path"]).name for item in skill_entries}
            self.assertEqual(configured, expected[agent])
            for item in skill_entries:
                self.assertTrue((ROOT / "product" / item["path"] / "SKILL.md").is_file())

    def test_agent_tool_allowlists_are_read_only_and_outputs_are_structured(self):
        for name, config in self.configs.items():
            instructions = config["developer_instructions"]
            tools = re.findall(r"[a-z_]+\.(?:lookup|query|calculate|check)", instructions)
            self.assertTrue(tools, name)
            self.assertTrue(
                all(tool.rsplit(".", 1)[1] in READ_ONLY_TOOL_VERBS | {"check"} for tool in tools)
            )
            if name in FIXTURE_COUNCIL_AGENTS:
                configured_tools = self.profile["agents"][name]["tool_permissions"]
                self.assertTrue(configured_tools)
                self.assertTrue(
                    all(
                        tool.rsplit(".", 1)[1] in READ_ONLY_TOOL_VERBS | {"check"}
                        for tool in configured_tools
                    )
                )
            if name != "runtime_cio":
                self.assertIn("只返回一个", instructions)
                self.assertIn("data_gaps", instructions)
                self.assertIn("TIMEOUT", instructions)

    def test_fixture_profile_has_three_distinct_versioned_identities(self):
        profile = {name: self.configs[name] for name in FIXTURE_COUNCIL_AGENTS}
        self.assertEqual(
            {
                name: self.profile["agents"][name]["version"]
                for name in profile
            },
            {
                "runtime_cio": "3.0.0",
                "runtime_company_analyst": "2.1.0",
                "runtime_skeptic": "2.0.0",
            },
        )
        self.assertEqual({config["name"] for config in profile.values()}, FIXTURE_COUNCIL_AGENTS)
        self.assertEqual(
            len({config["developer_instructions"] for config in profile.values()}),
            len(FIXTURE_COUNCIL_AGENTS),
        )
        self.assertNotIn("runtime_market_catalyst", FIXTURE_COUNCIL_AGENTS)
        self.assertEqual(self.profile["parallel_first_pass"], [
            "runtime_company_analyst",
            "runtime_skeptic",
        ])

    def test_specialist_boundaries_are_explicit(self):
        company = self.configs["runtime_company_analyst"]["developer_instructions"]
        skeptic = self.configs["runtime_skeptic"]["developer_instructions"]
        catalyst = self.configs["runtime_market_catalyst"]["developer_instructions"]
        cio = self.configs["runtime_cio"]["developer_instructions"]
        self.assertIn("禁止输出组合动作", company)
        self.assertIn("CONTEXT_ISOLATION_VIOLATION", skeptic)
        self.assertIn("禁止选择最终组合动作", skeptic)
        self.assertIn("禁止选择最终组合动作", catalyst)
        self.assertIn("deterministic Risk Engine", cio)
        self.assertIn("不得覆盖 REJECTED", cio)


class CapabilityRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_json(EVALS_ROOT / "registry.json")

    def test_registry_requires_complete_five_part_contracts(self):
        policy = self.registry["production_registration_policy"]
        self.assertEqual(set(policy["required_contract_sections"]), CONTRACT_SECTIONS)
        self.assertTrue(policy["eval_required"])

        capabilities = self.registry["capabilities"]
        self.assertEqual(
            {item["capability_id"] for item in capabilities}, SKILL_NAMES
        )
        for capability in capabilities:
            self.assertTrue(capability["production"])
            self.assertEqual(set(capability["contract"]), CONTRACT_SECTIONS)
            evaluation = capability["contract"]["eval"]
            self.assertTrue(evaluation["fixtures"])
            self.assertTrue(evaluation["acceptance"])
            for relative_path in evaluation["fixtures"]:
                self.assertTrue((EVALS_ROOT / relative_path).is_file())

    def test_registry_tools_are_read_only_by_name(self):
        for capability in self.registry["capabilities"]:
            tools = capability["contract"]["tool_data"]["read_only_tools"]
            self.assertTrue(tools)
            for tool in tools:
                self.assertIn(tool.rsplit(".", 1)[-1], READ_ONLY_TOOL_VERBS)

    def test_each_runtime_agent_maps_to_real_capabilities_and_an_ablation(self):
        agents = self.registry["runtime_agents"]
        self.assertEqual({item["agent_id"] for item in agents}, AGENT_NAMES)
        registered = {item["capability_id"] for item in self.registry["capabilities"]}
        for agent in agents:
            self.assertTrue(agent["capabilities"])
            self.assertTrue(set(agent["capabilities"]) <= registered)
            self.assertTrue(agent["ablation_baseline"])

    def test_fixture_council_roles_have_complete_execution_contracts(self):
        profile = self.registry["fixture_council_profile"]
        self.assertEqual(set(profile["agents"]), FIXTURE_COUNCIL_AGENTS)
        self.assertEqual(profile["parallel_first_pass"], [
            "runtime_company_analyst",
            "runtime_skeptic",
        ])
        self.assertNotIn("runtime_market_catalyst", profile["agents"])

        contracts = self.registry["council_role_contracts"]
        self.assertEqual({item["agent_id"] for item in contracts}, FIXTURE_COUNCIL_AGENTS)
        for role in contracts:
            self.assertEqual(set(role["contract"]), CONTRACT_SECTIONS)
            self.assertTrue(role["contract"]["input"]["required"])
            self.assertTrue(role["contract"]["tool_data"]["read_only_tools"])
            self.assertTrue(role["contract"]["skill_reasoning"]["skills"])
            self.assertTrue(role["contract"]["structured_output"]["required"])
            self.assertTrue(role["contract"]["eval"]["acceptance"])

    def test_fixture_matrix_covers_every_agent_and_failure_mode(self):
        for scenario, expected_status in EXPECTED_STATUS.items():
            fixture = load_json(EVALS_ROOT / "fixtures" / f"{scenario}.json")
            self.assertEqual(fixture["scenario_type"], scenario)
            self.assertEqual(
                {case["agent"] for case in fixture["cases"]},
                LEGACY_SPECIALIST_AGENTS,
            )
            for case in fixture["cases"]:
                expected = case["expected"]
                self.assertEqual(expected["status"], expected_status)
                if scenario != "success":
                    self.assertFalse(expected["unsupported_claims_allowed"])

    def test_skeptic_first_pass_fixture_proves_context_isolation(self):
        success = load_json(EVALS_ROOT / "fixtures" / "success.json")
        isolated = next(
            case for case in success["cases"] if case["agent"] == "runtime_skeptic"
        )
        self.assertEqual(isolated["input_context"]["mode"], "INDEPENDENT_FIRST_PASS")
        self.assertFalse(isolated["input_context"]["includes_other_agent_conclusions"])

        failure = load_json(EVALS_ROOT / "fixtures" / "failure.json")
        violation = next(
            case for case in failure["cases"] if case["agent"] == "runtime_skeptic"
        )
        self.assertTrue(violation["input_context"]["includes_other_agent_conclusions"])
        self.assertEqual(
            violation["expected"]["required_gap_code"],
            "CONTEXT_ISOLATION_VIOLATION",
        )

    def test_valuation_golden_cases_are_deterministic_tool_outputs(self):
        fixture = load_json(EVALS_ROOT / "fixtures" / "valuation_golden.json")
        self.assertEqual(fixture["owner"], "deterministic_valuation_tool")
        self.assertTrue(
            fixture["agent_expectation"]["must_reference_calculation_artifact"]
        )
        self.assertTrue(fixture["agent_expectation"]["must_not_recompute"])

        present_value = fixture["cases"][0]
        pv_inputs = present_value["inputs"]
        calculated = Decimal(pv_inputs["cash_flow"]) / (
            Decimal("1") + Decimal(pv_inputs["discount_rate"])
        ) ** pv_inputs["periods"]
        self.assertEqual(
            calculated.quantize(Decimal("0.01")),
            Decimal(present_value["expected"]["present_value"]),
        )

        equity = fixture["cases"][1]
        eq_inputs = equity["inputs"]
        equity_value = (
            Decimal(eq_inputs["enterprise_value"])
            + Decimal(eq_inputs["cash"])
            - Decimal(eq_inputs["debt"])
        )
        self.assertEqual(equity_value, Decimal(equity["expected"]["equity_value"]))
        self.assertEqual(
            equity_value / Decimal(eq_inputs["shares"]),
            Decimal(equity["expected"]["value_per_share"]),
        )


if __name__ == "__main__":
    unittest.main()
