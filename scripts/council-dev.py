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
from product.runtime.environment_preflight import build_restricted_command, permission_profile_overrides  # noqa: E402
from product.runtime.hashing import canonical_hash  # noqa: E402


def _review_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="受限测试/复核入口")
    parser.add_argument(
        "command", choices=("review-probe", "nested-codex-probe", "review-run")
    )
    parser.add_argument("--repo", type=Path, default=INSTALLATION_ROOT)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--tmpdir", type=Path, required=True)
    parser.add_argument("--outside-canary", type=Path)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    return parser


def _absolute(path: Path, cwd: Path) -> Path:
    return (cwd / path.expanduser()).resolve()


def _permission_bindings(repo: Path, run: Path, evidence: Path, tmpdir: Path) -> dict[str, str]:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    return {
        "repo_root": str(repo),
        "run_dir": str(run),
        "output_dir": str(evidence),
        "tmpdir": str(tmpdir),
        "codex_home_tmp": str(codex_home / "tmp"),
        "codex_installation_id": str(codex_home / "installation_id"),
    }


def _validated_permission_proof(
    proof_path: Path, *, expected_hash: str, bindings: dict[str, str]
) -> dict:
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    observed_hash = proof.get("profile_hash") or proof.get("parent", {}).get("profile_hash")
    observed_bindings = proof.get("path_bindings") or proof.get("parent", {}).get("path_bindings")
    if proof.get("status") != "PASS" or proof.get("child_inheritance") is not True:
        raise ValueError("PERMISSION_PROBE_NOT_PASSED")
    if observed_hash != expected_hash or observed_bindings != bindings:
        raise ValueError("PERMISSION_PROBE_BINDING_MISMATCH")
    return proof


