"""Preparation boundary for the independent predecision CIO run."""

from __future__ import annotations

import json
import hashlib
import os
import signal
import shlex
import subprocess
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.cio_handoff import cio_model_view
from product.runtime.cli import main as runtime_cli_main
from product.runtime.predecision_cio_stage import (
    PredecisionCioStageError,
    _run_cio_process,
    launch_predecision_cio_run,
    _decoding_schema,
    _output_schema,
    _native_output_schema,
    _stage_instruction_bundle,
    _stage_instruction_section,
    build_predecision_cio_prompt,
    check_predecision_cio_trace,
    finalize_predecision_cio_advice,
    finalize_predecision_cio_research,
    prepare_predecision_cio_run,
    predecision_cio_reference_map,
    validate_predecision_cio_run,
)


REPO = Path(__file__).resolve().parents[1]


def _write(root: Path, ref: str, value: dict) -> None:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class PredecisionCioPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.target = self.root / "cio"
        self.package_ref = "research/skeptic/pre-decision-research-package.json"
        self.package = {
            "run_id": "source-1", "package_hash": "a" * 64,
            "consumability": "DOWNSTREAM_READY", "decision_cutoff": "2026-09-20T00:00:00Z",
            "request_id": "source-request", "request_hash": "b" * 64,
            "handoff_id": "handoff-1", "handoff_hash": "c" * 64,
            "portfolio_hash": "d" * 64, "gate_hash": "e" * 64,
            "counter_theses": [{"security_id": "US:COMMON_STOCK:MRVL", "invocation_id": "skeptic-1", "report": {
                "artifact_ref": "research/skeptic/reports/mrvl/counter-thesis.json",
                "content_hash": "a" * 64,
            }}],
            "coverage": {},
            "execution_proof": {"artifact_ref": "research/skeptic/execution-proof.json"},
        }
        self.handoff = {
            "portfolio_hash": "d" * 64,
            "source_items": [{"source_id": "s1", "as_of": "2026-09-20T00:00:00Z",
                              "retrieved_at": "2026-09-20T00:00:00Z"}],
            "field_lineage": [{"field_path": "account_snapshot.cash_balance", "source_refs": ["s1"]},
                              {"field_path": "portfolio.positions.p1.quantity", "source_refs": ["s1"]}],
            "portfolio": {"base_currency": "USD", "as_of": "2026-09-20T00:00:00Z", "positions": [{
                "position_id": "p1", "security_id": "US:COMMON_STOCK:MRVL", "asset_type": "COMMON_STOCK", "quantity": 10,
                "quote_price": 80, "market_value": 800, "source_refs": ["s1"],
            }]},
            "account_snapshot": {"cash_balance": 200, "as_of": "2026-09-20T00:00:00Z"}, "unknown_fields": [],
        }
        self.bundle = {"common_stock_security_ids": ["US:COMMON_STOCK:MRVL"], "coverage": {}, "report_refs": [{
            "artifact_ref": "research/reports/mrvl.json", "report_id": "company:US:COMMON_STOCK:MRVL",
            "capability": "COMPANY_RESEARCH", "security_ids": ["US:COMMON_STOCK:MRVL"],
            "report_hash": "f" * 64,
        }]}
        self._create_files()

    def _create_files(self) -> None:
        # 此组隔离测试显式 mock 上游业务校验，不是完整反证执行证明。
        # 仍给准备器真实的（空任务）依赖索引，避免生产代码迁就缺字段 fixture。
        from product.intake import build_handoff, build_manual_draft
        payload = json.loads((REPO / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json").read_text())
        payload["positions"] = [{"ticker": "MRVL", "quantity": 10, "cost_basis": 80}]
        payload["as_of"] = payload["retrieved_at"] = "2026-09-20T00:00:00Z"
        self.handoff = build_handoff(build_manual_draft(payload), confirmed=True,
                                    confirmed_at="2026-09-20T00:00:00Z")
        self.package.update({key: self.handoff[key] for key in ("handoff_id", "handoff_hash", "portfolio_hash")})
        self.package["schema_version"] = "pre-decision-research-package/1.0.0"
        index = {"schema_version": "independent-skeptic-dispatch/1.0.0",
                 "run_id": "source-1", "attempt": 1, "tasks": []}
        index["index_hash"] = canonical_hash(index)
        self.package["dispatch_index"] = {"artifact_ref": "research/skeptic/dispatch-index.json"}
        gate = {"run_id": "source-1", "decision_cutoff": "2026-09-20T00:00:00Z",
                "source_mode": "fixture", "allowed_evidence_ids": ["ev-1"],
                "allowed_evidence": [{"evidence_id": "ev-1", "source_id": "sec",
                                      "as_of": "2026-09-20T00:00:00Z",
                                      "retrieved_at": "2026-09-20T00:00:00Z"},
                                     {"evidence_id": "price-1", "security_id": "US:COMMON_STOCK:MRVL",
                                      "semantic_field": "close_price", "currency": "USD",
                                      "value": "80", "source_id": "yahoo-daily",
                                      "as_of": "2026-09-20T00:00:00Z",
                                      "retrieved_at": "2026-09-20T00:00:00Z"}]}
        gate["allowed_evidence_ids"].append("price-1")
        gate["bundle_hash"] = canonical_hash(gate)
        self.package["gate_hash"] = gate["bundle_hash"]
        for ref, value in {
            self.package_ref: self.package,
            "run_manifest.json": {"run_id": "source-1", "handoff_hash": self.handoff["handoff_hash"],
                                  "portfolio_hash": self.handoff["portfolio_hash"]},
            "audit/portfolio-handoff.json": self.handoff,
            "council-request.json": {"request_id": "source-request"},
            "evidence/gate.json": gate,
            "research/holding-research-bundle.json": self.bundle,
            "research/skeptic/execution-proof.json": {"status": "PASSED"},
            "research/skeptic/dispatch-index.json": index,
            "research/skeptic/reports/mrvl/counter-thesis.json": {"challenges": []},
            "research/reports/mrvl.json": {"claims": []},
        }.items():
            _write(self.source, ref, value)

    def _prepare(self, **kwargs):
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package"
        ):
            return prepare_predecision_cio_run(
                REPO, source_run_dir=self.source, run_dir=self.target,
                run_id="cio-1", target_security_id="US:COMMON_STOCK:MRVL", **kwargs,
            )

    def _write_model_proof(self, output: dict) -> None:
        invocation = self.target / "invocation"
        invocation.mkdir(exist_ok=True)
        text = json.dumps(output)
        (invocation / "final-message.json").write_text(text, encoding="utf-8")
        (invocation / "prompt.txt").write_text(
            build_predecision_cio_prompt(REPO, self.target), encoding="utf-8"
        )
        (invocation / "cio-output.schema.json").write_text("{}", encoding="utf-8")
        (invocation / "environment-manifest.json").write_text(json.dumps({
            "command": ["codex", "exec", "--skip-git-repo-check", "--sandbox",
                        "workspace-write", "--add-dir", str(self.target.resolve()), "-C",
                        str(self.target.resolve()), "--model", "gpt-6-luna"],
            "run_id": "cio-1", "model": "gpt-6-luna",
            "started_at": "2026-09-20T00:00:00Z",
            "prompt_hash": file_hash(invocation / "prompt.txt"),
            "output_schema_hash": file_hash(invocation / "cio-output.schema.json"),
            "product_instructions_file_hash": file_hash(REPO / "product/AGENTS.md"),
            "skill_file_hash": file_hash(REPO / "product/skills/portfolio-council/SKILL.md"),
            "agent_file_hash": file_hash(REPO / "product/.codex/agents/runtime_cio.toml"),
            "stage_instructions_hash": hashlib.sha256(
                _stage_instruction_bundle(REPO / "product").encode("utf-8")
            ).hexdigest(),
        }), encoding="utf-8")
        (invocation / "codex-events.jsonl").write_text("\n".join(json.dumps(item) for item in (
            {"type": "thread.started", "thread_id": "test"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
            {"type": "turn.completed"},
        )) + "\n", encoding="utf-8")

    def test_research_prepare_keeps_source_and_no_risk_context(self) -> None:
        before = file_hash(self.source / self.package_ref)
        result = self._prepare()
        self.assertEqual(result["actual_level"], "RESEARCH_SYNTHESIS")
        self.assertEqual(file_hash(self.source / self.package_ref), before)
        self.assertEqual(file_hash(self.target / "source-inputs" / self.package_ref), before)
        self.assertFalse((self.target / "risk-context.json").exists())
        self.assertFalse((self.target / "decision.json").exists())
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        self.assertEqual(request["request_hash"], canonical_hash({
            key: value for key, value in request.items() if key != "request_hash"
        }))

    def test_historical_mrvl_request_reader_keeps_original_schema_and_bytes(self) -> None:
        from product.runtime.predecision_cio_stage import (
            _artifact_request_schema, REQUEST_SCHEMA_REF, MANIFEST_VERSION, REQUEST_VERSION,
        )
        path = REPO / REQUEST_SCHEMA_REF
        before = path.read_bytes()
        schema = _artifact_request_schema(REPO, self.root, {
            'schema_version': MANIFEST_VERSION,
            'resource_locks': {REQUEST_SCHEMA_REF: file_hash(path)},
        }, {'schema_version': REQUEST_VERSION})
        self.assertEqual(schema['$id'], 'predecision-cio-request/1.0.0')
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(PredecisionCioStageError, 'UNSUPPORTED_VERSION'):
            _artifact_request_schema(REPO, self.root, {'schema_version': MANIFEST_VERSION},
                                     {'schema_version': 'predecision-cio-request/999.0.0'})

    def _prepare_alb(self, report=None):
        from tests.test_single_stock_input import alb_request
        from product.runtime.research_input import research_input_binding
        source_input = alb_request()
        binding = research_input_binding(source_input)
        package = dict(self.package)
        for key in ("handoff_id", "handoff_hash", "portfolio_hash"):
            package.pop(key)
        package.update(binding, schema_version="pre-decision-research-package/2.0.0",
                       decision_cutoff=source_input["resolved_cutoff"])
        # This isolated consumer test uses synthetic upstream contents, not an
        # MRVL report promoted to ALB or a real downstream-readiness claim.
        bundle = dict(self.bundle, common_stock_security_ids=["US:COMMON_STOCK:ALB"])
        for obj in (package, bundle):
            text = json.dumps(obj).replace("MRVL", "ALB").replace("mrvl", "alb")
            if obj is package:
                package = json.loads(text)
            else:
                bundle = json.loads(text)
        _write(self.source, "run_manifest.json", {"run_id": "source-1", **binding})
        _write(self.source, "audit/single-stock-request.json", source_input)
        _write(self.source, self.package_ref, package)
        _write(self.source, "research/holding-research-bundle.json", bundle)
        _write(self.source, "research/reports/alb.json", report or {"claims": []})
        _write(self.source, "research/skeptic/reports/alb/counter-thesis.json", {"challenges": []})
        gate = json.loads((self.source / "evidence/gate.json").read_text())
        gate["decision_cutoff"] = source_input["resolved_cutoff"]
        gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
        _write(self.source, "evidence/gate.json", gate)
        package["gate_hash"] = gate["bundle_hash"]
        _write(self.source, self.package_ref, package)
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package"
        ):
            prepare_predecision_cio_run(REPO, source_run_dir=self.source, run_dir=self.target,
                                       run_id="cio-1", target_security_id="US:COMMON_STOCK:ALB")
        return source_input

    def test_alb_request_prepares_and_actual_cio_checker_has_no_mrvl_context(self) -> None:
        source_input = self._prepare_alb()
        _, request = validate_predecision_cio_run(REPO, self.target)
        self.assertEqual(request["input_request_hash"], source_input["request_hash"])
        self.assertNotIn("portfolio_hash", request)
        self.assertFalse((self.target / "source-inputs/audit/portfolio-handoff.json").exists())
        prompt = build_predecision_cio_prompt(REPO, self.target)
        self.assertNotIn("MRVL", prompt)
        self.assertNotIn("曾清仓", prompt)
        schema = _output_schema(REPO, request, json.loads((self.target / "report-catalog.json").read_text())["reports"], run_dir=self.target)
        self.assertEqual(schema["properties"]["target_security_id"]["const"], "US:COMMON_STOCK:ALB")

    def test_single_stock_source_review_order_reaches_real_launcher_stdin(self) -> None:
        self._prepare_alb()
        manifest, request = validate_predecision_cio_run(REPO, self.target)
        self.assertEqual(request["input_kind"], "SINGLE_STOCK_RESEARCH")
        prompt = build_predecision_cio_prompt(REPO, self.target)
        ordered = (
            "1. 完整读取报告后", "2. 先经query核实这些资料",
            "3. 基于核验结果再填写macro_market_transmission",
            "<validated_research_context>",
        )
        offsets = [prompt.index(text) for text in ordered]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(prompt.count("本次单股研究按以下顺序"), 1)
        self.assertNotIn("上游报告保存及结构验证不代表每条内容正确", prompt)
        self.assertIn("challenge_dispositions须针对原挑战对象", prompt)
        self.assertIn("即使最终不采用有疑点的上游主张", prompt)
        self.assertIn("若窗口方向不同", prompt)
        self.assertIn("不新增输出字段、工具、研究任务或语义修订次数", prompt)
        source_before = {str(p.relative_to(self.source)): file_hash(p)
                         for p in self.source.rglob("*") if p.is_file()}
        # This CLI only captures local stdin/argv and exits; no Codex or model.
        script = self.root / "capture-cio.py"
        script.write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "root = Path(os.environ['STOCK_AGENT_RUN_DIR'])\n"
            "(root / 'captured-prompt.bin').write_bytes(sys.stdin.buffer.read())\n"
            "(root / 'captured-cli.json').write_text(json.dumps({"
            "'argv': sys.argv[1:], 'cwd': os.getcwd(), 'python': sys.executable}))\n"
            "print('local fake cli')\nprint('expected exit', file=sys.stderr)\nsys.exit(9)\n",
            encoding="utf-8",
        )
        cli = self.root / "fake-cio-cli"
        cli.write_text(f"#!/bin/sh\nif [ \"$1\" = --version ]; then printf 'codex-cli 0.160.0\\n'; exit 0; fi\nexec {shlex.quote(sys.executable)} {shlex.quote(str(script))} \"$@\"\n",
                       encoding="utf-8")
        cli.chmod(0o700)
        with patch.dict(os.environ, {"STOCK_AGENT_PRODUCT_HOST_LAUNCH": "1"}):
            result, host_code = launch_predecision_cio_run(
                REPO, run_dir=self.target, codex_binary=str(cli), timeout_seconds=20,
            )
        self.assertEqual(host_code, 7)
        self.assertEqual(result["failure_code"], "CIO_CODEX_PROCESS_FAILED")
        saved = self.target / "invocation/prompt.txt"
        self.assertEqual(saved.read_bytes(), prompt.encode("utf-8"))
        self.assertEqual((self.target / "captured-prompt.bin").read_bytes(), saved.read_bytes())
        environment = json.loads((self.target / "invocation/environment-manifest.json").read_text())
        capture = json.loads((self.target / "captured-cli.json").read_text())
        self.assertEqual(environment["prompt_hash"], file_hash(saved))
        self.assertEqual(capture["argv"], environment["command"][1:])
        self.assertEqual(capture["cwd"], str(REPO / "product"))
        self.assertEqual(Path(capture["python"]).resolve(), Path(sys.executable).resolve())
        command = environment["command"]
        self.assertEqual(command[command.index("--model") + 1], request["model"])
        self.assertEqual(command[command.index("-C") + 1], str(self.target.resolve()))
        self.assertIn("--ignore-user-config", command)
        schema_path = self.target / "invocation/cio-output.schema.json"
        self.assertEqual(environment["output_schema_hash"], file_hash(schema_path))
        self.assertEqual(json.loads(schema_path.read_text()), _decoding_schema(
            _native_output_schema(REPO, request, manifest["report_catalog"], run_dir=self.target),
            shared_evidence=True,
        ))
        process = json.loads((self.target / "invocation/process-result.json").read_text())
        self.assertEqual(process["process_exit_code"], 9)
        self.assertFalse(process["timed_out"])
        self.assertTrue(process["source_integrity_unchanged"])
        self.assertTrue(process["local_process_group"]["cleanup_complete"])
        self.assertEqual(check_predecision_cio_trace(REPO, self.target)["failure_code"],
                         "CIO_CODEX_PROCESS_FAILED")
        self.assertEqual(source_before, {str(p.relative_to(self.source)): file_hash(p)
                                        for p in self.source.rglob("*") if p.is_file()})
        for ref in ("report.md", "cio-research-synthesis.json", "risk.json", "decision.json"):
            self.assertFalse((self.target / ref).exists())

    def test_portfolio_source_review_keeps_original_method(self) -> None:
        self._prepare()
        prompt = build_predecision_cio_prompt(REPO, self.target)
        self.assertNotIn("本次单股研究按以下顺序", prompt)
        self.assertIn("上游报告保存及结构验证不代表每条内容正确。核对缺口理由与实际来源", prompt)
        self.assertIn("目标证券对基准的相对表现及相反窗口", prompt)

    def test_single_stock_report_delivery_generated_mcp_and_binding(self) -> None:
        import os
        import subprocess
        import tomllib
        from copy import deepcopy
        from product.runtime.cio_handoff import (
            REPORT_DELIVERY_VERSION, expand_cio_report_view, read_cio_reports, verify_cio_report_reads,
        )
        from product.runtime.hashing import canonical_json
        from product.runtime.nested_codex import build_nested_codex_command
        self._prepare_alb({"claims": [], "calculations": [
            {"calculation_id": f"calc-{i}", "input_evidence_refs": ["ev-1"] * 1000,
             "value": i, "unit": "USD", "method": "synthetic calculation"} for i in range(20)]})
        manifest = json.loads((self.target / "run_manifest.json").read_text())
        invocation = json.loads((self.target / "invocations/runtime_cio.json").read_text())
        self.assertEqual(manifest["report_delivery_version"], REPORT_DELIVERY_VERSION)
        self.assertEqual(invocation["report_delivery_version"], REPORT_DELIVERY_VERSION)
        self.assertIn("input_evidence_ref_sets", build_predecision_cio_prompt(REPO, self.target))
        mapping = predecision_cio_reference_map(REPO, self.target)
        ids = list(mapping["reports"])
        identity = {"run_id": "cio-1", "agent": "runtime_cio", "invocation_id": "cio:cio-1"}
        command = build_nested_codex_command(codex_binary="codex", product_root=REPO / "product",
            run_dir=self.target, model="gpt-6-luna", sqlite_home=self.target / "test-sqlite",
            log_dir=self.target / "test-log", final_message_path=self.target / "test-final",
            hook_recorder_path=REPO / "product/runtime/codex_hook_recorder.py", fixture_mcp_run_dir=self.target,
            enable_cio_local_revision=True, hook_agent_matcher="^runtime_cio$", skip_git_repo_check=True)
        transport = tomllib.loads(next(arg for arg in command if arg.startswith("mcp_servers.fixture_runtime=")))["mcp_servers"]["fixture_runtime"]
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "read_reports", "arguments": {**identity, "report_ids": ids}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "query", "arguments": {**identity, "evidence_ids": [next(k for k, v in mapping["evidence"].items() if v == "ev-1")]}}}]
        evidence_ref = next(k for k, v in mapping["evidence"].items() if v == "ev-1")
        requests.extend([
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "calculate", "arguments": {**identity, "operation": "ratio", "evidence_ids": [evidence_ref, evidence_ref]}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
                "name": "query", "arguments": {**identity, "evidence_ids": [evidence_ref]}}},
        ])
        completed = subprocess.run([transport["command"], *transport["args"]], cwd=transport["cwd"],
            env={**os.environ, **transport["env"], "PYTHONDONTWRITEBYTECODE": "1"},
            input="\n".join(json.dumps(r) for r in requests) + "\n", text=True, capture_output=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = {r["id"]: r for r in map(json.loads, completed.stdout.splitlines())}
        advertised = {tool["name"]: tool for tool in responses[1]["result"]["tools"]}
        self.assertEqual(set(advertised) & set(transport["enabled_tools"]), {"query", "read_reports"})
        self.assertEqual(transport["enabled_tools"], ["query", "read_reports"])
        self.assertNotIn("result", responses[4])
        self.assertIn("TOOL_NOT_AUTHORIZED:fixture_math.calculate", responses[4]["error"]["message"])
        self.assertFalse(responses[5]["result"]["isError"], responses[5])
        self.assertIn("input_evidence_ref_sets", advertised["read_reports"]["description"])
        for response in (responses[2], responses[3]):
            self.assertNotIn("error", response, response)
            self.assertFalse(response["result"]["isError"], response)
        delivered = responses[2]["result"]["structuredContent"]
        self.assertEqual(responses[2]["result"]["content"][0]["text"], canonical_json(delivered))
        canonical, event = read_cio_reports(self.target, invocation, manifest["report_catalog"],
            [mapping["reports"][ref] for ref in ids], prefix="source-inputs")
        original = cio_model_view(canonical, mapping)
        encoded = {key: delivered[key] for key in ("reports", "report_delivery")}
        binding = {"run_id": "cio-1", "invocation_id": "cio:cio-1", "reference_map_hash": mapping["map_hash"]}
        self.assertEqual(expand_cio_report_view(encoded, binding=binding), original)
        self.assertLess(len(canonical_json(encoded).encode()), len(canonical_json(original).encode()) // 4)
        self.assertEqual(delivered["canonical_result_hash"], event["output_hash"])
        proof = verify_cio_report_reads(self.target, invocation, manifest["report_catalog"], [], prefix="source-inputs")
        self.assertEqual(len(proof["read_report_ids"]), len(ids))
        event_path = self.target / "events/mcp/events.jsonl"
        original_events = event_path.read_text()
        events = list(map(json.loads, original_events.splitlines()))
        wire_event = next(e for e in events if e.get("event_type") == "mcp_reference_transport" and e["tool"] == "read_reports")
        self.assertEqual(wire_event["output_hash"], canonical_hash(delivered))
        self.assertEqual(wire_event["output_bytes"], len(canonical_json(delivered).encode()))
        wire_event["output_bytes"] += 1
        wire_event["event_hash"] = canonical_hash({k: v for k, v in wire_event.items() if k != "event_hash"})
        event_path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        with self.assertRaisesRegex(ValueError, "DELIVERY_EVENT_INVALID"):
            verify_cio_report_reads(self.target, invocation, manifest["report_catalog"], [], prefix="source-inputs")
        event_path.write_text(original_events)
        intact_events = list(map(json.loads, original_events.splitlines()))
        other_run = deepcopy(next(e for e in intact_events if e.get("event_type") == "mcp_reference_transport" and e["tool"] == "read_reports"))
        other_run["run_id"] = "another-run"
        other_run["event_hash"] = canonical_hash({k: v for k, v in other_run.items() if k != "event_hash"})
        for changed_events in (
            [e for e in intact_events if not (e.get("event_type") == "mcp_reference_transport" and e["tool"] == "read_reports")],
            intact_events + [other_run],
        ):
            event_path.write_text("\n".join(json.dumps(e) for e in changed_events) + "\n")
            with self.assertRaisesRegex(ValueError, "DELIVERY_EVENT_INVALID"):
                verify_cio_report_reads(self.target, invocation, manifest["report_catalog"], [], prefix="source-inputs")
        # Legitimate interleaving does not weaken full event/hash/bytes matching.
        event_path.write_text("\n".join(json.dumps(e) for e in reversed(intact_events)) + "\n")
        self.assertEqual(verify_cio_report_reads(self.target, invocation, manifest["report_catalog"], [], prefix="source-inputs"), proof)
        event_path.write_text(original_events)
        # Valid rehashes cannot authorize a one-sided or unknown delivery version.
        for manifest_version, invocation_version in (("unknown", "unknown"), (REPORT_DELIVERY_VERSION, None)):
            bad_manifest, bad_invocation = deepcopy(manifest), deepcopy(invocation)
            bad_manifest["report_delivery_version"] = manifest_version
            bad_invocation["report_delivery_version"] = invocation_version
            for obj, hash_field in ((bad_manifest, "manifest_hash"), (bad_invocation, "invocation_hash")):
                obj[hash_field] = canonical_hash({k: v for k, v in obj.items() if k != hash_field})
            _write(self.target, "run_manifest.json", bad_manifest)
            _write(self.target, "invocations/runtime_cio.json", bad_invocation)
            with self.assertRaisesRegex(ValueError, "DELIVERY_PROTOCOL_INVALID"):
                validate_predecision_cio_run(REPO, self.target)
        # Legacy no-marker delivery stays byte-for-byte model-view equivalent.
        for obj, hash_field in ((manifest, "manifest_hash"), (invocation, "invocation_hash")):
            del obj["report_delivery_version"]
            obj[hash_field] = canonical_hash({k: v for k, v in obj.items() if k != hash_field})
        _write(self.target, "run_manifest.json", manifest)
        _write(self.target, "invocations/runtime_cio.json", invocation)
        tools = StatelessFixtureTools(default_run_dir=self.target)
        legacy = tools.read_reports(**identity, report_ids=ids)
        self.assertNotIn("report_delivery", legacy)
        self.assertEqual(legacy["reports"], original["reports"])
        legacy_prompt = build_predecision_cio_prompt(REPO, self.target)
        self.assertNotIn("input_evidence_ref_sets", legacy_prompt)
        self.assertNotIn("本次单股研究按以下顺序", legacy_prompt)
        self.assertIn("上游报告保存及结构验证不代表每条内容正确。核对缺口理由与实际来源", legacy_prompt)

    def test_advice_and_mandate_are_rejected_before_writes(self) -> None:
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            self._prepare(requested_level="PORTFOLIO_ADVICE")
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_MANDATE_NOT_APPLICABLE_TO_RESEARCH"):
            self._prepare(mandate_path=self.root / "mandate.json")
        self.assertFalse(self.target.exists())
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            finalize_predecision_cio_advice(REPO, self.target)

    def test_direct_cli_advice_paths_reject_before_model_or_output(self) -> None:
        common = ["--repo", str(REPO), "--run-dir", str(self.target)]
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            runtime_cli_main([
                "prepare-predecision-cio", *common, "--source-run", str(self.source),
                "--run-id", "cio-1", "--target-security-id", "US:COMMON_STOCK:MRVL",
                "--requested-level", "PORTFOLIO_ADVICE",
            ])
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            runtime_cli_main(["finalize-predecision-cio-advice", *common])
        self.assertFalse(self.target.exists())

    def test_prepared_advice_request_cannot_reenter_model_path(self) -> None:
        self._prepare()
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        manifest = json.loads((self.target / "run_manifest.json").read_text())
        request["requested_level"] = request["actual_level"] = "PORTFOLIO_ADVICE"
        request["request_hash"] = canonical_hash({
            key: value for key, value in request.items() if key != "request_hash"
        })
        manifest["request_hash"] = request["request_hash"]
        manifest["manifest_hash"] = canonical_hash({
            key: value for key, value in manifest.items() if key != "manifest_hash"
        })
        _write(self.target, "predecision-cio-request.json", request)
        _write(self.target, "run_manifest.json", manifest)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE"):
            validate_predecision_cio_run(REPO, self.target)
        self.assertFalse((self.target / "invocation").exists())

    def test_model_decoder_schema_keeps_types_and_finalizer_exact_contract(self) -> None:
        self._prepare()
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        catalog = json.loads((self.target / "report-catalog.json").read_text())["reports"]
        authoritative = _output_schema(REPO, request, catalog, run_dir=self.target)
        decoder = _decoding_schema(authoritative)
        self.assertEqual(authoritative["properties"]["consumed_reports"]["const"], [
            {key: item[key] for key in (
                "report_id", "role", "security_ids", "invocation_id", "content_hash"
            )} for item in catalog
        ])
        self.assertEqual(decoder["properties"]["consumed_reports"]["type"], "array")
        self.assertNotIn("const", decoder["properties"]["consumed_reports"])
        native = _native_output_schema(REPO, request, catalog, run_dir=self.target)
        from product.runtime.cio_handoff import PREDECISION_METADATA
        self.assertFalse((PREDECISION_METADATA - {"schema_version"}) & native["properties"].keys())
        self.assertEqual(native["properties"]["report_selections"]["items"]["enum"],
                         [ref for item in catalog for ref, report_id in
                          predecision_cio_reference_map(REPO, self.target)["reports"].items()
                          if report_id == item["report_id"]])
        self.assertEqual(decoder["properties"]["actual_level"], {
            "type": "string", "enum": ["RESEARCH_SYNTHESIS"]
        })
        allowed_ids = [item["report_id"] for item in catalog]
        for field in ("key_facts", "macro_market_transmission"):
            self.assertEqual(
                decoder["properties"][field]["items"]["properties"]["report_ids"]["items"]["enum"],
                allowed_ids,
            )

        def inspect(node: dict) -> None:
            self.assertNotIn("const", node)
            self.assertNotIn("uniqueItems", node)
            if "enum" in node:
                self.assertIn("type", node)
            for child in node.get("properties", {}).values():
                inspect(child)
            if isinstance(node.get("items"), dict):
                inspect(node["items"])

        inspect(decoder)

    def test_single_stock_decoder_shares_exact_enum_without_weakening_references(self) -> None:
        from copy import deepcopy
        from product.runtime.schema_validation import validate_schema_instance
        ids = ["e.scope.2", "e.scope.1"]
        node = {"type": "string", "enum": ids}
        schema = {"type": "object", "additionalProperties": False,
            "required": ["evidence_refs", "key_facts"], "properties": {
                "evidence_refs": {"type": "array", "items": deepcopy(node)},
                "key_facts": {"type": "array", "items": {"type": "object",
                    "required": ["evidence_refs"], "additionalProperties": False,
                    "properties": {"evidence_refs": {"type": "array", "items": deepcopy(node)}}}},
            }}
        original = deepcopy(schema)
        plain = _decoding_schema(schema)
        compact = _decoding_schema(schema, shared_evidence=True)
        self.assertEqual(schema, original)
        self.assertEqual(compact["$defs"]["cio_evidence_id"], node)
        expanded = deepcopy(compact)
        del expanded["$defs"]
        expanded["properties"]["evidence_refs"]["items"] = deepcopy(node)
        expanded["properties"]["key_facts"]["items"]["properties"]["evidence_refs"]["items"] = deepcopy(node)
        self.assertEqual(expanded, plain)
        for ref in ids + ["e.foreign.1", "p.scope.1", "ev-raw", "e.scope.1 decorated"]:
            value = {"evidence_refs": [ref], "key_facts": [{"evidence_refs": [ref]}]}
            for candidate in (plain, compact):
                if ref in ids:
                    validate_schema_instance(value, candidate)
                else:
                    with self.assertRaises(ValueError):
                        validate_schema_instance(value, candidate)
        different = deepcopy(schema)
        different["properties"]["key_facts"]["items"]["properties"]["evidence_refs"]["items"]["enum"] = ids[:1]
        self.assertEqual(_decoding_schema(different, shared_evidence=True), _decoding_schema(different))
        collision = deepcopy(schema)
        collision["$defs"] = {"cio_evidence_id": node}
        with self.assertRaisesRegex(PredecisionCioStageError, "DEFINITION_COLLISION"):
            _decoding_schema(collision, shared_evidence=True)
        self.assertEqual(_decoding_schema(collision)["$defs"], collision["$defs"])

    def test_prompt_keeps_locked_stage_instructions_and_explicit_sample_context(self) -> None:
        self._prepare()
        prompt = build_predecision_cio_prompt(REPO, self.target)
        context = json.loads(prompt.split("<validated_research_context>\n", 1)[1].split(
            "\n</validated_research_context>", 1)[0])
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        self.assertEqual(context["request"]["target_security_id"], request["target_security_id"])
        self.assertEqual(context["stage_constraints"]["authorized_target_security_id"], request["target_security_id"])
        self.assertEqual(context["stage_constraints"]["allowed_delivery_levels"], ["RESEARCH_SYNTHESIS"])
        self.assertEqual(context["stage_constraints"]["risk_status"], "NOT_RUN")
        self.assertEqual(context["stage_constraints"]["user_context"]["source_kind"], "RESEARCH_REQUEST_NOT_ACCOUNT_EVIDENCE")
        self.assertIn(_stage_instruction_bundle(REPO / "product"), prompt)
        self.assertNotIn((REPO / "product/AGENTS.md").read_text(), prompt)
        self.assertNotIn("## 固定运行阶段", prompt)
        self.assertNotIn("EVAL_ABLATION", prompt)

    def test_instruction_section_markers_are_explicit_and_fail_closed(self) -> None:
        start = "<!-- PREDECISION_CIO_INSTRUCTIONS_START -->"
        end = "<!-- PREDECISION_CIO_INSTRUCTIONS_END -->"
        self.assertEqual(_stage_instruction_section(
            f"## 任意改名的标题\n{start}\n安全规则\n{end}", "sample"
        ), "安全规则")
        for invalid in ("安全规则", f"{start}安全规则", f"{end}安全规则{start}",
                        f"{start}{end}", f"{start}规则{end}{start}重复{end}"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(PredecisionCioStageError, "CIO_INSTRUCTION_SECTION_INVALID:sample"):
                    _stage_instruction_section(invalid, "sample")

    def test_invalid_instruction_section_stops_before_run_writes(self) -> None:
        with patch("product.runtime.predecision_cio_stage._stage_instruction_bundle",
                   side_effect=PredecisionCioStageError("CIO_INSTRUCTION_SECTION_INVALID:sample")):
            with self.assertRaisesRegex(PredecisionCioStageError, "CIO_INSTRUCTION_SECTION_INVALID"):
                self._prepare()
        self.assertFalse(self.target.exists())

    def test_structurally_consumable_source_stops_before_writes(self) -> None:
        self.package["consumability"] = "STRUCTURALLY_CONSUMABLE"
        _write(self.source, self.package_ref, self.package)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_SOURCE_PACKAGE_NOT_READY"):
            self._prepare()
        self.assertFalse(self.target.exists())

    def test_source_validator_failure_stops_before_writes(self) -> None:
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package",
            side_effect=ValueError("COUNTER_PACKAGE_HASH_MISMATCH"),
        ):
            with self.assertRaisesRegex(ValueError, "COUNTER_PACKAGE_HASH_MISMATCH"):
                prepare_predecision_cio_run(
                    REPO, source_run_dir=self.source, run_dir=self.target,
                    run_id="cio-1", target_security_id="US:COMMON_STOCK:MRVL",
                )
        self.assertFalse(self.target.exists())

    def test_destination_cannot_be_nested_in_source_run(self) -> None:
        nested_target = self.source / "new-cio-run"
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package"
        ):
            with self.assertRaisesRegex(PredecisionCioStageError, "CIO_SOURCE_RUN_INVALID"):
                prepare_predecision_cio_run(
                    REPO, source_run_dir=self.source, run_dir=nested_target,
                    run_id="cio-1", target_security_id="US:COMMON_STOCK:MRVL",
                )
        self.assertFalse(nested_target.exists())

    def test_current_mode_requires_new_source(self) -> None:
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_CURRENT_RESEARCH_REQUIRES_NEW_SOURCE"):
            self._prepare(time_mode="CURRENT")
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_CURRENT_RESEARCH_REQUIRES_NEW_SOURCE"):
            self._prepare(time_mode="CURRENT", max_research_age_days=0)
        self.assertFalse(self.target.exists())

    def test_other_security_cannot_inherit_mrvl_nonholding_context(self) -> None:
        with patch("product.runtime.predecision_cio_stage.validate_forward_gate"), patch(
            "product.runtime.predecision_cio_stage.validate_predecision_package"
        ):
            with self.assertRaisesRegex(PredecisionCioStageError, "CIO_TARGET_NOT_RESEARCHED"):
                prepare_predecision_cio_run(
                    REPO, source_run_dir=self.source, run_dir=self.target,
                    run_id="cio-1", target_security_id="US:COMMON_STOCK:ALB",
                )
        self.assertFalse(self.target.exists())

    def test_mixed_assets_are_preserved_without_account_advice(self) -> None:
        from product.intake import build_handoff, build_manual_draft
        payload = json.loads((REPO / "evals/fixtures/portfolio-intake/synthetic-manual-ten-positions.json").read_text())
        payload["positions"] = [{"ticker": "MRVL", "quantity": 10, "cost_basis": 80},
                                {"ticker": "QQQ", "asset_type": "ETF", "quantity": 2, "cost_basis": None}]
        self.handoff = build_handoff(build_manual_draft(payload), confirmed=True,
                                    confirmed_at="2026-09-20T00:00:00Z")
        binding = {key: self.handoff[key] for key in ("handoff_id", "handoff_hash", "portfolio_hash")}
        self.package.update(binding)
        _write(self.source, self.package_ref, self.package)
        _write(self.source, "run_manifest.json", {"run_id": "source-1", **binding})
        _write(self.source, "audit/portfolio-handoff.json", self.handoff)
        self._prepare()
        frozen = json.loads((self.target / "source-inputs/audit/portfolio-handoff.json").read_text())
        self.assertEqual(len(frozen["portfolio"]["positions"]), 2)
        self.assertFalse((self.target / "risk-context.json").exists())

    def test_cio_query_is_bound_to_frozen_gate_and_run(self) -> None:
        self._prepare()
        validate_predecision_cio_run(REPO, self.target)
        tools = StatelessFixtureTools(default_run_dir=self.target)
        identity = {"run_id": "cio-1", "agent": "runtime_cio", "invocation_id": "cio:cio-1"}
        mapping = predecision_cio_reference_map(REPO, self.target)
        short = next(ref for ref, evidence_id in mapping["evidence"].items() if evidence_id == "ev-1")
        self.assertEqual([short], [
            fact["evidence_id"] for fact in tools.query(**identity, evidence_ids=[short])["evidence"]
        ])
        self.assertEqual(tools.events[-1]["evidence_ids"], ["ev-1"])
        with self.assertRaisesRegex(ToolAccessError, "UNKNOWN_EVIDENCE"):
            tools.query(**identity, evidence_ids=["outside-gate"])
        with self.assertRaisesRegex(ToolAccessError, "INVOCATION_IDENTITY_MISMATCH"):
            tools.query(**{**identity, "run_id": "another-run"}, evidence_ids=["ev-1"])

    def test_materialized_report_tampering_blocks_query(self) -> None:
        self._prepare()
        (self.target / "source-inputs/research/reports/mrvl.json").write_text("{}", encoding="utf-8")
        tools = StatelessFixtureTools(default_run_dir=self.target)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_FROZEN_INPUT_DRIFT"):
            tools.query(run_id="cio-1", agent="runtime_cio", invocation_id="cio:cio-1",
                        evidence_ids=["ev-1"])

    def test_research_finalizer_is_non_action_and_query_backed(self) -> None:
        # Non-action synthesis does not assess cash, but its source Handoff must
        # remain a valid immutable contract; missing accounts use the new request.
        self._prepare()
        mapping = predecision_cio_reference_map(REPO, self.target)
        tools = StatelessFixtureTools(default_run_dir=self.target)
        tools.query(run_id="cio-1", agent="runtime_cio", invocation_id="cio:cio-1",
                    evidence_ids=["ev-1"])
        events = self.target / "events/mcp/events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        events.write_text(json.dumps(tools.events[-1]) + "\n", encoding="utf-8")
        request = json.loads((self.target / "predecision-cio-request.json").read_text())
        catalog = json.loads((self.target / "report-catalog.json").read_text())["reports"]
        consumed = [{key: item[key] for key in (
            "report_id", "role", "security_ids", "invocation_id", "content_hash"
        )} for item in catalog]
        output = {
            "schema_version": "predecision-cio-synthesis/2.0.0", "run_id": "cio-1",
            "invocation_id": "cio:cio-1", "source_run_id": "source-1",
            "source_package_hash": request["source_package_hash"],
            "target_security_id": "US:COMMON_STOCK:MRVL", "requested_level": "RESEARCH_SYNTHESIS",
            "actual_level": "RESEARCH_SYNTHESIS", "decision_cutoff": request["decision_cutoff"],
            "generated_at": "2026-09-24T00:00:00Z", "status": "LOW_CONFIDENCE",
            "advisory_only": True, "complete_portfolio_decision": False,
            "risk_status": "NOT_RUN",
            "consumed_reports": consumed, "analysis_horizon": "未来两个季度，仅为分析假设",
            "judgment": "公司经营判断暂不确定。", "reasoning": "资料不足，保留分歧。",
            "thesis": "增长有待验证", "counter_thesis": "证据时点仍有缺口",
            "consensus": [], "conflicts": ["增长证据不足"],
            "business_outlook": "待核实", "price_attractiveness": "无法判断",
            "account_fit": "当前账户适配未评估", "key_facts": [{
                "fact": "测试事实", "report_ids": [catalog[0]["report_id"]],
                "evidence_refs": ["ev-1"], "reasoning": "仅测试结构",
            }], "challenge_dispositions": [], "macro_market_transmission": [{
                "channel": "利率", "report_ids": [catalog[0]["report_id"]],
                "mechanism": "贴现率", "assessment": "影响未知", "limitations": "缺估值输入",
            }], "unresolved_questions": [], "invalidation_conditions": ["新披露"],
            "watch_plan": [{"item": "季度披露", "trigger": "披露发布", "reassess_on": "发布后"}],
            "reevaluation_conditions": ["新披露"],
            "confidence_rationale": "资料不足", "limitations": ["非组合建议"],
            "evidence_refs": ["ev-1"],
        }
        from product.runtime.cio_handoff import PREDECISION_METADATA, NATIVE_CIO_VERSION
        output = {key: value for key, value in output.items() if key not in PREDECISION_METADATA}
        output.update(schema_version=NATIVE_CIO_VERSION,
                      report_selections=[catalog[0]["report_id"]])
        output = cio_model_view(output, mapping)
        self._write_model_proof(output)
        with self.assertRaisesRegex(ValueError, "CIO_SELECTED_REPORT_NOT_READ"):
            finalize_predecision_cio_research(REPO, self.target)
        tools.read_reports(run_id="cio-1", agent="runtime_cio", invocation_id="cio:cio-1",
                           report_ids=cio_model_view({"report_ids": [catalog[0]["report_id"]]}, mapping)["report_ids"])
        with events.open("a") as stream:
            stream.write(json.dumps(tools.events[-1]) + "\n")
        with self.assertRaisesRegex(ValueError, "CIO_REQUIRED_REPORT_NOT_READ"):
            finalize_predecision_cio_research(REPO, self.target)
        tools.read_reports(run_id="cio-1", agent="runtime_cio", invocation_id="cio:cio-1",
                           report_ids=cio_model_view({"report_ids": [item["report_id"] for item in catalog[1:]]}, mapping)["report_ids"])
        with events.open("a") as stream:
            stream.write(json.dumps(tools.events[-1]) + "\n")
        message = self.target / "invocation/final-message.json"
        self._write_model_proof(output)
        output["action"] = "BUY"
        self._write_model_proof(output)
        with self.assertRaises(ValueError):
            finalize_predecision_cio_research(REPO, self.target)
        self.assertFalse((self.target / "report.md").exists())
        del output["action"]
        output["account_fit"] = "当前账户适配良好"
        self._write_model_proof(output)
        with self.assertRaises(ValueError):
            finalize_predecision_cio_research(REPO, self.target)
        output["account_fit"] = "当前账户适配未评估"
        self._write_model_proof(output)
        environment_ref = "invocation/environment-manifest.json"
        environment = json.loads((self.target / environment_ref).read_text())
        environment["stage_instructions_hash"] = "0" * 64
        _write(self.target, environment_ref, environment)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_LOCKED_INSTRUCTION_DELIVERY_INVALID"):
            finalize_predecision_cio_research(REPO, self.target)
        self._write_model_proof(output)
        environment = json.loads((self.target / environment_ref).read_text())
        command = environment["command"]
        command[command.index("-C") + 1] = str(REPO / "product")
        _write(self.target, environment_ref, environment)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_SOURCE_READONLY_COMMAND_INVALID"):
            finalize_predecision_cio_research(REPO, self.target)
        self._write_model_proof(output)
        result = finalize_predecision_cio_research(REPO, self.target)
        self.assertEqual(result["status"], "COMPLETED_RESEARCH_SYNTHESIS")
        formal = json.loads((self.target / "cio-research-synthesis.json").read_text())
        self.assertEqual(formal["evidence_refs"], ["ev-1"])
        self.assertEqual(formal["key_facts"][0]["report_ids"], [catalog[0]["report_id"]])
        self.assertEqual(formal["judgment"], output["judgment"])
        self.assertEqual(formal["consumed_reports"], consumed)
        trace = json.loads((self.target / "decision_trace.json").read_text())
        self.assertEqual(trace["report_consumption"]["reference_map_hash"], mapping["map_hash"])
        self.assertEqual(trace["report_consumption"]["semantic_output_hash"], canonical_hash(output))
        process_ref = "invocation/process-result.json"
        with self.assertRaises(PredecisionCioStageError):
            check_predecision_cio_trace(REPO, self.target)
        process = {
            "run_id": "cio-1", "process_exit_code": 0, "timed_out": False,
            "failure_code": None, "stage_status": "COMPLETED_RESEARCH_SYNTHESIS",
            "source_integrity_unchanged": True,
        }
        _write(self.target, process_ref, process)
        self.assertEqual(check_predecision_cio_trace(REPO, self.target)["status"], "PASSED")
        invalid_results = (
            {"run_id": "different-run"}, {"process_exit_code": 1},
            {"process_exit_code": True}, {"timed_out": True},
            {"timed_out": "false"}, {"failure_code": "CIO_CODEX_PROCESS_FAILED"},
            {"stage_status": "FAILED_VALIDATION"},
            {"source_integrity_unchanged": False},
            {"source_integrity_unchanged": 1},
            {"interrupted": True}, {"interrupted": 0}, {"execution_error": "OSError"},
        )
        for invalid in invalid_results:
            with self.subTest(invalid=invalid):
                _write(self.target, process_ref, {**process, **invalid})
                with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PROCESS_RESULT_INVALID"):
                    check_predecision_cio_trace(REPO, self.target)
        for missing in process:
            with self.subTest(missing=missing):
                _write(self.target, process_ref, {
                    key: value for key, value in process.items() if key != missing
                })
                with self.assertRaises(PredecisionCioStageError):
                    check_predecision_cio_trace(REPO, self.target)
        _write(self.target, process_ref, process)
        cleanup_proof = {
            "local_process_group": {"pid": 12345, "term_sent": False, "kill_sent": False,
                                    "signal_permission_denied": False, "cleanup_complete": True},
            "remote_cancellation_status": "NOT_APPLICABLE",
        }
        _write(self.target, process_ref, {**process, **cleanup_proof})
        self.assertEqual(check_predecision_cio_trace(REPO, self.target)["status"], "PASSED")
        for invalid in (
            {"local_process_group": None}, {"remote_cancellation_status": "CANCELLED"},
            *({"local_process_group": {**cleanup_proof["local_process_group"], **value}} for value in (
                {"cleanup_complete": False}, {"cleanup_complete": 1}, {"pid": True},
                {"term_sent": 1}, {"signal_permission_denied": True},
            )),
        ):
            with self.subTest(cleanup=invalid):
                _write(self.target, process_ref, {**process, **cleanup_proof, **invalid})
                with self.assertRaisesRegex(PredecisionCioStageError, "CIO_PROCESS_RESULT_INVALID"):
                    check_predecision_cio_trace(REPO, self.target)
        _write(self.target, process_ref, process)
        published = json.loads((self.target / "cio-research-synthesis.json").read_text())
        self.assertNotIn("generated_at", output)
        self.assertTrue(published["generated_at"])
        self.assertEqual(
            json.loads((self.target / "decision_trace.json").read_text())["generated_at"],
            published["generated_at"],
        )
        self.assertFalse((self.target / "decision.json").exists())
        self.assertIn("Risk：未运行", (self.target / "report.md").read_text())
        published["generated_at"] = "2026-09-24T00:00:00Z"
        _write(self.target, "cio-research-synthesis.json", published)
        with self.assertRaisesRegex(PredecisionCioStageError, "CIO_RESEARCH_TRACE_INVALID"):
            check_predecision_cio_trace(REPO, self.target)

    def test_launcher_preserves_failure_and_records_group_cleanup(self) -> None:
        cases = (
            (124, True, True, "CIO_STAGE_TIMEOUT"),
            (9, False, True, "CIO_CODEX_PROCESS_FAILED"),
            (1, False, True, "CIO_CODEX_PROCESS_FAILED"),
            (0, False, False, "CIO_LOCAL_PROCESS_CLEANUP_INCOMPLETE"),
            (130, False, True, "CIO_STAGE_INTERRUPTED"),
        )
        for code, timed_out, cleanup, failure in cases:
            with self.subTest(failure=failure):
                self.target = self.root / f"{failure}-{code}"
                self._prepare()
                execution = {
                    "stdout": "fake-cli-stdout\n", "stderr": "fake-cli-stderr\n",
                    "process_exit_code": code, "timed_out": timed_out, "interrupted": code == 130,
                    "local_process_group": {"pid": 12345, "term_sent": timed_out,
                                            "kill_sent": False, "cleanup_complete": cleanup},
                    "remote_cancellation_status": "UNKNOWN" if timed_out or code == 130 else "NOT_APPLICABLE",
                }
                if code == 1:
                    execution.update(stdout="�", stderr="�", stdout_bytes=b"\xff",
                                     stderr_bytes=b"\xfe", execution_error="UnicodeDecodeError")
                with patch.dict(os.environ, {"STOCK_AGENT_PRODUCT_HOST_LAUNCH": "1"}), patch(
                    "product.runtime.predecision_cio_stage._run_cio_process", return_value=execution,
                ) as runner:
                    result, host_code = launch_predecision_cio_run(REPO, run_dir=self.target)
                self.assertEqual(host_code, 7)
                self.assertEqual(result["failure_code"], failure)
                self.assertEqual(runner.call_args.kwargs["timeout_seconds"], 2400)
                process = json.loads((self.target / "invocation/process-result.json").read_text())
                self.assertEqual(process["local_process_group"], execution["local_process_group"])
                self.assertEqual(process["remote_cancellation_status"], execution["remote_cancellation_status"])
                self.assertEqual(process["process_exit_code"], code)
                self.assertEqual(process["timed_out"], timed_out)
                self.assertEqual((self.target / "invocation/codex-events.jsonl").read_bytes(),
                                 execution.get("stdout_bytes", execution["stdout"].encode("utf-8")))
                self.assertEqual((self.target / "invocation/codex-stderr.log").read_bytes(),
                                 execution.get("stderr_bytes", execution["stderr"].encode("utf-8")))
                self.assertEqual(process["execution_error"], execution.get("execution_error"))
                self.assertEqual(check_predecision_cio_trace(REPO, self.target)["failure_code"], failure)
                for ref in ("report.md", "cio-research-synthesis.json", "risk.json", "decision.json"):
                    self.assertFalse((self.target / ref).exists())


class CioLocalProcessGroupTests(unittest.TestCase):
    def _run(self, script: str, root: Path, *, timeout: float = 3.0) -> dict:
        return _run_cio_process(
            [sys.executable, "-c", script], prompt="test-input", cwd=root,
            environment={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout_seconds=timeout, termination_grace_seconds=0.5,
        )

    def test_normal_and_nonzero_preserve_output_and_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for code in (0, 9):
                with self.subTest(code=code):
                    result = self._run(
                        f"import sys; print(sys.stdin.read()); print('stderr',file=sys.stderr); sys.exit({code})",
                        Path(tmp),
                    )
                    self.assertEqual(result["stdout"], "test-input\n")
                    self.assertEqual(result["stderr"], "stderr\n")
                    self.assertEqual(result["process_exit_code"], code)
                    self.assertFalse(result["timed_out"])
                    self.assertTrue(result["local_process_group"]["cleanup_complete"])
                    self.assertFalse(result["local_process_group"]["term_sent"])
                    self.assertEqual(result["remote_cancellation_status"], "NOT_APPLICABLE")

    def test_invalid_utf8_keeps_raw_bytes_and_cleans_descendants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for close_pipes in (True, False):
                with self.subTest(close_pipes=close_pipes):
                    identity = root / f"invalid-child-{close_pipes}.json"
                    child = (
                        "import os,signal,time,json; from pathlib import Path; "
                        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                        + ("os.close(1); os.close(2); " if close_pipes else "")
                        + f"Path({str(identity)!r}).write_text(json.dumps({{'pid':os.getpid(),'pgid':os.getpgrp()}})); time.sleep(60)"
                    )
                    parent = (
                        "import subprocess,sys,time,os; from pathlib import Path; "
                        f"subprocess.Popen([sys.executable,'-c',{child!r}]); p=Path({str(identity)!r}); "
                        "exec('while not p.exists(): time.sleep(0.01)'); os.write(1,b'\\xff'); os.write(2,b'\\xfe')"
                    )
                    try:
                        result = self._run(parent, root, timeout=0.7)
                        self.assertEqual(result["process_exit_code"], 1 if close_pipes else 124)
                        self.assertEqual(result["timed_out"], not close_pipes)
                        self.assertEqual(result["execution_error"], "UnicodeDecodeError")
                        self.assertEqual(result["stdout_bytes"], b"\xff")
                        self.assertEqual(result["stderr_bytes"], b"\xfe")
                        self.assertTrue(result["local_process_group"]["cleanup_complete"])
                        self.assertTrue(result["local_process_group"]["kill_sent"])
                        with self.assertRaises(ProcessLookupError):
                            os.killpg(json.loads(identity.read_text())["pgid"], 0)
                    finally:
                        if identity.exists():
                            try:
                                os.killpg(json.loads(identity.read_text())["pgid"], signal.SIGKILL)
                            except ProcessLookupError:
                                pass

    def test_actual_sigint_during_execution_and_cleanup_is_collected(self) -> None:
        sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                    start_new_session=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for phase in ("execution", "cleanup", "timeout_cleanup"):
                    with self.subTest(phase=phase):
                        identity = root / f"{phase}-child.json"
                        cleanup_marker = root / f"{phase}-cleanup.txt"
                        child = (
                            "import os,signal,time,json; from pathlib import Path; "
                            f"signal.signal(signal.SIGTERM,lambda *_: Path({str(cleanup_marker)!r}).write_text('TERM')); "
                            "os.close(1); os.close(2); "
                            f"Path({str(identity)!r}).write_text(json.dumps({{'pid':os.getpid(),'pgid':os.getpgrp()}})); "
                            "time.sleep(60)"
                        )
                        parent = (
                            "import subprocess,sys,time; from pathlib import Path; "
                            f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
                            f"p=Path({str(identity)!r}); "
                            "exec('while not p.exists(): time.sleep(0.01)'); print('parent-ready',flush=True); "
                            + ("time.sleep(60)" if phase != "cleanup" else "")
                        )
                        wrapper = (
                            "import os,sys,signal,json; from pathlib import Path; "
                            "from product.runtime.predecision_cio_stage import _run_cio_process; "
                            "handler=signal.getsignal(signal.SIGINT); "
                            f"result=_run_cio_process([sys.executable,'-c',{parent!r}],prompt='',cwd=Path({str(root)!r}),"
                            f"environment=dict(os.environ),timeout_seconds={0.7 if phase == 'timeout_cleanup' else 10},termination_grace_seconds=0.8); "
                            "result.pop('stdout_bytes'); result.pop('stderr_bytes'); "
                            "result['handler_restored']=signal.getsignal(signal.SIGINT)==handler; print(json.dumps(result))"
                        )
                        worker = subprocess.Popen(
                            [sys.executable, "-c", wrapper], cwd=REPO,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True,
                        )
                        binding = None
                        try:
                            marker = identity if phase == "execution" else cleanup_marker
                            deadline = time.monotonic() + 5
                            while not marker.exists() and worker.poll() is None and time.monotonic() < deadline:
                                time.sleep(0.01)
                            self.assertTrue(marker.exists(), phase)
                            binding = json.loads(identity.read_text())
                            os.kill(worker.pid, signal.SIGINT)
                            stdout, stderr = worker.communicate(timeout=8)
                            self.assertEqual(worker.returncode, 0, stderr)
                            result = json.loads(stdout)
                            self.assertEqual(result["process_exit_code"], 124 if phase == "timeout_cleanup" else 130)
                            self.assertEqual(result["timed_out"], phase == "timeout_cleanup")
                            self.assertTrue(result["interrupted"])
                            self.assertTrue(result["handler_restored"])
                            self.assertTrue(result["local_process_group"]["cleanup_complete"])
                            self.assertEqual(result["remote_cancellation_status"], "UNKNOWN")
                            with self.assertRaises(ProcessLookupError):
                                os.killpg(binding["pgid"], 0)
                            self.assertIsNone(sentinel.poll())
                        finally:
                            if worker.poll() is None:
                                worker.kill()
                            worker.communicate(timeout=3)
                            if binding is None and identity.exists():
                                binding = json.loads(identity.read_text())
                            if binding is not None:
                                try:
                                    os.killpg(binding["pgid"], signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
        finally:
            sentinel.terminate()
            sentinel.wait(timeout=3)

    def test_communicate_oserror_still_cleans_group(self) -> None:
        original = subprocess.Popen.communicate
        calls = 0

        def fail_once(process, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("synthetic pipe error")
            return original(process, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(subprocess.Popen, "communicate", fail_once):
            result = self._run("import time; time.sleep(60)", Path(tmp))
            self.assertEqual(result["process_exit_code"], 1)
            self.assertEqual(result["execution_error"], "OSError")
            self.assertTrue(result["local_process_group"]["cleanup_complete"])
            self.assertEqual(result["remote_cancellation_status"], "UNKNOWN")

    def test_signal_permission_denied_returns_incomplete_without_retrying_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch(
            "product.runtime.predecision_cio_stage.os.killpg", side_effect=PermissionError("denied"),
        ) as signal_group:
            started = time.monotonic()
            result = self._run("print('finished')", Path(tmp))
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(result["process_exit_code"], 0)
            self.assertTrue(result["local_process_group"]["signal_permission_denied"])
            self.assertFalse(result["local_process_group"]["cleanup_complete"])
            self.assertFalse(result["local_process_group"]["term_sent"])
            self.assertFalse(result["local_process_group"]["kill_sent"])
            self.assertEqual(result["remote_cancellation_status"], "UNKNOWN")
            self.assertTrue(all(call.args[1] == 0 for call in signal_group.call_args_list))

    def test_exited_parent_does_not_leave_closed_pipe_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = root / "closed-child.json"
            child = (
                "import os,signal,time; from pathlib import Path; "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); os.close(1); os.close(2); "
                f"Path({str(identity)!r}).write_text(str(os.getpid())); time.sleep(60)"
            )
            parent = (
                "import subprocess,sys,time; from pathlib import Path; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
                f"p=Path({str(identity)!r}); "
                "exec('while not p.exists(): time.sleep(0.01)'); print('parent-exited',flush=True)"
            )
            try:
                result = self._run(parent, root)
                self.assertEqual(result["process_exit_code"], 0)
                self.assertFalse(result["timed_out"])
                self.assertTrue(result["local_process_group"]["term_sent"])
                self.assertTrue(result["local_process_group"]["kill_sent"])
                self.assertTrue(result["local_process_group"]["cleanup_complete"])
                self.assertEqual(result["stdout"], "parent-exited\n")
                self.assertEqual(result["remote_cancellation_status"], "UNKNOWN")
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(identity.read_text()), 0)
            finally:
                if identity.exists():
                    try:
                        os.kill(int(identity.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_escaped_pipe_holder_is_not_killed_and_cleanup_fails_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = root / "escaped-child.json"
            child = (
                "import os,time; from pathlib import Path; "
                f"Path({str(identity)!r}).write_text(str(os.getpid())); time.sleep(60)"
            )
            parent = (
                "import subprocess,sys,time; "
                f"subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True); "
                "print('before-timeout',flush=True); time.sleep(60)"
            )
            started = time.monotonic()
            try:
                result = self._run(parent, root, timeout=0.7)
                child_pid = int(identity.read_text())
                self.assertLess(time.monotonic() - started, 5)
                self.assertEqual(result["process_exit_code"], 124)
                self.assertTrue(result["timed_out"])
                self.assertFalse(result["local_process_group"]["cleanup_complete"])
                self.assertIn("before-timeout", result["stdout"])
                self.assertEqual(result["remote_cancellation_status"], "UNKNOWN")
                os.kill(child_pid, 0)
                self.assertNotEqual(os.getpgid(child_pid), result["local_process_group"]["pid"])
            finally:
                if identity.exists():
                    try:
                        os.kill(int(identity.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_timeout_cleans_inherited_and_closed_pipe_descendants_only(self) -> None:
        sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                    start_new_session=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for close_pipes in (False, True):
                    with self.subTest(close_pipes=close_pipes):
                        identity = root / f"child-{close_pipes}.json"
                        child = (
                            "import os,signal,time,json; from pathlib import Path; "
                            "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                            f"Path({str(identity)!r}).write_text(json.dumps({{'pid':os.getpid(),'pgid':os.getpgrp()}})); "
                            + ("os.close(1); os.close(2); " if close_pipes else "")
                            + "time.sleep(60)"
                        )
                        parent = (
                            "import subprocess,sys,time; "
                            f"subprocess.Popen([sys.executable,'-c',{child!r}]); "
                            "print('parent-started',flush=True); time.sleep(60)"
                        )
                        child_pid = None
                        try:
                            result = self._run(parent, root, timeout=0.7)
                            binding = json.loads(identity.read_text())
                            child_pid = binding["pid"]
                            self.assertEqual(binding["pgid"], result["local_process_group"]["pid"])
                            self.assertEqual(result["process_exit_code"], 124)
                            self.assertTrue(result["timed_out"])
                            self.assertTrue(result["local_process_group"]["term_sent"])
                            self.assertTrue(result["local_process_group"]["kill_sent"])
                            self.assertTrue(result["local_process_group"]["cleanup_complete"])
                            self.assertIn("parent-started", result["stdout"])
                            self.assertEqual(result["remote_cancellation_status"], "UNKNOWN")
                            with self.assertRaises(ProcessLookupError):
                                os.kill(child_pid, 0)
                            self.assertIsNone(sentinel.poll())
                        finally:
                            if child_pid is None and identity.exists():
                                child_pid = json.loads(identity.read_text())["pid"]
                            if child_pid is not None:
                                try:
                                    os.kill(child_pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
        finally:
            sentinel.terminate()
            sentinel.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
