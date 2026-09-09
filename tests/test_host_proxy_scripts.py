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
        self.assertNotIn('dangerously-bypass', text)
        self.assertNotIn('network_proxy=false', text)

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
