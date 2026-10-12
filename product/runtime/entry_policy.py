"""公开执行入口的零副作用退役检查；不读取运行目录或宿主配置。"""
from typing import Sequence

RETIRED_MODEL_COMMANDS = frozenset({
    "nested-codex-smoke", "launch-common-stock-research", "launch-multidimensional-research",
    "launch-research-materials", "launch-independent-skeptic", "resume-independent-skeptic",
    "launch-predecision-cio", "common-stock-research-prompt",
    "multidimensional-research-prompt", "research-materials-prompt",
})


def reject_legacy_entry(arguments: Sequence[str]) -> None:
    if arguments and arguments[0] in {"review-run", "review-probe", "nested-codex-probe", "environment-preflight", "permission-probe"}:
        raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
    for token in arguments:
        flag = token.partition("=")[0]
        if flag == "--review":
            raise ValueError("PROJECT_SANDBOX_ENTRY_RETIRED")
        if flag == "--preflight-report":
            raise ValueError("LEGACY_SANDBOX_MODE_RETIRED")
    if arguments and arguments[0] in RETIRED_MODEL_COMMANDS:
        raise ValueError("NATIVE_HOST_EXECUTION_REQUIRED")
