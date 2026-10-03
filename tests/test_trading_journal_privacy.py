"""Synthetic private-root and clean-plugin checks; no real plugin/account access."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from product.trading_journal.packaging import OVERLAY_ROOTS, _registered_install, prepare_clean_source, verify_installed_source
from product.trading_journal.privacy import (
    PrivacyError, assert_real_write_ready, private_root, repository_root,
    tree_hash, write_private,
)


class SyntheticProject(unittest.TestCase):
    COPY_GUARD = 'import shutil\n\ndef clone(product_root, target):\n    return shutil.copytree(product_root, target, ignore=shutil.ignore_patterns(".private", "__pycache__"))\n'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.registry_patch = patch('product.trading_journal.packaging._registered_install', return_value={'synthetic': True})
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)
        self.base = Path(self.temporary.name).resolve()
        self.repo = self.base / "repository"
        self.repo.mkdir(mode=0o700)
        self.baseline = self.base / "installed-product"
        self.baseline.mkdir(mode=0o700)
        self.put(self.repo, ".gitignore", "/product/.private/trading-journal/\n/.codex-local/\n")
        self.put(self.repo, "product/runtime/common_stock_stage.py", self.COPY_GUARD)
        self.put(self.repo, "product/skills/company-research/SKILL.md", "Unrelated reviewed Skill\n")
        self.put(self.repo, "product/version-manifest.json", json.dumps({"skills": {"company-research": "1.0.0", "tiger-trade-journal": "1.0.0", "trading-reflection": "1.0.0"}, "other": "working-root"}))
        self.put(self.repo, ".agents/plugins/marketplace.json", json.dumps({"name": "synthetic-marketplace", "plugins": [{"name": "product", "source": {"source": "local", "path": "./product"}}, {"name": "unrelated-plugin", "source": {"source": "local", "path": "./unrelated-plugin"}}]}))
        for overlay in OVERLAY_ROOTS:
            name = "helper.py" if overlay == "trading_journal" else "SKILL.md"
            self.put(self.repo, f"product/{overlay}/{name}", f"Synthetic reviewed overlay: {overlay}\n")
        self.git("init", "--quiet")
        self.git("add", ".gitignore", "product", ".agents/plugins/marketplace.json")
        # Root code and an existing Skill are dirty; clean source must use the
        # immutable installed baseline for both, regardless of tracked status.
        self.put(self.repo, "product/runtime/common_stock_stage.py", self.COPY_GUARD + 'UNRELATED_DIRTY_RUNTIME = True\n')
        self.put(self.repo, "product/skills/company-research/SKILL.md", "UNRELATED_DIRTY_SKILL\n")
        self.put(self.repo, "product/unreviewed.tmp", "UNRELATED_UNTRACKED_SOURCE\n")
        self.put(self.baseline, ".codex-plugin/plugin.json", json.dumps({"name": "product", "skills": "./skills/"}))
        self.put(self.baseline, "version-manifest.json", json.dumps({"skills": {"company-research": "1.0.0"}, "baseline_metadata": "preserved"}))
        self.put(self.baseline, "runtime/common_stock_stage.py", "REVIEWED_INSTALLED_RUNTIME\n")
        self.put(self.baseline, "skills/company-research/SKILL.md", "REVIEWED_INSTALLED_SKILL\n")
        self.put(self.baseline, "data/public-fixture.json", "{\"synthetic\":true}\n")
        self.baseline_hash = tree_hash(self.baseline)
        self.overlay_hashes = {relative: tree_hash(self.repo / "product" / relative) for relative in OVERLAY_ROOTS}

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def put(root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def git(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.repo, capture_output=True, text=True, check=True)

    def prepare(self, *, activate=False, expected_hash=None, baseline=None, overlay_hashes=None):
        result = prepare_clean_source(self.repo, baseline or self.baseline,
                                    expected_baseline_hash=expected_hash or self.baseline_hash,
                                    expected_overlay_hashes=self.overlay_hashes if overlay_hashes is None else overlay_hashes,
                                    activate=activate)
        if activate:
            installed = self.base / 'synthetic-actual-cache'
            if installed.exists():
                shutil.rmtree(installed)
            shutil.copytree(self.repo / '.codex-local/product-plugin', installed)
            private = private_root(self.repo, create=True)
            sentinel = private / 'synthetic-private-isolation-sentinel.txt'
            if not sentinel.exists():
                write_private(sentinel, 'SYNTHETIC_PRIVATE_ISOLATION_SENTINEL\n')
            with patch('product.trading_journal.packaging._registered_install', return_value={'synthetic': True}):
                result = verify_installed_source(self.repo, installed)
        return result

    def assert_code(self, code, callable_, *args, **kwargs):
        with self.assertRaises(PrivacyError) as raised:
            callable_(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)


class PrivateRootTests(SyntheticProject):
    def test_current_install_registration_change_blocks_even_when_old_cache_unchanged(self):
        self.prepare(activate=True)
        with patch('product.trading_journal.packaging._registered_install', return_value={'different': True}):
            self.assert_code('JOURNAL_ACTUAL_INSTALL_REGISTRATION_CHANGED', assert_real_write_ready, self.repo)
        with patch('product.trading_journal.packaging._registered_install',
                   side_effect=PrivacyError('JOURNAL_ACTUAL_INSTALL_REGISTRATION_UNVERIFIED')):
            self.assert_code('JOURNAL_ACTUAL_INSTALL_REGISTRATION_UNVERIFIED', assert_real_write_ready, self.repo)

    def test_install_registry_requires_enabled_version_source_and_real_cache_location(self):
        proof = self.prepare()
        source = self.repo / '.codex-local/product-plugin'
        version = json.loads((source / '.codex-plugin/plugin.json').read_text())['version']
        name = 'synthetic-marketplace'
        cache = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'plugins/cache' / name / 'product' / version
        entry = {'pluginId': 'product@' + name, 'installed': True, 'enabled': True,
                 'version': version, 'source': {'path': str(source)},
                 'marketplaceSource': {'source': str(self.repo)}}
        def response(value):
            return subprocess.CompletedProcess([], 0, stdout=json.dumps({'installed': [value]}))
        with patch('product.trading_journal.packaging.subprocess.run', return_value=response(entry)) as registration:
            result = _registered_install(self.repo, cache.resolve(), proof)
            self.assertEqual(result['plugin_id'], entry['pluginId'])
            self.assertEqual(registration.call_args.args[0], ['codex', 'plugin', 'list', '--marketplace', name, '--json'])
            self.assert_code('JOURNAL_ACTUAL_INSTALL_REGISTRATION_UNVERIFIED', _registered_install,
                             self.repo, self.base / 'arbitrary-equivalent-copy', proof)
        for changed in ({'enabled': False}, {'version': 'wrong-version'},
                        {'source': {'path': str(self.repo / 'product')}}):
            with self.subTest(changed=changed), patch('product.trading_journal.packaging.subprocess.run',
                                                    return_value=response(entry | changed)):
                self.assert_code('JOURNAL_ACTUAL_INSTALL_REGISTRATION_UNVERIFIED', _registered_install,
                                 self.repo, cache.resolve(), proof)

    def test_source_activation_alone_keeps_real_writes_blocked(self):
        result = prepare_clean_source(self.repo, self.baseline, expected_baseline_hash=self.baseline_hash,
                                      expected_overlay_hashes=self.overlay_hashes, activate=True)
        self.assertEqual(result['status'], 'SOURCE_VERIFIED')
        self.assert_code('JOURNAL_REAL_WRITE_ISOLATION_UNVERIFIED', assert_real_write_ready, self.repo)
        self.assertFalse((self.repo / 'product/.private').exists())

    def test_actual_installed_copy_mutation_invalidates_readiness(self):
        self.prepare(activate=True)
        cache = self.base / 'synthetic-actual-cache'
        self.put(cache, 'skills/trading-reflection/extra.txt', 'unexpected install drift')
        self.assert_code('JOURNAL_ACTUAL_INSTALL_CHANGED', assert_real_write_ready, self.repo)

    def test_explicit_absolute_git_root_binding(self):
        self.assertEqual(repository_root(self.repo), self.repo)
        self.assert_code("JOURNAL_EXPLICIT_ABSOLUTE_REPOSITORY_REQUIRED", repository_root, Path("repository"))
        self.assert_code("JOURNAL_PROJECT_INVALID", repository_root, self.repo / "product")
        other = self.base / "non-git-project"
        (other / "product").mkdir(parents=True)
        self.assert_code("JOURNAL_REPOSITORY_BINDING_INVALID", repository_root, other)

    def test_create_private_directories_and_exclusive_private_files(self):
        root = private_root(self.repo, create=True)
        self.assertEqual(root, self.repo / "product/.private/trading-journal")
        for path in (root.parent, root, root / "sources", root / "market", root / "artifacts"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        file = root / "sources/synthetic.csv"
        write_private(file, "synthetic-source-only\n")
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(file.read_text(), "synthetic-source-only\n")
        self.assertNotEqual(self.git("check-ignore", "--", str(file.relative_to(self.repo))).stdout.strip(), "")
        self.assertEqual(self.git("ls-files", "--", "product/.private").stdout, "")
        with self.assertRaises(FileExistsError):
            write_private(file, "must-not-replace\n")
        self.assertEqual(file.read_text(), "synthetic-source-only\n")
        write_private(file, "explicit-revision\n", replace=True)
        self.assertEqual(file.read_text(), "explicit-revision\n")
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_uninitialized_read_requires_existing_journal(self):
        self.assert_code("JOURNAL_NOT_INITIALIZED", private_root, self.repo)
        self.assertFalse((self.repo / "product/.private").exists())

    def test_non_private_directory_permission_rejected(self):
        root = private_root(self.repo, create=True)
        root.chmod(0o755)
        self.assert_code("JOURNAL_PRIVATE_DIRECTORY_PERMISSION_INVALID", private_root, self.repo)
        root.chmod(0o700)
        (root / "sources").chmod(0o755)
        self.assert_code("JOURNAL_PRIVATE_DIRECTORY_PERMISSION_INVALID", private_root, self.repo, create=True)

    def test_symlink_escape_at_private_parent_rejected_before_write(self):
        outside = self.base / "outside"
        outside.mkdir(mode=0o700)
        (self.repo / "product/.private").symlink_to(outside, target_is_directory=True)
        self.assert_code("JOURNAL_SYMLINK_FORBIDDEN", private_root, self.repo, create=True)
        self.assertFalse((outside / "trading-journal").exists())

    def test_symlink_file_and_source_directory_rejected(self):
        root = private_root(self.repo, create=True)
        outside = self.base / "outside.txt"
        outside.write_text("DO_NOT_TOUCH\n")
        link = root / "sources/link.csv"
        link.symlink_to(outside)
        self.assert_code("JOURNAL_SYMLINK_FORBIDDEN", write_private, link, "malicious\n")
        self.assertEqual(outside.read_text(), "DO_NOT_TOUCH\n")
        link.unlink()
        (root / "sources").rmdir()
        (root / "sources").symlink_to(self.base, target_is_directory=True)
        self.assert_code("JOURNAL_SYMLINK_FORBIDDEN", write_private, root / "sources/escape.csv", "malicious\n")
        self.assertFalse((self.base / "escape.csv").exists())

    def test_git_tracked_private_file_rejected_even_if_ignored(self):
        root = private_root(self.repo, create=True)
        file = root / "sources/synthetic.csv"
        write_private(file, "SYNTHETIC_PRIVATE_SENTINEL\n")
        self.git("add", "--force", str(file.relative_to(self.repo)))
        self.assert_code("JOURNAL_PRIVATE_FILE_TRACKED", private_root, self.repo)

    def test_missing_ignore_prevents_initial_creation(self):
        self.put(self.repo, ".gitignore", "/.codex-local/\n")
        self.assert_code("JOURNAL_GIT_IGNORE_MISSING", private_root, self.repo, create=True)
        self.assertFalse((self.repo / "product/.private").exists())

    def test_real_write_without_receipt_is_blocked_before_creation(self):
        self.assert_code("JOURNAL_REAL_WRITE_ISOLATION_UNVERIFIED", private_root, self.repo, create=True, real=True)
        self.assertFalse((self.repo / "product/.private").exists())


class CleanSourceTests(SyntheticProject):
    def test_only_two_journal_skill_versions_propagate_from_working_source(self):
        declared = {"skills": {"tiger-trade-journal": "1.1.0", "trading-reflection": "2.3.4",
                                "company-research": "9.9.9"},
                    "runtime": "9.9.9", "candidate_version": "working-root-candidate", "other": "working-root"}
        self.put(self.repo, "product/version-manifest.json", json.dumps(declared))
        retained = {"skills": {"company-research": "1.0.0", "tiger-trade-journal": "0.8.0",
                                "trading-reflection": "0.9.0"},
                    "runtime": "0.3.0", "candidate_version": "reviewed-baseline-candidate", "baseline_metadata": "preserved"}
        baseline_manifest = self.put(self.baseline, "version-manifest.json", json.dumps(retained))
        self.baseline_hash = tree_hash(self.baseline)
        baseline_bytes = baseline_manifest.read_bytes()
        registry_before = (self.repo / ".agents/plugins/marketplace.json").read_bytes()
        self.prepare()
        clean = self.repo / ".codex-local/product-plugin"
        expected = deepcopy(retained)
        expected["skills"].update({name: declared["skills"][name] for name in ("tiger-trade-journal", "trading-reflection")})
        self.assertEqual(json.loads((clean / "version-manifest.json").read_text()), expected)
        self.assertEqual(baseline_manifest.read_bytes(), baseline_bytes)
        self.assertEqual((clean / "runtime/common_stock_stage.py").read_bytes(), (self.baseline / "runtime/common_stock_stage.py").read_bytes())
        self.assertEqual((self.repo / ".agents/plugins/marketplace.json").read_bytes(), registry_before)

    def test_missing_scoped_skill_versions_reject_before_staging(self):
        path = self.repo / "product/version-manifest.json"
        for case in (None, {}, {"skills": {}}, {"skills": {"tiger-trade-journal": "1.1.0"}},
                     {"skills": {"trading-reflection": "1.1.0"}}):
            with self.subTest(manifest=case):
                if case is None:
                    path.unlink(missing_ok=True)
                else:
                    self.put(self.repo, "product/version-manifest.json", json.dumps(case))
                self.assert_code("JOURNAL_SKILL_VERSIONS_INVALID", self.prepare)
                self.assertFalse((self.repo / ".codex-local").exists())
                self.assertEqual(tree_hash(self.baseline), self.baseline_hash)

    def test_invalid_scoped_skill_versions_reject_before_staging(self):
        registry_before = (self.repo / ".agents/plugins/marketplace.json").read_bytes()
        for name in ("tiger-trade-journal", "trading-reflection"):
            for invalid in ("01.1.0", "1.01.0", "1.1.00", "1.1", "-1.1.0", "1.1.0\n", "", None, True, 1.1, {"major": 1}):
                with self.subTest(skill=name, version=invalid):
                    versions = {"tiger-trade-journal": "1.1.0", "trading-reflection": "1.1.0"}
                    versions[name] = invalid
                    self.put(self.repo, "product/version-manifest.json", json.dumps({"skills": versions}))
                    self.assert_code("JOURNAL_SKILL_VERSIONS_INVALID", self.prepare)
                    self.assertFalse((self.repo / ".codex-local").exists())
                    self.assertEqual(tree_hash(self.baseline), self.baseline_hash)
                    self.assertEqual((self.repo / ".agents/plugins/marketplace.json").read_bytes(), registry_before)

    def test_external_baseline_and_explicit_overlay_omit_unrelated_dirty_and_private(self):
        journal = private_root(self.repo, create=True)
        write_private(journal / "sources/sentinel.csv", "SYNTHETIC_PRIVATE_SENTINEL\n")
        self.assertTrue(self.git("diff", "--", "product/runtime/common_stock_stage.py").stdout)
        registry_before = (self.repo / ".agents/plugins/marketplace.json").read_bytes()
        result = self.prepare()
        self.assertEqual(result["status"], "PREPARED")
        self.assertEqual(set(result["overlays"]), set(OVERLAY_ROOTS))
        clean = self.repo / ".codex-local/product-plugin"
        self.assertEqual((clean / "runtime/common_stock_stage.py").read_bytes(), (self.baseline / "runtime/common_stock_stage.py").read_bytes())
        self.assertEqual((clean / "skills/company-research/SKILL.md").read_bytes(), (self.baseline / "skills/company-research/SKILL.md").read_bytes())
        self.assertEqual((self.repo / ".agents/plugins/marketplace.json").read_bytes(), registry_before)
        self.assertFalse((clean / ".private").exists())
        self.assertFalse((clean / "unreviewed.tmp").exists())
        self.assertNotIn("SYNTHETIC_PRIVATE_SENTINEL", "\n".join(path.read_text() for path in clean.rglob("*") if path.is_file()))
        versions = json.loads((clean / "version-manifest.json").read_text())
        self.assertEqual(versions["baseline_metadata"], "preserved")
        self.assertEqual(versions["skills"], {"company-research": "1.0.0", "tiger-trade-journal": "1.0.0", "trading-reflection": "1.0.0"})
        for overlay in OVERLAY_ROOTS:
            self.assertEqual(tree_hash(clean / overlay), tree_hash(self.repo / "product" / overlay))

    def test_bad_baseline_hash_and_repository_internal_baseline_rejected(self):
        self.assert_code("JOURNAL_APPROVED_BASELINE_HASH_MISMATCH", self.prepare, expected_hash="0" * 64)
        internal = self.repo / "fake-installed"
        internal.mkdir()
        self.put(internal, "file.txt", "SYNTHETIC\n")
        self.assert_code("JOURNAL_APPROVED_BASELINE_HASH_MISMATCH", self.prepare, baseline=internal, expected_hash=tree_hash(internal))
        self.assertFalse((self.repo / ".codex-local/product-plugin").exists())

    def test_private_or_symlink_in_baseline_is_rejected(self):
        self.put(self.baseline, ".private/trading-journal/sentinel", "SYNTHETIC_PRIVATE_SENTINEL\n")
        self.assert_code("JOURNAL_CODE_COPY_CONTAINS_PRIVATE_OR_LINK", tree_hash, self.baseline)
        (self.baseline / ".private/trading-journal/sentinel").unlink()
        (self.baseline / ".private/trading-journal").rmdir()
        (self.baseline / ".private").rmdir()
        (self.baseline / "external-link").symlink_to(self.repo / "product")
        self.assert_code("JOURNAL_CODE_COPY_CONTAINS_PRIVATE_OR_LINK", tree_hash, self.baseline)

    def test_overlay_private_or_link_cannot_escape_copy_boundary(self):
        folder = self.repo / "product/trading_journal/.private"
        folder.mkdir()
        self.put(folder, "sentinel", "SYNTHETIC_PRIVATE_SENTINEL\n")
        self.assert_code("JOURNAL_CODE_COPY_CONTAINS_PRIVATE_OR_LINK", self.prepare)
        self.assertFalse((self.repo / ".codex-local/product-plugin").exists())

    def test_non_product_baseline_manifest_rejected(self):
        self.put(self.baseline, ".codex-plugin/plugin.json", json.dumps({"name": "other-plugin"}))
        self.assert_code("JOURNAL_BASELINE_NOT_PRODUCT_PLUGIN", self.prepare, expected_hash=tree_hash(self.baseline))

    def test_activation_is_local_fixture_only_and_keeps_recoverable_registry(self):
        original = (self.repo / ".agents/plugins/marketplace.json").read_bytes()
        registry = json.loads(original)
        result = self.prepare(activate=True)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(assert_real_write_ready(self.repo), self.repo / "product/.private/trading-journal")
        current = json.loads((self.repo / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(current["plugins"][1], registry["plugins"][1])
        self.assertEqual(current["plugins"][0]["source"]["path"], "./.codex-local/product-plugin")
        backup = self.repo / (".codex-local/marketplace.before-" + hashlib.sha256(original).hexdigest()[:12] + ".json")
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        receipt = self.repo / ".codex-local/trading-journal-isolation.json"
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(receipt.read_text())["source_hash"], tree_hash(self.repo / ".codex-local/product-plugin"))

    def test_source_mutation_invalidates_readiness(self):
        self.prepare(activate=True)
        self.put(self.repo, ".codex-local/product-plugin/trading_journal/helper.py", "CHANGED_SOURCE\n")
        self.assert_code("JOURNAL_PLUGIN_SOURCE_CHANGED", assert_real_write_ready, self.repo)

    def test_baseline_mutation_invalidates_readiness(self):
        proof = self.prepare(activate=True)
        self.put(Path(proof["installed_baseline"]), "runtime/common_stock_stage.py", "CHANGED_BASELINE\n")
        self.assert_code("JOURNAL_INSTALLED_BASELINE_CHANGED", assert_real_write_ready, self.repo)

    def test_reviewed_baseline_is_retained_byte_equivalent_before_source_switch(self):
        self.put(self.baseline, "__pycache__/ignored.pyc", "SYNTHETIC_CACHE_BYTES\n")
        expected_files = {path.relative_to(self.baseline).as_posix(): path.read_bytes()
                          for path in self.baseline.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
        registry_before = (self.repo / ".agents/plugins/marketplace.json").read_bytes()
        result = self.prepare()
        retained = Path(result["installed_baseline"])
        self.assertEqual(retained, self.repo / ".codex-local" / ("product-plugin-baseline-" + self.baseline_hash[:16]))
        self.assertEqual(result["original_installed_baseline"], str(self.baseline))
        self.assertEqual(tree_hash(retained), self.baseline_hash)
        self.assertEqual(retained.stat().st_mode & 0o777, 0o700)
        self.assertFalse((retained / "__pycache__").exists())
        self.assertEqual({path.relative_to(retained).as_posix(): path.read_bytes()
                          for path in retained.rglob("*") if path.is_file()}, expected_files)
        self.assertEqual((self.repo / ".agents/plugins/marketplace.json").read_bytes(), registry_before)

    def test_installer_removing_original_cache_keeps_verified_recovery_and_guard_valid(self):
        result = prepare_clean_source(self.repo, self.baseline, expected_baseline_hash=self.baseline_hash,
                                      expected_overlay_hashes=self.overlay_hashes, activate=True)
        retained = Path(result["installed_baseline"])
        shutil.rmtree(self.baseline)
        installed = self.base / "synthetic-cache-after-cleanup"
        shutil.copytree(self.repo / ".codex-local/product-plugin", installed)
        journal = private_root(self.repo, create=True)
        write_private(journal / "synthetic-private-isolation-sentinel.txt", "SYNTHETIC_PRIVATE_ISOLATION_SENTINEL\n")
        proof = verify_installed_source(self.repo, installed)
        self.assertEqual(proof["status"], "VERIFIED")
        self.assertEqual(proof["installed_baseline"], str(retained))
        self.assertEqual(tree_hash(retained), self.baseline_hash)
        self.assertEqual((retained / "runtime/common_stock_stage.py").read_text(), "REVIEWED_INSTALLED_RUNTIME\n")
        self.assertEqual(assert_real_write_ready(self.repo), journal)
        self.assertFalse(self.baseline.exists())

    def test_original_cache_can_disappear_after_retention_without_affecting_prepare(self):
        original_copytree = shutil.copytree
        registry_before = (self.repo / ".agents/plugins/marketplace.json").read_bytes()
        copied_before_switch = []

        def copy_and_simulate_cleanup(source, destination, *arguments, **options):
            result = original_copytree(source, destination, *arguments, **options)
            if Path(source) == self.baseline:
                self.assertEqual((self.repo / ".agents/plugins/marketplace.json").read_bytes(), registry_before)
                self.assertFalse((self.repo / ".codex-local/product-plugin").exists())
                copied_before_switch.append(Path(destination))
                shutil.rmtree(self.baseline)
            return result

        with patch("product.trading_journal.packaging.shutil.copytree", side_effect=copy_and_simulate_cleanup):
            proof = self.prepare(activate=True)
        self.assertEqual(copied_before_switch, [Path(proof["installed_baseline"])])
        self.assertFalse(self.baseline.exists())
        self.assertEqual(tree_hash(Path(proof["installed_baseline"])), self.baseline_hash)
        self.assertEqual(assert_real_write_ready(self.repo), self.repo / "product/.private/trading-journal")

    def test_existing_matching_retention_is_reused_without_copying_original_again(self):
        original = self.prepare()
        original_copytree = shutil.copytree
        with patch("product.trading_journal.packaging.shutil.copytree", wraps=original_copytree) as copier:
            repeated = self.prepare()
        self.assertEqual(repeated["installed_baseline"], original["installed_baseline"])
        self.assertFalse(any(Path(call.args[0]) == self.baseline for call in copier.call_args_list))
        self.assertEqual(tree_hash(Path(repeated["installed_baseline"])), self.baseline_hash)

    def test_corrupt_existing_retention_is_not_overwritten_or_activated(self):
        original = self.prepare()
        retained = Path(original["installed_baseline"])
        self.put(retained, "runtime/common_stock_stage.py", "CORRUPTED_RETAINED_BYTES\n")
        registry_before = (self.repo / ".agents/plugins/marketplace.json").read_bytes()
        source_hash_before = tree_hash(self.repo / ".codex-local/product-plugin")
        self.assert_code("JOURNAL_BASELINE_RETENTION_HASH_MISMATCH", self.prepare, activate=True)
        self.assertEqual((retained / "runtime/common_stock_stage.py").read_text(), "CORRUPTED_RETAINED_BYTES\n")
        self.assertEqual((self.repo / ".agents/plugins/marketplace.json").read_bytes(), registry_before)
        self.assertEqual(tree_hash(self.repo / ".codex-local/product-plugin"), source_hash_before)

    def test_linked_retention_and_linked_input_are_rejected(self):
        local = self.repo / ".codex-local"
        local.mkdir(mode=0o700)
        retained = local / ("product-plugin-baseline-" + self.baseline_hash[:16])
        retained.symlink_to(self.baseline, target_is_directory=True)
        self.assert_code("JOURNAL_SYMLINK_FORBIDDEN", self.prepare, activate=True)
        self.assertFalse((local / "product-plugin").exists())
        retained.unlink()
        linked_input = self.base / "linked-baseline"
        linked_input.symlink_to(self.baseline, target_is_directory=True)
        self.assert_code("JOURNAL_SYMLINK_FORBIDDEN", self.prepare, baseline=linked_input)

    def test_retention_copy_corruption_is_detected_before_source_activation(self):
        original_copytree = shutil.copytree
        registry_before = (self.repo / ".agents/plugins/marketplace.json").read_bytes()

        def corrupt_retained_copy(source, destination, *arguments, **options):
            result = original_copytree(source, destination, *arguments, **options)
            if Path(source) == self.baseline:
                self.put(Path(destination), "runtime/common_stock_stage.py", "COPY_CORRUPTION\n")
            return result

        with patch("product.trading_journal.packaging.shutil.copytree", side_effect=corrupt_retained_copy):
            self.assert_code("JOURNAL_BASELINE_RETENTION_HASH_MISMATCH", self.prepare, activate=True)
        self.assertEqual((self.repo / ".agents/plugins/marketplace.json").read_bytes(), registry_before)
        self.assertFalse((self.repo / ".codex-local/product-plugin").exists())

    def test_missing_corrupt_or_linked_recovery_baseline_does_not_publish_verified(self):
        source = prepare_clean_source(self.repo, self.baseline, expected_baseline_hash=self.baseline_hash,
                                      expected_overlay_hashes=self.overlay_hashes, activate=True)
        installed = self.base / "synthetic-copy"
        shutil.copytree(self.repo / ".codex-local/product-plugin", installed)
        journal = private_root(self.repo, create=True)
        write_private(journal / "synthetic-private-isolation-sentinel.txt", "SYNTHETIC_PRIVATE_ISOLATION_SENTINEL\n")
        retained = Path(source["installed_baseline"])
        receipt = self.repo / ".codex-local/trading-journal-isolation.json"
        previous_bytes = receipt.read_bytes()
        for failure in ("missing", "corrupt", "linked"):
            with self.subTest(failure=failure):
                if retained.is_symlink():
                    retained.unlink()
                elif retained.exists():
                    shutil.rmtree(retained)
                shutil.copytree(self.baseline, retained)
                if failure == "missing":
                    shutil.rmtree(retained)
                elif failure == "corrupt":
                    self.put(retained, "runtime/common_stock_stage.py", "CORRUPTED_BEFORE_VERIFY\n")
                else:
                    shutil.rmtree(retained)
                    retained.symlink_to(self.baseline, target_is_directory=True)
                with self.assertRaises(PrivacyError):
                    verify_installed_source(self.repo, installed)
                self.assertEqual(receipt.read_bytes(), previous_bytes)
                self.assertEqual(json.loads(receipt.read_text())["status"], "SOURCE_VERIFIED")

    def test_registry_mutation_invalidates_readiness(self):
        self.prepare(activate=True)
        registry = json.loads((self.repo / ".agents/plugins/marketplace.json").read_text())
        registry["name"] = "CHANGED_REGISTRY"
        self.put(self.repo, ".agents/plugins/marketplace.json", json.dumps(registry))
        self.assert_code("JOURNAL_PLUGIN_SOURCE_CHANGED", assert_real_write_ready, self.repo)

    def test_copy_guard_mutation_invalidates_readiness(self):
        self.prepare(activate=True)
        self.put(self.repo, "product/runtime/common_stock_stage.py", self.COPY_GUARD + "CHANGED_GUARD = True\n")
        self.assert_code("JOURNAL_RUNTIME_COPY_GUARD_CHANGED", assert_real_write_ready, self.repo)

    def test_comment_string_without_actual_copy_exclusion_does_not_authorize(self):
        self.put(self.repo, "product/runtime/common_stock_stage.py", 'import shutil\n\ndef clone(product_root, target):\n    # Pretend that ".private" is excluded\n    return shutil.copytree(product_root, target)\n')
        with self.assertRaises(PrivacyError):
            self.prepare(activate=True)

    def test_changed_overlay_or_missing_approved_hash_is_rejected(self):
        self.put(self.repo, "product/trading_journal/helper.py", "UNREVIEWED_CHANGE_WITHIN_NEW_DIRECTORY\n")
        with self.assertRaises(PrivacyError):
            self.prepare()
        self.assertFalse((self.repo / ".codex-local/product-plugin").exists())
        with self.assertRaises(PrivacyError):
            self.prepare(overlay_hashes={})

    def test_receipt_identity_or_status_mutation_invalidates_readiness(self):
        self.prepare(activate=True)
        receipt_path = self.repo / ".codex-local/trading-journal-isolation.json"
        original = json.loads(receipt_path.read_text())
        for change in ({"status": "PREPARED"}, {"repository_root": str(self.base / "other-project")}, {"source_hash": "0" * 64}):
            tampered = deepcopy(original)
            tampered.update(change)
            write_private(receipt_path, json.dumps(tampered), replace=True)
            with self.subTest(change=change), self.assertRaises(PrivacyError):
                assert_real_write_ready(self.repo)

    def test_receipt_symlink_cannot_supply_write_authorization(self):
        self.prepare(activate=True)
        receipt = self.repo / ".codex-local/trading-journal-isolation.json"
        outside = self.base / "outside-receipt.json"
        outside.write_bytes(receipt.read_bytes())
        receipt.unlink()
        receipt.symlink_to(outside)
        self.assert_code("JOURNAL_SYMLINK_FORBIDDEN", assert_real_write_ready, self.repo)

    def test_receipt_noncritical_metadata_mutation_also_invalidates_integrity(self):
        self.prepare(activate=True)
        receipt_path = self.repo / ".codex-local/trading-journal-isolation.json"
        original = json.loads(receipt_path.read_text())
        altered = deepcopy(original)
        altered["overlays"]["trading_journal"] = "0" * 64
        write_private(receipt_path, json.dumps(altered), replace=True)
        with self.assertRaises(PrivacyError):
            assert_real_write_ready(self.repo)
        altered = deepcopy(original)
        altered["unchanged_baseline_file_count"] += 1
        write_private(receipt_path, json.dumps(altered), replace=True)
        with self.assertRaises(PrivacyError):
            assert_real_write_ready(self.repo)

    def test_receipt_and_private_local_directory_must_keep_private_modes(self):
        self.prepare(activate=True)
        receipt_path = self.repo / ".codex-local/trading-journal-isolation.json"
        receipt_path.chmod(0o644)
        with self.assertRaises(PrivacyError):
            assert_real_write_ready(self.repo)
        receipt_path.chmod(0o600)
        receipt_path.parent.chmod(0o755)
        with self.assertRaises(PrivacyError):
            assert_real_write_ready(self.repo)

    def test_source_overlay_changed_in_working_tree_invalidates_approved_receipt(self):
        self.prepare(activate=True)
        self.put(self.repo, "product/trading_journal/helper.py", "CHANGED_CURRENT_OVERLAY_AFTER_APPROVAL\n")
        with self.assertRaises(PrivacyError):
            assert_real_write_ready(self.repo)


if __name__ == "__main__":
    unittest.main()
