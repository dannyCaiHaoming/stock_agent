"""操作方CLI与相同业务授权接缝；合成输入，零模型/零来源网络。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from product.mcp.live.peer_candidates import build_peer_candidate_pool
from product.tools.research import _write_json
from product.tools.research_connection import prepare_connection, ResearchConnection
from product.tools.report_contracts import semantic_schema
from tests.test_native_research_tools import AT, SECURITY, frozen_gate
from tests.test_single_stock_input import alb_request
from tests.test_multidimensional_research_contracts import _report

ROOT = Path(__file__).resolve().parents[1]


class NativeOperatorPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.temp.name)
        self.environment = dict(os.environ,PYTHONDONTWRITEBYTECODE="1",PYTHONPATH=str(ROOT))

    def tearDown(self):
        self.temp.cleanup()

    def cli_task(self, connection_root, *, capability, grant_output, dependencies=None, agent_grant_output=None):
        command = [sys.executable,"-B","-m","product.tools.prepare","task","--connection-root",str(connection_root),
                   "--connection-access",str(connection_root/"operator-grant.json"),"--security-id",SECURITY,
                   "--capability",capability,"--grant-output",str(grant_output)]
        if dependencies:
            command.extend(["--dependency-grants",str(dependencies)])
        if agent_grant_output is not None:
            command.extend(["--agent-grant-output",str(agent_grant_output)])
        return subprocess.run(command,cwd=ROOT,env=self.environment,text=True,capture_output=True,timeout=10)

    def connection(self, name, role, **options):
        path = self.root/name
        prepared = prepare_connection(path,research_input=alb_request(),gate=frozen_gate(),role=role,**options)
        _write_json(path/"operator-grant.json",prepared)
        return path, ResearchConnection(path,connection_token=prepared["connection_token"])

    def test_agent_grant_is_small_private_exact_and_consumable_without_operator_secret(self):
        from product.mcp.provenance import parse_timestamp
        from tests.test_native_research_submission import company_draft
        path, connection = self.connection("agent-company", "runtime_company_analyst")
        full, compact = self.root/"full.json", self.root/"agent.json"
        result = self.cli_task(path, capability="COMPANY_RESEARCH", grant_output=full, agent_grant_output=compact)
        self.assertEqual(result.returncode, 0, result.stderr)
        original, packet = json.loads(full.read_text()), json.loads(compact.read_text())
        legacy_keys = {"source_id", "as_of", "retrieved_at", "task_ref", "task_token",
                       "role", "capability", "security_id", "decision_cutoff", "task_hash"}
        self.assertEqual(set(packet), legacy_keys)
        self.assertLess(compact.stat().st_size, 1024)
        self.assertEqual(compact.stat().st_mode & 0o777, 0o600)
        self.assertEqual(packet["task_ref"], original["task_ref"])
        self.assertEqual(packet["task_token"], original["task_token"])
        self.assertEqual(packet["task_hash"], original["task"]["task_hash"])
        self.assertEqual(packet["as_of"], original["task"]["decision_cutoff"])
        self.assertGreaterEqual(parse_timestamp(packet["retrieved_at"]), parse_timestamp(packet["as_of"]))
        self.assertNotIn(connection.connection_token, compact.read_text())
        self.assertNotIn(packet["task_token"], result.stdout + result.stderr)
        self.assertNotIn(connection.connection_token, result.stdout + result.stderr)
        tools = connection.task_tools(task_ref=packet["task_ref"], task_token=packet["task_token"])
        context = tools.context()
        self.assertEqual(context["role"], packet["role"])
        self.assertEqual(context["capability"], packet["capability"])
        self.assertEqual(context["security"]["security_id"], packet["security_id"])
        tools.query(evidence_ids=["ev-revenue"])
        from product.mcp.research import dispatch
        response = dispatch(connection, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "research_submit", "arguments": {
                                **{key: packet[key] for key in ("task_ref", "task_token")}, "draft": company_draft()}}})
        self.assertFalse(response["result"]["isError"], response)
        receipt = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(receipt["accepted"], receipt)
        self.assertEqual(full.read_bytes(), json.dumps(original, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode() + b"\n")

    def test_derived_agent_arguments_preserve_exact_values_and_exclude_full_task_secrets(self):
        import runpy
        agent_grant = runpy.run_path(str(ROOT/"scripts/prepare-native-agent-grant.py"))["enriched_agent_grant"]
        for role, capability in (("runtime_company_analyst", "COMPANY_RESEARCH"),
                                 ("runtime_market_catalyst", "TECHNICAL_STRUCTURE"),
                                 ("runtime_skeptic", "COUNTER_THESIS"),
                                 ("runtime_cio", "CIO_SYNTHESIS")):
            with self.subTest(role=role):
                grant = {"task_ref": "t." + "a"*24, "task_token": 'opaque"\\\n' + "x"*40,
                         "connection_token": "operator-only-secret", "task": {
                             "role": role, "capability": capability, "decision_cutoff": AT,
                             "security": {"security_id": SECURITY}, "task_hash": "a"*64,
                             "allowed_evidence_ids": ["private-fact-id"],
                             "dependency_reports": [{"secret": "other-role-conclusion"}]}}
                original = copy.deepcopy(grant)
                packet = agent_grant(grant)
                decoded = json.loads(packet["specialist_args"])
                self.assertEqual(grant, original)
                self.assertEqual(packet["mcp_arguments"], {key: grant[key] for key in ("task_ref", "task_token")})
                self.assertEqual(decoded, {key: value for key, value in packet.items()
                                           if key not in {"mcp_arguments", "specialist_args"}})
                self.assertEqual(decoded["task_token"], grant["task_token"])
                self.assertEqual(decoded["role"], role)
                self.assertEqual(decoded["capability"], capability)
                for secret in ("operator-only-secret", "private-fact-id", "other-role-conclusion"):
                    self.assertNotIn(secret, json.dumps(packet))
                self.assertNotIn("task", decoded)
                self.assertNotIn("skill", decoded)
                self.assertNotIn("agent", decoded)

    def test_existing_task_handoff_cli_preserves_locks_and_rejects_before_output(self):
        import contextlib
        import io
        import runpy
        from unittest.mock import patch
        module = runpy.run_path(str(ROOT/"scripts/prepare-native-agent-grant.py"))
        path, connection = self.connection("handoff-company", "runtime_company_analyst")
        full, compact = self.root/"full.json", self.root/"compact.json"
        self.assertEqual(self.cli_task(path, capability="COMPANY_RESEARCH", grant_output=full,
                                      agent_grant_output=compact).returncode, 0)
        original = json.loads(compact.read_text())
        task_root = path/"tasks"/original["task_ref"]
        before = {p.relative_to(path): p.read_bytes() for p in path.rglob("*") if p.is_file()}
        output = self.root/"handoff.json"
        def run(grant=compact, target=output, root=task_root):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = module["main"](["--task-root", str(root), "--agent-grant", str(grant), "--output", str(target)])
            self.assertNotIn(original["task_token"], stdout.getvalue()+stderr.getvalue())
            self.assertNotIn(connection.connection_token, stdout.getvalue()+stderr.getvalue())
            return code
        public = self.root/"public-handoff"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        linked = self.root/"linked.json"
        linked.symlink_to(compact)
        for target in (Path("relative.json"), ROOT/"unapproved-handoff.json", public/"out.json", compact, linked):
            self.assertEqual(run(target=target), 1)
        for key, value in (("task_token", "x"*43), ("task_hash", "a"*64), ("role", "runtime_skeptic")):
            wrong = self.root/(key+".json")
            _write_json(wrong, {**original, key: value})
            self.assertEqual(run(grant=wrong), 1)
            self.assertFalse(output.exists())
        self.assertEqual(run(root=path/"tasks"/("t."+"b"*24)), 1)
        with patch("product.tools.resource_bindings.resource_bindings", return_value={}):
            self.assertEqual(run(), 1)
            self.assertFalse(output.exists())
        self.assertEqual(run(), 0)
        packet = json.loads(output.read_text())
        self.assertEqual(packet["mcp_arguments"], {key: original[key] for key in ("task_ref", "task_token")})
        self.assertEqual(json.loads(packet["specialist_args"]), {key: packet[key] for key in original})
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(run(), 1)
        self.assertEqual(before, {p.relative_to(path): p.read_bytes() for p in path.rglob("*") if p.is_file()})

    def test_invalid_agent_grant_outputs_reject_before_task_creation_and_preserve_files(self):
        path, connection = self.connection("invalid-agent", "runtime_company_analyst")
        public = self.root/"public"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        directory_link = self.root/"directory-link"
        directory_link.symlink_to(self.root, target_is_directory=True)
        existing = self.root/"existing.json"
        _write_json(existing, {"sentinel": "unchanged"})
        file_link = self.root/"file-link.json"
        file_link.symlink_to(existing)
        full = self.root/"new-full.json"
        cases = [(full, Path("relative-agent.json")),
                 (full, ROOT/"unapproved-agent.json"),
                 (full, public/"agent.json"),
                 (full, directory_link/"agent.json"),
                 (full, file_link), (full, existing), (full, full),
                 (existing, self.root/"new-agent.json"),
                 (public/"full.json", self.root/"new-agent.json")]
        before = {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}
        saved = existing.read_bytes()
        for full_output, agent_output in cases:
            with self.subTest(full=str(full_output), agent=str(agent_output)):
                result = self.cli_task(path, capability="COMPANY_RESEARCH", grant_output=full_output,
                                       agent_grant_output=agent_output)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotIn(connection.connection_token, result.stderr)
                self.assertEqual(before, {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()})
                self.assertEqual(existing.read_bytes(), saved)
                self.assertFalse(full.exists())
                self.assertFalse((self.root/"new-agent.json").exists())
        # Rejection has not damaged the connection or its legitimate preparation path.
        valid = self.cli_task(path, capability="COMPANY_RESEARCH", grant_output=full,
                              agent_grant_output=self.root/"new-agent.json")
        self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_archive_cli_binds_exact_grant_and_receipt_before_writes_and_feeds_web(self):
        from tests.test_native_research_submission import company_draft
        from product.runtime.research_memory import ResearchMemory
        from product.tools.report_history import read_archive_file
        from product.web.read_only import ArtifactCatalog
        path, connection = self.connection("archive-company", "runtime_company_analyst")
        grant = connection.prepare_task(security_id=SECURITY, capability="COMPANY_RESEARCH")
        grant_file = self.root/"archive-grant.json"
        _write_json(grant_file, grant)
        tools = connection.task_tools(task_ref=grant["task_ref"], task_token=grant["task_token"])
        tools.query(evidence_ids=["ev-revenue"])
        receipt = tools.submit(draft=company_draft())
        memory_root, output_dir = self.root/"archive-memory", self.root/"archive-export"
        command = [sys.executable, "-B", "-m", "product.tools.prepare", "archive",
                   "--connection-root", str(path), "--connection-access", str(path/"operator-grant.json"),
                   "--task-grant", str(grant_file), "--draft-ref", receipt["draft_ref"],
                   "--memory-root", str(memory_root), "--output-dir", str(output_dir)]
        def run():
            return subprocess.run(command, cwd=ROOT, env=self.environment, text=True, capture_output=True, timeout=10)
        # A different task token cannot create either destination.
        wrong = dict(grant, task_token="x"*40)
        bad_grant = self.root/"wrong-archive-grant.json"
        _write_json(bad_grant, wrong)
        position = command.index("--task-grant")+1
        command[position] = str(bad_grant)
        self.assertNotEqual(run().returncode, 0)
        command[position] = str(grant_file)
        ref_position = command.index("--draft-ref")+1
        command[ref_position] = "r1."+"x"*24
        self.assertNotEqual(run().returncode, 0)
        self.assertFalse(memory_root.exists())
        self.assertFalse(output_dir.exists())
        command[ref_position] = receipt["draft_ref"]
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        stored = json.loads(result.stdout)
        archive = read_archive_file(output_dir/"native-research-archive.json")
        self.assertEqual(ResearchMemory(memory_root).load_report_package(stored["object_ref"], stored["object_hash"]), archive)
        self.assertEqual(ArtifactCatalog(run_dirs=[output_dir]).native_reports(), [archive["report"]])
        from product.web.app import ResearchBrowser
        page = ResearchBrowser(None, ArtifactCatalog(run_dirs=[output_dir])).dispatch(
            "GET", "/reports", headers={"Host": "127.0.0.1"})
        self.assertEqual(page.status, 200)
        self.assertIn(archive["report"]["research"]["research_summary"]["summary"], page.body.decode("utf-8"))
        self.assertEqual(stored["model_calls"], 0)
        self.assertEqual(stored["host_execution"], "UNVERIFIED")
        self.assertEqual(stored["content_verdict"], "NOT_REVIEWED")
        self.assertEqual((output_dir/"native-research-archive.json").stat().st_mode & 0o777, 0o600)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertNotEqual(run().returncode, 0)  # Existing export cannot be overwritten.
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertNotIn(grant["task_token"], result.stdout)
        self.assertNotIn(connection.connection_token, result.stdout)
        archive_text = (output_dir/"native-research-archive.json").read_text()
        self.assertNotIn(grant["task_token"], archive_text)
        self.assertNotIn(connection.connection_token, archive_text)

    def test_operator_task_inherits_only_connection_approved_search_and_peer_inputs(self):
        from product.runtime.hashing import canonical_hash
        rows = [{"symbol": symbol,"name": symbol,"market_cap":"100","country":"United States","ipo_year":2000,
                 "sector":"Synthetic Sector","industry":"Synthetic Industry","source_id":"nasdaq-screener",
                 "as_of":AT,"retrieved_at":AT,"raw_content_hash":"a"*64} for symbol in ("ALB","PEER1")]
        universe = {"schema_version":"live-universe/1.0.0","provider":"nasdaq","source_id":"nasdaq-screener",
            "source_locator":"https://api.nasdaq.com/api/screener/stocks","request_started_at":AT,"as_of":AT,
            "retrieved_at":AT,"completeness":"COMPLETE","rows":rows,"snapshot_hash":canonical_hash({"rows":rows,"as_of":AT})}
        pool = build_peer_candidate_pool([{"security_id":SECURITY,"ticker":"ALB"}],universe=universe)
        path, connection = self.connection("market","runtime_market_catalyst",public_research_authorized=True,peer_candidate_pool=pool)
        grant = self.root/"peer-grant.json"
        result = self.cli_task(path,capability="PEER_SELECTION",grant_output=grant)
        self.assertEqual(result.returncode,0,result.stderr)
        value = json.loads(grant.read_text())
        self.assertTrue(value["task"]["peer_candidates"])
        self.assertNotIn("search",value["task"]["permissions"])
        self.assertEqual(connection.task_tools(task_ref=value["task_ref"],task_token=value["task_token"]).context()["capability"],"PEER_SELECTION")
        macro_grant = self.root/"macro-grant.json"
        macro = self.cli_task(path,capability="MACRO_RESEARCH_DISCOVERY",grant_output=macro_grant)
        self.assertEqual(macro.returncode,0,macro.stderr)
        self.assertIn("search",json.loads(macro_grant.read_text())["task"]["permissions"])
        unapproved, _ = self.connection("unapproved","runtime_market_catalyst")
        closed_grant = self.root/"closed-grant.json"
        closed = self.cli_task(unapproved,capability="MACRO_RESEARCH_DISCOVERY",grant_output=closed_grant)
        self.assertEqual(closed.returncode,0,closed.stderr)
        self.assertNotIn("search",json.loads(closed_grant.read_text())["task"]["permissions"])

    def test_operator_task_uses_precise_saved_dependency_grants_and_rejects_malformed_before_new_task(self):
        path, connection = self.connection("company","runtime_company_analyst")
        grant = connection.prepare_task(security_id=SECURITY,capability="FUNDAMENTAL_EVENT")
        tools = connection.task_tools(task_ref=grant["task_ref"],task_token=grant["task_token"])
        tools.query(evidence_ids=["ev-revenue"])
        original = _report(capability="FUNDAMENTAL_EVENT")
        draft = {k:copy.deepcopy(v) for k,v in original.items() if k in semantic_schema("FUNDAMENTAL_EVENT")["properties"]}
        draft.update(calculation_selections=[],document_selections=[])
        draft["claims"][0].pop("calculation_refs",None)
        draft["claims"][0]["evidence_refs"] = ["ev-revenue"]
        draft["observation_conditions"][0]["evidence_refs"] = ["ev-revenue"]
        saved = tools.submit(draft=draft)
        self.assertTrue(saved["accepted"],saved)
        dependencies = self.root/"dependencies.json"
        _write_json(dependencies,{"dependency_grants":[{"role":"runtime_company_analyst","task_ref":grant["task_ref"],
            "task_token":grant["task_token"],"draft_ref":saved["draft_ref"]}]})
        result = self.cli_task(path,capability="RESEARCH_REPORT",grant_output=self.root/"report-task.json",dependencies=dependencies)
        self.assertEqual(result.returncode,0,result.stderr)
        prepared = json.loads((self.root/"report-task.json").read_text())
        self.assertEqual(prepared["task"]["dependency_reports"][0]["report_id"],saved["report_id"])
        before = {p.name for p in (path/"tasks").iterdir()}
        malformed = self.root/"malformed.json"
        _write_json(malformed,{"dependency_grants":[{"role":"runtime_company_analyst","task_ref":grant["task_ref"],"task_token":grant["task_token"]}]})
        rejected = self.cli_task(path,capability="RESEARCH_REPORT",grant_output=self.root/"rejected.json",dependencies=malformed)
        self.assertNotEqual(rejected.returncode,0)
        self.assertFalse((self.root/"rejected.json").exists())
        self.assertEqual(before,{p.name for p in (path/"tasks").iterdir()})
        self.assertNotIn(grant["task_token"],result.stdout)
