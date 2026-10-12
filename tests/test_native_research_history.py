"""原生归档与Memory/网页的只读接缝；不接触真实账户或模型。"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from product.runtime.research_memory import ResearchMemory
from product.tools.report_history import archive_report, read_archive, validate_archive
from product.tools.research import prepare_task, ResearchTools
from product.web.read_only import ArtifactCatalog
from product.web.app import ResearchBrowser
from tests.test_native_research_tools import SECURITY, frozen_gate
from tests.test_native_research_submission import company_draft
from tests.test_single_stock_input import alb_request


class NativeResearchHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.base = Path(self.tmp.name)
        self.task_root = self.base/"task"
        task = prepare_task(self.task_root, research_input=alb_request(), gate=frozen_gate(),
                            security_id=SECURITY, capability="COMPANY_RESEARCH")
        self.tools = ResearchTools(self.task_root, access_token=task["access_token"])
        self.tools.query(evidence_ids=["ev-revenue"])
        self.result = self.tools.submit(draft=company_draft())
        self.memory = ResearchMemory(self.base/"memory")
        self.stored = archive_report(self.tools, draft_ref=self.result["draft_ref"], memory=self.memory)

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_rejects_symlinks_overlap_and_public_roots_before_memory_write(self):
        from product.tools.report_history import export_report
        memory_root = self.base/"new-memory"
        target = self.base/"unsafe-export"
        target.symlink_to(self.base/"missing-directory", target_is_directory=True)
        public = self.base/"public"
        public.mkdir(mode=0o755)
        for output, memory in ((target, memory_root), (memory_root, memory_root),
                               (public/"export", memory_root)):
            with self.subTest(output=output):
                with self.assertRaises((ValueError, FileExistsError)):
                    export_report(self.tools, draft_ref=self.result["draft_ref"],
                                  memory_root=memory, output_dir=output)
                self.assertFalse(memory_root.exists())
        self.assertTrue(target.is_symlink())

    def test_strict_reuse_keeps_original_report_cutoff_and_rejects_changed_input_or_resources(self):
        from product.tools.report_history import reuse_archive
        from product.runtime.hashing import canonical_hash
        archive = read_archive(self.memory, object_ref=self.stored["object_ref"], object_hash=self.stored["object_hash"])
        expected = copy.deepcopy(archive["task"])
        expected["task_id"] = "another-authorized-business-task"
        expected["task_hash"] = canonical_hash({k: v for k, v in expected.items() if k != "task_hash"})
        options = {"object_ref": self.stored["object_ref"], "object_hash": self.stored["object_hash"],
                   "research_input": alb_request(), "gate": frozen_gate(), "expected_task": expected}
        reused = reuse_archive(self.memory, **options)
        self.assertEqual(reused["report"], archive["report"])
        self.assertEqual(reused["model_calls"], 0)
        self.assertEqual(reused["host_execution"], "UNVERIFIED")
        for key, value in (("research_question", "另一个问题"), ("resource_bindings", {"wrong": "0"*64}),
                           ("allowed_evidence_ids", [])):
            changed = copy.deepcopy(expected)
            changed[key] = value
            changed["task_hash"] = canonical_hash({k: v for k, v in changed.items() if k != "task_hash"})
            with self.assertRaisesRegex(ValueError, "REUSE_TASK_DRIFT"):
                reuse_archive(self.memory, **{**options, "expected_task": changed})
        wrong_input = copy.deepcopy(alb_request())
        wrong_input["research_question"] = "另一个输入"
        with self.assertRaisesRegex(ValueError, "REUSE_INPUT_OR_VERSION_DRIFT"):
            reuse_archive(self.memory, **{**options, "research_input": wrong_input})
        self.assertEqual(read_archive(self.memory, object_ref=self.stored["object_ref"], object_hash=self.stored["object_hash"]), archive)

    def test_memory_reads_native_archive_without_old_executor_or_current_task_root(self):
        original = read_archive(self.memory, object_ref=self.stored["object_ref"], object_hash=self.stored["object_hash"])
        self.task_root.rename(self.base/"task-moved")
        read = self.memory.load_report_package(self.stored["object_ref"], self.stored["object_hash"])
        self.assertEqual(read, original)
        self.assertEqual(read["report"]["host_execution"], "UNVERIFIED")
        self.assertNotIn("token", json.dumps(read))

    def test_changed_archive_and_unknown_version_reject(self):
        original = read_archive(self.memory, object_ref=self.stored["object_ref"], object_hash=self.stored["object_hash"])
        for version in ("native-research-archive/999.0.0", "unknown"):
            bad = copy.deepcopy(original)
            bad["schema_version"] = version
            with self.assertRaises(ValueError):
                validate_archive(bad)
        bad = copy.deepcopy(original)
        bad["report"]["research"]["confidence"] = 0.99
        with self.assertRaises(ValueError):
            validate_archive(bad)

    def test_web_reads_verified_report_only_and_does_not_expose_private_archive(self):
        archive = read_archive(self.memory, object_ref=self.stored["object_ref"], object_hash=self.stored["object_hash"])
        path = self.base/"native-research-archive.json"
        path.write_text(json.dumps(archive, ensure_ascii=False))
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        catalog = ArtifactCatalog(run_dirs=[self.base])
        self.assertEqual(catalog.issues, [])
        reports = catalog.native_reports(SECURITY)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0], archive["report"])
        for forbidden in ("input", "task", "gate", "token", "access_token"):
            self.assertNotIn(forbidden, reports[0])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        catalog.rescan()
        self.assertEqual(catalog.native_reports(SECURITY), reports)
        # The actual HTTP application must consume the validated projection,
        # even without a legacy Company Memory View.
        response = ResearchBrowser(None, catalog).dispatch("GET", "/reports", headers={"Host": "127.0.0.1"})
        self.assertEqual(response.status, 200)
        page = response.body.decode("utf-8")
        self.assertIn("研究归档", page)
        self.assertIn(archive["report"]["research"]["research_summary"]["summary"], page)
        self.assertIn(archive["report"]["decision_cutoff"], page)
        self.assertIn("宿主执行：未验证", page)
        for private in (archive["input"]["request_hash"], archive["task"]["task_hash"], archive["gate"]["bundle_hash"]):
            self.assertNotIn(private, page)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_web_rejects_corrupt_archive_and_escapes_author_text(self):
        archive = read_archive(self.memory, object_ref=self.stored["object_ref"], object_hash=self.stored["object_hash"])
        path = self.base/"native-research-archive.json"
        corrupt = copy.deepcopy(archive)
        corrupt["report"]["research"]["research_summary"]["summary"] = "坏归档不能展示"
        path.write_text(json.dumps(corrupt, ensure_ascii=False))
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        catalog = ArtifactCatalog(run_dirs=[self.base])
        self.assertEqual(catalog.native_reports(), [])
        response = ResearchBrowser(None, catalog).dispatch("GET", "/reports", headers={"Host": "127.0.0.1"})
        self.assertNotIn("坏归档不能展示", response.body.decode("utf-8"))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        # Escaping is checked with the same report-only consumer, without
        # weakening archive hash validation to manufacture a saved report.
        from product.web.rendering import native_reports_page
        report = copy.deepcopy(archive["report"])
        report["research"]["research_summary"]["summary"] = '<script>alert("untrusted")</script>'
        page = native_reports_page([report])
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)

    def test_missing_or_corrupt_objects_do_not_fall_back_or_rewrite(self):
        for ref, digest in (("objects/missing.json", self.stored["object_hash"]),
                            (self.stored["object_ref"], "f"*64)):
            with self.assertRaises(ValueError):
                self.memory.load_report_package(ref, digest)
