"""真实 CIO 补验输入的最小准备接缝；不启动模型。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.common_stock_stage import (
    prepare_common_stock_stage_run, validate_common_stock_stage_run_package,
    common_stock_model_packet, build_common_stock_dispatch_packet,
)
from product.runtime.multidimensional_stage import (
    prepare_multidimensional_stage_run, MultidimensionalStageError,
)
from product.runtime.independent_skeptic_stage import CORE_CAPABILITIES
from product.runtime.hashing import legacy_envelope_hash
from tests.test_common_stock_research_contracts import stock_handoff, gate_for

ROOT = Path(__file__).resolve().parents[1]


class PredecisionSourcePreparationTests(unittest.TestCase):
    def inputs(self, root):
        handoff = stock_handoff(1)
        gate = gate_for(handoff, "historical-source")
        hp, gp = root / "handoff.json", root / "gate.json"
        hp.write_text(json.dumps(handoff))
        gp.write_text(json.dumps(gate))
        return hp, gp

    def test_skeptic_attempt_reader_validates_explicit_path_hash_and_run_scope(self):
        from product.runtime.independent_skeptic_stage import (
            DISPATCH_VERSION, read_dispatch_index, resolve_skeptic_tool_scope,
        )
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            relative = "research/skeptic/attempts/2/dispatch-index.json"
            index = {"schema_version": DISPATCH_VERSION, "run_id": "run", "attempt": 2, "tasks": []}
            index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
            path = run / relative
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(index))
            original = path.read_bytes()
            self.assertEqual(read_dispatch_index(run, relative), index)
            with self.assertRaisesRegex(ValueError, "COUNTER_DISPATCH_INDEX_PATH_INVALID"):
                read_dispatch_index(run, "../outside.json")
            with self.assertRaisesRegex(ValueError, "COUNTER_DISPATCH_INDEX_INVALID"):
                resolve_skeptic_tool_scope(run, run_id="foreign", invocation_id="any", gate={}, index_ref=relative)
            self.assertEqual(path.read_bytes(), original)
            index["run_id"] = "tampered"
            path.write_text(json.dumps(index))
            with self.assertRaisesRegex(ValueError, "COUNTER_DISPATCH_INDEX_INVALID"):
                read_dispatch_index(run, relative)

    def test_skeptic_task_keeps_target_scope_and_source_report_distinction(self):
        from product.runtime.independent_skeptic_stage import _skeptic_task_prompt
        prompt = _skeptic_task_prompt("US:COMMON_STOCK:MRVL")
        self.assertIn("US:COMMON_STOCK:MRVL", prompt)
        self.assertIn("scope", prompt)
        self.assertIn("confidence_rationale", prompt)
        self.assertIn(json.dumps({"assumption_id": "A1", "statement": "待检验的条件性假设"},
                                 ensure_ascii=False, separators=(",", ":")), prompt)
        self.assertIn("challenges.assumption_ids", prompt)
        self.assertIn('顶层 allowed_evidence_ids', prompt)
        self.assertNotIn('清单在 agent_input.allowed_evidence_ids', prompt)
        self.assertIn("Morningstar", prompt)
        self.assertIn("Company Analyst", prompt)
        # 核对协议边界，不以整段中文文案逐字充当研究质量测试。

    def test_frozen_company_uses_new_identity_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            hp, gp = self.inputs(root)
            before = gp.read_bytes()
            run = root / "company"
            with patch("product.runtime.research_memory.resolve_memory_root", return_value=None):
                prepare_common_stock_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                    run_dir=run, run_id="new-execution", model="gpt-6-luna",
                    reuse_frozen_gate=True, force_rerun=True)
            self.assertEqual(before, gp.read_bytes())
            validate_common_stock_stage_run_package(ROOT, run)
            manifest = json.loads((run / "run_manifest.json").read_text())
            self.assertEqual("historical-source", manifest["gate_input_binding"]["source_run_id"])
            self.assertEqual("new-execution", manifest["run_id"])
            frozen = run / "audit/frozen-gate-source.json"
            source = json.loads(frozen.read_text())
            source["allowed_evidence"][0]["value"] = 999
            source["bundle_hash"] = legacy_envelope_hash(source, hash_field="bundle_hash")
            frozen.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "FROZEN_GATE_BINDING_INVALID"):
                validate_common_stock_stage_run_package(ROOT, run)

    def test_explicit_counter_core_matches_existing_admission_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            hp, gp = self.inputs(root)
            run = root / "core"
            result = prepare_multidimensional_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                run_dir=run, run_id="historical-source", model="gpt-6-luna",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH", core_forward_only=True)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertEqual(CORE_CAPABILITIES - {"COMPANY_RESEARCH"},
                {item["capability"] for item in index["tasks"]})
            self.assertEqual(5, result["task_count"])
            manifest = json.loads((run / "run_manifest.json").read_text())
            self.assertEqual("SKEPTIC_REQUIRED_CORE_ONLY", manifest["forward_scope"])
            self.assertFalse((run / "invocation").exists())

    def test_preparation_keeps_original_identity_and_hash_under_verified_gate_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            hp, gp = self.inputs(root)
            handoff, gate = json.loads(hp.read_text()), json.loads(gp.read_text())
            prep = {"run_id": gate["run_id"], "handoff_id": handoff["handoff_id"],
                "handoff_hash": handoff["handoff_hash"], "portfolio_hash": handoff["portfolio_hash"],
                "common_cutoff": gate["decision_cutoff"], "items": [{
                    "security_id": handoff["portfolio"]["positions"][0]["security_id"],
                    "status": "READY", "evidence_ids": gate["allowed_evidence_ids"]}]}
            prep["preparation_hash"] = legacy_envelope_hash(prep, hash_field="preparation_hash")
            pp = root / "preparation.json"
            pp.write_text(json.dumps(prep))
            before = pp.read_bytes()
            run = root / "company"
            prepare_common_stock_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                run_dir=run, run_id="new-execution", model="gpt-6-luna",
                reuse_frozen_gate=True, data_preparation_path=pp, force_rerun=True)
            validate_common_stock_stage_run_package(ROOT, run)
            self.assertEqual(before, pp.read_bytes())
            self.assertEqual(prep, json.loads((run / "evidence/data-preparation.json").read_text()))
            with self.assertRaisesRegex(ValueError, "GATE_RUN_MISMATCH"):
                prepare_common_stock_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                    run_dir=root / "invalid", run_id="new-execution", model="gpt-6-luna",
                    data_preparation_path=pp)

    def test_core_scope_cannot_change_default_multidimensional_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            hp, gp = self.inputs(root)
            run = root / "invalid"
            with self.assertRaisesRegex(MultidimensionalStageError, "COUNTER_CORE_SCOPE_STAGE_INVALID"):
                prepare_multidimensional_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                    run_dir=run, run_id="historical-source", model="gpt-6-luna",
                    core_forward_only=True)
            self.assertFalse(run.exists())

    def test_core_capture_paths_follow_verified_source_package_not_execution_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            hp, gp = self.inputs(root)
            company = root / "company"
            prepare_common_stock_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                run_dir=company, run_id="new-execution", model="gpt-6-luna",
                reuse_frozen_gate=True, force_rerun=True)
            package = company / "evidence/source-package"
            package.mkdir()
            (package / "gate.json").write_bytes(gp.read_bytes())
            (package / "data-preparation.json").write_text("{}")
            (package / "source-bundle.json").write_text("{}")
            (company / "evidence/data-preparation.json").write_text("{}")
            manifest_path = company / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["source_bundle_ref"] = "evidence/source-package/source-bundle.json"
            manifest_path.write_text(json.dumps(manifest))
            with patch("product.runtime.common_stock_data.validate_common_stock_source_bundle") as source_check, \
                    patch("product.runtime.multidimensional_stage._load_research_capture_batches", return_value=[]) as captures, \
                    patch("product.runtime.multidimensional_stage._import_company_research_reports", return_value={"import_hash": "test"}):
                prepare_multidimensional_stage_run(ROOT, handoff_path=hp,
                    gate_path=company / "evidence/gate.json", run_dir=root / "core",
                    company_research_run_path=company, run_id="new-execution",
                    model="gpt-6-luna", stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
                    core_forward_only=True)
                source_check.assert_called_once()
                self.assertEqual(package / "gate.json", captures.call_args.kwargs["gate_path"])
                self.assertEqual("historical-source", captures.call_args.kwargs["gate"]["run_id"])
                self.assertFalse(captures.call_args.kwargs["allow_source_run_rebinding"])
            source = json.loads((package / "gate.json").read_text())
            source["allowed_evidence"][0]["value"] = 999
            source["bundle_hash"] = legacy_envelope_hash(source, hash_field="bundle_hash")
            (package / "gate.json").write_text(json.dumps(source))
            with self.assertRaisesRegex(MultidimensionalStageError, "COUNTER_COMPANY_SOURCE_GATE_MISMATCH"):
                prepare_multidimensional_stage_run(ROOT, handoff_path=hp,
                    gate_path=company / "evidence/gate.json", run_dir=root / "invalid",
                    company_research_run_path=company, run_id="new-execution",
                    model="gpt-6-luna", stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
                    core_forward_only=True)
            self.assertFalse((root / "invalid").exists())
            (package / "gate.json").write_bytes(gp.read_bytes())
            for name in ("gate.json", "data-preparation.json"):
                path = package / name
                original = path.read_bytes()
                outside = root / ("outside-" + name)
                outside.write_bytes(original)
                path.unlink()
                path.symlink_to(outside)
                with self.assertRaisesRegex(MultidimensionalStageError, "MULTIDIMENSIONAL_ARTIFACT_PATH_INVALID"):
                    prepare_multidimensional_stage_run(ROOT, handoff_path=hp,
                        gate_path=company / "evidence/gate.json", run_dir=root / ("invalid-" + name),
                        company_research_run_path=company, run_id="new-execution",
                        model="gpt-6-luna", stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
                        core_forward_only=True)
                path.unlink()
                path.write_bytes(original)

    def test_old_host_core_materials_arguments_reject_before_any_launch(self):
        import subprocess
        for extra in (["--peer-candidates", "missing-pool.json"], ["--require-materials"]):
            result = subprocess.run(["bash", str(ROOT / "scripts/run-product-smoke.sh"),
                "--stage", "independent-counter-thesis-research", "--core-forward-only",
                "--handoff", "missing-handoff.json", *extra, "/not-created"],
                capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertIn('NATIVE_HOST_EXECUTION_REQUIRED', result.stderr)

    def test_column_catalog_retains_all_ids_periods_and_original_values(self):
        from product.runtime.multidimensional_references import translate_references
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            hp, gp = self.inputs(root)
            run = root / "company"
            prepare_common_stock_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                run_dir=run, run_id="historical-source", model="gpt-6-luna")
            index = json.loads((run / "research/dispatch-index.json").read_text())
            packet = build_common_stock_dispatch_packet(ROOT, run, index["tasks"][0]["task_name"])
            original = translate_references(packet["evidence_catalog"], packet["reference_map"], to_model=True)
            view = common_stock_model_packet(packet)["evidence_catalog"]
            restored = [{"semantic_field": group["semantic_field"], "items": [
                {key: value for key, value in zip(group["columns"], row) if value is not None}
                for row in group["items"]]} if "columns" in group else group for group in view]
            self.assertEqual(original, restored)
            self.assertLessEqual(len(json.dumps(view)), len(json.dumps(original)))

    def test_explicit_frozen_skeptic_model_does_not_change_fixture_candidate_lock(self):
        from product.runtime.independent_skeptic_stage import build_first_pass_input
        from product.runtime.invocation import create_invocation_manifest, verify_invocation_manifest, build_specialist_output_schema
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            hp, gp = self.inputs(root)
            run = root / "core"
            prepare_multidimensional_stage_run(ROOT, handoff_path=hp, gate_path=gp,
                run_dir=run, run_id="historical-source", model="gpt-6-luna",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH", core_forward_only=True)
            gate = json.loads(gp.read_text())
            request = json.loads((run / "council-request.json").read_text())
            allowed = sorted(gate["allowed_evidence_ids"])
            agent_input = build_first_pass_input(run_id="historical-source",
                security_id="US:COMMON_STOCK:AAPL", request=request, gate=gate,
                allowed_ids=allowed, scope_limitations=[])
            schema = root / "schemas/counter-thesis.json"
            schema.parent.mkdir()
            schema.write_text(json.dumps(build_specialist_output_schema(ROOT,
                agent_name="runtime_skeptic", allowed_evidence_ids=allowed,
                report_schema_version="counter-thesis-report/2.1.0")))
            # 使用产品既有规范文件名，不改变候选 manifest。
            from product.runtime.invocation import OUTPUT_SCHEMAS
            target = schema.with_name(Path(OUTPUT_SCHEMAS["runtime_skeptic"]).name)
            schema.rename(target)
            candidate_before = (ROOT / "product/version-manifest.json").read_bytes()
            invocation = create_invocation_manifest(ROOT, run_id="historical-source",
                agent_name="runtime_skeptic", agent_input=agent_input, task_prompt="独立反证",
                model="gpt-6-luna", evidence_ids=allowed, output_schema_path=target)
            # 与实际 prepare_skeptic_phase 相同的最小反证权限绑定。
            invocation["tool_permissions"] = ["fixture_evidence.query", "fixture_math.calculate"]
            invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
            verify_invocation_manifest(ROOT, invocation, agent_input=agent_input)
            self.assertEqual(candidate_before, (ROOT / "product/version-manifest.json").read_bytes())
            invocation["model"] = "unapproved-model"
            invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
            with self.assertRaisesRegex(ValueError, "PRODUCT_RUNTIME_MODEL_UNSUPPORTED"):
                verify_invocation_manifest(ROOT, invocation, agent_input=agent_input)
            fixture_input = dict(agent_input, source_mode="fixture")
            candidate_model = json.loads(candidate_before)['model']
            different_model = 'gpt-5.6-terra' if candidate_model != 'gpt-5.6-terra' else 'gpt-6-luna'
            with self.assertRaisesRegex(ValueError, "model differs from candidate manifest"):
                create_invocation_manifest(ROOT, run_id="historical-source",
                    agent_name="runtime_skeptic", agent_input=fixture_input, task_prompt="fixture",
                    model=different_model, evidence_ids=allowed, output_schema_path=target)
