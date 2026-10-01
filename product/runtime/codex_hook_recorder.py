"""Record privacy-minimized Codex subagent lifecycle evidence.

The recorder validates dispatch inputs and observes lifecycle events. It never orchestrates an Agent and
never persists prompts, hidden reasoning or tool payloads. Opted-in live runs
persist only the Specialist's final structured report, without model re-copying.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

if __package__:
    from .hashing import canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError
else:
    # Codex invokes this hook by script path; Python then places this directory
    # (not the repository or installed product root) on sys.path.
    from hashing import canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError


RECORDER_VERSION = "codex-subagent-hook-recorder/1.19.1"
SUPPORTED_EVENTS = {"SubagentStart", "SubagentStop"}
COMMON_STOCK_STAGE_VERSION = "common-stock-research-runtime/1.0.0"
MULTIDIMENSIONAL_STAGE_VERSION = "multidimensional-holding-research-runtime/2.0.0"
RESEARCH_MATERIALS_STAGE_VERSION = "multidimensional-material-preparation-runtime/1.1.0"
INDEPENDENT_SKEPTIC_STAGE_VERSION = "independent-skeptic-runtime/1.0.0"
COMMON_STOCK_EVAL_VERSION = "common-stock-research-eval-runtime/1.0.0"


def _canonical_hash(value: Any) -> str:
    return canonical_hash(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_scoped_log(
    environ: Mapping[str, str], *, environment_key: str = "STOCK_AGENT_SUBAGENT_EVENT_LOG"
) -> Path:
    run_text = environ.get("STOCK_AGENT_RUN_DIR", "")
    log_text = environ.get(environment_key, "")
    if not run_text or not log_text:
        raise ValueError("HOOK_OUTPUT_ENVIRONMENT_MISSING")
    run_dir = Path(run_text).resolve()
    log_path = Path(log_text).resolve()
    if not log_path.is_relative_to(run_dir):
        raise ValueError("HOOK_OUTPUT_OUTSIDE_RUN_DIR")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def _dispatch_record(payload: Mapping[str, Any], *, decision: str) -> dict[str, Any]:
    required = ("session_id", "turn_id", "tool_name", "tool_use_id", "cwd")
    if any(not isinstance(payload.get(field), str) or not payload[field] for field in required):
        raise ValueError("HOOK_DISPATCH_IDENTITY_INCOMPLETE")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        raise ValueError("HOOK_DISPATCH_INPUT_INVALID")
    agent_type = tool_input.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type:
        agent_type = None
    record: dict[str, Any] = {
        "schema_version": "codex-subagent-dispatch/1.0.0",
        "recorder_version": RECORDER_VERSION,
        "hook_event_name": "PreToolUse",
        "parent_session_id": payload["session_id"],
        "turn_id": payload["turn_id"],
        "tool_name": payload["tool_name"],
        "tool_use_id": payload["tool_use_id"],
        "agent_type": agent_type,
        "task_name": tool_input.get("task_name"),
        "fork_turns": tool_input.get("fork_turns"),
        "model": payload.get("model"),
        "cwd": payload["cwd"],
        "permission_mode": payload.get("permission_mode"),
        "decision": decision,
        "observed_at": _utc_now(),
        "raw_prompt_or_reasoning_retained": False,
    }
    record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
    return record


def _reserved_agents(
    log_path: Path, *, parent_session_id: str, reserve_task_name: bool = False
) -> set[str]:
    if not log_path.is_file():
        return set()
    reserved: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(event, Mapping)
            and event.get("decision") == "ALLOW"
            and event.get("parent_session_id") == parent_session_id
            and isinstance(event.get("task_name" if reserve_task_name else "agent_type"), str)
        ):
            reserved.add(str(event["task_name" if reserve_task_name else "agent_type"]))
    return reserved


def _append_record(log_path: Path, record: Mapping[str, Any]) -> None:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _invocation_module():
    # The launcher also executes this file directly, without a package context.
    if __package__:
        from . import invocation
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from product.runtime import invocation
    return invocation


def _common_stock_stage(environment: Mapping[str, str]) -> bool:
    return environment.get("STOCK_AGENT_COMMON_STOCK_STAGE") == COMMON_STOCK_STAGE_VERSION


def _multidimensional_stage(environment: Mapping[str, str]) -> bool:
    return environment.get("STOCK_AGENT_MULTIDIMENSIONAL_STAGE") == MULTIDIMENSIONAL_STAGE_VERSION


def _research_materials_stage(environment: Mapping[str, str]) -> bool:
    return environment.get("STOCK_AGENT_RESEARCH_MATERIALS_STAGE") == RESEARCH_MATERIALS_STAGE_VERSION


def _independent_skeptic_stage(environment: Mapping[str, str]) -> bool:
    return environment.get("STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE") == INDEPENDENT_SKEPTIC_STAGE_VERSION


def _research_stage(environment: Mapping[str, str]) -> bool:
    return (
        _common_stock_stage(environment)
        or _multidimensional_stage(environment)
        or _research_materials_stage(environment)
        or _independent_skeptic_stage(environment)
    )


def _common_stock_module():
    if __package__:
        from . import common_stock_stage
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from product.runtime import common_stock_stage
    return common_stock_stage


def _multidimensional_module():
    if __package__:
        from . import multidimensional_stage
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from product.runtime import multidimensional_stage
    return multidimensional_stage


def _research_materials_module():
    if __package__:
        from . import research_materials_stage
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from product.runtime import research_materials_stage
    return research_materials_stage


def _independent_skeptic_module():
    if __package__:
        from . import independent_skeptic_stage
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from product.runtime import independent_skeptic_stage
    return independent_skeptic_stage


def _research_module(environment: Mapping[str, str]):
    if _independent_skeptic_stage(environment):
        return _independent_skeptic_module()
    if _research_materials_stage(environment):
        return _research_materials_module()
    return _multidimensional_module() if _multidimensional_stage(environment) else _common_stock_module()


def _common_stock_eval(environment: Mapping[str, str]) -> bool:
    return environment.get("STOCK_AGENT_COMMON_STOCK_EVAL") == COMMON_STOCK_EVAL_VERSION


def _common_stock_eval_module():
    if __package__:
        from . import common_stock_eval
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from product.runtime import common_stock_eval
    return common_stock_eval


def _research_index(environment: Mapping[str, str]) -> dict[str, Any]:
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    if _independent_skeptic_stage(environment):
        return _independent_skeptic_module().read_dispatch_index(
            run_dir, environment.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX")
        )
    relative = (
        "research/skeptic/dispatch-index.json"
        if _independent_skeptic_stage(environment)
        else "research/dispatch-index.json"
    )
    value = json.loads((run_dir / relative).read_text(encoding="utf-8"))
    body = {key: item for key, item in value.items() if key != "index_hash"}
    expected_version = _research_module(environment).DISPATCH_VERSION
    if (
        value.get("schema_version") != expected_version
        or value.get("index_hash") != _canonical_hash(body)
    ):
        raise ValueError("RESEARCH_DISPATCH_INDEX_INVALID")
    return value


def _selected_research_tasks(environment: Mapping[str, str]) -> set[str] | None:
    """返回宿主定点入口锁定的任务集合；未知或歧义选择必须拒绝。"""

    selected_many = environment.get("STOCK_AGENT_RESEARCH_TASK_NAMES")
    selected_one = environment.get("STOCK_AGENT_RESEARCH_TASK_NAME")
    if selected_many is None and selected_one is None:
        return None
    if selected_many is not None:
        try:
            decoded = json.loads(selected_many)
        except json.JSONDecodeError as exc:
            raise ValueError("RESEARCH_TARGET_TASKS_INVALID") from exc
        if (
            not isinstance(decoded, list)
            or not decoded
            or any(not isinstance(item, str) or not item.strip() for item in decoded)
            or len(set(decoded)) != len(decoded)
        ):
            raise ValueError("RESEARCH_TARGET_TASKS_INVALID")
        selected = set(decoded)
        if selected_one is not None and selected != {selected_one.strip()}:
            raise ValueError("RESEARCH_TARGET_TASKS_CONFLICT")
    else:
        if not isinstance(selected_one, str) or not selected_one.strip():
            raise ValueError("RESEARCH_TARGET_TASK_INVALID")
        selected = {selected_one.strip()}
    known = {
        item.get("task_name") for item in _research_index(environment)["tasks"]
        if isinstance(item.get("task_name"), str)
    }
    if not selected <= known:
        raise ValueError("RESEARCH_TARGET_TASK_UNKNOWN")
    return selected


def _verify_dispatch_input(tool_input: Mapping[str, Any], environment: Mapping[str, str]) -> dict[str, Any]:
    if _common_stock_eval(environment):
        module = _common_stock_eval_module()
        eval_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
        expected_model = environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL")
        packet = module.build_common_stock_eval_packet(
            eval_dir, expected_model=expected_model
        )
        actual = tool_input.get("message")
        return {
            "contract_version": module.EVAL_RUNTIME_VERSION,
            "input_hash": packet["input_manifest"]["input_hash"],
            "packet_hash": _canonical_hash(packet),
            "parent_message_hash": (
                _canonical_hash({"message": actual}) if isinstance(actual, str) else None
            ),
            "parent_message_authoritative": False,
            "matched": (
                tool_input.get("agent_type") == "dev_eval"
                and tool_input.get("task_name") == "grade_common_stock_report"
                and tool_input.get("fork_turns") == "none"
                and isinstance(actual, str)
                and 0 < len(actual.encode("utf-8")) <= 4096
            ),
        }
    if _research_stage(environment):
        stage = _research_module(environment)
        task_name = tool_input.get("task_name")
        selected_tasks = _selected_research_tasks(environment)
        if selected_tasks is not None and task_name not in selected_tasks:
            raise ValueError("RESEARCH_TARGET_TASK_MISMATCH")
        build_packet = (
            stage.build_skeptic_dispatch_packet
            if _independent_skeptic_stage(environment)
            else stage.build_research_materials_dispatch_packet
            if _research_materials_stage(environment)
            else stage.build_multidimensional_dispatch_packet
            if _multidimensional_stage(environment)
            else stage.build_common_stock_dispatch_packet
        )
        if _independent_skeptic_stage(environment):
            packet = build_packet(
                Path(__file__).resolve().parents[2],
                Path(environment["STOCK_AGENT_RUN_DIR"]), str(task_name),
                index_ref=environment.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"),
            )
        elif _multidimensional_stage(environment) or _research_materials_stage(environment):
            packet = build_packet(
                Path(__file__).resolve().parents[2],
                Path(environment["STOCK_AGENT_RUN_DIR"]),
                str(task_name),
                include_dependency_reports=False,
            )
        else:
            packet = build_packet(
                Path(__file__).resolve().parents[2],
                Path(environment["STOCK_AGENT_RUN_DIR"]),
                str(task_name),
            )
        actual = tool_input.get("message")
        return {
            "contract_version": stage.DISPATCH_VERSION,
            "packet_hash": _canonical_hash(packet),
            "parent_message_hash": (
                _canonical_hash({"message": actual}) if isinstance(actual, str) else None
            ),
            "parent_message_authoritative": False,
            "matched": (
                isinstance(actual, str)
                and 0 < len(actual.encode("utf-8")) <= 4096
                and tool_input.get("fork_turns") == "none"
                and tool_input.get("agent_type") == packet["identity"]["agent"]
            ),
        }
    invocation = _invocation_module()
    agent = tool_input["agent_type"]
    if environment.get("STOCK_AGENT_START_CONTEXT") == invocation.START_CONTEXT_VERSION:
        # The frozen input is delivered independently. Natural-language wording
        # is not an execution identity; never make the model copy a hash receipt.
        _, context = invocation.build_specialist_start_context(
            Path(__file__).resolve().parents[2], Path(environment["STOCK_AGENT_RUN_DIR"]), agent)
        return {"contract_version": invocation.START_CONTEXT_VERSION,
                "input_hash": context["input_hash"],
                "matched": (tool_input.get("task_name") == invocation.SPECIALIST_TASK_NAMES[agent]
                            and tool_input.get("fork_turns") == "none")}
    build_message = (invocation.build_specialist_dispatch_ticket
                     if environment.get("STOCK_AGENT_START_CONTEXT") == invocation.LEGACY_START_CONTEXT_VERSION
                     else invocation.build_specialist_dispatch_message)
    expected = build_message(
        Path(__file__).resolve().parents[2], Path(environment["STOCK_AGENT_RUN_DIR"]), agent,
    )
    actual = tool_input.get("message")
    binding = {
        "contract_version": (invocation.LEGACY_START_CONTEXT_VERSION
                             if environment.get("STOCK_AGENT_START_CONTEXT") == invocation.LEGACY_START_CONTEXT_VERSION
                             else "specialist-dispatch/1.0.0"),
        "expected_message_hash": _canonical_hash({"message": expected}),
        "actual_message_hash": _canonical_hash({"message": actual}),
        "matched": (
            actual == expected
            and tool_input.get("task_name") == invocation.SPECIALIST_TASK_NAMES[agent]
            and tool_input.get("fork_turns") == "none"
        ),
    }
    return binding


def _handle_pre_tool_use(
    payload: Mapping[str, Any], *, environment: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    dispatch_log = _resolve_scoped_log(
        environment,
        environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG",
    )
    expected = _expected_parallel_agents(environment)
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        raise ValueError("HOOK_DISPATCH_INPUT_INVALID")
    tool_name = "".join(
        character for character in str(payload.get("tool_name", "")).lower()
        if character.isalnum()
    )
    research_control = next(
        (
            name for name in ("followuptask", "sendmessage", "sendinput", "interruptagent", "listagents")
            if tool_name.endswith(name)
        ),
        None,
    )
    research_wait = tool_name.endswith("waitagent")
    if _research_stage(environment) and (research_control is not None or research_wait):
        parent_session_id = str(payload.get("session_id", ""))
        event_log = _resolve_scoped_log(environment)
        # 当前 CLI 的子任务 PreToolUse 仍携带父 session_id；不能只凭它
        # 把研究子 Agent 当协调器，否则会令子任务等待自身永不终止。
        child_turn = False
        if event_log.is_file():
            for event in _read_jsonl_records(event_log):
                context = event.get("context_binding", {})
                if (event.get("hook_event_name") == "SubagentStart"
                        and event.get("parent_session_id") == parent_session_id
                        and event.get("turn_id") == payload.get("turn_id")
                        and event.get("agent_type") in expected
                        and context.get("status") == "DELIVERED"
                        and isinstance(context.get("task_name"), str)
                        and event.get("event_hash") == legacy_envelope_hash(event, hash_field="event_hash")):
                    child_turn = True
                    break
        if child_turn:
            record = _dispatch_record(payload, decision="DENY_RESEARCH_CHILD_COORDINATION")
            lock_path = dispatch_log.with_suffix(dispatch_log.suffix + ".lock")
            with lock_path.open("a", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                _append_record(dispatch_log, record)
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            return record, {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "你是研究子 Agent，不是协调父线程；不得 wait_agent、list_agents、follow-up 或 interrupt。"
                    "不要等待自身或其它任务。继续你的只读研究并返回本任务 output_schema 规定的终态 JSON。"
                ),
            }}
        active = _allowed_dispatch_tasks(
            dispatch_log, parent_session_id=parent_session_id,
        ) - _terminal_research_tasks(
            event_log,
            parent_session_id=parent_session_id,
            environment=environment,
        )
        if active and research_control is not None:
            record = _dispatch_record(payload, decision="DENY_ACTIVE_RESEARCH_CONTROL")
            lock_path = dispatch_log.with_suffix(dispatch_log.suffix + ".lock")
            with lock_path.open("a", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                _append_record(dispatch_log, record)
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            return record, {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "研究任务仍在运行；不得 list、follow-up 或 interrupt。"
                    "请只使用 wait_agent 长等待其真实终态。"
                ),
            }}
        timeout_ms = tool_input.get("timeout_ms")
        if (
            active and research_wait
            and (
                not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool)
                or timeout_ms < 300_000
            )
        ):
            record = _dispatch_record(payload, decision="DENY_SHORT_RESEARCH_WAIT")
            lock_path = dispatch_log.with_suffix(dispatch_log.suffix + ".lock")
            with lock_path.open("a", encoding="utf-8") as lock_handle:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
                _append_record(dispatch_log, record)
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            return record, {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "研究任务仍在运行；请调用 wait_agent 并显式设置 timeout_ms=600000。"
                    "即使 wait 因进度或空状态提前返回，也必须继续等待真实终态。"
                ),
            }}
    agent_type = tool_input.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type:
        # A catch-all matcher is intentional: current Codex versions can expose
        # different aliases for local function tools. Non-Agent calls are
        # observed without retaining their arguments and are always allowed.
        is_spawn = str(payload.get("tool_name", "")).split(".")[-1] in {
            "spawn_agent", "collaborationspawn_agent", "Agent",
        }
        record = _dispatch_record(payload, decision=(
            "DENY_MISSING_AGENT_TYPE" if is_spawn else "IGNORE_NON_AGENT_TOOL"
        ))
        lock_path = dispatch_log.with_suffix(dispatch_log.suffix + ".lock")
        with lock_path.open("a", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            _append_record(dispatch_log, record)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        if is_spawn:
            return record, {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "deny",
                "permissionDecisionReason": "派发缺少 agent_type；不得使用默认 Agent 代替固定 Specialist。",
            }}
        return record, {}
    lock_path = dispatch_log.with_suffix(dispatch_log.suffix + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        research_stage = _research_stage(environment)
        reserved = _reserved_agents(
            dispatch_log,
            parent_session_id=str(payload.get("session_id", "")),
            reserve_task_name=research_stage,
        )
        binding = None
        if agent_type not in expected:
            decision = "DENY_UNAPPROVED_AGENT"
        elif (tool_input.get("task_name") if research_stage else agent_type) in reserved:
            decision = "DENY_DUPLICATE_AGENT"
        elif research_stage:
            event_log = _resolve_scoped_log(environment)
            terminal = _terminal_research_tasks(
                event_log,
                parent_session_id=str(payload.get("session_id", "")),
                environment=environment,
            )
            if len(reserved - terminal) >= _research_target_concurrency(environment):
                decision = "DENY_CONCURRENCY_LIMIT"
            else:
                try:
                    binding = _verify_dispatch_input(tool_input, environment)
                    if binding["matched"] and _multidimensional_stage(environment):
                        task_name = str(tool_input.get("task_name"))
                        task = next(
                            item for item in _research_index(environment)["tasks"]
                            if item["task_name"] == task_name
                        )
                        completed = _completed_research_tasks(
                            event_log,
                            parent_session_id=str(payload.get("session_id", "")),
                            environment=environment,
                        )
                        # 依赖使用稳定 task_id，而完成事件按 task_name 归集。
                        reused = _multidimensional_module().read_retry_dependencies(
                            Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), event_log.parent, task_name,
                        )
                        completed = set(completed) | {item["task_name"] for item in reused}
                        by_id = {
                            item["task_id"]: item["task_name"]
                            for item in _research_index(environment)["tasks"]
                        }
                        if any(by_id[dependency] not in completed for dependency in task.get("depends_on", [])):
                            binding["matched"] = False
                            binding["failure_code"] = "RESEARCH_DEPENDENCY_NOT_READY"
                    decision = "ALLOW" if binding["matched"] else "DENY_DISPATCH_CONTRACT"
                except (OSError, ValueError, KeyError, TypeError, ImportError):
                    decision = "DENY_DISPATCH_CONTRACT"
                    binding = {"contract_version": "specialist-dispatch/1.0.0",
                               "matched": False, "failure_code": "DISPATCH_SOURCE_INVALID"}
        else:
            try:
                binding = _verify_dispatch_input(tool_input, environment)
                decision = "ALLOW" if binding["matched"] else "DENY_DISPATCH_CONTRACT"
            except (OSError, ValueError, KeyError, TypeError, ImportError):
                # Return an explicit deny: hook process errors alone may not block Codex.
                decision = "DENY_DISPATCH_CONTRACT"
                binding = {"contract_version": "specialist-dispatch/1.0.0",
                           "matched": False, "failure_code": "DISPATCH_SOURCE_INVALID"}
        record = _dispatch_record(payload, decision=decision)
        if binding is not None:
            record["dispatch_binding"] = binding
            record.pop("event_hash")
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        _append_record(dispatch_log, record)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    if decision == "ALLOW":
        return record, {}
    reason = (
        f"DISPATCH_CONTRACT_MISMATCH：{agent_type} 的身份、输入或消息不匹配。"
        "请原样使用本次 smoke prompt 的派发消息映射，不得猜测 ID、截断输入或绕过拒绝。"
        if decision == "DENY_DISPATCH_CONTRACT" else
        "并发上限已达到；请等待任一已派发任务结束后再补位。"
        if decision == "DENY_CONCURRENCY_LIMIT" else
        f"拒绝重复派发 Specialist：{agent_type}。每个任务在本轮只能启动一次。"
        if decision == "DENY_DUPLICATE_AGENT"
        else f"拒绝未授权 Agent：{agent_type}。本轮只允许固定的两个 Specialist。"
    )
    return record, {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def minimize_hook_event(
    payload: Mapping[str, Any], *, blocked_stop: bool = False
) -> dict[str, Any]:
    event_name = payload.get("hook_event_name")
    if event_name not in SUPPORTED_EVENTS:
        raise ValueError("HOOK_EVENT_UNSUPPORTED")
    required = ("session_id", "turn_id", "agent_id", "agent_type", "model", "cwd")
    if any(not isinstance(payload.get(field), str) or not payload[field] for field in required):
        raise ValueError("HOOK_EVENT_IDENTITY_INCOMPLETE")

    record: dict[str, Any] = {
        "schema_version": "codex-subagent-hook-event/1.0.0",
        "recorder_version": RECORDER_VERSION,
        "hook_event_name": "SubagentStopBlocked" if blocked_stop else event_name,
        "parent_session_id": payload["session_id"],
        "turn_id": payload["turn_id"],
        "child_session_id": payload["agent_id"],
        "agent_type": payload["agent_type"],
        "model": payload["model"],
        "cwd": payload["cwd"],
        "permission_mode": payload.get("permission_mode"),
        "observed_at": _utc_now(),
        "raw_prompt_or_reasoning_retained": False,
    }
    if event_name == "SubagentStop":
        message = payload.get("last_assistant_message")
        record["assistant_message_present"] = isinstance(message, str) and bool(message)
        record["assistant_message_sha256"] = (
            _canonical_hash({"assistant_message": message})
            if isinstance(message, str)
            else None
        )
        structured: Mapping[str, Any] | None = None
        if isinstance(message, str):
            try:
                candidate = json.loads(message)
            except json.JSONDecodeError:
                candidate = None
            if isinstance(candidate, Mapping):
                structured = candidate
        record["structured_output_present"] = structured is not None
        record["final_structured_output_hash"] = (
            _canonical_hash(structured) if structured is not None else None
        )
        record["output_binding"] = (
            {
                "run_id": structured.get("run_id"),
                "invocation_id": structured.get("invocation_id"),
                "agent": structured.get("agent"),
            }
            if structured is not None
            else None
        )
        transcript = payload.get("agent_transcript_path")
        record["agent_transcript_present"] = isinstance(transcript, str) and bool(transcript)
        record["agent_transcript_path_sha256"] = (
            _canonical_hash({"path": transcript})
            if isinstance(transcript, str) and transcript
            else None
        )
        record["stop_hook_active"] = payload.get("stop_hook_active") is True
        if blocked_stop:
            record["hook_decision"] = "BLOCK"
    record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
    return record


def _bind_research_stop_identity(
    payload: Mapping[str, Any], record: dict[str, Any], *,
    log_path: Path, environment: Mapping[str, str],
) -> None:
    """Bind a final research Stop to its trusted Start without changing prose."""

    if payload.get("hook_event_name") != "SubagentStop" or not _research_stage(environment):
        return
    parent_session_id = str(payload.get("session_id", ""))
    child_session_id = str(payload.get("agent_id", ""))
    starts = []
    for item in _read_jsonl_records_unlocked(log_path):
        context = item.get("context_binding")
        if (
            item.get("hook_event_name") == "SubagentStart"
            and item.get("parent_session_id") == parent_session_id
            and item.get("child_session_id") == child_session_id
            and item.get("agent_type") == payload.get("agent_type")
            and item.get("model") == payload.get("model")
            and isinstance(context, Mapping)
            and context.get("status") == "DELIVERED"
        ):
            starts.append(context)
    if len(starts) != 1:
        record["identity_binding"] = {
            "status": "FAILED", "failure_code": "RESEARCH_STOP_START_BINDING_AMBIGUOUS",
        }
        return
    context = starts[0]
    index = _research_index(environment)
    matches = [
        item for item in index["tasks"]
        if item.get("task_name") == context.get("task_name")
        and item.get("invocation_id") == context.get("invocation_id")
        and (
            item.get("agent")
            or ("runtime_company_analyst" if _common_stock_stage(environment) else None)
        ) == payload.get("agent_type")
    ]
    dispatch_log = _resolve_scoped_log(
        environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG"
    )
    allowed = [
        item for item in _read_jsonl_records_unlocked(dispatch_log)
        if item.get("decision") == "ALLOW"
        and item.get("parent_session_id") == parent_session_id
        and item.get("task_name") == context.get("task_name")
        and item.get("agent_type") == payload.get("agent_type")
    ]
    if len(matches) != 1 or len(allowed) != 1 or context.get("run_id") != index.get("run_id"):
        record["identity_binding"] = {
            "status": "FAILED", "failure_code": "RESEARCH_STOP_TRUSTED_BINDING_INVALID",
        }
        return
    task = matches[0]
    task_agent = task.get("agent") or "runtime_company_analyst"
    trusted = {
        "run_id": index["run_id"], "invocation_id": task["invocation_id"],
        "agent": task_agent, "task_name": task["task_name"],
        "task_id": task.get("task_id", task["task_name"]),
    }
    record["trusted_task_binding"] = trusted
    authored = record.get("output_binding")
    conflicts = []
    if isinstance(authored, Mapping):
        for key in ("run_id", "invocation_id", "agent"):
            if authored.get(key) is not None and authored.get(key) != trusted[key]:
                conflicts.append(key)
    if conflicts:
        record["identity_binding"] = {
            "status": "CONFLICT", "failure_code": "RESEARCH_OUTPUT_IDENTITY_CONFLICT",
            "conflicting_fields": sorted(conflicts), "source": "TRUSTED_DISPATCH_AND_START",
        }
        return
    missing = [
        key for key in ("run_id", "invocation_id", "agent")
        if not isinstance(authored, Mapping) or authored.get(key) is None
    ]
    record["output_binding"] = {
        key: trusted[key] for key in ("run_id", "invocation_id", "agent")
    }
    record["identity_binding"] = {
        "status": "BOUND", "source": "TRUSTED_DISPATCH_AND_START",
        "filled_fields": missing,
    }


def _trusted_bound_output(
    payload: Mapping[str, Any], record: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the raw object with only trusted technical identity enveloped."""

    identity = record.get("identity_binding")
    if not isinstance(identity, Mapping) or identity.get("status") != "BOUND":
        code = (
            identity.get("failure_code")
            if isinstance(identity, Mapping) else "RESEARCH_OUTPUT_TRUSTED_BINDING_MISSING"
        )
        raise ValueError(str(code))
    try:
        value = json.loads(payload["last_assistant_message"])
    except json.JSONDecodeError as exc:
        raise ValueError("RESEARCH_OUTPUT_JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise ValueError("RESEARCH_OUTPUT_NOT_OBJECT")
    binding = record.get("output_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("RESEARCH_OUTPUT_TRUSTED_BINDING_MISSING")
    result = dict(value)
    for key in ("run_id", "invocation_id", "agent"):
        result[key] = binding[key]
    return result




def _expected_parallel_agents(environment: Mapping[str, str]) -> set[str]:
    return {
        item.strip()
        for item in environment.get("STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS", "").split(",")
        if item.strip()
    }


def _expected_research_tasks(environment: Mapping[str, str]) -> set[str]:
    if not _research_stage(environment):
        return set()
    selected_tasks = _selected_research_tasks(environment)
    if selected_tasks is not None:
        return selected_tasks
    return {item["task_name"] for item in _research_index(environment)["tasks"]}


def _allowed_dispatch_tasks(log_path: Path, *, parent_session_id: str) -> set[str]:
    if not log_path.is_file():
        return set()
    result = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            item.get("decision") == "ALLOW"
            and item.get("parent_session_id") == parent_session_id
            and isinstance(item.get("task_name"), str)
        ):
            result.add(item["task_name"])
    return result


def _read_jsonl_records_unlocked(log_path: Path) -> list[dict[str, Any]]:
    """Read records when the caller already holds the append lock."""

    lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.is_file() else []
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _read_jsonl_records(log_path: Path) -> list[dict[str, Any]]:
    """Read one append-only Hook log while excluding a concurrent writer."""

    lock_path = log_path.with_suffix(log_path.suffix + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        records = _read_jsonl_records_unlocked(log_path)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    return records


def _handle_parent_stop(
    payload: Mapping[str, Any], *, environment: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Block common-stock parent completion until every frozen task is terminal.

    A terminal task needs an allowed dispatch, a delivered start context and a
    SubagentStop from the same child whose structured output names the frozen
    invocation. Report validity remains the existing finalizer's concern.
    """

    required = ("session_id", "turn_id", "cwd")
    if any(not isinstance(payload.get(field), str) or not payload[field] for field in required):
        raise ValueError("PARENT_STOP_IDENTITY_INCOMPLETE")
    if not _common_stock_stage(environment):
        raise ValueError("PARENT_STOP_STAGE_INVALID")

    parent_session_id = str(payload["session_id"])
    index = _research_index(environment)
    tasks = {
        item["task_name"]: item
        for item in index["tasks"]
        if isinstance(item.get("task_name"), str)
        and isinstance(item.get("invocation_id"), str)
    }
    if len(tasks) != len(index["tasks"]):
        raise ValueError("PARENT_STOP_TASK_INDEX_INVALID")

    dispatch_log = _resolve_scoped_log(
        environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG"
    )
    event_log = _resolve_scoped_log(environment)
    allowed = {
        item["task_name"]
        for item in _read_jsonl_records(dispatch_log)
        if item.get("decision") == "ALLOW"
        and item.get("parent_session_id") == parent_session_id
        and item.get("task_name") in tasks
    }
    completed = allowed & _terminal_research_tasks(
        event_log, parent_session_id=parent_session_id, environment=environment,
    )

    expected = set(tasks)
    missing = expected - completed
    decision = "BLOCK" if missing else "ALLOW"
    record: dict[str, Any] = {
        "schema_version": "common-stock-parent-stop/1.0.0",
        "recorder_version": RECORDER_VERSION,
        "hook_event_name": "Stop",
        "run_id": index["run_id"],
        "parent_session_id": parent_session_id,
        "turn_id": payload["turn_id"],
        "observed_at": _utc_now(),
        "expected_task_names": sorted(expected),
        "completed_task_names": sorted(completed),
        "missing_task_names": sorted(missing),
        "decision": decision,
        "raw_prompt_or_reasoning_retained": False,
    }
    record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
    audit_log = _resolve_scoped_log(
        environment, environment_key="STOCK_AGENT_PARENT_STOP_LOG"
    )
    audit_lock = audit_log.with_suffix(audit_log.suffix + ".lock")
    with audit_lock.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        _append_record(audit_log, record)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    if missing:
        return record, {
            "decision": "block",
            "reason": (
                "普通股研究仍缺少可验证终态，请继续等待这些任务："
                + ",".join(sorted(missing))
                + "。wait 可能因非终态活动返回，不能据此结束。"
            ),
        }
    return record, {}


def _terminal_research_tasks(
    log_path: Path, *, parent_session_id: str, environment: Mapping[str, str]
) -> set[str]:
    """将最终 Stop 按可信 Start/派发身份绑定回已结束任务。"""

    if not log_path.is_file():
        return set()
    tasks = {item["task_name"]: item for item in _research_index(environment)["tasks"]}
    by_invocation = {item["invocation_id"]: item["task_name"] for item in tasks.values()}
    records = _read_jsonl_records(log_path)
    starts: dict[str, str] = {}
    for item in records:
        context = item.get("context_binding")
        if (
            item.get("hook_event_name") == "SubagentStart"
            and item.get("parent_session_id") == parent_session_id
            and isinstance(item.get("child_session_id"), str)
            and isinstance(context, Mapping)
            and context.get("status") == "DELIVERED"
            and context.get("task_name") in tasks
            and context.get("invocation_id") == tasks[context["task_name"]]["invocation_id"]
            and item.get("agent_type") == (
                tasks[context["task_name"]].get("agent")
                or ("runtime_company_analyst" if _common_stock_stage(environment) else None)
            )
        ):
            starts[item["child_session_id"]] = context["task_name"]
    result: set[str] = set()
    for item in records:
        binding = item.get("output_binding") or {}
        trusted = item.get("trusted_task_binding") or {}
        invocation_id = binding.get("invocation_id") if isinstance(binding, Mapping) else None
        if (
            item.get("hook_event_name") == "SubagentStop"
            and item.get("parent_session_id") == parent_session_id
        ):
            task_name = (
                trusted.get("task_name") if isinstance(trusted, Mapping) else None
            ) or starts.get(item.get("child_session_id"))
            if task_name in tasks:
                result.add(task_name)
            elif invocation_id in by_invocation:
                # Backward-compatible read path for historical/synthetic logs.
                result.add(by_invocation[invocation_id])
    return result


def _completed_research_tasks(
    log_path: Path, *, parent_session_id: str, environment: Mapping[str, str]
) -> set[str]:
    """只把已保存合法报告的子任务视为依赖成功。"""

    if not log_path.is_file():
        return set()
    by_id = {
        item["task_id"]: item["task_name"]
        for item in _research_index(environment)["tasks"]
    }
    result: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        capture = item.get("output_capture") or {}
        task_id = capture.get("task_id") if isinstance(capture, Mapping) else None
        if (
            item.get("hook_event_name") == "SubagentStop"
            and item.get("parent_session_id") == parent_session_id
            and capture.get("status") == "SAVED"
            and task_id in by_id
        ):
            result.add(by_id[task_id])
    return result


def _research_target_concurrency(environment: Mapping[str, str]) -> int:
    if _selected_research_tasks(environment) is not None:
        return 1
    value = _research_index(environment).get("target_concurrency")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("COMMON_STOCK_CONCURRENCY_INVALID")
    return value


def _next_research_task(
    event_log: Path, *, parent_session_id: str, environment: Mapping[str, str],
    agent_type: str | None = None,
) -> str:
    dispatch_log = _resolve_scoped_log(
        environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG"
    )
    ordered: list[str] = []
    if dispatch_log.is_file():
        for line in dispatch_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                item.get("decision") == "ALLOW"
                and item.get("parent_session_id") == parent_session_id
                and isinstance(item.get("task_name"), str)
            ):
                ordered.append(item["task_name"])
    bound = set()
    if event_log.is_file():
        for line in event_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            context = item.get("context_binding") or {}
            if (
                item.get("hook_event_name") == "SubagentStart"
                and item.get("parent_session_id") == parent_session_id
                and isinstance(context, Mapping)
                and isinstance(context.get("task_name"), str)
            ):
                bound.add(context["task_name"])
    tasks_by_name = {
        item["task_name"]: item for item in _research_index(environment)["tasks"]
    }
    for task_name in ordered:
        task = tasks_by_name.get(task_name, {})
        task_agent = task.get("agent")
        if (
            task_name not in bound
            and (agent_type is None or task_agent is None or task_agent == agent_type)
        ):
            return task_name
    raise ValueError("COMMON_STOCK_START_WITHOUT_DISPATCH")


def _started_agents(log_path: Path, *, parent_session_id: str) -> set[str]:
    if not log_path.is_file():
        return set()
    starts: set[str] = set()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(event, Mapping)
            and event.get("hook_event_name") == "SubagentStart"
            and event.get("parent_session_id") == parent_session_id
            and isinstance(event.get("agent_type"), str)
        ):
            starts.add(str(event["agent_type"]))
    return starts


def _capture_specialist_report(payload, record, environment):
    """Save the exact final JSON object; never repair references or overwrite it."""
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    delivery = manifest.get("specialist_output_delivery")
    if manifest.get("source_mode") != "live" or delivery not in {"native-final-json/1.0.0", "native-research-draft/1.0.0"}:
        raise ValueError("SPECIALIST_CAPTURE_CONTRACT_INVALID")
    agent = payload["agent_type"]
    if agent not in {"runtime_company_analyst", "runtime_skeptic"}:
        raise ValueError("SPECIALIST_CAPTURE_AGENT_INVALID")
    invocation = json.loads((run_dir / "invocations" / f"{agent}.json").read_text())
    value = json.loads(payload["last_assistant_message"])
    if (not isinstance(value, dict) or value.get("agent") != agent
            or invocation.get("agent", {}).get("name") != agent
            or any(value.get(k) != invocation.get(k) for k in ("run_id", "invocation_id"))):
        raise ValueError("SPECIALIST_CAPTURE_BINDING_INVALID")
    if payload["model"] != invocation["model"]:
        raise ValueError("SPECIALIST_CAPTURE_MODEL_INVALID")
    raw_value = value
    if delivery == "native-research-draft/1.0.0":
        value = _invocation_module().envelope_specialist_draft(raw_value, invocation, model=payload["model"])
    directory = run_dir / "agents"
    if directory.is_symlink() or not directory.resolve().is_relative_to(run_dir):
        raise ValueError("SPECIALIST_CAPTURE_PATH_INVALID")
    directory.mkdir(exist_ok=True, mode=0o700)
    outputs = [(directory / f"{agent}.json", value)]
    if delivery == "native-research-draft/1.0.0":
        outputs.insert(0, (directory / f"{agent}.native.json", raw_value))
    for path, content in outputs:
        if path.is_symlink():
            raise ValueError("SPECIALIST_CAPTURE_PATH_INVALID")
        if path.exists() and json.loads(path.read_text()) != content:
            raise ValueError("SPECIALIST_CAPTURE_OUTPUT_EXISTS")
    for path, content in outputs:
        if not path.exists():
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(content, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
    record["output_capture"] = {"version": delivery, "path": f"agents/{agent}.json",
                                "output_hash": _canonical_hash(value), "status": "SAVED"}
    if delivery == "native-research-draft/1.0.0":
        record["output_capture"].update(raw_path=f"agents/{agent}.native.json", raw_output_hash=_canonical_hash(raw_value))


def _capture_common_stock_report(payload, record, environment):
    """按 invocation 绑定保存普通股研究草案；非法引用不做静默修复。"""
    stage = _common_stock_module()
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    value = _trusted_bound_output(payload, record)
    if value.get("agent") != "runtime_company_analyst":
        raise ValueError("COMMON_STOCK_OUTPUT_BINDING_INVALID")
    index = _research_index(environment)
    matches = [item for item in index["tasks"] if item["invocation_id"] == value["invocation_id"]]
    if len(matches) != 1 or value["run_id"] != index["run_id"]:
        raise ValueError("COMMON_STOCK_OUTPUT_INVOCATION_UNKNOWN")
    task = matches[0]
    request = json.loads((run_dir / task["request_path"]).read_text(encoding="utf-8"))
    invocation = json.loads((run_dir / task["invocation_path"]).read_text(encoding="utf-8"))
    if payload["model"] != invocation["model"] or task["security_id"] != request["security"]["security_id"]:
        raise ValueError("COMMON_STOCK_OUTPUT_MODEL_OR_SECURITY_INVALID")
    calculation_ids = stage._calculation_ids_for_invocation(
        run_dir, value["invocation_id"]
    )
    draft = {key: item for key, item in value.items() if key not in {"run_id", "invocation_id", "agent"}}
    report = __import__(
        "product.council.common_stock_research", fromlist=["envelope_equity_research_draft"]
    ).envelope_equity_research_draft(
        draft,
        request=request,
        skill_execution=invocation["skill_execution"],
        report_id="equity-report:" + value["invocation_id"],
        calculation_artifact_ids=calculation_ids,
    )
    if task.get("equity_research_package_path"):
        stage.validate_delivered_research_references(
            report, run_dir=run_dir, invocation_id=value["invocation_id"],
        )
    gate = json.loads((run_dir / "evidence/gate.json").read_text(encoding="utf-8"))
    evidence = [item for item in gate["allowed_evidence"] if item["evidence_id"] in set(request["allowed_evidence_ids"])]
    output = __import__(
        "product.council.research_output", fromlist=["persist_equity_research_report"]
    ).persist_equity_research_report(
        run_dir / "research/reports", report=report, request=request, evidence=evidence,
        calculation_artifact_ids=calculation_ids,
    )
    record["output_capture"] = {
        "version": "native-equity-research-draft/1.0.0", "status": "SAVED",
        "path": str(Path(output["json"]).relative_to(run_dir)),
        "markdown_path": str(Path(output["markdown"]).relative_to(run_dir)),
        "output_hash": output["json_hash"], "security_id": task["security_id"],
    }


def _validate_multidimensional_tool_calculations(value, *, task, invocation, run_dir):
    """Match report calculations to this invocation's actual successful MCP results."""
    from product.runtime.calculation_handoff import VERSION, load_tool_receipts, receipt_calculation
    ledger_ref = task.get("calculation_ledger_ref")
    if ledger_ref is None:
        return
    calculations = value.get("calculations", [])
    if not isinstance(calculations, list) or any(not isinstance(item, dict) for item in calculations):
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_DRAFT_INVALID")
    receipts = load_tool_receipts(Path(run_dir), task, invocation, selected_ids={
        item.get("calculation_id") for item in calculations if item.get("artifact_ref") == ledger_ref
    })
    for calculation in calculations:
        if calculation.get("artifact_ref") != ledger_ref:
            continue
        receipt = receipts.get(calculation.get("calculation_id"))
        if receipt is None:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_RECORD_UNKNOWN")
        if calculation.get("input_evidence_refs") != receipt.get("evidence_ids"):
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_INPUT_MISMATCH")
        # Historical compound projections retain their original readable format;
        # scalar results always match the actual value/method/unit, not just IDs.
        if (task.get("calculation_selection_version") == VERSION
                and receipt["operation"] in {"ratio", "percent_change"}):
            expected = receipt_calculation(receipt, ledger_ref)
            if any(calculation.get(key) != expected[key] for key in ("method", "value", "unit")):
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_RESULT_MISMATCH")


def _validate_multidimensional_calculation_structure(value, *, packet):
    """Check calculation shape before consulting its tool receipts or lineage."""

    from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance

    output_schema = packet.get("output_schema")
    if (
        not isinstance(output_schema, Mapping)
        or packet.get("output_schema_hash") != _canonical_hash(output_schema)
    ):
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_SCHEMA_INVALID")
    definitions = output_schema.get("$defs")
    calculation_schema = definitions.get("calculation") if isinstance(definitions, Mapping) else None
    if not isinstance(calculation_schema, Mapping):
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_SCHEMA_INVALID")
    calculations = value.get("calculations")
    if not isinstance(calculations, list):
        raise ValueError("DIMENSION_REPORT_SCHEMA_INVALID:SCHEMA_TYPE_INVALID:$.calculations")
    schema = {"$defs": definitions, **calculation_schema}
    for index, calculation in enumerate(calculations):
        try:
            validate_schema_instance(calculation, schema, path=f"$.calculations[{index}]")
        except SchemaValidationError as exc:
            raise ValueError(f"DIMENSION_REPORT_SCHEMA_INVALID:{exc}") from exc


def _industry_source_identity_copy_paths(task: Mapping[str, Any], draft: Mapping[str, Any]) -> list[str]:
    if task.get("industry_source_boundary") != "industry-source-boundary/1.0.0":
        return []
    claims = draft.get("claims")
    if not isinstance(claims, list):
        return []
    return [
        f"claims[{index}].statement"
        for index, claim in enumerate(claims)
        if isinstance(claim, Mapping) and isinstance(claim.get("statement"), str)
        and re.search(r"\b(?:source_id|as_of|retrieved_at)\s*=", claim["statement"])
    ]


_SOURCE_LITERAL_VERSION = "source-literal-selection/1.0.0"
_MACRO_SOURCE_LITERAL_VERSION = "source-literal-selection/1.1.0"
_SOURCE_LITERAL_PLACEHOLDER = re.compile(r"\{\{sf\.[A-Za-z][A-Za-z0-9_]{0,23}\}\}")


def _macro_observation_literal(fact: Mapping[str, Any]) -> str:
    """呈现显式选中记录的原角色和时间；不换算、补缺或选择观察期。"""
    raw = fact.get("value")
    if (not isinstance(raw, Mapping) or fact.get("dataset") != "macro_history"
            or fact.get("source_family") != "moomoo_sg"
            or fact.get("source_type") != "SECONDARY_VENDOR"
            or fact.get("security_id") != "US:MARKET"
            or type(raw.get("indicator_id")) is not int
            or fact.get("source_id") != f"moomoo-sg-opend-macro:{raw['indicator_id']}"
            or raw.get("vintage_status") != "CURRENT_VENDOR_SNAPSHOT"):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    values = {}
    for key in ("actual", "previous", "consensus"):
        if key not in raw:
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        value = raw[key]
        if value is None:
            values[key] = "null（原缺失）"
        elif value == "N/A":
            values[key] = "N/A"
        else:
            if type(value) not in {str, int, float} or len(str(value)) > 128:
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            try:
                if not Decimal(str(value)).is_finite():
                    raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            except InvalidOperation:
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID") from None
            values[key] = str(value)
    for key in ("label", "unit_type", "raw_release_time"):
        if (not isinstance(raw.get(key), str) or not raw[key].strip()
                or len(raw[key]) > 128 or any(ord(c) < 32 for c in raw[key])
                or "{{sf." in raw[key]):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    try:
        # 只验证供应商标签的日期形状；没有时区证明，不据此创造UTC时点。
        datetime.fromisoformat(raw["raw_release_time"])
    except ValueError:
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID") from None
    return (
        f"【{raw['label']}；观察期(as_of)={fact['as_of']}；"
        f"actual(原值)={values['actual']}；previous(原值)={values['previous']}；"
        f"consensus(原值)={values['consensus']}；unit_type(原标签)={raw['unit_type']}；"
        f"raw_release_time(供应商原标签，时区未核实)={raw['raw_release_time']}；"
        "vintage_status=CURRENT_VENDOR_SNAPSHOT，历史vintage未核实】"
    )


def _source_literal_marker_findings(draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Locate marker transport errors only; do not validate or choose sources."""
    from product.runtime.local_revision import pointer
    findings = []
    # Binding is only legal in claims[i].statement, never in summary/gaps/etc.
    # Report locations, not author text or sources; leave correction to the author.
    pending = [(draft, [])]
    while pending and len(findings) < 16:
        value, path = pending.pop()
        if path and path[0] == "source_literal_selections":
            continue  # Declared placeholders are not prose binding locations.
        if len(path) == 3 and path[0] == "claims" and isinstance(path[1], int) and path[2] == "statement":
            continue
        if isinstance(value, str) and "{{sf." in value:
            findings.append({"code": "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID",
                             "path": pointer(path), "reason": "MARKER_OUTSIDE_STATEMENT",
                             "observed_count": value.count("{{sf.")})
        elif isinstance(value, Mapping):
            pending.extend((v, [*path, k]) for k, v in reversed(list(value.items())))
        elif isinstance(value, list):
            pending.extend((v, [*path, i]) for i, v in reversed(list(enumerate(value))))
    selections, claims = draft.get("source_literal_selections"), draft.get("claims")
    if not isinstance(selections, list) or len(selections) > 16 or not isinstance(claims, list):
        return findings
    by_id = {c.get("claim_id"): (i, c) for i, c in enumerate(claims)
             if isinstance(c, Mapping) and isinstance(c.get("claim_id"), str)}
    if len(by_id) != len(claims):
        return findings  # Ambiguous targets remain the original validator's responsibility.
    for index, selection in enumerate(selections):
        if not isinstance(selection, Mapping):
            continue
        marker, claim_id = selection.get("placeholder"), selection.get("claim_id")
        if not isinstance(marker, str) or not _SOURCE_LITERAL_PLACEHOLDER.fullmatch(marker):
            continue
        if not isinstance(claim_id, str) or claim_id not in by_id:
            findings.append({"code": "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID",
                             "path": f"source_literal_selections[{index}]",
                             "reason": "TARGET_CLAIM_MISSING"})
            continue
        claim_index, claim = by_id[claim_id]
        if not isinstance(claim.get("statement"), str):
            continue
        count = claim["statement"].count(marker)
        if count != 1:
            findings.append({"code": "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID",
                             "path": f"source_literal_selections[{index}]",
                             "related_claim_path": f"claims[{claim_index}].statement",
                             "placeholder": marker, "observed_count": count,
                             "expected_count": 1, "reason": "TARGET_MARKER_COUNT_INVALID"})
    return findings


def _bind_source_literal_selections(
    draft: Mapping[str, Any], *, task: Mapping[str, Any], run_dir: Path,
    reference_map: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Fill only explicitly selected source scalars in task-local draft statements."""

    result = dict(draft)
    had_selections = "source_literal_selections" in result
    selections = result.pop("source_literal_selections", None)
    version = task.get("source_literal_selection")
    if version not in {_SOURCE_LITERAL_VERSION, _MACRO_SOURCE_LITERAL_VERSION}:
        if had_selections or "{{sf." in json.dumps(result, ensure_ascii=False):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        return result
    macro = version == _MACRO_SOURCE_LITERAL_VERSION
    if ((macro and (task.get("capability") != "MACRO_CONTEXT"
                    or task.get("tool_identity_version") != "research-tool-identity/1.0.0"))
            or (not macro and task.get("capability") not in {"FUNDAMENTAL_EVENT", "OPTIONS_FLOW"})):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    if selections is None:
        selections = []
    if not isinstance(selections, list) or len(selections) > 16:
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    claims = result.get("claims")
    if not isinstance(claims, list):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    claims = [dict(claim) if isinstance(claim, dict) else claim for claim in claims]
    result["claims"] = claims
    by_id = {c.get("claim_id"): c for c in claims if isinstance(c, dict) and isinstance(c.get("claim_id"), str)}
    if len(by_id) != len(claims):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    if not selections:
        if "{{sf." in json.dumps(result, ensure_ascii=False):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        return result
    gate = json.loads((run_dir / "evidence/gate.json").read_text(encoding="utf-8"))
    if gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash"):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    allowed = set(task.get("allowed_evidence_ids", []))
    facts = {f["evidence_id"]: f for f in gate.get("allowed_evidence", [])
             if isinstance(f, dict) and f.get("evidence_id") in allowed}
    queried: set[str] = set()
    events_path = run_dir / "events/mcp/events.jsonl"
    if not events_path.is_file() or events_path.is_symlink():
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if (event.get("event_type") == "mcp_tool_result"
                and event.get("tool") in {"fixture_evidence.query", "live_evidence.query"}
                and event.get("access_mode") == "read"
                and all(event.get(k) == task.get(k) for k in ("run_id", "invocation_id", "agent"))
                and event.get("event_hash") == legacy_envelope_hash(event, hash_field="event_hash")):
            queried.update(x for x in event.get("evidence_ids", []) if isinstance(x, str))
    aliases = (reference_map or {}).get("evidence", {})
    seen: set[str] = set()
    replacements: dict[str, tuple[str, str]] = {}
    for selection in selections:
        if (not isinstance(selection, dict)
                or set(selection) != {"claim_id", "placeholder", "evidence_ref", "field"}):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        claim_id, marker, ref, field = (selection[k] for k in ("claim_id", "placeholder", "evidence_ref", "field"))
        claim = by_id.get(claim_id)
        if (not isinstance(marker, str) or not _SOURCE_LITERAL_PLACEHOLDER.fullmatch(marker)
                or marker in seen or not isinstance(ref, str) or not isinstance(field, str)
                or not isinstance(claim, dict) or not isinstance(claim.get("statement"), str)):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        seen.add(marker)
        evidence_id = aliases.get(ref, ref)
        cited = claim.get("evidence_refs", [])
        if (evidence_id not in facts or evidence_id not in queried
                or not isinstance(cited, list)
                or evidence_id not in {aliases.get(item, item) for item in cited if isinstance(item, str)}
                or (not macro and facts[evidence_id].get("security_id") not in task.get("security_ids", []))):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        fact = facts[evidence_id]
        if macro:
            if field != "moomoo_macro_observation":
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            literal = _macro_observation_literal(fact)
        elif task["capability"] == "FUNDAMENTAL_EVENT":
            raw = fact.get("value")
            if (field != "sec_usd_value" or fact.get("source_type") != "sec"
                    or fact.get("unit") != "USD" or not isinstance(raw, str)
                    or len(raw) > 128 or re.fullmatch(r"-?\d+", raw) is None):
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            literal = raw + " USD"
        else:
            if (field not in {"as_of", "retrieved_at"}
                    or fact.get("dataset") != "options_snapshot"
                    or not str(fact.get("semantic_field", "")).startswith((
                        "moomoo_option_quote:", "option_chain_contract:",
                    ))):
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            raw = fact.get(field)
            if not isinstance(raw, str) or len(raw) > 64 or not raw.endswith("Z"):
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            literal = field + "=" + raw
        try:
            if not str(fact["as_of"]).endswith("Z") or not str(gate["decision_cutoff"]).endswith("Z"):
                raise ValueError
            as_of = datetime.fromisoformat(str(fact["as_of"]).replace("Z", "+00:00"))
            cutoff = datetime.fromisoformat(str(gate["decision_cutoff"]).replace("Z", "+00:00"))
            if as_of > cutoff or (field in {"as_of", "retrieved_at"} and datetime.fromisoformat(raw.replace("Z", "+00:00")).tzinfo is None):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID") from None
        if claim["statement"].count(marker) != 1:
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        if field == "sec_usd_value" and re.match(
            r"\s*USD\b", claim["statement"].split(marker, 1)[1], flags=re.IGNORECASE,
        ):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        replacements[marker] = (claim_id, literal)
    # No placeholder may occur in metadata, another claim, or an undeclared location.
    for claim in claims:
        statement = claim["statement"]
        if "{{sf." in json.dumps({k: v for k, v in claim.items() if k != "statement"}, ensure_ascii=False):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        markers = _SOURCE_LITERAL_PLACEHOLDER.findall(statement)
        if "{{sf." in statement and statement.count("{{sf.") != len(markers):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        for marker in markers:
            if replacements.get(marker, (None,))[0] != claim["claim_id"]:
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        for marker in markers:
            statement = statement.replace(marker, replacements[marker][1], 1)
        claim["statement"] = statement
    other = {k: v for k, v in result.items() if k != "claims"}
    if "{{sf." in json.dumps(other, ensure_ascii=False):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    return result


def _capture_multidimensional_report(payload, record, environment):
    """保存多维研究草案并添加冻结绑定；不修复主张、引用或状态。"""

    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    value = _trusted_bound_output(payload, record)
    if value.get("agent") != payload.get("agent_type"):
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_BINDING_INVALID")
    index = _research_index(environment)
    matches = [item for item in index["tasks"] if item["invocation_id"] == value["invocation_id"]]
    if len(matches) != 1 or value["run_id"] != index["run_id"]:
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_INVOCATION_UNKNOWN")
    task = matches[0]
    invocation = json.loads((run_dir / task["invocation_path"]).read_text(encoding="utf-8"))
    if payload.get("model") != invocation.get("model") or payload.get("agent_type") != task["agent"]:
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_AGENT_OR_MODEL_INVALID")
    from product.runtime.multidimensional_references import load_reference_packet
    reference_packet = load_reference_packet(run_dir, value["invocation_id"])
    from product.runtime.calculation_handoff import require_current_selection_transport
    require_current_selection_transport(reference_packet, invocation, indexed_task=task)
    report, evidence, selected_upstream = _read_multidimensional_report_artifact(
        value, record, task=task, invocation=invocation, reference_packet=reference_packet,
        run_dir=run_dir,
    )
    output_dir = run_dir / "research/reports" / _canonical_hash({"task_id": task["task_id"]})[:16]
    from product.runtime.research_submission import mark_accepted
    output = __import__(
        "product.council.multidimensional_output", fromlist=["persist_dimension_report"]
    ).persist_dimension_report(
        output_dir, report=report, evidence=evidence,
        selected_upstream_calculations=selected_upstream,
    )
    accepted = mark_accepted(run_dir, record, report)
    reference_map = reference_packet.get("reference_map")
    record["output_capture"] = {
        "version": "native-research-dimension-draft/1.0.0", "status": "SAVED",
        "path": str(Path(output["json"]).relative_to(run_dir)),
        "markdown_path": str(Path(output["markdown"]).relative_to(run_dir)),
        "output_hash": output["json_hash"], "task_id": task["task_id"],
        "security_ids": task["security_ids"],
        **({"submission_selection_record": accepted} if accepted is not None else {}),
        **({"reference_map_hash": reference_map["map_hash"]} if reference_map is not None else {}),
    }


def _read_multidimensional_report_artifact(value, record, *, task, invocation, reference_packet, run_dir):
    """从明确版本的草稿/回执读取正式对象；无目录创建、发布或执行准入。

    当前 writer 在调用前检查可信 Stop 身份及当前协议。历史读取只据冻结
    来源和版本检查同一业务约束，不生成执行事件或重写历史报告。
    """
    from product.runtime.multidimensional_references import translate_references
    from product.runtime.calculation_handoff import validate_semantic_selection_draft
    stage = _multidimensional_module()
    if task.get("source_literal_selection"):
        frozen_task = json.loads((run_dir / task["task_path"]).read_text(encoding="utf-8"))
        if (reference_packet.get("task") != frozen_task
                or {k: v for k, v in task.items() if k not in {
                    "task_path", "invocation_path", "packet_path", "packet_hash",
                }} != frozen_task
                or frozen_task.get("task_hash") != legacy_envelope_hash(frozen_task, hash_field="task_hash")):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    reference_map = reference_packet.get("reference_map")
    # 身份已由可信 Start/任务绑定校验；只剥离程序装配的身份后检查原稿。
    # MCP resolve 已按冻结提交版本核验原稿/事件并完成选择装配；它的返回值
    # 是正式字段，不是第二份模型草稿。非 MCP 原稿则必须完整检查选择结构。
    from product.runtime.research_submission import ASSEMBLY_VERSIONS
    assembled_submission = record.get("submission_binding", {}).get("version")
    if assembled_submission not in ASSEMBLY_VERSIONS:
        validate_semantic_selection_draft(
            {key: item for key, item in value.items() if key not in {"run_id", "invocation_id", "agent"}},
            reference_packet,
        )
    elif assembled_submission != task.get("submission_version"):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    if "document_selections" in value:
        from product.runtime.research_submission import _selected_documents
        documents = _selected_documents(value, reference_packet, value["document_selections"])
        value = {key: item for key, item in value.items() if key != "document_selections"}
        value["documents"] = documents
    from product.runtime.calculation_handoff import assemble_calculation_selections
    value = assemble_calculation_selections(run_dir, reference_packet, value)
    value = _bind_source_literal_selections(
        value, task=task, run_dir=run_dir, reference_map=reference_map,
    )
    if reference_map is not None:
        value = translate_references(value, reference_map, local_claims={
            c["claim_id"] for c in value.get("claims", [])
            if isinstance(c, Mapping) and isinstance(c.get("claim_id"), str)
        })
    _validate_multidimensional_calculation_structure(value, packet=reference_packet)
    if _industry_source_identity_copy_paths(task, value):
        raise ValueError("DIMENSION_REPORT_SOURCE_IDENTITY_IN_PROSE")
    artifact_refs = value.get("artifact_refs")
    if (
        not isinstance(artifact_refs, list)
        or not set(artifact_refs) <= set(task.get("allowed_artifact_refs", []))
    ):
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID")
    _validate_multidimensional_tool_calculations(
        value, task=task, invocation=invocation, run_dir=run_dir,
    )
    stage.validate_breadth_calculation_references(run_dir, value)
    handoff = json.loads((run_dir / "audit/portfolio-handoff.json").read_text(encoding="utf-8"))
    council_request = json.loads((run_dir / "council-request.json").read_text(encoding="utf-8"))
    gate = json.loads((run_dir / "evidence/gate.json").read_text(encoding="utf-8"))
    from product.runtime.research_submission import selected_calculation_outputs
    selected_upstream = selected_calculation_outputs(
        run_dir, record.get("upstream_calculation_selections", []),
    )
    if _research_report_monetary_findings(
        value, task=task, gate=gate, reference_packet=reference_packet,
        selected_upstream=selected_upstream,
    ):
        raise ValueError("DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED")
    bindings = {
        "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"], "council_request_id": council_request["request_id"],
        "council_request_hash": council_request["request_hash"], "decision_cutoff": gate["decision_cutoff"],
    }
    dependency_claim_ids = []
    for dependency_id in task.get("depends_on", []):
        dependency_matches = []
        for path in (run_dir / "research/reports").glob("*/dimension-report.json"):
            dependency = json.loads(path.read_text(encoding="utf-8"))
            if dependency.get("report_id") == f"dimension-report:{dependency_id}":
                dependency_matches.append(dependency)
        if len(dependency_matches) != 1:
            raise ValueError("MULTIDIMENSIONAL_DEPENDENCY_REPORT_MISSING")
        from product.runtime.multidimensional_references import known_claim_references, VERSION
        dependency_claim_ids.extend(known_claim_references(
            dependency_matches,
            allow_legacy=not reference_map or reference_map["binding"]["version"] != VERSION,
        ))
    report = __import__(
        "product.council.multidimensional_research", fromlist=["envelope_research_dimension_draft"]
    ).envelope_research_dimension_draft(
        value, task=task, invocation=invocation, expected_bindings=bindings,
        allowed_security_ids=[
            item["security_id"] for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "COMMON_STOCK"
        ],
        allowed_evidence_ids=task["allowed_evidence_ids"],
        allowed_calculation_evidence_ids=task.get("allowed_calculation_evidence_ids", []),
        known_research_claim_ids=dependency_claim_ids,
        allowed_documents=task.get("allowed_documents", []),
    )
    evidence = [
        item for item in gate["allowed_evidence"]
        if item["evidence_id"] in set(task["allowed_evidence_ids"])
    ]
    return report, evidence, selected_upstream


def _capture_research_material_preparation(payload, record, environment):
    """保存资料准备结果；候选/正文引用必须来自本 Invocation 实际产物。"""

    stage = _research_materials_module()
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    value = _trusted_bound_output(payload, record)
    index = _research_index(environment)
    matches = [item for item in index["tasks"] if item.get("invocation_id") == value.get("invocation_id")]
    if len(matches) != 1 or value.get("run_id") != index.get("run_id"):
        raise ValueError("RESEARCH_MATERIALS_OUTPUT_INVOCATION_UNKNOWN")
    task = matches[0]
    invocation = json.loads((run_dir / task["invocation_path"]).read_text(encoding="utf-8"))
    if payload.get("agent_type") != task["agent"] or payload.get("model") != invocation.get("model"):
        raise ValueError("RESEARCH_MATERIALS_OUTPUT_AGENT_OR_MODEL_INVALID")
    if (task.get("semantic_output_version") not in {None, stage.SEMANTIC_OUTPUT_VERSION}
            or task.get("semantic_output_version") != invocation.get("semantic_output_version")):
        raise ValueError("RESEARCH_MATERIALS_SEMANTIC_PROTOCOL_INVALID")
    if task.get("semantic_output_version") != stage.SEMANTIC_OUTPUT_VERSION:
        raise ValueError("RESEARCH_MATERIALS_LEGACY_OUTPUT_WRITE_RETIRED")
    value, audit = stage.assemble_material_semantic_draft(
        json.loads(payload["last_assistant_message"]), task=task, run_dir=run_dir,
    )
    stage.validate_material_preparation_output(value, task=task, run_dir=run_dir)
    directory = run_dir / "research/material-results" / _canonical_hash({"task_id": task["task_id"]})[:16]
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "preparation-result.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if audit is not None:
        stage._write_object(directory / "tool-audit.json", audit)
    record["output_capture"] = {
        "version": "research-material-preparation-result/1.0.0", "status": "SAVED",
        "path": str(path.relative_to(run_dir)), "output_hash": _canonical_hash(value),
        "task_id": task["task_id"], "security_id": task["security_id"],
        "preparation_kind": task["preparation_kind"],
        **({"tool_audit_ref": str((directory / "tool-audit.json").relative_to(run_dir)),
            "tool_audit_hash": audit["audit_hash"]} if audit is not None else {}),
    }






def _capture_common_stock_eval_result(payload, record, environment):
    """保存 dev_eval 的原始结构化结果并由确定性收尾器验收。"""

    module = _common_stock_eval_module()
    eval_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    if payload.get("agent_type") != "dev_eval":
        raise ValueError("COMMON_STOCK_EVAL_AGENT_INVALID")
    expected_model = environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL")
    if not expected_model or payload.get("model") != expected_model:
        raise ValueError("COMMON_STOCK_EVAL_MODEL_INVALID")
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("COMMON_STOCK_EVAL_OUTPUT_MISSING")
    try:
        value = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError("COMMON_STOCK_EVAL_OUTPUT_NOT_JSON") from exc
    if not isinstance(value, Mapping) or value.get("model") != payload.get("model"):
        raise ValueError("COMMON_STOCK_EVAL_OUTPUT_MODEL_INVALID")
    semantic_path = eval_dir / "invocation/semantic-result.json"
    if semantic_path.exists():
        raise ValueError("COMMON_STOCK_EVAL_OUTPUT_EXISTS")
    descriptor = os.open(
        semantic_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(message)
        if not message.endswith("\n"):
            stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    result = module.finalize_common_stock_eval_job(
        eval_dir=eval_dir, semantic_result_path=semantic_path
    )
    record["output_capture"] = {
        "version": module.EVAL_RESULT_VERSION,
        "status": "SAVED",
        "path": "eval/result.json",
        "report_path": "eval/report.md",
        "output_hash": _canonical_hash(result),
        "eval_id": result["eval_id"],
        "security_id": result["security_id"],
    }


def _persist_rejected_common_stock_eval_output(payload, environment) -> dict[str, Any]:
    eval_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return {}
    path = eval_dir / "invocation/rejected-semantic-result.json"
    if not path.exists():
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(message)
            if not message.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "rejected_path": str(path.relative_to(eval_dir)),
        "rejected_output_hash": _canonical_hash({"assistant_message": message}),
    }


def _persist_rejected_common_stock_output(payload, environment) -> dict[str, Any]:
    """保留被确定性契约拒绝的原始最终消息；不解析、修补或冒充有效报告。"""

    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return {}
    child_id = str(payload.get("agent_id", "unknown"))
    name = hashlib.sha256(child_id.encode("utf-8")).hexdigest() + ".json"
    path = run_dir / "research/rejected" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(message)
            if not message.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "rejected_path": str(path.relative_to(run_dir)),
        "rejected_output_hash": _canonical_hash({"assistant_message": message}),
    }


def _multidimensional_output_attempt(
    log_path: Path, payload: Mapping[str, Any]
) -> int:
    """Return the append-only submission number for one child research session."""

    previous = 0
    records: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines() if log_path.is_file() else []:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    for item in records:
        capture = item.get("output_capture")
        if (
            item.get("parent_session_id") == payload.get("session_id")
            and item.get("child_session_id") == payload.get("agent_id")
            and isinstance(capture, Mapping)
            and isinstance(capture.get("attempt"), int)
            and item.get("identity_binding", {}).get("status") == "BOUND"
            and item.get("local_revision_authorized") is not False
        ):
            previous = max(previous, int(capture["attempt"]))
    return previous + 1


def _resolve_local_revision(log_path, payload, record, environment, attempt, *, authorize_only=False):
    """可信绑定先于额度/原稿写入；首稿之外不得绕过局部修订约束。"""
    if record.get("identity_binding", {}).get("status") != "BOUND":
        raise ValueError(record.get("identity_binding", {}).get("failure_code", "LOCAL_REVISION_IDENTITY_UNBOUND"))
    if attempt > 2:
        raise ValueError("LOCAL_REVISION_LIMIT_EXHAUSTED")
    if attempt == 1:
        return payload
    first = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    first = [item for item in first
             if item.get("parent_session_id") == payload.get("session_id")
             and item.get("child_session_id") == payload.get("agent_id")
             and item.get("identity_binding", {}).get("status") == "BOUND"
             and item.get("local_revision_authorized") is not False
             and item.get("output_capture", {}).get("attempt") == 1]
    if len(first) != 1 or first[0].get("output_capture", {}).get("repair_state") != "REPAIR_REQUESTED":
        raise ValueError("LOCAL_REVISION_NOT_AUTHORIZED")
    if first[0].get("repair_request", {}).get("transport") != "RESEARCH_SUBMISSION":
        from product.runtime.local_revision import verify_binding
        if verify_binding(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), payload, record, first[0]) is None:
            raise ValueError("LOCAL_REVISION_NOT_AUTHORIZED")
    if authorize_only:
        return payload
    if first[0].get("repair_request", {}).get("transport") == "RESEARCH_SUBMISSION":
        return payload  # 由 MCP 的原始对象/精确回执边界执行补丁，不解析回执为报告。
    from product.runtime.local_revision import resolve
    return resolve(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), payload, record, first[0])


