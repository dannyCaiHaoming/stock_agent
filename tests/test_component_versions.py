"""组件版本的实际资源/批准来源接缝；零模型、零网络。"""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.discovery import discover_product_resources
from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError
from product.runtime.hashing import file_hash
from product.runtime.versioning import (
    approved_component_version, derive_profile_agent_versions, derive_skill_version, load_version_manifest,
    read_skill_version, validate_current_component_versions, validate_profile_agent_versions,
)
from product.runtime.run_package import RunPackageError, prepare_live_run
from product.runtime.run_package import prepare_run
from tests.test_native_run_package import FIXTURES


ROOT = Path(__file__).resolve().parents[1]


class ComponentVersionTests(unittest.TestCase):
    def test_current_actual_components_and_stage_adapter_scopes_match(self):
        product = ROOT / "product"
        manifest = load_version_manifest(product / "version-manifest.json")
        validate_current_component_versions(product, manifest)
        self.assertEqual(manifest["mcp_adapters"]["fixture-gate-scoped"], "2.5.0")
        self.assertEqual(manifest["mcp_adapters"]["common-stock-field-query"], "2.4.0")
        self.assertEqual(manifest["mcp_adapters"]["independent-skeptic-query"], "2.3.0")
        with self.assertRaisesRegex(ValueError, "COMPONENT_VERSION_UNAPPROVED"):
            approved_component_version(manifest, "mcp_adapters", "invented")
        with self.assertRaisesRegex(ValueError, "COMPONENT_ADAPTER_SCOPE_UNKNOWN"):
            validate_current_component_versions(product, manifest, adapter_scopes=("invented",))
        with self.assertRaisesRegex(ValueError, "COMPONENT_SCHEMA_UNMAPPED"):
            validate_current_component_versions(product, manifest, schema_names=("invented",))

    def test_approved_manifest_is_not_silently_inferred_from_actual_resources(self):
        product = ROOT / "product"
        baseline = load_version_manifest(product / "version-manifest.json")
        for category, key in (("skills", "valuation"), ("schemas", "equity-research-report"),
                              ("mcp_adapters", "independent-skeptic-query")):
            manifest = deepcopy(baseline)
            manifest[category][key] = "99.0.0"
            with self.subTest(category=category), self.assertRaisesRegex(ValueError, "COMPONENT_VERSION_DRIFT"):
                validate_current_component_versions(product, manifest)
            self.assertEqual(manifest[category][key], "99.0.0")
        manifest = deepcopy(baseline)
        manifest["risk_policy"] = "risk/reference/99.0.0"
        with self.assertRaisesRegex(ValueError, "COMPONENT_VERSION_DRIFT:risk_policy"):
            validate_current_component_versions(product, manifest)

    def test_actual_schema_mirror_drift_blocks_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            shutil.copytree(ROOT / "product", repo / "product", ignore=shutil.ignore_patterns("__pycache__", ".private"))
            schema_path = repo / "product/schemas/runtime/equity-research-report.schema.json"
            schema = json.loads(schema_path.read_text())
            schema["properties"]["schema_version"]["const"] = "equity-research-report/99.0.0"
            schema_path.write_text(json.dumps(schema))
            before = schema_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "COMPONENT_VERSION_DRIFT:schemas:equity-research-report"):
                discover_product_resources(repo)
            self.assertEqual(schema_path.read_bytes(), before)

    def test_generation_is_explicit_idempotent_and_leaves_frozen_profile_unchanged(self):
        product = ROOT / "product"
        manifest_path = product / "version-manifest.json"
        frozen = product / "profiles/live-us-equity.json"
        before = manifest_path.read_bytes(), frozen.read_bytes()
        manifest = load_version_manifest(manifest_path)
        profile = json.loads((product / "runtime-profile.json").read_text())
        stale = deepcopy(profile)
        stale["agents"]["runtime_cio"]["version"] = "3.1.0"
        with self.assertRaisesRegex(ValueError, "PROFILE_AGENT_VERSION_DRIFT:runtime_cio"):
            validate_profile_agent_versions(manifest, stale)
        rendered = derive_profile_agent_versions(manifest, stale)
        self.assertEqual(rendered, profile)
        self.assertEqual(derive_profile_agent_versions(manifest, rendered), rendered)
        command = [sys.executable, str(ROOT / "scripts/check-product-version-mirrors.py"),
                   "--repo", str(ROOT), "--render"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), rendered)
        self.assertEqual(before, (manifest_path.read_bytes(), frozen.read_bytes()))
        self.assertEqual(file_hash(frozen), "d38d6124d4e2b14d2889e36af7ca700f9ac62ed96b21c5472adb5ac2bbd496bb")

    def test_skill_version_only_reads_one_metadata_entry_not_body_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text('---\nname: sample\nmetadata:\n  version: "1.2.3"\n---\nmetadata:\n  version: 99.0.0\n')
            self.assertEqual(read_skill_version(path), "1.2.3")
            path.write_text('---\nname: sample\nmetadata:\n  version: 1.2.3\n  version: 2.0.0\n---\nbody\n')
            with self.assertRaisesRegex(ValueError, "SKILL_VERSION_INVALID"):
                read_skill_version(path)

    def test_skill_render_does_not_change_methods_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            text = '---\nname: sample\nmetadata:\n  version: "0.0.0"\n  owner: preserved\n---\n中文方法\nmetadata:\n  version: 99.0.0\n'
            path.write_text(text)
            manifest = {"skills": {"sample": "1.2.3"}}
            rendered = derive_skill_version(manifest, "sample", path)
            self.assertEqual(rendered, text.replace('version: "0.0.0"', 'version: "1.2.3"', 1))
            self.assertEqual(path.read_text(), text)
            path.write_text(rendered)
            self.assertEqual(derive_skill_version(manifest, "sample", path), rendered)

    def test_actual_query_rejects_wrong_stage_adapter_before_event(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run"
            prepare_run(ROOT, fixture_path=FIXTURES / "normal-research.json", run_dir=run,
                        run_id="component-version-test", model="gpt-5.6-terra",
                        research_question="确定性接缝。", authenticity_required=False)
            tools = StatelessFixtureTools(default_run_dir=run)
            invocation = json.loads((run / "invocations/runtime_company_analyst.json").read_text())
            with patch("product.runtime.fixture_mcp.MCP_ADAPTER_VERSION", "fixture-gate-scoped/99.0.0"):
                with self.assertRaisesRegex(ToolAccessError, "COMPONENT_VERSION_DRIFT:mcp_adapters:fixture-gate-scoped"):
                    tools.query(run_id=invocation["run_id"], agent="runtime_company_analyst",
                                invocation_id=invocation["invocation_id"], evidence_ids=["ev-normal-revenue"])
            self.assertEqual(tools.events, [])

    def test_retired_live_preparation_rejects_real_execution_before_any_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RunPackageError, "LIVE_COUNCIL_ENTRY_RETIRED"):
                prepare_live_run(ROOT, portfolio_path=root / "missing-portfolio", snapshot_path=root / "missing-snapshot",
                                 cache_root=root / "missing-cache", calendar=None, run_dir=root / "run",
                                 run_id="retired-live-test", model="gpt-5.6-terra")
            self.assertFalse((root / "run").exists())


if __name__ == "__main__":
    unittest.main()
