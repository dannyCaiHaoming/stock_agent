"""仅测试重放启动参数与 fail-closed，不执行 Codex。"""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('replay_transport', ROOT / 'scripts/replay-codex-transport.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class ReplayTransportTests(unittest.TestCase):
    def setUp(self):
        self.run = Path('/tmp/run').resolve()
        self.workspace = Path('/tmp/frozen').resolve()
        self.source = Path('/tmp/source').resolve()
        self.manifest = {'run_id': 'new', 'run_mode': 'EXECUTION_REPLAY', 'output_dir': str(self.run), 'execution_replay': {'workspace': str(self.workspace)}}
        self.original = {'run_id': 'old'}
        self.binding = {'workspace': str(self.workspace), 'new_run_id': 'new', 'source_run_id': 'old', 'new_manifest_hash': adapter.canonical_hash(self.manifest), 'source_manifest_hash': adapter.canonical_hash(self.original), 'source_capsule_hash': 'sealed'}
        self.values = {self.run / 'run_manifest.json': self.manifest, self.run / 'execution-replay.json': self.binding, self.run / 'host-replay-source.json': {'source_run_dir': str(self.source)}, self.source / 'run_manifest.json': self.original}
        self.reader = patch.object(adapter, 'read', side_effect=lambda path: self.values[path])
        self.reader.start()
        self.addCleanup(self.reader.stop)
        self.args = ['exec', '--ephemeral', '--sandbox', 'workspace-write', '-C', str(self.workspace / 'product'), '-']

    def test_valid_replay_adds_only_git_check_exception(self):
        with patch.object(adapter, 'validate_materialized_snapshot', return_value={'manifest_hash': 'sealed'}) as validate:
            command, _ = adapter.verified_command(self.args, self.run, '/bin/codex')
            self.assertEqual(command, ['/bin/codex', 'exec', '--skip-git-repo-check', *self.args[1:]])
            validate.assert_called_once_with(self.source / 'replay_capsule', target_root=self.workspace, allowed_extra_paths=('evals/fixtures/codex-native/execution-replay-source.json',))

    def test_non_replay_or_changed_manifest_rejected_before_capsule(self):
        self.manifest['run_mode'] = 'PRODUCT_COUNCIL'
        with patch.object(adapter, 'validate_materialized_snapshot') as validate, self.assertRaisesRegex(ValueError, 'BINDING_MISMATCH'):
            adapter.verified_command(self.args, self.run, '/bin/codex')
        validate.assert_not_called()

    def test_capsule_validation_failure_propagates(self):
        with patch.object(adapter, 'validate_materialized_snapshot', side_effect=ValueError('HASH_MISMATCH')), self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            adapter.verified_command(self.args, self.run, '/bin/codex')

    def test_wrong_cwd_or_relaxed_sandbox_rejected(self):
        for args in ([x.replace('workspace-write', 'danger-full-access') for x in self.args], [*self.args, '--dangerously-bypass-approvals-and-sandbox'], [*self.args, '--skip-git-repo-check']):
            with patch.object(adapter, 'validate_materialized_snapshot', return_value={'manifest_hash': 'sealed'}), self.assertRaisesRegex(ValueError, 'COMMAND_REJECTED'):
                adapter.verified_command(args, self.run, '/bin/codex')


if __name__ == '__main__':
    unittest.main()