def restricted_main(argv: list[str], *, calling_cwd: Path) -> int:
    args = _review_parser().parse_args(argv)
    repo = _absolute(args.repo, calling_cwd)
    run = _absolute(args.run_dir, calling_cwd)
    evidence = _absolute(args.evidence_dir, calling_cwd)
    tmpdir = _absolute(args.tmpdir, calling_cwd)
    if evidence == repo or evidence.is_relative_to(repo) or tmpdir == repo or tmpdir.is_relative_to(repo):
        raise ValueError("REVIEW_OUTPUT_MUST_BE_OUTSIDE_SOURCE")
    evidence.mkdir(parents=True, exist_ok=True)
    tmpdir.mkdir(parents=True, exist_ok=True)
    profile_overrides = permission_profile_overrides(
        repository_root=repo, run_dir=run, output_dir=evidence, tmpdir=tmpdir
    )
    bindings = _permission_bindings(repo, run, evidence, tmpdir)
    environment = dict(os.environ)
    environment["TMPDIR"] = str(tmpdir)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(repo) + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    environment["STOCK_AGENT_PERMISSION_PROFILE_HASH"] = canonical_hash(
        {"overrides": list(profile_overrides)}
    )
    environment["STOCK_AGENT_PERMISSION_PATH_BINDINGS"] = json.dumps(bindings, sort_keys=True)
    if args.command == "review-probe":
        if args.outside_canary is None:
            raise ValueError("OUTSIDE_CANARY_REQUIRED")
        outside = _absolute(args.outside_canary, calling_cwd)
        inner = [
            sys.executable, str(Path(__file__).resolve()), "permission-probe",
            "--source-canary", str(repo / "AGENTS.md"), "--output-dir", str(evidence),
            "--tmpdir", str(tmpdir), "--outside-canary", str(outside),
            "--output", str(evidence / "permission-probe.json"),
            "--codex-binary", args.codex_binary,
        ]
    elif args.command == "nested-codex-probe":
        proof_path = evidence / "permission-probe.json"
        proof = _validated_permission_proof(
            proof_path,
            expected_hash=environment["STOCK_AGENT_PERMISSION_PROFILE_HASH"],
            bindings=bindings,
        )
        inner = [
            sys.executable,
            "-m",
            "product.runtime.cli",
            "nested-codex-probe",
            "--repo",
            str(repo),
            "--output-dir",
            str(evidence / "nested-codex-probe"),
            "--model",
            "gpt-5.6-terra",
            "--command-network-status",
            str(proof.get("COMMAND_NETWORK_STATUS", "UNKNOWN")),
            "--codex-binary",
            args.codex_binary,
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]
    else:
        proof_path = evidence / "permission-probe.json"
        if not proof_path.exists():
            # 复用既有权限检查作为启动准备；不要求操作者另跑检查命令。
            probe_code = restricted_main(
                [
                    "review-probe", "--repo", str(repo), "--run-dir", str(run),
                    "--evidence-dir", str(evidence), "--tmpdir", str(tmpdir),
                    "--outside-canary", str(Path(environment.get(
                        "CODEX_HOME", str(Path.home() / ".codex")
                    )) / "config.toml"),
                    "--codex-binary", args.codex_binary,
                ],
                calling_cwd=calling_cwd,
            )
            if probe_code != 0:
                return probe_code
        _validated_permission_proof(
            proof_path,
            expected_hash=environment["STOCK_AGENT_PERMISSION_PROFILE_HASH"],
            bindings=bindings,
        )
        preflight_dir = evidence / "preflight"
        if not (preflight_dir / "preflight.json").is_file():
            preflight_cmd = [
                sys.executable, str(Path(__file__).resolve()), "environment-preflight", "--repo", str(repo),
                "--run-dir", str(run), "--output-dir", str(preflight_dir), "--mode", "runtime",
                "--permission-evidence", str(proof_path), "--requested-model", "gpt-5.6-terra",
                "--codex-binary", args.codex_binary,
            ]
            preflight = subprocess.run(preflight_cmd, cwd=repo, env=environment, check=False)
            if preflight.returncode != 0:
                return preflight.returncode
        inner = [
            sys.executable, str(Path(__file__).resolve()), "nested-codex-smoke", "--repo", str(repo),
            "--run-dir", str(run), "--codex-binary", args.codex_binary,
            "--timeout-seconds", str(args.timeout_seconds),
            "--preflight-report", str(preflight_dir / "preflight.json"),
        ]
    command = build_restricted_command(
        inner, repository_root=repo, run_dir=run, output_dir=evidence,
        tmpdir=tmpdir, codex_binary=args.codex_binary, log_denials=True,
    )
    completed = subprocess.run(command, cwd=evidence, env=environment, text=True, capture_output=True, check=False)
    stem = {
        "review-probe": "permission-probe",
        "nested-codex-probe": "nested-codex-probe",
        "review-run": "runtime",
    }[args.command]
    (evidence / f"{stem}-stdout.log").write_text(completed.stdout, encoding="utf-8")
    (evidence / f"{stem}-stderr.log").write_text(completed.stderr, encoding="utf-8")
    nested_result = None
    nested_result_path = evidence / "nested-codex-probe" / "invocation" / "process-result.json"
    if args.command == "nested-codex-probe" and nested_result_path.is_file():
        nested_result = json.loads(nested_result_path.read_text(encoding="utf-8"))
    permission_result = None
    permission_result_path = evidence / "permission-probe.json"
    if permission_result_path.is_file():
        permission_result = json.loads(permission_result_path.read_text(encoding="utf-8"))
    status_source = nested_result or permission_result or {}
    result = {
        "status": "PASS" if completed.returncode == 0 else "BLOCKED",
        "failure_code": (
            None
            if completed.returncode == 0
            else (nested_result or {}).get("failure_code", "RESTRICTED_PROCESS_FAILED")
        ),
        "process_exit_code": completed.returncode,
        "profile_hash": environment["STOCK_AGENT_PERMISSION_PROFILE_HASH"],
        "path_bindings": bindings,
        "command": command,
        "COMMAND_NETWORK_STATUS": (
            status_source.get("COMMAND_NETWORK_STATUS")
        ),
        "NESTED_CODEX_STATUS": (
            (nested_result or {}).get("NESTED_CODEX_STATUS")
            if nested_result is not None
            else ("NOT_REACHED" if args.command == "nested-codex-probe" else "NOT_EXECUTED")
        ),
        "FIRST_DIVERGENCE": (
            status_source.get("FIRST_DIVERGENCE")
            or (
                "RESTRICTED_CHILD_ENTRY"
                if args.command == "nested-codex-probe" and nested_result is None
                else None
            )
        ),
        "blocks_change": completed.returncode != 0,
        "llm_calls": 0 if args.command == "review-probe" else (1 if args.command == "nested-codex-probe" else None),
    }
    (evidence / f"{stem}-process.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return completed.returncode


def forwarded_command(argv: list[str], *, calling_cwd: Path) -> tuple[list[str], Path]:
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
        if arguments and arguments[0] in {"review-probe", "nested-codex-probe", "review-run"}:
            raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED:独立复核只读取已有证据；隔离验收为UNVERIFIED")
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