def _bind_local_revision(repair, payload, record, raw, environment):
    """为已定位的对象错误绑定范围，沿用已有 Hook 反馈而非另建重试流程。"""
    from product.runtime.research_submission import BOUNDED_REVISION_VERSION, bounded_stop_repair
    if record.get("submission_mode") == BOUNDED_REVISION_VERSION:
        return bounded_stop_repair(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), record, repair)
    if repair is None or record.get("submission_mode"):
        return repair
    if repair.get("validation_error") == "RESEARCH_OUTPUT_JSON_INVALID":
        # 解析器行列只说明发现语法错误的位置，不是可证明的字段边界。
        # 保留原文和诊断，但不得借旧整稿反馈绕过当前局部修订契约。
        return None
    from product.runtime.local_revision import bind
    from product.runtime.schema_validation import schema_issue_locations
    draft = json.loads(payload["last_assistant_message"])
    # 校验作者实际提交的选择草稿，而不是装配后才成立的正式报告。
    # 两种契约不能混用；纠错辅助字段也不能覆盖当前可信任务的 Schema。
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    packet = None
    if (_common_stock_stage(environment) or _research_materials_stage(environment)
            or _common_stock_eval(environment) or environment.get("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT")):
        schema = _simple_research_draft_schema(environment, repair["invocation_id"])
    elif _independent_skeptic_stage(environment):
        # 独立 Skeptic 使用自己的业务契约，不能套用正向八维结构。
        module = _independent_skeptic_module()
        task = next(item for item in _research_index(environment)["tasks"]
                    if item["invocation_id"] == repair["invocation_id"])
        packet = module.build_skeptic_dispatch_packet(
            Path(__file__).resolve().parents[2], run_dir, task["task_name"],
            index_ref=environment.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"))
        schema = module.skeptic_model_packet(packet)["output_schema"]
    else:
        from product.runtime.multidimensional_references import load_reference_packet
        packet = load_reference_packet(run_dir, repair["invocation_id"])
        from product.runtime.calculation_handoff import semantic_selection_draft_schema
        schema = semantic_selection_draft_schema(packet)
    details = repair.get("validation_details", {})
    findings = [*details.get("findings", []), *details.get("dangling_references", [])]
    findings.extend(schema_issue_locations(draft, schema))
    if (isinstance(packet, Mapping) and "calculation_selections" in draft
            and repair["validation_error"].startswith("SCHEMA_")
            and packet.get("task", {}).get("prepared_result_reference_version") == "prepared-result-reference/1.0.0"):
        # The first schema error can mask an independently obvious empty claim.
        # Do not assemble malformed choices or call them ungrounded: their author
        # has declared an association, even if the reference itself needs repair.
        associated = set()
        choices = draft.get("calculation_selections", [])
        for choice in choices if isinstance(choices, list) else []:
            if isinstance(choice, Mapping) and isinstance(choice.get("claim_ids"), list):
                associated.update(x for x in choice["claim_ids"] if isinstance(x, str))
        upstream = draft.get("upstream_calculation_selections", [])
        for choice in upstream if isinstance(upstream, list) else []:
            if isinstance(choice, Mapping):
                if isinstance(choice.get("claim_id"), str):
                    associated.add(choice["claim_id"])
                if isinstance(choice.get("claim_ids"), list):
                    associated.update(x for x in choice["claim_ids"] if isinstance(x, str))
        claims = draft.get("claims", [])
        for i, claim in enumerate(claims if isinstance(claims, list) else []):
            if (isinstance(claim, Mapping) and isinstance(claim.get("claim_id"), str)
                    and claim["claim_id"] and claim["claim_id"] not in associated
                    and not any(claim.get(field) for field in (
                        "evidence_refs", "research_claim_refs", "document_refs", "assumption_ids", "calculation_refs"))):
                if len(findings) < 32 and not any(
                        f.get("code") == "DIMENSION_REPORT_CLAIM_UNGROUNDED"
                        and f.get("path") in {f"claims[{i}]", f"/claims/{i}"} for f in findings):
                    findings.append({"code": "DIMENSION_REPORT_CLAIM_UNGROUNDED", "path": f"claims[{i}]"})
    if repair["validation_error"] == "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID":
        # 仅开放作者自己声明的 selector 及关联占位主张，完整来源/PIT校验照旧。
        selections = draft.get("source_literal_selections")
        if ("source_literal_selections" not in draft
                and isinstance(packet, Mapping)
                and packet.get("task", {}).get("source_literal_selection") in {
                    _SOURCE_LITERAL_VERSION, _MACRO_SOURCE_LITERAL_VERSION,
                }
                and any(isinstance(c, Mapping) and re.search(r"\{\{sf\.[A-Za-z][A-Za-z0-9_]{0,23}\}\}", str(c.get("statement", "")))
                        for c in draft.get("claims", []))):
            findings.append({"path": "source_literal_selections"})
        marker_findings = details.get("findings", [])
        if marker_findings:
            findings.extend({"path": f["related_claim_path"]} for f in marker_findings
                            if f.get("related_claim_path"))
        if isinstance(selections, list):
            # Marker diagnostics cannot prove earlier source/PIT checks passed.
            # Preserve the original declared-selector scope for mixed errors.
            findings.extend({"path": f"source_literal_selections[{i}]"} for i in range(len(selections)))
            selected_claims = {s.get("claim_id") for s in selections if isinstance(s, Mapping)}
            findings.extend({"path": f"claims[{i}]"} for i, c in enumerate(draft.get("claims", []))
                            if isinstance(c, Mapping) and (c.get("claim_id") in selected_claims
                            or "{{sf." in str(c.get("statement", ""))))
    if not findings:
        diagnostics = _multidimensional_draft_diagnostics(
            payload, environment, failure_code=repair["validation_error"], trusted_record=record)
        findings.extend(diagnostics.get("findings", []))
    if repair["validation_error"] == "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED":
        findings.extend(_monetary_repetition_context(draft, findings))
    binding = bind(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), payload, record, raw, repair, findings)
    if binding is None:
        return None
    result = {**repair, **binding}
    result.pop("original_draft", None)
    result.pop("output_schema", None)
    result["instruction"] = (
        "这是原 Agent 同一会话的唯一一次局部纠正。仅返回"
        '{"base_draft_ref":"所给短引用","changes":[{"op":"replace","path":"允许的字段路径","value":"你自行纠正的内容"}]}。'
        "op 仅支持 add/replace/remove；不得修改 allowed_paths 之外的对象、身份或结论。"
        "删除已定位数组项用remove且不带value，不能replace成null；路径均按原稿索引。"
        "evidence_refs 必须由你核对真实允许资料后选择，不猜引用、不删除有据主张规避检查。"
        "可修正定位到的错误主张/观察条件；关联未改部分会再次校验，出现悬空引用仍失败。"
        "无需抄写 hash 或重发整稿；第二次失败终止，Python 不代写研究。"
    )
    if (repair["validation_error"] == "DIMENSION_REPORT_CLAIM_UNGROUNDED"
            or any(f.get("code") == "DIMENSION_REPORT_CLAIM_UNGROUNDED" for f in findings)):
        result["instruction"] += (
            " 缺依据位置按已选计算装配后定位，不要求在草稿手填calculation_refs。"
            "由你在允许路径内核对并选择真正支持本条的依据；可用research_claim_refs关联"
            "草稿中确实支持本条的已有主张，不能只在statement里写引用名称替代结构关联。"
        )
        result["validation_details"] = {**details, "findings": findings[:32]}
    if repair["validation_error"] == "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID":
        result["instruction"] += (
            " 逐项核对validation_details中的全部selector、目标statement及observed_count；"
            "每个声明占位在目标正文恰好一次。由你修正声明或使用位置，不只处理第一项。"
            "MARKER_OUTSIDE_STATEMENT指出不允许绑定的具体位置，由你重新表达该处；"
            "summary等位置不支持来源占位，不会自动填值。"
            "定位占位不证明来源/字段/PIT已合法，第二稿仍核对已query且同claim引用的来源。"
        )
    if repair["validation_error"] == "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED":
        result["instruction"] += (
            " amount_index按最终拼接的statement计数，包含core_statement和全部关系解释句，"
            "不是仅主段落的索引；对照source_value/reported_value逐项核对所有定位金额。"
            "只改core不能消除research_relation_clauses中残留的同类错误，"
            "须由你在原允许路径核对并纠正，不自动转换或扩大修订范围。"
            " 同额重复description仅供原作者核对，不是新增硬错误或来源证明；"
            "核对主张及这些精确路径中的单位，保留来源原表示或真实同源计算依据。"
        )
    return result


