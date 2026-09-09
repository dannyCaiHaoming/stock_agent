"""Version-locked manifest and deterministic preparation for a native rerun."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .discovery import discover_product_resources
from .hashing import canonical_hash
from .run_package import prepare_run


RERUN_MANIFEST_VERSION = "native-rerun-manifest/2.0.0"


class NativeRerunError(ValueError):
    """Raised when a source run cannot be reproduced under the same version lock."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeRerunError(f"RERUN_SOURCE_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise NativeRerunError(f"RERUN_SOURCE_NOT_OBJECT:{path.name}")
    return dict(value)


def _locked_inputs(manifest: Mapping[str, Any]) -> dict[str, Any]:
    discovery = manifest.get("discovery", {})
    if not isinstance(discovery, Mapping):
        raise NativeRerunError("RERUN_DISCOVERY_LOCK_MISSING")
    return {
        "candidate_version": manifest.get("candidate_version"),
        "codex_runtime": manifest.get("codex_runtime"),
        "model": manifest.get("model"),
        "runtime_profile": manifest.get("runtime_profile"),
        "fixture": manifest.get("fixture"),
        "fixture_id": manifest.get("fixture_id"),
        "decision_cutoff": manifest.get("decision_cutoff"),
        "research_question": manifest.get("research_question"),
        "discovery_hash": discovery.get("discovery_hash"),
        "version_manifest": discovery.get("version_manifest"),
    }


def prepare_native_rerun(
    repository_root: Path,
    *,
    source_run_dir: Path,
    new_run_dir: Path,
    new_run_id: str,
) -> dict[str, Any]:
    source = _read_object(source_run_dir / "run_manifest.json")
    discovery = discover_product_resources(repository_root)
    source_lock = _locked_inputs(source)
    if source_lock["discovery_hash"] != discovery.discovery_hash:
        raise NativeRerunError("RERUN_RESOURCE_VERSION_DRIFT")
    result = prepare_run(
        repository_root,
        fixture_path=Path(str(source["fixture"])),
        run_dir=new_run_dir,
        run_id=new_run_id,
        model=str(source["model"]),
        research_question=str(source["research_question"]),
        authenticity_required=source.get("authenticity_required") is not False,
    )
    if result.get("next_state") == "FAILED_VALIDATION":
        raise NativeRerunError("RERUN_PREPARATION_FAILED")
    rerun = _read_object(new_run_dir / "run_manifest.json")
    rerun_lock = _locked_inputs(rerun)
    if source_lock != rerun_lock:
        raise NativeRerunError("RERUN_INPUT_OR_VERSION_LOCK_MISMATCH")
    rerun_manifest = {
        "schema_version": RERUN_MANIFEST_VERSION,
        "source_run_id": source["run_id"],
        "new_run_id": new_run_id,
        "new_output_dir": str(new_run_dir.resolve()),
        "locked_inputs": source_lock,
        "locked_input_hash": canonical_hash(source_lock),
        "source_manifest_hash": canonical_hash(source),
        "new_manifest_hash": canonical_hash(rerun),
        "llm_output_equality_required": False,
        "contract_and_semantic_eval_required": True,
    }
    output = new_run_dir / "native-rerun-manifest.json"
    output.write_text(
        json.dumps(rerun_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "run_id": new_run_id,
        "next_state": result["next_state"],
        "rerun_manifest_hash": canonical_hash(rerun_manifest),
    }
