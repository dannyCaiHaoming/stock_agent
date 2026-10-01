"""实际语义 Hook 产物到既有只读消费者；无模型或网络。"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import file_hash, legacy_envelope_hash
from product.runtime.multidimensional_stage import (
    build_multidimensional_dispatch_packet, finalize_multidimensional_stage_run,
    check_multidimensional_bundle_consumable,
)
from product.web.read_only import ArtifactCatalog
from product.web.read_only import ReadOnlyResearchMemory, BrowserDataError
from product.runtime import common_stock_stage
from product.runtime.research_memory import ResearchMemory, report_entry_id
from tests import test_multidimensional_stage as stage_fixtures
from tests import test_common_stock_semantic_handoff as stock_semantic
from tests import test_common_stock_research_contracts as stock_fixtures
from tests.test_local_research_browser import dimension_report


class ResearchHandoffConsumerTests(unittest.TestCase):
    def test_all_native_dimension_reports_reach_original_bundle_and_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, dependent, source_path, _ = self.prepare_reports(Path(directory))
            f = stage_fixtures.MultidimensionalStageTests()
            index = json.loads((run / "research/dispatch-index.json").read_text())
            for task in index["tasks"]:
                if task["capability"] in {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT"}:
                    continue
                env = f.targeted_environment(run, task)
                parent, child = "bundle-parent:" + task["task_id"], "bundle-child:" + task["task_id"]
                allowed, _ = handle_hook_event(f.dispatch_payload(task, parent=parent), environ=env)
                self.assertEqual(allowed["decision"], "ALLOW", allowed)
                started, _ = handle_hook_event(f.start_payload(task, parent=parent, child=child), environ=env)
                self.assertEqual(started["context_binding"]["status"], "DELIVERED", started)
                saved, _ = handle_hook_event(f.stop_payload(task, f.dimension_draft(task),
                                                           parent=parent, child=child), environ=env)
                self.assertEqual(saved["output_capture"]["status"], "SAVED", saved)
            before_reports = {str(path.relative_to(run)): path.read_bytes()
                              for path in (run / "research/reports").rglob("*") if path.is_file()}
            result = finalize_multidimensional_stage_run(stage_fixtures.ROOT, run)
            self.assertEqual(result["status"], "PASSED", result)
            bundle = json.loads((run / "research/holding-research-bundle.json").read_text())
            self.assertEqual(len(bundle["report_refs"]), len(index["tasks"]))
            self.assertEqual(bundle["consumability"], "STRUCTURALLY_CONSUMABLE")
            self.assertNotIn("decision", bundle)
            for reference in bundle["report_refs"]:
                report = json.loads((run / reference["artifact_ref"]).read_text())
                self.assertEqual(reference["report_hash"], report["report_hash"])
                self.assertEqual(reference["report_id"], report["report_id"])
                self.assertEqual(reference["security_ids"], report["security_ids"])
            reference = next(item for item in bundle["report_refs"] if item["capability"] == "RESEARCH_REPORT")
            self.assertEqual(json.loads((run / reference["artifact_ref"]).read_text()), dependent)
            whole_package = {str(path.relative_to(run)): file_hash(path)
                             for path in run.rglob("*") if path.is_file()}
            parsed = check_multidimensional_bundle_consumable(stage_fixtures.ROOT, run, persist=False)
            self.assertEqual(parsed["status"], "PASSED")
            self.assertFalse(parsed["complete_portfolio_decision"])
            self.assertEqual(len(parsed["report_inventory"]), len(index["tasks"]))
            self.assertEqual(parsed["downstream_status"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(before_reports, {ref: (run / ref).read_bytes() for ref in before_reports})
            self.assertEqual(whole_package, {str(path.relative_to(run)): file_hash(path)
                                            for path in run.rglob("*") if path.is_file()})
            moved = Path(directory) / "copied-history"
            shutil.copytree(run, moved)
            preserved = Path(directory) / "original-outside-declared-path"
            run.rename(preserved)
            try:
                moved_result = check_multidimensional_bundle_consumable(
                    Path(directory) / "unavailable-repository", moved, persist=False)
                self.assertEqual(moved_result, parsed)
                self.assertEqual(whole_package, {str(path.relative_to(moved)): file_hash(path)
                                                for path in moved.rglob("*") if path.is_file()})
                for defect in ("missing-packet", "symlink-packet", "missing-original-binding"):
                    with self.subTest(defect=defect), tempfile.TemporaryDirectory() as broken:
                        clone = Path(broken) / "package"
                        shutil.copytree(moved, clone)
                        if defect == "missing-original-binding":
                            manifest = json.loads((clone / "run_manifest.json").read_text())
                            del manifest["output_dir"]
                            manifest["manifest_hash"] = legacy_envelope_hash(manifest, hash_field="manifest_hash")
                            (clone / "run_manifest.json").write_text(json.dumps(manifest))
                        else:
                            path = clone / index["tasks"][0]["packet_path"]
                            if defect == "symlink-packet":
                                outside = Path(broken) / "outside.json"
                                shutil.copyfile(path, outside)
                                path.unlink()
                                path.symlink_to(outside)
                            else:
                                path.unlink()
                        before = {str(path.relative_to(clone)): file_hash(path)
                                  for path in clone.rglob("*") if path.is_file()}
                        with self.assertRaises(ValueError):
                            check_multidimensional_bundle_consumable(stage_fixtures.ROOT, clone, persist=False)
                        self.assertEqual(before, {str(path.relative_to(clone)): file_hash(path)
                                                  for path in clone.rglob("*") if path.is_file()})
            finally:
                preserved.rename(run)
            # 改写了上游原报告版本，即使重算其自 hash，也不能满足旧引用。
            changed = json.loads(source_path.read_text())
            changed["claims"][0]["statement"] += " 另一版本。"
            changed["report_hash"] = legacy_envelope_hash(changed, hash_field="report_hash")
            source_path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                check_multidimensional_bundle_consumable(stage_fixtures.ROOT, run, persist=False)

    def test_native_stock_hook_to_finalizer_memory_and_readonly_report(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            memory_root = base / "memory"
            prepare = stock_fixtures.prepare_common_stock_stage_run

            def with_memory(*args, **kwargs):
                return prepare(*args, **{**kwargs, "memory_root": memory_root})

            helper = stock_semantic.CommonStockSemanticHandoffTests()
            with patch.object(stock_fixtures, "prepare_common_stock_stage_run", side_effect=with_memory):
                run, task, request, context, env, start = helper.prepare(directory)
            packet = helper.frozen_packet(run, task)
            helper.call(run, request, "query", evidence_ids=context["allowed_evidence_ids"])
            calculation = helper.call(run, request, "calculate", operation="ratio",
                                      evidence_ids=context["allowed_evidence_ids"])
            draft = helper.draft(request, packet)
            draft["calculation_selections"] = [{"calculation_ref": calculation["calculation_ref"],
                                                 "claim_ids": [draft["claims"][0]["claim_id"]]}]
            record = helper.stop(env, start, draft)
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            report_path = run / record["output_capture"]["path"]
            report = json.loads(report_path.read_text())
            self.assertEqual(common_stock_stage.finalize_common_stock_stage_run(stock_fixtures.ROOT, run)["status"], "PASSED")
            memory = ResearchMemory(memory_root)
            stored = memory.reusable_report(task["security_id"], task["reuse_key"])
            self.assertIsNotNone(stored)
            package = memory.load_report_package(stored["package_ref"], stored["package_hash"])
            self.assertEqual(package["report"], report)
            self.assertEqual(package["request"], request)
            gate = json.loads((run / "evidence/gate.json").read_text())
            self.assertEqual(package["evidence"], [fact for fact in gate["allowed_evidence"]
                                                   if fact["evidence_id"] in request["allowed_evidence_ids"]])
            self.assertEqual(package["manifest"]["report_hash"], stored["report_hash"])
            self.assertEqual(package["report"]["claims"][0]["statement"], draft["claims"][0]["statement"])
            before = report_path.read_bytes()
            reader = ReadOnlyResearchMemory(memory_root)
            entry = report_entry_id(task["reuse_key"], stored["report_hash"])
            displayed = reader.report(task["security_id"], entry)
            self.assertEqual(displayed["report"]["claims"], report["claims"])
            self.assertEqual(displayed["report_hash"], stored["report_hash"])
            self.assertEqual(report_path.read_bytes(), before)
            # 自包含 Memory 对象不是原绝对运行目录的跳转或技术包装。
            shutil.rmtree(run)
            self.assertEqual(reader.report(task["security_id"], entry), displayed)
            object_path = memory_root / stored["package_ref"]
            original = object_path.read_bytes()
            changed = json.loads(original)
            changed["report"]["claims"][0]["statement"] += " 非法篡改。"
            object_path.write_text(json.dumps(changed))
            with self.assertRaises(BrowserDataError):
                reader.report(task["security_id"], entry)
            self.assertEqual(object_path.read_text(), json.dumps(changed))

    def prepare_reports(self, base):
        f = stage_fixtures.MultidimensionalStageTests()
        run, _ = f.prepare(base, count=1)
        index = json.loads((run / "research/dispatch-index.json").read_text())
        f.save_fundamental_dependency(run, index)
        task = next(t for t in index["tasks"] if t["capability"] == "RESEARCH_REPORT")
        packet = build_multidimensional_dispatch_packet(stage_fixtures.ROOT, run, task["task_name"])
        ref = next(iter(packet["reference_map"]["claims"]))
        draft = f.dimension_draft(task)
        draft["claims"] = [{
            "claim_id": "local", "question": "上游事实能说明什么？",
            "statement": "上游仅提供经营基线，不能证明未来回报；仍缺独立研报正文。",
            "kind": "INTERPRETATION", "evidence_refs": [], "research_claim_refs": [ref],
            "document_refs": [], "assumption_ids": [],
        }]
        env = f.targeted_environment(run, task)
        handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=env)
        handle_hook_event(f.start_payload(task, parent="dependency-parent", child="reader-child"), environ=env)
        record, _ = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="reader-child"), environ=env)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        target_path = run / record["output_capture"]["path"]
        target = json.loads(target_path.read_text())
        source_path = next(path for path in (run / "research/reports").glob("*/dimension-report.json")
                           if json.loads(path.read_text())["capability"] == "FUNDAMENTAL_EVENT")
        return run, task, target, source_path, record

    def test_actual_hook_reports_reach_browser_without_loss_or_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, report, _, record = self.prepare_reports(Path(directory))
            before = {str(path.relative_to(run)): file_hash(path) for path in run.rglob('*') if path.is_file()}
            catalog = ArtifactCatalog(run_dirs=[run])
            # 基础合成 fixture 的 Gate 未声明浏览器 schema，不将其升级为真实 Gate。
            self.assertFalse(any(issue["code"].startswith("DIMENSION_REPORT_")
                                 for issue in catalog.issues), catalog.issues)
            items = catalog.company_reports(task["security_ids"][0], report["bindings"]["decision_cutoff"],
                                             task["run_id"], task["allowed_evidence_ids"])["items"]
            selected = next(item for item in items if item["capability"] == "RESEARCH_REPORT")
            self.assertEqual(selected["status"], "AVAILABLE")
            self.assertEqual(selected["reports"][0]["value"], report)
            markdown = (run / record["output_capture"]["markdown_path"]).read_text()
            self.assertIn(report["claims"][0]["statement"], markdown)
            self.assertEqual(before, {str(path.relative_to(run)): file_hash(path)
                                      for path in run.rglob('*') if path.is_file()})

    def test_missing_drifting_or_other_source_report_cannot_satisfy_loaded_claim(self):
        for defect in ("missing", "version", "foreign-directory", "invalid-source"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run, _, report, source_path, _ = self.prepare_reports(Path(directory))
                extras = []
                if defect == "version" or defect == "invalid-source":
                    source = json.loads(source_path.read_text())
                    source["claims"][0]["statement"] += " 更新后的不同版本。"
                    if defect == "invalid-source":
                        source["claims"][0]["research_claim_refs"] = ["not-loaded"]
                    source["report_hash"] = legacy_envelope_hash(source, hash_field="report_hash")
                    source_path.write_text(json.dumps(source))
                elif defect == "foreign-directory":
                    foreign = Path(directory) / "same-id-different-source"
                    target = foreign / "research/reports/source/dimension-report.json"
                    target.parent.mkdir(parents=True)
                    shutil.copy2(source_path, target)
                    shutil.copy2(run / "run_manifest.json", foreign / "run_manifest.json")
                    source_path.unlink()
                    extras.append(foreign)
                else:
                    source_path.unlink()
                before = {str(path): file_hash(path) for path in Path(directory).rglob('*') if path.is_file()}
                catalog = ArtifactCatalog(run_dirs=[run, *extras])
                self.assertFalse(any(item["value"]["report_id"] == report["report_id"]
                                     for item in catalog.by_kind("dimension_report")))
                self.assertTrue(any(issue["code"] == "DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING"
                                    for issue in catalog.issues))
                self.assertEqual(before, {str(path): file_hash(path) for path in Path(directory).rglob('*') if path.is_file()})

    def test_legacy_ambiguous_claim_and_cycles_do_not_depend_on_scan_order(self):
        for defect in ("ambiguous", "cycle"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run = Path(directory)
                (run / "run_manifest.json").write_text(json.dumps({"run_id": "run-1"}))
                sources = [dimension_report(capability="FUNDAMENTAL_EVENT", report_id="source:first"),
                           dimension_report(capability="FUNDAMENTAL_EVENT", report_id="source:second")]
                target = dimension_report(capability="RESEARCH_REPORT", report_id="dependent")
                target["claims"][0]["claim_id"] = "dependent-claim"
                target["observation_conditions"][0]["claim_refs"] = ["dependent-claim"]
                target["claims"][0]["research_claim_refs"] = ["claim-1"]
                if defect == "cycle":
                    sources = sources[:1]
                    sources[0]["claims"][0]["research_claim_refs"] = ["dependent-claim"]
                for i, value in enumerate([*sources, target]):
                    value["report_hash"] = legacy_envelope_hash(value, hash_field="report_hash")
                    path = run / f"research/reports/{i}/dimension-report.json"
                    path.parent.mkdir(parents=True)
                    path.write_text(json.dumps(value))
                catalog = ArtifactCatalog(run_dirs=[run])
                self.assertFalse(any(item["value"]["report_id"] == "dependent"
                                     for item in catalog.by_kind("dimension_report")))
                self.assertTrue(any(issue["code"] == "DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING"
                                    for issue in catalog.issues))
