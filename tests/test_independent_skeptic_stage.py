from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.fixture_mcp import (
    SKEPTIC_ADAPTER_VERSION,
    StatelessFixtureTools,
    ToolAccessError,
)
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run
from product.runtime.common_stock_stage import prepare_common_stock_stage_run
from product.council.research_output import persist_equity_research_report
from tests.test_common_stock_research_contracts import (
    gate_for, stock_handoff, valid_report,
)
from tests.test_multidimensional_stage import MultidimensionalStageTests

from product.runtime.independent_skeptic_stage import (
    DISPATCH_VERSION,
    IndependentSkepticStageError,
    build_first_pass_input,
    build_skeptic_dispatch_packet,
    capture_skeptic_report,
    finalize_skeptic_phase,
    prepare_skeptic_phase,
    prepare_skeptic_resume,
    read_dispatch_index,
    scope_evidence_ids,
    validate_core_coverage,
    validate_first_pass_input,
    validate_forward_gate,
    validate_report_query_closure,
)
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash

ROOT = Path(__file__).resolve().parents[1]


def semantic_draft(report, *, run=None, task=None, index_ref=None):
    from product.runtime.invocation import SPECIALIST_TECHNICAL_FIELDS
    result = {key: copy.deepcopy(value) for key, value in report.items() if key not in SPECIALIST_TECHNICAL_FIELDS}
    if run is not None:
        from product.runtime.multidimensional_references import translate_references
        packet = build_skeptic_dispatch_packet(ROOT, run, task["task_name"], index_ref=index_ref)
        result = translate_references(result, packet["reference_map"], to_model=True)
    return result


def prepare_complete_forward(root, *, count=1, single_stock=False):
    run_id = "counter-real-forward-run"
    handoff = stock_handoff(count)
    gate = gate_for(handoff, run_id)
    if single_stock:
        from tests.test_single_stock_input import SingleStockCompanyTests
        handoff, _, gate, _ = SingleStockCompanyTests().prepare_values()
        gate['run_id'] = run_id
        gate['bundle_hash'] = canonical_hash({k: v for k, v in gate.items() if k != 'bundle_hash'})
    handoff_path, gate_path = root / "handoff.json", root / "gate.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    gate_path.write_text(json.dumps(gate), encoding="utf-8")

    company = root / "company"
    prepare_common_stock_stage_run(
        ROOT, **({'research_input_path': handoff_path} if single_stock else {'handoff_path': handoff_path}), gate_path=gate_path,
        run_dir=company, run_id=run_id, model="gpt-5.6-terra",
    )
    company_gate = json.loads((company / "evidence/gate.json").read_text())
    company_index = json.loads((company / "research/dispatch-index.json").read_text())
    for task in company_index["tasks"]:
        request = json.loads((company / task["request_path"]).read_text())
        report = valid_report(request)
        report["report_id"] = f"equity:{task['security_id']}"
        evidence = {
            item["evidence_id"]: item for item in company_gate["allowed_evidence"]
        }
        persist_equity_research_report(
            company / "research/reports", report=report, request=request,
            evidence=[evidence[item] for item in request["allowed_evidence_ids"]],
        )
    company_proof = {
        "schema_version": "common-stock-research-execution-proof/1.0.0",
        "run_id": run_id,
        "expected_tasks": sorted(item["task_name"] for item in company_index["tasks"]),
        "completed_security_ids": sorted(item["security_id"] for item in company_index["tasks"]),
        "intervals": [], "parallel_overlap": False, "all_reports_valid": True,
        "agent": {}, "skills": [], "gate_hash": company_gate["bundle_hash"],
        "complete_portfolio_decision": False,
    }
    company_proof["proof_hash"] = canonical_hash(company_proof)
    (company / "research/execution-proof.json").write_text(
        json.dumps(company_proof), encoding="utf-8"
    )

    base = root / "base"
    prepare_multidimensional_stage_run(
        ROOT, **({'research_input_path': handoff_path} if single_stock else {'handoff_path': handoff_path}), gate_path=gate_path,
        run_dir=base, run_id=run_id, model="gpt-5.6-terra",
        stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
        company_research_run_path=company,
    )
    MultidimensionalStageTests().complete_with_explicit_gaps(base)
    run = base
    return run


