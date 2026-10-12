"""原 Agent 的有界局部编辑；不选择引用、不推断值、不代写研究。

约束包由 Hook 的可信首稿记录产生。短引用仅定位该包，完整身份和 hash
留在运行层；补丁应用后仍须经过调用方原有的完整报告校验。
"""

from __future__ import annotations

import copy
from difflib import SequenceMatcher
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError
from product.tools.revision import pointer, _parts, located_paths, _apply

VERSION = "research-local-revision/1.0.0"
MAX_BYTES = 256 * 1024
_IDENTITY = {"run_id", "invocation_id", "agent", "schema_version", "skill_execution"}

# 与既有 _apply 的操作形状一致；只解释运输格式，不推断要修什么内容。
REVISION_FORMAT_GUIDE = {
    "type": "object", "additionalProperties": False,
    "required": ["base_draft_ref", "changes"],
    "properties": {
        "base_draft_ref": {"type": "string"},
        "changes": {"type": "array", "minItems": 1, "maxItems": 32,
            "items": {"oneOf": [
                {"type": "object", "additionalProperties": False,
                 "required": ["op", "path", "value"], "properties": {
                     "op": {"enum": ["add", "replace"]},
                     "path": {"type": "string"}, "value": {}}},
                {"type": "object", "additionalProperties": False,
                 "required": ["op", "path"], "properties": {
                     "op": {"const": "remove"}, "path": {"type": "string"}}},
            ]}},
    },
    "description": (
        "Each change requires op. add adds a missing field; replace changes an existing field; "
        "remove deletes it and has no value; deleting an array item uses remove, not replace with null. "
        "Paths must be inside the returned allowed_paths, "
        "including permitted child fields. Choose the corrected content yourself; no full resubmission."
    ),
}











def _identity(payload: Mapping[str, Any], record: Mapping[str, Any]) -> dict:
    binding = record.get("trusted_task_binding")
    if (record.get("identity_binding", {}).get("status") != "BOUND"
            or not isinstance(binding, Mapping)):
        raise ValueError("LOCAL_REVISION_IDENTITY_UNBOUND")
    if record.get("execution_context") == "MAIN_THREAD":
        # Stop 属于主会话；不能给 CIO 编造 Subagent 的 child/session 身份。
        if payload.get("hook_event_name") != "Stop" or payload.get("agent_id") is not None:
            raise ValueError("LOCAL_REVISION_MAIN_THREAD_INVALID")
        result = {"execution_context": "MAIN_THREAD", "session_id": payload.get("session_id"),
                  "agent_type": binding.get("agent"), "model": payload.get("model")}
    else:
        result = {key: payload.get(key) for key in ("session_id", "agent_id", "agent_type", "model")}
    result["task"] = dict(binding)
    if any(not isinstance(v, str) or not v for k, v in result.items() if k != "task"):
        raise ValueError("LOCAL_REVISION_IDENTITY_INVALID")
    return result


def _path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("LOCAL_REVISION_PATH_INVALID")
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("LOCAL_REVISION_SYMLINK_FORBIDDEN")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("LOCAL_REVISION_PATH_INVALID")
    return path


def bind(root: Path, payload: Mapping[str, Any], record: Mapping[str, Any],
         raw: Mapping[str, Any], repair: Mapping[str, Any], findings: list[Mapping[str, Any]],
         *, exact_fields: bool = False) -> dict | None:
    """Persist an immutable bound base; return a small model-visible edit contract."""
    identity = _identity(payload, record)
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or len(message.encode()) > MAX_BYTES:
        return None
    try:
        draft = json.loads(message)
    except ValueError:
        return None  # 无可证明的对象边界时，不伪造 AST 或自动修 JSON。
    allowed = located_paths(findings, exact_fields=exact_fields)
    if not isinstance(draft, dict) or not allowed:
        return None
    json.dumps(draft, allow_nan=False)
    base_path = raw.get("raw_path")
    if not isinstance(base_path, str) or raw.get("raw_output_hash") != canonical_hash({"assistant_message": message}):
        raise ValueError("LOCAL_REVISION_BASE_BINDING_INVALID")
    if _path(root, base_path).read_text() != message + ("" if message.endswith("\n") else "\n"):
        raise ValueError("LOCAL_REVISION_BASE_DRIFT")
    relative = base_path + ".revision.json"
    value = {"version": VERSION, "identity": identity, "base_path": base_path,
             "raw_output_hash": raw["raw_output_hash"], "base_draft": draft,
             "base_hash": canonical_hash(draft), "allowed_paths": allowed,
             "base_draft_ref": "b." + secrets.token_urlsafe(18),
             "validation_error": repair["validation_error"]}
    value["content_hash"] = legacy_envelope_hash(value, hash_field="content_hash")
    path = _path(root, relative)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    return {"repair_contract": VERSION, "base_draft_ref": value["base_draft_ref"],
            "allowed_paths": allowed, "binding_path": relative, "binding_hash": value["content_hash"]}





