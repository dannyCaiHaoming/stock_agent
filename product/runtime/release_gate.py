"""Read-only release verdict for a terminal Council run package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .artifact_matrix import validate_artifact_matrix
from .native_eval import validate_native_eval_result
from .replay import replay_run
from .trace_validation import validate_decision_trace


RELEASE_GATE_VERSION = "council-release-gate/1.0.0"


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"ARTIFACT_NOT_OBJECT:{path.name}")
    return dict(value)


def _failure_result(
    *, run_dir: Path, category: str, message: str, exit_code: int
) -> tuple[dict[str, Any], int]:
    return (
        {
            "schema_version": RELEASE_GATE_VERSION,
            "status": "FAILED",
            "category": category,
            "run_dir": str(run_dir.resolve()),
            "message": message,
        },
        exit_code,
    )


def check_run(repository_root: Path, *, run_dir: Path) -> tuple[dict[str, Any], int]:
    """Return a package-derived verdict and process exit code without writes."""

    run_dir = run_dir.resolve()
    try:
        trace = _read_object(run_dir / "decision_trace.json")
        terminal_state = str(trace.get("terminal_state", ""))
        validate_decision_trace(trace, run_dir=run_dir)
        matrix = validate_artifact_matrix(run_dir, require_eval=False)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _failure_result(
            run_dir=run_dir,
            category="INVALID_OR_INCOMPLETE_RUN",
            message=str(exc),
            exit_code=3,
        )

    if terminal_state == "FAILED_VALIDATION":
        try:
            error = _read_object(run_dir / "run_error.json")
            diagnostic = replay_run(repository_root, run_dir=run_dir)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return _failure_result(
                run_dir=run_dir,
                category="INVALID_FAILED_RUN",
                message=str(exc),
                exit_code=3,
            )
        return (
            {
                "schema_version": RELEASE_GATE_VERSION,
                "status": "FAILED",
                "category": "FAILED_VALIDATION",
                "run_id": trace["run_id"],
                "terminal_state": terminal_state,
                "failed_stage": trace["failed_stage"],
                "run_error": {
                    "code": error["code"],
                    "message": error["message"],
                },
                "artifact_matrix_hash": matrix["matrix_hash"],
                "diagnostic_replay_hash": diagnostic["replay_hash"],
            },
            2,
        )

    if terminal_state not in {"COMPLETED", "SAFE_NO_TRADE"}:
        return _failure_result(
            run_dir=run_dir,
            category="NONTERMINAL_RUN",
            message=f"UNKNOWN_OR_NONTERMINAL_STATE:{terminal_state}",
            exit_code=3,
        )

    eval_path = run_dir / "eval" / "result.json"
    if not eval_path.is_file():
        return _failure_result(
            run_dir=run_dir,
            category="EVAL_MISSING_OR_FAILED",
            message="EVAL_RESULT_MISSING",
            exit_code=4,
        )
    try:
        saved_eval = _read_object(eval_path)
        validate_native_eval_result(saved_eval)
        if (
            saved_eval.get("run_id") != trace.get("run_id")
            or saved_eval.get("terminal_state") != terminal_state
            or saved_eval.get("status") != "PASSED"
        ):
            raise ValueError("EVAL_RESULT_RUN_OR_TERMINAL_MISMATCH")
        complete_matrix = validate_artifact_matrix(run_dir, require_eval=True)
        replay = replay_run(repository_root, run_dir=run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _failure_result(
            run_dir=run_dir,
            category="EVAL_MISSING_OR_FAILED",
            message=str(exc),
            exit_code=4,
        )
    return (
        {
            "schema_version": RELEASE_GATE_VERSION,
            "status": "PASSED",
            "category": "RELEASE_READY",
            "run_id": trace["run_id"],
            "terminal_state": terminal_state,
            "failed_stage": None,
            "artifact_matrix_hash": complete_matrix["matrix_hash"],
            "trace_status": "PASSED",
            "replay_hash": replay["replay_hash"],
            "eval_hash": saved_eval["eval_hash"],
        },
        0,
    )
