from __future__ import annotations

import copy
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from product.runtime.execution_proof import (
    ExecutionProofError,
    build_ephemeral_run_specialist_execution_proof,
    build_run_specialist_execution_proof,
    build_specialist_execution_proof,
    discover_run_rollouts,
    _verify_isolated_resource_load,
    verify_specialist_execution_proof,
)
from product.runtime.codex_hook_recorder import minimize_hook_event
from product.runtime.hashing import canonical_hash
from tests.test_agents_instruction_proof import bind_instruction_fixture
from product.runtime.invocation import (
    OUTPUT_SCHEMAS,
    build_specialist_output_schema,
    create_invocation_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ("runtime_company_analyst", "runtime_skeptic")


def write_jsonl(path: Path, records):
    path.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")


def message(role: str, text: str):
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": "input_text", "text": text}],
        },
    }


class NativeExecutionProofTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        schema_dir = Path(self.temp_dir.name) / "schemas"
        schema_dir.mkdir(parents=True)
        self.run_id = "proof-run"
        self.prompts = {
            agent: f"RUN {self.run_id} AGENT {agent}" for agent in AGENTS
        }
        self.inputs = {
            agent: {
                "run_id": self.run_id,
                "agent": agent,
                "allowed_evidence_ids": ["ev-1"],
            }
            for agent in AGENTS
        }
        self.schema_paths = {}
        for agent in AGENTS:
            path = schema_dir / Path(OUTPUT_SCHEMAS[agent]).name
            path.write_text(
                json.dumps(
                    build_specialist_output_schema(
                        ROOT,
                        agent_name=agent,
                        allowed_evidence_ids=["ev-1"],
                    ),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self.schema_paths[agent] = path
        self.manifests = {
            agent: create_invocation_manifest(
                ROOT,
                run_id=self.run_id,
                agent_name=agent,
                agent_input=self.inputs[agent],
                task_prompt=self.prompts[agent],
                model="gpt-5.6-terra",
                evidence_ids=["ev-1"],
                output_schema_path=self.schema_paths[agent],
            )
            for agent in AGENTS
        }

    def test_skill_load_requires_exact_successful_runtime_event(self):
        skill_path = ROOT / "product" / "skills" / "portfolio-council" / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")
        event = {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": f"sed -n '1,999p' {skill_path}",
                "exit_code": 0,
                "aggregated_output": skill_text,
            },
        }
        result = _verify_isolated_resource_load([event], resource_path=skill_path)
        self.assertEqual(result["status"], "LOAD_VERIFIED")
        for records in (
            [],
            [{**event, "item": {**event["item"], "exit_code": 1}}],
            [{**event, "item": {**event["item"], "aggregated_output": skill_text + "drift"}}],
            [event, event],
        ):
            with self.assertRaisesRegex(
                ExecutionProofError, "PORTFOLIO_COUNCIL_SKILL_LOAD_NOT_PROVEN"
            ):
                _verify_isolated_resource_load(records, resource_path=skill_path)
    def tearDown(self):
        self.temp_dir.cleanup()

    def _report(self, agent):
        return {
            "agent": agent,
            "run_id": self.run_id,
            "invocation_id": self.manifests[agent]["invocation_id"],
            "skill_execution": self.manifests[agent]["skill_execution"],
        }

    def _rollouts(
        self,
        directory: Path,
        *,
        second_dispatch_after_wait=False,
        raw_fixture_access_agent=None,
        protected_child_input=False,
        protected_message="gAAAA" + "A" * 120,
        agents=AGENTS,
    ):
        parent_id = "parent-session"
        call_ids = {agent: f"call-{index}" for index, agent in enumerate(agents, 1)}
        child_ids = {agent: f"child-{index}" for index, agent in enumerate(agents, 1)}
        parent = [
            {"timestamp": "2026-09-07T00:00:00Z", "type": "session_meta", "payload": {"id": parent_id, "cli_version": "0.153.4"}},
            {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
            message("user", f"$product:portfolio-council run_id={self.run_id}"),
        ]
        for index, agent in enumerate(agents):
            if second_dispatch_after_wait and index == 1:
                parent.append(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "namespace": "collaboration",
                            "name": "wait_agent",
                            "call_id": "wait-1",
                            "arguments": "{}",
                        },
                    }
                )
            parent.extend(
                [
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "namespace": "collaboration",
                            "name": "spawn_agent",
                            "call_id": call_ids[agent],
                            "arguments": json.dumps(
                                {
                                    "agent_type": agent,
                                    "task_name": (
                                        "company_research"
                                        if agent == "runtime_company_analyst"
                                        else "independent_skeptic"
                                    ),
                                    "fork_turns": "none",
                                    "message": protected_message,
                                }
                            ),
                        },
                    },
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "item_completed",
                            "item": {
                                "type": "SubAgentActivity",
                                "id": call_ids[agent],
                                "kind": "started",
                                "agent_thread_id": child_ids[agent],
                                "agent_path": f"/{agent}",
                            },
                        },
                    },
                ]
            )
        parent.append(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "namespace": "collaboration",
                    "name": "wait_agent",
                    "call_id": "wait-final",
                    "arguments": "{}",
                },
            }
        )
        for agent in agents:
            parent.append(
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "item_completed",
                        "item": {
                            "type": "SubAgentActivity",
                            "id": f"completed-{child_ids[agent]}",
                            "kind": "completed",
                            "agent_thread_id": child_ids[agent],
                            "agent_path": f"/{agent}",
                        },
                    },
                }
            )
        parent.append({
            "timestamp": "2026-09-07T00:00:03Z",
            "type": "event_msg",
            "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30}}},
        })
        parent_path = directory / "parent.jsonl"
        write_jsonl(parent_path, parent)

        children = {}
        for agent in agents:
            manifest = self.manifests[agent]
            with Path(manifest["agent"]["path"]).open("rb") as handle:
                instructions = tomllib.load(handle)["developer_instructions"]
            child_path = directory / f"{agent}.jsonl"
            task = f"{self.prompts[agent]} run_id={self.run_id} invocation_id={manifest['invocation_id']}"
            records = [
                {
                    "timestamp": "2026-09-07T00:00:00Z",
                    "type": "session_meta",
                    "payload": {
                        "id": child_ids[agent],
                        "parent_thread_id": parent_id,
                        "agent_role": agent,
                        "thread_source": "subagent",
                        "cli_version": "0.153.4",
                        "multi_agent_version": "v2",
                    },
                },
                message("developer", f"runtime envelope\n{instructions}\nend"),
                {"type": "turn_context", "payload": {"model": "gpt-5.6-terra"}},
            ]
            if not protected_child_input:
                records.insert(2, message("user", task))
            if agent == raw_fixture_access_agent:
                records.append(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "function_call",
                            "namespace": "shell",
                            "name": "exec_command",
                            "call_id": "forbidden-read",
                            "arguments": json.dumps(
                                {"cmd": "read audit/fixture_snapshot.json"}
                            ),
                        },
                    }
                )
            else:
                logical_tool = self.manifests[agent]["tool_permissions"][0]
                _, tool_name = logical_tool.split(".", 1)
                records.append(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "custom_tool_call",
                            "name": "exec",
                            "call_id": f"mcp-{agent}",
                            "input": (
                                "const r = await tools.mcp__fixture_runtime__"
                                f"{tool_name}({{run_id: 'proof-run'}}); text(r);"
                            ),
                        },
                    }
                )
            records.append(
                message(
                    "assistant",
                    json.dumps(self._report(agent), sort_keys=True),
                )
            )
            records.append({
                "timestamp": "2026-09-07T00:00:02Z",
                "type": "event_msg",
                "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 40, "cached_input_tokens": 10, "output_tokens": 20}}},
            })
            write_jsonl(
                child_path,
                records,
            )
            children[agent] = child_path
        return parent_path, children

    def _reports_and_events(self):
        reports = {
            agent: self._report(agent)
            for agent in AGENTS
        }
        events = []
        for agent in AGENTS:
            manifest = self.manifests[agent]
            events.append(
                {
                    "run_id": self.run_id,
                    "agent": agent,
                    "invocation_id": manifest["invocation_id"],
                    "tool": manifest["tool_permissions"][0],
                    "access_mode": "read",
                    "input_hash": "a" * 64,
                    "output_hash": "b" * 64,
                }
            )
        return reports, events

    def test_minimized_proof_requires_parallel_distinct_native_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, children = self._rollouts(Path(directory))
            proof = build_specialist_execution_proof(
                ROOT,
                parent_rollout=parent,
                child_rollouts=children,
                invocation_manifests=self.manifests,
                task_prompts=self.prompts,
            )
            self.assertTrue(proof["parallel_dispatch_proven"])
            self.assertTrue(proof["independent_sessions_proven"])
            self.assertFalse(proof["raw_prompt_or_reasoning_retained"])
            self.assertEqual(proof["telemetry"]["status"], "AVAILABLE")
            self.assertEqual(proof["telemetry"]["input_tokens"], 180)
            self.assertEqual(proof["telemetry"]["cached_tokens"], 40)
            self.assertEqual(proof["telemetry"]["latency_ms"], 3000)
            self.assertNotIn(self.prompts[AGENTS[0]], json.dumps(proof))
            self.assertEqual(
                {item["agent"] for item in proof["dispatches"]}, set(AGENTS)
            )
            reports, events = self._reports_and_events()
            verify_specialist_execution_proof(
                proof,
                invocation_manifests=self.manifests,
                reports=reports,
                mcp_events=events,
            )

    def test_dispatch_after_wait_fails_parallel_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, children = self._rollouts(
                Path(directory), second_dispatch_after_wait=True
            )
            with self.assertRaisesRegex(ExecutionProofError, "DISPATCH_AFTER_WAIT"):
                build_specialist_execution_proof(
                    ROOT,
                    parent_rollout=parent,
                    child_rollouts=children,
                    invocation_manifests=self.manifests,
                    task_prompts=self.prompts,
                )

    def test_zero_and_one_specialist_ablation_topologies_have_native_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, specialists in enumerate(((), ("runtime_company_analyst",))):
                case = root / str(index)
                case.mkdir()
                parent, children = self._rollouts(case, agents=specialists)
                proof = build_specialist_execution_proof(
                    ROOT,
                    parent_rollout=parent,
                    child_rollouts=children,
                    invocation_manifests={name: self.manifests[name] for name in specialists},
                    task_prompts={name: self.prompts[name] for name in specialists},
                    specialist_agents=specialists,
                )
                self.assertEqual(proof["specialist_topology"], list(specialists))
                self.assertTrue(proof["portfolio_council_skill_bound"])
                reports, events = self._reports_and_events()
                verify_specialist_execution_proof(
                    proof,
                    invocation_manifests={name: self.manifests[name] for name in specialists},
                    reports={name: reports[name] for name in specialists},
                    mcp_events=events,
                )

    def test_current_codex_protected_dispatch_binds_through_structured_output(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, children = self._rollouts(
                Path(directory), protected_child_input=True
            )
            proof = build_specialist_execution_proof(
                ROOT,
                parent_rollout=parent,
                child_rollouts=children,
                invocation_manifests=self.manifests,
                task_prompts=self.prompts,
            )
            for agent in AGENTS:
                self.assertEqual(
                    proof["children"][agent]["task_binding"]["binding_method"],
                    "protected_dispatch_plus_structured_output",
                )

    def test_opaque_placeholder_cannot_replace_protected_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, children = self._rollouts(
                Path(directory),
                protected_child_input=True,
                protected_message="encrypted",
            )
            with self.assertRaisesRegex(ExecutionProofError, "CHILD_TASK_BINDING_MISSING"):
                build_specialist_execution_proof(
                    ROOT,
                    parent_rollout=parent,
                    child_rollouts=children,
                    invocation_manifests=self.manifests,
                    task_prompts=self.prompts,
                )

    def test_self_report_without_codex_skill_or_mcp_proof_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, children = self._rollouts(Path(directory))
            proof = build_specialist_execution_proof(
                ROOT,
                parent_rollout=parent,
                child_rollouts=children,
                invocation_manifests=self.manifests,
                task_prompts=self.prompts,
            )
            reports, events = self._reports_and_events()
            with self.assertRaisesRegex(ExecutionProofError, "MCP_EXECUTION_PROOF_MISSING"):
                verify_specialist_execution_proof(
                    proof,
                    invocation_manifests=self.manifests,
                    reports=reports,
                    mcp_events=[],
                )
            bad = copy.deepcopy(proof)
            bad["children"][AGENTS[0]]["configured_skills"] = []
            body = dict(bad)
            body.pop("proof_hash")
            bad["proof_hash"] = canonical_hash(body)
            with self.assertRaisesRegex(ExecutionProofError, "SKILL_CONFIGURATION_PROOF_MISSING"):
                verify_specialist_execution_proof(
                    bad,
                    invocation_manifests=self.manifests,
                    reports=reports,
                    mcp_events=events,
                )

    def test_saved_report_must_equal_child_final_structured_output(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, children = self._rollouts(Path(directory))
            proof = build_specialist_execution_proof(
                ROOT,
                parent_rollout=parent,
                child_rollouts=children,
                invocation_manifests=self.manifests,
                task_prompts=self.prompts,
            )
            reports, events = self._reports_and_events()
            reports[AGENTS[0]] = {
                **reports[AGENTS[0]],
                "forged": "not emitted by the child",
            }
            with self.assertRaisesRegex(
                ExecutionProofError, "CHILD_REPORT_OUTPUT_HASH_MISMATCH"
            ):
                verify_specialist_execution_proof(
                    proof,
                    invocation_manifests=self.manifests,
                    reports=reports,
                    mcp_events=events,
                )

    def test_raw_fixture_shell_access_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, children = self._rollouts(
                Path(directory), raw_fixture_access_agent=AGENTS[0]
            )
            with self.assertRaisesRegex(ExecutionProofError, "RAW_FIXTURE_ACCESS_ATTEMPT"):
                build_specialist_execution_proof(
                    ROOT,
                    parent_rollout=parent,
                    child_rollouts=children,
                    invocation_manifests=self.manifests,
                    task_prompts=self.prompts,
                )

    def test_run_proof_command_persists_only_verified_minimized_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            (run_dir / "invocations").mkdir(parents=True)
            (run_dir / "prompts").mkdir()
            (run_dir / "agents").mkdir()
            (run_dir / "events" / "mcp").mkdir(parents=True)
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"run_id": self.run_id, "output_dir": str(run_dir)}),
                encoding="utf-8",
            )
            reports, events = self._reports_and_events()
            for agent in AGENTS:
                (run_dir / "invocations" / f"{agent}.json").write_text(
                    json.dumps(self.manifests[agent]), encoding="utf-8"
                )
                (run_dir / "prompts" / f"{agent}.txt").write_text(
                    self.prompts[agent], encoding="utf-8"
                )
                (run_dir / "agents" / f"{agent}.json").write_text(
                    json.dumps(reports[agent]), encoding="utf-8"
                )
            write_jsonl(run_dir / "events" / "mcp" / "events.jsonl", events)
            parent, children = self._rollouts(root)
            result = build_run_specialist_execution_proof(
                ROOT,
                run_dir=run_dir,
                parent_rollout=parent,
                child_rollouts=children,
            )
            self.assertEqual(result["next_state"], "EXECUTION_PROOF_VERIFIED")
            output = run_dir / "events" / "codex" / "specialist-execution-proof.json"
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["proof_hash"], result["proof_hash"])
            self.assertNotIn(self.prompts[AGENTS[0]], output.read_text(encoding="utf-8"))

    def test_ephemeral_hook_proof_uses_public_events_and_distinct_children(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            (run_dir / "invocations").mkdir(parents=True)
            (run_dir / "prompts").mkdir()
            (run_dir / "agents").mkdir()
            (run_dir / "events" / "mcp").mkdir(parents=True)
            (run_dir / "invocation").mkdir()
            (run_dir / "run_manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": self.run_id,
                        "output_dir": str(run_dir),
                        "run_mode": "PRODUCT_COUNCIL",
                        "ablation_profile": None,
                        "model": "gpt-5.6-terra",
                        "codex_runtime": "codex-cli/0.153.4",
                        "trigger_reason": "product_council",
                    }
                ),
                encoding="utf-8",
            )
            reports, mcp_events = self._reports_and_events()
            for agent in AGENTS:
                (run_dir / "invocations" / f"{agent}.json").write_text(
                    json.dumps(self.manifests[agent]), encoding="utf-8"
                )
                (run_dir / "prompts" / f"{agent}.txt").write_text(
                    self.prompts[agent], encoding="utf-8"
                )
                (run_dir / "agents" / f"{agent}.json").write_text(
                    json.dumps(reports[agent]), encoding="utf-8"
                )
            write_jsonl(run_dir / "events" / "mcp" / "events.jsonl", mcp_events)
            (run_dir / "invocation" / "prompt.txt").write_text(
                f"$product:portfolio-council\nrun_id={self.run_id}\n",
                encoding="utf-8",
            )
            codex_events = run_dir / "invocation" / "codex-events.jsonl"
            write_jsonl(
                codex_events,
                [
                    {"type": "thread.started", "thread_id": "parent-session"},
                    {"type": "turn.started"},
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "command": f"sed -n '1,999p' {ROOT / 'product' / 'skills' / 'portfolio-council' / 'SKILL.md'}",
                            "exit_code": 0,
                            "aggregated_output": (ROOT / "product" / "skills" / "portfolio-council" / "SKILL.md").read_text(encoding="utf-8"),
                        },
                    },
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 120,
                            "cached_input_tokens": 20,
                            "output_tokens": 30,
                        },
                    },
                ],
            )
            bind_instruction_fixture(ROOT, run_dir)
            hook_records = []
            for index, agent in enumerate(AGENTS, 1):
                hook_records.append(
                    minimize_hook_event(
                        {
                            "hook_event_name": "SubagentStart",
                            "session_id": "parent-session",
                            "turn_id": "turn-1",
                            "agent_id": f"child-{index}",
                            "agent_type": agent,
                            "model": "gpt-5.6-terra",
                            "cwd": str(ROOT / "product"),
                            "permission_mode": "dontAsk",
                        }
                    )
                )
            for index, agent in enumerate(AGENTS, 1):
                hook_records.append(
                    minimize_hook_event(
                        {
                            "hook_event_name": "SubagentStop",
                            "session_id": "parent-session",
                            "turn_id": "turn-1",
                            "agent_id": f"child-{index}",
                            "agent_type": agent,
                            "model": "gpt-5.6-terra",
                            "cwd": str(ROOT / "product"),
                            "permission_mode": "dontAsk",
                            "agent_transcript_path": None,
                            "stop_hook_active": False,
                            "last_assistant_message": json.dumps(reports[agent]),
                        }
                    )
                )
            hook_events = run_dir / "invocation" / "subagent-events.jsonl"
            write_jsonl(hook_events, hook_records)

            result = build_ephemeral_run_specialist_execution_proof(
                ROOT,
                run_dir=run_dir,
                codex_events_path=codex_events,
                hook_events_path=hook_events,
                latency_ms=3210,
            )
            proof = json.loads(
                (run_dir / "events" / "codex" / "specialist-execution-proof.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(result["next_state"], "EXECUTION_PROOF_VERIFIED")
            self.assertEqual(proof["capture_mode"], "ephemeral_lifecycle_hooks")
            self.assertEqual(proof["telemetry"]["input_tokens"], 120)
            self.assertEqual(proof["telemetry"]["latency_ms"], 3210)
            self.assertEqual(
                {item["child_session_id"] for item in proof["dispatches"]},
                {"child-1", "child-2"},
            )
            self.assertNotIn("last_assistant_message", json.dumps(proof))

    def test_run_proof_rejects_parent_cross_run_artifact_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            (run_dir / "invocations").mkdir(parents=True)
            (run_dir / "prompts").mkdir()
            (run_dir / "agents").mkdir()
            (run_dir / "events" / "mcp").mkdir(parents=True)
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"run_id": self.run_id, "output_dir": str(run_dir)}),
                encoding="utf-8",
            )
            reports, events = self._reports_and_events()
            for agent in AGENTS:
                (run_dir / "invocations" / f"{agent}.json").write_text(
                    json.dumps(self.manifests[agent]), encoding="utf-8"
                )
                (run_dir / "prompts" / f"{agent}.txt").write_text(
                    self.prompts[agent], encoding="utf-8"
                )
                (run_dir / "agents" / f"{agent}.json").write_text(
                    json.dumps(reports[agent]), encoding="utf-8"
                )
            write_jsonl(run_dir / "events" / "mcp" / "events.jsonl", events)
            parent, children = self._rollouts(root)
            records = [json.loads(line) for line in parent.read_text().splitlines()]
            records.append(
                {
                    "type": "response_item",
                    "payload": {
                        "type": "custom_tool_call",
                        "name": "exec",
                        "call_id": "cross-run-read",
                        "input": (
                            "const r = await tools.exec_command({cmd: 'jq . "
                            f"{ROOT / 'evals' / 'results' / 'other-run' / 'decision.json'}"
                            "'}); text(r.output);"
                        ),
                    },
                }
            )
            write_jsonl(parent, records)
            with self.assertRaisesRegex(
                ExecutionProofError, "PARENT_CROSS_RUN_ARTIFACT_ACCESS"
            ):
                build_run_specialist_execution_proof(
                    ROOT,
                    run_dir=run_dir,
                    parent_rollout=parent,
                    child_rollouts=children,
                )

    def test_rollout_discovery_requires_run_binding_and_role_bound_children(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            run_dir.mkdir()
            (run_dir / "run_manifest.json").write_text("{}", encoding="utf-8")
            parent, children = self._rollouts(root)
            records = [json.loads(line) for line in parent.read_text().splitlines()]
            records.insert(2, message("user", f"{self.run_id} {run_dir.resolve()}"))
            write_jsonl(parent, records)
            found_parent, found_children = discover_run_rollouts(
                root,
                run_dir=run_dir,
                run_id=self.run_id,
            )
            self.assertEqual(found_parent, parent)
            self.assertEqual(found_children, children)


if __name__ == "__main__":
    unittest.main()
