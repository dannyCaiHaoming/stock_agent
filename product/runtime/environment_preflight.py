"""旧项目沙箱、权限和网络探针的零副作用退役入口。

开发自检使用当前宿主的确定性测试；正常产品由当前原生会话执行。
历史preflight原件仍可由历史读取器读取，不在当前源码重建探针。
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence


def reject_legacy_entry(arguments: Sequence[str]) -> None:
    """薄入口和底层入口共用退役检查；不读取文件或启动进程。"""
    retired = {"review-run", "review-probe", "nested-codex-probe", "environment-preflight", "permission-probe"}
    if arguments and arguments[0] in retired:
        raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
    for token in arguments:
        flag = token.partition("=")[0]
        if flag == "--review":
            raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
        if flag == "--preflight-report":
            raise ValueError("LEGACY_SANDBOX_MODE_RETIRED")


def run_permission_probe_with_child(
    *, source_canary: Path, output_dir: Path, tmpdir: Path, outside_canary: Path,
    output_path: Path, child: bool = False, codex_binary: str = "codex",
):
    raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")


def run_environment_preflight(
    repository_root: Path, *, run_dir: Path, output_dir: Path, mode: str,
    requested_model: str | None = None, permission_evidence: Path | None = None, codex_binary: str = "codex",
):
    raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
