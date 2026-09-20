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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


RECORDER_VERSION = "codex-subagent-hook-recorder/1.16.0"
SUPPORTED_EVENTS = {"SubagentStart", "SubagentStop"}
COMMON_STOCK_STAGE_VERSION = "common-stock-research-runtime/1.0.0"
MULTIDIMENSIONAL_STAGE_VERSION = "multidimensional-holding-research-runtime/2.0.0"
RESEARCH_MATERIALS_STAGE_VERSION = "multidimensional-material-preparation-runtime/1.1.0"
COMMON_STOCK_EVAL_VERSION = "common-stock-research-eval-runtime/1.0.0"


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
    record["event_hash"] = _canonical_hash(record)
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


def _research_stage(environment: Mapping[str, str]) -> bool:
    return (
        _common_stock_stage(environment)
        or _multidimensional_stage(environment)
        or _research_materials_stage(environment)
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


def _research_module(environment: Mapping[str, str]):
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
    value = json.loads((run_dir / "research/dispatch-index.json").read_text(encoding="utf-8"))
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
            stage.build_research_materials_dispatch_packet
            if _research_materials_stage(environment)
            else stage.build_multidimensional_dispatch_packet
            if _multidimensional_stage(environment)
            else stage.build_common_stock_dispatch_packet
        )
        if _multidimensional_stage(environment) or _research_materials_stage(environment):
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
            name for name in ("followuptask", "interruptagent", "listagents")
            if tool_name.endswith(name)
        ),
        None,
    )
    research_wait = tool_name.endswith("waitagent")
    if _research_stage(environment) and (research_control is not None or research_wait):
        parent_session_id = str(payload.get("session_id", ""))
        event_log = _resolve_scoped_log(environment)
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
            record["event_hash"] = _canonical_hash(record)
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
    record["event_hash"] = _canonical_hash(record)
    return record


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


