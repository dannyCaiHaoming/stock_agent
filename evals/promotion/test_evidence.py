"""Persist and verify deterministic-test subprocess evidence for Promotion."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.schema_validation import validate_schema_instance


TEST_EVENT_VERSION = "deterministic-test-execution/1.0.0"
TEST_REPORT_VERSION = "deterministic-test-report/1.0.0"


class DeterministicTestEvidenceError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeterministicTestEvidenceError(f"TEST_EVIDENCE_INVALID:{path}") from exc
    if not isinstance(value, Mapping):
        raise DeterministicTestEvidenceError(f"TEST_EVIDENCE_NOT_OBJECT:{path}")
    return dict(value)


def _counter(output: str, name: str) -> int:
    matches = re.findall(rf"{re.escape(name)}=(\d+)", output)
    return sum(int(item) for item in matches)


def _tests_run(output: str) -> int:
    matches = re.findall(r"Ran\s+(\d+)\s+tests?\b", output)
    return int(matches[-1]) if matches else 0


def _transcript_record(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": file_hash(path), "bytes": path.stat().st_size}


def _schema(repository_root: Path, name: str) -> dict[str, Any]:
    return _read(repository_root.resolve() / "product" / "schemas" / "runtime" / name)


def run_deterministic_test_evidence(
    repository_root: Path,
    *,
    output_dir: Path,
    tmpdir: Path,
    test_targets: Sequence[str] = (),
) -> dict[str, Any]:
    """Run unittest in a subprocess and preserve its original execution evidence."""

    repository_root = repository_root.resolve()
    output_dir = output_dir.resolve()
    tmpdir = tmpdir.resolve()
    if output_dir.exists():
        raise DeterministicTestEvidenceError("TEST_EVIDENCE_OUTPUT_EXISTS")
    if tmpdir.exists() and any(tmpdir.iterdir()):
        raise DeterministicTestEvidenceError("TEST_EVIDENCE_TMPDIR_NOT_EMPTY")
    output_dir.mkdir(parents=True)
    tmpdir.mkdir(parents=True, exist_ok=True)

    probe = tmpdir / ".promotion-test-write-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        if probe.read_text(encoding="utf-8") != "ok":
            raise OSError("probe read mismatch")
        probe.unlink()
        environment_probe = "PASS"
    except OSError:
        environment_probe = "FAIL"

    command = [sys.executable, "-m", "unittest"]
    command.extend(test_targets if test_targets else ("discover", "-s", "tests"))
    environment = os.environ.copy()
    environment["TMPDIR"] = str(tmpdir)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started_at = _utc_now()
    process = subprocess.Popen(
        command,
        cwd=repository_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout, stderr = process.communicate()
    completed_at = _utc_now()
    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    combined = f"{stdout}\n{stderr}"
    failures = _counter(combined, "failures")
    test_errors = _counter(combined, "errors")
    environment_errors = 0 if environment_probe == "PASS" else 1
    event: dict[str, Any] = {
        "schema_version": TEST_EVENT_VERSION,
        "event_id": f"test-event-{uuid.uuid4()}",
        "runner": "python-unittest-subprocess/1.0.0",
        "command": command,
        "cwd": str(repository_root),
        "tmpdir": str(tmpdir),
        "started_at": started_at,
        "completed_at": completed_at,
        "process_id": process.pid,
        "exit_code": process.returncode,
        "tests_run": _tests_run(combined),
        "assertion_failures": failures,
        "test_errors": test_errors,
        "environment_errors": environment_errors,
        "environment_probe": environment_probe,
        "stdout": _transcript_record(stdout_path),
        "stderr": _transcript_record(stderr_path),
    }
    event["event_hash"] = canonical_hash(event)
    validate_schema_instance(event, _schema(repository_root, "deterministic-test-execution.schema.json"))
    event_path = output_dir / "execution-event.json"
    _write_json(event_path, event)

    passed = (
        process.returncode == 0
        and event["tests_run"] > 0
        and failures == 0
        and test_errors == 0
        and environment_errors == 0
    )
    report: dict[str, Any] = {
        "schema_version": TEST_REPORT_VERSION,
        "status": "PASS" if passed else "FAIL",
        "event": {"path": str(event_path), "sha256": file_hash(event_path)},
        **{
            key: event[key]
            for key in (
                "event_id",
                "command",
                "cwd",
                "tmpdir",
                "started_at",
                "completed_at",
                "exit_code",
                "tests_run",
                "assertion_failures",
                "test_errors",
                "environment_errors",
            )
        },
    }
    report["result_hash"] = canonical_hash(report)
    validate_schema_instance(report, _schema(repository_root, "deterministic-test-report.schema.json"))
    _write_json(output_dir / "result.json", report)
    return report


def verify_deterministic_test_evidence(
    report_path: Path,
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Recompute a deterministic-test report from the bound subprocess event."""

    report_path = report_path.resolve()
    report = _read(report_path)
    if repository_root is not None:
        validate_schema_instance(report, _schema(repository_root, "deterministic-test-report.schema.json"))
    if report.get("schema_version") != TEST_REPORT_VERSION:
        raise DeterministicTestEvidenceError("TEST_REPORT_VERSION_INVALID")
    report_body = dict(report)
    if report_body.pop("result_hash", None) != canonical_hash(report_body):
        raise DeterministicTestEvidenceError("TEST_REPORT_HASH_INVALID")
    event_record = report.get("event")
    if not isinstance(event_record, Mapping) or set(event_record) != {"path", "sha256"}:
        raise DeterministicTestEvidenceError("TEST_EVENT_RECORD_INVALID")
    event_path = Path(str(event_record["path"])).resolve()
    if not event_path.is_file() or file_hash(event_path) != event_record.get("sha256"):
        raise DeterministicTestEvidenceError("TEST_EVENT_HASH_MISMATCH")
    event = _read(event_path)
    if repository_root is not None:
        validate_schema_instance(event, _schema(repository_root, "deterministic-test-execution.schema.json"))
    event_body = dict(event)
    if event_body.pop("event_hash", None) != canonical_hash(event_body):
        raise DeterministicTestEvidenceError("TEST_EVENT_SELF_HASH_INVALID")
    required = {
        "schema_version", "event_id", "runner", "command", "cwd", "tmpdir",
        "started_at", "completed_at", "process_id", "exit_code", "tests_run",
        "assertion_failures", "test_errors", "environment_errors", "environment_probe",
        "stdout", "stderr", "event_hash",
    }
    if set(event) != required or event.get("schema_version") != TEST_EVENT_VERSION:
        raise DeterministicTestEvidenceError("TEST_EVENT_CONTRACT_INVALID")
    if not isinstance(event.get("command"), list) or event["command"][1:3] != ["-m", "unittest"]:
        raise DeterministicTestEvidenceError("TEST_EVENT_COMMAND_INVALID")
    if not isinstance(event.get("process_id"), int) or event["process_id"] <= 0:
        raise DeterministicTestEvidenceError("TEST_EVENT_PROCESS_INVALID")
    for name in ("stdout", "stderr"):
        record = event[name]
        if not isinstance(record, Mapping) or set(record) != {"path", "sha256", "bytes"}:
            raise DeterministicTestEvidenceError(f"TEST_EVENT_TRANSCRIPT_INVALID:{name}")
        path = Path(str(record["path"])).resolve()
        if (
            not path.is_file()
            or file_hash(path) != record.get("sha256")
            or path.stat().st_size != record.get("bytes")
        ):
            raise DeterministicTestEvidenceError(f"TEST_EVENT_TRANSCRIPT_HASH_MISMATCH:{name}")
    transcript = "\n".join(
        Path(str(event[name]["path"])).read_text(encoding="utf-8")
        for name in ("stdout", "stderr")
    )
    if _tests_run(transcript) != event.get("tests_run"):
        raise DeterministicTestEvidenceError("TEST_EVENT_COUNT_MISMATCH")
    if _counter(transcript, "failures") != event.get("assertion_failures"):
        raise DeterministicTestEvidenceError("TEST_EVENT_FAILURE_COUNT_MISMATCH")
    if _counter(transcript, "errors") != event.get("test_errors"):
        raise DeterministicTestEvidenceError("TEST_EVENT_ERROR_COUNT_MISMATCH")
    copied = {
        key: event[key]
        for key in (
            "event_id", "command", "cwd", "tmpdir", "started_at", "completed_at",
            "exit_code", "tests_run", "assertion_failures", "test_errors", "environment_errors",
        )
    }
    if any(report.get(key) != value for key, value in copied.items()):
        raise DeterministicTestEvidenceError("TEST_REPORT_EVENT_MISMATCH")
    passed = (
        event["environment_probe"] == "PASS"
        and event["exit_code"] == 0
        and event["tests_run"] > 0
        and event["assertion_failures"] == 0
        and event["test_errors"] == 0
        and event["environment_errors"] == 0
    )
    expected_status = "PASS" if passed else "FAIL"
    if report.get("status") != expected_status:
        raise DeterministicTestEvidenceError("TEST_REPORT_STATUS_MISMATCH")
    return report