def _simple_research_draft_schema(environment, invocation_id):
    """从当前角色的实际交付包读取草稿契约，不新建通用报告结构。"""
    root = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    if _common_stock_eval(environment):
        return _common_stock_eval_module().build_common_stock_eval_packet(
            root, expected_model=environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL"))["output_schema"]
    if environment.get("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT"):
        module = _invocation_module()
        matches = [json.loads((root / "invocations" / f"{agent}.json").read_text())
                   for agent in sorted(module.SPECIALIST_AGENTS)
                   if (root / "invocations" / f"{agent}.json").is_file()]
        matches = [item for item in matches if item["invocation_id"] == invocation_id]
        if len(matches) != 1:
            raise ValueError("SPECIALIST_CAPTURE_BINDING_INVALID")
        path = Path(matches[0]["output_schema"])
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError("SPECIALIST_CAPTURE_SCHEMA_PATH_INVALID")
        return module.specialist_semantic_schema(json.loads(path.read_text()))
    task = next(item for item in _research_index(environment)["tasks"]
                if item["invocation_id"] == invocation_id)
    repository = Path(__file__).resolve().parents[2]
    if _common_stock_stage(environment):
        module = _common_stock_module()
        packet = module.build_common_stock_dispatch_packet(repository, root, task["task_name"])
        return module.common_stock_model_packet(packet)["output_schema"]
    module = _research_materials_module()
    return module.build_research_materials_dispatch_packet(repository, root, task["task_name"])["output_schema"]


def _simple_research_repair_packet(payload, record, environment, *, failure_code, attempt):
    located_selection_errors = (
        "MULTIDIMENSIONAL_REFERENCE_UNKNOWN:",
        "RESEARCH_MATERIALS_DOCUMENT_SELECTION_INVALID:",
    )
    eval_selection_errors = {
        "COMMON_STOCK_EVAL_CLAIM_REF_INVALID": "claim_refs",
        "COMMON_STOCK_EVAL_EVIDENCE_REF_INVALID": "evidence_refs",
        "COMMON_STOCK_EVAL_DIMENSION_STATUS_INVALID": "status",
    }
    if (attempt != 1 or record.get("identity_binding", {}).get("status") != "BOUND"
            or not failure_code.startswith(("SCHEMA_", "COMMON_STOCK_EVAL_RESULT_SCHEMA_INVALID:",
                                           *located_selection_errors,
                                           *(key + ":" for key in eval_selection_errors),
                                           "COMMON_STOCK_EVAL_AGGREGATE_INVALID"))):
        return None
    from product.runtime.schema_validation import schema_issue_locations
    trusted = record["trusted_task_binding"]
    schema = _simple_research_draft_schema(environment, trusted["invocation_id"])
    draft = json.loads(payload["last_assistant_message"])
    if environment.get("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT"):
        reserved = _invocation_module().SPECIALIST_TECHNICAL_FIELDS
    elif _common_stock_eval(environment):
        module = _common_stock_eval_module()
        packet = module.build_common_stock_eval_packet(
            Path(environment["STOCK_AGENT_RUN_DIR"]),
            expected_model=environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL"))
        reserved = set(module.build_common_stock_eval_result_schema(packet["input_manifest"])["properties"]) - set(schema["properties"])
    else:
        reserved = set()
    if isinstance(draft, dict) and reserved.intersection(draft):
        return None  # 技术身份冒用不因删除额外字段进入宽松修复分支。
    findings = schema_issue_locations(draft, schema)
    if not findings and _common_stock_eval(environment):
        code, _, name = failure_code.partition(":")
        if code in eval_selection_errors and name in _common_stock_eval_module().DIMENSIONS:
            findings = [{"code": code, "path": f"dimensions.{name}.{eval_selection_errors[code]}"}]
        elif failure_code == "COMMON_STOCK_EVAL_AGGREGATE_INVALID":
            findings = [{"code": failure_code, "path": "status"}]
    if not findings and failure_code.startswith(located_selection_errors):
        # 只采用校验器的字段定位；错误引用文本不参与路径解析或引用修正。
        path = failure_code.split(":", 2)[1]
        if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\[\d+\]|\.[A-Za-z_][A-Za-z_0-9]*)*", path):
            findings = [{"code": failure_code.split(":", 1)[0], "path": path}]
    if not findings or len(findings) > 32:
        return None
    return {"task_id": trusted["task_id"], "invocation_id": trusted["invocation_id"],
            "attempt": 1, "maximum_submissions": 2, "validation_error": failure_code,
            "validation_details": {"findings": findings}}


def _capture_revisable_research_output(payload, record, environment, log_path, capture):
    """沿已有 Stop 边界复用有界局部修订；不调用模型、不改研究语义。"""
    attempt = _multidimensional_output_attempt(log_path, payload)
    raw = {}
    candidate = payload
    record["local_revision_authorized"] = False
    try:
        if environment.get("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT"):
            saved = [item for item in _read_jsonl_records_unlocked(log_path)
                     if item.get("parent_session_id") == payload["session_id"]
                     and item.get("child_session_id") == payload["agent_id"]
                     and item.get("output_capture", {}).get("status") == "SAVED"
                     and not item.get("duplicate_of")]
            if saved:
                if len(saved) != 1:
                    raise ValueError("SPECIALIST_CAPTURE_OUTPUT_EXISTS")
                previous = saved[0]
                verify_legacy_envelope_hash(previous, hash_field="event_hash", location="specialist:accepted-Stop")
                if (previous.get("trusted_task_binding") != record.get("trusted_task_binding")
                        or previous.get("assistant_message_sha256") != record.get("assistant_message_sha256")):
                    raise ValueError("SPECIALIST_CAPTURE_OUTPUT_EXISTS")
                # Hook 重复交付同一已接受消息不是第三次草稿；仍重验原稿/补丁及正式输出。
                candidate = _resolve_local_revision(log_path, payload, record, environment,
                                                    previous["output_capture"]["attempt"])
                capture(candidate, record, environment)
                record["output_capture"].update({key: previous["output_capture"][key]
                                                for key in ("attempt", "repair_state", "submission_path", "submission_hash")})
                record["duplicate_of"] = previous["event_hash"]
                return None
        _resolve_local_revision(log_path, payload, record, environment, attempt, authorize_only=True)
        record["local_revision_authorized"] = True
        raw = _persist_multidimensional_raw_output(payload, environment, attempt=attempt)
        candidate = _resolve_local_revision(log_path, payload, record, environment, attempt)
        capture(candidate, record, environment)
        record["output_capture"].update(
            attempt=attempt, repair_state="REPAIRED" if attempt == 2 else "NOT_REQUIRED",
        )
        # Specialist 消费者原 raw_* 指的是已解析的语义稿，不改其 hash 口径。
        # 原始事件消息（第二次可能是补丁）单独保存，不冒充装配后的语义稿。
        if environment.get("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT"):
            record["output_capture"].update(submission_path=raw["raw_path"], submission_hash=raw["raw_output_hash"])
        else:
            record["output_capture"].update(raw)
        return None
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        failure_code = str(exc)
        repair = None
        try:
            repair = _simple_research_repair_packet(
                candidate, record, environment, failure_code=failure_code, attempt=attempt,
            )
            repair = _bind_local_revision(repair, candidate, record, raw, environment)
        except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
            record["repair_binding_error"] = str(error)
            repair = None
        record["output_capture"] = {
            "status": "FAILED", "failure_code": failure_code, "attempt": attempt,
            "repair_state": "REPAIR_REQUESTED" if repair else "EXHAUSTED" if attempt >= 2 else "NOT_ALLOWED",
            **raw,
        }
        if raw:
            record["output_capture"].update(rejected_path=raw["raw_path"], rejected_output_hash=raw["raw_output_hash"])
        if repair is None:
            return None
        record["hook_event_name"] = "SubagentStopBlocked"
        record["hook_decision"] = "BLOCK"
        record["repair_request"] = {key: repair[key] for key in (
            "repair_contract", "task_id", "invocation_id", "attempt", "maximum_submissions",
            "validation_error", "base_draft_ref", "allowed_paths", "binding_path", "binding_hash",
        ) if key in repair}
        return {"decision": "block", "reason": json.dumps(
            _repair_model_view(repair), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )}


def _repair_model_view(repair):
    from product.runtime.local_revision import VERSION
    if repair.get("repair_contract") != VERSION:
        return repair
    return {key: value for key, value in repair.items() if key not in {
        "binding_path", "binding_hash", "output_schema_hash", "task_id", "invocation_id"}}


def _persist_multidimensional_raw_output(
    payload: Mapping[str, Any], environment: Mapping[str, str], *, attempt: int
) -> dict[str, Any]:
    """Preserve each submitted draft exactly; never treat it as a valid report."""

    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return {}
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    identity = f"{payload.get('session_id')}:{payload.get('agent_id')}"
    name = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    path = run_dir / "research/raw-drafts" / f"{name}-attempt-{attempt}.json"
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != run_dir and run_dir in parent.parents):
        raise ValueError("RESEARCH_RAW_DRAFT_SYMLINK_FORBIDDEN")
    if not path.resolve().is_relative_to(run_dir):
        raise ValueError("RESEARCH_RAW_DRAFT_PATH_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(message)
        if not message.endswith("\n"):
            stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "raw_path": str(path.relative_to(run_dir)),
        "raw_output_hash": _canonical_hash({"assistant_message": message}),
    }


