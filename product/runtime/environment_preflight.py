"""Codex 开发环境的确定性路径、权限和加载证据检查。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .hashing import canonical_hash, file_hash
from .model_routing import load_model_routing


PREFLIGHT_VERSION = "codex-environment-preflight/1.0.0"
PERMISSION_PROBE_VERSION = "codex-permission-probe/1.0.0"
REQUIRED_EXEC_OPTIONS = ("--ephemeral", "--json", "--sandbox", "--add-dir", "--strict-config")
REQUIRED_SANDBOX_OPTIONS = ("--permission-profile", "--sandbox-state-json", "--cd")
COMMAND_NETWORK_PROBE_URL = "https://chatgpt.com/backend-api/codex/responses"


def reject_legacy_entry(arguments: Sequence[str]) -> None:
    """薄入口和底层入口共用退役检查；不读取文件或启动进程。"""
    retired = {
        "review-run", "review-probe", "nested-codex-probe",
        "environment-preflight", "permission-probe",
    }
    if arguments and arguments[0] in retired:
        raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
    for token in arguments:
        flag = token.partition("=")[0]
        if flag == "--review":
            raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
        if flag == "--preflight-report":
            raise ValueError("LEGACY_SANDBOX_MODE_RETIRED")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"ARTIFACT_NOT_OBJECT:{path}")
    return dict(value)


def _is_within(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _contains_symlink(path: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current == current.parent:
            return False
        current = current.parent


def resolve_run_paths(
    repository_root: Path,
    *,
    run_dir: Path,
    authorized_output_root: Path | None = None,
) -> dict[str, Any]:
    """在启动模型或创建 invocation 前验证准备好的运行身份。"""
    calling_cwd = Path.cwd().resolve()
    raw_repo = repository_root.expanduser().absolute()
    raw_run = run_dir.expanduser().absolute()
    if _contains_symlink(raw_repo) or _contains_symlink(raw_run):
        raise ValueError("PATH_ANCESTOR_SYMLINK_FORBIDDEN")
    repo = raw_repo.resolve(strict=True)
    run = raw_run.resolve(strict=True)
    output_root = (
        authorized_output_root.expanduser().absolute().resolve(strict=True)
        if authorized_output_root is not None
        else run
    )
    if not _is_within(run, output_root):
        raise ValueError("RUN_DIRECTORY_OUTSIDE_AUTHORIZED_OUTPUT_ROOT")
    product = repo / "product"
    if product.resolve() != product:
        raise ValueError("PRODUCT_ROOT_SYMLINK_ESCAPE")
    plugin = _read_object(product / ".codex-plugin" / "plugin.json")
    if plugin.get("name") != "product":
        raise ValueError("PRODUCT_PACKAGE_IDENTITY_MISMATCH")
    if run == repo or repo.is_relative_to(run):
        raise ValueError("RUN_DIRECTORY_OVERLAPS_SOURCE")
    if run.is_relative_to(repo) and not run.is_relative_to(repo / "evals" / "results"):
        raise ValueError("RUN_DIRECTORY_OVERLAPS_SOURCE")
    if any(path.is_symlink() for path in run.rglob("*")):
        raise ValueError("RUN_DIRECTORY_SYMLINK_ESCAPE")
    manifest = _read_object(run / "run_manifest.json")
    if not manifest.get("output_dir") or Path(str(manifest["output_dir"])).resolve() != run:
        raise ValueError("RUN_DIRECTORY_IDENTITY_MISMATCH")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("RUN_ID_MISSING")
    trace_path = run / "decision_trace.json"
    if trace_path.is_file() and _read_object(trace_path).get("run_id") != run_id:
        raise ValueError("RUN_IDENTITY_CONFLICT")
    replay = manifest.get("execution_replay")
    if manifest.get("run_mode") == "EXECUTION_REPLAY":
        if not isinstance(replay, Mapping) or not replay.get("workspace"):
            raise ValueError("REPLAY_WORKSPACE_MISSING")
        if Path(str(replay["workspace"])).resolve() != repo:
            raise ValueError("REPLAY_REPOSITORY_CONFLICT")
    if (run / "invocation").exists():
        raise ValueError("INVOCATION_DIRECTORY_ALREADY_EXISTS")
    if (run / ".codex-runtime").exists():
        raise ValueError("RUN_STATE_ALREADY_EXISTS")
    return {
        "calling_cwd": str(calling_cwd),
        "repo_root": str(repo),
        "repo_source": "execution_replay.workspace" if replay else "explicit_repository_root",
        "product_root": str(product),
        "product_source": "repo_root/product",
        "run_dir": str(run),
        "run_source": "explicit_run_dir+run_manifest.output_dir",
        "authorized_output_root": str(output_root),
        "authorized_output_source": "explicit" if authorized_output_root else "exact_run_dir",
        "run_id": run_id,
        "state_dir": str(run / ".codex-runtime"),
        "state_source": "run_dir/.codex-runtime",
        "child_cwd": str(product),
    }


def permission_profile_override(
    *, repository_root: Path, run_dir: Path, output_dir: Path, tmpdir: Path
) -> str:
    """返回可由本机 `codex sandbox -c` 解析的单一动态权限表。"""
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    system_tmp_roots = {
        Path(tempfile.gettempdir()).resolve(),
        Path("/tmp").resolve(),
    }
    filesystem = {
        ":root": "deny",
        ":minimal": "read",
        **{str(path): "deny" for path in sorted(system_tmp_roots)},
        str(Path(sys.base_prefix).resolve()): "read",
        str(repository_root.resolve()): "read",
        str(run_dir.resolve()): "write",
        str(output_dir.resolve()): "write",
        str(tmpdir.resolve()): "write",
        str(codex_home / "auth.json"): "read",
        str(codex_home / "config.toml"): "read",
        str(codex_home / "AGENTS.md"): "read",
        # codex-cli 0.153.4 在配置加载阶段会写入这两个精确路径。
        # 其余全局状态（sessions、SQLite、logs、auth、config）仍保持不可写。
        str(codex_home / "installation_id"): "write",
        str(codex_home / "tmp"): "write",
        str(codex_home / "models_cache.json"): "read",
        str(codex_home / "rules"): "read",
        str(codex_home / "skills"): "read",
        str(codex_home / "plugins"): "read",
    }
    entries = ",".join(f'{json.dumps(path)}={json.dumps(access)}' for path, access in filesystem.items())
    return f"permissions.council_review.filesystem={{{entries}}}"


def permission_profile_overrides(
    *, repository_root: Path, run_dir: Path, output_dir: Path, tmpdir: Path
) -> tuple[str, ...]:
    """返回完整 profile 覆盖；网络仅允许当前 Codex 服务端点。"""
    return (
        permission_profile_override(
            repository_root=repository_root,
            run_dir=run_dir,
            output_dir=output_dir,
            tmpdir=tmpdir,
        ),
        # sandbox 的显式 profile 与代理初始化的默认 profile 必须一致。
        # 否则文件沙箱可能使用 council_review，代理仍按另一默认策略启动。
        'default_permissions="council_review"',
        "features.network_proxy=true",
        "permissions.council_review.network.enabled=true",
        'permissions.council_review.network.domains={"chatgpt.com"="allow"}',
    )


def build_restricted_command(
    child_command: Sequence[str],
    *,
    repository_root: Path,
    run_dir: Path,
    output_dir: Path,
    tmpdir: Path,
    codex_binary: str = "codex",
    log_denials: bool = False,
) -> list[str]:
    command = [codex_binary, "sandbox", "-C", str(output_dir.resolve())]
    for override in permission_profile_overrides(
        repository_root=repository_root,
        run_dir=run_dir,
        output_dir=output_dir,
        tmpdir=tmpdir,
    ):
        command.extend(("-c", override))
    command.extend(("--permission-profile", "council_review"))
    if log_denials:
        command.append("--log-denials")
    command.extend(("--", *child_command))
    return command


def _open_without_writing(path: Path) -> dict[str, Any]:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
    except OSError as exc:
        return {"path": str(path), "write_open": "DENIED", "error": type(exc).__name__}
    os.close(descriptor)
    return {"path": str(path), "write_open": "ALLOWED"}


def _write_probe(directory: Path, name: str) -> dict[str, Any]:
    path = directory / name
    try:
        path.write_text("permission-probe\n", encoding="utf-8")
        path.unlink()
        return {"path": str(directory), "write": "ALLOWED"}
    except OSError as exc:
        return {"path": str(directory), "write": "DENIED", "error": type(exc).__name__}


def permission_probe(
    *, source_canary: Path, output_dir: Path, tmpdir: Path, outside_canary: Path
) -> dict[str, Any]:
    """安全探针：源码和越界文件只尝试写模式打开，不写入任何字节。"""
    checks = {
        "source_write": _open_without_writing(source_canary),
        "output_write": _write_probe(output_dir, ".permission-output-probe"),
        "tmp_write": _write_probe(tmpdir, ".permission-tmp-probe"),
        "outside_write": _open_without_writing(outside_canary),
    }
    status = "PASS" if (
        checks["source_write"]["write_open"] == "DENIED"
        and checks["outside_write"]["write_open"] == "DENIED"
        and checks["output_write"]["write"] == "ALLOWED"
        and checks["tmp_write"]["write"] == "ALLOWED"
    ) else "FAIL"
    return {
        "schema_version": PERMISSION_PROBE_VERSION,
        "status": status,
        "checks": checks,
        "source_bytes_written": 0,
        "outside_bytes_written": 0,
        "llm_calls": 0,
        "profile_hash": os.environ.get("STOCK_AGENT_PERMISSION_PROFILE_HASH"),
        "path_bindings": json.loads(os.environ.get("STOCK_AGENT_PERMISSION_PATH_BINDINGS", "{}")),
    }


def command_network_probe() -> dict[str, Any]:
    """探测沙箱命令网络；结果不得冒充 Codex 客户端模型通道状态。"""
    request = urllib.request.Request(COMMAND_NETWORK_PROBE_URL, method="HEAD")
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        proxy_error = exc.headers.get("x-proxy-error")
        reachable = proxy_error is None
        return {
            "scope": "SANDBOXED_COMMAND",
            "gating": False,
            "status": "REACHABLE" if reachable else "BLOCKED",
            "http_status": exc.code,
            "proxy_error": proxy_error,
            "failure_code": None if reachable else "NETWORK_PROXY_ALLOWLIST_BLOCKED",
            "credentials_sent": False,
            "response_body_read": False,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = str(getattr(exc, "reason", exc))
        proxy_rejected = "403" in reason and (
            "proxy" in reason.lower() or "tunnel" in reason.lower()
        )
        return {
            "scope": "SANDBOXED_COMMAND",
            "gating": False,
            "status": "BLOCKED",
            "http_status": None,
            "proxy_error": None,
            "failure_code": (
                "NETWORK_PROXY_CONNECT_REJECTED"
                if proxy_rejected
                else "CODEX_SERVICE_UNREACHABLE"
            ),
            "error_type": type(exc).__name__,
            "error_classification": "HTTP_CONNECT_403" if proxy_rejected else "UNREACHABLE",
            "credentials_sent": False,
            "response_body_read": False,
        }
    else:
        status = getattr(response, "status", None)
        response.close()
        return {
            "scope": "SANDBOXED_COMMAND",
            "gating": False,
            "status": "REACHABLE",
            "http_status": status,
            "proxy_error": None,
            "failure_code": None,
            "credentials_sent": False,
            "response_body_read": False,
        }


def run_permission_probe_with_child(
    *,
    source_canary: Path,
    output_dir: Path,
    tmpdir: Path,
    outside_canary: Path,
    output_path: Path,
    child: bool = False,
    codex_binary: str = "codex",
) -> tuple[dict[str, Any], int]:
    """旧权限子进程探针已退役，不能再创建或继承项目沙箱。"""
    raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")


# 兼容现有调用方；名称保留，但语义明确限定为沙箱命令网络。
network_access_probe = command_network_probe


def _command_output(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False, timeout=30)


def _resource_inventory(repo: Path) -> dict[str, Any]:
    paths = {
        "root_agents": repo / "AGENTS.md",
        "product_agents": repo / "product" / "AGENTS.md",
        "portfolio_council_skill": repo / "product" / "skills" / "portfolio-council" / "SKILL.md",
        "company_agent": repo / "product" / ".codex" / "agents" / "runtime_company_analyst.toml",
        "skeptic_agent": repo / "product" / ".codex" / "agents" / "runtime_skeptic.toml",
        "cio_agent": repo / "product" / ".codex" / "agents" / "runtime_cio.toml",
        "mcp": repo / "product" / ".mcp.json",
        "hook": repo / "product" / "runtime" / "codex_hook_recorder.py",
        "launcher": repo / "product" / "runtime" / "nested_codex.py",
        "runtime_cli": repo / "product" / "runtime" / "cli.py",
        "development_entry": repo / "scripts" / "council-dev.py",
    }
    return {
        name: {
            "status": "DISCOVERED" if path.is_file() else "MISSING",
            "path": str(path),
            "sha256": file_hash(path) if path.is_file() else None,
            "load_status": "UNKNOWN",
        }
        for name, path in paths.items()
    }


def _doctor_summary(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        value = json.loads(completed.stdout)
        checks = value.get("checks", {})
    except (json.JSONDecodeError, AttributeError):
        return {"status": "UNAVAILABLE", "exit_code": completed.returncode}
    selected: dict[str, Any] = {}
    for name in ("auth.credentials", "config.load", "sandbox.helpers", "state.paths"):
        item = checks.get(name, {}) if isinstance(checks, Mapping) else {}
        selected[name] = {"status": item.get("status"), "summary": item.get("summary")}
    config = checks.get("config.load", {}).get("details", {}) if isinstance(checks, Mapping) else {}
    return {
        "status": "AVAILABLE",
        "exit_code": completed.returncode,
        "codex_version": value.get("codexVersion"),
        "configured_model": config.get("model") if isinstance(config, Mapping) else None,
        "checks": selected,
    }


def _prompt_input_summary(
    completed: subprocess.CompletedProcess[str], *, repo: Path
) -> dict[str, Any]:
    stderr_lines = [line.strip() for line in completed.stderr.splitlines() if line.strip()]
    stderr_first = next(
        (line for line in stderr_lines if not line.startswith("WARNING:")),
        stderr_lines[0] if stderr_lines else None,
    )
    try:
        records = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "UNAVAILABLE",
            "exit_code": completed.returncode,
            "stderr_first_exception": stderr_first,
            "stderr_summary": stderr_lines[:20],
        }
    all_texts = [
        str(content.get("text", ""))
        for record in records if isinstance(record, Mapping)
        for content in record.get("content", []) if isinstance(content, Mapping)
    ] if isinstance(records, list) else []
    developer_texts = [
        str(content.get("text", ""))
        for record in records if isinstance(record, Mapping) and record.get("role") == "developer"
        for content in record.get("content", []) if isinstance(content, Mapping)
    ] if isinstance(records, list) else []
    combined = "\n".join(all_texts)
    developer_combined = "\n".join(developer_texts)
    root_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    product_agents = (repo / "product" / "AGENTS.md").read_text(encoding="utf-8")
    return {
        "status": "LOAD_VERIFIED" if completed.returncode == 0 else "UNAVAILABLE",
        "exit_code": completed.returncode,
        "root_agents_loaded": root_agents in combined,
        "product_agents_loaded": product_agents in combined,
        "portfolio_council_advertised": "product:portfolio-council" in developer_combined,
        "raw_prompt_retained": False,
        "stderr_first_exception": stderr_first,
    }


def run_environment_preflight(
    repository_root: Path,
    *,
    run_dir: Path,
    output_dir: Path,
    mode: str,
    requested_model: str | None = None,
    permission_evidence: Path | None = None,
    codex_binary: str = "codex",
) -> tuple[dict[str, Any], int]:
    """历史 preflight 仅供读取；拒绝重新执行旧启动检查。"""
    raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
