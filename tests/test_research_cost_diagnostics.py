"""只验证已有事件的统计口径，不调用模型或生成费用基准。"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import shutil

from product.runtime.execution_proof import (
    ExecutionProofError, _public_codex_telemetry, _rollout_telemetry,
    _session_telemetry_summary,
)
from product.runtime.hashing import canonical_hash
from product.runtime.research_consumption_audit import build_research_consumption_audit
from product.runtime.codex_hook_recorder import handle_hook_event
from tests import test_multidimensional_stage as fixture


def records(*usages):
    return [{"timestamp": "2026-09-30T00:00:00Z", "type": "session_meta"}, *[
        {"timestamp": "2026-09-30T00:00:02Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"total_token_usage": usage}}}
        for usage in usages
    ]]


class ResearchCostDiagnosticsTests(unittest.TestCase):

    def test_parent_public_turn_usage_is_observed_without_inventing_child_or_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence").mkdir()
            (root / "evidence/gate.json").write_text(json.dumps({"run_id": "cost-run", "allowed_evidence": []}))
            path = root / "invocation/codex-events.jsonl"
            path.parent.mkdir()
            events = [
                {"type": "thread.started", "thread_id": "parent"},
                {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30}},
                {"type": "turn.completed", "usage": {"input_tokens": 50, "cached_input_tokens": 10, "output_tokens": 5}},
            ]
            path.write_text("\n".join(json.dumps(event) for event in events))
            cost = build_research_consumption_audit(root)["cost_diagnostics"]
            self.assertEqual(cost["parent_usage"]["input_tokens"], 150)
            self.assertEqual(cost["parent_usage"]["cached_tokens"], 30)
            self.assertEqual(len(cost["parent_usage"]["by_turn"]), 2)
            self.assertIsNone(cost["child_usage"])
            self.assertIsNone(cost["token_usage"])
            self.assertIsNone(cost["total_cost"])
            for invalid in ({}, {"cached_input_tokens": False}, {"input_tokens": 1, "cached_input_tokens": 2, "output_tokens": 1}):
                with self.subTest(usage=invalid):
                    events[-1]["usage"] = invalid
                    path.write_text("\n".join(json.dumps(event) for event in events))
                    value = build_research_consumption_audit(root)["cost_diagnostics"]["parent_usage"]
                    self.assertEqual(value["status"], "MISSING_TELEMETRY")
                    self.assertIsNone(value["input_tokens"])
                    self.assertIsNone(value["cached_tokens"])

    def test_cumulative_updates_not_added_and_cache_is_already_in_input(self):
        value = _rollout_telemetry(records(
            {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3},
            {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30},
            {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30},
        ))
        self.assertEqual(value["input_tokens"], 100)
        self.assertEqual(value["cached_tokens"], 20)
        self.assertEqual(value["output_tokens"], 30)
        self.assertEqual(value["token_count_events"], 3)
        self.assertIsNone(value["llm_calls"])
        self.assertEqual(value["llm_calls_status"], "NOT_OBSERVED")

    def test_missing_or_invalid_counter_is_never_zero(self):
        for counter in (None, True, -1, "20"):
            with self.subTest(counter=counter):
                value = _rollout_telemetry(records({
                    "input_tokens": 100, "cached_input_tokens": counter, "output_tokens": 30,
                }))
                self.assertIsNone(value["cached_tokens"])
                self.assertEqual(value["status"], "MISSING_TELEMETRY")
                self.assertIn("cached_tokens", value["missing_fields"])
        no_usage = _rollout_telemetry(records())
        self.assertIsNone(no_usage["input_tokens"])
        self.assertIsNone(no_usage["output_tokens"])

    def test_empty_latest_counter_does_not_reuse_prior_cumulative_values(self):
        value = _rollout_telemetry(records({
            "input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30,
        }, {}))
        self.assertIsNone(value["input_tokens"])
        self.assertEqual(value["status"], "MISSING_TELEMETRY")

    def test_parent_and_child_separate_unknown_child_prevents_total_claim(self):
        parent = records({"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 30})
        child = records({"input_tokens": 50, "output_tokens": 10})
        value = _session_telemetry_summary(parent, {"analyst": child})
        self.assertEqual(value["by_session"]["parent"]["input_tokens"], 100)
        self.assertEqual(value["by_session"]["analyst"]["input_tokens"], 50)
        self.assertEqual(value["scope"], "OBSERVED_SESSION_SUM_NOT_FULL_CHAIN")
        self.assertEqual(value["input_tokens"], 150)
        self.assertIsNone(value["cached_tokens"])
        self.assertEqual(value["status"], "MISSING_TELEMETRY")
        self.assertEqual(value["latency_ms"], 2000)  # 不把重叠子会话延迟相加。

    def test_public_usage_rejects_impossible_cache_and_negative_values(self):
        for usage in (
            {"input_tokens": -1, "cached_input_tokens": 0, "output_tokens": 3},
            {"input_tokens": 10, "cached_input_tokens": 11, "output_tokens": 3},
            {"input_tokens": 10, "cached_input_tokens": False, "output_tokens": 3},
        ):
            with self.subTest(usage=usage), self.assertRaisesRegex(ExecutionProofError, "CODEX_USAGE_INVALID"):
                _public_codex_telemetry([{"type": "turn.completed", "usage": usage}], latency_ms=5, llm_calls=1)

    def test_query_representations_not_added_or_mislabelled_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "evidence").mkdir()
            (run / "evidence/gate.json").write_text(json.dumps({
                "run_id": "cost-run", "bundle_hash": "g", "allowed_evidence": [],
            }))
            events = [
                {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query", "output_bytes": 100},
                {"event_type": "mcp_reference_transport", "tool": "query", "output_bytes": 40},
                {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query", "output_bytes": True},
                {"event_type": "mcp_reference_transport", "tool": "query", "output_bytes": None},
            ]
            for event in events:
                event.update(run_id="cost-run", invocation_id="one", evidence_ids=[])
                event["event_hash"] = canonical_hash(event)
            path = run / "events/mcp/events.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(json.dumps(event) for event in events))
            audit = build_research_consumption_audit(run)
            cost = audit["cost_diagnostics"]
            row = cost["query_representations"][0]
            self.assertEqual(row["result_bytes_observed"], 100)
            self.assertEqual(row["model_transport_bytes_observed"], 40)
            self.assertEqual(row["result_bytes_missing_count"], 1)
            self.assertEqual(row["model_transport_bytes_missing_count"], 1)
            self.assertIsNone(cost["token_usage"])
            self.assertIsNone(cost["total_cost"])

    def test_nonquery_transport_bytes_are_visible_but_not_added_to_canonical_response(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "evidence").mkdir()
            (run / "evidence/gate.json").write_text(json.dumps({
                "run_id": "cost-run", "bundle_hash": "g", "allowed_evidence": [],
            }))
            events = []
            for tool in ("calculate", "read_reports"):
                for event_type, size in (("mcp_tool_result", 200),
                                         ("mcp_reference_transport", 70),
                                         ("mcp_reference_transport", None)):
                    event = {"event_type": event_type, "tool": tool, "run_id": "cost-run",
                             "invocation_id": "one", "output_bytes": size, "evidence_ids": []}
                    event["event_hash"] = canonical_hash(event)
                    events.append(event)
            path = run / "events/mcp/events.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(json.dumps(event) for event in events))
            cost = build_research_consumption_audit(run)["cost_diagnostics"]
            for row in cost["tool_return_representations"]:
                self.assertEqual(row["success_count"], 1)
                self.assertEqual(row["result_bytes_observed"], 200)
                self.assertEqual(row["model_transport_bytes_observed"], 70)
                self.assertEqual(row["model_transport_count"], 2)
                self.assertEqual(row["model_transport_bytes_missing_count"], 1)
            self.assertEqual(cost["byte_accounting"], "CANONICAL_AND_MODEL_TRANSPORT_ARE_NOT_ADDITIVE")
            self.assertEqual(cost["byte_accounting"], "CANONICAL_AND_MODEL_TRANSPORT_ARE_NOT_ADDITIVE")

    def test_actual_hook_delivery_bytes_and_hash_bound_to_same_frozen_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = fixture.MultidimensionalStageTests()
            run, _ = helper.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            environment = helper.targeted_environment(run, task)
            handle_hook_event(helper.dispatch_payload(task, parent="cost-parent"), environ=environment)
            event, response = handle_hook_event(helper.start_payload(
                task, parent="cost-parent", child="cost-child",
            ), environ=environment)
            context = response["hookSpecificOutput"]["additionalContext"].encode("utf-8")
            diag = event["delivery_diagnostics"]
            self.assertEqual(diag["model_context_bytes"], len(context))
            self.assertEqual(diag["byte_delta"], len(context) - diag["full_packet_bytes"])
            self.assertEqual(diag["comparison_status"], "SAME_FROZEN_PACKET")
            self.assertEqual(diag["token_count_status"], "NOT_OBSERVED")
            audit = build_research_consumption_audit(run)
            observed = audit["cost_diagnostics"]["initial_contexts"][0]
            self.assertEqual(observed["event_hash"], event["event_hash"])
            self.assertEqual(observed["diagnostics"], diag)
            path = run / "invocation/subagent-events.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            rows[-1]["delivery_diagnostics"]["model_context_bytes"] += 1
            path.write_text("\n".join(json.dumps(item) for item in rows))
            with self.assertRaisesRegex(ValueError, "DELIVERY_HASH_MISMATCH"):
                build_research_consumption_audit(run)

    def test_all_observed_tools_have_separate_missing_byte_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "evidence").mkdir()
            (run / "evidence/gate.json").write_text(json.dumps({
                "run_id": "cost-run", "bundle_hash": "g", "allowed_evidence": [],
            }))
            events = []
            for tool in ("research_search", "research_fetch", "fixture_math.calculate", "read_reports"):
                for size in (20, None):
                    event = {"event_type": "mcp_tool_result", "tool": tool, "run_id": "cost-run",
                             "invocation_id": "one", "output_bytes": size, "evidence_ids": []}
                    event["event_hash"] = canonical_hash(event)
                    events.append(event)
            path = run / "events/mcp/events.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(json.dumps(event) for event in events))
            cost = build_research_consumption_audit(run)["cost_diagnostics"]
            rows = cost["tool_return_representations"]
            self.assertEqual(len(rows), 4)
            for row in rows:
                self.assertEqual(row["success_count"], 2)
                self.assertEqual(row["result_bytes_observed"], 20)
                self.assertEqual(row["result_bytes_missing_count"], 1)
            self.assertIsNone(cost["total_cost"])


if __name__ == "__main__":
    unittest.main()
