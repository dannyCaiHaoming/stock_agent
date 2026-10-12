"""Real local version subprocesses and fail-closed host command binding; zero LLM."""

import json
from pathlib import Path
import tempfile
import unittest

from product.runtime.codex_runtime import capture_codex_runtime, read_codex_runtime_binding
from product.runtime.hashing import canonical_hash
from product.runtime.nested_codex import build_verified_nested_codex_command

ROOT = Path(__file__).resolve().parents[1]


class CodexRuntimeTests(unittest.TestCase):
    def fixture(self, directory, output='codex-cli 0.160.0', exit_code=0):
        root = Path(directory)
        binary = root / 'codex'
        binary.write_text('#!/bin/sh\n'
                          'if [ "$1" != "--version" ]; then touch "' + str(root / 'model-started') + '"; exit 99; fi\n'
                          f"printf '%s\\n' '{output}'\nexit {exit_code}\n")
        binary.chmod(0o700)
        lock = root / 'run_manifest.json'
        lock.write_text(json.dumps({'run_id': 'runtime-test', 'codex_runtime': 'codex-cli/0.160.0'}))
        return root, binary, lock

    def test_real_version_measurement_and_binding_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root, binary, lock = self.fixture(directory)
            path = root / 'invocation/codex-runtime.json'
            record = capture_codex_runtime(str(binary), expected_runtime='codex-cli/0.160.0',
                                          run_id='runtime-test', lock_path=lock, output_path=path)
            self.assertEqual(record['observed_runtime'], 'codex-cli/0.160.0')
            self.assertEqual(read_codex_runtime_binding(path, expected_runtime='codex-cli/0.160.0',
                                                       run_id='runtime-test'), record)
            self.assertFalse((root / 'model-started').exists())

    def test_mismatch_unknown_and_failed_measurement_never_return_exec(self):
        for output, code, failure in [('codex-cli 0.159.3', 0, 'VERSION_MISMATCH'),
                                      ('not-a-version', 0, 'VERSION_UNVERIFIED'),
                                      ('codex-cli 0.160.0', 2, 'VERSION_UNVERIFIED')]:
            with self.subTest(output=output, code=code), tempfile.TemporaryDirectory() as directory:
                root, binary, _ = self.fixture(directory, output, code)
                with self.assertRaisesRegex(ValueError, failure):
                    build_verified_nested_codex_command(
                        runtime_binding_path=root / 'invocation/codex-runtime.json',
                        codex_binary=str(binary), product_root=ROOT / 'product', run_dir=root,
                        model='gpt-6-luna', sqlite_home=root / 'sqlite', log_dir=root / 'logs',
                        final_message_path=root / 'final.txt',
                        hook_recorder_path=ROOT / 'product/runtime/codex_hook_recorder.py',
                        hook_agent_matcher='^dev_eval$')
                record = json.loads((root / 'invocation/codex-runtime.json').read_text())
                self.assertEqual(record['status'], 'REJECTED')
                self.assertFalse((root / 'model-started').exists())

    def test_missing_binary_and_invalid_lock_are_rejected_with_record(self):
        for binary, runtime, code in [('missing-codex-test', 'codex-cli/0.160.0', 'BINARY_MISSING'),
                                      ('missing-codex-test', None, 'LOCK_INVALID')]:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                root, _, lock = self.fixture(directory)
                with self.assertRaisesRegex(ValueError, code):
                    capture_codex_runtime(binary, expected_runtime=runtime, run_id='runtime-test',
                                          lock_path=lock, output_path=root / 'binding.json')
                self.assertEqual(json.loads((root / 'binding.json').read_text())['status'], 'REJECTED')

    def test_proof_consumer_rejects_missing_drift_and_cross_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root, binary, lock = self.fixture(directory)
            path = root / 'binding.json'
            with self.assertRaisesRegex(ValueError, 'MISSING_OR_INVALID'):
                read_codex_runtime_binding(path, expected_runtime='codex-cli/0.160.0', run_id='runtime-test')
            record = capture_codex_runtime(str(binary), expected_runtime='codex-cli/0.160.0',
                                          run_id='runtime-test', lock_path=lock, output_path=path)
            for runtime, run_id in [('codex-cli/0.153.4', 'runtime-test'),
                                    ('codex-cli/0.160.0', 'other-run')]:
                with self.assertRaisesRegex(ValueError, 'IDENTITY_MISMATCH'):
                    read_codex_runtime_binding(path, expected_runtime=runtime, run_id=run_id)
            record['observed_runtime'] = 'codex-cli/0.159.3'
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
                read_codex_runtime_binding(path, expected_runtime='codex-cli/0.160.0', run_id='runtime-test')
            record.pop('binding_hash'); record['binding_hash'] = canonical_hash(record)
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'IDENTITY_MISMATCH'):
                read_codex_runtime_binding(path, expected_runtime='codex-cli/0.160.0', run_id='runtime-test')

    def test_stage_without_run_cli_field_binds_selected_product_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root, binary, lock = self.fixture(directory)
            lock.write_text(json.dumps({'run_id': 'runtime-test'}))
            product = root / 'product'; product.mkdir()
            (product / 'version-manifest.json').write_text(json.dumps({'codex_runtime': 'codex-cli/0.160.0'}))
            command = build_verified_nested_codex_command(
                runtime_binding_path=root / 'invocation/binding.json', codex_binary=str(binary),
                product_root=product, run_dir=root, model='gpt-6-luna', sqlite_home=root / 'sqlite',
                log_dir=root / 'logs', final_message_path=root / 'final.txt',
                hook_recorder_path=ROOT / 'product/runtime/codex_hook_recorder.py',
                        hook_agent_matcher='^dev_eval$')
            record = json.loads((root / 'invocation/binding.json').read_text())
            self.assertEqual(record['lock_path'], str((product / 'version-manifest.json').resolve()))
            self.assertEqual(command[0], str(binary.resolve()))
            self.assertFalse((root / 'model-started').exists())
