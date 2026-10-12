from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime import discover_product_resources, load_version_manifest
from product.runtime.discovery import RESOURCE_PATHS
from product.runtime.versioning import CURRENT_SCHEMA_FILES, derive_profile_agent_versions, validate_version_manifest
from product.runtime.hashing import canonical_hash, file_hash
from evals.regression.runner import load_regression_set


ROOT = Path(__file__).resolve().parents[1]


class VersionManifestTests(unittest.TestCase):
    def test_profile_version_derivation_is_explicit_and_idempotent(self):
        manifest = load_version_manifest(ROOT / "product" / "version-manifest.json")
        profile = json.loads((ROOT / "product/runtime-profile.json").read_text(encoding="utf-8"))
        stale = copy.deepcopy(profile)
        stale["agents"]["runtime_cio"]["version"] = "3.1.0"
        stale["multidimensional_holding_research_stage"]["market_agent_version"] = "1.0.1"
        derived = derive_profile_agent_versions(manifest, stale)
        self.assertEqual(derived, profile)
        self.assertEqual(derive_profile_agent_versions(manifest, derived), derived)
        self.assertEqual(stale["agents"]["runtime_cio"]["version"], "3.1.0")

    def test_candidate_manifest_locks_native_runtime_versions(self):
        manifest = load_version_manifest(ROOT / "product" / "version-manifest.json")
        self.assertRegex(manifest["candidate_version"], r"^\d+\.\d+\.\d+-candidate\.\d+(?:[-+].+)?$")
        self.assertEqual("codex-cli/0.153.4", manifest["codex_runtime"])
        self.assertEqual("gpt-6-luna", manifest["model"])
        self.assertIn("fixture-gate-scoped", manifest["mcp_adapters"])
        self.assertIn("runtime-cio", manifest["agents"])
        self.assertEqual(len(manifest["resource_hashes"]), 9)
        self.assertEqual(len(manifest["assurance_hashes"]), 8)

    def test_manifest_fails_closed_for_missing_or_fixture_model(self):
        manifest = load_version_manifest(ROOT / "product" / "version-manifest.json")
        missing = copy.deepcopy(manifest)
        del missing["codex_runtime"]
        with self.assertRaises(ValueError):
            validate_version_manifest(missing)
        fixture_model = copy.deepcopy(manifest)
        fixture_model["model"] = "fixture-model/1"
        with self.assertRaises(ValueError):
            validate_version_manifest(fixture_model)
        missing_assurance = copy.deepcopy(manifest)
        del missing_assurance["assurance_hashes"]["runtime_eval_rubric"]
        with self.assertRaises(ValueError):
            validate_version_manifest(missing_assurance)

    def test_assurance_version_hashes_resolve_to_current_control_plane(self):
        manifest = load_version_manifest(ROOT / "product" / "version-manifest.json")
        expected = {
            "model_routing_policy": canonical_hash(json.loads((ROOT / "product" / "model-routing.json").read_text(encoding="utf-8"))),
            "runtime_eval_rubric": canonical_hash(json.loads((ROOT / "evals" / "grading" / "semantic-rubric-v1.json").read_text(encoding="utf-8"))),
            "runtime_eval_grader_skill": file_hash(ROOT / ".agents" / "skills" / "runtime-eval-grading" / "SKILL.md"),
            "runtime_eval_grader_agent": file_hash(ROOT / ".codex" / "agents" / "dev_eval.toml"),
            "runtime_eval_calibration": canonical_hash(json.loads((ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json").read_text(encoding="utf-8"))),
            "regression_set": load_regression_set(ROOT)["set_hash"],
            "ablation_profiles": canonical_hash(json.loads((ROOT / "evals" / "ablation" / "profiles-v1.json").read_text(encoding="utf-8"))),
            "promotion_policy": canonical_hash(json.loads((ROOT / "evals" / "promotion" / "policy-v1.json").read_text(encoding="utf-8"))),
        }
        self.assertEqual(manifest["assurance_hashes"], expected)


class ProductDiscoveryTests(unittest.TestCase):
    def copy_locked_resources(self, root):
        manifest = load_version_manifest(ROOT / "product/version-manifest.json")
        names = {*RESOURCE_PATHS.values(), *CURRENT_SCHEMA_FILES.values(), "version-manifest.json",
                 *(f"skills/{name}/SKILL.md" for name in manifest["skills"])}
        for relative in names:
            target = root / "product" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / "product" / relative).read_bytes())

    def test_local_mcp_is_not_a_locked_resource_or_a_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.copy_locked_resources(root)
            expected = discover_product_resources(root)
            self.assertEqual(expected.plugin_mcp.relative_path, "hosts/codex/fixture-mcp.json")
            self.assertEqual(expected.plugin_mcp.sha256, expected.version_manifest["resource_hashes"]["plugin_mcp"])
            local = root / "product/.mcp.json"
            for raw in (b'{"mcpServers":{}}', b"NOT_A_RESOURCE_OR_VALID_JSON"):
                local.write_bytes(raw)
                self.assertEqual(discover_product_resources(root), expected)
                self.assertEqual(local.read_bytes(), raw)
            template = root / "product/hosts/codex/fixture-mcp.json"
            original = template.read_bytes()
            template.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "product resource hash mismatch: plugin_mcp"):
                discover_product_resources(root)
            self.assertEqual(template.read_bytes(), original + b"\n")
            template.unlink()
            local.write_bytes(original)
            with self.assertRaisesRegex(FileNotFoundError, "hosts/codex/fixture-mcp.json"):
                discover_product_resources(root)
            self.assertEqual(local.read_bytes(), original)

    def test_locked_mcp_template_cannot_escape_product_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self.copy_locked_resources(root)
            template = root / "product/hosts/codex/fixture-mcp.json"
            outside = root / "outside.json"
            outside.write_bytes(template.read_bytes())
            template.unlink()
            template.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "resource escapes product root"):
                discover_product_resources(root)
            self.assertTrue(template.is_symlink())

    def test_discovery_resolves_only_repository_product_resources(self):
        result = discover_product_resources(ROOT)
        product_root = (ROOT / "product").resolve()
        self.assertEqual(str(product_root), result.product_root)
        for record in (
            result.plugin,
            result.plugin_mcp,
            result.runtime_config,
            result.runtime_profile,
            result.decision_contract,
            result.council_skill,
            result.cio_agent,
            result.company_agent,
            result.skeptic_agent,
        ):
            self.assertTrue(Path(record.resolved_path).is_relative_to(product_root))
            self.assertEqual(64, len(record.sha256))
        self.assertEqual(64, len(result.discovery_hash))

    def test_discovery_does_not_fall_back_to_global_same_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            global_like = root / ".agents" / "skills" / "portfolio-council"
            global_like.mkdir(parents=True)
            (global_like / "SKILL.md").write_text("global fallback", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                discover_product_resources(root)

    def test_discovery_fails_before_model_when_a_locked_resource_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "repo"
            copied.mkdir()
            product = copied / "product"
            product.mkdir()
            for relative in (
                ".codex-plugin/plugin.json",
                "hosts/codex/fixture-mcp.json",
                ".codex/config.toml",
                "runtime-profile.json",
                "contracts/council-decision-contract.json",
                "schemas/runtime/cio-decision-draft.schema.json",
                "skills/portfolio-council/SKILL.md",
                ".codex/agents/runtime_cio.toml",
                ".codex/agents/runtime_company_analyst.toml",
                ".codex/agents/runtime_skeptic.toml",
                "version-manifest.json",
            ):
                source = ROOT / "product" / relative
                target = product / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            target = product / "skills/portfolio-council/SKILL.md"
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "resource hash mismatch"):
                discover_product_resources(copied)

    def test_discovery_rejects_stale_market_mirror_even_if_profile_hash_is_updated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            copied = Path(temp_dir) / "repo"
            product = copied / "product"
            product.mkdir(parents=True)
            for relative in (
                ".codex-plugin/plugin.json", "hosts/codex/fixture-mcp.json", ".codex/config.toml",
                "runtime-profile.json", "contracts/council-decision-contract.json",
                "schemas/runtime/cio-decision-draft.schema.json",
                "skills/portfolio-council/SKILL.md", ".codex/agents/runtime_cio.toml",
                ".codex/agents/runtime_company_analyst.toml",
                ".codex/agents/runtime_skeptic.toml", "version-manifest.json",
            ):
                target = product / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / "product" / relative).read_bytes())
            profile_path = product / "runtime-profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["multidimensional_holding_research_stage"]["market_agent_version"] = "1.0.1"
            profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            manifest_path = product / "version-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["resource_hashes"]["runtime_profile"] = file_hash(profile_path)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PROFILE_AGENT_VERSION_DRIFT:runtime_market_catalyst"):
                discover_product_resources(copied)


if __name__ == "__main__":
    unittest.main()