def _json_syntax_finding(message: Any) -> dict[str, Any] | None:
    """Parser coordinates only: no excerpts, guessed identity or repaired content."""
    if not isinstance(message, str) or len(message.encode("utf-8")) > 256 * 1024:
        return None
    try:
        json.loads(message)
    except json.JSONDecodeError as exc:
        return {
            "code": "RESEARCH_OUTPUT_JSON_INVALID", "parser_error": exc.msg,
            "line": exc.lineno, "column": exc.colno, "character_offset": exc.pos,
            "character_count": len(message), "offset_basis": "zero-based Unicode characters",
        }
    except (ValueError, RecursionError):
        return None
    return None


_CHINESE_USD_HUNDRED_MILLION = re.compile(
    r"(?<![\d.,])(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*亿美元"
)
_DOLLAR_PREFIX_HUNDRED_MILLION = re.compile(
    r"\$(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*亿"
)
_OTHER_CURRENCY_BEFORE_DOLLAR = re.compile(
    r"(?<![A-Za-z])(?:HKD|HK|CAD|CA|C|AUD|AU|SGD|SG|NZD|NZ|TWD|NT|RMB|JPY|EUR|GBP|CHF|"
    r"港币|港元|加元|澳元|新元|欧元|英镑|人民币|[€£¥])\s*[:：]?\s*$",
    re.IGNORECASE,
)
_EXPLICIT_DOLLAR_CODE_PREFIX = re.compile(r"(?<![A-Za-z])([A-Z]{1,3})\s*[:：]?\s*$")
_ENGLISH_USD_BILLION = re.compile(
    r"(?<![\d.,])(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*billion\s*USD\b"
    r"|\bUSD\s*(?P<prefixed>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*billion\b"
    r"|\$(?P<symbol_amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*billion\b",
    re.IGNORECASE,
)


