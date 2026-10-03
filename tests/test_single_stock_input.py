"""零模型身份接缝；合成 HTTP 记录不冒充真实 ALB 取数。"""
from copy import deepcopy
import hashlib
import json
import unittest
from pathlib import Path
import tempfile

from product.mcp.live.identity import parse_sec_ticker_map
from product.mcp.live.security_metadata import parse_chart_identity, bind_disclosure_security
from product.mcp.provenance import content_hash
from product.runtime.single_stock_input import (
    DEFAULT_QUESTION, build_single_stock_request, normalize_single_stock_intent,
    resolve_single_stock_identity, single_stock_subject, validate_single_stock_request,
)

AT = "2026-10-02T00:00:00Z"


def alb_identity():
    mapping = parse_sec_ticker_map(json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
        "data": [[915913, "ALB synthetic issuer", "ALB", "NYSE"]]}).encode(), retrieved_at=AT)
    raw = json.dumps({"chart": {"error": None, "result": [{"meta": {
        "symbol": "ALB", "instrumentType": "EQUITY", "currency": "USD",
        "exchangeName": "NYQ", "exchangeTimezoneName": "America/New_York"}}]}}).encode()
    record = {"raw_content_hash": hashlib.sha256(raw).hexdigest(), "retrieved_at": AT,
              "key": {"endpoint": "https://query1.finance.yahoo.com/v8/finance/chart/ALB"}}
    quote = parse_chart_identity(raw, ticker="ALB", record=record)
    cover = b'<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">Common Stock</ix:nonNumeric><ix:nonNumeric name="dei:TradingSymbol" contextRef="C">ALB</ix:nonNumeric><ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">NYSE</ix:nonNumeric>'
    document = {"form": "10-K", "raw_content_hash": hashlib.sha256(cover).hexdigest(),
        "cik": "0000915913", "source_id": "sec-synthetic-cover", "source_locator": "https://www.sec.gov/synthetic/cover.htm",
        "retrieved_at": AT, "published_at": "2026-02-01T00:00:00Z", "accession": "0000915913-26-000001"}
    return mapping, [bind_disclosure_security(cover, document, quote)]


def alb_request():
    mapping, metadata = alb_identity()
    return build_single_stock_request(normalize_single_stock_intent("alb", at=AT),
        sec_mapping=mapping, security_metadata=metadata, resolved_cutoff=AT, request_id="synthetic-alb")


class SingleStockInputTests(unittest.TestCase):
    def test_real_parsers_resolve_nyse_common_stock_without_account(self):
        request = alb_request()
        validate_single_stock_request(request)
        self.assertEqual(request["security"]["exchange"], "XNYS")
        self.assertEqual(request["security"]["cik"], "0000915913")
        self.assertEqual(request["research_question"], DEFAULT_QUESTION)
        self.assertEqual(request["resolved_cutoff"], AT)
        self.assertEqual(single_stock_subject(request)["security_id"], "US:COMMON_STOCK:ALB")
        for forbidden in ("portfolio", "quantity", "cost", "cash", "confirmation", "handoff_hash"):
            self.assertNotIn(forbidden, request)

    def test_unknown_ambiguous_foreign_etf_and_conflicting_identity_rejected(self):
        mapping, metadata = alb_identity()
        cases = [(mapping, []), (mapping * 2, metadata), ([], metadata)]
        for field, bad in (("security_type", "ETF"), ("exchange", "XNAS"), ("cik", "0000000001"),
                           ("filing_regime", "FOREIGN_20F"), ("currency", "HKD")):
            changed = deepcopy(metadata)
            changed[0][field] = bad
            cases.append((mapping, changed))
        for listing, covers in cases:
            with self.subTest(listing=listing, covers=covers), self.assertRaises(ValueError):
                resolve_single_stock_identity("ALB", sec_mapping=listing, security_metadata=covers, cutoff=AT)

    def test_dates_and_blank_question_fail_closed(self):
        for cutoff in ("2027-01-01T00:00:00Z", "2026-10-01", "garbage", None):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                normalize_single_stock_intent("ALB", cutoff=cutoff, at=AT)
        for symbol in ("ALB,MRVL", "", "US:ALB", 1):
            with self.assertRaises(ValueError):
                normalize_single_stock_intent(symbol, at=AT)
        with self.assertRaises(ValueError):
            normalize_single_stock_intent("ALB", question=" ", at=AT)

    def test_rehash_does_not_make_identity_or_future_provenance_valid(self):
        for field, bad in (("security_id", "US:COMMON_STOCK:MRVL"), ("cik", "0000000001")):
            request = alb_request()
            request["security"][field] = bad
            request["request_hash"] = content_hash({k: v for k, v in request.items() if k != "request_hash"})
            with self.assertRaises(ValueError):
                validate_single_stock_request(request)
        mapping, metadata = alb_identity()
        metadata[0]["retrieved_at"] = "2026-10-03T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "AFTER_CUTOFF"):
            resolve_single_stock_identity("ALB", sec_mapping=mapping, security_metadata=metadata, cutoff=AT)

    def test_explicit_cutoff_requires_frozen_identity_not_today_mapping(self):
        mapping, metadata = alb_identity()
        intent = normalize_single_stock_intent("ALB", cutoff="2026-09-01T00:00:00Z", at=AT)
        with self.assertRaisesRegex(ValueError, "AFTER_CUTOFF"):
            build_single_stock_request(intent, sec_mapping=mapping, security_metadata=metadata,
                resolved_cutoff=intent["requested_cutoff"])


