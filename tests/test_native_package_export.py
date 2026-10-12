"""精确候选导出/隔离检查；输出仅是合成安装候选，不切换真实安装。"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from product.tools.package_content import export_package, verify_export, PUBLIC_PREPARATION_RESOURCES

ROOT = Path(__file__).resolve().parents[1]


def candidate_sources():
    """测试用显式基线+本Change源；不把并行Tiger导出注册作为已审阅来源。"""
    result = {}
    def read(name):
        if name == "product/intake/__init__.py":
            return subprocess.check_output(["git", "show", "HEAD:"+name], cwd=ROOT)
        return (ROOT/name).read_bytes()
    queue = ["product/mcp/research.py", "product/tools/report_history.py", "product/trading_journal/cli.py",
             "product/tools/prepare.py", "product/tools/material_preparation.py",
             "product/contracts/council-decision-contract.json",
             "product/deterministic/risk.py", "product/deterministic/policy.py"]
    queue.extend(sorted(PUBLIC_PREPARATION_RESOURCES))
    queue.extend("evals/fixtures/codex-native/"+name for name in (
        "normal-research.json", "insufficient-evidence.json", "evidence-conflict.json", "future-or-stale.json", "risk-veto.json", "invalid-portfolio.json"))
    for directory in (ROOT/"product/agents", ROOT/"product/hosts", ROOT/"product/skills", ROOT/"product/schemas", ROOT/"product/trading_journal"):
        for path in directory.rglob("*"):
            if (path.is_file() and "__pycache__" not in path.parts and not path.is_symlink()
                    and not path.is_relative_to(ROOT/"product/schemas/broker")):
                queue.append(str(path.relative_to(ROOT)))
    queue.extend(["product/AGENTS.md", "product/version-manifest.json", "product/model-routing.json", "product/runtime-profile.json"])
    while queue:
        name = queue.pop()
        if name in result:
            continue
        result[name] = read(name)
        if not name.endswith(".py") or name.startswith("product/skills/"):
            continue
        module = name.removesuffix(".py").replace("/", ".")
        package = module.removesuffix(".__init__") if module.endswith(".__init__") else module.rsplit(".",1)[0]
        for node in ast.walk(ast.parse(result[name])):
            imports = []
            if isinstance(node, ast.Import):
                imports = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split(".")[:len(package.split("."))-node.level+1]
                    imports = [".".join([*parts, *([node.module] if node.module else [])])]
                else:
                    imports = [node.module or ""]
            for imported in imports:
                if not (imported == "product" or imported.startswith("product.")):
                    continue
                relative = imported.replace(".","/")
                file = relative+".py" if (ROOT/(relative+".py")).is_file() else relative+"/__init__.py"
                queue.append(file)
                parts=relative.split("/")
                queue.extend("/".join(parts[:i])+"/__init__.py" for i in range(1,len(parts)))
    return result


class NativePackageExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = candidate_sources()
        assert not any(Path(name).name in {"nested_codex.py", "codex_hook_recorder.py"} for name in cls.sources)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.source = self.root/"reviewed-source"
        self.source.mkdir()
        for name, raw in self.sources.items():
            path = self.source/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
        self.hashes = {name:hashlib.sha256(raw).hexdigest() for name,raw in self.sources.items()}

    def tearDown(self):
        self.tmp.cleanup()

    def export(self, host):
        target = self.root/(host+" package")
        result = export_package(self.source,target,host=host,reviewed_file_hashes=self.hashes,
                                python_interpreter=sys.executable)
        return target,result

    def test_three_exports_expand_one_body_keep_business_imports_and_trading_sources(self):
        for host in ("codex", "claude-code", "opencode"):
            target,result = self.export(host)
            verify_export(target,result)
            self.assertEqual(result["status"],"EXPORTED_NOT_INSTALLED")
            self.assertEqual(result["host_execution"],"UNVERIFIED")
            script = 'import sys; import product.mcp.research as m; import product.tools.prepare; import product.tools.material_preparation; from pathlib import Path; assert Path(m.__file__).resolve().is_relative_to(Path.cwd()); assert not any(k in sys.modules for k in ("product.runtime.nested_codex", "product.runtime.codex_hook_recorder", "product.runtime.fixture_mcp", "product.runtime.common_stock_data", "product.runtime.live_input", "product.runtime.live_context")); print("BUSINESS_AND_OPERATOR_IMPORT_OK")'
            env = dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(target))
            run = subprocess.run([sys.executable,"-B","-c",script],cwd=target,env=env,text=True,capture_output=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            from tests.test_single_stock_input import alb_request
            from tests.test_native_research_tools import frozen_gate, SECURITY
            packet = self.root/(host+"-synthetic-input.json")
            packet.write_text(json.dumps({"input": alb_request(), "gate": frozen_gate()}))
            script = ('import json,sys; from pathlib import Path; from product.tools.research import prepare_task,ResearchTools; '
                      'p=json.loads(Path(sys.argv[1]).read_text()); '
                      't=prepare_task(Path(sys.argv[2]),research_input=p["input"],gate=p["gate"],security_id=sys.argv[3],capability="COMPANY_RESEARCH"); '
                      'tools=ResearchTools(Path(sys.argv[2]),access_token=t["access_token"]); '
                      'assert tools.query(evidence_ids=["ev-revenue"])["evidence"][0]["value"]=="100"; '
                      'print("EXPORTED_TASK_QUERY_OK_NOT_HOST_EXECUTION")')
            prepared = subprocess.run([sys.executable,"-B","-c",script,str(packet),str(self.root/(host+"-task")),SECURITY],
                                      cwd=target,env=env,text=True,capture_output=True,timeout=10)
            self.assertEqual(prepared.returncode,0,prepared.stderr)
            for name in self.sources:
                if name.startswith("product/trading_journal/"):
                    self.assertEqual((target/name).read_bytes(),self.sources[name])
            if host == "codex":
                import tomllib
                text=(target/".codex/agents/runtime_skeptic.toml").read_text()
                self.assertEqual(tomllib.loads(text)["developer_instructions"].strip(),self.sources["product/agents/runtime_skeptic.md"].decode().strip())
            elif host == "claude-code":
                text=(target/".claude/agents/runtime_skeptic.md").read_text()
                self.assertIn(self.sources["product/agents/runtime_skeptic.md"].decode(),text)

    def test_claude_root_loads_exact_reviewed_host_guidance_without_changing_other_host_roots(self):
        guide = self.sources["product/hosts/claude-code/main-thread.md"]
        for host in ("claude-code", "codex", "opencode"):
            target, result = self.export(host)
            verify_export(target, result)
            if host == "claude-code":
                expected = (self.sources["product/AGENTS.md"] + b"\n" + guide + b"\n"
                            + self.sources["product/agents/runtime_cio.md"])
                self.assertEqual((target/"CLAUDE.md").read_bytes(), expected)
                self.assertFalse((target/".git").exists())
                import re
                example = re.search(rb"```json\n(.*?)\n```", guide, re.DOTALL)
                call_shape = json.loads(example.group(1))
                self.assertEqual(set(call_shape), {"skill", "args"})
                self.assertEqual(call_shape["skill"], "company-native")
                from tests.test_native_host_templates import frontmatter
                for role in ("runtime_company_analyst", "runtime_market_catalyst", "runtime_skeptic"):
                    original = frontmatter(self.source/f"product/hosts/claude-code/agents/{role}.md")
                    scalars, lists, body = frontmatter(target/f".claude/agents/{role}.md")
                    self.assertEqual(scalars, original[0])
                    self.assertEqual(lists, original[1])
                    self.assertEqual(body.strip(), self.sources[f"product/agents/{role}.md"].decode().strip())
            elif host == "codex":
                self.assertEqual((target/"AGENTS.md").read_bytes(), self.sources["product/AGENTS.md"]
                                 + b"\n" + self.sources["product/agents/runtime_cio.md"])
                self.assertFalse((target/"CLAUDE.md").exists())
            else:
                self.assertEqual((target/"opencode.json").read_text(),
                    self.sources["product/hosts/opencode/opencode.json"].decode()
                    .replace("{{PYTHON}}", json.dumps(sys.executable)[1:-1])
                    .replace("{{REPOSITORY_ROOT}}", json.dumps(str(target))[1:-1]))
                self.assertFalse((target/"CLAUDE.md").exists())

    def test_missing_or_drifted_claude_guidance_rejects_before_export_and_keeps_old_package(self):
        guide_name = "product/hosts/claude-code/main-thread.md"
        old_target, old_export = self.export("claude-code")
        old_root = (old_target/"CLAUDE.md").read_bytes()
        reviewed = {name: digest for name, digest in self.hashes.items() if name != guide_name}
        target = self.root/"missing-main-thread"
        with self.assertRaisesRegex(ValueError, "MAIN_THREAD_INSTRUCTIONS_MISSING"):
            export_package(self.source, target, host="claude-code", reviewed_file_hashes=reviewed,
                           python_interpreter=sys.executable)
        self.assertFalse(target.exists())
        guide_path = self.source/guide_name
        guide_path.write_text("UNREVIEWED_GUIDANCE")
        target = self.root/"drifted-main-thread"
        with self.assertRaisesRegex(ValueError, "REVIEWED_SOURCE_DRIFT"):
            export_package(self.source, target, host="claude-code", reviewed_file_hashes=self.hashes,
                           python_interpreter=sys.executable)
        self.assertFalse(target.exists())
        verify_export(old_target, old_export)
        self.assertEqual((old_target/"CLAUDE.md").read_bytes(), old_root)
        guide_path.write_bytes(self.sources[guide_name])
        recovered = self.root/"restored-main-thread"
        result = export_package(self.source, recovered, host="claude-code", reviewed_file_hashes=self.hashes,
                                python_interpreter=sys.executable)
        verify_export(recovered, result)
        self.assertEqual((recovered/"CLAUDE.md").read_bytes(), old_root)
        # Other hosts do not require Claude-only operating instructions.
        for host in ("codex", "opencode"):
            target = self.root/(host+"-without-claude-guidance")
            result = export_package(self.source, target, host=host, reviewed_file_hashes=reviewed,
                                    python_interpreter=sys.executable)
            verify_export(target, result)

    def test_company_native_skill_is_exactly_installed_only_for_claude(self):
        name = "product/hosts/claude-code/skills/company-native/SKILL.md"
        for host in ("claude-code", "codex", "opencode"):
            target, exported = self.export(host)
            verify_export(target, exported)
            destination = target/".claude/skills/company-native/SKILL.md"
            if host == "claude-code":
                self.assertEqual(destination.read_bytes(), self.sources[name])
                from tests.test_native_host_templates import frontmatter
                header, _, body = frontmatter(destination)
                role = target/".claude/agents"/(header["agent"]+".md")
                self.assertTrue(role.is_file())
                self.assertEqual(frontmatter(role)[0]["model"], "inherit")
                self.assertIn("$ARGUMENTS", body)
            else:
                self.assertFalse(destination.exists())
            self.assertFalse((target/".agents/skills/company-native").exists())
            self.assertEqual(exported["host_execution"], "UNVERIFIED")

    def test_company_native_skill_missing_drift_and_collision_reject_before_write_and_recover(self):
        name = "product/hosts/claude-code/skills/company-native/SKILL.md"
        old, old_export = self.export("claude-code")
        reviewed = {path: digest for path, digest in self.hashes.items() if path != name}
        target = self.root/"missing-company-native"
        with self.assertRaisesRegex(ValueError, "COMPANY_NATIVE_SKILL_MISSING"):
            export_package(self.source, target, host="claude-code", reviewed_file_hashes=reviewed,
                           python_interpreter=sys.executable)
        self.assertFalse(target.exists())
        for host in ("codex", "opencode"):
            target = self.root/(host+"-without-company-native")
            result = export_package(self.source, target, host=host, reviewed_file_hashes=reviewed,
                                    python_interpreter=sys.executable)
            verify_export(target, result)
        path = self.source/name
        path.write_text("UNREVIEWED_SKILL")
        target = self.root/"drifted-company-native"
        with self.assertRaisesRegex(ValueError, "REVIEWED_SOURCE_DRIFT"):
            export_package(self.source, target, host="claude-code", reviewed_file_hashes=self.hashes,
                           python_interpreter=sys.executable)
        self.assertFalse(target.exists())
        verify_export(old, old_export)
        path.write_bytes(self.sources[name])
        for filename in ("SKILL.md", "notes.txt"):
            conflict = "product/skills/company-native/"+filename
            conflict_path = self.source/conflict
            conflict_path.parent.mkdir(parents=True, exist_ok=True)
            conflict_path.write_text("SYNTHETIC_SHARED_SKILL_COLLISION")
            hashes = {**self.hashes, conflict: hashlib.sha256(conflict_path.read_bytes()).hexdigest()}
            target = self.root/("collision-"+filename)
            with self.assertRaisesRegex(ValueError, "COMPANY_NATIVE_SKILL_CONFLICT"):
                export_package(self.source, target, host="claude-code", reviewed_file_hashes=hashes,
                               python_interpreter=sys.executable)
            self.assertFalse(target.exists())
            verify_export(old, old_export)
        target = self.root/"restored-company-native"
        restored = export_package(self.source, target, host="claude-code", reviewed_file_hashes=self.hashes,
                                  python_interpreter=sys.executable)
        verify_export(target, restored)
        self.assertEqual((target/".claude/skills/company-native/SKILL.md").read_bytes(),
                         (old/".claude/skills/company-native/SKILL.md").read_bytes())
        self.assertEqual(restored["exported_files"], old_export["exported_files"] | {
            ".mcp.json": restored["exported_files"][".mcp.json"]})

    def test_market_skeptic_native_exact_export_and_all_rejections_before_target_creation(self):
        old, old_export = self.export("claude-code")
        for role in ("market", "skeptic"):
            name = f"product/hosts/claude-code/skills/{role}-native/SKILL.md"
            installed = f".claude/skills/{role}-native/SKILL.md"
            self.assertEqual((old/installed).read_bytes(), self.sources[name])
            reviewed = {path: digest for path, digest in self.hashes.items() if path != name}
            target = self.root/("missing-"+role)
            with self.assertRaisesRegex(ValueError, role.upper()+"_NATIVE_SKILL_MISSING"):
                export_package(self.source, target, host="claude-code", reviewed_file_hashes=reviewed,
                               python_interpreter=sys.executable)
            self.assertFalse(target.exists())
            for host in ("codex", "opencode"):
                target = self.root/(host+"-without-"+role)
                result = export_package(self.source, target, host=host, reviewed_file_hashes=reviewed,
                                        python_interpreter=sys.executable)
                verify_export(target, result)
                self.assertFalse((target/installed).exists())
            (self.source/name).write_text("UNREVIEWED_NATIVE_SKILL")
            target = self.root/("drifted-"+role)
            with self.assertRaisesRegex(ValueError, "REVIEWED_SOURCE_DRIFT"):
                export_package(self.source, target, host="claude-code", reviewed_file_hashes=self.hashes,
                               python_interpreter=sys.executable)
            self.assertFalse(target.exists())
            (self.source/name).write_bytes(self.sources[name])
            for filename in ("SKILL.md", "notes.txt"):
                conflict = f"product/skills/{role}-native/{filename}"
                path = self.source/conflict
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("SYNTHETIC_SHARED_SKILL_COLLISION")
                hashes = {**self.hashes, conflict: hashlib.sha256(path.read_bytes()).hexdigest()}
                target = self.root/("collision-"+role+"-"+filename)
                with self.assertRaisesRegex(ValueError, role.upper()+"_NATIVE_SKILL_CONFLICT"):
                    export_package(self.source, target, host="claude-code", reviewed_file_hashes=hashes,
                                   python_interpreter=sys.executable)
                self.assertFalse(target.exists())
                verify_export(old, old_export)
        restored = self.root/"restored-three-native-skills"
        result = export_package(self.source, restored, host="claude-code", reviewed_file_hashes=self.hashes,
                                python_interpreter=sys.executable)
        verify_export(restored, result)
        for role in ("company", "market", "skeptic"):
            name = f".claude/skills/{role}-native/SKILL.md"
            self.assertEqual((restored/name).read_bytes(), (old/name).read_bytes())

    def test_parent_tool_filters_survive_export_and_source_rejection(self):
        from tests.test_native_host_templates import frontmatter
        name = "product/hosts/claude-code/agents/runtime_company_analyst.md"
        target, exported = self.export("claude-code")
        role_path = target/".claude/agents/runtime_company_analyst.md"
        original = role_path.read_bytes()
        mcp = json.loads((target/".mcp.json").read_text())["mcpServers"]
        for role, server, count in (("runtime_company_analyst", "company", 11),
                                    ("runtime_market_catalyst", "market", 11),
                                    ("runtime_skeptic", "skeptic", 5)):
            scalars, limits, _ = frontmatter(target/f".claude/agents/{role}.md")
            _, source_limits, _ = frontmatter(self.source/f"product/hosts/claude-code/agents/{role}.md")
            self.assertEqual(limits, source_limits)
            self.assertEqual(set(limits), {"tools", "skills"})
            self.assertNotIn("mcpServers", scalars)
            self.assertEqual(scalars["model"], "inherit")
            self.assertIn(server, mcp)
            self.assertEqual(len(limits["tools"]), count)
            self.assertTrue(all(tool.startswith(f"mcp__{server}__research_") for tool in limits["tools"]))
        missing = {path: digest for path, digest in self.hashes.items() if path != name}
        rejected = self.root/"missing-company-role"
        with self.assertRaisesRegex(ValueError, "TEMPLATE_MISSING"):
            export_package(self.source, rejected, host="claude-code", reviewed_file_hashes=missing,
                           python_interpreter=sys.executable)
        self.assertFalse(rejected.exists())
        (self.source/name).write_text("UNREVIEWED_ROLE")
        rejected = self.root/"drifted-company-role"
        with self.assertRaisesRegex(ValueError, "REVIEWED_SOURCE_DRIFT"):
            export_package(self.source, rejected, host="claude-code", reviewed_file_hashes=self.hashes,
                           python_interpreter=sys.executable)
        self.assertFalse(rejected.exists())
        verify_export(target, exported)
        self.assertEqual(role_path.read_bytes(), original)

    def test_desktop_project_mcp_reads_private_file_without_cli_auth_or_environment_injection(self):
        from product.tools.research import _write_json
        from tests.test_single_stock_input import alb_request
        from tests.test_native_research_tools import frozen_gate, SECURITY
        private = self.root/"desktop-private"; private.mkdir(mode=0o700)
        filename = private/"connections.json"
        target = self.root/"desktop-package"
        result = export_package(self.source,target,host="claude-code",reviewed_file_hashes=self.hashes,
                                python_interpreter=sys.executable,claude_connection_files={"company":str(filename)})
        config = json.loads((target/".mcp.json").read_text())
        self.assertEqual(set(config["mcpServers"]),{"company"})
        server = config["mcpServers"]["company"]
        self.assertEqual(server["args"][-2:],["--connection-env-file",str(filename)])
        self.assertEqual(server["env"],{"PYTHONPATH":str(target)})
        self.assertNotIn("${STOCK_AGENT_",(target/".mcp.json").read_text())
        self.assertFalse(filename.exists())  # Export does not read or create a private credential file.
        original, gate = private/"input.json", private/"gate.json"
        _write_json(original,alb_request()); _write_json(gate,frozen_gate())
        connection, grant = private/"company", private/"task-grant.json"
        environment = {k:v for k,v in os.environ.items() if not k.startswith("STOCK_AGENT_")}
        environment.update(PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(target))
        command = [sys.executable,"-B","-m","product.tools.prepare"]
        created = subprocess.run([*command,"connection","--input",str(original),"--gate",str(gate),
            "--role","runtime_company_analyst","--root",str(connection)],cwd=target,env=environment,
            text=True,capture_output=True,timeout=10)
        self.assertEqual(created.returncode,0,created.stderr)
        token = json.loads((connection/"operator-grant.json").read_text())["connection_token"]
        _write_json(filename,{"STOCK_AGENT_COMPANY_CONNECTION":str(connection),"STOCK_AGENT_COMPANY_TOKEN":token})
        prepared = subprocess.run([*command,"task","--connection-root",str(connection),
            "--connection-access",str(connection/"operator-grant.json"),"--security-id",SECURITY,
            "--capability","COMPANY_RESEARCH","--grant-output",str(grant)],cwd=target,env=environment,
            text=True,capture_output=True,timeout=10)
        self.assertEqual(prepared.returncode,0,prepared.stderr)
        task = json.loads(grant.read_text())
        messages = [{"jsonrpc":"2.0","id":1,"method":"tools/list"}]
        for number,task_token in ((2,"x"*43),(3,task["task_token"])):
            messages.append({"jsonrpc":"2.0","id":number,"method":"tools/call","params":{
                "name":"research_query","arguments":{"task_ref":task["task_ref"],"task_token":task_token,
                "evidence_ids":["ev-revenue"]}}})
        environment.update(server["env"])
        run = subprocess.run([server["command"],*server["args"]],cwd=self.root,env=environment,
            input="".join(json.dumps(m)+"\n" for m in messages),text=True,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        replies = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertTrue(replies[1]["result"]["isError"])
        self.assertFalse(replies[2]["result"]["isError"])
        self.assertNotIn(token,run.stdout+run.stderr)
        self.assertNotIn(task["task_token"],run.stdout+run.stderr)
        self.assertTrue(all(token.encode() not in p.read_bytes() for p in target.rglob("*") if p.is_file()))
        verify_export(target,result)

    def test_desktop_bindings_reject_unknown_services_relative_and_source_paths_before_export(self):
        cases = [("codex",{"company":str(self.root/"private.json")}),
                 ("opencode",{"company":str(self.root/"private.json")}),
                 ("claude-code",{}),("claude-code",["company"]),
                 ("claude-code",{"other":str(self.root/"private.json")}),
                 ("claude-code",{"company":"relative.json"}),
                 ("claude-code",{"company":str(self.source/"private.json")}),
                 ("claude-code",{"company":str(self.root/"invalid-desktop"/"private.json")})]
        for host,files in cases:
            with self.subTest(host=host,files=files):
                target = self.root/"invalid-desktop"
                with self.assertRaises(ValueError):
                    export_package(self.source,target,host=host,reviewed_file_hashes=self.hashes,
                                   python_interpreter=sys.executable,claude_connection_files=files)
                self.assertFalse(target.exists())

    def test_missing_operator_or_material_entry_rejects_before_candidate_creation(self):
        for name in ("product/tools/prepare.py", "product/tools/material_preparation.py"):
            reviewed = {path: digest for path, digest in self.hashes.items() if path != name}
            target = self.root/"missing-operator"
            with self.assertRaisesRegex(ValueError, "REVIEWED_CONTENT_INCOMPLETE"):
                export_package(self.source,target,host="claude-code",reviewed_file_hashes=reviewed,python_interpreter=sys.executable)
            self.assertFalse(target.exists())

    def test_exported_operator_cli_creates_bound_connection_and_task_without_model(self):
        from tests.test_single_stock_input import alb_request
        from tests.test_native_research_tools import frozen_gate, SECURITY
        from product.tools.research import _write_json
        target, exported = self.export("claude-code")
        source = self.root/"input.json"; gate = self.root/"gate.json"
        source.write_text(json.dumps(alb_request())); gate.write_text(json.dumps(frozen_gate()))
        connection = self.root/"operator-connection"; grant = self.root/"task-grant.json"
        environment = dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(target))
        command = [sys.executable,"-B","-m","product.tools.prepare"]
        created = subprocess.run([*command,"connection","--input",str(source),"--gate",str(gate),
            "--role","runtime_company_analyst","--root",str(connection)],cwd=target,env=environment,text=True,capture_output=True,timeout=10)
        self.assertEqual(created.returncode,0,created.stderr)
        prepared = subprocess.run([*command,"task","--connection-root",str(connection),"--connection-access",str(connection/"operator-grant.json"),
            "--security-id",SECURITY,"--capability","COMPANY_RESEARCH","--grant-output",str(grant)],
            cwd=target,env=environment,text=True,capture_output=True,timeout=10)
        self.assertEqual(prepared.returncode,0,prepared.stderr)
        value = json.loads(grant.read_text())
        self.assertEqual(value["task"]["security"]["security_id"],SECURITY)
        self.assertEqual(json.loads(prepared.stdout)["model_calls"],0)
        self.assertNotIn(value["task_token"],prepared.stdout)
        self.assertEqual(grant.stat().st_mode & 0o777,0o600)
        verify_export(target,exported)
        wrong = self.root/"wrong-access.json"
        _write_json(wrong,{"connection_token":"wrong-private-token"})
        rejected = subprocess.run([*command,"task","--connection-root",str(connection),"--connection-access",str(wrong),
            "--security-id",SECURITY,"--capability","COMPANY_RESEARCH","--grant-output",str(self.root/"rejected.json")],
            cwd=target,env=environment,text=True,capture_output=True,timeout=10)
        self.assertNotEqual(rejected.returncode,0)
        self.assertFalse((self.root/"rejected.json").exists())

    def test_exported_material_operator_reuses_frozen_peer_without_controller_or_provider_call(self):
        from product.mcp.live.peer_candidates import build_peer_candidate_pool
        from product.runtime.hashing import canonical_hash, legacy_envelope_hash
        from tests.test_single_stock_input import alb_request
        from tests.test_native_research_tools import frozen_gate, SECURITY, AT
        rows = [{"symbol":symbol,"name":symbol,"market_cap":"100","country":"United States","ipo_year":2000,
                 "sector":"Synthetic Sector","industry":"Synthetic Industry","source_id":"nasdaq-screener",
                 "as_of":AT,"retrieved_at":AT,"raw_content_hash":"a"*64} for symbol in ("ALB","PEER1")]
        universe = {"schema_version":"live-universe/1.0.0","provider":"nasdaq","source_id":"nasdaq-screener",
            "source_locator":"https://api.nasdaq.com/api/screener/stocks","request_started_at":AT,"as_of":AT,
            "retrieved_at":AT,"completeness":"COMPLETE","rows":rows,"snapshot_hash":canonical_hash({"rows":rows,"as_of":AT})}
        pool = build_peer_candidate_pool([{"security_id":SECURITY,"ticker":"ALB"}],universe=universe)
        gate = frozen_gate()
        peer = {"evidence_id":"peer-revenue","security_id":"US:COMMON_STOCK:PEER1","semantic_field":"revenue",
                "value":"80","unit":"USD","source_id":"synthetic-sec","source_type":"sec","as_of":AT,"retrieved_at":AT}
        gate["allowed_evidence"].append(peer); gate["allowed_evidence_ids"].append(peer["evidence_id"])
        gate["bundle_hash"] = legacy_envelope_hash(gate,hash_field="bundle_hash")
        packet = self.root/"peer-input.json"
        packet.write_text(json.dumps({"input":alb_request(),"gate":gate,"pool":pool}))
        access = self.root/"source-access.json"
        access.write_text(json.dumps([{"operator_approval":{"record":{"scope":{"max_positions":3}}}}]))
        target, exported = self.export("claude-code")
        script = '''import json,sys
from pathlib import Path
from product.tools.research import prepare_task,ResearchTools
from product.tools.material_preparation import materialize_peer_selection
p=json.loads(Path(sys.argv[1]).read_text()); base=Path(sys.argv[2])
t=prepare_task(base/'peer-task',research_input=p['input'],gate=p['gate'],security_id='US:COMMON_STOCK:ALB',capability='PEER_SELECTION',peer_candidate_pool=p['pool'])
tools=ResearchTools(base/'peer-task',access_token=t['access_token']); candidate=tools.context()['peer_candidates'][0]
saved=tools.submit(draft={'status':'READY','summary':'合成接缝，不是研究结论。','query_intents':[],'selections':[{'candidate_id':candidate['candidate_id'],'document_id':None,'rationale':'仅验证已有选择的机械物化'}],'gaps':[]})
assert saved['accepted'],saved
def forbidden(*args,**kwargs):raise AssertionError('No provider request is allowed')
result=materialize_peer_selection(tools,draft_ref=saved['draft_ref'],output_dir=base/'materialized',source_access_path=Path(sys.argv[3]),cache_root=base/'cache',sec_user_agent='synthetic',collector=forbidden)
assert result['materialization']['status']=='FROZEN',result
assert not any(k in sys.modules for k in ('product.runtime.nested_codex','product.runtime.codex_hook_recorder','product.runtime.common_stock_data','product.runtime.multidimensional_stage','product.runtime.research_materials_stage'))
print('EXPORTED_FROZEN_PEER_REUSE_OK_NOT_HOST_EXECUTION')
'''
        result = subprocess.run([sys.executable,"-B","-c",script,str(packet),str(self.root),str(access)],
            cwd=target,env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(target)),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        verify_export(target,exported)

    def test_missing_public_policy_resource_rejects_before_export(self):
        for name in sorted(PUBLIC_PREPARATION_RESOURCES):
            hashes = {path:digest for path,digest in self.hashes.items() if path != name}
            target = self.root/"missing-resource"
            with self.assertRaisesRegex(ValueError,"REVIEWED_CONTENT_INCOMPLETE"):
                export_package(self.source,target,host="claude-code",reviewed_file_hashes=hashes,python_interpreter=sys.executable)
            self.assertFalse(target.exists())

    def test_exported_public_resource_readers_work_without_source_network(self):
        target,exported = self.export("claude-code")
        script = '''import json
from product.mcp.live.security_metadata import eastmoney_policy
from product.tools.materials import POLICY
from product.mcp.live.research_supplement import load_source_plan
from product.mcp.live.contracts import APPROVAL_RECORD
from product.mcp.live.moomoo_opend import DEFAULT_MANIFEST
policy,_=eastmoney_policy()
assert policy['policy_version']=='eastmoney-us-identity/1.0.0'
assert 'openalex' in json.loads(POLICY.read_text())['sources']
assert load_source_plan()['schema_version']=='research-supplement-source-plan/1.0.0'
assert json.loads(APPROVAL_RECORD.read_text())['approval_id']
assert json.loads(DEFAULT_MANIFEST.read_text())
print('EXPORTED_POLICY_READERS_OK_NO_NETWORK_NO_MODEL')
'''
        result = subprocess.run([sys.executable,"-B","-c",script],cwd=target,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(target)),text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        verify_export(target,exported)

    def test_private_unreviewed_and_unrelated_sentinels_not_copied(self):
        for name in ("product/.private/secret.txt", "product/unreviewed.txt", "other-change.txt"):
            path=self.source/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text("SYNTHETIC_NOT_FOR_EXPORT")
        target,result=self.export("codex")
        self.assertFalse((target/"product/.private").exists())
        self.assertFalse((target/"product/unreviewed.txt").exists())
        self.assertFalse((target/"other-change.txt").exists())
        verify_export(target,result)

    def test_content_drift_missing_dependency_and_existing_target_stop_before_overwrite(self):
        target=self.root/"destination"
        original=self.source/"product/agents/runtime_skeptic.md"
        original.write_text("drift")
        with self.assertRaisesRegex(ValueError,"SOURCE_DRIFT"):
            export_package(self.source,target,host="codex",reviewed_file_hashes=self.hashes,python_interpreter=sys.executable)
        self.assertFalse(target.exists())
        original.write_bytes(self.sources["product/agents/runtime_skeptic.md"])
        missing=dict(self.hashes)
        del missing["product/tools/research.py"]
        with self.assertRaisesRegex(ValueError,"DEPENDENCY_MISSING"):
            export_package(self.source,target,host="codex",reviewed_file_hashes=missing,python_interpreter=sys.executable)
        self.assertFalse(target.exists())
        target.mkdir(); sentinel=target/"existing.txt"; sentinel.write_text("KEEP")
        with self.assertRaisesRegex(ValueError,"TARGET_UNSAFE_OR_EXISTS"):
            export_package(self.source,target,host="codex",reviewed_file_hashes=self.hashes,python_interpreter=sys.executable)
        self.assertEqual(sentinel.read_text(),"KEEP")

    def test_explicit_private_source_and_symlinks_reject(self):
        hashes=dict(self.hashes)
        hashes["product/.private/fake.txt"]="a"*64
        with self.assertRaisesRegex(ValueError,"SOURCE_PATH_FORBIDDEN"):
            export_package(self.source,self.root/"bad",host="codex",reviewed_file_hashes=hashes,python_interpreter=sys.executable)
        link=self.root/"link"; link.symlink_to(self.source,target_is_directory=True)
        with self.assertRaises(ValueError):
            export_package(link,self.root/"bad",host="codex",reviewed_file_hashes=self.hashes,python_interpreter=sys.executable)

    def test_modified_cache_or_file_set_not_an_equivalent_export(self):
        target,result=self.export("claude-code")
        (target/"CLAUDE.md").write_text("drift")
        with self.assertRaisesRegex(ValueError,"CONTENT_DRIFT"):
            verify_export(target,result)
        target2,result2=self.export("opencode")
        (target2/"extra-private.txt").write_text("SYNTHETIC")
        with self.assertRaisesRegex(ValueError,"FILE_SET_DRIFT"):
            verify_export(target2,result2)
