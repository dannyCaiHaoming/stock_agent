"""Observe the selected host CLI without starting a model or changing its lock."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .hashing import canonical_hash, file_hash


VERSION = "codex-runtime-binding/1.0.0"


def capture_codex_runtime(
    binary: str, *, expected_runtime: str, run_id: str,
    lock_path: Path, output_path: Path,
) -> dict[str, Any]:
    if output_path.exists():
        raise ValueError("CODEX_RUNTIME_BINDING_ALREADY_EXISTS")
    resolved = shutil.which(binary)
    record: dict[str, Any] = {
        "schema_version": VERSION, "run_id": run_id,
        "expected_runtime": expected_runtime, "observed_runtime": None,
        "lock_path": str(lock_path.resolve()), "lock_sha256": file_hash(lock_path),
        "binary_path": str(Path(resolved).resolve()) if resolved else None,
        "binary_sha256": None, "version_exit_code": None,
        "status": "REJECTED", "failure_code": None,
    }
    if not isinstance(expected_runtime, str) or not re.fullmatch(
        r"codex-cli/\d+\.\d+\.\d+(?:[-+][\w.-]+)?", expected_runtime
    ):
        record["failure_code"] = "CODEX_RUNTIME_LOCK_INVALID"
    elif not resolved:
        record["failure_code"] = "CODEX_RUNTIME_BINARY_MISSING"
    else:
        try:
            record["binary_sha256"] = file_hash(Path(record["binary_path"]))
            with subprocess.Popen(
                [record["binary_path"], "--version"], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True,
            ) as process:
                try:
                    stdout, _ = process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    raise
                record["version_exit_code"] = process.returncode
            match = re.fullmatch(r"codex-cli (\d+\.\d+\.\d+(?:[-+][\w.-]+)?)", stdout.strip())
            if file_hash(Path(record["binary_path"])) != record["binary_sha256"]:
                record["failure_code"] = "CODEX_RUNTIME_BINARY_CHANGED"
            elif record["version_exit_code"] != 0 or match is None:
                record["failure_code"] = "CODEX_RUNTIME_VERSION_UNVERIFIED"
            else:
                record["observed_runtime"] = "codex-cli/" + match.group(1)
                if record["observed_runtime"] != expected_runtime:
                    record["failure_code"] = "CODEX_RUNTIME_VERSION_MISMATCH"
                else:
                    record["status"] = "VERIFIED"
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            record["failure_code"] = "CODEX_RUNTIME_VERSION_UNVERIFIED"
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record.update(
        source_id="host-codex-version:" + canonical_hash({
            "output_path": str(output_path.resolve()), "lock_sha256": record["lock_sha256"],
        }), as_of=observed_at, retrieved_at=observed_at,
    )
    record["binding_hash"] = canonical_hash(record)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if record["status"] != "VERIFIED":
        raise ValueError(f"{record['failure_code']}:{record['observed_runtime']}:{expected_runtime}")
    return record


def read_codex_runtime_binding(
    path: Path, *, expected_runtime: str, run_id: str,
) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("CODEX_RUNTIME_BINDING_MISSING_OR_INVALID") from exc
    if not isinstance(record, dict):
        raise ValueError("CODEX_RUNTIME_BINDING_INVALID")
    body = dict(record)
    claimed = body.pop("binding_hash", None)
    if claimed != canonical_hash(body):
        raise ValueError("CODEX_RUNTIME_BINDING_HASH_MISMATCH")
    if (record.get("schema_version") != VERSION or record.get("run_id") != run_id
            or record.get("status") != "VERIFIED" or record.get("failure_code") is not None
            or record.get("version_exit_code") != 0
            or record.get("expected_runtime") != expected_runtime
            or record.get("observed_runtime") != expected_runtime):
        raise ValueError("CODEX_RUNTIME_BINDING_IDENTITY_MISMATCH")
    if (not isinstance(record.get("binary_path"), str)
            or not Path(record["binary_path"]).is_absolute()
            or any(not isinstance(record.get(field), str)
                   or not re.fullmatch(r"[0-9a-f]{64}", record[field])
                   for field in ("binary_sha256", "lock_sha256"))):
        raise ValueError("CODEX_RUNTIME_BINDING_METADATA_INVALID")
    # Historical proof reads do not require an old executable to remain installed.
    return record