def _explicit_amounts(pattern: re.Pattern[str], text: str) -> list[Decimal]:
    result = []
    for match in pattern.finditer(text):
        symbol = match.groupdict().get("symbol_amount")
        if symbol is not None and _other_dollar_currency_prefix(text, match.start()):
            continue
        raw = match.group("amount") or match.groupdict().get("prefixed") or symbol
        try:
            amount = Decimal(raw.replace(",", ""))
        except (AttributeError, InvalidOperation):
            continue
        if amount.is_finite():
            result.append(amount)
    return result


def _other_dollar_currency_prefix(text: str, start: int) -> bool:
    preceding = text[max(0, start - 12):start]
    immediate = preceding[-1:] if preceding else ""
    before_separator = preceding.rstrip(" \t:：")[-1:]
    explicit_code = _EXPLICIT_DOLLAR_CODE_PREFIX.search(preceding)
    if explicit_code:
        return explicit_code.group(1) not in {"USD", "US"}
    return bool(
        (immediate and immediate.isascii() and immediate.isalpha())
        or (before_separator and unicodedata.category(before_separator) == "Sc")
        or _OTHER_CURRENCY_BEFORE_DOLLAR.search(preceding)
    )


def _unprefixed_dollar_yi_amounts(text: str) -> list[Decimal]:
    result = []
    for match in _DOLLAR_PREFIX_HUNDRED_MILLION.finditer(text):
        if _other_dollar_currency_prefix(text, match.start()):
            continue
        try:
            amount = Decimal(match.group("amount").replace(",", ""))
        except InvalidOperation:
            continue
        if amount.is_finite():
            result.append(amount)
    return result


