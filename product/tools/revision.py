"""原作者精确补丁的纯函数；不依赖Hook、会话或模型执行。"""
from __future__ import annotations
import copy
import json
import re
from typing import Any, Mapping

_IDENTITY = {"run_id", "invocation_id", "agent", "schema_version", "skill_execution"}

def pointer(parts: list[str | int]) -> str:
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)

def _parts(path: Any) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        raise ValueError("LOCAL_REVISION_PATH_INVALID")
    if re.search(r"~(?![01])", path):
        raise ValueError("LOCAL_REVISION_PATH_INVALID")
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path[1:].split("/")]
    if parts[0] in _IDENTITY or any(p in {"", "*", "..", "-"} for p in parts):
        raise ValueError("LOCAL_REVISION_PATH_FORBIDDEN")
    return parts

def located_paths(findings: list[Mapping[str, Any]], *, exact_fields: bool = False) -> list[str]:
    """Convert only complete validator locators, never identifiers/error prose."""
    paths = set()
    for finding in findings:
        locator = finding.get("path")
        if not isinstance(locator, str):
            continue
        if locator.startswith("/"):
            try:
                parts = _parts(locator)
            except ValueError:
                continue
        elif re.fullmatch(r"(?:\$\.)?[A-Za-z_][A-Za-z_0-9]*(?:\[\d+\]|\.[A-Za-z_][A-Za-z_0-9]*)*", locator):
            parts = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|\d+", locator)
        else:
            continue
        # 仅定位到的单个主张/条件/计算选择可由原作者纠正或删除，不开放整数组。
        if (not exact_fields and len(parts) >= 2
                and parts[0] in {"claims", "observation_conditions", "calculation_selections"}
                and parts[1].isdigit()):
            parts = parts[:2]
        value = pointer(parts)
        try:
            _parts(value)
        except ValueError:
            continue
        paths.add(value)
    return sorted(p for p in paths if not any(p.startswith(q + "/") for q in paths if p != q))

def _apply(base: dict, changes: Any, allowed: list[str]) -> dict:
    if not isinstance(changes, list) or not 1 <= len(changes) <= 32:
        raise ValueError("LOCAL_REVISION_CHANGES_INVALID")
    draft = copy.deepcopy(base)
    seen = []
    def operation_order(item):
        if not isinstance(item, dict) or item.get("op") != "remove":
            return (0, "", 0)
        parts = _parts(item.get("path"))
        return (1, pointer(parts[:-1]), -int(parts[-1]) if parts[-1].isdigit() else 0)

    # 所有路径均针对原稿：先写字段，最后按索引倒序删除，不能借移位修改别的对象。
    for change in sorted(changes, key=operation_order):
        if not isinstance(change, dict) or change.get("op") not in {"add", "replace", "remove"}:
            raise ValueError("LOCAL_REVISION_OPERATION_INVALID")
        op, path = change["op"], change.get("path")
        parts = _parts(path)
        if set(change) != ({"op", "path"} if op == "remove" else {"op", "path", "value"}):
            raise ValueError("LOCAL_REVISION_OPERATION_INVALID")
        if not any(path == p or path.startswith(p + "/") for p in allowed):
            raise ValueError("LOCAL_REVISION_OUT_OF_SCOPE:" + path)
        if any(path == p or path.startswith(p + "/") or p.startswith(path + "/") for p in seen):
            raise ValueError("LOCAL_REVISION_OVERLAPPING_PATHS")
        seen.append(path)
        parent: Any = draft
        for part in parts[:-1]:
            if isinstance(parent, list) and re.fullmatch(r"0|[1-9]\d*", part) and int(part) < len(parent):
                parent = parent[int(part)]
            elif isinstance(parent, dict) and part in parent:
                parent = parent[part]
            else:
                raise ValueError("LOCAL_REVISION_TARGET_MISSING:" + path)
        key = parts[-1]
        if isinstance(parent, list):
            # 插入/删除会移动位置；同一次补丁不得借移位改动另一原始对象。
            if not re.fullmatch(r"0|[1-9]\d*", key) or int(key) >= len(parent):
                raise ValueError("LOCAL_REVISION_TARGET_MISSING:" + path)
            if op == "add":
                raise ValueError("LOCAL_REVISION_ARRAY_INSERT_FORBIDDEN")
            if op == "remove":
                parent.pop(int(key))
            else:
                parent[int(key)] = copy.deepcopy(change["value"])
        elif isinstance(parent, dict):
            if (op in {"remove", "replace"} and key not in parent) or (op == "add" and key in parent):
                raise ValueError("LOCAL_REVISION_TARGET_MISSING:" + path)
            if op == "remove":
                del parent[key]
            else:
                parent[key] = copy.deepcopy(change["value"])
        else:
            raise ValueError("LOCAL_REVISION_TARGET_MISSING:" + path)
    json.dumps(draft, allow_nan=False)
    return draft