class SingleStockCompanyTests(unittest.TestCase):
    def prepare_values(self):
        from product.council.intake_planning import build_common_stock_council_request
        from product.runtime.common_stock_stage import current_research_bindings
        from product.council.common_stock_research import prepare_common_stock_research_stage
        from product.runtime.hashing import canonical_hash
        source = alb_request()
        facts = [{"evidence_id": "ev-alb-revenue", "security_id": "US:COMMON_STOCK:ALB",
                  "semantic_field": "revenue", "value": "100", "source_id": "synthetic-sec",
                  "as_of": "2026-06-30T00:00:00Z", "retrieved_at": "2026-07-01T00:00:00Z"}]
        gate = {"run_id": "synthetic-alb-research", "decision_cutoff": AT,
                "input_evidence_ids": ["ev-alb-revenue"], "allowed_evidence_ids": ["ev-alb-revenue"],
                "excluded_evidence_ids": [], "allowed_evidence": facts, "excluded": []}
        gate["bundle_hash"] = canonical_hash(gate)
        council = build_common_stock_council_request(source, request_id="synthetic-council-alb",
                                                    research_question=source["research_question"])
        agent, skills = current_research_bindings(Path(__file__).resolve().parents[1])
        stage = prepare_common_stock_research_stage(source, council, gate, run_id=gate["run_id"],
            batch_id="synthetic-alb-batch", agent_binding=agent, skill_bindings=skills,
            effective_concurrency=1, execution_mode_reason="one research target")
        return source, council, gate, stage

    def test_single_input_plan_request_and_coverage_close_without_handoff(self):
        source, council, gate, stage = self.prepare_values()
        self.assertEqual(council["schema_version"], "council-request/3.0.0")
        self.assertEqual(stage["planning"]["schema_version"], "council-research-plan/2.0.0")
        self.assertEqual(stage["holding_requests"][0]["input_request_hash"], source["request_hash"])
        self.assertEqual(stage["coverage"]["schema_version"], "research-coverage/2.0.0")
        self.assertNotIn("handoff_hash", stage["coverage"])
        self.assertNotIn("portfolio_hash", stage["holding_requests"][0])

    def test_company_draft_is_enveloped_and_real_report_consumer_rejects_bad_refs(self):
        from product.council.common_stock_research import (
            EQUITY_DRAFT_KEYS, envelope_equity_research_draft, validate_equity_research_report,
        )
        # Only synthetic semantic fields are reused to test mechanical assembly;
        # the legacy fixture's identity is not supplied to the ALB producer.
        from tests.test_common_stock_research_contracts import research_request, valid_report
        source, council, gate, stage = self.prepare_values()
        request = stage["holding_requests"][0]
        report = valid_report(research_request()[2], evidence_refs=["ev-alb-revenue"])
        draft = {key: deepcopy(report[key]) for key in EQUITY_DRAFT_KEYS}
        executed = [{"skill_name": item["name"], "version": item["version"],
                     "invocation_hash": content_hash({"invocation_id": request["invocation_id"], "skill": item})}
                    for item in request["skill_bindings"]]
        result = envelope_equity_research_draft(draft, request=request,
            skill_execution=executed, report_id="synthetic-alb-report")
        self.assertEqual(result["schema_version"], "equity-research-report/2.0.0")
        self.assertEqual(result["bindings"]["input_request_hash"], source["request_hash"])
        self.assertNotIn("portfolio_hash", result["bindings"])
        self.assertEqual(result["security"]["display_symbol"], "ALB")
        broken = deepcopy(result)
        broken["claims"][0]["evidence_refs"] = ["ev-mrvl-unrelated"]
        with self.assertRaises(ValueError):
            validate_equity_research_report(broken, request=request)
        broken = deepcopy(result)
        broken["claims"][0]["calculation_refs"] = ["calc-unexecuted"]
        with self.assertRaises(ValueError):
            validate_equity_research_report(broken, request=request)

    def test_company_native_stage_rebuilds_from_actual_nonholding_audit(self):
        from product.runtime.common_stock_stage import prepare_common_stock_stage_run, _validate_common_stock_stage_run_package
        source, council, gate, stage = self.prepare_values()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request_path, gate_path = root / "request.json", root / "gate.json"
            request_path.write_text(json.dumps(source))
            gate_path.write_text(json.dumps(gate))
            prepare_common_stock_stage_run(Path(__file__).resolve().parents[1],
                research_input_path=request_path, gate_path=gate_path, run_dir=root / "run",
                run_id=gate["run_id"], model="gpt-6-luna")
            _validate_common_stock_stage_run_package(Path(__file__).resolve().parents[1], root / "run")
            self.assertTrue((root / "run/audit/single-stock-request.json").is_file())
            self.assertFalse((root / "run/audit/portfolio-handoff.json").exists())
            from product.runtime.common_stock_stage import build_common_stock_dispatch_packet
            task = json.loads((root / 'run/research/dispatch-index.json').read_text())['tasks'][0]
            packet = build_common_stock_dispatch_packet(Path(__file__).resolve().parents[1], root / 'run', task['task_name'])
            self.assertIn('vendor_money_flow', packet['catalog_policy']['excluded_datasets'])
            self.assertNotIn('若存在 moomoo_sg 的 vendor_money_flow', packet['instruction'])
            self.assertIn('financial_history 与当前核心问题相关的事实', packet['instruction'])
            self.assertIn('缺冻结附件不等于这些来源事实缺失', packet['instruction'])
            manifest_path = root / 'run/run_manifest.json'
            manifest = json.loads(manifest_path.read_text())
            from product.runtime.hashing import canonical_hash
            for key, bad in (('input_kind', 'PORTFOLIO_HOLDING'),
                             ('input_request_hash', 'f' * 64),
                             ('input_contract_locks', {})):
                changed = deepcopy(manifest)
                changed[key] = bad
                changed['manifest_hash'] = canonical_hash({k: v for k, v in changed.items() if k != 'manifest_hash'})
                manifest_path.write_text(json.dumps(changed))
                with self.subTest(field=key), self.assertRaises(ValueError):
                    _validate_common_stock_stage_run_package(Path(__file__).resolve().parents[1], root / 'run')
            manifest_path.write_text(json.dumps(manifest))

    def test_alb_native_hook_math_serialization_finalizer_and_memory_consumer(self):
        from product.runtime import common_stock_stage as runtime
        from product.runtime.codex_hook_recorder import handle_hook_event
        from product.runtime.hashing import canonical_hash
        from product.runtime.research_memory import ResearchMemory
        from tests.test_common_stock_semantic_handoff import CommonStockSemanticHandoffTests
        from tests import test_common_stock_research_contracts as fixtures
        source, _, gate, _ = self.prepare_values()
        net = deepcopy(gate['allowed_evidence'][0])
        net.update(evidence_id='ev-alb-net-income', semantic_field='net_income', value='20')
        gate['allowed_evidence'].append(net)
        gate['allowed_evidence_ids'].append(net['evidence_id'])
        gate['input_evidence_ids'].append(net['evidence_id'])
        gate['bundle_hash'] = canonical_hash({k: v for k, v in gate.items() if k != 'bundle_hash'})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'request.json').write_text(json.dumps(source))
            (root / 'gate.json').write_text(json.dumps(gate))
            repo = Path(__file__).resolve().parents[1]
            run = root / 'run'
            runtime.prepare_common_stock_stage_run(repo, research_input_path=root / 'request.json',
                gate_path=root / 'gate.json', run_dir=run, run_id=gate['run_id'],
                model='gpt-5.6-terra', memory_root=root / 'memory')
            task = json.loads((run / 'research/dispatch-index.json').read_text())['tasks'][0]
            helper = fixtures.CommonStockNativeStageTests()
            env = helper.hook_environment(run)
            record, _ = handle_hook_event(helper.dispatch_payload(run, task), environ=env)
            self.assertEqual(record['decision'], 'ALLOW')
            start = helper.event('SubagentStart', parent='parent-session', child='synthetic-alb-child', turn='turn-alb')
            record, response = handle_hook_event(start, environ=env)
            view = json.loads(response['hookSpecificOutput']['additionalContext'])
            request = json.loads((run / task['request_path']).read_text())
            semantic = CommonStockSemanticHandoffTests()
            semantic.call(run, request, 'query', evidence_ids=view['allowed_evidence_ids'])
            calculation = semantic.call(run, request, 'calculate', operation='ratio',
                                        evidence_ids=view['allowed_evidence_ids'])
            # Reuse only synthetic research fields; no legacy identity is sent
            # to the ALB producer, Hook, serialized report or Memory package.
            report = fixtures.valid_report(fixtures.research_request()[2],
                                           evidence_refs=request['allowed_evidence_ids'][:1])
            frozen = runtime.build_common_stock_dispatch_packet(repo, run, task['task_name'])
            draft = fixtures.CommonStockDispatchTests.semantic_draft(report, packet=frozen)
            draft['calculation_selections'] = [{'calculation_ref': calculation['calculation_ref'],
                'claim_ids': [draft['claims'][0]['claim_id']]}]
            record = semantic.stop(env, start, draft)
            self.assertEqual(record['output_capture']['status'], 'SAVED', record)
            result = runtime.finalize_common_stock_stage_run(repo, run)
            self.assertEqual(result['status'], 'PASSED')
            emitted = json.loads((run / record['output_capture']['path']).read_text())
            self.assertEqual(emitted['security']['display_symbol'], 'ALB')
            self.assertEqual(emitted['bindings']['input_request_hash'], source['request_hash'])
            self.assertNotIn('portfolio_hash', emitted['bindings'])
            memory = ResearchMemory(root / 'memory')
            stored = memory.reusable_report(task['security_id'], task['reuse_key'])
            self.assertIsNotNone(stored)
            package = memory.load_report_package(stored['package_ref'], stored['package_hash'])
            self.assertEqual(package['report'], emitted)