def _research_report_monetary_findings(
    draft: Mapping[str, Any], *, task: Mapping[str, Any], gate: Mapping[str, Any],
    reference_packet: Mapping[str, Any], selected_upstream: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Locate an unreceipted USD scale rewrite with one identifiable cited source."""
    from product.runtime.monetary import require_monetary_equivalence
    from product.runtime.research_submission import ASSEMBLY_VERSIONS

    if task.get("capability") != "RESEARCH_REPORT" or task.get("submission_version") not in ASSEMBLY_VERSIONS:
        return []
    if gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash"):
        raise ValueError("DIMENSION_REPORT_MONETARY_GATE_INVALID")
    allowed = set(task.get("allowed_evidence_ids", []))
    evidence = {item["evidence_id"]: item for item in gate.get("allowed_evidence", [])
                if item.get("evidence_id") in allowed}
    mapping = reference_packet.get("reference_map", {})
    evidence_map = mapping.get("evidence", {})
    claim_map = mapping.get("claims", {})
    dependencies = {
        (report["report_id"], claim["claim_id"]): claim.get("statement", "")
        for report in reference_packet.get("dependency_reports", [])
        for claim in report.get("claims", [])
        if isinstance(claim, Mapping)
    }
    findings = []
    claims = draft.get("claims", [])
    local_claim_ids = {
        claim.get("claim_id") for claim in claims if isinstance(claim, Mapping)
        and isinstance(claim.get("claim_id"), str)
    } if isinstance(claims, list) else set()
    for index, claim in enumerate(claims if isinstance(claims, list) else []):
        if not isinstance(claim, Mapping) or not isinstance(claim.get("statement"), str):
            continue
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) for ref in refs):
            continue
        cited_ids = [evidence_map.get(ref, ref) for ref in refs]
        if len(cited_ids) != len(set(cited_ids)) or any(source_id not in evidence for source_id in cited_ids):
            continue
        reported = _explicit_amounts(_ENGLISH_USD_BILLION, claim["statement"])
        if not reported:
            continue
        cited_contents = []
        for source_id in cited_ids:
            value = evidence[source_id].get("value")
            cited_contents.append((source_id, value.get("content_tier"), value.get("content"))
                                  if isinstance(value, Mapping) else (source_id, None, None))
        upstream_english = set()
        ambiguous_upstream = False
        upstream_refs = claim.get("research_claim_refs", [])
        if not isinstance(upstream_refs, list):
            continue  # Original schema validation handles malformed draft fields.
        for ref in upstream_refs:
            if not isinstance(ref, str):
                continue
            if ref in local_claim_ids:
                continue  # Local claims take precedence over same-named dependencies.
            mapped = claim_map.get(ref)
            if isinstance(mapped, Mapping):
                upstream_english.update(_explicit_amounts(
                    _ENGLISH_USD_BILLION,
                    str(dependencies.get((mapped.get("report_id"), mapped.get("claim_id")), "")),
                ))
            else:
                matches = [statement for (_, claim_id), statement in dependencies.items() if claim_id == ref]
                if len(matches) == 1:
                    upstream_english.update(_explicit_amounts(_ENGLISH_USD_BILLION, str(matches[0])))
                elif len(matches) > 1:
                    ambiguous_upstream = True
        if ambiguous_upstream:
            continue
        for amount_index, target in enumerate(reported):
            if target in upstream_english:
                continue
            matching_sources = []
            original_english = False
            for source_id, tier, content in cited_contents:
                if not isinstance(content, str):
                    continue
                if target in _explicit_amounts(_ENGLISH_USD_BILLION, content):
                    original_english = True
                    break
                originals = {amount: "亿美元" for amount in _explicit_amounts(
                    _CHINESE_USD_HUNDRED_MILLION, content,
                )}
                for amount in _unprefixed_dollar_yi_amounts(content):
                    originals.setdefault(amount, "$亿")
                for original, source_unit in originals.items():
                    try:
                        require_monetary_equivalence(
                            source_value=original, source_scale="亿",
                            reported_value=target, reported_scale="billion",
                        )
                    except ValueError:
                        continue
                    matching_sources.append((source_id, tier, original, source_unit))
            # Multiple matching Evidence are ambiguous, even when only one is licensed.
            # Repeated identical amounts inside one Evidence do not create a new source.
            if original_english or len(matching_sources) != 1:
                continue
            source_id, tier, original, source_unit = matching_sources[0]
            if tier != "LICENSED_API_CONTENT":
                continue
            short_ids = [short for short, full in evidence_map.items() if full == source_id]
            if len(short_ids) != 1:
                continue
            verified = False
            for selection in selected_upstream:
                calculation = selection.get("calculation", {})
                output = selection.get("verified_output", {})
                if (selection.get("claim_id") != claim.get("claim_id")
                        or calculation.get("input_evidence_refs") != [source_id]
                        or output.get("operation") != "monetary_scale"
                        or output.get("evidence_ids") != [source_id]):
                    continue
                for conversion in output.get("conversions", []):
                    if (conversion.get("source_scale") != "亿"
                            or conversion.get("target_scale") != "billion"):
                        continue
                    try:
                        source_amount = Decimal(str(conversion.get("source_value")).replace(",", ""))
                        converted = Decimal(str(conversion.get("converted_value")).replace(",", ""))
                    except InvalidOperation:
                        continue
                    if source_amount.is_finite() and converted.is_finite() and source_amount == original and converted == target:
                        verified = True
                        break
                if verified:
                    break
            if not verified:
                findings.append({
                    "code": "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                    "path": f"claims[{index}].statement", "identifier": short_ids[0],
                    "amount_index": amount_index,
                    "source_unit": source_unit, "reported_unit": "billion USD",
                    "source_value": str(original) if len(str(original)) <= 64 else None,
                    "reported_value": str(target) if len(str(target)) <= 64 else None,
                    "amount_index_basis": "FINAL_ASSEMBLED_STATEMENT",
                })
    return findings


def _monetary_repetition_context(
    draft: Mapping[str, Any], findings: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Open exact repeated gap descriptions for author review, not factual validation."""
    located_amounts = set()
    claims = draft.get("claims", [])
    if not isinstance(claims, list):
        return []
    for finding in findings:
        if finding.get("code") != "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED":
            continue
        match = re.fullmatch(r"claims\[(\d+)\]\.statement", str(finding.get("path", "")))
        offset = finding.get("amount_index")
        if not match or type(offset) is not int or offset < 0 or int(match[1]) >= len(claims):
            continue
        claim = claims[int(match[1])]
        if not isinstance(claim, Mapping):
            continue
        statement = claim.get("statement")
        if statement is None and isinstance(claim.get("core_statement"), str):
            clauses = claim.get("research_relation_clauses", [])
            if not isinstance(clauses, list) or any(
                not isinstance(c, Mapping) or not isinstance(c.get("relation_statement"), str) for c in clauses
            ):
                continue
            statement = " ".join([claim["core_statement"], *(c["relation_statement"] for c in clauses)])
        if not isinstance(statement, str):
            continue
        amounts = _explicit_amounts(_ENGLISH_USD_BILLION, statement)
        if offset < len(amounts):
            located_amounts.add(amounts[offset])
    gaps = draft.get("data_gaps", [])
    if not located_amounts or not isinstance(gaps, list):
        return []
    context = []
    for index, gap in enumerate(gaps):
        if not isinstance(gap, Mapping) or not isinstance(gap.get("description"), str):
            continue
        if located_amounts.intersection(_explicit_amounts(_ENGLISH_USD_BILLION, gap["description"])):
            context.append({"path": f"data_gaps[{index}].description",
                            "status": "REPEATED_EXPLICIT_AMOUNT_AUTHOR_RECHECK"})
        if len(context) >= 32:
            break
    return context


def _multidimensional_draft_diagnostics(
    payload: Mapping[str, Any], environment: Mapping[str, str], *, failure_code: str,
    trusted_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Locate known structural defects without changing a draft or its validation result."""

    result: dict[str, Any] = {
        "stage": "REPORT_VALIDATION",
        "first_failure_code": failure_code.split(":", 1)[0],
        "status": "UNAVAILABLE", "findings": [],
    }
    if failure_code == "RESEARCH_OUTPUT_JSON_INVALID":
        finding = _json_syntax_finding(payload.get("last_assistant_message"))
        if finding is not None:
            result.update(status="LOCATED", findings=[finding], finding_count=1, truncated=False)
        else:
            result["reason"] = "SYNTAX_NOT_LOCATABLE_OR_OVER_BUDGET"
        return result
    try:
        message = payload.get("last_assistant_message")
        draft = json.loads(message) if isinstance(message, str) else None
        if not isinstance(draft, Mapping):
            result["reason"] = "DRAFT_NOT_OBJECT"
            return result
        invocation_id = draft.get("invocation_id")
        if trusted_record is not None:
            trusted_id = (trusted_record.get("trusted_task_binding") or {}).get("invocation_id")
            if ((trusted_record.get("identity_binding") or {}).get("status") != "BOUND"
                    or not trusted_id or invocation_id not in (None, trusted_id)):
                result["reason"] = "TASK_BINDING_UNAVAILABLE"
                return result
            invocation_id = trusted_id
        matches = [task for task in _research_index(environment)["tasks"]
                   if task.get("invocation_id") == invocation_id]
        if len(matches) != 1:
            result["reason"] = "TASK_BINDING_UNAVAILABLE"
            return result
        task = matches[0]
        allowed = set(task["allowed_evidence_ids"])
        from product.runtime.multidimensional_references import load_reference_packet
        packet = load_reference_packet(
            Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), task["invocation_id"],
            include_dependencies=(failure_code != "DIMENSION_REPORT_CLAIM_UNGROUNDED"
                                  or bool(draft.get("calculation_selections"))),
        )
        if failure_code == "DIMENSION_REPORT_CLAIM_UNGROUNDED" and "calculation_selections" in draft:
            # 语义稿省略机械引用；按与正式校验相同的精确装配观察，不能
            # 将已经选择的依据误报为缺失。装配只读且不替作者补任何选择。
            from product.runtime.calculation_handoff import assemble_calculation_selections
            draft = assemble_calculation_selections(
                Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), packet, dict(draft),
            )
        mapping = packet.get("reference_map", {})
        allowed.update(mapping.get("evidence", {}))
        external = set(packet.get("allowed_research_claim_ids", [])) | set(mapping.get("claims", {}))
        claims = draft.get("claims")
        claims = claims if isinstance(claims, list) else []
        claim_ids = {claim["claim_id"] for claim in claims
                     if isinstance(claim, Mapping) and isinstance(claim.get("claim_id"), str)}
        internal_ids = {
            "assumption_ids": {
                item["assumption_id"] for item in draft.get("assumptions", [])
                if isinstance(item, Mapping) and isinstance(item.get("assumption_id"), str)
            },
            "calculation_refs": {
                item["calculation_id"] for item in draft.get("calculations", [])
                if isinstance(item, Mapping) and isinstance(item.get("calculation_id"), str)
            },
            "document_refs": {
                item["document_id"] for item in draft.get("documents", [])
                if isinstance(item, Mapping) and isinstance(item.get("document_id"), str)
            },
        }
        # Final reference translation accepts exact aliases of selected documents.
        # Diagnostics must use that same representation, not flag valid short refs.
        selected_document_ids = set(internal_ids["document_refs"])
        internal_ids["document_refs"].update(
            short for short, full in mapping.get("documents", {}).items()
            if isinstance(short, str) and isinstance(full, str)
            and full in selected_document_ids
        )
        count = 0

        def add(code: str, path: str, identifier: Any, **details: Any) -> None:
            nonlocal count
            count += 1
            if len(result["findings"]) >= 32:
                return
            finding = {"code": code, "path": path}
            # Only compact technical identifiers are retained; never free-form text.
            if (isinstance(identifier, str) and 0 < len(identifier) <= 128
                    and identifier.isascii()
                    and all(char.isalnum() or char in "_:.-" for char in identifier)):
                finding["identifier"] = identifier
            else:
                finding["identifier_hash"] = _canonical_hash(identifier)
            finding.update(details)
            result["findings"].append(finding)

        if draft.get("status") == "SOURCE_LIMITED" and draft.get("evaluation_status") != "SOURCE_LIMITED":
            add("DIMENSION_REPORT_SOURCE_LIMITED_STATE_INVALID", "evaluation_status", draft.get("evaluation_status"))
        if draft.get("status") in {"FAILED", "TIMEOUT"} and draft.get("evaluation_status") == "PASS":
            add("DIMENSION_REPORT_FAILED_EVALUATION_INVALID", "evaluation_status", "PASS")
        expected_documents = {d["document_id"]: d for d in packet["task"].get("allowed_documents", [])}
        documents = draft.get("documents", [])
        for index, document in enumerate(documents if isinstance(documents, list) else []):
            if not isinstance(document, Mapping):
                continue
            expected = expected_documents.get(str(document.get("document_id")))
            if expected is None:
                add("DIMENSION_REPORT_DOCUMENT_NOT_ALLOWED", f"documents[{index}].document_id", document.get("document_id"))
                continue
            for field in sorted(expected):
                if field not in document or document[field] != expected[field]:
                    add("DIMENSION_REPORT_DOCUMENT_METADATA_DRIFT", f"documents[{index}].{field}", document.get(field))
            if set(document) - set(expected):
                add("DIMENSION_REPORT_DOCUMENT_METADATA_DRIFT", f"documents[{index}]", sorted(set(document) - set(expected)))

        identity_copy_paths = set(_industry_source_identity_copy_paths(task, draft))
        for collection in ("claims", "assumptions", "calculations", "documents",
                           "research_relationships", "observation_conditions"):
            items = draft.get(collection)
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, Mapping):
                    continue
                for field in ("evidence_refs", "counter_evidence_refs", "input_evidence_refs"):
                    refs = item.get(field)
                    if not isinstance(refs, list):
                        continue
                    field_allowed = (allowed | set(task.get("allowed_calculation_evidence_ids", []))
                                     if collection == "calculations" and field == "input_evidence_refs"
                                     else allowed)
                    for offset, ref in enumerate(refs):
                        if isinstance(ref, str) and ref not in field_allowed:
                            add("EVIDENCE_CLOSURE_FAILED", f"{collection}[{index}].{field}[{offset}]", ref)
                for field, code in (
                    ("research_claim_refs", "DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING"),
                    ("target_claim_refs", "DIMENSION_REPORT_RELATIONSHIP_TARGET_DANGLING"),
                ):
                    refs = item.get(field)
                    if isinstance(refs, list):
                        for offset, ref in enumerate(refs):
                            if isinstance(ref, str) and ref not in claim_ids | external:
                                add(code, f"{collection}[{index}].{field}[{offset}]", ref)
                if collection == "claims" and not any(item.get(field) for field in (
                    "evidence_refs", "research_claim_refs", "document_refs",
                    "assumption_ids", "calculation_refs",
                )):
                    add("DIMENSION_REPORT_CLAIM_UNGROUNDED", f"claims[{index}]", item.get("claim_id"))
                if collection == "claims":
                    for field, valid_ids in internal_ids.items():
                        refs = item.get(field)
                        if isinstance(refs, list):
                            for offset, ref in enumerate(refs):
                                if ref not in valid_ids:
                                    add("DIMENSION_REPORT_INTERNAL_REFERENCE_DANGLING",
                                        f"claims[{index}].{field}[{offset}]", ref)
                if collection == "claims" and f"claims[{index}].statement" in identity_copy_paths:
                    add("DIMENSION_REPORT_SOURCE_IDENTITY_IN_PROSE", f"claims[{index}].statement", item.get("claim_id"))
                if collection == "observation_conditions" and isinstance(item.get("claim_refs"), list):
                    for offset, ref in enumerate(item["claim_refs"]):
                        if isinstance(ref, str) and ref not in claim_ids:
                            add("DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING",
                                f"observation_conditions[{index}].claim_refs[{offset}]", ref)
        if failure_code == "MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID":
            allowed_artifacts = set(task.get("allowed_artifact_refs", []))
            for index, ref in enumerate(draft.get("artifact_refs", [])):
                if ref not in allowed_artifacts:
                    add("MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID",
                        f"artifact_refs[{index}]", ref)
            for index, calculation in enumerate(draft.get("calculations", [])):
                if isinstance(calculation, Mapping) and calculation.get("artifact_ref") not in allowed_artifacts:
                    add("MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID",
                        f"calculations[{index}].artifact_ref", calculation.get("artifact_ref"))
        if (
            trusted_record is not None
            and (trusted_record.get("identity_binding") or {}).get("status") == "BOUND"
            and trusted_record.get("submission_mode") in {
                "research-object-submission/3.0.0", "research-object-submission/4.0.0",
                "research-object-submission/5.0.0", "research-object-submission/6.0.0",
            }
            and all(
                (trusted_record.get("trusted_task_binding") or {}).get(field) == task.get(field)
                for field in ("run_id", "invocation_id", "task_id", "task_name", "agent")
            )
        ):
            from product.runtime.research_submission import selected_calculation_outputs
            root = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
            gate = json.loads((root / "evidence/gate.json").read_text(encoding="utf-8"))
            selections = selected_calculation_outputs(
                root, trusted_record.get("upstream_calculation_selections", []),
            )
            for finding in _research_report_monetary_findings(
                draft, task=task, gate=gate, reference_packet=packet,
                selected_upstream=selections,
            ):
                add(
                    finding["code"], finding["path"], finding["identifier"],
                    amount_index=finding["amount_index"],
                    source_unit=finding["source_unit"],
                    reported_unit=finding["reported_unit"],
                    source_value=finding["source_value"],
                    reported_value=finding["reported_value"],
                    amount_index_basis=finding["amount_index_basis"],
                )
        result.update(status="LOCATED" if count else "NO_KNOWN_ISSUES",
                      task_id=task["task_id"], finding_count=count, truncated=count > 32)
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        result.update(status="UNAVAILABLE", reason="DIAGNOSTIC_INPUT_INVALID", findings=[])
    return result


def _multidimensional_repair_packet(
    payload: Mapping[str, Any], environment: Mapping[str, str], *,
    failure_code: str, attempt: int, trusted_record: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build one model-visible repair request for structural draft errors only."""

    from product.runtime.research_submission import BOUNDED_REVISION_VERSION, bounded_stop_repair
    if (attempt == 1 and (trusted_record or {}).get("submission_mode") == BOUNDED_REVISION_VERSION
            and (trusted_record or {}).get("submission_binding", {}).get("submission") == 1):
        try:
            inline_repair = bounded_stop_repair(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), trusted_record)
        except (OSError, ValueError, KeyError, TypeError):
            return None  # 事件或基础稿不可信时不开放修订，保留原始拒绝原因。
        if inline_repair is not None:
            return inline_repair

    if failure_code.startswith("SCHEMA_"):
        if (attempt != 1 or not trusted_record
                or (trusted_record.get("identity_binding") or {}).get("status") != "BOUND"
                or trusted_record.get("submission_mode")):
            return None
        try:
            from product.runtime.multidimensional_references import load_reference_packet
            from product.runtime.calculation_handoff import semantic_selection_draft_schema
            from product.runtime.schema_validation import schema_issue_locations
            packet = load_reference_packet(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(),
                                           trusted_record["trusted_task_binding"]["invocation_id"])
            draft = json.loads(payload["last_assistant_message"])
            schema = semantic_selection_draft_schema(packet)
            findings = schema_issue_locations(draft, schema)
            if not findings or len(findings) > 32:
                return None
            return {
                "repair_contract": "multidimensional-draft-repair/1.0.0",
                "task_id": packet["task"]["task_id"], "invocation_id": packet["identity"]["invocation_id"],
                "attempt": 1, "maximum_submissions": 2, "validation_error": failure_code,
                "output_schema_hash": packet["output_schema_hash"], "output_schema": schema,
                "validation_details": {"findings": findings},
                "instruction": "按当前语义草稿结构修订定位字段；必须保留研究原意并重新完整验证，不填写技术记录。",
            }
        except (OSError, ValueError, KeyError, TypeError, ImportError):
            return None

    if (failure_code.startswith("RESEARCH_SUBMISSION_RELATION_")
            or (failure_code.startswith("MULTIDIMENSIONAL_REFERENCE_UNKNOWN:")
                and (trusted_record or {}).get("submission_mode") in {
                    "research-object-submission/4.0.0", "research-object-submission/5.0.0", "research-object-submission/6.0.0"
                })):
        if (attempt != 1 or not trusted_record
                or (trusted_record.get("identity_binding") or {}).get("status") != "BOUND"
                or (trusted_record.get("submission_binding") or {}).get("version")
                not in {"research-object-submission/4.0.0", "research-object-submission/5.0.0", "research-object-submission/6.0.0"}):
            return None
        try:
            from product.runtime.multidimensional_references import load_reference_packet
            invocation = trusted_record["trusted_task_binding"]["invocation_id"]
            packet = load_reference_packet(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), invocation)
            task = packet["task"]
            if task.get("submission_version") not in {
                "research-object-submission/4.0.0", "research-object-submission/5.0.0", "research-object-submission/6.0.0"
            }:
                return None
            return {
                "repair_contract": "multidimensional-draft-repair/1.0.0",
                "task_id": task["task_id"], "invocation_id": invocation,
                "attempt": 1, "maximum_submissions": 2,
                "validation_error": failure_code,
                "output_schema_hash": packet["output_schema_hash"],
                "instruction": (
                    "这是唯一一次同会话纠正机会。按validation_error中的claim及引用位置检查v4草稿："
                    "每条claim只能写core_statement及research_relation_clauses，不同时写statement；"
                    "每个真实外部research_claim_ref须在同一claim有且仅有一条自行撰写的具体关系句。"
                    "无有据关系时删去该引用；不可借另一claim的解释或虚构关系。"
                    "再次提交完整草稿并原样返回新final_message；第二稿仍全量校验。"
                ),
            }
        except (OSError, ValueError, KeyError, TypeError):
            return None

    if failure_code == "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID":
        if attempt != 1 or not trusted_record or (trusted_record.get("identity_binding") or {}).get("status") != "BOUND":
            return None
        try:
            from product.runtime.multidimensional_references import load_reference_packet
            invocation = trusted_record["trusted_task_binding"]["invocation_id"]
            packet = load_reference_packet(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), invocation)
            task = packet["task"]
            if task.get("source_literal_selection") not in {
                _SOURCE_LITERAL_VERSION, _MACRO_SOURCE_LITERAL_VERSION,
            }:
                return None
            draft = _trusted_bound_output(payload, trusted_record)
            if draft["invocation_id"] != invocation:
                return None
            marker_findings = _source_literal_marker_findings(draft)
            return {
                "repair_contract": "multidimensional-draft-repair/1.0.0",
                "task_id": task["task_id"], "invocation_id": invocation,
                "attempt": 1, "maximum_submissions": 2,
                "validation_error": failure_code,
                "output_schema_hash": packet["output_schema_hash"],
                "validation_details": {"findings": marker_findings,
                                       "source_validation": "NOT_PROVEN_BY_MARKER_DIAGNOSTIC"},
                "instruction": (
                    "这是唯一一次同会话纠正机会。核对source_literal_selections中每个占位的"
                    "claim_id、已成功查询且在同一claim引用的evidence_ref、允许的field，"
                    "以及claim.statement中恰好一次的{{sf.key}}。只选真实来源字段；"
                    "validation_details列出所有可定位占位计数错误；逐项核对，不只处理第一处。"
                    + ("moomoo_macro_observation填同条原观察记录的全部角色/时间，不拼其它期、不自行换算；"
                       if task.get("source_literal_selection") == _MACRO_SOURCE_LITERAL_VERSION else
                       "sec_usd_value占位会填完整的原整数及USD，不要在占位后再手写USD；")
                    +
                    "不要猜测或手抄来源数值/时点。返回完整草稿，第二稿仍全量校验。"
                ),
            }
        except (OSError, ValueError, KeyError, TypeError):
            return None

    if failure_code in {"MARKET_BREADTH_VALUE_INVALID", "MARKET_BREADTH_REFERENCE_INVALID"}:
        if attempt != 1 or not trusted_record or (trusted_record.get("identity_binding") or {}).get("status") != "BOUND":
            return None
        try:
            from product.runtime.multidimensional_references import load_reference_packet, translate_references
            stage = _multidimensional_module()
            root = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
            invocation = trusted_record["trusted_task_binding"]["invocation_id"]
            packet = load_reference_packet(root, invocation)
            if packet["task"]["capability"] != "MARKET_STATE":
                return None
            expected = packet["prepared_analysis"]["breadth_report_calculation"]
            if expected["artifact_ref"] not in packet["task"]["allowed_artifact_refs"]:
                return None
            # Recheck the frozen receipt, not the erroneous draft, before offering it.
            stage.validate_breadth_calculation_references(root, {"calculations": [expected]})
            draft = json.loads(payload["last_assistant_message"])
            if draft.get("invocation_id") != invocation:
                return None
            mapping = packet.get("reference_map")
            resolved = translate_references(draft, mapping) if mapping else draft
            diagnostics = _multidimensional_draft_diagnostics(payload, environment, failure_code=failure_code)
            if diagnostics.get("status") == "UNAVAILABLE" or diagnostics.get("truncated") or any(
                f["code"] in {"DIMENSION_REPORT_DOCUMENT_NOT_ALLOWED", "EVIDENCE_CLOSURE_FAILED"}
                for f in diagnostics.get("findings", [])
            ):
                return None
            allowed_documents = {d["document_id"] for d in packet["task"].get("allowed_documents", [])}
            document_refs = {ref for c in resolved.get("claims", []) for ref in c.get("document_refs", [])}
            document_refs.update(r["document_id"] for r in resolved.get("research_relationships", []))
            if not document_refs.issubset(allowed_documents):
                return None
            refs = set(resolved.get("artifact_refs", [])) | {
                c["artifact_ref"] for c in resolved.get("calculations", [])}
            if not refs.issubset(set(packet["task"]["allowed_artifact_refs"])):
                return None
            findings = []
            for i, calculation in enumerate(resolved.get("calculations", [])):
                if calculation.get("artifact_ref") != expected["artifact_ref"]:
                    continue
                for field, value in expected.items():
                    equal = calculation.get(field) == value
                    if field == "value":
                        try:
                            counts = json.loads(calculation.get(field, ""))
                            equal = (isinstance(counts, dict) and all(type(v) is int for v in counts.values())
                                     and counts == json.loads(value))
                        except (TypeError, ValueError):
                            equal = False
                    if not equal:
                        findings.append({"code": failure_code, "path": f"calculations[{i}].{field}"})
            if not findings or len(findings) > 32:
                return None
            result = {
                "repair_contract": "multidimensional-draft-repair/1.0.0",
                "task_id": packet["task"]["task_id"], "invocation_id": invocation,
                "attempt": attempt, "maximum_submissions": 2, "validation_error": failure_code,
                "output_schema_hash": packet["output_schema_hash"],
                "validation_details": {"findings": findings,
                    "breadth_report_calculation": translate_references(expected, mapping, to_model=True) if mapping else expected},
                "instruction": "这是唯一一次纠正机会。按字段位置核对同任务breadth_report_calculation，返回完整草稿；同步核对claim的calculation_refs。保留研究内容，不删有据主张、不修改附件。程序不改稿，第二稿仍完整校验。",
            }
            return result if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= 16 * 1024 else None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    if failure_code == "RESEARCH_OUTPUT_JSON_INVALID":
        finding = _json_syntax_finding(payload.get("last_assistant_message"))
        if attempt != 1 or finding is None or not trusted_record:
            return None
        if (trusted_record.get("identity_binding") or {}).get("status") != "BOUND":
            return None
        binding = trusted_record.get("trusted_task_binding") or {}
        try:
            from product.runtime.multidimensional_references import load_reference_packet
            packet = load_reference_packet(
                Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), binding["invocation_id"],
            )
            task = packet["task"]
            if any(binding.get(key) != task.get(key) for key in (
                "run_id", "invocation_id", "task_id", "task_name", "agent",
            )) or payload.get("agent_type") != task["agent"]:
                return None
            result = {
                "repair_contract": "multidimensional-draft-repair/1.0.0",
                "task_id": task["task_id"], "invocation_id": task["invocation_id"],
                "attempt": attempt, "maximum_submissions": 2,
                "validation_error": failure_code,
                "output_schema_hash": packet["output_schema_hash"],
                "validation_details": {"findings": [finding]},
                "instruction": (
                    "这是唯一一次纠正机会，与其他纠错共享两次提交上限。"
                    "按解析器行列和字符 offset 检查原稿，返回完整合法 JSON 对象，不加代码围栏或说明文字。"
                    "错误位置是解析器发现问题的位置，不保证是根因位置；同时检查全稿语法。"
                    "保持原研究内容、合法引用和冻结身份，不删除有依据主张来过关。"
                    "Python 不自动修 JSON；第二稿仍经过全部身份、Schema、Evidence和引用校验。"
                ),
            }
            return result if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= 16 * 1024 else None
        except (OSError, ValueError, KeyError, TypeError, ImportError):
            return None

    condition_reference_error = failure_code == "DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING"
    ungrounded_claim_error = failure_code == "DIMENSION_REPORT_CLAIM_UNGROUNDED"
    evidence_closure_error = failure_code.startswith("EVIDENCE_CLOSURE_FAILED:")
    artifact_reference_error = failure_code == "MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID"
    monetary_reference_error = failure_code == "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED"
    source_identity_error = failure_code == "DIMENSION_REPORT_SOURCE_IDENTITY_IN_PROSE"
    internal_reference_error = failure_code == "DIMENSION_REPORT_INTERNAL_REFERENCE_DANGLING"
    research_reference_error = failure_code in {
        "DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING", "DIMENSION_REPORT_RELATIONSHIP_TARGET_DANGLING",
    }
    short_reference_error = failure_code.startswith("MULTIDIMENSIONAL_REFERENCE_UNKNOWN:")
    contract_metadata_error = failure_code in {
        "DIMENSION_REPORT_SOURCE_LIMITED_STATE_INVALID", "DIMENSION_REPORT_FAILED_EVALUATION_INVALID",
        "DIMENSION_REPORT_DOCUMENT_METADATA_DRIFT",
    }
    if attempt != 1 or not (
        condition_reference_error or ungrounded_claim_error or evidence_closure_error
        or artifact_reference_error or monetary_reference_error or source_identity_error or internal_reference_error or research_reference_error
        or short_reference_error or contract_metadata_error or failure_code.startswith((
            "DIMENSION_DRAFT_KEYS_INVALID",
            "DIMENSION_REPORT_SCHEMA_INVALID",
        ))
    ):
        return None
    message = payload.get("last_assistant_message")
    if not isinstance(message, str):
        return None
    try:
        draft = json.loads(message)
    except json.JSONDecodeError:
        return None
    if not isinstance(draft, Mapping):
        return None
    invocation_id = draft.get("invocation_id")
    if trusted_record is not None:
        trusted_id = (trusted_record.get("trusted_task_binding") or {}).get("invocation_id")
        if ((trusted_record.get("identity_binding") or {}).get("status") != "BOUND"
                or not trusted_id or invocation_id not in (None, trusted_id)):
            return None
        invocation_id = trusted_id
    matches = [
        item for item in _research_index(environment)["tasks"]
        if item.get("invocation_id") == invocation_id
    ]
    if len(matches) != 1:
        return None
    task = matches[0]
    initial_fundamental = (
        task.get("capability") == "FUNDAMENTAL_EVENT"
        and environment.get("STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT") == "1"
    )
    reference_details = None
    if condition_reference_error:
        if not (
            task.get("capability") == "RESEARCH_REPORT"
            or initial_fundamental
        ):
            return None
        claims = draft.get("claims")
        conditions = draft.get("observation_conditions")
        if not isinstance(claims, list) or not isinstance(conditions, list):
            return None
        valid_claim_ids = sorted({
            item["claim_id"] for item in claims
            if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)
        })
        dangling = [
            {"path": f"observation_conditions[{index}].claim_refs[{offset}]", "claim_id": ref}
            for index, condition in enumerate(conditions)
            if isinstance(condition, Mapping) and isinstance(condition.get("claim_refs"), list)
            for offset, ref in enumerate(condition["claim_refs"])
            if ref not in valid_claim_ids
        ]
        if not dangling:
            return None
        reference_details = {
            "dangling_references": dangling,
            "valid_claim_ids": valid_claim_ids,
        }
    if (
        (condition_reference_error and initial_fundamental)
        or ungrounded_claim_error or evidence_closure_error or artifact_reference_error
        or monetary_reference_error or source_identity_error or internal_reference_error or research_reference_error or short_reference_error or contract_metadata_error
    ):
        diagnostics = _multidimensional_draft_diagnostics(
            payload, environment, failure_code=failure_code, trusted_record=trusted_record,
        )
        if diagnostics.get("status") != "LOCATED" or diagnostics.get("truncated"):
            return None
        findings = diagnostics["findings"]
        if ungrounded_claim_error:
            ungrounded = [
                {"path": item["path"], "claim_id": item["identifier"]}
                for item in findings if item["code"] == failure_code and "identifier" in item
            ]
            if not ungrounded:
                return None
            reference_details = {"ungrounded_claims": ungrounded}
        if monetary_reference_error and not any(
            item["code"] == failure_code for item in findings
        ):
            return None
        if source_identity_error and not any(
            item["code"] == failure_code for item in findings
        ):
            return None
        if internal_reference_error and not any(
            item["code"] == failure_code for item in findings
        ):
            return None
        if contract_metadata_error and (
            not any(item["code"] == failure_code for item in findings)
            or any(item["code"] == "DIMENSION_REPORT_DOCUMENT_NOT_ALLOWED" for item in findings)
        ):
            return None
        if evidence_closure_error:
            reported = set(failure_code.partition(":")[2].split(","))
            located = {
                item.get("identifier") for item in findings
                if item["code"] == "EVIDENCE_CLOSURE_FAILED"
            }
            if not reported or reported != located:
                return None
        reference_details = {**(reference_details or {}), "findings": findings}
        if monetary_reference_error:
            reference_details["repeated_amount_context"] = _monetary_repetition_context(draft, findings)
        if any(item["code"] in {
            "DIMENSION_REPORT_SOURCE_LIMITED_STATE_INVALID", "DIMENSION_REPORT_FAILED_EVALUATION_INVALID",
            "DIMENSION_REPORT_DOCUMENT_METADATA_DRIFT",
        } for item in findings):
            from product.runtime.multidimensional_references import load_reference_packet
            checked_packet = load_reference_packet(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), invocation_id)
            reference_details["output_contract_rules"] = _multidimensional_module().OUTPUT_CONTRACT_RULES
            selected = {d.get("document_id") for d in draft.get("documents", []) if isinstance(d, Mapping)}
            reference_details["allowed_documents"] = [
                d for d in checked_packet["task"].get("allowed_documents", []) if d["document_id"] in selected
            ]
        if artifact_reference_error:
            reference_details["allowed_artifact_refs"] = task.get("allowed_artifact_refs", [])
        if internal_reference_error:
            reference_details["valid_internal_ids"] = {
                "assumption_ids": sorted(item["assumption_id"] for item in draft.get("assumptions", [])
                                         if isinstance(item, Mapping) and isinstance(item.get("assumption_id"), str)),
                "calculation_refs": sorted(item["calculation_id"] for item in draft.get("calculations", [])
                                           if isinstance(item, Mapping) and isinstance(item.get("calculation_id"), str)),
                "document_refs": sorted(item["document_id"] for item in draft.get("documents", [])
                                        if isinstance(item, Mapping) and isinstance(item.get("document_id"), str)),
            }
        if research_reference_error or short_reference_error or any(item["code"] in {
            "DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING", "DIMENSION_REPORT_RELATIONSHIP_TARGET_DANGLING",
        } for item in findings):
            from product.runtime.multidimensional_references import load_reference_packet
            reference_packet = load_reference_packet(
                Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), invocation_id,
            )
            reference_details["valid_local_claim_ids"] = [
                c["claim_id"] for c in draft.get("claims", [])
                if isinstance(c, Mapping) and isinstance(c.get("claim_id"), str)
            ]
            reference_details["valid_upstream_claims"] = [
                {"report_id": r["report_id"], "claim_id": c["claim_id"], "statement": c["statement"]}
                for r in reference_packet.get("dependency_reports", []) for c in r["claims"]
            ]
            from product.runtime.multidimensional_references import model_claim_targets
            reference_details["upstream_short_references"] = (
                model_claim_targets(reference_packet["reference_map"])
                if reference_packet.get("reference_map") is not None else {}
            )
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    packet = json.loads((run_dir / task["packet_path"]).read_text(encoding="utf-8"))
    output_schema = packet.get("output_schema")
    if (
        not isinstance(output_schema, Mapping)
        or packet.get("output_schema_hash") != _canonical_hash(output_schema)
    ):
        return None
    result = {
        "repair_contract": "multidimensional-draft-repair/1.0.0",
        "task_id": task["task_id"],
        "invocation_id": invocation_id,
        "attempt": attempt,
        "maximum_submissions": 2,
        "validation_error": failure_code,
        "output_schema_hash": packet["output_schema_hash"],
        "instruction": (
            "这是唯一一次纠正机会。由原 Agent 在当前会话内返回完整 JSON 草稿；"
            "逐项核对 validation_details.findings 的所有位置。非法 Evidence ID 必须用已授权只读工具"
            "重新查询并复制确实支持主张的合法引用（新协议为短引用，旧协议为完整原样 ID）；不得按前缀猜测、模糊匹配或虚构 ID。"
            "本地 claim 引用须指向草稿实际主张，上游引用须选已验证依赖中的真实主张（见 valid_upstream_claims）；"
            "短引用使用目录/工具给出的原值。其他已合法引用也须核对是否实际支持所在主张；"
            "不能仅因 ID 合法就保留无关引用。无依据 claim 只能依据真实允许的引用支撑，"
            "若仅陈述资料不足则保留在 data_gaps/limitations。保留有依据的实质主张和冻结身份；"
            "Python 不代写草稿，第二次提交仍经过完整校验。"
            "状态配对按 output_contract_rules 核对；由你按真实覆盖选择，不自动提升完成状态。"
            "文档字段漂移按 allowed_documents 中相同 document_id 的冻结记录核对，不推断新日期或改写来源。"
            if (
                condition_reference_error or ungrounded_claim_error or evidence_closure_error
                or artifact_reference_error or monetary_reference_error or source_identity_error or internal_reference_error or research_reference_error
                or short_reference_error or contract_metadata_error
            ) else
            "这是唯一一次纠正机会。由原 Agent 在当前会话内返回完整 JSON 草稿；"
            "按 validation_details 定位无依据 claim：只有经工具查询并确实支持主张的允许引用才能补入；"
            "若它仅陈述资料不足，应将该限制保留在 data_gaps/limitations，移去无依据 claim。"
            "不得虚构 Evidence、删除有依据的实质性主张或改变冻结身份；Python 不代写草稿。"
            if ungrounded_claim_error else
            "这是唯一一次纠正机会。由原 Agent 在当前会话内返回完整 JSON 草稿；"
            "先按 output_schema 复核整个草稿的必填字段和禁止字段，再修正 validation_error 指出的"
            "结构问题；不要只修第一个报错后留下其他非法字段。保留冻结身份、证据引用和其他研究内容。"
            "缺少 impact 等实质字段时，必须依据本次冻结资料自行填写，Python 或父线程不会代写。"
            "不得增加未获准 Evidence、改写身份或删除主张来规避校验。"
        ),
    }
    if reference_details and any(
        finding["code"] == "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED"
        for finding in reference_details.get("findings", [])
    ):
        result["instruction"] += (
            " 对定位到的金额单位换写，请由原 Agent 核对同源 Evidence 与已选上游计算："
            "有来源支持的原中文单位可原样表述；换算成 billion USD 必须有同主张、同来源的有效计算收据；"
            "否则将无法证实的换算保留为资料缺口。不得猜测、自动补算或删去有据事实。"
        )
    if source_identity_error:
        result["instruction"] += (
            " 行业主张不要手抄source_id=、as_of=或retrieved_at=；"
            "来源身份从所引evidence_refs追溯。请自行核对所选证券的实际业务原文，"
            "删除错误技术身份，并修正或降级没有对应原文支持的业务交集；Python不会代写。"
        )
    if internal_reference_error:
        result["instruction"] += (
            " 对定位到的内部引用，逐项核对valid_internal_ids中本稿真实assumption_id、"
            "calculation_id或document_id；由你决定保留正确关联或移去无依据引用。"
            "不得按名称猜测未在本稿存在的ID，Python不会替你选择计算或改写研究。"
        )
    if (initial_fundamental and not contract_metadata_error) or not (
        condition_reference_error or ungrounded_claim_error or evidence_closure_error
        or artifact_reference_error or monetary_reference_error or source_identity_error or internal_reference_error or research_reference_error
        or short_reference_error or contract_metadata_error
    ):
        result["original_draft"] = draft
        result["output_schema"] = output_schema
    if reference_details is not None:
        result["validation_details"] = reference_details
    if len(json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")) > (
        16 * 1024 if not ("original_draft" in result) else 256 * 1024
    ):
        return None
    return result


