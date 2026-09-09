from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime import discover_product_resources, load_version_manifest
from product.runtime.versioning import validate_version_manifest
from product.runtime.hashing import canonical_hash, file_hash
from evals.regression.runner import load_regression_set


ROOT = Path(__file__).resolve().parents[1]


class VersionManifestTests(unittest.TestCase):
    def test_candidate_manifest_locks_native_runtime_versions(self):
        manifest = load_version_manifest(ROOT / "product" / "version-manifest.json")
        self.assertEqual("0.3.0-candidate.1", manifest["candidate_version"])
        self.assertEqual("codex-cli/0.153.4", manifest["codex_runtime"])
        self.assertEqual("gpt-5.6-terra", manifest["model"])
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
                ".mcp.json",
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


if __name__ == "__main__":
    unittest.main()
