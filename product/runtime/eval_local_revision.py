"""显式 Runtime Eval 的原 dev_eval 局部修订；不另建 launcher 或评分器。

沿现有 rollout 收集入口向协调线程返回反馈，由 Codex 原生 send_input
送回原 child。两版输入与真实会话持续绑定，最后仍经原五维评分校验。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path

from .hashing import canonical_hash, file_hash, legacy_envelope_hash, verify_legacy_envelope_hash
from .local_revision import bind, resolve, verify_binding, _path
from .schema_validation import schema_issue_locations
from .execution_proof import _final_structured_output, _function_calls, _message_texts

VERSION = "runtime-eval-local-revision/1.0.0"
RECORD = "semantic-revision.json"


def _sources(repository: Path, root: Path, context: dict) -> dict:
    from .runtime_eval import semantic_output_schema, _source_tree_hash, _rubric_path, verify_runtime_eval_model_input
    manifest = context["manifest"]
    hashes = manifest["source_hashes"]
    checks = {"semantic_input": canonical_hash(json.loads(_path(root, "grader-input.json").read_text())),
              "semantic_output_schema": canonical_hash(json.loads(_path(root, "semantic-output-schema.json").read_text())),
              "grader_prompt": canonical_hash({"prompt": _path(root, "grader-prompt.txt").read_text().removesuffix("\n")}),
              "run_tree": _source_tree_hash(Path(manifest["run_dir"])),
              "rubric": canonical_hash(json.loads(_rubric_path(repository, Path(manifest["run_dir"])).read_text()))}
    if (any(hashes.get(key) != value for key, value in checks.items())
            or json.loads(_path(root, "semantic-output-schema.json").read_text()) != semantic_output_schema(repository, native_draft=True)):
        raise ValueError("EVAL_LOCAL_REVISION_INPUT_DRIFT")
    model_input = verify_runtime_eval_model_input(root, manifest)
    if model_input is not None:
        checks["semantic_model_input"] = canonical_hash(model_input)
    return {"eval_id": manifest["eval_id"], "agent": "dev_eval", "model": context["child_context"]["model"],
            "manifest_hash": canonical_hash(manifest), "agent_hash": file_hash(context["agent_path"]),
            "skill_hash": file_hash(context["skill_path"]), "input_hashes": checks}


def _author(context: dict, message: str, task: dict) -> tuple[dict, dict]:
    # 由真实父/子 rollout 产生身份；不是伪造 SubagentStop 原生事件。
    payload = {"session_id": context["parent_meta"]["id"], "agent_id": context["child_meta"]["id"],
               "agent_type": "dev_eval", "model": context["child_context"]["model"],
               "last_assistant_message": message}
    record = {"version": VERSION, "execution_context": "CODEX_ROLLOUT_SUBAGENT",
              "identity_binding": {"status": "BOUND", "source": "ACTUAL_ROLLOUT_AND_MANIFEST_READ"},
              "trusted_task_binding": task}
    return payload, record


def _assistant_outputs(records):
    # 原生 commentary 不是提交；不按 JSON 是否合法去猜选较早的 final。
    return _message_texts([item for item in records if item.get("payload", {}).get("phase") != "commentary"], role="assistant")


def _last_message(context: dict) -> str:
    texts = _assistant_outputs(context["child_records"])
    if not texts or not texts[-1].strip():
        raise ValueError("EVAL_LOCAL_REVISION_DRAFT_MISSING")
    # 不从较早的合法对象猜选最后一稿。
    return texts[-1]


def _save_json(root: Path, ref: str, value: dict) -> None:
    path = _path(root, ref)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def _raw(root: Path, message: str, attempt: int) -> dict:
    ref = f"semantic-attempt-{attempt}.json"
    fd = os.open(_path(root, ref), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(message + ("" if message.endswith("\n") else "\n"))
        stream.flush()
        os.fsync(stream.fileno())
    return {"raw_path": ref, "raw_output_hash": canonical_hash({"assistant_message": message})}


def _prefix(path: Path) -> dict:
    data = path.read_bytes()
    return {"bytes": len(data), "file_prefix_hash": hashlib.sha256(data).hexdigest()}


def _continuation(repository: Path, root: Path, parent: Path, child: Path, context: dict):
    first = json.loads(_path(root, RECORD).read_text())
    verify_legacy_envelope_hash(first, hash_field="event_hash", location=RECORD)
    task = _sources(repository, root, context)
    payload, record = _author(context, _last_message(context), task)
    if first["trusted_task_binding"] != task:
        raise ValueError("EVAL_LOCAL_REVISION_CONFIGURATION_DRIFT")
    if verify_binding(root, payload, record, first) is None:
        raise ValueError("EVAL_LOCAL_REVISION_NOT_AUTHORIZED")
    for path, name in ((parent, "parent_prefix"), (child, "child_prefix")):
        prefix = first[name]
        data = path.read_bytes()[:prefix["bytes"]]
        if len(data) != prefix["bytes"] or hashlib.sha256(data).hexdigest() != prefix["file_prefix_hash"]:
            raise ValueError("EVAL_LOCAL_REVISION_ROLLOUT_DRIFT")
    # 正好一次真实原 child 续投；不能只在文件里替换 JSON 或启动新 grader。
    appended = parent.read_bytes()[first["parent_prefix"]["bytes"]:]
    calls = _function_calls([json.loads(line) for line in appended.decode().splitlines() if line.strip()])
    sent = [item for item in calls if item["name"] == "send_input"]
    if (len(sent) != 1 or sent[0]["namespace"] != "collaboration"
            or sent[0]["arguments"].get("id") != payload["agent_id"]
            or sent[0]["arguments"].get("message") != first["feedback"]):
        raise ValueError("EVAL_LOCAL_REVISION_CONTINUATION_MISSING")
    base_records = [json.loads(line) for line in child.read_bytes()[:first["child_prefix"]["bytes"]].decode().splitlines() if line.strip()]
    delta = context["child_records"][len(base_records):]
    if _message_texts(delta, role="user") != [first["feedback"]]:
        raise ValueError("EVAL_LOCAL_REVISION_FEEDBACK_NOT_DELIVERED")
    messages = _assistant_outputs(delta)
    if len(messages) != 1 or messages[0] != payload["last_assistant_message"]:
        raise ValueError("EVAL_LOCAL_REVISION_LIMIT_EXHAUSTED")
    return first, payload, record


def _bound_candidate(repository: Path, root: Path, parent: Path, child: Path, context: dict) -> tuple[dict, dict]:
    first, payload, record = _continuation(repository, root, parent, child, context)
    candidate = resolve(root, payload, record, first)
    draft = json.loads(candidate["last_assistant_message"])
    from .eval_execution_proof import normalize_native_grade
    normalize_native_grade(draft, context["manifest"], model=payload["model"])
    return draft, record


def resolved(repository: Path, *, eval_dir: Path, parent_rollout: Path, child_rollout: Path, context: dict) -> dict:
    root = eval_dir.resolve()
    if context["manifest"].get("local_revision_contract"):
        _sources(repository, root, context)
    if _path(root, RECORD).is_file():
        draft, record = _bound_candidate(repository, root, parent_rollout, child_rollout, context)
        accepted = json.loads(_path(root, "semantic-revision-accepted.json").read_text())
        verify_legacy_envelope_hash(accepted, hash_field="event_hash", location="semantic-revision-accepted.json")
        if accepted.get("local_revision") != record.get("local_revision") or accepted.get("candidate_hash") != canonical_hash(draft):
            raise ValueError("EVAL_LOCAL_REVISION_PROOF_DRIFT")
        return draft
    # 首稿仍由原 native normalizer 校验；未经局部反馈的第二份完整稿不猜选。
    if context["manifest"].get("semantic_output_delivery") == "native-draft/1.0.0":
        message = _last_message(context)
        if len(_assistant_outputs(context["child_records"])) != 1:
            raise ValueError("EVAL_LOCAL_REVISION_NOT_AUTHORIZED")
        raw = _path(root, "semantic-attempt-1.json")
        if raw.exists() and raw.read_text() != message + ("" if message.endswith("\n") else "\n"):
            raise ValueError("EVAL_LOCAL_REVISION_BASE_DRIFT")
        return json.loads(message)
    return _final_structured_output(context["child_records"], agent_name="dev_eval")


def collect(repository: Path, *, eval_dir: Path, parent_rollout: Path, child_rollout: Path, context: dict):
    from .eval_execution_proof import normalize_native_grade
    root = eval_dir.resolve()
    task = _sources(repository, root, context)  # 输入、身份先验；错误身份不能占目标额度。
    with _path(root, "semantic-revision.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if _path(root, "semantic-attempt-2.json").exists():
            raise ValueError("EVAL_LOCAL_REVISION_LIMIT_EXHAUSTED")
        if _path(root, RECORD).is_file():
            # 尚未续投、冒用会话或损坏基础稿时，不能占用原 Agent 的第二稿槽位。
            first, payload, record = _continuation(repository, root, parent_rollout, child_rollout, context)
            raw = _raw(root, payload["last_assistant_message"], 2)
            draft, record = _bound_candidate(repository, root, parent_rollout, child_rollout, context)
            record.update(output_capture=raw, candidate_hash=canonical_hash(draft))
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
            _save_json(root, "semantic-revision-accepted.json", record)
            return draft, None
        if _path(root, "semantic-attempt-1.json").exists():
            raise ValueError("EVAL_LOCAL_REVISION_NOT_AUTHORIZED")
        if len(_assistant_outputs(context["child_records"])) != 1:
            raise ValueError("EVAL_LOCAL_REVISION_NOT_AUTHORIZED")
        message = _last_message(context)
        payload, record = _author(context, message, task)
        raw = _raw(root, message, 1)
        # 重复键、不可解析消息不产生宽松修订；保留原文但不发布评分。
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("EVAL_LOCAL_REVISION_DUPLICATE_KEY")
                value[key] = item
            return value
        draft = json.loads(message, object_pairs_hook=unique)
        try:
            normalize_native_grade(draft, context["manifest"], model=payload["model"])
            return draft, None
        except ValueError as exc:
            if (not isinstance(draft, dict) or set(draft) - {"schema_version", "eval_id", "dimensions"}
                    or draft.get("eval_id") != context["manifest"]["eval_id"]
                    or draft.get("schema_version") != "semantic-rubric-draft/1.0.0"):
                raise
            schema = json.loads(_path(root, "semantic-output-schema.json").read_text())
            findings = schema_issue_locations(draft, schema)
            repair = {"validation_error": str(exc)}
            binding = bind(root, payload, record, raw, repair, findings)
            if binding is None:
                raise
            feedback = json.dumps({"base_draft_ref": binding["base_draft_ref"], "allowed_paths": binding["allowed_paths"],
                                   "instruction": "这是原 dev_eval 的唯一局部纠正；只返回 base_draft_ref + changes 补丁，"
                                                  "仅改允许字段，其余评分和理由保持不变。不猜引用、不重新评分、不抄写 hash。"
                                                  "第二次仍错则终止；完整五维契约会再验。"}, ensure_ascii=False, sort_keys=True)
            record.update(output_capture=raw, repair_request={**repair, **binding}, feedback=feedback,
                          parent_prefix=_prefix(parent_rollout), child_prefix=_prefix(child_rollout))
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
            _save_json(root, RECORD, record)
            return None, {"eval_id": context["manifest"]["eval_id"], "next_state": "EVAL_LOCAL_REVISION_REQUIRED",
                          "child_session_id": payload["agent_id"], "feedback": feedback}