def _read_jsonl_records(log_path: Path) -> list[dict[str, Any]]:
    """Read one append-only Hook log while excluding a concurrent writer."""

    lock_path = log_path.with_suffix(log_path.suffix + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        lines = log_path.read_text(encoding="utf-8").splitlines() if log_path.is_file() else []
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
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
    events = _read_jsonl_records(event_log)
    starts: dict[str, tuple[str, str]] = {}
    for item in events:
        binding = item.get("context_binding")
        task_name = binding.get("task_name") if isinstance(binding, Mapping) else None
        invocation_id = binding.get("invocation_id") if isinstance(binding, Mapping) else None
        child_id = item.get("child_session_id")
        if (
            item.get("hook_event_name") == "SubagentStart"
            and item.get("parent_session_id") == parent_session_id
            and item.get("agent_type") == "runtime_company_analyst"
            and isinstance(child_id, str)
            and task_name in tasks
            and binding.get("status") == "DELIVERED"
            and invocation_id == tasks[task_name]["invocation_id"]
        ):
            starts[child_id] = (task_name, invocation_id)

    completed: set[str] = set()
    for item in events:
        child_id = item.get("child_session_id")
        start = starts.get(child_id) if isinstance(child_id, str) else None
        binding = item.get("output_binding")
        if (
            item.get("hook_event_name") == "SubagentStop"
            and item.get("parent_session_id") == parent_session_id
            and item.get("agent_type") == "runtime_company_analyst"
            and start is not None
            and isinstance(binding, Mapping)
            and binding.get("agent") == "runtime_company_analyst"
            and binding.get("invocation_id") == start[1]
            and start[0] in allowed
        ):
            completed.add(start[0])

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
    record["event_hash"] = _canonical_hash(record)
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
    """将已结束子会话按其结构化 Invocation 绑定回任务。"""

    if not log_path.is_file():
        return set()
    by_invocation = {
        item["invocation_id"]: item["task_name"]
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
        binding = item.get("output_binding") or {}
        invocation_id = binding.get("invocation_id") if isinstance(binding, Mapping) else None
        if (
            item.get("hook_event_name") == "SubagentStop"
            and item.get("parent_session_id") == parent_session_id
            and invocation_id in by_invocation
        ):
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
    value = json.loads(payload["last_assistant_message"])
    if (
        not isinstance(value, dict)
        or value.get("agent") != "runtime_company_analyst"
        or value.get("run_id") is None
        or value.get("invocation_id") is None
    ):
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


def _capture_multidimensional_report(payload, record, environment):
    """保存多维研究草案并添加冻结绑定；不修复主张、引用或状态。"""

    stage = _multidimensional_module()
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    value = json.loads(payload["last_assistant_message"])
    if (
        not isinstance(value, dict)
        or value.get("run_id") is None
        or value.get("invocation_id") is None
        or value.get("agent") != payload.get("agent_type")
    ):
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_BINDING_INVALID")
    index = _research_index(environment)
    matches = [item for item in index["tasks"] if item["invocation_id"] == value["invocation_id"]]
    if len(matches) != 1 or value["run_id"] != index["run_id"]:
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_INVOCATION_UNKNOWN")
    task = matches[0]
    invocation = json.loads((run_dir / task["invocation_path"]).read_text(encoding="utf-8"))
    if payload.get("model") != invocation.get("model") or payload.get("agent_type") != task["agent"]:
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_AGENT_OR_MODEL_INVALID")
    artifact_refs = value.get("artifact_refs")
    if (
        not isinstance(artifact_refs, list)
        or not set(artifact_refs) <= set(task.get("allowed_artifact_refs", []))
    ):
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID")
    handoff = json.loads((run_dir / "audit/portfolio-handoff.json").read_text(encoding="utf-8"))
    council_request = json.loads((run_dir / "council-request.json").read_text(encoding="utf-8"))
    gate = json.loads((run_dir / "evidence/gate.json").read_text(encoding="utf-8"))
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
        dependency_claim_ids.extend(
            claim["claim_id"] for claim in dependency_matches[0].get("claims", [])
        )
    report = __import__(
        "product.council.multidimensional_research", fromlist=["envelope_research_dimension_draft"]
    ).envelope_research_dimension_draft(
        value, task=task, invocation=invocation, expected_bindings=bindings,
        allowed_security_ids=[
            item["security_id"] for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "COMMON_STOCK"
        ],
        allowed_evidence_ids=task["allowed_evidence_ids"],
        known_research_claim_ids=dependency_claim_ids,
        allowed_documents=task.get("allowed_documents", []),
    )
    evidence = [
        item for item in gate["allowed_evidence"]
        if item["evidence_id"] in set(task["allowed_evidence_ids"])
    ]
    output_dir = run_dir / "research/reports" / _canonical_hash({"task_id": task["task_id"]})[:16]
    output = __import__(
        "product.council.multidimensional_output", fromlist=["persist_dimension_report"]
    ).persist_dimension_report(output_dir, report=report, evidence=evidence)
    record["output_capture"] = {
        "version": "native-research-dimension-draft/1.0.0", "status": "SAVED",
        "path": str(Path(output["json"]).relative_to(run_dir)),
        "markdown_path": str(Path(output["markdown"]).relative_to(run_dir)),
        "output_hash": output["json_hash"], "task_id": task["task_id"],
        "security_ids": task["security_ids"],
    }


def _capture_research_material_preparation(payload, record, environment):
    """保存资料准备结果；候选/正文引用必须来自本 Invocation 实际产物。"""

    stage = _research_materials_module()
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    value = json.loads(payload["last_assistant_message"])
    if not isinstance(value, Mapping):
        raise ValueError("RESEARCH_MATERIALS_OUTPUT_NOT_OBJECT")
    index = _research_index(environment)
    matches = [item for item in index["tasks"] if item.get("invocation_id") == value.get("invocation_id")]
    if len(matches) != 1 or value.get("run_id") != index.get("run_id"):
        raise ValueError("RESEARCH_MATERIALS_OUTPUT_INVOCATION_UNKNOWN")
    task = matches[0]
    invocation = json.loads((run_dir / task["invocation_path"]).read_text(encoding="utf-8"))
    if payload.get("agent_type") != task["agent"] or payload.get("model") != invocation.get("model"):
        raise ValueError("RESEARCH_MATERIALS_OUTPUT_AGENT_OR_MODEL_INVALID")
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
    record["output_capture"] = {
        "version": "research-material-preparation-result/1.0.0", "status": "SAVED",
        "path": str(path.relative_to(run_dir)), "output_hash": _canonical_hash(value),
        "task_id": task["task_id"], "security_id": task["security_id"],
        "preparation_kind": task["preparation_kind"],
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
        ):
            previous = max(previous, int(capture["attempt"]))
    return previous + 1


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


def _multidimensional_repair_packet(
    payload: Mapping[str, Any], environment: Mapping[str, str], *,
    failure_code: str, attempt: int,
) -> dict[str, Any] | None:
    """Build one model-visible repair request for structural draft errors only."""

    if attempt != 1 or not failure_code.startswith((
        "DIMENSION_DRAFT_KEYS_INVALID",
        "DIMENSION_REPORT_SCHEMA_INVALID",
    )):
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
    matches = [
        item for item in _research_index(environment)["tasks"]
        if item.get("invocation_id") == invocation_id
    ]
    if len(matches) != 1:
        return None
    task = matches[0]
    run_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    packet = json.loads((run_dir / task["packet_path"]).read_text(encoding="utf-8"))
    output_schema = packet.get("output_schema")
    if (
        not isinstance(output_schema, Mapping)
        or packet.get("output_schema_hash") != _canonical_hash(output_schema)
    ):
        return None
    return {
        "repair_contract": "multidimensional-draft-repair/1.0.0",
        "task_id": task["task_id"],
        "invocation_id": invocation_id,
        "attempt": attempt,
        "maximum_submissions": 2,
        "validation_error": failure_code,
        "original_draft": draft,
        "output_schema": output_schema,
        "output_schema_hash": packet["output_schema_hash"],
        "instruction": (
            "这是唯一一次纠正机会。由原 Agent 在当前会话内返回完整 JSON 草稿；"
            "只修正 validation_error 指出的结构问题，保留冻结身份、证据引用和其他研究内容。"
            "缺少 impact 等实质字段时，必须依据本次冻结资料自行填写，Python 或父线程不会代写。"
            "不得增加未获准 Evidence、改写身份或删除主张来规避校验。"
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
    with lock_path.open("a", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        blocked_stop = False
        if payload.get("hook_event_name") == "SubagentStop" and expected:
            if _research_stage(environment):
                required_tasks = _expected_research_tasks(environment)
                dispatch_log = _resolve_scoped_log(
                    environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG"
                )
                observed_tasks = _allowed_dispatch_tasks(
                    dispatch_log, parent_session_id=str(payload.get("session_id", ""))
                )
                initial_wave = min(_research_target_concurrency(environment), len(required_tasks))
                blocked_stop = len(observed_tasks) < initial_wave and payload.get("stop_hook_active") is not True
            else:
                started = _started_agents(
                    log_path,
                    parent_session_id=str(payload.get("session_id", "")),
                )
                blocked_stop = not expected <= started and payload.get("stop_hook_active") is not True
        record = minimize_hook_event(payload, blocked_stop=blocked_stop)
        response = {}
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
                    stage.build_research_materials_dispatch_packet
                    if _research_materials_stage(environment)
                    else stage.build_multidimensional_dispatch_packet
                    if _multidimensional_stage(environment)
                    else stage.build_common_stock_dispatch_packet
                )
                packet = build_packet(
                    Path(__file__).resolve().parents[2],
                    Path(environment["STOCK_AGENT_RUN_DIR"]),
                    task_name,
                )
                if payload["agent_type"] != packet["identity"]["agent"]:
                    raise ValueError("RESEARCH_START_AGENT_INVALID")
                record["context_binding"] = {
                    "status": "DELIVERED",
                    "task_name": task_name,
                    "run_id": packet["identity"]["run_id"],
                    "invocation_id": packet["identity"]["invocation_id"],
                    "security_id": packet["identity"].get("security_id"),
                    "security_ids": packet["identity"].get("security_ids"),
                    "packet_hash": _canonical_hash(packet),
                }
                response = {
                    "hookSpecificOutput": {
                        "hookEventName": "SubagentStart",
                        "additionalContext": (
                            stage.serialize_common_stock_dispatch_context(packet)
                            if _common_stock_stage(environment)
                            else json.dumps(
                                packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                            )
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
                            f"冻结上下文交付失败：{code}。禁止研究、猜测绑定或输出报告。"
                        ),
                    }
                }
            record.pop("event_hash")
            record["event_hash"] = _canonical_hash(record)
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
            record["event_hash"] = _canonical_hash(record)
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
            try:
                raw_capture = _persist_multidimensional_raw_output(
                    payload, environment, attempt=attempt
                )
                _capture_multidimensional_report(payload, record, environment)
                record["output_capture"].update(
                    {"attempt": attempt, "repair_state": (
                        "REPAIRED" if attempt == 2 else "NOT_REQUIRED"
                    ), **raw_capture}
                )
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                failure_code = str(exc)
                repair = _multidimensional_repair_packet(
                    payload, environment,
                    failure_code=failure_code,
                    attempt=attempt,
                )
                record["output_capture"] = {
                    "status": "FAILED",
                    "failure_code": failure_code,
                    "attempt": attempt,
                    "repair_state": (
                        "REPAIR_REQUESTED" if repair is not None
                        else "EXHAUSTED" if attempt >= 2
                        else "NOT_ALLOWED"
                    ),
                    **raw_capture,
                }
                if repair is not None:
                    record["hook_event_name"] = "SubagentStopBlocked"
                    record["repair_request"] = {
                        key: repair[key] for key in (
                            "repair_contract", "task_id", "invocation_id", "attempt",
                            "maximum_submissions", "validation_error", "output_schema_hash",
                        )
                    }
                    response = {
                        "decision": "block",
                        "reason": json.dumps(
                            repair, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                        ),
                    }
            record.pop("event_hash")
            record["event_hash"] = _canonical_hash(record)
        if (
            payload.get("hook_event_name") == "SubagentStop"
            and not blocked_stop
            and _research_materials_stage(environment)
        ):
            try:
                _capture_research_material_preparation(payload, record, environment)
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                record["output_capture"] = {"status": "FAILED", "failure_code": str(exc)}
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
