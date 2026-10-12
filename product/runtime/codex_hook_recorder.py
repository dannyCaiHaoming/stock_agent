"""显式 dev_eval 维护的最小 Hook；正常研究控制已退役。

只保留冻结评分输入、可信派发/Start绑定、原稿保存和一次局部修订。
历史事件的纯投影可独立读取；不派发研究、不处理父Stop或CIO运行。
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

if __package__:
    from .hashing import canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError
else:
    from hashing import canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError

RECORDER_VERSION = "codex-subagent-hook-recorder/1.19.1"
SUPPORTED_EVENTS = {"SubagentStart", "SubagentStop"}
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


def _common_stock_eval_module():
    if __package__:
        from . import common_stock_eval
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from product.runtime import common_stock_eval
    return common_stock_eval


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


def _common_stock_eval_stop_packet(payload, environment):
    """从真实 Start 取得评分输入；修订前后均重验，不信任作者回填身份。"""
    module = _common_stock_eval_module()
    eval_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    if payload.get("agent_type") != "dev_eval":
        raise ValueError("COMMON_STOCK_EVAL_AGENT_INVALID")
    expected_model = environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL")
    if not expected_model or payload.get("model") != expected_model:
        raise ValueError("COMMON_STOCK_EVAL_MODEL_INVALID")
    packet = module.build_common_stock_eval_packet(eval_dir, expected_model=expected_model)
    log_path = _resolve_scoped_log(environment)
    starts = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    starts = [event for event in starts if event.get("hook_event_name") == "SubagentStart"
              and event.get("parent_session_id") == payload.get("session_id")
              and event.get("child_session_id") == payload.get("agent_id")]
    if len(starts) == 1:
        try:
            verify_legacy_envelope_hash(starts[0], hash_field="event_hash", location="events/subagents:dev_eval:SubagentStart")
        except HashContractError as exc:
            raise ValueError(f"COMMON_STOCK_EVAL_START_BINDING_INVALID:{exc}") from exc
    if (len(starts) != 1 or starts[0].get("agent_type") != "dev_eval"
            or starts[0].get("model") != expected_model
            or starts[0].get("context_binding", {}).get("packet_hash") != _canonical_hash(packet)
            or starts[0].get("context_binding", {}).get("model_packet_hash") != _canonical_hash(module.common_stock_eval_model_packet(packet))
            or starts[0].get("context_binding", {}).get("input_hash") != packet["input_manifest"]["input_hash"]):
        raise ValueError("COMMON_STOCK_EVAL_START_BINDING_INVALID")
    return packet


def _bind_common_stock_eval_stop_identity(payload, record, environment):
    packet = _common_stock_eval_stop_packet(payload, environment)
    log = _resolve_scoped_log(environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG")
    dispatches = [item for item in _read_jsonl_records_unlocked(log)
                  if item.get("decision") == "ALLOW" and item.get("agent_type") == "dev_eval"
                  and item.get("parent_session_id") == payload["session_id"]
                  and item.get("task_name") == "grade_common_stock_report" and item.get("fork_turns") == "none"
                  and item.get("dispatch_binding", {}).get("matched") is True]
    if len(dispatches) != 1:
        raise ValueError("COMMON_STOCK_EVAL_DISPATCH_BINDING_INVALID")
    dispatch = dispatches[0]
    try:
        verify_legacy_envelope_hash(dispatch, hash_field="event_hash", location="events/subagents:dev_eval:dispatch")
    except HashContractError as exc:
        raise ValueError(f"COMMON_STOCK_EVAL_DISPATCH_BINDING_INVALID:{exc}") from exc
    if (dispatch["dispatch_binding"].get("contract_version") != packet["runtime_contract"]
            or dispatch["dispatch_binding"].get("packet_hash") != _canonical_hash(packet)
            or dispatch["dispatch_binding"].get("model_packet_hash") != _canonical_hash(
                _common_stock_eval_module().common_stock_eval_model_packet(packet))
            or dispatch["dispatch_binding"].get("input_hash") != packet["input_manifest"]["input_hash"]):
        raise ValueError("COMMON_STOCK_EVAL_DISPATCH_BINDING_INVALID")
    manifest = packet["input_manifest"]
    record["trusted_task_binding"] = {
        **{key: manifest[key] for key in ("run_id", "invocation_id")},
        "agent": "dev_eval", "task_id": manifest["eval_id"], "task_name": "grade_common_stock_report",
    }
    record["identity_binding"] = {"status": "BOUND", "source": "TRUSTED_DISPATCH_AND_START"}


def _capture_common_stock_eval_result(payload, record, environment):
    """合法评分草稿才占用正式路径；失败原稿由有界修订边界另存。"""
    module = _common_stock_eval_module()
    eval_dir = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    packet = _common_stock_eval_stop_packet(payload, environment)
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("COMMON_STOCK_EVAL_OUTPUT_MISSING")
    try:
        value = json.loads(message)
    except json.JSONDecodeError as exc:
        raise ValueError("COMMON_STOCK_EVAL_OUTPUT_NOT_JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError("COMMON_STOCK_EVAL_OUTPUT_NOT_OBJECT")
    # 纯装配执行原 Schema、引用闭合与聚合校验；不改变评分、阈值或 FAIL 结论。
    module.envelope_common_stock_eval_draft(
        value, manifest=packet["input_manifest"], actual_model=payload["model"],
        input_binding_hash=packet["input_manifest"]["input_hash"],
    )
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
        eval_dir=eval_dir, semantic_result_path=semantic_path,
        actual_model=payload["model"], input_binding_hash=packet["input_manifest"]["input_hash"],
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


def _eval_output_attempt(
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
    from product.runtime.local_revision import verify_binding
    if verify_binding(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), payload, record, first[0]) is None:
        raise ValueError("LOCAL_REVISION_NOT_AUTHORIZED")
    if authorize_only:
        return payload
    from product.runtime.local_revision import resolve
    return resolve(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), payload, record, first[0])


def _repair_model_view(repair):
    from product.runtime.local_revision import VERSION
    if repair.get("repair_contract") != VERSION:
        return repair
    return {key: value for key, value in repair.items() if key not in {
        "binding_path", "binding_hash", "output_schema_hash", "task_id", "invocation_id"}}


def _persist_eval_raw_output(
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


def _verify_eval_dispatch(tool_input, environment):
    module = _common_stock_eval_module()
    packet = module.build_common_stock_eval_packet(
        Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(),
        expected_model=environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL"),
    )
    message = tool_input.get("message")
    return {
        "contract_version": module.EVAL_RUNTIME_VERSION,
        "input_hash": packet["input_manifest"]["input_hash"],
        "packet_hash": _canonical_hash(packet),
        "model_packet_hash": _canonical_hash(module.common_stock_eval_model_packet(packet)),
        "parent_message_hash": _canonical_hash({"message": message}) if isinstance(message, str) else None,
        "parent_message_authoritative": False,
        "matched": (tool_input.get("agent_type") == "dev_eval"
                    and tool_input.get("task_name") == "grade_common_stock_report"
                    and tool_input.get("fork_turns") == "none"
                    and isinstance(message, str) and 0 < len(message.encode("utf-8")) <= 4096),
    }


def _handle_eval_dispatch(payload, environment):
    log = _resolve_scoped_log(environment, environment_key="STOCK_AGENT_SUBAGENT_DISPATCH_LOG")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        raise ValueError("HOOK_DISPATCH_INPUT_INVALID")
    agent = tool_input.get("agent_type")
    binding = None
    with log.with_suffix(log.suffix + ".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not isinstance(agent, str) or not agent:
            spawn = str(payload.get("tool_name", "")).split(".")[-1] in {"spawn_agent", "collaborationspawn_agent", "Agent"}
            decision = "DENY_MISSING_AGENT_TYPE" if spawn else "IGNORE_NON_AGENT_TOOL"
        elif agent != "dev_eval":
            decision = "DENY_UNAPPROVED_AGENT"
        elif agent in _reserved_agents(log, parent_session_id=str(payload.get("session_id", ""))):
            decision = "DENY_DUPLICATE_AGENT"
        else:
            try:
                binding = _verify_eval_dispatch(tool_input, environment)
                decision = "ALLOW" if binding["matched"] else "DENY_DISPATCH_CONTRACT"
            except (OSError, ValueError, KeyError, TypeError, ImportError):
                decision = "DENY_DISPATCH_CONTRACT"
                binding = {"contract_version": COMMON_STOCK_EVAL_VERSION,
                           "matched": False, "failure_code": "DISPATCH_SOURCE_INVALID"}
        record = _dispatch_record(payload, decision=decision)
        if binding is not None:
            record["dispatch_binding"] = binding
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        _append_record(log, record)
    if decision in {"ALLOW", "IGNORE_NON_AGENT_TOOL"}:
        return record, {}
    return record, {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": decision + ":显式评分只允许本次冻结输入的一个dev_eval。",
    }}


def _eval_repair_packet(payload, record, environment, *, failure_code, attempt):
    fields = {"COMMON_STOCK_EVAL_CLAIM_REF_INVALID": "claim_refs",
              "COMMON_STOCK_EVAL_EVIDENCE_REF_INVALID": "evidence_refs",
              "COMMON_STOCK_EVAL_DIMENSION_STATUS_INVALID": "status"}
    if (attempt != 1 or record.get("identity_binding", {}).get("status") != "BOUND"
            or not failure_code.startswith(("SCHEMA_", "COMMON_STOCK_EVAL_RESULT_SCHEMA_INVALID:",
                                            *(key + ":" for key in fields), "COMMON_STOCK_EVAL_AGGREGATE_INVALID"))):
        return None
    from product.runtime.schema_validation import schema_issue_locations
    module = _common_stock_eval_module()
    packet = module.build_common_stock_eval_packet(
        Path(environment["STOCK_AGENT_RUN_DIR"]), expected_model=environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL"))
    schema = packet["output_schema"]
    draft = json.loads(payload["last_assistant_message"])
    reserved = set(module.build_common_stock_eval_result_schema(packet["input_manifest"])["properties"]) - set(schema["properties"])
    if isinstance(draft, dict) and reserved.intersection(draft):
        return None
    findings = schema_issue_locations(draft, schema)
    if not findings:
        code, _, name = failure_code.partition(":")
        if code in fields and name in module.DIMENSIONS:
            findings = [{"code": code, "path": f"dimensions.{name}.{fields[code]}"}]
        elif failure_code == "COMMON_STOCK_EVAL_AGGREGATE_INVALID":
            findings = [{"code": failure_code, "path": "status"}]
    if not findings or len(findings) > 32:
        return None
    from product.runtime.local_revision import bind
    trusted = record["trusted_task_binding"]
    repair = {"task_id": trusted["task_id"], "invocation_id": trusted["invocation_id"],
              "attempt": 1, "maximum_submissions": 2, "validation_error": failure_code,
              "validation_details": {"findings": findings}}
    binding = bind(Path(environment["STOCK_AGENT_RUN_DIR"]).resolve(), payload, record,
                   record["output_capture"], repair, findings)
    if binding is None:
        return None
    return {**repair, **binding,
            "instruction": "原评分作者在同一会话仅可按allowed_paths提交base_draft_ref及changes；"
                           "保留未改字段、原评分与FAIL结论。第二稿完整校验，最多一次修订。"}


def _capture_eval_output(payload, record, environment, log):
    attempt = _eval_output_attempt(log, payload)
    raw, candidate = {}, payload
    record["local_revision_authorized"] = False
    try:
        _resolve_local_revision(log, payload, record, environment, attempt, authorize_only=True)
        record["local_revision_authorized"] = True
        raw = _persist_eval_raw_output(payload, environment, attempt=attempt)
        candidate = _resolve_local_revision(log, payload, record, environment, attempt)
        _capture_common_stock_eval_result(candidate, record, environment)
        record["output_capture"].update(attempt=attempt, repair_state="REPAIRED" if attempt == 2 else "NOT_REQUIRED", **raw)
        return None
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        failure = str(exc)
        record["output_capture"] = {"status": "FAILED", "failure_code": failure, "attempt": attempt,
                                    "repair_state": "EXHAUSTED" if attempt >= 2 else "NOT_ALLOWED", **raw}
        if raw:
            record["output_capture"].update(rejected_path=raw["raw_path"], rejected_output_hash=raw["raw_output_hash"])
        repair = None
        try:
            repair = _eval_repair_packet(candidate, record, environment, failure_code=failure, attempt=attempt)
        except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
            record["repair_binding_error"] = str(error)
        if repair is None:
            return None
        record["output_capture"]["repair_state"] = "REPAIR_REQUESTED"
        record["hook_event_name"], record["hook_decision"] = "SubagentStopBlocked", "BLOCK"
        record["repair_request"] = {key: repair[key] for key in (
            "repair_contract", "task_id", "invocation_id", "attempt", "maximum_submissions",
            "validation_error", "base_draft_ref", "allowed_paths", "binding_path", "binding_hash") if key in repair}
        return {"decision": "block", "reason": json.dumps(_repair_model_view(repair), ensure_ascii=False, sort_keys=True, separators=(",", ":"))}


def handle_hook_event(payload: Mapping[str, Any], *, environ: Mapping[str, str] | None = None):
    environment = os.environ if environ is None else environ
    if (environment.get("STOCK_AGENT_COMMON_STOCK_EVAL") != COMMON_STOCK_EVAL_VERSION
            or any(environment.get(key) for key in (
                "STOCK_AGENT_COMMON_STOCK_STAGE", "STOCK_AGENT_MULTIDIMENSIONAL_STAGE",
                "STOCK_AGENT_RESEARCH_MATERIALS_STAGE", "STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE",
                "STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT", "STOCK_AGENT_CIO_LOCAL_REVISION"))):
        raise ValueError("NATIVE_HOST_EXECUTION_REQUIRED:旧正常研究Hook已退役；只保留显式dev_eval维护。")
    if payload.get("hook_event_name") == "PreToolUse":
        return _handle_eval_dispatch(payload, environment)
    if payload.get("hook_event_name") not in SUPPORTED_EVENTS:
        raise ValueError("HOOK_EVENT_UNSUPPORTED")
    log = _resolve_scoped_log(environment)
    response = {}
    with log.with_suffix(log.suffix + ".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        record = minimize_hook_event(payload)
        if payload["hook_event_name"] == "SubagentStart":
            try:
                if payload["agent_type"] != "dev_eval":
                    raise ValueError("COMMON_STOCK_EVAL_START_AGENT_INVALID")
                model = environment.get("STOCK_AGENT_COMMON_STOCK_EVAL_MODEL")
                if not model or payload.get("model") != model:
                    raise ValueError("COMMON_STOCK_EVAL_START_MODEL_INVALID")
                module = _common_stock_eval_module()
                packet = module.build_common_stock_eval_packet(Path(environment["STOCK_AGENT_RUN_DIR"]), expected_model=model)
                view = module.common_stock_eval_model_packet(packet)
                manifest = packet["input_manifest"]
                record["context_binding"] = {"status": "DELIVERED", **{key: manifest[key] for key in (
                    "eval_id", "run_id", "invocation_id", "security_id", "input_hash")},
                    "packet_hash": _canonical_hash(packet), "model_packet_hash": _canonical_hash(view)}
                response = {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": json.dumps(
                    view, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}}
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                code = str(exc).split(":", 1)[0]
                record["context_binding"] = {"status": "FAILED", "failure_code": code}
                response = {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext":
                            f"冻结Eval上下文交付失败：{code}。禁止评分或补充外部事实。"}}
        else:
            try:
                _bind_common_stock_eval_stop_identity(payload, record, environment)
                response = _capture_eval_output(payload, record, environment, log) or {}
            except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
                record["output_capture"] = {"status": "FAILED", "failure_code": str(exc)}
        record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        _append_record(log, record)
    return record, response


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
