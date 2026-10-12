"""product就地薄发现的确定性正反例，不执行宿主或证明原生加载。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from product.tools.package_content import prepare_claude_workspace, ROLES

ROOT = Path(__file__).resolve().parents[1]


def discovery_sources():
    names = {"product/AGENTS.md", "product/agents/runtime_cio.md",
             "product/hosts/claude-code/main-thread.md", "product/hosts/claude-code/mcp.json"}
    names.update(f"product/agents/{role}.md" for role in ROLES)
    names.update(f"product/hosts/claude-code/agents/{role}.md" for role in ROLES)
    names.update(f"product/hosts/claude-code/skills/{role}-native/SKILL.md" for role in ("company", "market", "skeptic"))
    names.update(str(path.relative_to(ROOT)) for path in (ROOT/"product/skills").rglob("*")
                 if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    return {name: (ROOT/name).read_bytes() for name in sorted(names)}


class NativeProductWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.base = Path(self.tmp.name)
        self.repo = self.base/"repo"
        self.sources = discovery_sources()
        for name, raw in self.sources.items():
            path = self.repo/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.product = self.repo/"product"
        (self.product/"business.py").write_text("SOURCE_SENTINEL = True\n")
        self.hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in self.sources.items()}

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, **kwargs):
        return prepare_claude_workspace(self.repo, reviewed_file_hashes=self.hashes,
                                        python_interpreter=sys.executable, **kwargs)

    def snapshot(self):
        return {str(p.relative_to(self.repo)): ("link", os.readlink(p)) if p.is_symlink() else p.read_bytes()
                for p in self.repo.rglob("*") if p.is_file() or p.is_symlink()}

    def test_default_discovery_is_thin_source_bound_and_has_no_active_research_connection(self):
        before = self.snapshot()
        result = self.prepare()
        self.assertEqual(result["status"], "PREPARED_NOT_LOAD_VERIFIED")
        self.assertEqual(result["host_execution"], "UNVERIFIED")
        self.assertEqual(json.loads((self.product/".mcp.json").read_text()), {"mcpServers": {}})
        for name, raw in before.items():
            self.assertEqual((self.repo/name).read_bytes(), raw)
        for name in result["files"]:
            self.assertTrue(name in {"CLAUDE.md", ".mcp.json"} or name.startswith((".claude/agents/", ".claude/skills/")))
        for path in (self.product/".claude").rglob("*.py"):
            self.assertTrue(path.is_symlink())
            self.assertTrue(path.resolve().is_relative_to(self.product/"skills"))
        council = self.product/".claude/skills/portfolio-council/SKILL.md"
        self.assertIn("`../../../agents/`", council.read_text())
        self.assertNotIn("../../../product/agents/", council.read_text())
        for relative in ("tiger-trade-journal/scripts/journal.py", "trading-reflection/references/report-format.md"):
            link = self.product/".claude/skills"/relative
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), self.product/"skills"/relative)
        from tests.test_native_host_templates import frontmatter
        for role in ROLES:
            original = frontmatter(self.product/f"hosts/claude-code/agents/{role}.md")
            header, lists, body = frontmatter(self.product/f".claude/agents/{role}.md")
            self.assertEqual((header, lists), original[:2])
            self.assertEqual(header["model"], "inherit")
            self.assertEqual(body.strip(), self.sources[f"product/agents/{role}.md"].decode().strip())
        expected = (self.sources["product/AGENTS.md"] + b"\n"
                    + self.sources["product/hosts/claude-code/main-thread.md"] + b"\n"
                    + self.sources["product/agents/runtime_cio.md"])
        self.assertEqual((self.product/"CLAUDE.md").read_bytes(), expected)
        self.assertFalse((self.product/"product").exists())

    def test_in_place_and_export_skill_layouts_only_relocate_shared_links(self):
        from product.tools.package_content import _claude_discovery
        before = self.snapshot()
        exported = _claude_discovery(self.sources, python_interpreter=sys.executable,
                                      module_root=self.repo, connection_files={}, in_place=False)
        self.assertEqual(self.snapshot(), before)
        result = self.prepare()
        for name, raw in self.sources.items():
            if not (name.startswith("product/skills/") and name.count("/") == 3
                    and name.endswith("/SKILL.md")):
                continue
            relative = ".claude/skills/"+name.removeprefix("product/skills/")
            current = self.product/relative
            with self.subTest(skill=name):
                expected = raw.replace(b"`../../agents/`", b"`../../../agents/`")
                expected = expected.replace(b"`../../hosts/README.md`", b"`../../../hosts/README.md`")
                self.assertFalse(current.is_symlink())
                self.assertEqual(current.read_bytes(), expected)
                self.assertEqual(exported[relative].replace(b"`../../../product/agents/`", b"`../../../agents/`")
                                 .replace(b"`../../../product/hosts/README.md`", b"`../../../hosts/README.md`"),
                                 expected)
                self.assertEqual(result["source_files"][name], hashlib.sha256(raw).hexdigest())
                self.assertEqual(result["files"][relative], {"sha256": hashlib.sha256(expected).hexdigest()})
                self.assertEqual((self.repo/name).read_bytes(), raw)
        council = ".claude/skills/portfolio-council/SKILL.md"
        self.assertIn(b"`../../../product/agents/`", exported[council])
        self.assertNotIn(b"`../../../product/agents/`", (self.product/council).read_bytes())
        self.assertEqual((self.product/"business.py").read_bytes(), before["product/business.py"])
        self.assertFalse((self.product/"product").exists())
        self.assertEqual(result["status"], "PREPARED_NOT_LOAD_VERIFIED")
        self.assertEqual(result["host_execution"], "UNVERIFIED")
        self.assertEqual(result["content_verdict"], "NOT_REVIEWED")

    def test_explicit_connections_bind_current_module_root_and_never_read_the_private_file(self):
        private_file = self.base/"private-connections.json"
        private_file.write_text("SYNTHETIC_SECRET_NOT_READ")
        read_bytes = Path.read_bytes
        def read(path):
            if path == private_file:
                raise AssertionError("Configuration preparation must not read credentials")
            return read_bytes(path)
        with patch.object(Path, "read_bytes", read):
            self.prepare(claude_connection_files={"company": str(private_file), "skeptic": str(private_file)})
        config = json.loads((self.product/".mcp.json").read_text())
        self.assertEqual(set(config["mcpServers"]), {"company", "skeptic"})
        for server in config["mcpServers"].values():
            self.assertEqual(server["command"], sys.executable)
            self.assertEqual(server["env"], {"PYTHONPATH": str(self.repo)})
            self.assertEqual(server["args"][-2:], ["--connection-env-file", str(private_file)])
            self.assertEqual(server["args"][:3], ["-B", "-m", "product.mcp.research"])
        self.assertNotIn("SYNTHETIC_SECRET_NOT_READ", json.dumps(self.snapshot(), default=str))

    def test_refresh_only_unmodified_owned_files_and_preserves_unrelated_files(self):
        connections = {role: str(self.base/f"{role}-connections.json")
                       for role in ("company", "market", "skeptic", "cio")}
        self.prepare(claude_connection_files=connections)
        mcp_before = (self.product/".mcp.json").read_bytes()
        user = self.product/".claude/settings.local.json"
        user.write_text('{"user":true}\n')
        updates = ("product/agents/runtime_company_analyst.md", "product/hosts/claude-code/main-thread.md")
        for name in updates:
            (self.repo/name).write_bytes(self.sources[name]+b"\n<!-- reviewed update -->\n")
            self.hashes[name] = hashlib.sha256((self.repo/name).read_bytes()).hexdigest()
        result = self.prepare(claude_connection_files=connections)
        self.assertIn("<!-- reviewed update -->", (self.product/".claude/agents/runtime_company_analyst.md").read_text())
        expected = b"\n".join((self.repo/name).read_bytes() for name in (
            "product/AGENTS.md", "product/hosts/claude-code/main-thread.md", "product/agents/runtime_cio.md"))
        self.assertEqual((self.product/"CLAUDE.md").read_bytes(), expected)
        self.assertEqual((self.product/".mcp.json").read_bytes(), mcp_before)
        for name in updates:
            self.assertEqual(result["source_files"][name], self.hashes[name])
        self.assertEqual(user.read_text(), '{"user":true}\n')
        before = self.snapshot()
        self.prepare(claude_connection_files=connections)
        after = self.snapshot()
        before.pop("product/.claude/native-product.json")
        after.pop("product/.claude/native-product.json")
        self.assertEqual(before, after)

    def test_unknown_same_named_file_rejects_before_any_writes(self):
        for relative in ("CLAUDE.md", ".mcp.json", ".claude/agents/runtime_skeptic.md", ".claude/skills/valuation/SKILL.md"):
            path = self.product/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("USER_FILE")
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, "TARGET_CONFLICT"):
                self.prepare()
            self.assertEqual(self.snapshot(), before)
            path.unlink()

    def test_source_drift_missing_method_and_non_discovery_source_reject_before_write(self):
        path = self.product/"agents/runtime_skeptic.md"
        path.write_text("UNREVIEWED")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "SOURCE_DRIFT"):
            self.prepare()
        self.assertEqual(before, self.snapshot())
        path.write_bytes(self.sources["product/agents/runtime_skeptic.md"])
        del self.hashes["product/skills/valuation/SKILL.md"]
        with self.assertRaisesRegex(ValueError, "CONTENT_INCOMPLETE"):
            self.prepare()
        self.assertFalse((self.product/"CLAUDE.md").exists())
        self.hashes["product/business.py"] = hashlib.sha256((self.product/"business.py").read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "SOURCE_NOT_DISCOVERY"):
            self.prepare()
        self.assertFalse((self.product/".claude").exists())

    def test_managed_file_or_attachment_link_drift_rejects_and_keeps_everything(self):
        self.prepare()
        for relative in ("CLAUDE.md", ".mcp.json", ".claude/skills/counter-thesis/SKILL.md",
                         ".claude/skills/tiger-trade-journal/scripts/journal.py"):
            path = self.product/relative
            original = ("link", os.readlink(path)) if path.is_symlink() else ("file", path.read_bytes())
            path.unlink()
            path.write_text("USER_EDIT")
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, "TARGET_DRIFT"):
                self.prepare()
            self.assertEqual(before, self.snapshot())
            path.unlink()
            if original[0] == "link":
                path.symlink_to(original[1])
            else:
                path.write_bytes(original[1])

    def test_legacy_mcp_requires_exact_reviewed_hash_and_is_not_a_refresh_override(self):
        path = self.product/".mcp.json"
        raw = b'{"mcpServers":{"legacy":{"command":"never-start"}}}\n'
        path.write_bytes(raw)
        before = self.snapshot()
        for digest in (None, "a"*64):
            with self.assertRaisesRegex(ValueError, "TARGET_CONFLICT"):
                self.prepare(migrate_mcp_sha256=digest)
            self.assertEqual(before, self.snapshot())
        self.prepare(migrate_mcp_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(json.loads(path.read_bytes()), {"mcpServers": {}})
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "MCP_ALREADY_MANAGED"):
            self.prepare(migrate_mcp_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(before, self.snapshot())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlink_roots_sources_and_destination_parents_or_leaves_reject(self):
        link = self.base/"linked-repo"
        link.symlink_to(self.repo, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "ROOT_UNSAFE"):
            prepare_claude_workspace(link, reviewed_file_hashes=self.hashes, python_interpreter=sys.executable)
        for relative in (".claude", "CLAUDE.md", ".mcp.json"):
            path = self.product/relative
            path.symlink_to(self.base/"outside")
            before = self.snapshot()
            with self.assertRaises(ValueError):
                self.prepare()
            self.assertEqual(before, self.snapshot())
            path.unlink()
        path = self.product/"skills/valuation/SKILL.md"
        path.unlink()
        path.symlink_to(self.base/"outside")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "SOURCE_UNSAFE"):
            self.prepare()
        self.assertEqual(before, self.snapshot())

    def test_invalid_connection_scope_and_interpreter_reject_before_discovery(self):
        for files in ({}, ["company"], {"other":str(self.base/"private.json")}, {"company":"relative"},
                      {"company":str(self.repo/"secret.json")}):
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.prepare(claude_connection_files=files)
            self.assertFalse((self.product/"CLAUDE.md").exists())
        with self.assertRaisesRegex(ValueError, "INTERPRETER_MUST_BE_EXPLICIT"):
            prepare_claude_workspace(self.repo, reviewed_file_hashes=self.hashes, python_interpreter="python3")

    def test_missing_attachment_rejects_before_discovery(self):
        del self.hashes["product/skills/trading-reflection/references/report-format.md"]
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "CONTENT_INCOMPLETE"):
            self.prepare()
        self.assertEqual(before, self.snapshot())

    def test_registry_cannot_claim_files_outside_the_discovery_set(self):
        self.prepare()
        path = self.product/".claude/native-product.json"
        record = json.loads(path.read_bytes())
        record["files"]["../business.py"] = {"sha256":"a"*64}
        path.write_text(json.dumps(record))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "FILE_SET_CHANGED"):
            self.prepare()
        self.assertEqual(before, self.snapshot())

    def test_cli_in_place_has_no_target_copy_and_rejects_other_hosts(self):
        manifest = self.base/"reviewed-files.json"
        manifest.write_text(json.dumps(self.hashes))
        command = [sys.executable, "-B", "-m", "product.tools.package_content", "--source", str(self.repo),
                   "--in-place", "--reviewed-files", str(manifest), "--python", sys.executable]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        rejected = subprocess.run([*command, "--host", "codex"], cwd=ROOT, env=env,
                                  text=True, capture_output=True, timeout=10)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse((self.product/"CLAUDE.md").exists())
        result = subprocess.run([*command, "--host", "claude-code"], cwd=ROOT, env=env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "PREPARED_NOT_LOAD_VERIFIED")
        self.assertFalse((self.repo/"native-package-export.json").exists())
