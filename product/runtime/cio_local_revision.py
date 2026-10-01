"""CIO 主线程 Stop 接缝：复用局部修订，保持原装配/风控与研究权限。

这里不启动模型、不发布决策；主会话由真实 SessionStart 绑定，首稿和
唯一修订由 Stop 保存。宿主结束后必须重读底层记录，不信任 SAVED 摘要。
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .hashing import canonical_hash, file_hash, legacy_envelope_hash, verify_legacy_envelope_hash
from .local_revision import bind, resolve, verify_binding, _path
from .schema_validation import schema_issue_locations, validate_schema_instance

VERSION = "cio-local-revision/1.0.1"
LOG = "invocation/cio-stop-events.jsonl"


def implementation_hashes(repository: Path) -> dict[str, str]:
    return {ref: file_hash(repository / ref) for ref in (
        "product/runtime/cio_local_revision.py", "product/runtime/local_revision.py",
    )}


def _delivery(root: Path) -> dict:
    """复用实际启动文件；只统计明确可比较的表示，不估算 token/历史费用。"""
    prompt = _path(root, "invocation/prompt.txt").read_text()
    value = {"scope": "MAIN_THREAD_STDIN_PROMPT_AND_FROZEN_INPUT_REPRESENTATIONS",
             "prompt_bytes": len(prompt.encode("utf-8")), "prompt_hash": file_hash(_path(root, "invocation/prompt.txt")),
             "comparison_status": "NOT_COMPARABLE", "full_input_bytes": None, "model_input_bytes": None,
             "byte_delta": None, "token_usage": None, "token_usage_status": "NOT_OBSERVED",
             "total_cost": None, "total_prompt_baseline": "NOT_OBSERVED"}
    if _path(root, "inputs/runtime_cio.model.json").exists():
        full = _read(_path(root, "inputs/runtime_cio.json"))
        model = _read(_path(root, "inputs/runtime_cio.model.json"))
        from .cio_handoff import fixture_cio_model_input
        if model != fixture_cio_model_input(root, full):
            raise ValueError("CIO_MODEL_INPUT_DRIFT")
        value["input_measurement_scope"] = "FROZEN_JSON_REPRESENTATION_NOT_PROOF_OF_MODEL_READ"
    elif "<validated_research_context>\n" in prompt:
        model = json.loads(prompt.split("<validated_research_context>\n", 1)[1].split("\n</validated_research_context>", 1)[0])
        full = {**model, "request": _read(_path(root, "predecision-cio-request.json"))}
        value["input_measurement_scope"] = "EMBEDDED_CONTEXT_REQUEST_WRAPPER_ONLY"
    else:
        return value
    serialize = lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    value.update(comparison_status="SAME_FROZEN_INPUT_REPRESENTATION",
                 full_input_hash=canonical_hash(full), model_input_hash=canonical_hash(model),
                 full_input_bytes=len(serialize(full)), model_input_bytes=len(serialize(model)),
                 byte_delta=len(serialize(model)) - len(serialize(full)))
    return value


def _verify_delivery_start(root: Path, start: dict, current: dict) -> None:
    """启动只绑定当时存在的内容；fixture 的 CIO 输入在研究结束后才生成。"""
    expected = current
    if start.get("comparison_status") == "NOT_COMPARABLE":
        if (root / "predecision-cio-request.json").is_file():
            raise ValueError("CIO_LOCAL_REVISION_DELIVERY_DRIFT")
        expected = {key: value for key, value in current.items()
                    if key not in {"input_measurement_scope", "full_input_hash", "model_input_hash"}}
        expected.update(comparison_status="NOT_COMPARABLE", full_input_bytes=None,
                        model_input_bytes=None, byte_delta=None)
    if start != expected:
        raise ValueError("CIO_LOCAL_REVISION_DELIVERY_DRIFT")


def _read(path: Path) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("CIO_LOCAL_REVISION_DUPLICATE_KEY")
            value[key] = item
        return value
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("CIO_LOCAL_REVISION_NOT_OBJECT")
    return value


def _records(root: Path) -> list[dict]:
    path = _path(root, LOG)
    values = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    for value in values:
        verify_legacy_envelope_hash(value, hash_field="event_hash", location=LOG)
    return values


def _launch(root: Path, payload: Mapping[str, Any]) -> tuple[dict, dict]:
    environment = _read(_path(root, "invocation/environment-manifest.json"))
    run = _read(_path(root, "run_manifest.json"))
    command = environment.get("command", [])
    if (environment.get("cio_local_revision_version") != VERSION
            or environment.get("run_id") != run.get("run_id")
            or environment.get("model") != run.get("model")
            or not isinstance(command, list) or "--model" not in command or "-C" not in command
            or command[command.index("--model") + 1] != environment.get("model")
            or payload.get("model") != environment.get("model")
            or not isinstance(payload.get("session_id"), str) or not payload["session_id"]
            or payload.get("agent_id") is not None
            or payload.get("cwd") != command[command.index("-C") + 1]
            or not any(str(item).startswith("hooks.SessionStart=") for item in command)
            or not any(str(item).startswith("hooks.Stop=") for item in command)):
        raise ValueError("CIO_LOCAL_REVISION_LAUNCH_BINDING_INVALID")
    prompt_hash = file_hash(_path(root, "invocation/prompt.txt"))
    expected_prompt = environment.get("prompt_hash", environment.get("resource_hashes", {}).get("prompt"))
    if prompt_hash != expected_prompt:
        raise ValueError("CIO_LOCAL_REVISION_PROMPT_DRIFT")
    if environment.get("cio_local_revision_source_hashes") != implementation_hashes(Path(__file__).resolve().parents[2]):
        raise ValueError("CIO_LOCAL_REVISION_IMPLEMENTATION_DRIFT")
    return environment, {"run_id": run["run_id"], "model": environment["model"],
                         "environment_hash": file_hash(_path(root, "invocation/environment-manifest.json")),
                         "prompt_hash": prompt_hash}


def _contract(repository: Path, root: Path) -> tuple[dict, dict, set, Any]:
    """复用两种 CIO 的权威 schema 和纯校验；不能在 Stop 执行 Risk。"""
    from .cio_handoff import COUNCIL_METADATA, PREDECISION_METADATA, NATIVE_CIO_VERSION, assemble_cio_draft
    from .invocation import verify_invocation_manifest
    invocation = _read(_path(root, "invocations/runtime_cio.json"))
    if invocation.get("draft_delivery") != NATIVE_CIO_VERSION:
        raise ValueError("CIO_LEGACY_WRITE_RETIRED")
    if (root / "predecision-cio-request.json").is_file():
        from . import predecision_cio_stage as stage
        manifest, request = stage.validate_predecision_cio_run(repository, root)
        catalog = manifest["report_catalog"]
        schema = stage._native_output_schema(repository, request, catalog, run_dir=root)
        def validate(draft):
            output, _ = stage._assemble_native_output(repository, root, request, catalog, draft,
                                                      stage._host_generated_at(root, request))
            stage._validate_cio_content_and_queries(root, request, output, catalog)
        reserved = PREDECISION_METADATA - {"schema_version"}
    else:
        from .cio_handoff import fixture_cio_model_input
        from .invocation import OUTPUT_SCHEMAS
        from .validation import validate_cio_draft
        original = _read(_path(root, "inputs/runtime_cio.json"))
        verify_invocation_manifest(repository, invocation, agent_input=original)
        if _read(_path(root, "inputs/runtime_cio.model.json")) != fixture_cio_model_input(root, original):
            raise ValueError("CIO_MODEL_INPUT_DRIFT")
        schema = _read(_path(root, str(Path(invocation["output_schema"]).relative_to(root))))
        formal = _read(repository / "product" / OUTPUT_SCHEMAS["runtime_cio"])
        catalog = invocation["report_catalog"]
        if _read(_path(root, "run_manifest.json")).get("run_mode") == "EVAL_ABLATION":
            from .invocation import build_cio_ablation_output_schema
            formal = build_cio_ablation_output_schema(repository, expected_report_agents=tuple(item["report_id"] for item in catalog))
        def validate(draft):
            output, _ = assemble_cio_draft(draft, formal, {
                "schema_version": "cio-decision-draft/2.1.0", "run_id": invocation["run_id"],
                "invocation_id": invocation["invocation_id"], "agent": "runtime_cio",
                "skill_execution": invocation["skill_execution"], "advisory_only": True,
                "consumed_reports": [item["identity"] for item in catalog],
            }, root=root, invocation=invocation, catalog=catalog)
            validate_cio_draft(output, run_id=invocation["run_id"], manifest=invocation,
                               report_hashes={item["report_id"]: canonical_hash(_read(_path(root, item["artifact_ref"])))
                                              for item in catalog},
                               expected_report_agents=tuple(item["report_id"] for item in catalog))
        reserved = COUNCIL_METADATA - {"schema_version"}
    task = {"run_id": invocation["run_id"], "invocation_id": invocation["invocation_id"],
            "agent": "runtime_cio", "schema_hash": canonical_hash(schema),
            "invocation_hash": canonical_hash(invocation)}
    reserved = set(reserved) | {"model", "input_hash", "output_hash", "prompt_hash", "rubric_hash"}
    return schema, task, reserved, validate


def _draft_message(root: Path, payload: Mapping[str, Any]) -> str:
    if (root / "predecision-cio-request.json").is_file():
        message = payload.get("last_assistant_message")
    else:
        message = _path(root, "cio/runtime_cio.json").read_text(encoding="utf-8")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("CIO_LOCAL_REVISION_DRAFT_MISSING")
    return message


def _submission(root: Path, record: dict, message: str, attempt: int) -> dict:
    name = canonical_hash({"session_id": record["session_id"], "task": record["trusted_task_binding"]})
    relative = f"invocation/cio-drafts/{name}-{attempt}.json"
    path = _path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(message + ("" if message.endswith("\n") else "\n"))
        stream.flush()
        os.fsync(stream.fileno())
    return {"raw_path": relative, "raw_output_hash": canonical_hash({"assistant_message": message})}


def handle(payload: Mapping[str, Any], environment: Mapping[str, str]) -> tuple[dict, dict]:
    root = Path(environment["STOCK_AGENT_RUN_DIR"]).resolve()
    repository = Path(__file__).resolve().parents[2]
    event = payload.get("hook_event_name")
    if event not in {"SessionStart", "Stop"}:
        raise ValueError("CIO_LOCAL_REVISION_EVENT_INVALID")
    _, launch = _launch(root, payload)  # 授权、路径、实际模型先于任何额度和原稿写入。
    path = _path(root, LOG)
    with _path(root, LOG + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = _records(root)
        starts = [item for item in previous if item["hook_event_name"] == "SessionStart"]
        record = {"version": VERSION, "execution_context": "MAIN_THREAD", "hook_event_name": event,
                  "session_id": payload["session_id"], "launch_binding": launch}
        response = {}
        if event == "SessionStart":
            if starts and any(item["session_id"] != payload["session_id"] or item["launch_binding"] != launch for item in starts):
                raise ValueError("CIO_LOCAL_REVISION_SESSION_DRIFT")
            if starts:
                return starts[0], {}
            if payload.get("source") != "startup":
                raise ValueError("CIO_LOCAL_REVISION_START_MISSING")
            record["delivery_diagnostics"] = _delivery(root)
        else:
            if (len(starts) != 1 or starts[0]["session_id"] != payload["session_id"]
                    or starts[0]["launch_binding"] != launch):
                raise ValueError("CIO_LOCAL_REVISION_SESSION_UNBOUND")
            schema, task, reserved, validate = _contract(repository, root)
            delivery = _delivery(root)
            _verify_delivery_start(root, starts[0]["delivery_diagnostics"], delivery)
            record["delivery_diagnostics"] = delivery
            record.update(trusted_task_binding=task, identity_binding={"status": "BOUND"})
            message = _draft_message(root, payload)
            author = {**payload, "last_assistant_message": message}
            stops = [item for item in previous if item["hook_event_name"] == "Stop"]
            attempt = len(stops) + 1
            record.update(attempt=attempt, final_response_hash=canonical_hash({"assistant_message": payload.get("last_assistant_message")}))
            if attempt > 2 or (stops and stops[0].get("status") != "REPAIR_REQUESTED"):
                raise ValueError("CIO_LOCAL_REVISION_NOT_AUTHORIZED")
            if stops and stops[0]["trusted_task_binding"] != task:
                raise ValueError("CIO_LOCAL_REVISION_CONFIGURATION_DRIFT")
            if stops and stops[0].get("delivery_diagnostics") != delivery:
                raise ValueError("CIO_LOCAL_REVISION_DELIVERY_DRIFT")
            if stops and verify_binding(root, author, record, stops[0]) is None:
                raise ValueError("CIO_LOCAL_REVISION_NOT_AUTHORIZED")
            raw = _submission(root, record, message, attempt)
            record["output_capture"] = raw
            try:
                candidate = resolve(root, author, record, stops[0]) if stops else author
                draft = json.loads(candidate["last_assistant_message"])
                if not isinstance(draft, dict) or reserved.intersection(draft):
                    raise ValueError("CIO_LOCAL_REVISION_TECHNICAL_FIELDS_FORBIDDEN")
                # 保存原始对象，禁止重复键通过不同解析器偷换含义。
                _read(_path(root, raw["raw_path"]))
                validate_schema_instance(draft, schema)
                validate(draft)
                record.update(status="SAVED", candidate_hash=canonical_hash(draft))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                record.update(status="FAILED", failure_code=str(exc))
                findings = (schema_issue_locations(json.loads(message), schema)
                            if attempt == 1 and str(exc).startswith("SCHEMA_") else [])
                if findings and not reserved.intersection(json.loads(message)):
                    repair = {"validation_error": str(exc)}
                    binding = bind(root, author, record, raw, repair, findings)
                    if binding:
                        record.update(status="REPAIR_REQUESTED", repair_request={**repair, **binding})
                        response = {"decision": "block", "reason": json.dumps({
                            "allowed_paths": binding["allowed_paths"],
                            "instruction": "唯一一次原 CIO 局部修订。只改 allowed_paths 定位的字段，其他字段保持原稿不变；"
                                           "沿当前入口返回/保存完整语义对象，程序会按原稿比较差异并完整再验。"
                                           "不要重新派发研究、填写身份/hash、猜引用或扩大事实/权限；第二次失败终止。",
                        }, ensure_ascii=False)}
                if not response:
                    response = {"continue": False, "stopReason": "CIO 草稿校验失败；保留失败，不再增加尝试。"}
        record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record, response


def verify(root: Path, *, payload: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict:
    """宿主从真实终态消息重验两版原稿/范围/配置，不把 Hook SAVED 当证明。"""
    root = Path(root).resolve()
    _, launch = _launch(root, payload)
    records = _records(root)
    starts = [item for item in records if item["hook_event_name"] == "SessionStart"]
    stops = [item for item in records if item["hook_event_name"] == "Stop"]
    if (len(starts) != 1 or not 1 <= len(stops) <= 2
            or starts[0]["session_id"] != payload["session_id"]
            or any(item["launch_binding"] != launch or item["session_id"] != payload["session_id"] for item in records)
            or any(item.get("execution_context") != "MAIN_THREAD" for item in records)
            or stops[-1].get("status") != "SAVED"
            or stops[-1]["final_response_hash"] != canonical_hash({"assistant_message": payload["last_assistant_message"]})):
        raise ValueError("CIO_LOCAL_REVISION_COMPLETION_INVALID")
    delivery = _delivery(root)
    _verify_delivery_start(root, starts[0].get("delivery_diagnostics", {}), delivery)
    if any(item.get("delivery_diagnostics") != delivery for item in stops):
        raise ValueError("CIO_LOCAL_REVISION_DELIVERY_DRIFT")
    schema, task, reserved, validate = _contract(Path(__file__).resolve().parents[2], root)
    last = stops[-1]
    if last["trusted_task_binding"] != task or last["identity_binding"] != {"status": "BOUND"}:
        raise ValueError("CIO_LOCAL_REVISION_CONFIGURATION_DRIFT")
    messages = []
    for item in stops:
        raw = item["output_capture"]
        text = _path(root, raw["raw_path"]).read_text()
        matches = [v for v in (text, text[:-1] if text.endswith("\n") else text)
                   if canonical_hash({"assistant_message": v}) == raw["raw_output_hash"]]
        if not matches:
            raise ValueError("CIO_LOCAL_REVISION_RAW_DRIFT")
        _read(_path(root, raw["raw_path"]))
        messages.append(matches[0])
    verification = {**last}
    submitted = {**payload, "last_assistant_message": messages[-1]}
    if len(stops) == 2:
        if stops[0].get("status") != "REPAIR_REQUESTED" or stops[0]["trusted_task_binding"] != task:
            raise ValueError("CIO_LOCAL_REVISION_NOT_AUTHORIZED")
        submitted = resolve(root, submitted, verification, stops[0])
        if verification.get("local_revision") != last.get("local_revision"):
            raise ValueError("CIO_LOCAL_REVISION_PROOF_DRIFT")
    resolved = json.loads(submitted["last_assistant_message"])
    if (resolved != candidate or canonical_hash(resolved) != last["candidate_hash"]
            or reserved.intersection(resolved)):
        raise ValueError("CIO_LOCAL_REVISION_CANDIDATE_DRIFT")
    validate_schema_instance(resolved, schema)
    validate(resolved)
    return {"version": VERSION, "execution_context": "MAIN_THREAD", "session_id": payload["session_id"],
            "attempts": len(stops), "event_hashes": [item["event_hash"] for item in records],
            "candidate_hash": canonical_hash(resolved), "delivery_diagnostics": delivery,
            "launch_delivery_diagnostics": starts[0]["delivery_diagnostics"]}


def verify_completed(root: Path, *, candidate: Mapping[str, Any]) -> dict:
    """从宿主保存的事件流绑定真实主会话/最终消息，再校验修订原件。"""
    root = Path(root).resolve()
    environment = _read(_path(root, "invocation/environment-manifest.json"))
    path = _path(root, "invocation/codex-events.jsonl")
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    sessions = {item.get("thread_id") for item in events if item.get("type") == "thread.started"}
    messages = [item["item"].get("text") for item in events if item.get("type") == "item.completed"
                and isinstance(item.get("item"), dict) and item["item"].get("type") == "agent_message"]
    if (len(sessions) != 1 or None in sessions or not messages or not isinstance(messages[-1], str)
            or not events or events[-1].get("type") != "turn.completed"):
        raise ValueError("CIO_LOCAL_REVISION_THREAD_MISSING")
    command = environment["command"]
    proof = verify(root, payload={"hook_event_name": "Stop", "session_id": next(iter(sessions)),
                                 "model": environment["model"], "cwd": command[command.index("-C") + 1],
                                 "last_assistant_message": messages[-1]}, candidate=candidate)
    proof["event_file_hash"] = file_hash(path)
    return proof
