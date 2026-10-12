"""原生业务报告的只读归档；不把历史保存升级为当前执行或质量证明。"""
from __future__ import annotations
import copy
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash
from product.runtime.research_memory import ResearchMemory
from product.tools.research import ResearchTools, _private_root, _read_json, _write_json, validate_gate
from product.tools.report_reading import validate_report, render_report
from product.tools.report_submission import read_submission

VERSION = "native-research-archive/1.0.0"


def _archive_value(tools: ResearchTools, *, draft_ref: str) -> dict[str, Any]:
    task, gate = tools._authorize()
    report = read_submission(tools, draft_ref=draft_ref)
    value = {"schema_version": VERSION, "report": report, "task": copy.deepcopy(task),
             "input": _read_json(tools.root/"input.json"), "gate": copy.deepcopy(gate),
             "markdown": render_report(report)}
    value["archive_hash"] = canonical_hash(value)
    validate_archive(value)
    return value


def archive_report(tools: ResearchTools, *, draft_ref: str, memory: ResearchMemory) -> dict[str, Any]:
    value = _archive_value(tools, draft_ref=draft_ref)
    stored = memory.store_object(value)
    return {**stored, "archive_hash": value["archive_hash"], "report_hash": value["report"]["report_hash"],
            "host_execution": "UNVERIFIED", "content_verdict": "NOT_REVIEWED"}


def export_report(tools: ResearchTools, *, draft_ref: str, memory_root: Path,
                  output_dir: Path) -> dict[str, Any]:
    """操作方显式归档精确有效稿；凭据/回执校验先于写入，不覆盖旧导出。"""
    value = _archive_value(tools, draft_ref=draft_ref)
    memory_root = Path(memory_root)
    memory_destination, export_destination = memory_root.resolve(), Path(output_dir).resolve()
    if (memory_destination.is_relative_to(export_destination)
            or export_destination.is_relative_to(memory_destination)):
        raise ValueError("NATIVE_RESEARCH_ARCHIVE_DESTINATIONS_OVERLAP")
    # Validate both destinations before creating a Memory database or object.
    memory_path = _private_root(memory_root if memory_root.exists() else memory_root.parent)
    output_parent = _private_root(Path(output_dir).parent)
    output_path = output_parent / Path(output_dir).name
    output_path = _private_root(output_path, create=True)
    if not memory_root.exists():
        memory_path = _private_root(memory_root, create=True)
    memory = ResearchMemory(memory_path)
    stored = memory.store_object(value)
    _write_json(output_path/"native-research-archive.json", value)
    return {**stored, "archive_hash": value["archive_hash"],
            "report_hash": value["report"]["report_hash"], "model_calls": 0,
            "status": "ARCHIVED_NOT_HOST_VERIFIED", "host_execution": "UNVERIFIED",
            "content_verdict": "NOT_REVIEWED"}


def validate_archive(value: Mapping[str, Any]) -> None:
    if (set(value) != {"schema_version", "report", "task", "input", "gate", "markdown", "archive_hash"}
            or value.get("schema_version") != VERSION
            or value.get("archive_hash") != canonical_hash({k: v for k, v in value.items() if k != "archive_hash"})):
        raise ValueError("NATIVE_RESEARCH_ARCHIVE_HASH_INVALID")
    task, gate, original = value["task"], value["gate"], value["input"]
    from product.tools.research_input import validate_research_input, research_input_binding
    validate_research_input(original, historical=True)
    validate_gate(gate)
    if (task.get("task_hash") != canonical_hash({k: v for k, v in task.items() if k != "task_hash"})
            or task["input_binding"] != research_input_binding(original, historical=True)
            or task["input_hash"] != canonical_hash(original)
            or task["gate_hash"] != gate["bundle_hash"]):
        raise ValueError("NATIVE_RESEARCH_ARCHIVE_BINDING_INVALID")
    validate_report(value["report"], input_binding=task["input_binding"], gate_hash=gate["bundle_hash"],
                    security_id=task["security"]["security_id"], cutoff=gate["decision_cutoff"])
    if value["report"]["task_hash"] != task["task_hash"] or value["markdown"] != render_report(value["report"]):
        raise ValueError("NATIVE_RESEARCH_ARCHIVE_BINDING_INVALID")


def read_archive(memory: ResearchMemory, *, object_ref: str, object_hash: str) -> dict[str, Any]:
    import json
    value = json.loads(memory.read_object(object_ref, object_hash))
    validate_archive(value)
    return value


def reuse_archive(memory: ResearchMemory, *, object_ref: str, object_hash: str,
                  research_input: Mapping[str, Any], gate: Mapping[str, Any], expected_task: Mapping[str, Any]) -> dict[str, Any]:
    """显式精确版本复用；不搜索最近报告、不创建模型或伪造本次取证。"""
    archive = read_archive(memory, object_ref=object_ref, object_hash=object_hash)
    validate_gate(gate)
    task = archive["task"]
    from product.tools.resource_bindings import resource_bindings
    if (archive["input"] != dict(research_input) or archive["gate"] != dict(gate)
            or not task.get("resource_bindings")
            or task["resource_bindings"] != resource_bindings(task["capability"], task["role"])
            or expected_task.get("task_hash") != canonical_hash({k: v for k, v in expected_task.items() if k != "task_hash"})):
        raise ValueError("NATIVE_RESEARCH_REUSE_INPUT_OR_VERSION_DRIFT")
    transient = {"task_id", "task_hash", "source_id", "retrieved_at", "connection_binding"}
    if {k: v for k, v in task.items() if k not in transient} != {k: v for k, v in expected_task.items() if k not in transient}:
        raise ValueError("NATIVE_RESEARCH_REUSE_TASK_DRIFT")
    old_connection, new_connection = task.get("connection_binding"), expected_task.get("connection_binding")
    if (old_connection or {}).get("request_hash") != (new_connection or {}).get("request_hash"):
        raise ValueError("NATIVE_RESEARCH_REUSE_REQUEST_DRIFT")
    report = copy.deepcopy(archive["report"])
    if report["research"]["status"] not in {"COMPLETE", "LOW_CONFIDENCE"}:
        raise ValueError("NATIVE_RESEARCH_REUSE_NOT_READY")
    return {"report": report, "archive_hash": archive["archive_hash"], "model_calls": 0,
            "business_reuse": "VALIDATED", "host_execution": "UNVERIFIED", "content_verdict": "NOT_REVIEWED"}


def read_archive_file(path: Path) -> dict[str, Any]:
    """仅读取显式准入产物；文件不可是symlink，不回写或启动任何执行器。"""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("NATIVE_RESEARCH_ARCHIVE_PATH_INVALID")
    import json
    value = json.loads(path.read_bytes())
    validate_archive(value)
    return value
