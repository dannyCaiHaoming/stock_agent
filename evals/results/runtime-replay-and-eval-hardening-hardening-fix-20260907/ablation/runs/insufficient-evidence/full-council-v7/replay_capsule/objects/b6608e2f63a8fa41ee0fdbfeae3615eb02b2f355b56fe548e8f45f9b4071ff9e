"""Minimize Codex rollouts and verify native multi-Agent execution.

The generated proof deliberately excludes prompt text, hidden reasoning, tool output
payloads, and the raw rollout path.  It keeps only identities, ordering, hashes, and
contract-presence booleans needed by the acceptance gate.
"""

from __future__ import annotations

import json
import re
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .hashing import canonical_hash, file_hash
from .runtime_profiles import validate_runtime_mode


PROOF_SCHEMA_VERSION = "codex-execution-proof/2.0.0"
SPECIALIST_AGENTS = ("runtime_company_analyst", "runtime_skeptic")
SPECIALIST_TASK_NAMES = {
    "runtime_company_analyst": "company_research",
    "runtime_skeptic": "independent_skeptic",
}


class ExecutionProofError(ValueError):
    """Raised when native Codex execution cannot be proven."""


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ExecutionProofError("ROLLOUT_NOT_FOUND")
    records: list[dict[str, Any]] = []
    for ordinal, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExecutionProofError(f"INVALID_ROLLOUT_JSONL:{ordinal}") from exc
        if not isinstance(value, Mapping):
            raise ExecutionProofError(f"INVALID_ROLLOUT_RECORD:{ordinal}")
        records.append(dict(value))
    if not records:
        raise ExecutionProofError("EMPTY_ROLLOUT")
    return records