def _skeptic_repair_packet(payload, environment, *, failure_code: str, attempt: int):
    """只在第一次结构错误时请求同一 Agent 修正格式，不改写研究。"""

    if attempt != 1 or not failure_code.startswith(("SCHEMA_", "COUNTER_OUTPUT_JSON_INVALID")):
        return None
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        return None
    try:
        draft = json.loads(message)
    except json.JSONDecodeError:
        draft = None
    if not isinstance(draft, Mapping):
        return None
    matches = [
        item for item in _research_index(environment)["tasks"]
        if item["invocation_id"] == draft.get("invocation_id")
    ]
    if len(matches) != 1:
        return None
    task = matches[0]
    packet = _independent_skeptic_module().build_skeptic_dispatch_packet(
        Path(__file__).resolve().parents[2], Path(environment["STOCK_AGENT_RUN_DIR"]),
        task["task_name"], index_ref=environment.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"),
    )
    return {
        "repair_contract": "independent-skeptic-format-repair/1.0.0",
        "task_id": task["task_id"], "invocation_id": task["invocation_id"],
        "attempt": attempt, "maximum_submissions": 2,
        "validation_error": failure_code, "original_draft": draft,
        "output_schema": packet["output_schema"],
        "instruction": (
            "这是唯一一次格式修复机会。原 Agent 在当前会话返回完整 JSON；"
            "只修正字段、类型或 Schema 结构，不新增事实、Evidence、挑战、假设，"
            "不改变研究状态、身份或结论。若无法仅作格式修复，请保留失败。"
        ),
    }


