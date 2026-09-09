"""路径无关的开发薄入口；产品执行和成功判断仍由既有 CLI/launcher 负责。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


INSTALLATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INSTALLATION_ROOT))

from product.runtime.cli import build_parser  # noqa: E402
from product.runtime.environment_preflight import reject_legacy_entry  # noqa: E402


def restricted_main(argv: list[str], *, calling_cwd: Path) -> int:
    """旧项目沙箱入口已退役，不读取路径、不创建产物。"""
    raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")


def forwarded_command(argv: list[str], *, calling_cwd: Path) -> tuple[list[str], Path]:
    reject_legacy_entry(argv)
    parser = build_parser()
    subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    # 从权威 CLI 读取参数契约，不维护另一份子命令或路径参数清单。
    for command_parser in subparsers.choices.values():
        for action in command_parser._actions:
            if action.dest == "repo":
                action.required = False
    args = parser.parse_args(argv)
    selected = subparsers.choices[args.command]
    path_flags = {flag for action in selected._actions if action.type is Path for flag in action.option_strings}
    forwarded = list(argv)
    for index, token in enumerate(argv):
        flag, separator, value = token.partition("=")
        if flag not in path_flags:
            continue
        raw = value if separator else argv[index + 1]
        path = Path(raw).expanduser()
        absolute = str((calling_cwd / path).resolve())
        if separator:
            forwarded[index] = f"{flag}={absolute}"
        else:
            forwarded[index + 1] = absolute
    explicit_repo = getattr(args, "repo", None)
    repo = (calling_cwd / explicit_repo.expanduser()).resolve() if explicit_repo else INSTALLATION_ROOT
    if args.command in {"nested-codex-smoke", "check-run"}:
        run = (calling_cwd / args.run_dir.expanduser()).resolve()
        manifest = json.loads((run / "run_manifest.json").read_text())
        if manifest.get("run_mode") == "EXECUTION_REPLAY":
            workspace = manifest.get("execution_replay", {}).get("workspace")
            if not workspace:
                raise ValueError("REPLAY_WORKSPACE_MISSING")
            frozen = Path(workspace).resolve()
            if explicit_repo and frozen != repo:
                raise ValueError("REPLAY_REPOSITORY_CONFLICT")
            repo = frozen
            if args.command == "nested-codex-smoke":
                if "--codex-binary" in argv or any(x.startswith("--codex-binary=") for x in argv):
                    raise ValueError("REPLAY_TRANSPORT_BINARY_OVERRIDE_FORBIDDEN")
                if not (run / "host-replay-source.json").is_file():
                    raise ValueError("REPLAY_HOST_SOURCE_BINDING_MISSING")
                forwarded.extend(["--codex-binary", str(INSTALLATION_ROOT / "scripts/replay-codex-transport.py")])
    if hasattr(args, "repo") and explicit_repo is None:
        forwarded.extend(["--repo", str(repo)])
    if not (repo / "product" / "runtime" / "cli.py").is_file():
        raise ValueError("REPOSITORY_ROOT_INVALID")
    return [sys.executable, "-m", "product.runtime.cli", *forwarded], repo


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = list(sys.argv[1:] if argv is None else argv)
        reject_legacy_entry(arguments)
        if arguments and arguments[0] == "self-check":
            # 明确白名单，不允许自检参数转发为任意运行/沙箱命令。
            allowed = {"check-run", "trace-check"}
            if len(arguments) < 2 or arguments[1] not in allowed:
                raise ValueError("SELF_CHECK_COMMAND_NOT_ALLOWED")
            arguments = arguments[1:]
        command, repo = forwarded_command(arguments, calling_cwd=Path.cwd())
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        status = subprocess.run(command, cwd=repo, env=environment, check=False).returncode
        if status == 0 and arguments and arguments[0] == "prepare-execution-replay":
            parsed = build_parser().parse_args(command[3:])
            # 外置宿主启动元数据，不加入或改写冻结版本锁。
            with (parsed.run_dir / "host-replay-source.json").open("x", encoding="utf-8") as stream:
                json.dump({"source_run_dir": str(parsed.source_run_dir.resolve())}, stream)
        return status
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "failure_code": str(exc), "llm_calls": 0}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
