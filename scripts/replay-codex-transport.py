#!/usr/bin/env python3
"""宿主重放启动适配：验证密封快照后补非 Git 目录参数，不改冻结代码。"""
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.replay_capsule import validate_materialized_snapshot


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def verified_command(args, run, binary):
    manifest = read(run / 'run_manifest.json')
    binding = read(run / 'execution-replay.json')
    source = Path(read(run / 'host-replay-source.json')['source_run_dir']).resolve()
    original = read(source / 'run_manifest.json')
    workspace = Path(binding['workspace']).resolve()
    if (manifest.get('run_mode') != 'EXECUTION_REPLAY'
            or binding['new_manifest_hash'] != canonical_hash(manifest)
            or binding['source_manifest_hash'] != canonical_hash(original)
            or binding['source_run_id'] != original['run_id']
            or binding['new_run_id'] != manifest['run_id']
            or Path(manifest['output_dir']).resolve() != run
            or Path(manifest['execution_replay']['workspace']).resolve() != workspace):
        raise ValueError('REPLAY_TRANSPORT_BINDING_MISMATCH')
    capsule = validate_materialized_snapshot(
        source / 'replay_capsule', target_root=workspace,
        allowed_extra_paths=('evals/fixtures/codex-native/execution-replay-source.json',),
    )
    if capsule['manifest_hash'] != binding['source_capsule_hash']:
        raise ValueError('REPLAY_TRANSPORT_CAPSULE_MISMATCH')
    if (args.count('exec') != 1 or args.count('-C') != 1
            or Path(args[args.index('-C') + 1]).resolve() != workspace / 'product'
            or args.count('--sandbox') != 1
            or args[args.index('--sandbox') + 1] != 'workspace-write'
            or '--dangerously-bypass-approvals-and-sandbox' in args
            or '--skip-git-repo-check' in args):
        raise ValueError('REPLAY_TRANSPORT_COMMAND_REJECTED')
    command = [binary, *args]
    command.insert(command.index('exec') + 1, '--skip-git-repo-check')
    return command, capsule['manifest_hash']


def main():
    try:
        run = Path(os.environ['STOCK_AGENT_RUN_DIR']).resolve()
        binary = shutil.which('codex')
        if not binary:
            raise ValueError('CODEX_BINARY_MISSING')
        command, capsule_hash = verified_command(sys.argv[1:], run, binary)
        proof = {
            'adapter_version': 'host-replay-transport/1.0.0',
            'adapter_sha256': file_hash(Path(__file__)),
            'source_capsule_hash': capsule_hash,
            'command': command, 'added_argument': '--skip-git-repo-check',
            'native_sandbox': 'workspace-write',
        }
        with (run / 'invocation/host-transport.json').open('x', encoding='utf-8') as stream:
            json.dump(proof, stream, ensure_ascii=False, indent=2)
        os.execv(binary, command)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        print('REPLAY_TRANSPORT_REJECTED:' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
