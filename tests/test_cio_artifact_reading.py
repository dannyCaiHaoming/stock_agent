"""冻结 CIO 输入的只读与执行分离；实际 Hook/归集，零模型。"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.intake import build_handoff, build_manual_draft
from product.runtime import independent_skeptic_stage as skeptic
from product.runtime import predecision_cio_stage as cio
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.multidimensional_references import translate_references
from tests import test_skeptic_semantic_handoff as semantic
from tests import test_independent_skeptic_stage as forward_fixtures
from tests import test_cio_reference_handoff as cio_tools


ROOT = Path(__file__).resolve().parents[1]


def mrvl_handoff(count=1):
    payload = json.loads((ROOT / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json").read_text())
    payload["draft_id"] = "synthetic-mrvl-artifact-reader"
    payload["positions"] = [{"ticker": "MRVL", "quantity": 2, "cost_basis": 100}]
    return build_handoff(build_manual_draft(payload), confirmed=True,
                         confirmed_at="2026-09-11T20:05:00+08:00")


def snapshot(root):
    return {str(path.relative_to(root)): file_hash(path)
            for path in root.rglob("*") if path.is_file()}


class CioArtifactReadingTests(unittest.TestCase):
    def prepare(self, root):
        # 正向报告使用既有合成 fixture；反证报告由真正的当前语义 Hook
        # 和 stdio MCP 产生。所有事件仍是确定性测试，不冒称模型执行。
        helper = semantic.SkepticSemanticHandoffTests()
        with patch.object(forward_fixtures, "stock_handoff", side_effect=mrvl_handoff):
            source, task, env, start, _ = helper.prepare(str(root))
        response = helper.query(source, task, task["allowed_evidence_ids"])
        self.assertNotIn("error", response, response)
        saved, _ = helper.stop(env, start, helper.draft(task, run=source))
        self.assertEqual(saved["output_capture"]["status"], "SAVED", saved)
        self.assertEqual(skeptic.finalize_skeptic_phase(ROOT, source)["status"], "PASSED")
        target = root / "cio"
        cio.prepare_predecision_cio_run(ROOT, source_run_dir=source, run_dir=target,
                                       run_id="cio-artifact-test", target_security_id=cio.RESEARCH_TARGET,
                                       model="gpt-5.6-terra")
        return source, target

    def test_actual_package_to_frozen_inputs_survives_move_without_rewriting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = self.prepare(root)
            manifest, request = cio.validate_predecision_cio_run(ROOT, target)
            for item in manifest["frozen_inputs"]:
                self.assertEqual((source / item["artifact_ref"]).read_bytes(),
                                 (target / "source-inputs" / item["artifact_ref"]).read_bytes())
            invocation = json.loads((target / "invocations/runtime_cio.json").read_text())
            mapping = cio.predecision_cio_reference_map(ROOT, target)
            delivered = cio_tools.CioReferenceHandoffTests().call(
                target, invocation, "read_reports", report_ids=list(mapping["reports"]))
            self.assertNotIn("error", delivered, delivered)
            restored = translate_references({"reports": delivered["result"]["structuredContent"]["reports"]}, mapping)
            self.assertEqual([item["report_id"] for item in restored["reports"]], list(mapping["reports"].values()))
            self.assertEqual({item["report_id"]: item["report"] for item in restored["reports"]}, {
                item["report_id"]: json.loads((source / item["artifact_ref"]).read_text())
                for item in manifest["report_catalog"]})
            before = snapshot(target)
            moved = root / "copied-history"
            shutil.copytree(target, moved)
            shutil.rmtree(source)
            shutil.rmtree(target)
            # 没有原目录，也没有可读取的当前仓库；只读使用包内原 Schema。
            loaded = cio.validate_predecision_cio_run(root / "unavailable-repository", moved,
                                                     for_execution=False)
            self.assertEqual(loaded, (manifest, request))
            self.assertEqual(snapshot(moved), before)
            self.assertEqual(loaded[0]["risk_status"], "NOT_RUN")
            self.assertFalse((moved / "decision.json").exists())
            with self.assertRaisesRegex(cio.PredecisionCioStageError, "CIO_RUN_BINDING_INVALID"):
                cio.validate_predecision_cio_run(ROOT, moved)

    def test_current_resources_can_upgrade_but_execution_still_rejects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, target = self.prepare(root)
            before = snapshot(target)
            # 实际当前文件仍按原检查读取；模拟发现结果升级，不改源树。
            from product.runtime.discovery import discover_product_resources
            current = discover_product_resources(ROOT)
            changed = type("ChangedDiscovery", (), {"discovery_hash": "0" * 64})()
            self.assertNotEqual(current.discovery_hash, changed.discovery_hash)
            with patch("product.runtime.discovery.discover_product_resources", return_value=changed) as discovery:
                cio.validate_predecision_cio_run(ROOT, target, for_execution=False)
                discovery.assert_not_called()
                with self.assertRaisesRegex(cio.PredecisionCioStageError, "CIO_PRODUCT_DISCOVERY_DRIFT"):
                    cio.validate_predecision_cio_run(ROOT, target)
            upgraded_repo = root / "upgraded-repository"
            for relative in json.loads((target / "run_manifest.json").read_text())["resource_locks"]:
                path = upgraded_repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, path)
            agent = upgraded_repo / "product/.codex/agents/runtime_cio.toml"
            agent.write_text(agent.read_text() + "\n# 新的当前组件字节，不是历史版本。\n")
            cio.validate_predecision_cio_run(upgraded_repo, target, for_execution=False)
            with patch("product.runtime.discovery.discover_product_resources", return_value=current):
                with self.assertRaisesRegex(cio.PredecisionCioStageError, "CIO_RUNTIME_RESOURCE_DRIFT"):
                    cio.validate_predecision_cio_run(upgraded_repo, target)
            self.assertEqual(snapshot(target), before)

    def test_missing_contract_unknown_version_and_path_escape_fail_readonly(self):
        for defect in ("schema-missing", "schema-tampered", "unknown-version", "missing-input", "escape", "symlink"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, target = self.prepare(root)
                if defect.startswith("schema-"):
                    path = target / cio.FROZEN_REQUEST_SCHEMA_REF
                    if defect == "schema-missing":
                        path.unlink()
                    else:
                        path.write_text("{}")
                elif defect == "unknown-version":
                    manifest = json.loads((target / "run_manifest.json").read_text())
                    manifest["schema_version"] = "predecision-cio-manifest/99.0.0"
                    manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
                    (target / "run_manifest.json").write_text(json.dumps(manifest))
                else:
                    manifest = json.loads((target / "run_manifest.json").read_text())
                    item = manifest["frozen_inputs"][0]
                    path = target / "source-inputs" / item["artifact_ref"]
                    if defect == "missing-input":
                        path.unlink()
                    elif defect == "symlink":
                        outside = root / "outside.json"
                        shutil.copy2(path, outside)
                        path.unlink()
                        path.symlink_to(outside)
                    else:
                        item["artifact_ref"] = "../outside.json"
                        (target / "outside.json").write_text("{}")
                        manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
                        (target / "run_manifest.json").write_text(json.dumps(manifest))
                before = snapshot(target)
                with self.assertRaises(cio.PredecisionCioStageError):
                    cio.validate_predecision_cio_run(ROOT, target, for_execution=False)
                self.assertEqual(snapshot(target), before)

    def test_legacy_without_frozen_schema_uses_only_exact_registered_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, target = self.prepare(root)
            manifest = json.loads((target / "run_manifest.json").read_text())
            del manifest["frozen_request_schema"]
            manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
            (target / "run_manifest.json").write_text(json.dumps(manifest))
            (target / cio.FROZEN_REQUEST_SCHEMA_REF).unlink()
            before = snapshot(target)
            cio.validate_predecision_cio_run(ROOT, target, for_execution=False)
            other_repo = root / "different-schema-repository"
            path = other_repo / cio.REQUEST_SCHEMA_REF
            path.parent.mkdir(parents=True)
            schema = json.loads((ROOT / cio.REQUEST_SCHEMA_REF).read_text())
            schema["description"] = "同名 Schema 但不是历史字节，不可替代。"
            path.write_text(json.dumps(schema))
            with self.assertRaisesRegex(cio.PredecisionCioStageError, "UNSUPPORTED_VERSION"):
                cio.validate_predecision_cio_run(other_repo, target, for_execution=False)
            self.assertEqual(snapshot(target), before)

    def test_source_contract_or_task_dependency_missing_is_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, target = self.prepare(root)
            for defect in ("missing-contract", "tampered-contract", "legacy-contract-unavailable", "missing-task-input"):
                with self.subTest(defect=defect), tempfile.TemporaryDirectory() as copied:
                    moved = Path(copied) / "history"
                    shutil.copytree(target, moved)
                    contract = moved / cio.FROZEN_SOURCE_PACKAGE_SCHEMA_REF
                    if defect == "missing-contract":
                        contract.unlink()
                    elif defect == "tampered-contract":
                        contract.write_text("{}")
                    elif defect == "legacy-contract-unavailable":
                        manifest = json.loads((moved / "run_manifest.json").read_text())
                        del manifest["frozen_source_package_schema"]
                        manifest["manifest_hash"] = canonical_hash({k: v for k, v in manifest.items() if k != "manifest_hash"})
                        (moved / "run_manifest.json").write_text(json.dumps(manifest))
                    else:
                        manifest = json.loads((moved / "run_manifest.json").read_text())
                        item = next(item for item in manifest["frozen_inputs"]
                                    if item["artifact_ref"].startswith("research/skeptic/inputs/"))
                        (moved / "source-inputs" / item["artifact_ref"]).unlink()
                    before = snapshot(moved)
                    with self.assertRaises(cio.PredecisionCioStageError):
                        cio.validate_predecision_cio_run(root / "unavailable-repository", moved, for_execution=False)
                    self.assertEqual(snapshot(moved), before)


if __name__ == "__main__":
    unittest.main()
