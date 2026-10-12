"""旧正常启动的拒绝壳，以及显式 dev_eval 维护所需的命令构造。

不启动研究、探针、CIO或项目沙箱；冻结Replay使用其冻结源码入口。
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

from .run_package import integrity_snapshot


def build_nested_codex_command(
    *, codex_binary: str, product_root: Path, run_dir: Path, model: str,
    sqlite_home: Path, log_dir: Path, final_message_path: Path, hook_recorder_path: Path,
    externally_sandboxed: bool = False, output_schema_path: Path | None = None,
    research_submission_enabled: bool = False, research_task_state_enabled: bool = False,
    fixture_mcp_run_dir: Path | None = None, fixture_mcp_skeptic_dispatch_index: str | None = None,
    hook_agent_matcher: str = "^(runtime_company_analyst|runtime_skeptic)$",
    enable_parent_stop_barrier: bool = False, enable_cio_local_revision: bool = False,
    skip_git_repo_check: bool = False,
) -> list[str]:
    """仅构造已保留的显式评分命令；正常研究选项在任何I/O前拒绝。"""
    if externally_sandboxed:
        raise ValueError("LEGACY_SANDBOX_MODE_RETIRED")
    if (hook_agent_matcher != "^dev_eval$" or research_submission_enabled or research_task_state_enabled
            or fixture_mcp_run_dir is not None or fixture_mcp_skeptic_dispatch_index is not None
            or enable_parent_stop_barrier or enable_cio_local_revision or skip_git_repo_check):
        raise ValueError("NATIVE_HOST_EXECUTION_REQUIRED:旧研究命令构造已退役；仅保留显式dev_eval维护。")
    hook_command = " ".join((shlex.quote(sys.executable), shlex.quote(str(hook_recorder_path))))
    start = (f'[{{matcher="^dev_eval$",hooks=[{{type="command",command={json.dumps(hook_command)},'
             'timeout=15,additionalContextLimit=0}]}]')
    stop = (f'[{{matcher="^dev_eval$",hooks=[{{type="command",command={json.dumps(hook_command)},'
            'timeout=3}]}]')
    dispatch = f'[{{hooks=[{{type="command",command={json.dumps(hook_command)},timeout=3}}]}}]'
    command = [codex_binary, "--ask-for-approval", "never", "--dangerously-bypass-hook-trust",
               "exec", "--ephemeral", "--json", "--sandbox", "workspace-write"]
    if output_schema_path is not None:
        command.extend(("--output-schema", str(output_schema_path)))
    command.extend(("--add-dir", str(run_dir), "-C", str(product_root), "--strict-config",
                    "-c", f'sqlite_home="{sqlite_home}"', "-c", f'log_dir="{log_dir}"',
                    "-c", 'history.persistence="none"',
                    "-c", f"hooks.PreToolUse={dispatch}", "-c", f"hooks.SubagentStart={start}",
                    "-c", f"hooks.SubagentStop={stop}", "--output-last-message", str(final_message_path),
                    "--model", model, "-"))
    return command


def build_verified_nested_codex_command(*, runtime_binding_path: Path, **kwargs: Any) -> list[str]:
    """仅对显式评分命令绑定锁定二进制；拒绝先于读取或启动进程。"""
    command = build_nested_codex_command(**kwargs)
    from .codex_runtime import capture_codex_runtime
    run_manifest_path = Path(kwargs["run_dir"]) / "run_manifest.json"
    manifest = json.loads(run_manifest_path.read_text()) if run_manifest_path.is_file() else {}
    expected = manifest.get("codex_runtime")
    lock_path = run_manifest_path
    if "codex_runtime" not in manifest:
        product_root = Path(kwargs["product_root"])
        lock_path = product_root / "version-manifest.json"
        if not lock_path.is_file():
            lock_path = product_root / "product/version-manifest.json"
        expected = json.loads(lock_path.read_text()).get("codex_runtime")
    binding = capture_codex_runtime(
        kwargs["codex_binary"], expected_runtime=expected, run_id=str(manifest.get("run_id", "")),
        lock_path=lock_path, output_path=runtime_binding_path,
    )
    command[0] = binding["binary_path"]
    return command


def run_nested_codex_connectivity_probe(
    repository_root: Path, *, output_dir: Path, model: str, command_network_status: str,
    codex_binary: str = "codex", timeout_seconds: int = 180,
):
    raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")


def launch_nested_codex(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex", timeout_seconds: int = 1800,
    preflight_report: Path | None = None,
):
    if preflight_report is not None:
        raise ValueError("LEGACY_SANDBOX_MODE_RETIRED")
    raise ValueError("NATIVE_HOST_EXECUTION_REQUIRED:使用当前宿主portfolio-council原生会话；旧执行维护仅限明确批准的冻结版本。")
