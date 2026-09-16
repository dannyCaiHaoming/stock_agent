"""来源 profile 分流，无模型、网络或 SDK 安装要求。"""
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from product.runtime.runtime_profiles import load_source_profile
from product.runtime.discovery import discover_product_resources
from product.runtime.invocation import create_invocation_manifest, verify_invocation_manifest, build_specialist_output_schema, build_specialist_task_prompt
from product.runtime.hashing import canonical_hash

ROOT = Path(__file__).resolve().parents[1]


class LiveProfileTests(unittest.TestCase):
    def test_live_mcp_stdio_starts_without_provider_requests(self):
        requests = [dict(jsonrpc="2.0", id=1, method="initialize"), dict(jsonrpc="2.0", id=2, method="tools/list")]
        result = subprocess.run([sys.executable, "-B", "-m", "runtime.live_mcp"], cwd=ROOT / "product",
                                input="\n".join(json.dumps(r) for r in requests) + "\n", text=True,
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(output[0]["result"]["serverInfo"]["name"], "live-gate-scoped")
        self.assertEqual(
            {t["name"] for t in output[1]["result"]["tools"]},
            {"query", "calculate", "research_search", "research_fetch"},
        )

    def test_live_execution_proof_does_not_accept_another_query_server(self):
        from product.runtime.execution_proof import _logical_tool_name
        permissions = {"live_evidence.query"}
        self.assertEqual(_logical_tool_name({"name": "mcp__live_runtime__query"}, permissions), "live_evidence.query")
        for name in ("mcp__fixture_runtime__query", "mcp__web__query", "mcp__live_runtime__query_extra"):
            with self.subTest(name=name):
                self.assertIsNone(_logical_tool_name({"name": name}, permissions))

    def test_defaults_remain_fixture_and_live_explicit(self):
        self.assertEqual(load_source_profile(ROOT)["profile_id"], "fixture-council/3.1.0")
        live = load_source_profile(ROOT, "live-us-equity")
        self.assertEqual(live["source_mode"], "live")
        self.assertNotIn("fixture_id", live)
        self.assertNotIn("BUY", live["allowed_actions"])
        for name in ("live", "normal", "unknown", "../live-us-equity"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "UNKNOWN_SOURCE_PROFILE"):
                load_source_profile(ROOT, name)

    def test_profile_cannot_change_topology_tools_or_schema_path(self):
        profile = load_source_profile(ROOT, "live-us-equity")
        variants = []
        for field, value in (("source_mode", "fixture"), ("allowed_actions", ["BUY"]),
                             ("providers", ["other", "sec"]), ("max_positions", 4)):
            variants.append(dict(profile, **{field: value}))
        for field, value in (("tool_permissions", ["http.get"]), ("skills", []),
                             ("config_file", "../../outside.toml")):
            item = json.loads(json.dumps(profile))
            item["agents"]["runtime_skeptic"][field] = value
            variants.append(item)
        variants.append(dict(profile, schema_files={"portfolio": "../../outside.json"}))
        for value in variants:
            with self.subTest(value=value), patch.object(Path, "read_text", return_value=json.dumps(value)):
                with self.assertRaises(ValueError):
                    load_source_profile(ROOT, "live-us-equity")

    def test_live_discovery_lock_does_not_modify_fixture_manifest(self):
        path = ROOT / "product/version-manifest.json"
        before = path.read_bytes()
        fixture = discover_product_resources(ROOT)
        live = discover_product_resources(ROOT, source_profile="live-us-equity")
        self.assertEqual(path.read_bytes(), before)
        self.assertNotEqual(fixture.discovery_hash, live.discovery_hash)
        self.assertEqual(live.version_manifest["runtime_profile"], "live-us-equity/4.0.0")
        self.assertEqual(live.version_manifest["data_snapshot"], "live-snapshot/4.0.0")
        self.assertEqual(live.version_manifest["schemas"]["live-source-access"], "live-source-access/4.0.0")
        self.assertEqual(live.version_manifest["schemas"]["live-fact-v2"], "live-fact/2.0.0")
        self.assertIn("routing_hash", live.version_manifest["data_adapters"])
        self.assertEqual(live.version_manifest["resource_hashes"]["runtime_profile"], live.runtime_profile.sha256)
        with self.assertRaisesRegex(ValueError, "UNKNOWN_SOURCE_PROFILE"):
            discover_product_resources(ROOT, source_profile="anything")

    def test_live_invocation_binds_source_and_rejects_rehashed_permissions(self):
        agent = "runtime_skeptic"
        agent_input = {"agent": agent, "run_id": "synthetic", "source_mode": "live", "allowed_evidence_ids": ["ev-test"],
                      **{key: "a" * 64 for key in ("portfolio_hash", "snapshot_hash", "gate_hash", "valuation_hash", "identity_hash")}}
        with tempfile.TemporaryDirectory() as temp:
            schema_path = Path(temp) / "schemas/counter-thesis-report.schema.json"
            schema_path.parent.mkdir()
            schema_path.write_text(json.dumps(build_specialist_output_schema(ROOT, agent_name=agent, allowed_evidence_ids=["ev-test"])))
            prompt = build_specialist_task_prompt(agent_name=agent, allowed_evidence_ids=["ev-test"], source_mode="live")
            self.assertIn("mcp__live_runtime__query", prompt)
            self.assertNotIn("fixture", prompt)
            model = discover_product_resources(ROOT).version_manifest["model"]
            manifest = create_invocation_manifest(ROOT, run_id="synthetic", agent_name=agent, agent_input=agent_input,
                task_prompt=prompt, model=model, evidence_ids=["ev-test"], output_schema_path=schema_path)
            verify_invocation_manifest(ROOT, manifest, agent_input=agent_input)
            self.assertEqual(manifest["tool_permissions"], ["live_evidence.query"])
            self.assertEqual(manifest["source_context"]["snapshot_hash"], "a" * 64)
            for key in ("portfolio_hash", "snapshot_hash", "gate_hash", "valuation_hash", "identity_hash"):
                changed_input = dict(agent_input, **{key: None})
                changed_manifest = json.loads(json.dumps(manifest))
                changed_manifest["source_context"][key] = None
                changed_manifest["input_hash"] = canonical_hash(changed_input)
                changed_manifest["manifest_hash"] = canonical_hash({k:v for k,v in changed_manifest.items() if k != "manifest_hash"})
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "LIVE_INVOCATION_SOURCE_BINDING_MISMATCH"):
                    verify_invocation_manifest(ROOT, changed_manifest, agent_input=changed_input)
            manifest["tool_permissions"].append("live_math.calculate")
            manifest["manifest_hash"] = canonical_hash({k:v for k,v in manifest.items() if k != "manifest_hash"})
            with self.assertRaisesRegex(ValueError, "LIVE_INVOCATION_SOURCE_BINDING_MISMATCH"):
                verify_invocation_manifest(ROOT, manifest, agent_input=agent_input)