def _full_draft_changes(base: Any, candidate: Any, allowed: list[str], parts=None) -> list[dict]:
    """兼容完整对象传输时仅比较显式差异；不选择证据、不修正候选内容。"""
    parts = [] if parts is None else parts
    if canonical_hash(base) == canonical_hash(candidate):
        return []
    path = pointer(parts) if parts else ""
    if path and any(path == p or path.startswith(p + "/") for p in allowed):
        return [{"op": "replace", "path": path, "value": candidate}]
    if isinstance(base, dict) and isinstance(candidate, dict):
        result = []
        for key in sorted(set(base) | set(candidate)):
            child = pointer(parts + [key])
            if key not in base or key not in candidate:
                if not any(child == p or child.startswith(p + "/") for p in allowed):
                    raise ValueError("LOCAL_REVISION_OUT_OF_SCOPE:" + child)
                result.append({"op": "add", "path": child, "value": candidate[key]} if key not in base
                              else {"op": "remove", "path": child})
            else:
                result.extend(_full_draft_changes(base[key], candidate[key], allowed, parts + [key]))
        return result
    if isinstance(base, list) and isinstance(candidate, list):
        if len(base) == len(candidate):
            return [change for i, (left, right) in enumerate(zip(base, candidate))
                    for change in _full_draft_changes(left, right, allowed, parts + [i])]
        result = []
        matcher = SequenceMatcher(a=[canonical_hash(v) for v in base],
                                  b=[canonical_hash(v) for v in candidate], autojunk=False)
        for op, start, end, new_start, new_end in matcher.get_opcodes():
            if op == "equal":
                continue
            if op != "delete":
                raise ValueError("LOCAL_REVISION_ARRAY_SHIFT_FORBIDDEN")
            for i in range(start, end):
                child = pointer(parts + [i])
                if child not in allowed:
                    raise ValueError("LOCAL_REVISION_OUT_OF_SCOPE:" + child)
                result.append({"op": "remove", "path": child})
        return result
    raise ValueError("LOCAL_REVISION_OUT_OF_SCOPE:" + path)


def verify_binding(root: Path, payload: Mapping[str, Any], record: Mapping[str, Any],
                   first: Mapping[str, Any]) -> dict | None:
    """先验证身份和不可变基础稿；不消费修订额度，也不解析新稿。"""
    identity = _identity(payload, record)
    repair = first.get("repair_request", {})
    if repair.get("repair_contract") != VERSION:
        return None
    try:
        verify_legacy_envelope_hash(first, hash_field="event_hash", location="local-revision:first-Stop")
    except HashContractError as exc:
        raise ValueError(f"LOCAL_REVISION_EVENT_DRIFT:{exc}") from exc
    path = _path(root, repair["binding_path"])
    if path.stat().st_size > MAX_BYTES * 2:
        raise ValueError("LOCAL_REVISION_BINDING_TOO_LARGE")
    binding = json.loads(path.read_text())
    try:
        verify_legacy_envelope_hash(binding, hash_field="content_hash", location=repair["binding_path"])
    except HashContractError as exc:
        raise ValueError(f"LOCAL_REVISION_BINDING_DRIFT:{exc}") from exc
    if (binding.get("version") != VERSION or binding.get("identity") != identity
            or repair.get("binding_hash") != binding.get("content_hash")
            or binding.get("base_hash") != canonical_hash(binding["base_draft"])):
        raise ValueError("LOCAL_REVISION_BINDING_DRIFT")
    raw = _path(root, binding["base_path"]).read_text()
    if canonical_hash(json.loads(raw)) != binding["base_hash"]:
        raise ValueError("LOCAL_REVISION_BASE_DRIFT")
    # 原稿只允许保存时附加一个换行；hash 仍验证原始事件中的完整 message。
    candidates = [raw, raw[:-1]] if raw.endswith("\n") else [raw]
    if binding["raw_output_hash"] not in [canonical_hash({"assistant_message": v}) for v in candidates]:
        raise ValueError("LOCAL_REVISION_BASE_DRIFT")
    return binding


def resolve(root: Path, payload: Mapping[str, Any], record: dict, first: Mapping[str, Any]) -> dict:
    """Resolve only a patch bound to the exact original session and task."""
    binding = verify_binding(root, payload, record, first)
    if binding is None:
        return dict(payload)
    message = payload["last_assistant_message"]
    if not isinstance(message, str) or len(message.encode()) > MAX_BYTES:
        raise ValueError("LOCAL_REVISION_DRAFT_TOO_LARGE")
    patch = json.loads(message)
    if not isinstance(patch, dict):
        raise ValueError("LOCAL_REVISION_BASE_REFERENCE_INVALID")
    if "base_draft_ref" in patch or "changes" in patch:
        if set(patch) != {"base_draft_ref", "changes"} or patch["base_draft_ref"] != binding["base_draft_ref"]:
            raise ValueError("LOCAL_REVISION_BASE_REFERENCE_INVALID")
        changes = patch["changes"]
        draft = _apply(binding["base_draft"], changes, binding["allowed_paths"])
        transport = "NATIVE_PATCH"
    else:
        # 已有完整对象传输不要求重抄技术引用，但仍绑定同一首稿且严格检查其它字段。
        changes = _full_draft_changes(binding["base_draft"], patch, binding["allowed_paths"])
        draft = _apply(binding["base_draft"], changes, binding["allowed_paths"]) if changes else copy.deepcopy(patch)
        if canonical_hash(draft) != canonical_hash(patch):
            raise ValueError("LOCAL_REVISION_OUTSIDE_FIELDS_DRIFT")
        transport = "FULL_OBJECT_COMPATIBILITY"
    record["local_revision"] = {"version": VERSION, "binding_hash": binding["content_hash"],
                                "base_hash": binding["base_hash"], "output_hash": canonical_hash(draft),
                                "changed_paths": [c["path"] for c in changes], "transport": transport}
    return {**payload, "last_assistant_message": json.dumps(draft, ensure_ascii=False, allow_nan=False)}
