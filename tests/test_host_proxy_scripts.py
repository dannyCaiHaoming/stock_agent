"""宿主代理适配的零网络、零 LLM 合约测试。"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import runpy
import io
import contextlib
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class HostProxyTests(unittest.TestCase):
    def detect(self, settings, vpn='', route=''):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            # 测试命令只输出合成系统状态，不调用真实网络或模型。
            for name, body in {
                'scutil': 'if [ "$1" = "--proxy" ]; then printf "%s\\n" "$TEST_PROXY"; else printf "%s\\n" "$TEST_VPN"; fi',
                'networksetup': 'printf "Enabled: No\\nServer: localhost\\nPort: 54321\\n"',
                'lsof': 'printf "unrelated 1 user TCP 127.0.0.1:54321 (LISTEN)\\n"',
                'route': 'printf "%s\\n" "$TEST_ROUTE"',
            }.items():
                path = base / name
                path.write_text('#!/bin/bash\n' + body + '\n')
                path.chmod(0o700)
            result = subprocess.run(
                ['bash', str(ROOT / 'scripts/detect-host-proxy.sh'), str(base / 'evidence')],
                env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                     'TEST_PROXY': settings, 'TEST_VPN': vpn, 'TEST_ROUTE': route},
                text=True, capture_output=True, check=True,
            )
            self.assertTrue((base / 'evidence/wifi-http.exit').exists())
            return dict(line.split('=', 1) for line in result.stdout.splitlines())

    def test_http_preserves_distinct_https(self):
        value = self.detect('HTTPEnable : 1\nHTTPProxy : localhost\nHTTPPort : 23456\nHTTPSEnable : 1\nHTTPSProxy : localhost\nHTTPSPort : 23457')
        self.assertEqual(value['PROXY_MODE'], 'SYSTEM_HTTP_PROXY')
        self.assertEqual(value['HTTP_PROXY_URL'], 'http://localhost:23456')
        self.assertEqual(value['HTTPS_PROXY_URL'], 'http://localhost:23457')

    def test_http_only_supplies_https(self):
        value = self.detect('HTTPEnable : 1\nHTTPProxy : localhost\nHTTPPort : 23456')
        self.assertEqual(value['HTTP_PROXY_URL'], value['HTTPS_PROXY_URL'])

    def test_https_only(self):
        value = self.detect('HTTPSEnable : 1\nHTTPSProxy : localhost\nHTTPSPort : 23457')
        self.assertEqual(value['PROXY_MODE'], 'SYSTEM_HTTPS_PROXY')

    def test_socks_no_http_guess(self):
        value = self.detect('SOCKSEnable : 1\nSOCKSProxy : 127.0.0.1\nSOCKSPort : 23458')
        self.assertEqual(value['PROXY_MODE'], 'SYSTEM_SOCKS_PROXY')
        self.assertEqual(value['ALL_PROXY_URL'], 'socks5h://127.0.0.1:23458')
        self.assertNotIn('HTTP_PROXY_URL', value)

    def test_disabled_stale_values_and_listener_do_not_select_port(self):
        value = self.detect('HTTPEnable : 0\nHTTPProxy : localhost\nHTTPPort : 54321')
        self.assertEqual(value['PROXY_MODE'], 'UNKNOWN')
        self.assertNotIn('PROXY_PORT', value)

    def test_tunnel_requires_positive_evidence(self):
        for vpn, route in [('(Connected) VPN', ''), ('', 'interface: utun7')]:
            value = self.detect('HTTPEnable : 0', vpn, route)
            self.assertEqual(value['PROXY_MODE'], 'TUN_OR_VPN')
            self.assertEqual(value['LOCAL_PROXY_PORT'], 'NONE')
            self.assertNotIn('ALL_PROXY_URL', value)

    def test_invalid_endpoint_fails_closed(self):
        value = self.detect('HTTPEnable : 1\nHTTPProxy : localhost\nHTTPPort : 99999')
        self.assertEqual(value['PROXY_MODE'], 'UNKNOWN')

    def test_entry_reuses_launcher_and_terminal_check(self):
        text = (ROOT / 'scripts/run-product-smoke.sh').read_text()
        self.assertIn('nested-codex-smoke', text)
        self.assertIn('check-run --run-dir', text)
        self.assertIn('--resume-multidimensional-run', text)
        self.assertIn('--resume-multidimensional-task', text)
        self.assertIn('--task-name "$resume_multidimensional_task"', text)
        self.assertIn('launch-multidimensional-research', text)
        resume = text.index('if [ -n "$resume_multidimensional_run" ]')
        default_prepare = text.index('if [ -z "$prepared_run" ]')
        self.assertLess(resume, default_prepare)
        self.assertNotIn('dangerously-bypass', text)
        self.assertNotIn('network_proxy=false', text)

    def test_required_materials_guard_precedes_formal_model_launch(self):
        text = (ROOT / 'scripts/run-product-smoke.sh').read_text()
        # Check the original holding branch, not the earlier single-stock path.
        self.assertIn('--require-materials) require_materials=1', text)
        text = text[text.index('if [ "$stage" = "common-stock-research" ] || [ "$multidimensional_stage" = "1" ]; then'):]
        self.assertIn('--max-concurrency 2', text)
        self.assertIn('REQUIRED_PEER_GATE_MISSING', text)
        self.assertIn('REQUIRED_PEER_EVIDENCE_MISSING', text)
        self.assertIn('require_complete_research_materials_stage(Path(sys.argv[2]))', text)
        self.assertIn('set -- "$@" --base-gate "$base_stock_gate"', text)
        self.assertLess(
            text.index('require_complete_research_materials_stage(Path(sys.argv[2]))'),
            text.index('materialize-selected-peers'),
        )
        self.assertLess(
            text.index('REQUIRED_PEER_EVIDENCE_MISSING'),
            text.index('prepare-multidimensional-research'),
        )

    def test_required_materials_failure_does_not_start_formal_research(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            wrapper = base / 'python3'
            wrapper.write_text(
                '#!/bin/bash\n'
                'if [ "$1" = "-" ]; then exec "' + os.sys.executable + '" "$@"; fi\n'
                'printf "%s\\n" "$*" >> "$TEST_COMMAND_LOG"\n'
            )
            wrapper.chmod(0o700)
            scutil = base / 'scutil'
            scutil.write_text(
                '#!/bin/bash\n'
                'if [ "$1" = "--proxy" ]; then '
                'printf "HTTPEnable : 1\\nHTTPProxy : localhost\\nHTTPPort : 23456\\n"; fi\n'
            )
            scutil.chmod(0o700)
            gate = base / 'gate.json'
            gate.write_text(json.dumps({'run_id': 'required-test'}))
            pool = base / 'pool.json'
            pool.write_text('{}')
            log = base / 'commands'
            result = subprocess.run(
                ['bash', str(ROOT / 'scripts/run-product-smoke.sh'), '--stage',
                 'multidimensional-holding-research', '--handoff', str(base / 'handoff.json'),
                 '--gate', str(gate), '--peer-candidates', str(pool),
                 '--require-materials', str(base / 'host')],
                env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                     'TEST_COMMAND_LOG': str(log)},
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            calls = log.read_text().splitlines()
            self.assertTrue(any('launch-research-materials' in call for call in calls))
            self.assertFalse(any('prepare-multidimensional-research' in call for call in calls))
            self.assertFalse(any('launch-multidimensional-research' in call for call in calls))

    def test_initial_targeted_host_entry_routes_to_existing_launcher(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            prepared = base / 'prepared'
            prepared.mkdir()
            wrapper = base / 'python3'
            wrapper.write_text(
                '#!/bin/bash\n'
                'if [ "$1" = "-" ]; then exec "' + sys.executable + '" "$@"; fi\n'
                'printf "%s\\n" "$*" >> "$TEST_COMMAND_LOG"\n'
            )
            wrapper.chmod(0o700)
            scutil = base / 'scutil'
            scutil.write_text(
                '#!/bin/bash\n'
                'if [ "$1" = "--proxy" ]; then '
                'printf "HTTPEnable : 1\\nHTTPProxy : localhost\\nHTTPPort : 23456\\n"; '
                'fi\n'
            )
            scutil.chmod(0o700)
            log = base / 'commands'
            result = subprocess.run(
                ['bash', str(ROOT / 'scripts/run-product-smoke.sh'),
                 '--start-multidimensional-task', str(prepared),
                 'dimension_research_3', str(base / 'host')],
                env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                     'TEST_COMMAND_LOG': str(log)},
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(log.read_text().splitlines()), 1)
            call = log.read_text()
            self.assertIn('launch-multidimensional-research', call)
            self.assertIn('--task-name dimension_research_3 --initial-task', call)

    def test_prepared_skeptic_host_resume_forwards_index_without_prepare_and_preserves_failure(self):
        import sys
        for index_ref in (None, 'research/skeptic/attempts/6/dispatch-index.json'):
            for status in (0, 7):
                with self.subTest(index_ref=index_ref, status=status), tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    prepared = base / 'prepared run'
                    prepared.mkdir()
                    wrapper = base / 'python3'
                    wrapper.write_text('#!/bin/bash\nif [ "$1" = "-" ]; then exec "' + sys.executable + '" "$@"; fi\nprintf "%s\\n" "$*" >> "$TEST_COMMAND_LOG"\nexit "$TEST_STATUS"\n')
                    wrapper.chmod(0o700)
                    scutil = base / 'scutil'
                    scutil.write_text('#!/bin/bash\nif [ "$1" = "--proxy" ]; then printf "HTTPEnable : 1\\nHTTPProxy : localhost\\nHTTPPort : 23456\\n"; fi\n')
                    scutil.chmod(0o700)
                    log = base / 'commands'
                    result = subprocess.run(['bash', str(ROOT / 'scripts/run-product-smoke.sh'),
                        '--resume-independent-skeptic-run', str(prepared),
                        *(['--prepared-index', index_ref] if index_ref else []), str(base / 'host')],
                        env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                             'TEST_COMMAND_LOG': str(log), 'TEST_STATUS': str(status)}, text=True, capture_output=True)
                    self.assertEqual(result.returncode, status, result.stderr)
                    calls = log.read_text().splitlines()
                    self.assertEqual(len(calls), 1)
                    self.assertIn('resume-independent-skeptic', calls[0])
                    self.assertEqual('--prepared-index' in calls[0], index_ref is not None)
                    if index_ref:
                        self.assertTrue(calls[0].endswith('--prepared-index ' + index_ref))
                    self.assertNotIn('prepare-independent-skeptic', calls[0])
                    self.assertNotIn('predecision-cio', calls[0])

    def test_single_stock_entry_captures_complete_scope_and_stops_before_dependents(self):
        import json
        import shlex
        import sys
        for prepare_only, failed_stage in ((True, ''), (False, ''), (False, 'launch-research-materials'), (False, 'launch-independent-skeptic'), (False, 'launch-predecision-cio')):
            with self.subTest(prepare_only=prepare_only, failed_stage=failed_stage), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                wrapper = base / 'python3'
                wrapper_body = base / 'python-wrapper.py'
                wrapper.write_text('#!/bin/bash\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(wrapper_body)) + ' "$@"\n')
                wrapper_body.write_text('''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if args[0] == '-':
    os.execv(sys.executable, [sys.executable, *args])
with open(os.environ['TEST_COMMAND_LOG'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
with open(os.environ['TEST_ENVIRONMENT_LOG'], 'a') as log:
    log.write(json.dumps({'command': args[1], 'host_launch': os.environ.get('STOCK_AGENT_PRODUCT_HOST_LAUNCH')}) + '\\n')
command = args[1]
if command == 'launch-predecision-cio' and os.environ.get('STOCK_AGENT_PRODUCT_HOST_LAUNCH') != '1':
    sys.exit('CIO_HOST_LAUNCH_REQUIRED')
def argument(name):
    return args[args.index(name) + 1]
if command == os.environ.get('TEST_FAIL_STAGE'):
    sys.exit(7)
if command == 'collect-single-stock-data':
    root = Path(argument('--output-dir')); root.mkdir(parents=True)
    request = {'input_kind': 'SINGLE_STOCK_RESEARCH', 'request_hash': 'a'*64,
        'resolved_cutoff': '2026-10-02T00:00:00Z', 'research_question': argument('--question'),
        'security': {'security_id': 'US:COMMON_STOCK:ALB'}}
    (root / 'single-stock-request.json').write_text(json.dumps(request))
elif command == 'prepare-research-materials':
    root = Path(argument('--run-dir')); (root / 'research').mkdir(parents=True)
    model = argument('--model')
    (root / 'run_manifest.json').write_text(json.dumps({'model': model, 'parent_model': model,
        'manifest_hash': 'b'*64}))
    (root / 'research/dispatch-index.json').write_text(json.dumps({'tasks': [{}, {}, {}, {}]}))
elif command == 'freeze-single-stock-data':
    root = Path(argument('--output-dir')); root.mkdir(parents=True)
    (root / 'single-stock-request.json').write_bytes((Path(argument('--data-dir')) / 'single-stock-request.json').read_bytes())
''')
                wrapper.chmod(0o700)
                scutil = base / 'scutil'
                scutil.write_text('#!/bin/bash\nif [ "$1" = "--proxy" ]; then printf "HTTPEnable : 1\\nHTTPProxy : localhost\\nHTTPPort : 23456\\n"; fi\n')
                scutil.chmod(0o700)
                log = base / 'commands'
                bundle = base / 'host'
                args = ['bash', str(ROOT / 'scripts/run-product-smoke.sh'), '--stage', 'single-stock-research',
                    '--single-stock', 'ALB', '--question', '核验雅宝的经营与周期风险', '--through', 'cio']
                if prepare_only:
                    args.append('--prepare-only')
                environment_log = base / 'environment'
                host_environment = {key: value for key, value in os.environ.items()
                    if key != 'STOCK_AGENT_PRODUCT_HOST_LAUNCH'}
                result = subprocess.run([*args, str(bundle)], env={**host_environment,
                    'PATH': str(base) + os.pathsep + os.environ['PATH'], 'TEST_COMMAND_LOG': str(log),
                    'TEST_ENVIRONMENT_LOG': str(environment_log),
                    'TEST_FAIL_STAGE': failed_stage, 'LIVE_SOURCE_ACCESS_FILE': str(base / 'external-config'),
                    'SEC_USER_AGENT': 'synthetic contact@example.invalid', 'RESEARCH_MEMORY_ROOT': str(base / 'memory')},
                    text=True, capture_output=True)
                self.assertEqual(result.returncode, 7 if failed_stage else 0, result.stderr)
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                commands = [item[1] for item in calls]
                environments = [json.loads(line) for line in environment_log.read_text().splitlines()]
                self.assertEqual([item['command'] for item in environments], commands)
                for environment in environments:
                    self.assertEqual(environment['host_launch'],
                        '1' if environment['command'] in ('prepare-predecision-cio', 'launch-predecision-cio', 'check-predecision-cio') else None)
                self.assertEqual(commands[0], 'collect-single-stock-data')
                self.assertIn('--cutoff', calls[0]); self.assertIn('latest', calls[0])
                self.assertIn('ALB', calls[0]); self.assertIn('核验雅宝的经营与周期风险', calls[0])
                for call in calls:
                    self.assertNotIn('--handoff', call)
                    if '--model' in call:
                        self.assertEqual(call[call.index('--model') + 1], 'gpt-6-luna')
                plan = json.loads((bundle / 'single-stock-run-plan.json').read_text())
                self.assertEqual(sum(plan['specialist_call_limits'].values()), 14)
                self.assertEqual(plan['host_parent_limit'], 5)
                self.assertEqual(plan['model'], 'gpt-6-luna')
                if prepare_only:
                    self.assertFalse(any(item.startswith('launch-') for item in commands))
                    self.assertIn('validate-common-stock-research', commands)
                    dimensions = next(item for item in calls if item[1] == 'prepare-multidimensional-research')
                    self.assertEqual(dimensions[dimensions.index('--stage') + 1], 'INDEPENDENT_COUNTER_THESIS_RESEARCH')
                    self.assertNotIn('--task-bound-tools', dimensions)
                elif failed_stage:
                    self.assertEqual(commands[-1], failed_stage)
                    if failed_stage == 'launch-research-materials':
                        self.assertNotIn('freeze-single-stock-data', commands)
                    elif failed_stage == 'launch-independent-skeptic':
                        self.assertNotIn('prepare-predecision-cio', commands)
                    else:
                        self.assertNotIn('check-predecision-cio', commands)
                else:
                    self.assertEqual([item for item in commands if item.startswith('launch-')],
                        ['launch-research-materials', 'launch-common-stock-research',
                         'launch-multidimensional-research', 'launch-independent-skeptic', 'launch-predecision-cio'])
                    self.assertIn('check-predecision-cio', commands)

    def test_research_prepare_defaults_to_pinned_luna_without_model_call(self):
        import json
        import sys
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            wrapper = base / 'python3'
            wrapper.write_text(
                '#!/bin/bash\n'
                'if [ "$1" = "-" ]; then exec "' + sys.executable + '" "$@"; fi\n'
                'printf "%s\\n" "$*" >> "$TEST_COMMAND_LOG"\n'
                'if [ "$2" = "validate-common-stock-research" ]; then echo "{}"; fi\n'
            )
            wrapper.chmod(0o700)
            gate = base / 'gate.json'
            gate.write_text(json.dumps({'run_id': 'luna-test'}))
            log = base / 'commands'
            result = subprocess.run(
                ['bash', str(ROOT / 'scripts/run-product-smoke.sh'),
                 '--stage', 'common-stock-research', '--handoff', str(base / 'handoff.json'),
                 '--gate', str(gate), '--data-preparation', str(base / 'data.json'),
                 '--source-bundle', str(base / 'source.json'), '--question', '研究当前确认的普通股持仓。',
                 '--prepare-only', str(base / 'bundle')],
                env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                     'TEST_COMMAND_LOG': str(log)},
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text().splitlines()
            self.assertTrue(any('prepare-common-stock-research' in call and '--model gpt-6-luna' in call for call in calls))
            self.assertTrue(any('--question 研究当前确认的普通股持仓。' in call for call in calls))

    def test_multidimensional_and_counter_prepare_default_to_luna(self):
        import json
        import sys
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            wrapper = base / 'python3'
            wrapper.write_text(
                '#!/bin/bash\n'
                'if [ "$1" = "-" ]; then exec "' + sys.executable + '" "$@"; fi\n'
                'printf "%s\\n" "$*" >> "$TEST_COMMAND_LOG"\n'
            )
            wrapper.chmod(0o700)
            for name, body in {
                'scutil': 'printf "HTTPEnable : 1\\nHTTPProxy : localhost\\nHTTPPort : 23456\\n"',
                'networksetup': 'printf "Enabled: No\\n"',
                'lsof': 'exit 0',
                'route': 'exit 0',
            }.items():
                path = base / name
                path.write_text('#!/bin/bash\n' + body + '\n')
                path.chmod(0o700)
            gate = base / 'gate.json'
            gate.write_text(json.dumps({'run_id': 'luna-test'}))
            log = base / 'commands'
            for stage, structured in (
                ('multidimensional-holding-research', False),
                ('independent-counter-thesis-research', False),
                ('multidimensional-holding-research', True),
            ):
                with self.subTest(stage=stage, structured=structured):
                    result = subprocess.run(
                        ['bash', str(ROOT / 'scripts/run-product-smoke.sh'), '--stage', stage,
                         '--handoff', str(base / 'handoff.json'), '--gate', str(gate),
                         *(['--structured-report-submission'] if structured else []),
                         str(base / (stage + str(structured)))],
                        env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                             'TEST_COMMAND_LOG': str(log)},
                        text=True, capture_output=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text().splitlines()
            multidimensional = [call for call in calls if 'prepare-multidimensional-research' in call]
            self.assertEqual(len(multidimensional), 3)
            self.assertFalse(any('--structured-report-submission' in call for call in multidimensional[:2]))
            self.assertIn('--structured-report-submission', multidimensional[2])
            self.assertTrue(all('--model gpt-6-luna' in call for call in multidimensional))
            import shlex
            arguments = [shlex.split(call) for call in multidimensional]
            identifiers = [args[args.index('--run-id') + 1] for args in arguments]
            self.assertNotEqual(identifiers[0], identifiers[2])
            self.assertTrue(all(identifier.startswith('host-multidimensional-')
                                for identifier in (identifiers[0], identifiers[2])))
            self.assertEqual(identifiers[1], 'luna-test')  # 反证同批身份契约不变。
            self.assertTrue(all('--reuse-frozen-gate' in arguments[i] for i in (0, 2)))
            self.assertNotIn('--reuse-frozen-gate', arguments[1])
            company = [call for call in calls if 'prepare-common-stock-research' in call]
            self.assertEqual(len(company), 1)
            self.assertIn('--model gpt-6-luna', company[0])

    def test_structured_report_flag_rejects_other_stages_before_launch(self):
        for stage in ('common-stock-research', 'independent-counter-thesis-research',
                      'predecision-cio-synthesis'):
            result = subprocess.run(
                ['bash', str(ROOT / 'scripts/run-product-smoke.sh'), '--stage', stage,
                 '--handoff', 'unused', '--source-run', 'unused',
                 '--target-security-id', 'US:COMMON_STOCK:MRVL',
                 '--structured-report-submission', '/unused-not-created'],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn('STRUCTURED_REPORT_STAGE_UNSUPPORTED', result.stderr)

    def test_prepared_common_stock_routes_to_existing_stage_launcher(self):
        import json
        import sys
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            wrapper = base / 'python3'
            wrapper.write_text(
                '#!/bin/bash\n'
                'if [ "$1" = "-" ]; then exec "' + sys.executable + '" "$@"; fi\n'
                'printf "%s\\n" "$*" >> "$TEST_COMMAND_LOG"\n'
            )
            wrapper.chmod(0o700)
            for name, body in {
                'scutil': 'printf "HTTPEnable : 1\\nHTTPProxy : localhost\\nHTTPPort : 23456\\n"',
                'networksetup': 'printf "Enabled: No\\n"',
                'lsof': 'exit 0',
                'route': 'exit 0',
            }.items():
                path = base / name
                path.write_text('#!/bin/bash\n' + body + '\n')
                path.chmod(0o700)
            prepared = base / 'prepared'
            prepared.mkdir()
            (prepared / 'run_manifest.json').write_text(json.dumps({'stage': 'COMMON_STOCK_RESEARCH'}))
            log = base / 'commands'
            result = subprocess.run(
                ['bash', str(ROOT / 'scripts/run-product-smoke.sh'), '--prepared-run',
                 str(prepared), str(base / 'bundle')],
                env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                     'TEST_COMMAND_LOG': str(log)},
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                [line.split()[1] for line in log.read_text().splitlines()],
                ['launch-common-stock-research'],
            )

    def test_host_routes_and_preserves_failure(self):
        for status in (0, 9, 7):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                binary = base / 'python3'
                binary.write_text('''#!/bin/bash
if [ "$1" = "-" ]; then
  case "$2" in
    */host-proxy) printf 'PROXY_MODE=SYSTEM_HTTP_PROXY\\nHTTP_PROXY_URL=http://localhost:23456\\nHTTPS_PROXY_URL=http://localhost:23456\\n' ;;
    *) echo gpt-5.6-terra ;;
  esac
  exit 0
fi
printf '%s|%s|%s|%s|%s\\n' "$2" "$HTTP_PROXY" "$HTTPS_PROXY" "$http_proxy" "$https_proxy" >> "$TEST_COMMAND_LOG"
if [ "$2" = nested-codex-smoke ] && [ "$TEST_REVIEW_STATUS" = 9 ]; then exit 9; fi
if [ "$2" = check-run ] && [ "$TEST_REVIEW_STATUS" = 7 ]; then exit 7; fi
''')
                binary.chmod(0o700)
                for name in ('scutil', 'networksetup', 'lsof', 'route'):
                    path = base / name
                    path.write_text('#!/bin/bash\nexit 0\n')
                    path.chmod(0o700)
                log = base / 'commands'
                result = subprocess.run(
                    ['bash', str(ROOT / 'scripts/run-product-smoke.sh'), str(base / 'bundle')],
                    env={**os.environ, 'PATH': str(base) + os.pathsep + os.environ['PATH'],
                         'TEST_COMMAND_LOG': str(log), 'TEST_REVIEW_STATUS': str(status)},
                    text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, status, result.stderr)
                calls = log.read_text().splitlines()
                self.assertEqual([c.split('|')[0] for c in calls], ['prepare', 'nested-codex-smoke', 'check-run'])
                self.assertEqual(calls[1].split('|')[1:], ['http://localhost:23456'] * 4)


class EntrySeparationTests(unittest.TestCase):
    def test_predecision_advice_rejected_before_proxy_or_run_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'new-run'
            result = subprocess.run(
                ['/bin/bash', str(ROOT / 'scripts/run-product-smoke.sh'),
                 '--stage', 'predecision-cio-synthesis', '--source-run', '/missing/source',
                 '--target-security-id', 'US:COMMON_STOCK:MRVL', '--requested-level', 'PORTFOLIO_ADVICE',
                 str(target)],
                env={**os.environ, 'PATH': '/nonexistent'}, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn('CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE', result.stderr)
            self.assertFalse(target.exists())

    def test_predecision_current_and_other_security_rejected_before_run_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'new-run'
            common = ['/bin/bash', str(ROOT / 'scripts/run-product-smoke.sh'),
                      '--stage', 'predecision-cio-synthesis', '--source-run', '/missing/source']
            for security_id, extra, expected in (
                ('US:COMMON_STOCK:ALB', ['--requested-level', 'PORTFOLIO_ADVICE'], 'CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE'),
                ('US:COMMON_STOCK:MRVL', ['--time-mode', 'CURRENT'],
                 'CIO_CURRENT_RESEARCH_REQUIRES_NEW_SOURCE'),
            ):
                result = subprocess.run(
                    [*common, '--target-security-id', security_id, *extra, str(target)],
                    env={**os.environ, 'PATH': '/nonexistent'}, text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)
                self.assertFalse(target.exists())

    def test_review_rejected_before_any_external_call(self):
        with tempfile.TemporaryDirectory() as directory:
            for args in (['--review'], ['--review=true'], [directory, '--review']):
                result = subprocess.run(
                    ['/bin/bash', str(ROOT / 'scripts/run-product-smoke.sh'), *args],
                    env={**os.environ, 'PATH': '/nonexistent'}, text=True, capture_output=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn('REVIEW_MODE_RETIRED', result.stderr)

    def test_self_check_and_retired_entries_never_start_process(self):
        main = runpy.run_path(str(ROOT / 'scripts/council-dev.py'))['main']
        commands = [['review-run'], ['review-probe'], ['nested-codex-probe'],
                    ['environment-preflight'], ['permission-probe'],
                    ['nested-codex-smoke', '--preflight-report=missing.json'],
                    ['self-check'], ['self-check', 'nested-codex-smoke'],
                    ['self-check', 'environment-preflight'], ['self-check', 'regression']]
        for args in commands:
            with self.subTest(args=args), patch('subprocess.run') as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 2)
                run.assert_not_called()

    def test_self_check_only_forwards_deterministic_command_and_exit(self):
        main = runpy.run_path(str(ROOT / 'scripts/council-dev.py'))['main']
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'run_manifest.json').write_text('{}')
            for name in ('trace-check', 'check-run'):
                for status in (0, 7):
                    arguments = ['self-check', name, '--run-dir', directory]
                    if name == 'trace-check':
                        arguments.extend(['--output', str(base / 'trace-result.json')])
                    with patch('subprocess.run', return_value=subprocess.CompletedProcess([], status)) as run:
                        self.assertEqual(main(arguments), status)
                        command = run.call_args.args[0]
                        self.assertEqual(command[3], name)
                        self.assertNotIn('sandbox', command)
                        self.assertNotIn('nested-codex-smoke', command)

    def test_prepared_replay_and_check_use_frozen_root(self):
        import json
        forward = runpy.run_path(str(ROOT / 'scripts/council-dev.py'))['forwarded_command']
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            frozen = (base / 'frozen').resolve()
            (frozen / 'product/runtime').mkdir(parents=True)
            (frozen / 'product/runtime/cli.py').touch()
            run_dir = base / 'run'
            run_dir.mkdir()
            (run_dir / 'run_manifest.json').write_text(json.dumps({'run_mode': 'EXECUTION_REPLAY', 'execution_replay': {'workspace': str(frozen)}}))
            (run_dir / 'host-replay-source.json').write_text('{}')
            for name in ('nested-codex-smoke', 'check-run'):
                command, repo = forward([name, '--run-dir', str(run_dir)], calling_cwd=ROOT)
                self.assertEqual(repo, frozen)
                self.assertEqual(command[command.index('--repo') + 1], str(frozen))
                self.assertNotIn('sandbox', command)


if __name__ == '__main__':
    unittest.main()