def handle_hook_event(
    payload: Mapping[str, Any], *, environ: Mapping[str, str] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    environment = os.environ if environ is None else environ
    if payload.get("hook_event_name") == "PreToolUse":
        return _handle_pre_tool_use(payload, environment=environment)
    if payload.get("hook_event_name") == "Stop":
        return _handle_parent_stop(payload, environment=environment)
    log_path = _resolve_scoped_log(environment)
    expected = _expected_parallel_agents(environment)
    lock_path = log_path.with_suffix(log_path.suffix + ".lock")
    comparison_packet = None
    with lock_path.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        blocked_stop = False
        if payload.get("hook_event_name") == "SubagentStop" and expected:
            if _research_materials_stage(environment):
                required_tasks = _expected_research_tasks(environment)
                dispatch_log = _resolve_scoped_log(
                    environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG"
                )
                observed_tasks = _allowed_dispatch_tasks(
                    dispatch_log, parent_session_id=str(payload.get("session_id", ""))
                )
                initial_wave = min(_research_target_concurrency(environment), len(required_tasks))
                blocked_stop = len(observed_tasks) < initial_wave and payload.get("stop_hook_active") is not True
            elif not _research_stage(environment):
                started = _started_agents(
                    log_path,
                    parent_session_id=str(payload.get("session_id", "")),
                )
                blocked_stop = not expected <= started and payload.get("stop_hook_active") is not True
        record = minimize_hook_event(payload, blocked_stop=blocked_stop)
        response = {}
        if (
            payload.get("hook_event_name") == "SubagentStop"
            and not blocked_stop
            and _research_stage(environment)
        ):
            _bind_research_stop_identity(
                payload, record, log_path=log_path, environment=environment,
            )
            record.pop("event_hash")
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        if payload.get("hook_event_name") == "SubagentStart" and _common_stock_eval(environment):
            try:
                if payload["agent_type"] != "dev_eval":
                    raise ValueError("COMMON_STOCK_EVAL_START_AGENT_INVALID")
                expected_model = environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL")
                if not expected_model or payload.get("model") != expected_model:
                    raise ValueError("COMMON_STOCK_EVAL_START_MODEL_INVALID")
                module = _common_stock_eval_module()
                packet = module.build_common_stock_eval_packet(
                    Path(environment["STOCK_AGENT_RUN_DIR"]),
                    expected_model=expected_model,
                )
                manifest = packet["input_manifest"]
                record["context_binding"] = {
                    "status": "DELIVERED",
                    "eval_id": manifest["eval_id"],
                    "run_id": manifest["run_id"],
                    "invocation_id": manifest["invocation_id"],
                    "security_id": manifest["security_id"],
                    "input_hash": manifest["input_hash"],
                    "packet_hash": _canonical_hash(packet),
                }
                response = {
                    "hookSpecificOutput": {
                        "hookEventName": "SubagentStart",
                        "additionalContext": json.dumps(
                            packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        ),
                    }
                }
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                code = str(exc).split(":", 1)[0]
                record["context_binding"] = {"status": "FAILED", "failure_code": code}
                response = {
                    "hookSpecificOutput": {
                        "hookEventName": "SubagentStart",
                        "additionalContext": (
                            f"冻结 Eval 上下文交付失败：{code}。禁止评分或补充外部事实。"
                        ),
                    }
                }
            record.pop("event_hash")
            record["event_hash"] = _canonical_hash(record)
        if payload.get("hook_event_name") == "SubagentStart" and _research_stage(environment):
            try:
                task_name = _next_research_task(
                    log_path,
                    parent_session_id=payload["session_id"],
                    environment=environment,
                    agent_type=payload.get("agent_type"),
                )
                stage = _research_module(environment)
                build_packet = (
                    stage.build_skeptic_dispatch_packet
                    if _independent_skeptic_stage(environment)
                    else stage.build_research_materials_dispatch_packet
                    if _research_materials_stage(environment)
                    else stage.build_multidimensional_dispatch_packet
                    if _multidimensional_stage(environment)
                    else stage.build_common_stock_dispatch_packet
                )
                packet = (
                    build_packet(
                        Path(__file__).resolve().parents[2],
                        Path(environment["STOCK_AGENT_RUN_DIR"]), task_name,
                        index_ref=environment.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"),
                    ) if _independent_skeptic_stage(environment) else build_packet(
                        Path(__file__).resolve().parents[2],
                        Path(environment["STOCK_AGENT_RUN_DIR"]), task_name,
                    )
                )
                if payload["agent_type"] != packet["identity"]["agent"]:
                    raise ValueError("RESEARCH_START_AGENT_INVALID")
                comparison_packet = packet
                if _multidimensional_stage(environment) and not _independent_skeptic_stage(environment):
                    from product.runtime.calculation_handoff import require_current_selection_transport
                    task = next(item for item in _research_index(environment)["tasks"]
                                if item["invocation_id"] == packet["identity"]["invocation_id"])
                    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
                    invocation = json.loads((run_dir / task["invocation_path"]).read_text(encoding="utf-8"))
                    require_current_selection_transport(packet, invocation, indexed_task=task)
                record["context_binding"] = {
                    "status": "DELIVERED",
                    "task_name": task_name,
                    "run_id": packet["identity"]["run_id"],
                    "invocation_id": packet["identity"]["invocation_id"],
                    "security_id": packet["identity"].get("security_id"),
                    "security_ids": packet["identity"].get("security_ids"),
                    "packet_hash": _canonical_hash(packet),
                }
                context = (
                    stage.serialize_common_stock_dispatch_context(packet)
                    if _common_stock_stage(environment)
                    else stage.serialize_multidimensional_initial_context(packet)
                    if (_multidimensional_stage(environment)
                        and environment.get("STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT") == "1")
                    else stage.serialize_multidimensional_model_context(packet)
                    if _multidimensional_stage(environment)
                    else stage.serialize_research_materials_dispatch_context(packet)
                    if _research_materials_stage(environment)
                    else json.dumps(
                        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    )
                )
                if (_common_stock_stage(environment) or _independent_skeptic_stage(environment)) and packet.get("reference_map") is not None:
                    record["context_binding"].update(
                        reference_map_hash=packet["reference_map"]["map_hash"],
                        model_context_sha256=hashlib.sha256(context.encode("utf-8")).hexdigest(),
                        model_context_bytes=len(context.encode("utf-8")),
                    )
                if _multidimensional_stage(environment):
                    old_context = json.dumps(
                        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    )
                    record["context_binding"]["delivery_diagnostics"] = {
                        "schema_version": "research-input-delivery-diagnostics/1.0.0",
                        "model_context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
                        "model_context_bytes": len(context.encode("utf-8")),
                        "full_packet_bytes": len(old_context.encode("utf-8")),
                        "evidence_catalog_rows": len(packet.get("evidence_catalog", [])),
                        "dependency_report_count": len(packet.get("dependency_reports", [])),
                        "token_count_status": "NOT_OBSERVED",
                    }
                response = {
                    "hookSpecificOutput": {
                        "hookEventName": "SubagentStart",
                        "additionalContext": context,
                    }
                }
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                code = str(exc).split(":", 1)[0]
                record["context_binding"] = {"status": "FAILED", "failure_code": code}
                response = {
                    "hookSpecificOutput": {
                        "hookEventName": "SubagentStart",
                        "additionalContext": (
                            f"冻结上下文交付失败：{code}。禁止研究、猜测绑定或输出报告。"
                        ),
                    }
                }
            record.pop("event_hash")
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        if payload.get("hook_event_name") == "SubagentStart" and environment.get("STOCK_AGENT_START_CONTEXT"):
            try:
                invocation = _invocation_module()
                if environment["STOCK_AGENT_START_CONTEXT"] not in (invocation.START_CONTEXT_VERSION, invocation.LEGACY_START_CONTEXT_VERSION):
                    raise ValueError("START_CONTEXT_VERSION_INVALID")
                if payload["agent_type"] not in expected:
                    raise ValueError("START_CONTEXT_AGENT_INVALID")
                if payload["agent_type"] in _started_agents(log_path, parent_session_id=payload["session_id"]):
                    raise ValueError("START_CONTEXT_DUPLICATE_AGENT")
                context, binding = invocation.build_specialist_start_context(
                    Path(__file__).resolve().parents[2], Path(environment["STOCK_AGENT_RUN_DIR"]), payload["agent_type"])
                comparison_packet = json.loads(invocation.build_specialist_dispatch_message(
                    Path(__file__).resolve().parents[2], Path(environment["STOCK_AGENT_RUN_DIR"]), payload["agent_type"]))
                if payload["model"] != binding["model"]:
                    raise ValueError("START_CONTEXT_MODEL_MISMATCH")
                record["context_binding"] = binding
                response = {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": context}}
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                code = str(exc) if str(exc).startswith("START_CONTEXT_") else "START_CONTEXT_SOURCE_INVALID"
                record["context_binding"] = {"status": "FAILED", "failure_code": code}
                response = {"hookSpecificOutput": {"hookEventName": "SubagentStart",
                    "additionalContext": f"冻结上下文交付失败：{code}。禁止研究、猜测参数或生成建议，向父线程报告失败。"}}
            record.pop("event_hash")
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        if (payload.get("hook_event_name") == "SubagentStop" and not blocked_stop
                and environment.get("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT") in {"native-final-json/1.0.0", "native-research-draft/1.0.0"}):
            try:
                _capture_specialist_report(payload, record, environment)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                record["output_capture"] = {"status": "FAILED", "failure_code": str(exc)}
            record.pop("event_hash")
            record["event_hash"] = _canonical_hash(record)
        if (
            payload.get("hook_event_name") == "SubagentStop"
            and not blocked_stop
            and _common_stock_stage(environment)
        ):
            try:
                _capture_common_stock_report(payload, record, environment)
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                record["output_capture"] = {"status": "FAILED", "failure_code": str(exc)}
                try:
                    record["output_capture"].update(
                        _persist_rejected_common_stock_output(payload, environment)
                    )
                except OSError:
                    record["output_capture"]["rejected_persistence"] = "FAILED"
            record.pop("event_hash")
            record["event_hash"] = _canonical_hash(record)
        if (
            payload.get("hook_event_name") == "SubagentStop"
            and not blocked_stop
            and _multidimensional_stage(environment)
        ):
            attempt = _multidimensional_output_attempt(log_path, payload)
            raw_capture: dict[str, Any] = {}
            capture_payload = payload
            record["local_revision_authorized"] = False
            try:
                _resolve_local_revision(log_path, payload, record, environment, attempt, authorize_only=True)
                record["local_revision_authorized"] = True
                raw_capture = _persist_multidimensional_raw_output(
                    payload, environment, attempt=attempt
                )
                capture_payload = _resolve_local_revision(log_path, payload, record, environment, attempt)
                from product.runtime.research_submission import resolve
                capture_payload = resolve(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), capture_payload, record, attempt,
                                          for_execution=True)
                _capture_multidimensional_report(capture_payload, record, environment)
                record["output_capture"].update(
                    {"attempt": attempt, "repair_state": (
                        "REPAIRED" if attempt == 2 else "NOT_REQUIRED"
                    ), **raw_capture}
                )
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                failure_code = str(exc)
                repair = _multidimensional_repair_packet(
                    capture_payload, environment,
                    failure_code=failure_code,
                    attempt=attempt,
                    trusted_record=record,
                )
                try:
                    repair = _bind_local_revision(repair, capture_payload, record, raw_capture, environment)
                except (OSError, ValueError, KeyError, TypeError, ImportError) as binding_error:
                    record["repair_binding_error"] = str(binding_error)
                    repair = None
                from product.runtime.research_submission import BOUNDED_REVISION_VERSION
                if repair is not None and record.get("submission_mode") and record["submission_mode"] != BOUNDED_REVISION_VERSION:
                    repair["instruction"] += (
                        " 本任务是结构化提交模式：修正研究对象后再次调用research_report_submit，"
                        "draft省略技术身份，最终仅返回新final_message回执，不输出整稿。"
                    )
                    if len(json.dumps(repair, ensure_ascii=False).encode("utf-8")) > 16 * 1024:
                        repair = None
                record["output_capture"] = {
                    "status": "FAILED",
                    "failure_code": failure_code,
                    "attempt": attempt,
                    "repair_state": (
                        "REPAIR_REQUESTED" if repair is not None
                        else "EXHAUSTED" if (attempt >= 2 or (record.get("submission_mode") == BOUNDED_REVISION_VERSION
                            and record.get("submission_binding", {}).get("submission", 0) >= 2))
                        else "NOT_ALLOWED"
                    ),
                    **raw_capture,
                }
                if failure_code.startswith((
                    "RESEARCH_OUTPUT_JSON_INVALID",
                    "EVIDENCE_CLOSURE_FAILED:", "DIMENSION_REPORT_CLAIM_UNGROUNDED",
                    "MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID",
                    "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                    "DIMENSION_REPORT_SOURCE_IDENTITY_IN_PROSE",
                    "DIMENSION_REPORT_INTERNAL_REFERENCE_DANGLING",
                    "DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING", "DIMENSION_REPORT_RELATIONSHIP_TARGET_DANGLING",
                    "MULTIDIMENSIONAL_REFERENCE_UNKNOWN:",
                )) or environment.get("STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT") == "1":
                    record["output_capture"]["diagnostics"] = _multidimensional_draft_diagnostics(
                        capture_payload, environment, failure_code=failure_code,
                        trusted_record=record,
                    )
                if repair is not None:
                    record["hook_event_name"] = "SubagentStopBlocked"
                    record["repair_request"] = {
                        key: repair[key] for key in (
                            "repair_contract", "task_id", "invocation_id", "attempt",
                            "maximum_submissions", "validation_error", "output_schema_hash",
                        )
                    }
                    record["repair_request"].update({key: repair[key] for key in (
                        "base_draft_ref", "allowed_paths", "binding_path", "binding_hash", "transport") if key in repair})
                    response = {
                        "decision": "block",
                        "reason": json.dumps(
                            _repair_model_view(repair), ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        ),
                    }
            record.pop("event_hash")
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        if (
            payload.get("hook_event_name") == "SubagentStop"
            and not blocked_stop
            and _research_materials_stage(environment)
        ):
            repair_response = _capture_revisable_research_output(
                payload, record, environment, log_path, _capture_research_material_preparation,
            )
            if repair_response is not None:
                response = repair_response
            record.pop("event_hash")
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        if (
            payload.get("hook_event_name") == "SubagentStop"
            and not blocked_stop
            and _independent_skeptic_stage(environment)
        ):
            attempt = _multidimensional_output_attempt(log_path, payload)
            raw_capture: dict[str, Any] = {}
            try:
                raw_capture = _persist_multidimensional_raw_output(
                    payload, environment, attempt=attempt,
                )
                index = _research_index(environment)
                binding = record.get("output_binding") or {}
                matches = [
                    item for item in index["tasks"]
                    if item["invocation_id"] == binding.get("invocation_id")
                ]
                if len(matches) != 1 or payload.get("agent_type") != "runtime_skeptic":
                    raise ValueError("COUNTER_OUTPUT_INVOCATION_UNKNOWN")
                record["output_capture"] = _independent_skeptic_module().capture_skeptic_report(
                    Path(__file__).resolve().parents[2],
                    Path(environment["STOCK_AGENT_RUN_DIR"]),
                    task_name=matches[0]["task_name"],
                    raw_message=json.dumps(
                        _trusted_bound_output(payload, record),
                        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                    ),
                    model=payload["model"],
                    index_ref=environment.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"),
                )
                record["output_capture"].update({
                    "attempt": attempt,
                    "repair_state": "REPAIRED" if attempt == 2 else "NOT_REQUIRED",
                    **raw_capture,
                })
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                failure_code = str(exc).split(":", 1)[0]
                repair = _skeptic_repair_packet(
                    payload, environment, failure_code=failure_code, attempt=attempt,
                )
                record["output_capture"] = {
                    "status": "FAILED", "failure_code": failure_code,
                    "attempt": attempt,
                    "repair_state": "REPAIR_REQUESTED" if repair else "EXHAUSTED",
                    **raw_capture,
                }
                if repair is not None:
                    record["hook_event_name"] = "SubagentStopBlocked"
                    record["repair_request"] = {
                        key: repair[key] for key in (
                            "repair_contract", "task_id", "invocation_id", "attempt",
                            "maximum_submissions", "validation_error",
                        )
                    }
                    response = {
                        "decision": "block",
                        "reason": json.dumps(repair, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    }
            record.pop("event_hash")
            record["event_hash"] = _canonical_hash(record)
        if (
            payload.get("hook_event_name") == "SubagentStop"
            and not blocked_stop
            and _common_stock_eval(environment)
        ):
            try:
                _capture_common_stock_eval_result(payload, record, environment)
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                record["output_capture"] = {
                    "status": "FAILED", "failure_code": str(exc)
                }
                try:
                    record["output_capture"].update(
                        _persist_rejected_common_stock_eval_output(payload, environment)
                    )
                except OSError:
                    record["output_capture"]["rejected_persistence"] = "FAILED"
            record.pop("event_hash")
            record["event_hash"] = _canonical_hash(record)
        delivered = response.get("hookSpecificOutput", {}).get("additionalContext")
        if (payload.get("hook_event_name") == "SubagentStart"
                and isinstance(delivered, str)
                and record.get("context_binding", {}).get("status") in {"DELIVERED", "EMITTED"}):
            raw_context = delivered.encode("utf-8")
            baseline = (json.dumps(comparison_packet, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")
                        if comparison_packet is not None else None)
            record["delivery_diagnostics"] = {
                "schema_version": "research-input-delivery-diagnostics/1.0.0",
                "scope": "SUBAGENT_START_ADDITIONAL_CONTEXT_ONLY",
                "model_context_bytes": len(raw_context),
                "model_context_sha256": hashlib.sha256(raw_context).hexdigest(),
                "comparison_status": "SAME_FROZEN_PACKET" if baseline is not None else "NOT_COMPARABLE",
                "baseline_kind": "FULL_FROZEN_PACKET_NOT_HISTORICAL_MODEL_RUN" if baseline is not None else None,
                "full_packet_bytes": len(baseline) if baseline is not None else None,
                "full_packet_sha256": hashlib.sha256(baseline).hexdigest() if baseline is not None else None,
                "byte_delta": len(raw_context) - len(baseline) if baseline is not None else None,
                "token_count_status": "NOT_OBSERVED",
                "model_usage_status": "NOT_OBSERVED",
            }
            record.pop("event_hash")
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        _append_record(log_path, record)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    if blocked_stop:
        if _research_stage(environment):
            dispatch_log = _resolve_scoped_log(
                environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG"
            )
            missing = sorted(_expected_research_tasks(environment) - _allowed_dispatch_tasks(
                dispatch_log, parent_session_id=str(payload.get("session_id", ""))
            ))
        else:
            missing = sorted(expected - _started_agents(
                log_path,
                parent_session_id=str(payload.get("session_id", "")),
            ))
        return record, {
            "decision": "block",
            "reason": (
                "并行派发屏障：以下 Specialist 尚未启动，当前 Agent 不得先结束："
                + ",".join(missing)
            ),
        }
    return record, response


def record_hook_event(
    payload: Mapping[str, Any], *, environ: Mapping[str, str] | None = None
) -> dict[str, Any]:
    record, _ = handle_hook_event(payload, environ=environ)
    return record


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, Mapping):
            raise ValueError("HOOK_INPUT_NOT_OBJECT")
        _, response = handle_hook_event(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    # SubagentStop requires JSON stdout on a successful command hook.  An empty
    # object is advisory and adds no model-visible context.
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