class IndependentSkepticContractTests(unittest.TestCase):
    def test_catalog_preserves_periods_and_text_locators_without_facts(self):
        from product.runtime.independent_skeptic_stage import DELIVERY_VERSION, read_skeptic_evidence_catalog
        facts = [{'evidence_id': 'toc', 'security_id': 'US:COMMON_STOCK:ALB',
            'semantic_field': 'sec_risk_text', 'source_id': 'sec', 'as_of': '2026-06-30',
            'retrieved_at': '2026-10-02T00:00:00Z', 'unit': 'text',
            'value': 'Risk Factors 16', 'metadata': {'section': 'Risk Factors'}},
            {'evidence_id': 'body', 'security_id': 'US:COMMON_STOCK:ALB',
             'semantic_field': 'sec_risk_text', 'source_id': 'sec', 'as_of': '2026-06-30',
             'retrieved_at': '2026-10-02T00:00:00Z', 'unit': 'text',
             'value': 'A real source excerpt; not a heading.', 'metadata': {'section': 'Risk Factors', 'truncated': True}},
            {'evidence_id': 'eps', 'security_id': 'US:COMMON_STOCK:ALB',
             'semantic_field': 'diluted_eps', 'source_id': 'sec', 'as_of': '2026-06-30',
             'retrieved_at': '2026-10-02T00:00:00Z', 'unit': 'USD/share', 'value': '-2.00',
             'metadata': {'period_start': '2026-01-01', 'period_end': '2026-06-30',
                          'fiscal_period': 'Q2', 'context_type': 'duration', 'form': '10-Q'}}]
        packet = {'invocation': {'skeptic_delivery_version': DELIVERY_VERSION},
                  'agent_input': {'allowed_evidence_ids': [f['evidence_id'] for f in facts]},
                  'reference_map': {'evidence': {'e.1': 'toc', 'e.2': 'body', 'e.3': 'eps'}}}
        result = read_skeptic_evidence_catalog(packet, {'allowed_evidence': facts}, view='records')
        rows = {r['evidence_id']: r for r in result['rows']}
        self.assertEqual(rows['e.1']['content_kind'], 'HEADING_ONLY')
        self.assertEqual(rows['e.2']['content_kind'], 'SECTION_EXCERPT')
        self.assertEqual(rows['e.3']['period_start'], '2026-01-01')
        self.assertEqual(rows['e.3']['period_end'], '2026-06-30')
        self.assertEqual(rows['e.3']['unit'], 'USD/share')
        self.assertEqual(rows['e.3']['context_type'], 'duration')
        self.assertTrue(all('value' not in r for r in result['rows']))
        fields = read_skeptic_evidence_catalog(packet, {'allowed_evidence': facts}, semantic_field_prefix='sec_')
        self.assertEqual(fields['rows'][0]['count'], 2)

    def test_single_stock_grounding_failure_allows_only_one_local_author_revision(self):
        from tests.test_task_bound_research_tools import TaskBoundResearchToolsTests
        from product.runtime.local_revision import _apply
        from product.runtime.independent_skeptic_stage import read_skeptic_task_state
        with tempfile.TemporaryDirectory() as temp:
            run = prepare_complete_forward(Path(temp), single_stock=True)
            prepare_skeptic_phase(ROOT, run)
            task = read_dispatch_index(run)['tasks'][0]
            env = {'STOCK_AGENT_RUN_DIR': str(run),
                'STOCK_AGENT_SUBAGENT_EVENT_LOG': str(run / 'invocation/skeptic/subagent-events.jsonl'),
                'STOCK_AGENT_SUBAGENT_DISPATCH_LOG': str(run / 'invocation/skeptic/subagent-dispatches.jsonl'),
                'STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS': 'runtime_skeptic',
                'STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE': 'independent-skeptic-runtime/1.0.0',
                'STOCK_AGENT_RESEARCH_TASK_NAME': task['task_name']}
            dispatch = {'hook_event_name': 'PreToolUse', 'session_id': 'grounding-parent', 'turn_id': 'turn',
                'tool_name': 'spawn_agent', 'tool_use_id': 'grounding-spawn', 'cwd': str(ROOT / 'product'),
                'model': 'gpt-5.6-terra', 'permission_mode': 'workspace-write',
                'tool_input': {'agent_type': 'runtime_skeptic', 'task_name': task['task_name'],
                    'fork_turns': 'none', 'message': '读取冻结首轮上下文。'}}
            self.assertEqual(handle_hook_event(dispatch, environ=env)[0]['decision'], 'ALLOW')
            start = {'hook_event_name': 'SubagentStart', 'session_id': 'grounding-parent', 'turn_id': 'turn',
                'agent_id': 'grounding-child', 'agent_type': 'runtime_skeptic', 'model': 'gpt-5.6-terra',
                'cwd': str(ROOT / 'product'), 'permission_mode': 'read-only'}
            _, response = handle_hook_event(start, environ=env)
            state = read_skeptic_task_state(run, index_ref='research/skeptic/dispatch-index.json')
            self.assertFalse(state['all_tasks_terminal'])
            self.assertEqual(state['tasks'][0]['execution_status'], 'RUNNING')
            view = json.loads(response['hookSpecificOutput']['additionalContext'])
            refs = view['allowed_evidence_ids'][:1]
            query = TaskBoundResearchToolsTests().call(run, 'query', {
                **view['tool_context']['required_identity_arguments'], 'evidence_ids': refs})
            self.assertNotIn('error', query, query)
            bad = {'status': 'INSUFFICIENT_EVIDENCE', 'mode': 'INDEPENDENT_FIRST_PASS', 'scope': task['security_id'],
                'assumptions': [], 'challenges': [
                    {'challenge_id': 'grounded', 'statement': '单期收入不能证明持续性。', 'evidence_refs': refs,
                     'assumption_ids': [], 'resolution_evidence_needed': ['后续披露']},
                    {'challenge_id': 'gap', 'statement': '估值数据没有查询。', 'evidence_refs': [],
                     'assumption_ids': [], 'resolution_evidence_needed': ['估值资料']}],
                'evidence_refs': refs, 'counter_evidence_refs': [], 'uncertainties': ['合成接缝'],
                'data_gaps': ['尚未核验估值'], 'invalidation_conditions': ['后续披露消除疑问'],
                'confidence': .3, 'confidence_rationale': '仅验证局部纠正，不是经济判断。'}
            stop = {**start, 'hook_event_name': 'SubagentStop', 'stop_hook_active': False}
            first, feedback = handle_hook_event({**stop, 'last_assistant_message': json.dumps(bad)}, environ=env)
            self.assertEqual(first['output_capture']['repair_state'], 'REPAIR_REQUESTED', first)
            repair = json.loads(feedback['reason'])
            self.assertFalse(read_skeptic_task_state(run, index_ref='research/skeptic/dispatch-index.json')['all_tasks_terminal'])
            self.assertEqual(set(repair['allowed_paths']), {'/challenges/1', '/data_gaps'})
            for field in ('status', 'mode', 'confidence', 'assumptions', 'scope', 'challenges/0'):
                with self.assertRaises(ValueError):
                    _apply(bad, [{'op': 'replace', 'path': '/' + field, 'value': None}], repair['allowed_paths'])
            raw = run / first['output_capture']['raw_path']
            raw_bytes, gate_hash = raw.read_bytes(), file_hash(run / 'evidence/gate.json')
            revised, response = handle_hook_event({**stop, 'last_assistant_message': json.dumps({
                'base_draft_ref': repair['base_draft_ref'], 'changes': [
                    {'op': 'remove', 'path': '/challenges/1'},
                    {'op': 'replace', 'path': '/data_gaps', 'value': ['未查询估值不能视为数据源没有估值。']}]
            })}, environ=env)
            self.assertEqual(revised['output_capture']['status'], 'SAVED', revised)
            self.assertEqual(response, {})
            self.assertEqual(raw.read_bytes(), raw_bytes)
            self.assertEqual(file_hash(run / 'evidence/gate.json'), gate_hash)
            state = read_skeptic_task_state(run, index_ref='research/skeptic/dispatch-index.json')
            self.assertTrue(state['all_tasks_terminal'])
            self.assertEqual(state['tasks'][0]['research_status'], 'INSUFFICIENT_EVIDENCE')
            self.assertEqual(state['content_acceptance'], 'NOT_EVALUATED')
            self.assertNotIn('challenges', json.dumps(state))
            report_path = run / task['report_ref']
            report_bytes = report_path.read_bytes()
            altered = json.loads(report_bytes)
            altered['status'] = 'COMPLETE'
            report_path.write_text(json.dumps(altered))
            with self.assertRaisesRegex(IndependentSkepticStageError, 'REPORT_DRIFT'):
                read_skeptic_task_state(run, index_ref='research/skeptic/dispatch-index.json')
            report_path.write_bytes(report_bytes)
            log_path = run / 'invocation/skeptic/subagent-events.jsonl'
            log_bytes = log_path.read_bytes()
            forged = [json.loads(line) for line in log_bytes.decode().splitlines()]
            forged[-1]['trusted_task_binding']['invocation_id'] = 'other-attempt'
            forged[-1]['event_hash'] = legacy_envelope_hash(forged[-1], hash_field='event_hash')
            log_path.write_text('\n'.join(json.dumps(row) for row in forged) + '\n')
            with self.assertRaisesRegex(IndependentSkepticStageError, 'BINDING_INVALID'):
                read_skeptic_task_state(run, index_ref='research/skeptic/dispatch-index.json')
            log_path.write_bytes(log_bytes)
            self.assertEqual(finalize_skeptic_phase(ROOT, run)['status'], 'PARTIAL')
            third, _ = handle_hook_event({**stop, 'last_assistant_message': json.dumps(bad)}, environ=env)
            self.assertEqual(third['output_capture']['failure_code'], 'LOCAL_REVISION_LIMIT_EXHAUSTED')

    def test_skeptic_32_field_structure_errors_allow_one_author_patch_through_real_hooks(self):
        from tests.test_task_bound_research_tools import TaskBoundResearchToolsTests
        from tests.test_single_stock_input import SingleStockCompanyTests
        from product.runtime.schema_validation import schema_issue_locations
        values = SingleStockCompanyTests().prepare_values()
        gate = values[2]
        second_fact = {**gate['allowed_evidence'][0], 'evidence_id': 'ev-alb-revenue-second', 'value': '90'}
        gate['allowed_evidence'].append(second_fact)
        gate['allowed_evidence_ids'].append(second_fact['evidence_id'])
        gate['input_evidence_ids'].append(second_fact['evidence_id'])
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(SingleStockCompanyTests, 'prepare_values', return_value=values):
                run = prepare_complete_forward(Path(temp), single_stock=True)
            prepare_skeptic_phase(ROOT, run)
            task = read_dispatch_index(run)['tasks'][0]
            env = {'STOCK_AGENT_RUN_DIR': str(run),
                'STOCK_AGENT_SUBAGENT_EVENT_LOG': str(run / 'invocation/skeptic/subagent-events.jsonl'),
                'STOCK_AGENT_SUBAGENT_DISPATCH_LOG': str(run / 'invocation/skeptic/subagent-dispatches.jsonl'),
                'STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS': 'runtime_skeptic',
                'STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE': 'independent-skeptic-runtime/1.0.0',
                'STOCK_AGENT_RESEARCH_TASK_NAME': task['task_name']}
            dispatch = {'hook_event_name': 'PreToolUse', 'session_id': 'repair-parent', 'turn_id': 'turn',
                'tool_name': 'spawn_agent', 'tool_use_id': 'repair-spawn', 'cwd': str(ROOT / 'product'),
                'model': 'gpt-5.6-terra', 'permission_mode': 'workspace-write',
                'tool_input': {'agent_type': 'runtime_skeptic', 'task_name': task['task_name'],
                    'fork_turns': 'none', 'message': '读取冻结首轮上下文。'}}
            self.assertEqual(handle_hook_event(dispatch, environ=env)[0]['decision'], 'ALLOW')
            start = {'hook_event_name': 'SubagentStart', 'session_id': 'repair-parent', 'turn_id': 'turn',
                'agent_id': 'repair-child', 'agent_type': 'runtime_skeptic', 'model': 'gpt-5.6-terra',
                'cwd': str(ROOT / 'product'), 'permission_mode': 'read-only'}
            delivered, response = handle_hook_event(start, environ=env)
            self.assertEqual(delivered['context_binding']['status'], 'DELIVERED')
            view = json.loads(response['hookSpecificOutput']['additionalContext'])
            refs = view['allowed_evidence_ids'][:2]
            query = TaskBoundResearchToolsTests().call(run, 'query', {
                **view['tool_context']['required_identity_arguments'], 'evidence_ids': refs})
            self.assertNotIn('error', query, query)
            good = {'status': 'LOW_CONFIDENCE', 'mode': 'INDEPENDENT_FIRST_PASS', 'scope': task['security_id'],
                'assumptions': [{'assumption_id': f'A{i}', 'statement': '合成的待核验假设。'} for i in range(3)],
                'challenges': [{'challenge_id': f'C{i}', 'statement': '单期资料不足以验证持续性。',
                    'evidence_refs': refs, 'assumption_ids': [f'A{i}'],
                    'resolution_evidence_needed': ['后续可比披露']} for i in range(3)],
                'evidence_refs': refs, 'counter_evidence_refs': [], 'uncertainties': ['合成接缝'],
                'data_gaps': ['测试不代表经济判断'], 'invalidation_conditions': ['后续披露消除疑问'],
                'confidence': .3, 'confidence_rationale': '仅验证结构纠正路径。'}
            bad = copy.deepcopy(good)
            changes = [{'op': 'remove', 'path': '/counter_thesis'}]
            bad['counter_thesis'] = '额外的错误字段'
            for key in ('mode', 'counter_evidence_refs', 'uncertainties', 'invalidation_conditions', 'confidence_rationale'):
                bad.pop(key)
                changes.append({'op': 'add', 'path': f'/{key}', 'value': good[key]})
            for i, assumption in enumerate(bad['assumptions']):
                assumption['id'] = assumption.pop('assumption_id')
                assumption['evidence_refs'] = refs
                changes.extend([{'op': 'remove', 'path': f'/assumptions/{i}/id'},
                    {'op': 'remove', 'path': f'/assumptions/{i}/evidence_refs'},
                    {'op': 'add', 'path': f'/assumptions/{i}/assumption_id', 'value': f'A{i}'}])
            for i, challenge in enumerate(bad['challenges']):
                challenge['claim'] = challenge.pop('statement')
                challenge['challenge'] = '错误的字段名称'
                challenge.pop('challenge_id')
                challenge.pop('resolution_evidence_needed')
                changes.extend([{'op': 'remove', 'path': f'/challenges/{i}/claim'},
                    {'op': 'remove', 'path': f'/challenges/{i}/challenge'}])
                for key in ('statement', 'challenge_id', 'resolution_evidence_needed'):
                    changes.append({'op': 'add', 'path': f'/challenges/{i}/{key}', 'value': good['challenges'][i][key]})
            bad['evidence_refs'] = [{'evidence_id': ref} for ref in refs]
            changes.extend({'op': 'replace', 'path': f'/evidence_refs/{i}', 'value': ref} for i, ref in enumerate(refs))
            self.assertEqual(len(changes), 32)
            findings = schema_issue_locations(bad, view['output_schema'])
            self.assertEqual(len({item['path'] for item in findings}), 32)
            stop = {**start, 'hook_event_name': 'SubagentStop', 'stop_hook_active': False}
            first, feedback = handle_hook_event({**stop, 'last_assistant_message': json.dumps(bad)}, environ=env)
            self.assertEqual(first['output_capture']['repair_state'], 'REPAIR_REQUESTED', first)
            repair = json.loads(feedback['reason'])
            self.assertNotIn('original_draft', repair)
            original_path = run / first['output_capture']['raw_path']
            original_bytes = original_path.read_bytes()
            gate_hash = file_hash(run / 'evidence/gate.json')
            revised, response = handle_hook_event({**stop, 'last_assistant_message': json.dumps({
                'base_draft_ref': repair['base_draft_ref'], 'changes': changes})}, environ=env)
            self.assertEqual(revised['output_capture']['status'], 'SAVED', revised)
            self.assertEqual(response, {})
            self.assertEqual(original_path.read_bytes(), original_bytes)
            self.assertEqual(file_hash(run / 'evidence/gate.json'), gate_hash)
            self.assertEqual(finalize_skeptic_phase(ROOT, run)['status'], 'PASSED')
            third, _ = handle_hook_event({**stop, 'last_assistant_message': json.dumps(good)}, environ=env)
            self.assertEqual(third['output_capture']['failure_code'], 'LOCAL_REVISION_LIMIT_EXHAUSTED')

    def test_alb_forward_actual_gate_enters_independent_first_pass_without_holding(self):
        with tempfile.TemporaryDirectory() as temp:
            run = prepare_complete_forward(Path(temp), single_stock=True)
            forward = validate_forward_gate(ROOT, run)
            self.assertEqual(forward['common_stock_security_ids'], ['US:COMMON_STOCK:ALB'])
            prepared = prepare_skeptic_phase(ROOT, run)
            self.assertEqual(prepared['task_count'], 1)
            index = json.loads((run / 'research/skeptic/dispatch-index.json').read_text())
            packet = build_skeptic_dispatch_packet(ROOT, run, index['tasks'][0]['task_name'])
            first = packet['agent_input']
            self.assertEqual(first['security_id'], 'US:COMMON_STOCK:ALB')
            for key in ('forward_bundle_hash', 'reports', 'unresolved_cross_dimension_questions', 'portfolio_hash'):
                self.assertNotIn(key, first)
            self.assertFalse((run / 'audit/portfolio-handoff.json').exists())
            task = index['tasks'][0]
            invocation = json.loads((run / task['invocation_ref']).read_text())
            evidence_id = task['allowed_evidence_ids'][0]
            report = {'schema_version': 'counter-thesis-report/2.1.0', 'run_id': index['run_id'],
                'invocation_id': task['invocation_id'], 'status': 'LOW_CONFIDENCE', 'agent': 'runtime_skeptic',
                'mode': 'INDEPENDENT_FIRST_PASS', 'scope': 'US:COMMON_STOCK:ALB 的合成独立反证接缝',
                'challenges': [{'challenge_id': 'synthetic-counter', 'statement': '单期营收不足以验证持续性。',
                    'evidence_refs': [evidence_id], 'assumption_ids': [], 'resolution_evidence_needed': ['后续可比期间']}],
                'assumptions': [], 'evidence_refs': [evidence_id], 'counter_evidence_refs': [],
                'uncertainties': ['测试没有真实经济含义'], 'data_gaps': ['合成资料仅有单期营收'],
                'invalidation_conditions': ['后续资料验证持续性'], 'confidence': 0.3,
                'confidence_rationale': '仅验证交付，不验证投资质量。',
                'skill_execution': invocation['skill_execution'], 'artifact_refs': []}
            environment = {'STOCK_AGENT_RUN_DIR': str(run),
                'STOCK_AGENT_SUBAGENT_EVENT_LOG': str(run / 'invocation/skeptic/subagent-events.jsonl'),
                'STOCK_AGENT_SUBAGENT_DISPATCH_LOG': str(run / 'invocation/skeptic/subagent-dispatches.jsonl'),
                'STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS': 'runtime_skeptic',
                'STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE': 'independent-skeptic-runtime/1.0.0',
                'STOCK_AGENT_RESEARCH_TASK_NAME': task['task_name']}
            dispatched, _ = handle_hook_event({'hook_event_name': 'PreToolUse', 'session_id': 'synthetic-parent',
                'turn_id': 'synthetic-turn', 'tool_name': 'spawn_agent', 'tool_use_id': 'synthetic-spawn',
                'cwd': str(ROOT / 'product'), 'model': 'gpt-5.6-terra', 'permission_mode': 'workspace-write',
                'tool_input': {'agent_type': 'runtime_skeptic', 'task_name': task['task_name'],
                    'fork_turns': 'none', 'message': '启动冻结的独立反证研究，等待 Hook 输入。'}}, environ=environment)
            self.assertEqual(dispatched['decision'], 'ALLOW')
            start = {'hook_event_name': 'SubagentStart', 'session_id': 'synthetic-parent', 'turn_id': 'synthetic-turn',
                'agent_id': 'synthetic-skeptic', 'agent_type': 'runtime_skeptic', 'model': 'gpt-5.6-terra',
                'cwd': str(ROOT / 'product'), 'permission_mode': 'read-only'}
            delivered, response = handle_hook_event(start, environ=environment)
            self.assertEqual(delivered['context_binding']['status'], 'DELIVERED')
            wire = response['hookSpecificOutput']['additionalContext']
            view = json.loads(wire)
            self.assertEqual(list(view)[:3], ['tool_context', 'identity', 'task_prompt'])
            self.assertLess(wire.index('required_identity_arguments'), wire.index('allowed_evidence_ids'))
            from product.runtime.independent_skeptic_stage import skeptic_model_packet
            from product.runtime.invocation import compact_specialist_schema
            expected_view = skeptic_model_packet(packet)
            expected_view['output_schema'] = compact_specialist_schema(
                expected_view['output_schema'], expected_view['allowed_evidence_ids'],
                evidence_schema=expected_view['output_schema']['properties']['evidence_refs']['items'])
            expected_view['agent_input'].pop('allowed_evidence_ids')
            self.assertEqual(view, expected_view)
            self.assertLess(wire.index('"required"'), wire.index('"start_context_evidence_id":'))
            from product.runtime.independent_skeptic_stage import serialize_skeptic_dispatch_context
            before_packet = copy.deepcopy(packet)
            self.assertEqual(json.loads(serialize_skeptic_dispatch_context(packet)), view)
            self.assertEqual(packet, before_packet)
            mismatched_view = skeptic_model_packet(packet)
            mismatched_view['agent_input']['allowed_evidence_ids'] = ['e.foreign']
            with patch('product.runtime.independent_skeptic_stage.skeptic_model_packet', return_value=mismatched_view):
                with self.assertRaisesRegex(IndependentSkepticStageError, 'COUNTER_CONTEXT_ALLOWED_SET_MISMATCH'):
                    serialize_skeptic_dispatch_context(packet)
            self.assertIn('输出 JSON 不填这些身份', view['task_prompt'])
            self.assertIn('两者均空会被既有 UNGROUNDED_CHALLENGE 门禁拒绝', view['task_prompt'])
            self.assertIn('纯资料缺口或无法形成反证写入 data_gaps/uncertainties', view['task_prompt'])
            self.assertIn('尚未查询也不等于来源没有该数据', view['task_prompt'])
            self.assertNotIn('及 agent_input.allowed_evidence_ids', view['task_prompt'])
            # Use only the actual Hook-delivered identity and reference, not
            # test-side invocation knowledge, through the real stdio server.
            from tests.test_task_bound_research_tools import TaskBoundResearchToolsTests
            caller = TaskBoundResearchToolsTests()
            catalog_arguments = {**view['tool_context']['required_identity_arguments'], 'view': 'records', 'limit': 1}
            from product.runtime.nested_codex import build_nested_codex_command
            command = build_nested_codex_command(codex_binary='codex', product_root=ROOT / 'product',
                run_dir=run, model='gpt-5.6-terra', sqlite_home=run / 'test-sqlite', log_dir=run / 'test-log',
                final_message_path=run / 'test-final', hook_recorder_path=ROOT / 'product/runtime/codex_hook_recorder.py',
                fixture_mcp_run_dir=run, fixture_mcp_skeptic_dispatch_index='research/skeptic/dispatch-index.json')
            transport = tomllib.loads(next(item for item in command if item.startswith('mcp_servers.fixture_runtime=')))['mcp_servers']['fixture_runtime']
            self.assertIn('evidence_catalog', transport['enabled_tools'])
            self.assertIn('research_task_state', transport['enabled_tools'])
            requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'evidence_catalog', 'arguments': catalog_arguments}},
                {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'query', 'arguments': {
                    **view['tool_context']['required_identity_arguments'], 'evidence_ids': view['allowed_evidence_ids'][:1]}}},
                {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'research_task_state', 'arguments': {}}}]
            # Execute only the exact generated MCP transport; never start codex or a model.
            completed = subprocess.run([transport['command'], *transport['args']], cwd=transport['cwd'],
                env={**os.environ, **transport['env'], 'PYTHONDONTWRITEBYTECODE': '1'},
                input='\n'.join(json.dumps(request) for request in requests) + '\n', text=True,
                capture_output=True, timeout=15)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            responses = {r['id']: r for r in map(json.loads, completed.stdout.splitlines())}
            advertised = {tool['name'] for tool in responses[1]['result']['tools']}
            self.assertIn('evidence_catalog', advertised & set(transport['enabled_tools']))
            self.assertFalse(responses[2].get('result', {}).get('isError', False), responses[2])
            self.assertNotIn('error', responses[2])
            self.assertNotIn('error', responses[3])
            self.assertNotIn('error', responses[4])
            state = responses[4]['result']['structuredContent']
            self.assertEqual(state['schema_version'], 'independent-skeptic-task-state/1.0.0')
            self.assertEqual(state['expected'], 1)  # Never return the already completed 8 forward tasks.
            self.assertFalse(state['all_tasks_terminal'])
            catalog = caller.call(run, 'evidence_catalog', catalog_arguments)
            self.assertNotIn('error', catalog, catalog)
            metadata = catalog['result']['structuredContent']
            self.assertFalse(metadata['facts_read'])
            self.assertEqual(metadata['total'], len(task['allowed_evidence_ids']))
            self.assertEqual(len(metadata['rows']), 1)
            row = metadata['rows'][0]
            self.assertTrue({'source_id', 'as_of', 'retrieved_at', 'semantic_field', 'evidence_id'} <= row.keys())
            self.assertTrue({'value', 'text', 'reports', 'claims'}.isdisjoint(row))
            self.assertIn(row['evidence_id'], view['allowed_evidence_ids'])
            for override in ({'invocation_id': 'wrong'}, {'run_id': 'wrong'}, {'agent': 'runtime_company_analyst'},
                             {'security_id': 'US:COMMON_STOCK:MRVL'}, {'limit': 65}, {'offset': -1},
                             {'semantic_field': 'x', 'semantic_field_prefix': 'x'}):
                self.assertIn('error', caller.call(run, 'evidence_catalog', {**catalog_arguments, **override}))
            from product.runtime.independent_skeptic_stage import read_skeptic_evidence_catalog
            gate = json.loads((run / 'evidence/gate.json').read_text())
            found, offset = [], 0
            while True:
                page = read_skeptic_evidence_catalog(packet, gate, view='records', offset=offset, limit=1)
                found.extend(item['evidence_id'] for item in page['rows'])
                if page['next_offset'] is None:
                    break
                offset = page['next_offset']
            self.assertEqual(set(found), set(view['allowed_evidence_ids']))
            historical = copy.deepcopy(packet)
            historical['invocation'].pop('skeptic_delivery_version')
            with self.assertRaisesRegex(IndependentSkepticStageError, 'NOT_AUTHORIZED'):
                read_skeptic_evidence_catalog(historical, gate)
            arguments = {**view['tool_context']['required_identity_arguments'],
                         'evidence_ids': view['allowed_evidence_ids'][:1]}
            result = caller.call(run, 'query', arguments)
            self.assertNotIn('error', result, result)
            self.assertTrue(result['result']['structuredContent']['evidence'])
            for override in ({'invocation_id': 'wrong'}, {'run_id': 'wrong'},
                             {'agent': 'runtime_company_analyst'}, {'evidence_ids': ['e.foreign']}):
                self.assertIn('error', caller.call(run, 'query', {**arguments, **override}))
            stopped, _ = handle_hook_event({**start, 'hook_event_name': 'SubagentStop', 'stop_hook_active': False,
                'last_assistant_message': json.dumps(semantic_draft(report, run=run, task=task))}, environ=environment)
            self.assertEqual(stopped['output_capture']['status'], 'SAVED', stopped)
            result = finalize_skeptic_phase(ROOT, run)
            self.assertEqual(result['status'], 'PASSED')
            package = json.loads((run / 'research/skeptic/pre-decision-research-package.json').read_text())
            self.assertEqual(package['schema_version'], 'pre-decision-research-package/2.0.0')
            self.assertEqual(package['consumability'], 'DOWNSTREAM_READY')
            self.assertNotIn('portfolio_hash', package)
            from product.runtime.predecision_cio_stage import prepare_predecision_cio_run
            cio = prepare_predecision_cio_run(ROOT, source_run_dir=run, run_dir=Path(temp) / 'cio',
                run_id='synthetic-alb-cio', target_security_id='US:COMMON_STOCK:ALB', model='gpt-6-luna')
            self.assertEqual(cio['actual_level'], 'RESEARCH_SYNTHESIS')

    def test_alb_skeptic_resume_keeps_no_query_failure_and_uses_current_hook_identity(self):
        from tests.test_task_bound_research_tools import TaskBoundResearchToolsTests
        caller = TaskBoundResearchToolsTests()
        with tempfile.TemporaryDirectory() as temp:
            run = prepare_complete_forward(Path(temp), single_stock=True)
            prepare_skeptic_phase(ROOT, run)
            index = read_dispatch_index(run)
            old = index['tasks'][0]
            report = {'status': 'INSUFFICIENT_EVIDENCE', 'mode': 'INDEPENDENT_FIRST_PASS', 'scope': old['security_id'],
                'challenges': [], 'assumptions': [], 'evidence_refs': [], 'counter_evidence_refs': [],
                'uncertainties': ['合成缺口'], 'data_gaps': ['没有查询'], 'invalidation_conditions': [],
                'confidence': 0, 'confidence_rationale': '合成接缝，不代表研究。'}
            def hook_attempt(task, index_ref, parent, draft=None):
                event_root = run / ('invocation/skeptic' if task['attempt'] == 1 else 'invocation/skeptic/attempt-2')
                env = {'STOCK_AGENT_RUN_DIR': str(run),
                    'STOCK_AGENT_SUBAGENT_EVENT_LOG': str(event_root / 'subagent-events.jsonl'),
                    'STOCK_AGENT_SUBAGENT_DISPATCH_LOG': str(event_root / 'subagent-dispatches.jsonl'),
                    'STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS': 'runtime_skeptic',
                    'STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE': 'independent-skeptic-runtime/1.0.0',
                    'STOCK_AGENT_SKEPTIC_DISPATCH_INDEX': index_ref,
                    'STOCK_AGENT_RESEARCH_TASK_NAME': task['task_name']}
                dispatch = {'hook_event_name': 'PreToolUse', 'session_id': parent, 'turn_id': 'turn',
                    'tool_name': 'spawn_agent', 'tool_use_id': parent, 'cwd': str(ROOT / 'product'),
                    'model': 'gpt-5.6-terra', 'permission_mode': 'workspace-write',
                    'tool_input': {'agent_type': 'runtime_skeptic', 'task_name': task['task_name'],
                        'fork_turns': 'none', 'message': '读取冻结首轮上下文。'}}
                self.assertEqual(handle_hook_event(dispatch, environ=env)[0]['decision'], 'ALLOW')
                start = {'hook_event_name': 'SubagentStart', 'session_id': parent, 'turn_id': 'turn',
                    'agent_id': parent + '-child', 'agent_type': 'runtime_skeptic', 'model': 'gpt-5.6-terra',
                    'cwd': str(ROOT / 'product'), 'permission_mode': 'read-only'}
                _, response = handle_hook_event(start, environ=env)
                view = json.loads(response['hookSpecificOutput']['additionalContext'])
                if draft is not None:
                    capture, _ = handle_hook_event({**start, 'hook_event_name': 'SubagentStop',
                        'last_assistant_message': json.dumps(draft), 'stop_hook_active': False}, environ=env)
                    self.assertEqual(capture['output_capture']['status'], 'SAVED', capture)
                return env, start, view
            old_ref = 'research/skeptic/dispatch-index.json'
            _, _, old_view = hook_attempt(old, old_ref, 'first', report)
            first = finalize_skeptic_phase(ROOT, run)
            self.assertEqual(first['status'], 'PARTIAL')
            process = run / 'invocation/skeptic/process-result.json'
            process.write_text(json.dumps({'run_id': index['run_id'], 'source_integrity_unchanged': True,
                'stage_status': 'PARTIAL', 'process_exit_code': 0, 'timed_out': False}))
            immutable = [run / old['packet_ref'], run / old['report_ref'],
                run / 'research/skeptic/pre-decision-research-package.json', run / 'evidence/gate.json']
            before = [file_hash(p) for p in immutable]
            resumed = prepare_skeptic_resume(ROOT, run)
            new_index = read_dispatch_index(run, resumed['dispatch_index'])
            task = new_index['tasks'][0]
            env, start, view = hook_attempt(task, resumed['dispatch_index'], 'second')
            self.assertNotIn('forward_bundle_hash', view)
            self.assertNotIn('reports', view['agent_input'])
            args = {**view['tool_context']['required_identity_arguments'],
                    'evidence_ids': view['allowed_evidence_ids'][:1]}
            with patch.dict('os.environ', {'STOCK_AGENT_SKEPTIC_DISPATCH_INDEX': resumed['dispatch_index']}):
                self.assertIn('error', caller.call(run, 'query', {**args,
                    'invocation_id': old_view['identity']['invocation_id']}))
                self.assertIn('error', caller.call(run, 'query', {**args,
                    'evidence_ids': old_view['allowed_evidence_ids'][:1]}))
                result = caller.call(run, 'query', args)
            self.assertNotIn('error', result, result)
            draft = {**report, 'status': 'LOW_CONFIDENCE', 'evidence_refs': args['evidence_ids'],
                'challenges': [{'challenge_id': 'synthetic', 'statement': '单期财务不足以证明持续性。',
                    'evidence_refs': args['evidence_ids'], 'assumption_ids': [],
                    'resolution_evidence_needed': ['可比期间']}], 'confidence': .3}
            capture, _ = handle_hook_event({**start, 'hook_event_name': 'SubagentStop',
                'last_assistant_message': json.dumps(draft), 'stop_hook_active': False}, environ=env)
            self.assertEqual(capture['output_capture']['status'], 'SAVED', capture)
            final = finalize_skeptic_phase(ROOT, run, index_ref=resumed['dispatch_index'])
            self.assertEqual(final['status'], 'PASSED')
            self.assertEqual([file_hash(p) for p in immutable], before)
            package = json.loads((run / final['package_ref']).read_text())
            self.assertEqual(package['consumability'], 'DOWNSTREAM_READY')

    def test_prepared_resume_uses_actual_cli_launch_and_rejects_drift_or_relaunch(self):
        from product.runtime.cli import main
        from product.runtime.independent_skeptic_stage import validate_prepared_skeptic_resume
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as temp:
            run = prepare_complete_forward(Path(temp), single_stock=True)
            prepare_skeptic_phase(ROOT, run)
            first = finalize_skeptic_phase(ROOT, run)
            self.assertEqual(first['status'], 'PARTIAL')
            (run / 'invocation/skeptic').mkdir(parents=True)
            (run / 'invocation/skeptic/process-result.json').write_text(json.dumps({
                'run_id': first['run_id'], 'source_integrity_unchanged': True, 'stage_status': 'PARTIAL'}))
            prepared = prepare_skeptic_resume(ROOT, run)
            index_ref = prepared['dispatch_index']
            index = read_dispatch_index(run, index_ref)
            task = index['tasks'][0]
            frozen = [run / 'evidence/gate.json', run / first['package_ref'], run / index_ref,
                      run / task['packet_ref'], run / task['invocation_ref']]
            before = [file_hash(path) for path in frozen]
            self.assertEqual(validate_prepared_skeptic_resume(ROOT, run, index_ref), prepared)
            self.assertFalse((run / 'research/skeptic/attempts/3').exists())
            for bad_ref in ('../outside.json', str(run / index_ref), 'research/skeptic/dispatch-index.json'):
                with self.subTest(bad_ref=bad_ref), self.assertRaises(IndependentSkepticStageError):
                    validate_prepared_skeptic_resume(ROOT, run, bad_ref)
            for field, value, expected in (
                ('run_id', 'foreign-run', 'COUNTER_DISPATCH_FORWARD_DRIFT'),
                ('gate_hash', '0' * 64, 'COUNTER_DISPATCH_FORWARD_DRIFT'),
                ('previous_package', {**index['previous_package'], 'file_hash': '0' * 64}, 'COUNTER_RESUME_CHAIN_DRIFT'),
            ):
                changed = {**index, field: value}
                changed['index_hash'] = legacy_envelope_hash(changed, hash_field='index_hash')
                (run / index_ref).write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaisesRegex(IndependentSkepticStageError, expected):
                    validate_prepared_skeptic_resume(ROOT, run, index_ref)
                (run / index_ref).write_text(json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
            packet_path = run / task['packet_ref']
            original_packet = packet_path.read_bytes()
            packet_path.write_text('{}')
            with self.assertRaisesRegex(IndependentSkepticStageError, 'COUNTER_PACKET_BINDING_INVALID'):
                validate_prepared_skeptic_resume(ROOT, run, index_ref)
            packet_path.write_bytes(original_packet)
            next_root = run / 'research/skeptic/attempts/3'
            next_root.mkdir()
            with self.assertRaisesRegex(IndependentSkepticStageError, 'COUNTER_PREPARED_ATTEMPT_NOT_LATEST'):
                validate_prepared_skeptic_resume(ROOT, run, index_ref)
            next_root.rmdir()
            report_path = run / task['report_ref']
            report_path.parent.mkdir(parents=True)
            report_path.write_text('{}')
            with self.assertRaisesRegex(IndependentSkepticStageError, 'COUNTER_ALREADY_LAUNCHED'):
                validate_prepared_skeptic_resume(ROOT, run, index_ref)
            report_path.unlink()
            self.assertEqual([file_hash(path) for path in frozen], before)
            # Capture the real generated command, but never start codex or a model.
            with patch('product.runtime.independent_skeptic_stage.subprocess.run',
                       return_value=subprocess.CompletedProcess([], 1, '', 'synthetic stopped process')) as launch, \
                 patch('product.runtime.cli.prepare_skeptic_resume') as prepare, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['resume-independent-skeptic', '--repo', str(ROOT), '--run-dir', str(run),
                                       '--prepared-index', index_ref]), 7)
            prepare.assert_not_called()
            launch.assert_called_once()
            environment = launch.call_args.kwargs['env']
            self.assertEqual(environment['STOCK_AGENT_SKEPTIC_DISPATCH_INDEX'], index_ref)
            self.assertEqual(json.loads(environment['STOCK_AGENT_RESEARCH_TASK_NAMES']), prepared['retry_task_names'])
            command = launch.call_args.args[0]
            transport = tomllib.loads(next(arg for arg in command if arg.startswith('mcp_servers.fixture_runtime=')))['mcp_servers']['fixture_runtime']
            self.assertEqual(transport['env']['STOCK_AGENT_SKEPTIC_DISPATCH_INDEX'], index_ref)
            self.assertIn('evidence_catalog', transport['enabled_tools'])
            self.assertIn('research_task_state', transport['enabled_tools'])
            with self.assertRaisesRegex(IndependentSkepticStageError, 'COUNTER_ALREADY_LAUNCHED'):
                validate_prepared_skeptic_resume(ROOT, run, index_ref)
            self.assertEqual([file_hash(path) for path in frozen], before)
            self.assertFalse(next_root.exists())

    def test_alb_resume_reads_frozen_history_after_role_drift_but_rejects_old_execution(self):
        from product.runtime.independent_skeptic_stage import (
            resolve_skeptic_tool_scope, validate_predecision_package,
        )
        real_resume = prepare_skeptic_resume
        for resource in ('.codex/agents/runtime_skeptic.toml', 'skills/counter-thesis/SKILL.md'):
            with self.subTest(resource=resource), tempfile.TemporaryDirectory() as temp:
                repository = Path(temp) / 'repository'
                shutil.copytree(ROOT / 'product', repository / 'product',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                def resume_after_resource_change(repo, run):
                    index = read_dispatch_index(run)
                    old = index['tasks'][0]
                    package_path = run / 'research/skeptic/pre-decision-research-package.json'
                    package = json.loads(package_path.read_text())
                    frozen = [run / old[key] for key in ('input_ref', 'invocation_ref', 'prompt_ref',
                        'schema_ref', 'packet_ref', 'report_ref')] + [package_path]
                    before = [file_hash(path) for path in frozen]
                    role = repository / 'product' / resource
                    role.write_text(role.read_text() + '\n# synthetic resource revision\n')
                    if resource.endswith('.toml'):
                        version_path = repository / 'product/version-manifest.json'
                        version = json.loads(version_path.read_text())
                        version['resource_hashes']['skeptic_agent'] = file_hash(role)
                        version_path.write_text(json.dumps(version))
                    gate = json.loads((run / 'evidence/gate.json').read_text())
                    validate_predecision_package(repo, run, package, for_execution=False)
                    for key, error in (('prompt_ref', 'COUNTER_ARTIFACT_PROMPT_DRIFT'),
                                       ('schema_ref', 'COUNTER_ARTIFACT_SCHEMA_DRIFT')):
                        artifact = run / old[key]
                        original = artifact.read_bytes()
                        try:
                            artifact.write_bytes(original + b'\n ')
                            with self.assertRaisesRegex(IndependentSkepticStageError, error):
                                validate_predecision_package(repo, run, package, for_execution=False)
                        finally:
                            artifact.write_bytes(original)
                    with self.assertRaises(ValueError):
                        resolve_skeptic_tool_scope(run, run_id=index['run_id'],
                            invocation_id=old['invocation_id'], gate=gate)
                    result = real_resume(repo, run)
                    new = read_dispatch_index(run, result['dispatch_index'])['tasks'][0]
                    invocation = json.loads((run / new['invocation_ref']).read_text())
                    from product.runtime.invocation import verify_invocation_manifest
                    verify_invocation_manifest(repo, invocation,
                        agent_input=json.loads((run / new['input_ref']).read_text()))
                    self.assertEqual(invocation['agent']['sha256'],
                        file_hash(repository / 'product/.codex/agents/runtime_skeptic.toml'))
                    counter_skill = next(item for item in invocation['skills']
                        if item['name'] == 'counter-thesis')
                    self.assertEqual(counter_skill['sha256'],
                        file_hash(repository / 'product/skills/counter-thesis/SKILL.md'))
                    self.assertEqual([file_hash(path) for path in frozen], before)
                    self.assertNotEqual(json.loads((run / old['invocation_ref']).read_text())
                        ['manifest_hash'], invocation['manifest_hash'])
                    return result
                with patch(f'{__name__}.ROOT', repository), patch(
                    f'{__name__}.prepare_skeptic_resume', side_effect=resume_after_resource_change
                ):
                    self.test_alb_skeptic_resume_keeps_no_query_failure_and_uses_current_hook_identity()

    def test_report_requires_actual_same_invocation_query_and_attempt_10_is_valid(self):
        with self.assertRaisesRegex(
            IndependentSkepticStageError, "COUNTER_REPORT_EVIDENCE_NOT_QUERIED:ev-2"
        ):
            validate_report_query_closure(
                {"evidence_refs": ["ev-1", "ev-2"]},
                [{"evidence_ids": ["ev-1"]}],
            )
        self.assertEqual(
            {"ev-1", "ev-2"},
            validate_report_query_closure(
                {"evidence_refs": ["ev-1"], "counter_evidence_refs": ["ev-2"]},
                [{"evidence_ids": ["ev-1", "ev-2"]}],
            ),
        )
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            relative = "research/skeptic/attempts/10/dispatch-index.json"
            index = {
                "schema_version": DISPATCH_VERSION,
                "run_id": "attempt-10-run",
                "attempt": 10,
                "tasks": [],
            }
            index["index_hash"] = canonical_hash(index)
            path = run / relative
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(index), encoding="utf-8")
            self.assertEqual(10, read_dispatch_index(run, relative)["attempt"])

    def test_real_forward_gate_prepares_skeptic_without_mocking_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            run = prepare_complete_forward(Path(temp))
            forward = validate_forward_gate(ROOT, run)
            self.assertEqual("counter-real-forward-run", forward["run_id"])
            prepared = prepare_skeptic_phase(ROOT, run)
            self.assertEqual("PREPARED", prepared["status"])
            self.assertEqual(1, prepared["task_count"])
            agent_input = json.loads(next(
                (run / "research/skeptic/inputs").glob("*.json")
            ).read_text())
            self.assertNotIn("forward_bundle_hash", agent_input)
            self.assertNotIn("unresolved_cross_dimension_questions", agent_input)

    def test_resume_keeps_first_attempt_and_retries_only_unready_security(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            (root / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            (root / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                run_dir=run, run_id="counter-resume-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            security_ids = [item["security_id"] for item in handoff["portfolio"]["positions"]]
            bundle = {"run_id": "counter-resume-run", "common_stock_security_ids": security_ids,
                      "bundle_hash": "b" * 64}
            bundle_path = run / "research/holding-research-bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            (run / "research/holding-research-bundle.md").write_text("正向样例", encoding="utf-8")
            fake_forward = {
                "run_id": "counter-resume-run", "decision_cutoff": gate["decision_cutoff"],
                "gate_hash": json.loads((run / "evidence/gate.json").read_text())["bundle_hash"],
                "bundle_hash": bundle["bundle_hash"], "bundle_file_hash": file_hash(bundle_path),
                "common_stock_security_ids": security_ids,
            }
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                prepare_skeptic_phase(ROOT, run)
            original_index = json.loads((run / "research/skeptic/dispatch-index.json").read_text())
            first = original_index["tasks"][0]
            invocation = json.loads((run / first["invocation_ref"]).read_text())
            evidence_id = first["allowed_evidence_ids"][0]
            report = {
                "schema_version": "counter-thesis-report/2.1.0", "run_id": "counter-resume-run",
                "invocation_id": first["invocation_id"], "status": "COMPLETE",
                "agent": "runtime_skeptic", "mode": "INDEPENDENT_FIRST_PASS",
                "scope": first["security_id"], "challenges": [], "assumptions": [],
                "evidence_refs": [evidence_id], "counter_evidence_refs": [],
                "uncertainties": [], "data_gaps": [], "invalidation_conditions": [],
                "confidence": 0.5, "confidence_rationale": "测试引用当前证据。",
                "skill_execution": invocation["skill_execution"], "artifact_refs": [],
            }
            capture_skeptic_report(
                ROOT, run, task_name=first["task_name"], raw_message=json.dumps(semantic_draft(report, run=run, task=first)),
                model="gpt-5.6-terra",
            )
            event_dir = run / "invocation/skeptic"
            event_dir.mkdir(parents=True)
            (event_dir / "subagent-dispatches.jsonl").write_text(
                json.dumps({"decision": "ALLOW", "task_name": first["task_name"]}) + "\n", encoding="utf-8"
            )
            (event_dir / "subagent-events.jsonl").write_text("\n".join(json.dumps(item) for item in [{
                "hook_event_name": "SubagentStart", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic", "context_binding": {
                    "status": "DELIVERED", "invocation_id": first["invocation_id"],
                },
            }, {
                "hook_event_name": "SubagentStop", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic", "output_binding": {"invocation_id": first["invocation_id"]},
                "output_capture": {"status": "SAVED", "output_hash": canonical_hash(report)},
            }]) + "\n", encoding="utf-8")
            tool_event = {
                "adapter_version": "fixture-gate-scoped/2.3.0", "run_id": "counter-resume-run",
                "agent": "runtime_skeptic", "invocation_id": first["invocation_id"],
                "tool": "fixture_evidence.query", "evidence_ids": [evidence_id],
                "access_mode": "read", "input_hash": "a" * 64, "output_hash": "b" * 64,
            }
            tool_event["event_hash"] = canonical_hash(tool_event)
            (run / "events/mcp").mkdir(parents=True)
            (run / "events/mcp/events.jsonl").write_text(json.dumps(tool_event) + "\n", encoding="utf-8")
            successful_report_hash = file_hash(run / first["report_ref"])
            successful_invocation_hash = file_hash(run / first["invocation_ref"])
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                partial = finalize_skeptic_phase(ROOT, run)
            self.assertEqual("PARTIAL", partial["status"])
            (run / "invocation/skeptic").mkdir(parents=True, exist_ok=True)
            (run / "invocation/skeptic/process-result.json").write_text(json.dumps({
                "run_id": "counter-resume-run", "source_integrity_unchanged": True,
                "stage_status": "PARTIAL",
            }), encoding="utf-8")
            original_package_hash = file_hash(run / "research/skeptic/pre-decision-research-package.json")
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                resumed = prepare_skeptic_resume(ROOT, run)
            self.assertEqual(2, resumed["attempt"])
            self.assertEqual([original_index["tasks"][1]["task_name"]], resumed["retry_task_names"])
            latest = json.loads((run / resumed["dispatch_index"]).read_text())
            self.assertEqual(2, latest["attempt"])
            self.assertEqual(first, latest["tasks"][0])
            from product.runtime.independent_skeptic_stage import validate_prepared_skeptic_resume
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                checked = validate_prepared_skeptic_resume(ROOT, run, resumed['dispatch_index'])
            self.assertEqual(checked['retry_task_names'], [original_index['tasks'][1]['task_name']])
            self.assertEqual(2, latest["tasks"][1]["attempt"])
            self.assertEqual(successful_report_hash, file_hash(run / first["report_ref"]))
            self.assertEqual(successful_invocation_hash, file_hash(run / first["invocation_ref"]))
            self.assertEqual(original_package_hash, file_hash(run / "research/skeptic/pre-decision-research-package.json"))
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                with self.assertRaisesRegex(IndependentSkepticStageError, "COUNTER_INPUT_INVALID"):
                    prepare_skeptic_resume(ROOT, run)
            second = latest["tasks"][1]
            old_second = original_index["tasks"][1]
            old_packet = build_skeptic_dispatch_packet(ROOT, run, old_second["task_name"])
            new_packet = build_skeptic_dispatch_packet(ROOT, run, second["task_name"], index_ref=resumed["dispatch_index"])
            self.assertNotEqual(old_packet["reference_map"]["map_hash"], new_packet["reference_map"]["map_hash"])
            self.assertTrue(set(old_packet["reference_map"]["evidence"]).isdisjoint(new_packet["reference_map"]["evidence"]))
            tool = StatelessFixtureTools(default_run_dir=run)
            with patch.dict("os.environ", {"STOCK_AGENT_SKEPTIC_DISPATCH_INDEX": resumed["dispatch_index"]}):
                identity = {"run_id": "counter-resume-run", "agent": "runtime_skeptic", "invocation_id": second["invocation_id"]}
                with self.assertRaisesRegex(ValueError, "MULTIDIMENSIONAL_REFERENCE_UNKNOWN"):
                    tool.query(**identity, evidence_ids=[next(iter(old_packet["reference_map"]["evidence"]))])
                result = tool.query(**identity, evidence_ids=list(new_packet["reference_map"]["evidence"]))
                self.assertEqual(set(new_packet["reference_map"]["evidence"]), {fact["evidence_id"] for fact in result["evidence"]})
            retry_invocation = json.loads((run / second["invocation_ref"]).read_text())
            retry_evidence_id = second["allowed_evidence_ids"][0]
            retry_report = {
                **report, "invocation_id": second["invocation_id"],
                "scope": second["security_id"], "evidence_refs": [retry_evidence_id],
                "skill_execution": retry_invocation["skill_execution"],
            }
            capture_skeptic_report(
                ROOT, run, task_name=second["task_name"], raw_message=json.dumps(semantic_draft(retry_report, run=run, task=second, index_ref=resumed["dispatch_index"])),
                model="gpt-5.6-terra", index_ref=resumed["dispatch_index"],
            )
            retry_events = run / "invocation/skeptic/attempt-2"
            retry_events.mkdir(parents=True)
            (retry_events / "subagent-dispatches.jsonl").write_text(
                json.dumps({"decision": "ALLOW", "task_name": second["task_name"]}) + "\n", encoding="utf-8"
            )
            (retry_events / "subagent-events.jsonl").write_text("\n".join(json.dumps(item) for item in [{
                "hook_event_name": "SubagentStart", "child_session_id": "child-2",
                "agent_type": "runtime_skeptic", "context_binding": {
                    "status": "DELIVERED", "invocation_id": second["invocation_id"],
                },
            }, {
                "hook_event_name": "SubagentStop", "child_session_id": "child-2",
                "agent_type": "runtime_skeptic", "output_binding": {"invocation_id": second["invocation_id"]},
                "output_capture": {"status": "SAVED", "output_hash": canonical_hash(retry_report)},
            }]) + "\n", encoding="utf-8")
            retry_event = {
                **tool_event, "invocation_id": second["invocation_id"],
                "evidence_ids": [retry_evidence_id],
            }
            retry_event.pop("event_hash")
            retry_event["event_hash"] = canonical_hash(retry_event)
            with (run / "events/mcp/events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(retry_event) + "\n")
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                completed = finalize_skeptic_phase(ROOT, run, index_ref=resumed["dispatch_index"])
            self.assertEqual("PASSED", completed["status"])
            self.assertEqual(successful_report_hash, file_hash(run / first["report_ref"]))
            self.assertEqual(original_package_hash, file_hash(run / "research/skeptic/pre-decision-research-package.json"))

    def test_finalizer_builds_reference_only_package_and_blocks_hash_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(1)
            gate = gate_for(handoff)
            (root / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            (root / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                run_dir=run, run_id="counter-package-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            security_id = handoff["portfolio"]["positions"][0]["security_id"]
            bundle = {
                "run_id": "counter-package-run", "common_stock_security_ids": [security_id],
                "bundle_hash": "b" * 64,
            }
            bundle_path = run / "research/holding-research-bundle.json"
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            (run / "research/holding-research-bundle.md").write_text("正向测试报告", encoding="utf-8")
            frozen_gate = json.loads((run / "evidence/gate.json").read_text())
            fake_forward = {
                "run_id": "counter-package-run", "decision_cutoff": gate["decision_cutoff"],
                "gate_hash": frozen_gate["bundle_hash"], "bundle_hash": bundle["bundle_hash"],
                "bundle_file_hash": file_hash(bundle_path),
                "common_stock_security_ids": [security_id],
            }
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                prepare_skeptic_phase(ROOT, run)
            index = json.loads((run / "research/skeptic/dispatch-index.json").read_text())
            task = index["tasks"][0]
            invocation = json.loads((run / task["invocation_ref"]).read_text())
            evidence_id = task["allowed_evidence_ids"][0]
            report = {
                "schema_version": "counter-thesis-report/2.1.0", "run_id": "counter-package-run",
                "invocation_id": task["invocation_id"], "status": "COMPLETE",
                "agent": "runtime_skeptic", "mode": "INDEPENDENT_FIRST_PASS",
                "scope": security_id, "challenges": [{
                    "challenge_id": "challenge-1", "statement": "测试中的可观察风险。",
                    "evidence_refs": [evidence_id], "assumption_ids": [],
                    "resolution_evidence_needed": ["后续正式披露"],
                }],
                "assumptions": [], "evidence_refs": [evidence_id],
                "counter_evidence_refs": [], "uncertainties": [], "data_gaps": [],
                "invalidation_conditions": ["正式披露否定风险"], "confidence": 0.6,
                "confidence_rationale": "已核验当前事实。",
                "skill_execution": invocation["skill_execution"], "artifact_refs": [],
            }
            capture_skeptic_report(
                ROOT, run, task_name=task["task_name"],
                raw_message=json.dumps(semantic_draft(report, run=run, task=task)), model="gpt-5.6-terra",
            )
            event_dir = run / "invocation/skeptic"
            event_dir.mkdir(parents=True)
            (event_dir / "subagent-dispatches.jsonl").write_text(json.dumps({
                "decision": "ALLOW", "task_name": task["task_name"],
            }) + "\n", encoding="utf-8")
            events = [{
                "hook_event_name": "SubagentStart", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic",
                "context_binding": {"status": "DELIVERED", "invocation_id": task["invocation_id"]},
            }, {
                "hook_event_name": "SubagentStop", "child_session_id": "child-1",
                "agent_type": "runtime_skeptic",
                "output_binding": {"invocation_id": task["invocation_id"]},
                "output_capture": {"status": "SAVED", "output_hash": canonical_hash(report)},
            }]
            (event_dir / "subagent-events.jsonl").write_text(
                "\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8"
            )
            event_path = run / "events/mcp/events.jsonl"
            event_path.parent.mkdir(parents=True)
            tool = StatelessFixtureTools(default_run_dir=run)
            result = tool.query(
                run_id="counter-package-run", agent="runtime_skeptic",
                invocation_id=task["invocation_id"], evidence_ids=[evidence_id],
            )
            self.assertEqual(SKEPTIC_ADAPTER_VERSION, result["adapter_version"])
            tool_event = tool.events[-1]
            self.assertEqual(SKEPTIC_ADAPTER_VERSION, tool_event["adapter_version"])
            from product.mcp.provenance import content_hash
            from product.runtime.hashing import legacy_envelope_hash
            from product.runtime.multidimensional_references import translate_references
            packet = build_skeptic_dispatch_packet(ROOT, run, task["task_name"])
            canonical_result = translate_references(result, packet["reference_map"])
            canonical_result["result_hash"] = canonical_result.pop("canonical_result_hash")
            canonical_result.pop("reference_map_hash")
            self.assertEqual(content_hash(canonical_result), tool_event["output_hash"])
            self.assertEqual(
                legacy_envelope_hash(tool_event, hash_field="event_hash"),
                tool_event["event_hash"],
            )
            self.assertEqual(
                content_hash({key: value for key, value in tool_event.items() if key != "event_hash"}),
                tool_event["event_hash"],
            )
            tampered_event = {**tool_event, "tool": "fixture_math.calculate"}
            self.assertNotEqual(
                legacy_envelope_hash(tampered_event, hash_field="event_hash"),
                tampered_event["event_hash"],
            )
            event_path.write_text(json.dumps(tool_event) + "\n", encoding="utf-8")
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                result = finalize_skeptic_phase(ROOT, run)
            self.assertEqual("PASSED", result["status"])
            package = json.loads((run / "research/skeptic/pre-decision-research-package.json").read_text())
            self.assertEqual("DOWNSTREAM_READY", package["consumability"])
            self.assertNotIn("challenges", package)
            bundle_path.write_text(json.dumps({**bundle, "bundle_hash": "c" * 64}), encoding="utf-8")
            from product.runtime.independent_skeptic_stage import validate_predecision_package
            with self.assertRaisesRegex(IndependentSkepticStageError, "PACKAGE_BINDING_INVALID"):
                validate_predecision_package(ROOT, run, package)

    def test_two_securities_have_distinct_server_side_query_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            handoff = stock_handoff(2)
            gate = gate_for(handoff)
            (root / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            (root / "gate.json").write_text(json.dumps(gate), encoding="utf-8")
            run = root / "run"
            prepare_multidimensional_stage_run(
                ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                run_dir=run, run_id="counter-scope-run", model="gpt-5.6-terra",
                stage="INDEPENDENT_COUNTER_THESIS_RESEARCH",
            )
            fake_forward = {
                "run_id": "counter-scope-run", "decision_cutoff": gate["decision_cutoff"],
                "gate_hash": json.loads((run / "evidence/gate.json").read_text())["bundle_hash"],
                "bundle_hash": "b" * 64, "bundle_file_hash": "c" * 64,
                "common_stock_security_ids": [
                    item["security_id"] for item in handoff["portfolio"]["positions"]
                ],
            }
            with patch("product.runtime.independent_skeptic_stage.validate_forward_gate", return_value=fake_forward):
                prepare_skeptic_phase(ROOT, run)
            index = json.loads((run / "research/skeptic/dispatch-index.json").read_text())
            first, second = index["tasks"]
            self.assertEqual(2, len(index["tasks"]))
            own_id = first["allowed_evidence_ids"][0]
            other_id = second["allowed_evidence_ids"][0]
            tool = StatelessFixtureTools(default_run_dir=run)
            identity = {
                "run_id": "counter-scope-run", "agent": "runtime_skeptic",
                "invocation_id": first["invocation_id"],
            }
            self.assertEqual(
                next(iter(build_skeptic_dispatch_packet(ROOT, run, first["task_name"])["reference_map"]["evidence"])),
                tool.query(**identity, evidence_ids=[own_id])["evidence"][0]["evidence_id"]
            )
            self.assertEqual(
                "ratio", tool.calculate(
                    **identity, calculation_id="own-ratio", operation="ratio",
                    evidence_ids=first["allowed_evidence_ids"],
                )["operation"]
            )
            with self.assertRaisesRegex(ToolAccessError, "INVOCATION_EVIDENCE_NOT_AUTHORIZED"):
                tool.query(**identity, evidence_ids=[other_id])
            with self.assertRaisesRegex(ToolAccessError, "INVOCATION_EVIDENCE_NOT_AUTHORIZED"):
                tool.calculate(
                    **identity, calculation_id="cross-ratio", operation="ratio",
                    evidence_ids=[own_id, other_id],
                )
            with self.assertRaisesRegex(ToolAccessError, "INVOCATION_EVIDENCE_NOT_AUTHORIZED"):
                tool.query(**{**identity, "invocation_id": second["invocation_id"]}, evidence_ids=[own_id])
            with self.assertRaises((ToolAccessError, ValueError)):
                tool.query(**{**identity, "invocation_id": "invented"}, evidence_ids=[own_id])
            with self.assertRaisesRegex(ToolAccessError, "RUN_DIRECTORY_OVERRIDE_REJECTED"):
                tool.query(**identity, run_dir=str(root), evidence_ids=[own_id])

            invocation = json.loads((run / first["invocation_ref"]).read_text())
            report = {
                "schema_version": "counter-thesis-report/2.1.0",
                "run_id": "counter-scope-run", "invocation_id": first["invocation_id"],
                "status": "LOW_CONFIDENCE", "agent": "runtime_skeptic",
                "mode": "INDEPENDENT_FIRST_PASS",
                "scope": f"{first['security_id']} 的独立反证",
                "challenges": [{
                    "challenge_id": "challenge-1", "statement": "现金流压力可能限制投资弹性。",
                    "evidence_refs": [own_id], "assumption_ids": ["future-cost"],
                    "resolution_evidence_needed": ["未来债务到期明细"],
                }],
                "assumptions": [{"assumption_id": "future-cost", "statement": "假设未来融资成本上行。"}],
                "evidence_refs": [own_id], "counter_evidence_refs": [],
                "uncertainties": ["融资路径尚不确定"], "data_gaps": ["缺债务明细"],
                "invalidation_conditions": ["融资成本下降"],
                "confidence": 0.35, "confidence_rationale": "仅有一项当前事实。",
                "skill_execution": invocation["skill_execution"], "artifact_refs": [],
            }
            captured = capture_skeptic_report(
                ROOT, run, task_name=first["task_name"],
                raw_message=json.dumps(semantic_draft(report, run=run, task=first)), model="gpt-5.6-terra",
            )
            self.assertEqual("SAVED", captured["status"])
            markdown = (run / captured["markdown_path"]).read_text()
            self.assertIn("现金流压力", markdown)
            self.assertIn("假设未来融资成本上行", markdown)
            self.assertIn(own_id, markdown)

            hook_env = {
                "STOCK_AGENT_RUN_DIR": str(run),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(run / "invocation/skeptic/subagent-events.jsonl"),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(run / "invocation/skeptic/subagent-dispatches.jsonl"),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_skeptic",
                "STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE": "independent-skeptic-runtime/1.0.0",
                "STOCK_AGENT_RESEARCH_TASK_NAME": first["task_name"],
            }
            dispatch_payload = {
                "hook_event_name": "PreToolUse", "session_id": "parent-1",
                "turn_id": "turn-1", "tool_name": "spawn_agent", "tool_use_id": "tool-1",
                "cwd": str(ROOT / "product"), "model": "gpt-5.6-terra",
                "permission_mode": "workspace-write",
                "tool_input": {
                    "agent_type": "runtime_skeptic", "task_name": first["task_name"],
                    "fork_turns": "none",
                    "message": "启动本次冻结的独立反证研究；完整上下文由 SubagentStart Hook 交付。",
                },
            }
            decision, _ = handle_hook_event(dispatch_payload, environ=hook_env)
            self.assertEqual("ALLOW", decision["decision"])
            start_payload = {
                "hook_event_name": "SubagentStart", "session_id": "parent-1",
                "turn_id": "turn-1", "agent_id": "child-1",
                "agent_type": "runtime_skeptic", "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"), "permission_mode": "read-only",
            }
            start, context = handle_hook_event(start_payload, environ=hook_env)
            self.assertEqual("DELIVERED", start["context_binding"]["status"])
            delivered = context["hookSpecificOutput"]["additionalContext"]
            self.assertIn(first["invocation_id"], delivered)
            self.assertNotIn("forward_bundle_hash", delivered)

            second_invocation = json.loads((run / second["invocation_ref"]).read_text())
            second_report = copy.deepcopy(report)
            second_report["invocation_id"] = second["invocation_id"]
            second_report["scope"] = f"{second['security_id']} 的独立反证"
            second_report["evidence_refs"] = [other_id]
            second_report["challenges"][0]["evidence_refs"] = [other_id]
            second_report["skill_execution"] = second_invocation["skill_execution"]
            second_env = {**hook_env, "STOCK_AGENT_RESEARCH_TASK_NAME": second["task_name"]}
            second_dispatch = copy.deepcopy(dispatch_payload)
            second_dispatch["session_id"] = "parent-2"
            second_dispatch["tool_input"]["task_name"] = second["task_name"]
            allowed_dispatch, _ = handle_hook_event(second_dispatch, environ=second_env)
            self.assertEqual("ALLOW", allowed_dispatch["decision"])
            second_start = {**start_payload, "session_id": "parent-2", "agent_id": "child-2"}
            handle_hook_event(second_start, environ=second_env)
            second_stop = {
                **second_start, "hook_event_name": "SubagentStop",
                "last_assistant_message": json.dumps(semantic_draft(second_report, run=run, task=second)),
                "stop_hook_active": False,
            }
            stopped, _ = handle_hook_event(second_stop, environ=second_env)
            self.assertEqual("SAVED", stopped["output_capture"]["status"])
            self.assertTrue((run / second["report_ref"]).is_file())

    def test_core_coverage_blocks_failed_core_but_allows_specialist_source_limit(self):
        core = [
            "COMPANY_RESEARCH", "TECHNICAL_STRUCTURE", "FUNDAMENTAL_EVENT",
            "INDUSTRY_COMPARISON", "MACRO_CONTEXT", "MARKET_STATE",
        ]
        bundle = {
            "consumability": "DOWNSTREAM_READY", "common_stock_security_ids": ["US:COMMON_STOCK:MRVL"],
            "coverage": [
                {"security_id": "US:COMMON_STOCK:MRVL", "capability": capability,
                 "status": "COMPLETE", "report_id": f"report:{capability}"}
                for capability in core
            ] + [{
                "security_id": "US:COMMON_STOCK:MRVL", "capability": "RESEARCH_REPORT",
                "status": "SOURCE_LIMITED", "report_id": "report:research",
            }],
        }
        validate_core_coverage(bundle)
        structural = copy.deepcopy(bundle)
        structural["consumability"] = "STRUCTURALLY_CONSUMABLE"
        validate_core_coverage(structural)
        source_limited_core = copy.deepcopy(bundle)
        source_limited_core["coverage"][2]["status"] = "SOURCE_LIMITED"
        validate_core_coverage(source_limited_core)
        for status in ("FAILED", "TIMEOUT", "NOT_RESEARCHED"):
            broken = copy.deepcopy(bundle)
            broken["coverage"][2]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(
                IndependentSkepticStageError, "COUNTER_FORWARD_CORE_NOT_READY"
            ):
                validate_core_coverage(broken)
        missing = copy.deepcopy(bundle)
        missing["coverage"].pop(0)
        with self.assertRaisesRegex(IndependentSkepticStageError, "CORE_COVERAGE_INCOMPLETE"):
            validate_core_coverage(missing)

    def test_gate_scoping_keeps_target_shared_and_frozen_peer_not_other_holding(self):
        gate = {
            "allowed_evidence_ids": ["target", "other", "peer", "macro", "market"],
            "allowed_evidence": [
                {"evidence_id": "target", "security_id": "US:COMMON_STOCK:MRVL"},
                {"evidence_id": "other", "security_id": "US:COMMON_STOCK:MSFT"},
                {"evidence_id": "peer", "security_id": "US:COMMON_STOCK:NVDA"},
                {"evidence_id": "macro", "security_id": "US:MACRO"},
                {"evidence_id": "market", "security_id": "US:MARKET"},
            ],
        }
        self.assertEqual(
            ["macro", "market", "peer", "target"],
            scope_evidence_ids(
                gate, security_id="US:COMMON_STOCK:MRVL",
                shared_evidence_ids=["macro", "market", "other"],
                peer_security_ids=["US:COMMON_STOCK:NVDA"],
            ),
        )
        with self.assertRaisesRegex(IndependentSkepticStageError, "OUTSIDE_GATE"):
            scope_evidence_ids(gate, security_id="US:COMMON_STOCK:MRVL", shared_evidence_ids=["unknown"])

    def test_first_pass_is_exact_allowlist_not_recursive_denylist(self):
        request = {"request_id": "request-1", "research_question": "分析风险。", "holding_horizon": None}
        gate = {"decision_cutoff": "2026-09-01T00:00:00Z", "bundle_hash": "a" * 64}
        value = build_first_pass_input(
            run_id="run-1", security_id="US:COMMON_STOCK:MRVL", request=request,
            gate=gate, allowed_ids=["ev-1"],
        )
        self.assertNotIn("portfolio_summary", value)
        for key in ("bundle_hash", "unresolved_cross_dimension_questions", "artifact_refs", "analyst_summary"):
            broken = {**value, key: {"nested": "polluted"}}
            with self.subTest(key=key), self.assertRaisesRegex(
                IndependentSkepticStageError, "CONTEXT_ISOLATION_VIOLATION"
            ):
                validate_first_pass_input(broken, allowed_ids=["ev-1"])


if __name__ == "__main__":
    unittest.main()
