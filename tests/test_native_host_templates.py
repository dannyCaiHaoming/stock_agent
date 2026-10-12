"""共享正文与宿主薄配置的确定性检查，不证明宿主实际加载。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest

from product.mcp.research import tool_manifest, preparation_tool_manifest
from product.runtime.versioning import read_skill_version
from product.tools.research import prepare_task
from tests.test_native_research_tools import SECURITY, frozen_gate
from tests.test_single_stock_input import alb_request

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT/"product"
ROLES = ("runtime_company_analyst", "runtime_market_catalyst", "runtime_skeptic")


def frontmatter(path):
    text = path.read_text()
    header, body = text[4:].split("\n---\n", 1)
    scalars, lists = {}, {}
    current = None
    for line in header.splitlines():
        if line.startswith("  - "):
            lists[current].append(line[4:])
        else:
            key, value = line.split(":", 1)
            if value.strip():
                scalars[key] = value.strip()
                current = None
            else:
                current = key
                lists[key] = []
    return scalars, lists, body


class NativeHostTemplateTests(unittest.TestCase):
    def test_shared_role_sources_have_no_private_dispatch_or_launcher_parameters(self):
        for name in (*ROLES, "runtime_cio"):
            text = (PRODUCT/"agents"/(name+".md")).read_text()
            self.assertTrue(text.strip())
            for obsolete in ("codex exec", "wait_agent", "fork_turns", "SubagentStart", "SubagentStop", "process-result.json"):
                self.assertNotIn(obsolete, text)
        self.assertIn("当前宿主主线程", (PRODUCT/"skills/portfolio-council/SKILL.md").read_text())

    def test_council_source_observation_does_not_fork_or_preapprove_tools(self):
        scalars, lists, _ = frontmatter(PRODUCT/"skills/portfolio-council/SKILL.md")
        self.assertEqual(scalars["name"], "portfolio-council")
        for field in ("context", "agent", "model", "allowed-tools"):
            self.assertNotIn(field, scalars)
            self.assertNotIn(field, lists)
        for name in ("company", "market", "skeptic"):
            header, _, _ = frontmatter(PRODUCT/f"hosts/claude-code/skills/{name}-native/SKILL.md")
            self.assertEqual(header["context"], "fork")
            self.assertIn(header["agent"], ROLES)

    def test_current_skill_versions_match_manifest(self):
        manifest = json.loads((PRODUCT/"version-manifest.json").read_text())
        for name in ("portfolio-council", "counter-thesis"):
            self.assertEqual(read_skill_version(PRODUCT/"skills"/name/"SKILL.md"), manifest["skills"][name])

    def test_codex_templates_bind_only_one_role_and_disable_builtin_shell(self):
        config = tomllib.loads((PRODUCT/"hosts/codex/config.toml").read_text())
        self.assertEqual(config["sandbox_mode"], "read-only")
        self.assertFalse(config["features"]["shell_tool"])
        self.assertEqual(set(config["agents"])-{"max_threads"}, set(ROLES))
        self.assertNotIn("runtime_cio", config["agents"])
        known_tools = {tool["name"] for tool in tool_manifest()} | {preparation_tool_manifest()["name"]}
        for server in config["mcp_servers"].values():
            self.assertFalse(server["enabled"])
            self.assertEqual(server["command"], "{{PYTHON}}")
            self.assertEqual(server["args"][:3], ["-B", "-m", "product.mcp.research"])
            self.assertIn("--connection-env-prefix", server["args"])
            self.assertTrue(any(value.endswith("_CONNECTION") for value in server["env_vars"]))
            self.assertTrue(set(server["enabled_tools"]) <= known_tools)
        for name in ROLES:
            text = (PRODUCT/"hosts/codex"/config["agents"][name]["config_file"]).read_text()
            parsed = tomllib.loads(text)
            self.assertEqual(parsed["name"], name)
            self.assertEqual(parsed["developer_instructions"].strip(), "{{ROLE_BODY}}")
            active = [key for key, value in parsed["mcp_servers"].items() if value["enabled"]]
            self.assertEqual(active, [{"runtime_company_analyst":"company", "runtime_market_catalyst":"market", "runtime_skeptic":"skeptic"}[name]])
            self.assertIn("research_prepare_task", parsed["mcp_servers"][active[0]]["disabled_tools"])
            # Codex deserializes role MCP entries as complete transports, even
            # for disabled services; a partial enabled-only overlay is invalid.
            for server_name, server in parsed["mcp_servers"].items():
                for key in ("command", "args", "cwd", "env_vars", "enabled_tools"):
                    self.assertEqual(server[key], config["mcp_servers"][server_name][key])
            for item in parsed["skills"]["config"]:
                skill = Path(item["path"]).name
                self.assertTrue((PRODUCT/"skills"/skill/"SKILL.md").is_file())

    def test_claude_templates_exact_mcp_tools_and_preload_skills_without_generic_file_tools(self):
        known = {tool["name"] for tool in tool_manifest()}
        for name in ROLES:
            scalars, lists, body = frontmatter(PRODUCT/"hosts/claude-code/agents"/(name+".md"))
            self.assertEqual(scalars["name"], name)
            self.assertEqual(scalars["model"], "inherit")
            self.assertNotIn("mcpServers", scalars)
            self.assertEqual(set(lists), {"tools", "skills"})
            self.assertNotIn("isolation", scalars)
            self.assertNotIn("permissionMode", scalars)
            self.assertEqual(body.strip(), "{{ROLE_BODY}}")
            for tool in lists["tools"]:
                self.assertRegex(tool, r"^mcp__(company|market|skeptic)__research_")
                self.assertIn(tool.split("__")[-1], known)
            self.assertFalse(set(lists["tools"]) & {"Read", "Bash", "Write", "Edit", "Agent", "WebSearch", "WebFetch"})
            self.assertFalse({tool.split("__")[-1] for tool in lists["tools"]}
                             & {"research_connection_context", "research_prepare_task"})
            for skill in lists["skills"]:
                self.assertTrue((PRODUCT/"skills"/skill/"SKILL.md").is_file())
            if name == "runtime_skeptic":
                self.assertEqual(lists["tools"], ["mcp__skeptic__research_context", "mcp__skeptic__research_catalog",
                    "mcp__skeptic__research_query", "mcp__skeptic__research_submit", "mcp__skeptic__research_read_submission"])
        mcp = json.loads((PRODUCT/"hosts/claude-code/mcp.json").read_text())
        self.assertEqual(set(mcp["mcpServers"]), {"company", "market", "skeptic", "cio"})
        for server in mcp["mcpServers"].values():
            self.assertIn("--connection-env-prefix", server["args"])
            self.assertTrue(any(key.endswith("_CONNECTION") for key in server["env"]))

    def test_claude_company_native_skill_binds_original_role_without_dispatch_overrides(self):
        scalars, lists, body = frontmatter(PRODUCT/"hosts/claude-code/skills/company-native/SKILL.md")
        self.assertEqual(set(scalars), {"name", "description", "context", "agent", "background", "user-invocable"})
        self.assertEqual(scalars["name"], "company-native")
        self.assertEqual(scalars["context"], "fork")
        self.assertEqual(scalars["agent"], "runtime_company_analyst")
        self.assertEqual(scalars["background"], "false")
        self.assertEqual(scalars["user-invocable"], "false")
        self.assertEqual(lists, {})
        self.assertEqual(body.count("$ARGUMENTS"), 1)
        self.assertNotIn("{{ROLE_BODY}}", body)
        role, limits, _ = frontmatter(PRODUCT/"hosts/claude-code/agents"/(scalars["agent"]+".md"))
        self.assertEqual(role["model"], "inherit")
        self.assertEqual(limits["skills"], ["evidence-grounding", "company-research", "valuation",
                                           "catalyst-analysis", "research-report-analysis"])
        self.assertTrue(all(tool.startswith("mcp__company__research_") for tool in limits["tools"]))
        self.assertNotIn("company-native", limits["skills"])

    def test_claude_company_reuses_one_parent_connection_without_widening_tools(self):
        fixture = json.loads((ROOT/"tests/fixtures/native-hosts/claude-code-2.1.289-company-tools.json").read_text())
        names = fixture["company_tools"]
        self.assertEqual(hashlib.sha256(json.dumps(names, separators=(",", ":")).encode()).hexdigest(),
                         fixture["names_canonical_sha256"])
        scalars, lists, body = frontmatter(PRODUCT/"hosts/claude-code/agents/runtime_company_analyst.md")
        self.assertEqual(set(lists), {"tools", "skills"})
        self.assertNotIn("mcpServers", scalars)
        self.assertEqual(set(lists["tools"]), set(names)-{"mcp__company__research_prepare_task"})
        self.assertEqual(len(lists["tools"]), 11)
        self.assertEqual(scalars["model"], "inherit")
        self.assertEqual(body.strip(), "{{ROLE_BODY}}")
        mcp = json.loads((PRODUCT/"hosts/claude-code/mcp.json").read_text())
        self.assertIn("company", mcp["mcpServers"])
        self.assertNotIn("mcp__company__*", lists["tools"])
        for other, server in (("runtime_market_catalyst", "market"), ("runtime_skeptic", "skeptic")):
            header, other_lists, _ = frontmatter(PRODUCT/"hosts/claude-code/agents"/(other+".md"))
            self.assertNotIn("mcpServers", header)
            self.assertEqual(set(other_lists), {"tools", "skills"})
            self.assertIn(server, mcp["mcpServers"])
            self.assertTrue(all(tool.startswith(f"mcp__{server}__research_") for tool in other_lists["tools"]))
        # A captured parent inventory cannot prove this version's child tool pool.
        self.assertIn("不证明", fixture["scope"])

    def test_market_skeptic_native_skills_bind_existing_roles_without_extra_permissions(self):
        for name, role, server in (("market", "runtime_market_catalyst", "market"),
                                   ("skeptic", "runtime_skeptic", "skeptic")):
            header, lists, body = frontmatter(PRODUCT/f"hosts/claude-code/skills/{name}-native/SKILL.md")
            self.assertEqual(set(header), {"name", "description", "context", "agent", "background", "user-invocable"})
            self.assertEqual(header["name"], name+"-native")
            self.assertEqual(header["agent"], role)
            self.assertEqual(header["context"], "fork")
            self.assertEqual(header["background"], "false")
            self.assertEqual(header["user-invocable"], "false")
            self.assertEqual(lists, {})
            self.assertEqual(body.count("$ARGUMENTS"), 1)
            scalars, limits, _ = frontmatter(PRODUCT/f"hosts/claude-code/agents/{role}.md")
            self.assertEqual(scalars["model"], "inherit")
            self.assertNotIn("mcpServers", scalars)
            self.assertEqual(set(limits), {"tools", "skills"})
            self.assertTrue(all(tool.startswith(f"mcp__{server}__research_") for tool in limits["tools"]))
            self.assertNotIn(name+"-native", limits["skills"])
            if name == "skeptic":
                self.assertEqual(limits["skills"], ["evidence-grounding", "counter-thesis"])
                self.assertNotIn("mcp__skeptic__research_read_reports", limits["tools"])

    def test_captured_agent_schema_allows_omission_and_has_no_optional_field_defaults(self):
        from jsonschema import Draft202012Validator
        fixture = json.loads((ROOT/"tests/fixtures/native-hosts/claude-code-2.1.289-tools.json").read_text())
        for name, schema in fixture["input_schemas"].items():
            Draft202012Validator.check_schema(schema)
            encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
            self.assertEqual(hashlib.sha256(encoded).hexdigest(), fixture["schema_canonical_sha256"][name])
        schema = fixture["input_schemas"]["Agent"]
        self.assertEqual(schema["required"], ["description", "prompt"])
        self.assertFalse(any("default" in prop for prop in schema["properties"].values()))
        minimal = {"description": "合成Schema检查", "prompt": "不执行研究", "subagent_type": "runtime_company_analyst"}
        original = dict(minimal)
        Draft202012Validator(schema).validate(minimal)
        self.assertEqual(minimal, original)
        # Schema legality is not task authorization or evidence of host execution.
        self.assertTrue(Draft202012Validator(schema).is_valid({**minimal, "isolation": "worktree", "model": "opus"}))

    def test_company_native_example_matches_captured_skill_schema_without_dispatch_fields(self):
        from jsonschema import Draft202012Validator
        fixture = json.loads((ROOT/"tests/fixtures/native-hosts/claude-code-2.1.289-tools.json").read_text())
        schema = fixture["input_schemas"]["Skill"]
        guide = (PRODUCT/"hosts/claude-code/main-thread.md").read_text()
        example = json.loads(re.search(r"```json\n(.*?)\n```", guide, re.DOTALL).group(1))
        self.assertEqual(example["skill"], "company-native")
        self.assertEqual(set(example), {"skill", "args"})
        validator = Draft202012Validator(schema)
        validator.validate(example)
        for key, value in (("isolation", "worktree"), ("model", "opus"),
                           ("subagent_type", "runtime_company_analyst"), ("run_in_background", True)):
            with self.subTest(key=key):
                self.assertFalse(validator.is_valid({**example, key: value}))
        self.assertFalse(validator.is_valid({"args": "synthetic task"}))
        self.assertFalse(validator.is_valid({"skill": "company-native", "args": {"model": "opus"}}))

    def test_opencode_role_modes_permission_order_and_prompt_source(self):
        config = json.loads((PRODUCT/"hosts/opencode/opencode.json").read_text())
        for name, agent in config["agent"].items():
            self.assertEqual(agent["mode"], "primary" if name == "runtime_cio" else "subagent")
            self.assertEqual(next(iter(agent["permission"])), "*")
            self.assertEqual(agent["permission"]["*"], "deny")
            path = agent["prompt"].removeprefix("{file:./").removesuffix("}")
            self.assertTrue((ROOT/path).is_file())
            self.assertNotIn("model", agent)
            if name != "runtime_cio":
                self.assertNotIn("task", agent["permission"])
        for server in config["mcp"].values():
            self.assertFalse(server["enabled"])
            self.assertEqual(server["type"], "local")
            self.assertEqual(server["command"][1:4], ["-B", "-m", "product.mcp.research"])
            self.assertIn("--connection-env-prefix", server["command"])
            self.assertTrue(any(key.endswith("_CONNECTION") for key in server["environment"]))

    def test_role_bound_actual_stdio_cannot_use_another_role_task(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            task_root = Path(temp)/"company"
            prepared = prepare_task(task_root, research_input=alb_request(), gate=frozen_gate(),
                                    security_id=SECURITY, capability="COMPANY_RESEARCH")
            prefix = "STOCK_AGENT_SKEPTIC"
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            env[prefix+"_TASK"], env[prefix+"_TOKEN"] = str(task_root), prepared["access_token"]
            result = subprocess.run([sys.executable,"-B","-m","product.mcp.research","--task-env-prefix",prefix],
                                    input='', text=True, capture_output=True, cwd=ROOT, env=env, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr.strip(), "NATIVE_RESEARCH_CONNECTION_REJECTED")
            self.assertNotIn(prepared["access_token"], result.stderr+result.stdout)
            self.assertFalse((task_root/"tools").exists())
            prefix = "STOCK_AGENT_COMPANY"
            env[prefix+"_TASK"], env[prefix+"_TOKEN"] = str(task_root), prepared["access_token"]
            messages = [dict(jsonrpc="2.0",id=1,method="tools/list"),
                        dict(jsonrpc="2.0",id=2,method="tools/call",params={"name":"research_query","arguments":{"evidence_ids":["ev-other"]}}),
                        dict(jsonrpc="2.0",id=3,method="tools/call",params={"name":"research_query","arguments":{"evidence_ids":["ev-revenue"]}})]
            result = subprocess.run([sys.executable,"-B","-m","product.mcp.research","--task-env-prefix",prefix],
                                    input='\n'.join(json.dumps(m) for m in messages)+'\n', text=True, capture_output=True,
                                    cwd=ROOT,env=env,timeout=10,check=True)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertTrue(replies[1]["result"]["isError"])
            self.assertFalse(replies[2]["result"]["isError"])