class SingleStockDownstreamTests(unittest.TestCase):
    def test_single_forward_host_isolates_desktop_config_without_changing_legacy_counter_host(self):
        import subprocess
        from unittest.mock import patch
        from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run, launch_multidimensional_stage
        from tests.test_common_stock_research_contracts import stock_handoff, gate_for
        repo = Path(__file__).resolve().parents[1]
        for single in (True, False):
            with self.subTest(single=single), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                if single:
                    source, _, gate, _ = SingleStockCompanyTests().prepare_values()
                    kwargs = {"research_input_path": root / "input.json"}
                else:
                    source = stock_handoff(1)
                    gate = gate_for(source, "legacy-counter-command")
                    kwargs = {"handoff_path": root / "input.json"}
                (root / "input.json").write_text(json.dumps(source))
                (root / "gate.json").write_text(json.dumps(gate))
                run = root / "run"
                prepare_multidimensional_stage_run(repo, **kwargs, gate_path=root / "gate.json",
                    run_dir=run, run_id=gate["run_id"], model="gpt-6-luna",
                    stage="INDEPENDENT_COUNTER_THESIS_RESEARCH", structured_report_submission=True)
                from product.runtime.fixture_mcp import StatelessFixtureTools
                from product.runtime.multidimensional_stage import build_multidimensional_stage_prompt
                tools = {t['name']: t for t in StatelessFixtureTools(default_run_dir=run).available_tools()}
                self.assertEqual('research_task_state' in tools, single)
                self.assertEqual('research_task_state' in build_multidimensional_stage_prompt(repo, run), single)
                # State-only extension must not widen the research identity protocol.
                self.assertIn('run_id', tools['query']['inputSchema']['required'])
                self.assertNotIn('task_name', tools['query']['inputSchema']['properties'])
                with patch("product.runtime.multidimensional_stage.subprocess.run",
                           return_value=subprocess.CompletedProcess([], 1, "", "synthetic command stop")) as call:
                    _, code = launch_multidimensional_stage(repo, run_dir=run)
                self.assertEqual(code, 7)
                command = call.call_args.args[0]
                self.assertEqual("--ignore-user-config" in command, single)
                self.assertIn("--strict-config", command)
                self.assertEqual(command[command.index("--model") + 1], "gpt-6-luna")
                self.assertTrue(any("mcp_servers.fixture_runtime=" in value for value in command))
                import tomllib
                override = next(v for v in command if v.startswith('mcp_servers.fixture_runtime='))
                allowed = tomllib.loads(override)['mcp_servers']['fixture_runtime']['enabled_tools']
                self.assertEqual('research_task_state' in allowed, single)
                if single:
                    self.assertIn("agents.max_threads=3", command)
                    for role in ("runtime_company_analyst", "runtime_market_catalyst"):
                        self.assertTrue(any(value.startswith("agents." + role + "=")
                            and str(repo / "product/.codex/agents" / (role + ".toml")) in value for value in command))
                self.assertEqual(command, json.loads((run / "invocation/environment-manifest.json").read_text())["command"])
                self.assertEqual(len(json.loads((run / "research/dispatch-index.json").read_text())["tasks"]), 8)

    def test_single_state_actual_hook_failure_and_dependency_denial_preserve_namespace_gate(self):
        from product.runtime.multidimensional_stage import (
            prepare_multidimensional_stage_run, read_multidimensional_task_state,
            build_multidimensional_dispatch_packet, serialize_multidimensional_initial_context,
            serialize_multidimensional_model_context, MultidimensionalStageError,
        )
        from product.runtime.codex_hook_recorder import handle_hook_event
        from product.runtime.fixture_mcp import StatelessFixtureTools
        from tests import test_multidimensional_stage as fixtures
        from tests.test_task_bound_research_tools import TaskBoundResearchToolsTests
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, _, gate, _ = SingleStockCompanyTests().prepare_values()
            (root / 'input.json').write_text(json.dumps(source))
            (root / 'gate.json').write_text(json.dumps(gate))
            run = root / 'run'
            prepare_multidimensional_stage_run(repo, research_input_path=root / 'input.json',
                gate_path=root / 'gate.json', run_dir=run, run_id=gate['run_id'],
                model='gpt-5.6-terra', stage='INDEPENDENT_COUNTER_THESIS_RESEARCH')
            tasks = json.loads((run / 'research/dispatch-index.json').read_text())['tasks']
            fund = next(t for t in tasks if t['capability'] == 'FUNDAMENTAL_EVENT')
            rr = next(t for t in tasks if t['capability'] == 'RESEARCH_REPORT')
            packet = build_multidimensional_dispatch_packet(repo, run, fund['task_name'])
            for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                context = json.loads(serialize(packet))
                self.assertIn('claim_business', context['output_contract_rules']['local_claim_ids'])
                self.assertIn('rc1', context['output_contract_rules']['local_claim_ids'])
            helper = fixtures.MultidimensionalStageTests()
            env = helper.targeted_environment(run, fund)
            env['STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT'] = '1'
            dispatched, _ = handle_hook_event(helper.dispatch_payload(fund, parent='p'), environ=env)
            self.assertEqual(dispatched['decision'], 'ALLOW')
            started, _ = handle_hook_event(helper.start_payload(fund, parent='p', child='fund'), environ=env)
            self.assertEqual(started['context_binding']['status'], 'DELIVERED')
            draft = helper.dimension_draft(fund)
            draft['claims'] = [{'claim_id': 'c.business', 'kind': 'FACT', 'question': 'synthetic',
                'statement': '合成来源事实', 'evidence_refs': packet['allowed_evidence_ids'][:1],
                'research_claim_refs': [], 'assumption_ids': [], 'document_refs': []}]
            stopped, _ = handle_hook_event(helper.stop_payload(fund, draft, parent='p', child='fund'), environ=env)
            capture = stopped['output_capture']
            self.assertEqual(capture['failure_code'], 'MULTIDIMENSIONAL_REFERENCE_LOCAL_NAMESPACE_COLLISION')
            self.assertEqual(capture['repair_state'], 'NOT_ALLOWED')
            self.assertEqual(capture['diagnostics']['status'], 'LOCATED')
            self.assertEqual(capture['diagnostics']['findings'][0]['path'], 'claims[0].claim_id')
            self.assertEqual(json.loads((run / capture['raw_path']).read_text()), draft)
            rr_env = helper.targeted_environment(run, rr)
            denied, _ = handle_hook_event(helper.dispatch_payload(rr, parent='p'), environ=rr_env)
            self.assertEqual(denied['dispatch_binding']['failure_code'], 'RESEARCH_DEPENDENCY_NOT_READY')
            reply = TaskBoundResearchToolsTests().call(run, 'research_task_state', {})
            states = {t['task_name']: t for t in reply['result']['structuredContent']['tasks']}
            self.assertEqual(states[fund['task_name']]['outcome'], 'FAILED')
            self.assertEqual(states[rr['task_name']]['outcome'], 'DEPENDENCY_BLOCKED')
            self.assertFalse(reply['result']['structuredContent']['all_tasks_terminal'])
            self.assertNotIn('claims', json.dumps(reply['result']['structuredContent']))
            self.assertIn('error', TaskBoundResearchToolsTests().call(run, 'research_task_state', {'run_id':'foreign'}))
            changed = json.loads((run / 'run_manifest.json').read_text())
            changed['input_request_hash'] = '0' * 64
            (run / 'run_manifest.json').write_text(json.dumps(changed))
            with self.assertRaises(MultidimensionalStageError):
                read_multidimensional_task_state(run)

    def test_single_skeptic_host_registers_only_original_skeptic_and_preserves_legacy_command(self):
        import subprocess
        from unittest.mock import patch
        from tests.test_independent_skeptic_stage import prepare_complete_forward
        from product.runtime.independent_skeptic_stage import prepare_skeptic_phase, launch_skeptic_phase
        repo = Path(__file__).resolve().parents[1]
        for single in (True, False):
            with self.subTest(single=single), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                run = prepare_complete_forward(root, single_stock=single)
                prepare_skeptic_phase(repo, run)
                with patch("product.runtime.independent_skeptic_stage.subprocess.run",
                           return_value=subprocess.CompletedProcess([], 1, "", "synthetic command stop")) as call:
                    _, code = launch_skeptic_phase(repo, run_dir=run)
                self.assertEqual(code, 7)
                command = call.call_args.args[0]
                self.assertEqual("--ignore-user-config" in command, single)
                self.assertIn("--strict-config", command)
                self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-terra")
                if single:
                    registered = [value for value in command if value.startswith("agents.runtime_")]
                    self.assertEqual(len(registered), 1)
                    self.assertTrue(registered[0].startswith("agents.runtime_skeptic="))
                    self.assertIn(str(repo / "product/.codex/agents/runtime_skeptic.toml"), registered[0])
                    self.assertIn("agents.max_threads=3", command)
                self.assertEqual(command, json.loads((run / "invocation/skeptic/environment-manifest.json").read_text())["command"])

    def test_single_targeted_dependency_retry_adopts_without_rewriting_six_valid_reports(self):
        from product.runtime.multidimensional_stage import (
            prepare_multidimensional_stage_run, finalize_multidimensional_stage_run,
            finalize_multidimensional_task_evidence, _adopt_multidimensional_retry,
            check_multidimensional_bundle_consumable,
        )
        from product.runtime.codex_hook_recorder import handle_hook_event
        from product.runtime.hashing import file_hash
        from tests import test_multidimensional_stage as fixtures
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, _, gate, _ = SingleStockCompanyTests().prepare_values()
            (root / 'input.json').write_text(json.dumps(source))
            (root / 'gate.json').write_text(json.dumps(gate))
            run = root / 'run'
            prepare_multidimensional_stage_run(repo, research_input_path=root / 'input.json',
                gate_path=root / 'gate.json', run_dir=run, run_id=gate['run_id'],
                model='gpt-5.6-terra', stage='INDEPENDENT_COUNTER_THESIS_RESEARCH')
            tasks = json.loads((run / 'research/dispatch-index.json').read_text())['tasks']
            fund = next(t for t in tasks if t['capability'] == 'FUNDAMENTAL_EVENT')
            rr = next(t for t in tasks if t['capability'] == 'RESEARCH_REPORT')
            helper = fixtures.MultidimensionalStageTests()
            def execute(task, *, parent, directory=None, failed=False):
                env = helper.targeted_environment(run, task)
                if directory:
                    env['STOCK_AGENT_SUBAGENT_EVENT_LOG'] = str(directory / 'subagent-events.jsonl')
                    env['STOCK_AGENT_SUBAGENT_DISPATCH_LOG'] = str(directory / 'subagent-dispatches.jsonl')
                dispatched, _ = handle_hook_event(helper.dispatch_payload(task, parent=parent), environ=env)
                self.assertEqual(dispatched['decision'], 'ALLOW', dispatched)
                child = parent + task['task_name']
                handle_hook_event(helper.start_payload(task, parent=parent, child=child), environ=env)
                draft = helper.dimension_draft(task)
                payload = helper.stop_payload(task, draft, parent=parent, child=child)
                if failed:
                    payload['last_assistant_message'] = 'invalid synthetic JSON'
                record, _ = handle_hook_event(payload, environ=env)
                self.assertEqual(record['output_capture']['status'], 'FAILED' if failed else 'SAVED', record)
            for task in tasks:
                if task is not rr:
                    execute(task, parent='original', failed=(task is fund))
            env = helper.targeted_environment(run, rr)
            denied, _ = handle_hook_event(helper.dispatch_payload(rr, parent='original'), environ=env)
            self.assertEqual(denied['dispatch_binding']['failure_code'], 'RESEARCH_DEPENDENCY_NOT_READY')
            base = finalize_multidimensional_stage_run(repo, run)
            self.assertEqual(base['completed'], 6)
            self.assertEqual(base['status'], 'FAILED')
            preserved = {p: p.read_bytes() for p in (run / 'research/reports').glob('**/dimension-report.*')}
            preserved[run / 'evidence/gate.json'] = (run / 'evidence/gate.json').read_bytes()
            old_bundle_hash = file_hash(run / 'research/holding-research-bundle.json')
            retry = run / 'invocation/retries/dependency/attempt-1'
            retry.mkdir(parents=True)
            execute(fund, parent='retry', directory=retry)
            execute(rr, parent='retry', directory=retry)
            finalize_multidimensional_task_evidence(repo, run, rr['task_name'], invocation_dir=retry)
            adopted = _adopt_multidimensional_retry(repo, run, invocation_dir=retry)
            self.assertEqual((adopted['completed'], adopted['expected']), (8, 8))
            self.assertEqual(file_hash(run / 'research/revisions/1/holding-research-bundle.json'), old_bundle_hash)
            self.assertTrue(all(p.read_bytes() == content for p, content in preserved.items()))
            consumed = check_multidimensional_bundle_consumable(repo, run, persist=False)
            self.assertEqual(consumed['status'], 'PASSED')
            # All synthetic reports retain insufficient evidence; 8 saves do not
            # upgrade the chain to research/CIO readiness.
            bundle = json.loads((run / 'research/holding-research-bundle.json').read_text())
            self.assertNotEqual(bundle['consumability'], 'DOWNSTREAM_READY')

    def test_latest_freeze_preserves_preparation_and_rejects_wrong_lineage(self):
        from product.runtime.single_stock_input import freeze_latest_research_request, validate_preparation_request_lineage
        source = alb_request()
        original = deepcopy(source)
        final = freeze_latest_research_request(source, resolved_cutoff="2026-10-02T01:00:00Z")
        validate_preparation_request_lineage(final, source)
        self.assertEqual(source, original)
        self.assertNotEqual(final["request_hash"], source["request_hash"])
        changed = deepcopy(source)
        changed["research_question"] = "different question"
        changed["request_hash"] = content_hash({k: v for k, v in changed.items() if k != "request_hash"})
        with self.assertRaises(ValueError):
            validate_preparation_request_lineage(final, changed)
        with self.assertRaises(ValueError):
            freeze_latest_research_request(source, resolved_cutoff="2026-10-01T00:00:00Z")

    def test_materials_and_eight_tasks_use_single_stock_audit_and_bindings(self):
        from product.runtime.research_materials_stage import prepare_research_materials_stage
        from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run, build_multidimensional_dispatch_packet
        from product.mcp.live.peer_candidates import build_peer_candidate_pool
        source, council, gate, _ = SingleStockCompanyTests().prepare_values()
        pool = build_peer_candidate_pool([{**single_stock_subject(source), "ticker": "ALB"}], universe={
            "schema_version": "live-universe/1.0.0", "completeness": "COMPLETE", "rows": [],
            "source_id": "synthetic-directory", "source_locator": "https://example.com/directory",
            "snapshot_hash": "a" * 64, "request_started_at": AT, "as_of": AT, "retrieved_at": AT,
        })
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, obj in (("request", source), ("gate", gate), ("pool", pool)):
                (root / f"{name}.json").write_text(json.dumps(obj))
            kwargs = dict(research_input_path=root / "request.json", gate_path=root / "gate.json",
                          run_id=gate["run_id"], model="gpt-6-luna", peer_candidate_pool_path=root / "pool.json")
            repo = Path(__file__).resolve().parents[1]
            result = prepare_research_materials_stage(repo, run_dir=root / "materials", **kwargs)
            self.assertEqual(result["task_count"], 4)
            result = prepare_multidimensional_stage_run(repo, run_dir=root / "eight", **kwargs,
                                                       structured_report_submission=True, task_bound_tools=True)
            self.assertEqual(result["task_count"], 8)
            for folder in ("materials", "eight"):
                self.assertFalse((root / folder / "audit/portfolio-handoff.json").exists())
                manifest = json.loads((root / folder / "run_manifest.json").read_text())
                self.assertEqual(manifest["input_request_hash"], source["request_hash"])
                self.assertNotIn("portfolio_hash", manifest)
            index = json.loads((root / "eight/research/dispatch-index.json").read_text())
            for task in index["tasks"]:
                packet = build_multidimensional_dispatch_packet(repo, root / "eight", task["task_name"], include_dependency_reports=False)
                self.assertEqual(packet["task"]["security_ids"], ["US:COMMON_STOCK:ALB"])

    def test_materials_and_eight_reject_wrong_cutoff_before_writing_run(self):
        from product.runtime.research_materials_stage import prepare_research_materials_stage
        from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run
        from product.runtime.hashing import legacy_envelope_hash
        source, council, gate, _ = SingleStockCompanyTests().prepare_values()
        gate["decision_cutoff"] = "2026-10-02T01:00:00Z"
        gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, obj in (("request", source), ("gate", gate)):
                (root / f"{name}.json").write_text(json.dumps(obj))
            for index, prepare in enumerate((prepare_research_materials_stage, prepare_multidimensional_stage_run)):
                kwargs = {"peer_candidate_pool_path": root / "missing-pool.json"} if index == 0 else {}
                with self.assertRaisesRegex(ValueError, "INPUT_CUTOFF_MISMATCH"):
                    prepare(Path(__file__).resolve().parents[1], research_input_path=root / "request.json",
                            gate_path=root / "gate.json", run_dir=root / str(index),
                            run_id=gate["run_id"], model="gpt-6-luna", **kwargs)
                self.assertFalse((root / str(index)).exists())


if __name__ == "__main__":
    unittest.main()
