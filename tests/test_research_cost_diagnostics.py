"""只验证已有事件的统计口径，不调用模型或生成费用基准。"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from product.runtime.execution_proof import (
    ExecutionProofError, _public_codex_telemetry, _rollout_telemetry,
    _session_telemetry_summary,
)
from product.runtime.hashing import canonical_hash
from product.runtime.research_consumption_audit import build_research_consumption_audit
from tests import test_multidimensional_stage as fixture


def records(*usages):
    return [{"timestamp": "2026-09-30T00:00:00Z", "type": "session_meta"}, *[
        {"timestamp": "2026-09-30T00:00:02Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"total_token_usage": usage}}}
        for usage in usages
    ]]


class ResearchCostDiagnosticsTests(unittest.TestCase):
    def test_historical_main_and_skeptic_deliveries_remain_distinct_contexts(self):
        from product.runtime.research_consumption_audit import _cost_diagnostics
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # 显式历史向量，只测试读取/统计，不认证宿主加载、首轮输入或作者执行。
            for relative, event in (
                ("invocation/cio-stop-events.jsonl", {
                    "hook_event_name": "SessionStart", "execution_context": "MAIN_THREAD",
                    "context_binding": {"invocation_id": "cio"},
                    "delivery_diagnostics": {"model_context_bytes": 100},
                }),
                ("invocation/skeptic/subagent-events.jsonl", {
                    "hook_event_name": "SubagentStart", "agent_type": "runtime_skeptic",
                    "child_session_id": "historical-skeptic",
                    "context_binding": {"status": "DELIVERED", "invocation_id": "skeptic"},
                    "delivery_diagnostics": {"model_context_bytes": 50},
                }),
            ):
                event["event_hash"] = canonical_hash(event)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(event) + "\n")
            queries = {"by_invocation": [], "by_tool": []}
            before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            diagnostics = _cost_diagnostics(root, queries)
            observed = diagnostics["initial_contexts"]
            main = next(item for item in observed if item["execution_context"] == "MAIN_THREAD")
            self.assertEqual(main["agent"], "runtime_cio")
            self.assertEqual(main["event_path"], "invocation/cio-stop-events.jsonl")
            self.assertIsNone(main["child_session_id"])
            separate = next(item for item in observed if item["execution_context"] == "SUBAGENT")
            self.assertEqual(separate["agent"], "runtime_skeptic")
            self.assertEqual(separate["event_path"], "invocation/skeptic/subagent-events.jsonl")
            self.assertEqual(separate["measurement_status"], "OBSERVED")
            self.assertIsNone(diagnostics["total_cost"])
            self.assertIsNone(diagnostics["token_usage"])
            self.assertEqual(before, {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()})
            del event["event_hash"]
            path.write_text(json.dumps(event) + "\n")
            with self.assertRaisesRegex(ValueError, "DELIVERY_HASH_MISMATCH"):
                _cost_diagnostics(root, queries)

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

    def test_serialized_bytes_and_historical_delivery_hash_are_not_model_cost(self):
        from product.runtime.multidimensional_stage import (
            build_multidimensional_dispatch_packet, serialize_multidimensional_model_context,
        )
        with tempfile.TemporaryDirectory() as directory:
            helper = fixture.MultidimensionalStageTests()
            run, _ = helper.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "TECHNICAL_STRUCTURE")
            packet = build_multidimensional_dispatch_packet(fixture.ROOT, run, task["task_name"])
            original = canonical_hash(packet)
            context = serialize_multidimensional_model_context(packet).encode("utf-8")
            full_bytes = len(json.dumps(packet, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            diag = {"model_context_bytes": len(context), "full_packet_bytes": full_bytes,
                    "byte_delta": len(context) - full_bytes, "comparison_status": "SAME_FROZEN_PACKET",
                    "token_count_status": "NOT_OBSERVED"}
            self.assertEqual(canonical_hash(packet), original)
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
            # 统计消费者的显式历史输入；不是当前实际交付或token基准。
            event = {"hook_event_name": "SubagentStart", "agent_type": task["agent"],
                     "child_session_id": "historical-byte-fixture",
                     "context_binding": {"status": "DELIVERED", "invocation_id": task["invocation_id"]},
                     "delivery_diagnostics": diag}
            event["event_hash"] = canonical_hash(event)
            path = run / "invocation/subagent-events.jsonl"
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(event) + "\n")
            before = path.read_bytes()
            audit = build_research_consumption_audit(run)
            cost = audit["cost_diagnostics"]
            observed = cost["initial_contexts"][0]
            self.assertEqual(observed["event_hash"], event["event_hash"])
            self.assertEqual(observed["diagnostics"], diag)
            self.assertIsNone(cost["token_usage"])
            self.assertIsNone(cost["total_cost"])
            self.assertEqual(path.read_bytes(), before)
            event["delivery_diagnostics"]["model_context_bytes"] += 1
            path.write_text(json.dumps(event) + "\n")
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
