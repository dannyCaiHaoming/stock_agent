"""Terminal-state artifact matrix for native Council run packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .hashing import canonical_hash, file_hash


ARTIFACT_MATRIX_VERSION = "native-artifact-matrix/2.0.0"
PUBLISHED_STATES = {"COMPLETED", "SAFE_NO_TRADE"}


class ArtifactMatrixError(ValueError):
    """Raised when a run package is incomplete or internally inconsistent."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactMatrixError(f"INVALID_REQUIRED_ARTIFACT:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise ArtifactMatrixError(f"ARTIFACT_NOT_OBJECT:{path.name}")
    return dict(value)


def _required_chain_files(*, authenticity_required: bool) -> set[str]:
    agents = ("runtime_company_analyst", "runtime_skeptic")
    required = {
        "evidence/gate.json",
        "inputs/runtime_cio.json",
        "invocations/runtime_cio.json",
        "prompts/runtime_cio.txt",
        "cio/runtime_cio.json",
        "risk/check-1.json",
    }
    for agent in agents:
        required.update(
            {
                f"inputs/{agent}.json",
                f"invocations/{agent}.json",
                f"prompts/{agent}.txt",
                f"agents/{agent}.json",
            }
        )
    if authenticity_required:
        required.update(
            {
                "events/codex/specialist-execution-proof.json",
                "events/mcp/events.jsonl",
            }
        )
    return required


def validate_artifact_matrix(
    run_dir: Path, *, require_eval: bool = True
) -> dict[str, Any]:
    """Validate required/forbidden files and Trace artifact hashes."""

    run_dir = run_dir.resolve()
    trace = _read_object(run_dir / "decision_trace.json")
    terminal_state = str(trace.get("terminal_state", ""))
    if terminal_state not in PUBLISHED_STATES | {"FAILED_VALIDATION"}:
        raise ArtifactMatrixError("UNKNOWN_OR_NONTERMINAL_STATE")

    required = {"decision_trace.json"}
    forbidden: set[str] = set()
    manifest_path = run_dir / "run_manifest.json"
    manifest = _read_object(manifest_path) if manifest_path.is_file() else None
    if manifest is not None:
        required.add("run_manifest.json")
        if manifest.get("run_id") != trace.get("run_id"):
            raise ArtifactMatrixError("RUN_ID_MISMATCH")

    if terminal_state == "FAILED_VALIDATION":
        required.add("run_error.json")
        forbidden.update({"decision.json", "report.md"})
    else:
        required.update({"decision.json", "report.md", "run_manifest.json"})
        if require_eval:
            required.add("eval/result.json")
        decision = _read_object(run_dir / "decision.json")
        if decision.get("terminal_state") != terminal_state:
            raise ArtifactMatrixError("DECISION_TERMINAL_STATE_MISMATCH")
        has_chain = (run_dir / "invocations").is_dir()
        if has_chain:
            if manifest is None:
                raise ArtifactMatrixError("RUN_MANIFEST_REQUIRED_FOR_CHAIN")
            required.update(
                _required_chain_files(
                    authenticity_required=manifest.get("authenticity_required") is not False
                )
            )
        else:
            forbidden.update(
                {
                    "agents/runtime_company_analyst.json",
                    "agents/runtime_skeptic.json",
                    "cio/runtime_cio.json",
                    "risk/check-1.json",
                    "events/codex/specialist-execution-proof.json",
                }
            )

    missing = sorted(path for path in required if not (run_dir / path).is_file())
    present_forbidden = sorted(path for path in forbidden if (run_dir / path).exists())
    if missing or present_forbidden:
        raise ArtifactMatrixError(
            f"ARTIFACT_MATRIX_FAILED:missing={missing},forbidden={present_forbidden}"
        )

    traced = trace.get("artifacts", {})
    if not isinstance(traced, Mapping):
        raise ArtifactMatrixError("TRACE_ARTIFACT_MAP_INVALID")
    for relative in required - {"decision_trace.json"}:
        expected = traced.get(relative)
        if expected != file_hash(run_dir / relative):
            raise ArtifactMatrixError(f"TRACE_ARTIFACT_HASH_MISMATCH:{relative}")
    summary = {
        "schema_version": ARTIFACT_MATRIX_VERSION,
        "run_id": trace.get("run_id"),
        "terminal_state": terminal_state,
        "required_files": sorted(required),
        "forbidden_files": sorted(forbidden),
        "status": "PASSED",
    }
    summary["matrix_hash"] = canonical_hash(summary)
    return summary