def _payload(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("payload", {})
    return value if isinstance(value, Mapping) else {}


def _session_meta(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    matches = [_payload(record) for record in records if record.get("type") == "session_meta"]
    if len(matches) != 1:
        raise ExecutionProofError("SESSION_METADATA_MISSING_OR_DUPLICATE")
    return matches[0]


def _turn_context(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    matches = [_payload(record) for record in records if record.get("type") == "turn_context"]
    if not matches:
        raise ExecutionProofError("TURN_CONTEXT_MISSING")
    return matches[-1]


def _message_texts(
    records: Sequence[Mapping[str, Any]], *, role: str
) -> list[str]:
    texts: list[str] = []
    for record in records:
        payload = _payload(record)
        if (
            record.get("type") != "response_item"
            or payload.get("type") != "message"
            or payload.get("role") != role
        ):
            continue
        content = payload.get("content", [])
        if not isinstance(content, list):
            continue
        texts.append(
            "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, Mapping)
            )
        )
    return texts


def _final_structured_output(
    records: Sequence[Mapping[str, Any]], *, agent_name: str
) -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    for text in _message_texts(records, role="assistant"):
        if not text.strip():
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            parsed.append(dict(value))
    if not parsed:
        raise ExecutionProofError(f"CHILD_STRUCTURED_OUTPUT_MISSING:{agent_name}")
    return parsed[-1]


def _is_protected_dispatch_message(value: Any) -> bool:
    """Recognize the opaque authenticated envelope emitted by current Codex rollouts."""

    if not isinstance(value, str) or len(value) < 100 or not value.startswith("gAAAA"):
        return False
    return re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value) is not None


def _function_calls(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for ordinal, record in enumerate(records):
        payload = _payload(record)
        if record.get("type") != "response_item" or payload.get("type") != "function_call":
            continue
        arguments = payload.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, Mapping):
            arguments = {}
        calls.append(
            {
                "ordinal": ordinal,
                "namespace": payload.get("namespace"),
                "name": payload.get("name"),
                "call_id": payload.get("call_id"),
                "arguments": dict(arguments),
            }
        )
    return calls


def _custom_tool_calls(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for ordinal, record in enumerate(records):
        payload = _payload(record)
        if record.get("type") != "response_item" or payload.get("type") != "custom_tool_call":
            continue
        calls.append(
            {
                "ordinal": ordinal,
                "name": payload.get("name"),
                "call_id": payload.get("call_id"),
                "input": str(payload.get("input", "")),
            }
        )
    return calls


def _subagent_events(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for ordinal, record in enumerate(records):
        payload = _payload(record)
        if record.get("type") != "event_msg" or payload.get("type") != "item_completed":
            continue
        item = payload.get("item", {})
        if not isinstance(item, Mapping) or item.get("type") != "SubAgentActivity":
            continue
        events.append(
            {
                "ordinal": ordinal,
                "event_id": item.get("id"),
                "kind": item.get("kind"),
                "child_session_id": item.get("agent_thread_id"),
                "agent_path_hash": canonical_hash({"agent_path": item.get("agent_path")}),
            }
        )
    return events


def _expected_runtime(runtime: str) -> str:
    prefix = "codex-cli/"
    if not runtime.startswith(prefix):
        raise ExecutionProofError("UNSUPPORTED_CODEX_RUNTIME_IDENTIFIER")
    return runtime.removeprefix(prefix)


def _rollout_telemetry(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals: Mapping[str, Any] | None = None
    calls = 0
    timestamps: list[datetime] = []
    for record in records:
        timestamp = record.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamps.append(datetime.fromisoformat(timestamp.replace("Z", "+00:00")))
            except ValueError:
                pass
        payload = _payload(record)
        if record.get("type") == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info", {})
            total = info.get("total_token_usage", {}) if isinstance(info, Mapping) else {}
            if isinstance(total, Mapping):
                totals = total
                calls += 1
    if totals is None:
        return {
            "status": "MISSING_TELEMETRY",
            "input_tokens": None,
            "output_tokens": None,
            "cached_tokens": None,
            "latency_ms": None,
            "llm_calls": None,
        }
    latency = int((max(timestamps) - min(timestamps)).total_seconds() * 1000) if len(timestamps) >= 2 else None
    return {
        "status": "AVAILABLE" if latency is not None else "MISSING_TELEMETRY",
        "input_tokens": int(totals.get("input_tokens", 0)),
        "output_tokens": int(totals.get("output_tokens", 0)),
        "cached_tokens": int(totals.get("cached_input_tokens", 0)),
        "latency_ms": latency,
        "llm_calls": calls,
    }


def _logical_tool_name(call: Mapping[str, Any], allowed_tools: set[str]) -> str | None:
    namespace = str(call.get("namespace") or "")
    name = str(call.get("name") or "")
    searchable = f"{namespace}.{name}".casefold().replace("__", ".")
    for logical_name in allowed_tools:
        _, tool = logical_name.casefold().split(".", 1)
        if tool in searchable:
            return logical_name
    return None


def _child_proof(
    *,
    repository_root: Path,
    records: Sequence[Mapping[str, Any]],
    rollout_hash: str,
    parent_session_id: str,
    manifest: Mapping[str, Any],
    task_prompt: str,
    dispatch: Mapping[str, Any],
) -> dict[str, Any]:
    meta = _session_meta(records)
    context = _turn_context(records)
    expected_agent = manifest["agent"]["name"]
    if meta.get("agent_role") != expected_agent:
        raise ExecutionProofError(f"CHILD_AGENT_ROLE_MISMATCH:{expected_agent}")
    if meta.get("parent_thread_id") != parent_session_id:
        raise ExecutionProofError(f"CHILD_PARENT_MISMATCH:{expected_agent}")
    if context.get("model") != manifest.get("model"):
        raise ExecutionProofError(f"CHILD_MODEL_MISMATCH:{expected_agent}")
    if meta.get("cli_version") != _expected_runtime(str(manifest.get("codex_runtime", ""))):
        raise ExecutionProofError(f"CHILD_RUNTIME_MISMATCH:{expected_agent}")

    product_root = (repository_root.resolve() / "product").resolve()
    agent_path = Path(str(manifest["agent"]["path"])).resolve()
    if not agent_path.is_relative_to(product_root) or file_hash(agent_path) != manifest["agent"]["sha256"]:
        raise ExecutionProofError(f"CHILD_AGENT_RESOURCE_MISMATCH:{expected_agent}")
    with agent_path.open("rb") as handle:
        agent_config = tomllib.load(handle)
    role_instructions = str(agent_config.get("developer_instructions", ""))
    developer_text = "\n".join(_message_texts(records, role="developer"))
    if not role_instructions or role_instructions not in developer_text:
        raise ExecutionProofError(f"ROLE_INSTRUCTIONS_NOT_LOADED:{expected_agent}")

    configured_skills = [
        Path(str(item.get("path", ""))).name
        for item in agent_config.get("skills", {}).get("config", [])
        if isinstance(item, Mapping) and item.get("enabled") is True
    ]
    manifest_skills = [str(item["name"]) for item in manifest.get("skills", [])]
    if configured_skills != manifest_skills:
        raise ExecutionProofError(f"CONFIGURED_SKILLS_MISMATCH:{expected_agent}")
    missing_skill_mentions = [name for name in manifest_skills if name not in role_instructions]
    if missing_skill_mentions:
        raise ExecutionProofError(
            f"SKILL_PROTOCOL_NOT_BOUND:{expected_agent}:{','.join(missing_skill_mentions)}"
        )

    allowed_tools = set(str(item) for item in manifest.get("tool_permissions", []))
    observed_tool_calls: list[dict[str, Any]] = []
    for call in _function_calls(records):
        logical_name = _logical_tool_name(call, allowed_tools)
        if logical_name is None:
            arguments_text = json.dumps(call.get("arguments", {}), ensure_ascii=False).casefold()
            if "fixture_snapshot" in arguments_text or "evals/fixtures" in arguments_text:
                raise ExecutionProofError(f"RAW_FIXTURE_ACCESS_ATTEMPT:{expected_agent}")
            raise ExecutionProofError(f"UNAPPROVED_CHILD_TOOL_CALL:{expected_agent}")
        observed_tool_calls.append(
            {
                "ordinal": call["ordinal"],
                "tool": logical_name,
                "call_id": call["call_id"],
                "arguments_hash": canonical_hash(call.get("arguments", {})),
            }
        )
    for call in _custom_tool_calls(records):
        code = call["input"]
        nested_tools = re.findall(r"tools\.([A-Za-z0-9_]+)", code)
        if not nested_tools and "ALL_TOOLS" in code:
            continue
        if not nested_tools:
            raise ExecutionProofError(f"UNAPPROVED_CHILD_CUSTOM_TOOL:{expected_agent}")
        for nested_name in nested_tools:
            logical_name = _logical_tool_name(
                {"namespace": "mcp", "name": nested_name}, allowed_tools
            )
            if logical_name is None:
                raise ExecutionProofError(f"UNAPPROVED_CHILD_CUSTOM_TOOL:{expected_agent}")
            observed_tool_calls.append(
                {
                    "ordinal": call["ordinal"],
                    "tool": logical_name,
                    "call_id": call["call_id"],
                    "arguments_hash": canonical_hash({"custom_tool_input": code}),
                }
            )

    final_output = _final_structured_output(records, agent_name=expected_agent)
    user_text = "\n".join(_message_texts(records, role="user"))
    plaintext_binding = {
        "run_id_present": str(manifest["run_id"]) in user_text,
        "invocation_id_present": str(manifest["invocation_id"]) in user_text,
        "task_prompt_present": task_prompt in user_text,
    }
    output_binding = {
        "run_id_matches": final_output.get("run_id") == manifest.get("run_id"),
        "invocation_id_matches": final_output.get("invocation_id")
        == manifest.get("invocation_id"),
        "agent_matches": final_output.get("agent") == expected_agent,
    }
    plaintext_verified = all(plaintext_binding.values())
    protected_verified = bool(
        dispatch.get("request", {}).get("protected_message_present")
    ) and all(output_binding.values())
    if not plaintext_verified and not protected_verified:
        raise ExecutionProofError(f"CHILD_TASK_BINDING_MISSING:{expected_agent}")
    task_binding = {
        **plaintext_binding,
        **output_binding,
        "binding_method": (
            "plaintext_child_input"
            if plaintext_verified
            else "protected_dispatch_plus_structured_output"
        ),
        "verified": True,
        "task_prompt_hash": canonical_hash({"task_prompt": task_prompt}),
    }
    if task_binding["task_prompt_hash"] != manifest.get("task_prompt_hash"):
        raise ExecutionProofError(f"CHILD_TASK_PROMPT_HASH_MISMATCH:{expected_agent}")

    assistant_text = "\n".join(_message_texts(records, role="assistant"))
    return {
        "session_id": meta.get("id"),
        "parent_session_id": meta.get("parent_thread_id"),
        "agent_role": meta.get("agent_role"),
        "thread_source": meta.get("thread_source"),
        "model": context.get("model"),
        "codex_runtime": f"codex-cli/{meta.get('cli_version')}",
        "multi_agent_version": meta.get("multi_agent_version"),
        "rollout_sha256": rollout_hash,
        "agent_resource_sha256": manifest["agent"]["sha256"],
        "role_instruction_sha256": canonical_hash({"developer_instructions": role_instructions}),
        "role_instructions_loaded": True,
        "configured_skills": [
            {
                "name": skill["name"],
                "version": skill["version"],
                "sha256": skill["sha256"],
                "configured": True,
                "protocol_bound": True,
            }
            for skill in manifest.get("skills", [])
        ],
        "observed_tool_calls": observed_tool_calls,
        "unapproved_tool_calls": 0,
        "raw_fixture_access_attempts": 0,
        "task_binding": task_binding,
        "assistant_output_hash": canonical_hash({"assistant_messages": assistant_text}),
        "final_structured_output_hash": canonical_hash(final_output),
    }


def build_specialist_execution_proof(
    repository_root: Path,
    *,
    parent_rollout: Path,
    child_rollouts: Mapping[str, Path],
    invocation_manifests: Mapping[str, Mapping[str, Any]],
    task_prompts: Mapping[str, str],
    specialist_agents: Sequence[str] = SPECIALIST_AGENTS,
) -> dict[str, Any]:
    """Build a privacy-minimized proof for the fixed parallel specialist pass."""

    specialists = tuple(specialist_agents)
    if any(name not in SPECIALIST_AGENTS for name in specialists) or len(set(specialists)) != len(specialists):
        raise ExecutionProofError("SPECIALIST_TOPOLOGY_INVALID")
    if set(invocation_manifests) != set(specialists):
        raise ExecutionProofError("SPECIALIST_MANIFEST_SET_INVALID")
    if set(child_rollouts) != set(specialists) or set(task_prompts) != set(specialists):
        raise ExecutionProofError("SPECIALIST_PROOF_INPUT_SET_INVALID")

    parent_records = _load_jsonl(parent_rollout)
    parent_meta = _session_meta(parent_records)
    parent_context = _turn_context(parent_records)
    parent_session_id = str(parent_meta.get("id", ""))
    calls = _function_calls(parent_records)
    events = _subagent_events(parent_records)
    waits = [
        call["ordinal"]
        for call in calls
        if call["namespace"] == "collaboration" and call["name"] == "wait_agent"
    ]
    first_wait = min(waits) if waits else None

    dispatches: list[dict[str, Any]] = []
    for agent_name in specialists:
        matches = [
            call
            for call in calls
            if call["namespace"] == "collaboration"
            and call["name"] == "spawn_agent"
            and call["arguments"].get("agent_type") == agent_name
        ]
        if len(matches) != 1:
            raise ExecutionProofError(f"SPECIALIST_DISPATCH_COUNT_INVALID:{agent_name}")
        call = matches[0]
        if call["arguments"].get("task_name") != SPECIALIST_TASK_NAMES[agent_name]:
            raise ExecutionProofError(f"SPECIALIST_TASK_NAME_INVALID:{agent_name}")
        if call["arguments"].get("fork_turns") != "none":
            raise ExecutionProofError(f"SPECIALIST_CONTEXT_ISOLATION_INVALID:{agent_name}")
        if first_wait is not None and call["ordinal"] >= first_wait:
            raise ExecutionProofError(f"SPECIALIST_DISPATCH_AFTER_WAIT:{agent_name}")
        starts = [
            event
            for event in events
            if event["kind"] == "started" and event["event_id"] == call["call_id"]
        ]
        if len(starts) != 1 or not starts[0]["child_session_id"]:
            raise ExecutionProofError(f"SPECIALIST_START_EVENT_INVALID:{agent_name}")
        child_id = starts[0]["child_session_id"]
        completions = [
            event
            for event in events
            if event["kind"] == "completed" and event["child_session_id"] == child_id
        ]
        if len(completions) != 1:
            raise ExecutionProofError(f"SPECIALIST_COMPLETION_EVENT_INVALID:{agent_name}")
        safe_request = {
            "agent_type": agent_name,
            "task_name": call["arguments"].get("task_name"),
            "fork_turns": call["arguments"].get("fork_turns"),
            "protected_message_present": _is_protected_dispatch_message(
                call["arguments"].get("message")
            ),
            "message_sha256": canonical_hash({"message": call["arguments"].get("message")}),
        }
        dispatches.append(
            {
                "agent": agent_name,
                "call_id": call["call_id"],
                "child_session_id": child_id,
                "dispatch_ordinal": call["ordinal"],
                "start_ordinal": starts[0]["ordinal"],
                "completion_ordinal": completions[0]["ordinal"],
                "request": safe_request,
                "request_hash": canonical_hash(safe_request),
            }
        )

    child_ids = [dispatch["child_session_id"] for dispatch in dispatches]
    if len(set(child_ids)) != len(specialists):
        raise ExecutionProofError("SPECIALISTS_SHARE_SESSION")
    if dispatches and first_wait is not None and max(item["dispatch_ordinal"] for item in dispatches) >= first_wait:
        raise ExecutionProofError("PARALLEL_DISPATCH_NOT_PROVEN")

    children: dict[str, Any] = {}
    child_record_sets: dict[str, Sequence[Mapping[str, Any]]] = {}
    for agent_name, rollout in child_rollouts.items():
        records = _load_jsonl(rollout)
        child_record_sets[agent_name] = records
        dispatch = next(item for item in dispatches if item["agent"] == agent_name)
        child = _child_proof(
            repository_root=repository_root,
            records=records,
            rollout_hash=file_hash(rollout),
            parent_session_id=parent_session_id,
            manifest=invocation_manifests[agent_name],
            task_prompt=task_prompts[agent_name],
            dispatch=dispatch,
        )
        expected_child_id = next(
            item["child_session_id"] for item in dispatches if item["agent"] == agent_name
        )
        if child["session_id"] != expected_child_id:
            raise ExecutionProofError(f"CHILD_SESSION_MISMATCH:{agent_name}")
        children[agent_name] = child

    telemetry_parts = [_rollout_telemetry(parent_records)] + [
        _rollout_telemetry(child_record_sets[name]) for name in specialists
    ]
    telemetry_available = all(item["status"] == "AVAILABLE" for item in telemetry_parts)
    proof: dict[str, Any] = {
        "schema_version": PROOF_SCHEMA_VERSION,
        "parent": {
            "session_id": parent_session_id,
            "model": parent_context.get("model"),
            "codex_runtime": f"codex-cli/{parent_meta.get('cli_version')}",
            "rollout_sha256": file_hash(parent_rollout),
        },
        "dispatches": sorted(dispatches, key=lambda item: item["dispatch_ordinal"]),
        "first_wait_ordinal": first_wait,
        "parallel_dispatch_proven": True,
        "independent_sessions_proven": True,
        "specialist_topology": list(specialists),
        "portfolio_council_skill_bound": "$product:portfolio-council" in "\n".join(
            _message_texts(parent_records, role="user")
        ),
        "children": children,
        "raw_prompt_or_reasoning_retained": False,
        "telemetry": {
            "status": "AVAILABLE" if telemetry_available else "MISSING_TELEMETRY",
            "input_tokens": sum(item["input_tokens"] for item in telemetry_parts) if telemetry_available else None,
            "output_tokens": sum(item["output_tokens"] for item in telemetry_parts) if telemetry_available else None,
            "cached_tokens": sum(item["cached_tokens"] for item in telemetry_parts) if telemetry_available else None,
            "latency_ms": telemetry_parts[0]["latency_ms"] if telemetry_available else None,
            "llm_calls": sum(item["llm_calls"] for item in telemetry_parts) if telemetry_available else None,
        },
    }
    proof["proof_hash"] = canonical_hash(proof)
    return proof


def verify_specialist_execution_proof(
    proof: Mapping[str, Any],
    *,
    invocation_manifests: Mapping[str, Mapping[str, Any]],
    reports: Mapping[str, Mapping[str, Any]],
    mcp_events: Sequence[Mapping[str, Any]],
) -> None:
    """Require Codex, configured Skill, structured output, and MCP evidence together."""

    body = dict(proof)
    claimed_hash = body.pop("proof_hash", None)
    if claimed_hash != canonical_hash(body):
        raise ExecutionProofError("EXECUTION_PROOF_HASH_MISMATCH")
    if not proof.get("parallel_dispatch_proven") or not proof.get("independent_sessions_proven"):
        raise ExecutionProofError("NATIVE_SPECIALIST_EXECUTION_NOT_PROVEN")
    if proof.get("raw_prompt_or_reasoning_retained") is not False:
        raise ExecutionProofError("UNMINIMIZED_CODEX_LOG")

    children = proof.get("children", {})
    specialists = tuple(str(name) for name in proof.get("specialist_topology", []))
    if set(specialists) != set(invocation_manifests) or proof.get("portfolio_council_skill_bound") is not True:
        raise ExecutionProofError("COUNCIL_SKILL_OR_TOPOLOGY_PROOF_INVALID")
    for agent_name in specialists:
        manifest = invocation_manifests.get(agent_name)
        report = reports.get(agent_name)
        child = children.get(agent_name) if isinstance(children, Mapping) else None
        if not isinstance(manifest, Mapping) or not isinstance(report, Mapping) or not isinstance(child, Mapping):
            raise ExecutionProofError(f"AUTHENTICITY_COMPONENT_MISSING:{agent_name}")
        if child.get("agent_role") != agent_name or child.get("model") != manifest.get("model"):
            raise ExecutionProofError(f"CHILD_IDENTITY_PROOF_INVALID:{agent_name}")
        if not child.get("role_instructions_loaded") or not child.get("configured_skills"):
            raise ExecutionProofError(f"SKILL_CONFIGURATION_PROOF_MISSING:{agent_name}")
        if child.get("task_binding", {}).get("verified") is not True:
            raise ExecutionProofError(f"CHILD_TASK_BINDING_PROOF_MISSING:{agent_name}")
        if child.get("unapproved_tool_calls") != 0 or child.get("raw_fixture_access_attempts") != 0:
            raise ExecutionProofError(f"FORBIDDEN_CHILD_ACCESS:{agent_name}")
        if report.get("skill_execution") != manifest.get("skill_execution"):
            raise ExecutionProofError(f"SKILL_OUTPUT_PROTOCOL_MISMATCH:{agent_name}")
        if child.get("final_structured_output_hash") != canonical_hash(report):
            raise ExecutionProofError(f"CHILD_REPORT_OUTPUT_HASH_MISMATCH:{agent_name}")
        allowed_tools = set(manifest.get("tool_permissions", []))
        agent_events = [
            event
            for event in mcp_events
            if event.get("run_id") == manifest.get("run_id")
            and event.get("agent") == agent_name
            and event.get("invocation_id") == manifest.get("invocation_id")
        ]
        if not agent_events:
            raise ExecutionProofError(f"MCP_EXECUTION_PROOF_MISSING:{agent_name}")
        for event in agent_events:
            if event.get("tool") not in allowed_tools or event.get("access_mode") != "read":
                raise ExecutionProofError(f"UNAUTHORIZED_MCP_EVENT:{agent_name}")
            if not isinstance(event.get("input_hash"), str) or not isinstance(event.get("output_hash"), str):
                raise ExecutionProofError(f"MCP_EVENT_HASH_MISSING:{agent_name}")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionProofError(f"PROOF_INPUT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise ExecutionProofError(f"PROOF_INPUT_NOT_OBJECT:{path.name}")
    return dict(value)


def _read_event_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ExecutionProofError("MCP_EVENT_LOG_MISSING") from exc
    for ordinal, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExecutionProofError(f"MCP_EVENT_LOG_INVALID:{ordinal}") from exc
        if not isinstance(value, Mapping):
            raise ExecutionProofError(f"MCP_EVENT_NOT_OBJECT:{ordinal}")
        events.append(dict(value))
    return events


def build_run_specialist_execution_proof(
    repository_root: Path,
    *,
    run_dir: Path,
    parent_rollout: Path,
    child_rollouts: Mapping[str, Path],
) -> dict[str, Any]:
    """Build, verify, and persist the minimized proof for one prepared run."""

    run_dir = run_dir.resolve()
    run_manifest = _read_object(run_dir / "run_manifest.json")
    if Path(str(run_manifest.get("output_dir", ""))).resolve() != run_dir:
        raise ExecutionProofError("RUN_DIRECTORY_IDENTITY_MISMATCH")
    run_id = str(run_manifest.get("run_id", ""))
    topology = validate_runtime_mode(
        run_mode=str(run_manifest.get("run_mode", "PRODUCT_COUNCIL")),
        ablation_profile=run_manifest.get("ablation_profile"),
    )
    specialists = tuple(agent for agent in topology if agent != "runtime_cio")
    manifests = {
        agent_name: _read_object(run_dir / "invocations" / f"{agent_name}.json")
        for agent_name in specialists
    }
    reports = {
        agent_name: _read_object(run_dir / "agents" / f"{agent_name}.json")
        for agent_name in specialists
    }
    task_prompts = {
        agent_name: (run_dir / "prompts" / f"{agent_name}.txt").read_text(
            encoding="utf-8"
        )
        for agent_name in specialists
    }
    if any(manifest.get("run_id") != run_id for manifest in manifests.values()):
        raise ExecutionProofError("CROSS_RUN_INVOCATION_MANIFEST")

    proof = build_specialist_execution_proof(
        repository_root,
        parent_rollout=parent_rollout,
        child_rollouts=child_rollouts,
        invocation_manifests=manifests,
        task_prompts=task_prompts,
        specialist_agents=specialists,
    )
    proof_body = dict(proof)
    proof_body.pop("proof_hash")
    proof_body["telemetry"] = {
        **proof_body["telemetry"],
        "model": run_manifest.get("model"),
        "trigger_reason": run_manifest.get("trigger_reason", "product_council"),
        "cache_provenance": "NEW_EXECUTION",
    }
    proof = proof_body
    proof["proof_hash"] = canonical_hash(proof)
    mcp_events = _read_event_jsonl(run_dir / "events" / "mcp" / "events.jsonl")
    verify_specialist_execution_proof(
        proof,
        invocation_manifests=manifests,
        reports=reports,
        mcp_events=mcp_events,
    )
    output_path = run_dir / "events" / "codex" / "specialist-execution-proof.json"
    if output_path.exists():
        raise ExecutionProofError("EXECUTION_PROOF_ALREADY_EXISTS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "run_id": run_id,
        "next_state": "EXECUTION_PROOF_VERIFIED",
        "proof_hash": proof["proof_hash"],
    }


def discover_run_rollouts(
    sessions_root: Path,
    *,
    run_dir: Path,
    run_id: str,
    specialist_agents: Sequence[str] = SPECIALIST_AGENTS,
) -> tuple[Path, dict[str, Path]]:
    """Resolve one parent and its role-bound children without exposing raw logs."""

    if not sessions_root.is_dir():
        raise ExecutionProofError("CODEX_SESSIONS_ROOT_NOT_FOUND")
    run_manifest = run_dir / "run_manifest.json"
    try:
        earliest_mtime = run_manifest.stat().st_mtime - 60
    except OSError as exc:
        raise ExecutionProofError("RUN_MANIFEST_NOT_FOUND") from exc
    candidates = [
        path
        for path in sessions_root.rglob("*.jsonl")
        if path.is_file() and path.stat().st_mtime >= earliest_mtime
    ]
    loaded: dict[Path, list[dict[str, Any]]] = {}
    parents: list[tuple[Path, str]] = []
    run_dir_text = str(run_dir.resolve())
    for path in candidates:
        try:
            records = _load_jsonl(path)
            meta = _session_meta(records)
        except ExecutionProofError:
            continue
        loaded[path] = records
        source = meta.get("source")
        if isinstance(source, Mapping) and "subagent" in source:
            continue
        user_text = "\n".join(_message_texts(records, role="user"))
        if run_id not in user_text or run_dir_text not in user_text:
            continue
        calls = _function_calls(records)
        dispatched = {
            str(call["arguments"].get("agent_type"))
            for call in calls
            if call.get("namespace") == "collaboration"
            and call.get("name") == "spawn_agent"
        }
        if set(specialist_agents) == dispatched & set(SPECIALIST_AGENTS):
            parents.append((path, str(meta.get("id", ""))))
    if len(parents) != 1:
        raise ExecutionProofError(f"RUN_PARENT_ROLLOUT_COUNT_INVALID:{len(parents)}")
    parent_path, parent_id = parents[0]

    children: dict[str, Path] = {}
    for path, records in loaded.items():
        if path == parent_path:
            continue
        meta = _session_meta(records)
        if meta.get("parent_thread_id") != parent_id:
            continue
        role = meta.get("agent_role")
        if role not in specialist_agents:
            continue
        if role in children:
            raise ExecutionProofError(f"DUPLICATE_CHILD_ROLE:{role}")
        children[str(role)] = path
    missing = set(specialist_agents) - set(children)
    if missing:
        raise ExecutionProofError(
            f"ROLE_BOUND_CHILD_ROLLOUT_MISSING:{','.join(sorted(missing))}"
        )
    return parent_path, children


def discover_and_build_run_specialist_execution_proof(
    repository_root: Path,
    *,
    run_dir: Path,
    sessions_root: Path,
) -> dict[str, Any]:
    run_manifest = _read_object(run_dir / "run_manifest.json")
    topology = validate_runtime_mode(
        run_mode=str(run_manifest.get("run_mode", "PRODUCT_COUNCIL")),
        ablation_profile=run_manifest.get("ablation_profile"),
    )
    specialists = tuple(agent for agent in topology if agent != "runtime_cio")
    parent, children = discover_run_rollouts(
        sessions_root,
        run_dir=run_dir,
        run_id=str(run_manifest.get("run_id", "")),
        specialist_agents=specialists,
    )
    return build_run_specialist_execution_proof(
        repository_root,
        run_dir=run_dir,
        parent_rollout=parent,
        child_rollouts=children,
    )
