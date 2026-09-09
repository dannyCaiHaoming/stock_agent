"""指令加载接缝的合成事件测试；不调用 Codex 或读取历史运行包。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.execution_proof import ExecutionProofError, verify_agents_instruction_load
from product.runtime.hashing import canonical_hash, file_hash


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def bind_instruction_fixture(repo, run, *, prepend_reads=True):
    """给测试自己的临时事件绑定本次 invocation，不用于真实产物。"""
    repo, run = repo.resolve(), run.resolve()
    invocation_dir = run / "invocation"
    manifest = json.loads((run / "run_manifest.json").read_text())
    prompt = invocation_dir / "prompt.txt"
    events = invocation_dir / "codex-events.jsonl"
    names = [name for name in ("AGENTS.md", "product/AGENTS.md") if (repo / name).is_file()]
    if prepend_reads:
        records = [json.loads(line) for line in events.read_text().splitlines()]
        reads = [{"type": "item.completed", "item": {
            "type": "command_execution", "command": f"cat '{repo / name}'",
            "exit_code": 0, "aggregated_output": (repo / name).read_text(),
        }} for name in names]
        records[1:1] = reads
        events.write_text("\n".join(json.dumps(item) for item in records) + "\n")
    environment = {
        "run_id": manifest["run_id"], "run_dir": str(run), "repo_root": str(repo),
        "cwd": str(repo / "product"), "command": ["codex", "exec", "-"],
        "resource_hashes": {"agents_md": {name: file_hash(repo / name) for name in names},
                            "prompt": file_hash(prompt)},
    }
    write_json(invocation_dir / "environment-manifest.json", environment)
    invocation = {
        "run_id": manifest["run_id"], "cwd": environment["cwd"], "command": environment["command"],
        "prompt_path": str(prompt), "prompt_sha256": file_hash(prompt),
        "environment_manifest_sha256": file_hash(invocation_dir / "environment-manifest.json"),
    }
    invocation["invocation_hash"] = canonical_hash(invocation)
    write_json(invocation_dir / "invocation-manifest.json", invocation)


class AgentsInstructionProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name).resolve() / "repo with spaces"
        self.run = Path(self.temp.name).resolve() / "run"
        self.invocation = self.run / "invocation"
        self.invocation.mkdir(parents=True)
        for name in ("AGENTS.md", "product/AGENTS.md", "product/skills/portfolio-council/SKILL.md"):
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"中文指令 {name}\n")
        write_json(self.run / "run_manifest.json", {"run_id": "synthetic-1", "output_dir": str(self.run)})
        (self.invocation / "prompt.txt").write_text("fixture prompt only")
        skill = self.repo / "product/skills/portfolio-council/SKILL.md"
        records = [{"type": "thread.started", "thread_id": "session-1"},
                   {"type": "item.completed", "item": {"type": "command_execution",
                    "command": f"cat '{skill}'", "exit_code": 0, "aggregated_output": skill.read_text()}}]
        (self.invocation / "codex-events.jsonl").write_text("\n".join(json.dumps(item) for item in records))
        bind_instruction_fixture(self.repo, self.run)

    def verify(self):
        return verify_agents_instruction_load(self.repo, run_dir=self.run)

    def test_exact_ordered_reads_bind_run_session_prompt_and_events(self):
        proof = self.verify()
        self.assertEqual(proof["status"], "LOAD_VERIFIED")
        self.assertEqual(proof["run_id"], "synthetic-1")
        self.assertEqual(proof["session_id"], "session-1")
        self.assertEqual(set(proof["resources"]), {"AGENTS.md", "product/AGENTS.md"})
        self.assertEqual(proof["codex_events_sha256"], file_hash(self.invocation / "codex-events.jsonl"))
        self.assertEqual(proof["prompt_sha256"], file_hash(self.invocation / "prompt.txt"))

    def test_missing_failed_truncated_wrong_path_and_duplicate_reads_fail(self):
        path = self.invocation / "codex-events.jsonl"
        baseline = [json.loads(line) for line in path.read_text().splitlines()]
        for mutation in ("missing", "failed", "truncated", "wrong_path", "duplicate", "order", "session"):
            with self.subTest(mutation=mutation):
                records = copy.deepcopy(baseline)
                if mutation == "missing":
                    records.pop(1)
                elif mutation == "failed":
                    records[1]["item"]["exit_code"] = 1
                elif mutation == "truncated":
                    records[1]["item"]["aggregated_output"] = "部分内容"
                elif mutation == "wrong_path":
                    records[1]["item"]["command"] = "cat other/AGENTS.md"
                elif mutation == "duplicate":
                    records.append(records[1])
                elif mutation == "order":
                    records[1], records[2] = records[2], records[1]
                else:
                    records.pop(0)
                path.write_text("\n".join(json.dumps(item) for item in records))
                with self.assertRaises(ExecutionProofError):
                    self.verify()

    def test_hash_only_or_forged_summary_cannot_replace_events(self):
        (self.invocation / "codex-events.jsonl").write_text(json.dumps({"type": "thread.started", "thread_id": "session-1"}))
        with self.assertRaisesRegex(ExecutionProofError, "AGENTS_LOAD_NOT_PROVEN"):
            self.verify()

    def test_resource_drift_after_invocation_fails(self):
        (self.repo / "AGENTS.md").write_text("changed")
        with self.assertRaisesRegex(ExecutionProofError, "VERSION_MISMATCH"):
            self.verify()

    def test_prompt_or_invocation_or_environment_drift_fails(self):
        for name in ("prompt.txt", "invocation-manifest.json", "environment-manifest.json"):
            with self.subTest(name=name):
                path = self.invocation / name
                original = path.read_text()
                path.write_text(original + " " if name != "prompt.txt" else "changed")
                # Invocation canonical hash ignores harmless whitespace; change identity instead.
                if name == "invocation-manifest.json":
                    value = json.loads(original)
                    value["run_id"] = "other-run"
                    write_json(path, value)
                with self.assertRaisesRegex(ExecutionProofError, "BINDING_INVALID"):
                    self.verify()
                path.write_text(original)

    def test_frozen_workspace_does_not_borrow_host_root_instruction(self):
        (self.repo / "AGENTS.md").unlink()  # 仅删除本测试创建的临时文件。
        manifest = json.loads((self.run / "run_manifest.json").read_text())
        manifest["execution_replay"] = {"workspace": str(self.repo)}
        write_json(self.run / "run_manifest.json", manifest)
        bind_instruction_fixture(self.repo, self.run, prepend_reads=False)
        self.assertEqual(set(self.verify()["resources"]), {"product/AGENTS.md"})
