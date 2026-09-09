from __future__ import annotations

import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from product.runtime.eval_execution_proof import (
    EvalExecutionProofError,
    build_eval_execution_proof,
    persist_eval_execution_proof,
    verify_eval_execution_proof,
)
from product.runtime.hashing import canonical_hash
from product.runtime.runtime_eval import finalize_eval_job, prepare_eval_job
from tests.test_native_execution_proof import message, write_jsonl
from tests.test_replay_capsule import ROOT, complete_run
from tests.test_runtime_eval_job import semantic_result, write_json


def rollouts(
    root: Path,
    eval_dir: Path,
    semantic: dict,
    *,
    child_role: str = "dev_eval",
    plaintext_bindings: bool = True,
) -> tuple[Path, Path]:
    manifest = json.loads((eval_dir / "input-manifest.json").read_text(encoding="utf-8"))
    parent_id = "eval-parent"
    parent = [
        {"timestamp": "2026-09-07T00:00:00Z", "type": "session_meta", "payload": {"id": parent_id, "cli_version": "0.153.4"}},
        {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
        message("user", f"$runtime-eval-grading eval_id={manifest['eval_id']} eval_dir={eval_dir}"),
        {"type": "response_item", "payload": {"type": "function_call", "namespace": "collaboration", "name": "spawn_agent", "call_id": "eval-call", "arguments": json.dumps({"agent_type": "dev_eval", "task_name": "semantic_grading", "fork_turns": "none", "message": "gAAAA" + "A" * 120})}},
        {"timestamp": "2026-09-07T00:00:03Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30}}}},
    ]
    with (ROOT / ".codex" / "agents" / "dev_eval.toml").open("rb") as handle:
        instructions = tomllib.load(handle)["developer_instructions"]
    hashes = manifest["source_hashes"]
    child_user = (
        f"eval_id={manifest['eval_id']} eval_dir={eval_dir} "
        f"{hashes['grader_prompt']} {hashes['rubric']} {hashes['semantic_input']}"
    ) if plaintext_bindings else f"eval_dir={eval_dir}"
    child = [
        {"timestamp": "2026-09-07T00:00:00Z", "type": "session_meta", "payload": {"id": "eval-child", "parent_thread_id": parent_id, "agent_role": child_role, "cli_version": "0.153.4"}},
        message("developer", f"runtime\n{instructions}\nend"),
        message("user", child_user),
        {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
        message("assistant", json.dumps(semantic, sort_keys=True)),
        {"timestamp": "2026-09-07T00:00:02Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 50, "cached_input_tokens": 10, "output_tokens": 40}}}},
    ]
    parent_path, child_path = root / "parent.jsonl", root / "child.jsonl"
    write_jsonl(parent_path, parent)
    write_jsonl(child_path, child)
    return parent_path, child_path


class EvalExecutionProofTests(unittest.TestCase):
    def test_real_grader_lineage_is_hash_bound_and_required_for_authentic_eval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, eval_dir = root / "run", root / "eval"
            complete_run(run_dir, "eval-proof-run")
            prepare_eval_job(ROOT, run_dir=run_dir, eval_dir=eval_dir, eval_id="eval-proof")
            manifest_path = eval_dir / "input-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["authenticity_required"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            semantic = semantic_result(eval_dir)
            semantic["grader"]["model"] = "gpt-5.6-terra"
            semantic.pop("output_hash")
            semantic["output_hash"] = canonical_hash(semantic)
            semantic_path = root / "semantic.json"
            write_json(semantic_path, semantic)
            parent, child = rollouts(root, eval_dir, semantic)
            proof = build_eval_execution_proof(
                ROOT,
                eval_dir=eval_dir,
                semantic_result_path=semantic_path,
                parent_rollout=parent,
                child_rollout=child,
            )
            persist_eval_execution_proof(proof, eval_dir=eval_dir)
            verify_eval_execution_proof(ROOT, eval_dir=eval_dir, semantic_result=semantic)
            result = finalize_eval_job(ROOT, eval_dir=eval_dir, semantic_result_path=semantic_path)
            self.assertEqual(result["grader"]["execution_proof_hash"], proof["proof_hash"])
            self.assertGreater(result["grader"]["telemetry"]["input_tokens"], 0)

    def test_wrong_child_agent_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, eval_dir = root / "run", root / "eval"
            complete_run(run_dir, "eval-proof-wrong-agent")
            prepare_eval_job(ROOT, run_dir=run_dir, eval_dir=eval_dir, eval_id="eval-proof-wrong")
            semantic = semantic_result(eval_dir)
            semantic["grader"]["model"] = "gpt-5.6-terra"
            semantic.pop("output_hash")
            semantic["output_hash"] = canonical_hash(semantic)
            semantic_path = root / "semantic.json"
            write_json(semantic_path, semantic)
            parent, child = rollouts(root, eval_dir, semantic, child_role="runtime_cio")
            with self.assertRaisesRegex(EvalExecutionProofError, "IDENTITY_INVALID"):
                build_eval_execution_proof(
                    ROOT,
                    eval_dir=eval_dir,
                    semantic_result_path=semantic_path,
                    parent_rollout=parent,
                    child_rollout=child,
                )

    def test_protected_dispatch_and_structured_output_bind_task_when_child_prompt_is_opaque(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir, eval_dir = root / "run", root / "eval"
            complete_run(run_dir, "eval-proof-protected")
            prepare_eval_job(ROOT, run_dir=run_dir, eval_dir=eval_dir, eval_id="eval-proof-protected")
            semantic = semantic_result(eval_dir)
            semantic["grader"]["model"] = "gpt-5.6-terra"
            semantic.pop("output_hash")
            semantic["output_hash"] = canonical_hash(semantic)
            semantic_path = root / "semantic.json"
            write_json(semantic_path, semantic)
            parent, child = rollouts(root, eval_dir, semantic, plaintext_bindings=False)
            proof = build_eval_execution_proof(
                ROOT,
                eval_dir=eval_dir,
                semantic_result_path=semantic_path,
                parent_rollout=parent,
                child_rollout=child,
            )
            self.assertEqual(proof["task_binding_method"], "protected_dispatch_plus_structured_output")


if __name__ == "__main__":
    unittest.main()
