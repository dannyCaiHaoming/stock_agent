"""权威路由到准备及实际消费的确定性接缝，不启动模型或网络。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from product.runtime.hashing import canonical_hash
from product.runtime.multidimensional_stage import _capability_routing_coverage, _facts_for_capability
from product.runtime.research_consumption_audit import build_research_consumption_audit
from product.runtime.research_input_topology import (
    CAPABILITY_BINDINGS, DATASET_DOMAIN, capability_tools, dataset_consumers,
)
from product.runtime.fixture_mcp import GateScopedFixtureTools
from tests import test_multidimensional_stage as stage_fixtures
from tests.test_research_consumption_audit import write_json

ROOT = Path(__file__).resolve().parents[1]
SID = "US:COMMON_STOCK:AAPL"


def fact(dataset: str, evidence_id: str = "ev-one", **overrides) -> dict:
    return {
        "evidence_id": evidence_id, "dataset": dataset, "security_id": SID,
        "semantic_field": dataset, "source_family": "moomoo_sg",
        "source_type": "SECONDARY_VENDOR", "source_id": "moomoo-sg",
        "as_of": "2026-01-01T00:00:00Z", "retrieved_at": "2026-01-02T00:00:00Z",
        **overrides,
    }


class ResearchRoutingContractTests(unittest.TestCase):
    def coverage(self, facts, batches=()):
        return _capability_routing_coverage(
            facts, capture_batches=batches, security_ids=[SID], benchmark_id="US:SPY",
        )

    def test_all_declared_supplement_datasets_have_domain_and_consumers(self):
        plan = json.loads((ROOT / "product/mcp/live/research-supplement-source-plan.json").read_text())
        manifest = json.loads((ROOT / "product/mcp/live/moomoo-opend-quote-manifest.json").read_text())
        for dataset in {item["dataset"] for item in plan["datasets"]}:
            with self.subTest(dataset=dataset):
                self.assertIn(dataset, DATASET_DOMAIN)
                self.assertTrue(dataset_consumers(dataset))
        for dataset in {item["dataset"] for item in manifest["capabilities"]}:
            # global-state 是工具连通元数据，indicator catalog 是发现目录；不是研究事实许可。
            if dataset == "source_capability":
                self.assertFalse(dataset_consumers(dataset))
                continue
            self.assertIn(dataset, DATASET_DOMAIN)
            if dataset == "macro_indicator_catalog":
                self.assertFalse(dataset_consumers(dataset))
            else:
                self.assertTrue(dataset_consumers(dataset))

    def test_many_to_many_keeps_source_domain_and_existing_permissions(self):
        original = [fact("business_segments")]
        before = copy.deepcopy(original)
        coverage = self.coverage(original)
        selected = [row for row in coverage["dataset_observations"] if row["dataset"] == "business_segments"]
        self.assertEqual({row["target_capability"] for row in selected},
                         {"FUNDAMENTAL_EVENT", "INDUSTRY_COMPARISON"})
        self.assertTrue(all(row["delivered_evidence_count"] == 1 for row in selected))
        self.assertTrue(all(row["source_domain"] == "COMPANY" for row in selected))
        self.assertEqual(original, before)
        # 财务数据在原同行选择器仅接收 SEC/Yahoo，不因登记候选关系而扩大 OpenD 权限。
        financial = self.coverage([fact("financial_history")])
        industry = next(row for row in financial["dataset_observations"]
                        if row["dataset"] == "financial_history" and row["target_capability"] == "INDUSTRY_COMPARISON")
        self.assertEqual(industry["delivered_evidence_count"], 0)
        self.assertEqual(industry["exclusions"][0]["reason"], "OUTSIDE_EXISTING_CAPABILITY_SCOPE")
        self.assertEqual(financial["status"], "CLOSED")

    def test_each_declared_dataset_reaches_its_existing_scoped_route(self):
        plan = json.loads((ROOT / "product/mcp/live/research-supplement-source-plan.json").read_text())
        shared = {"macro_history", "economic_calendar", "dot_plot", "market_breadth",
                  "fedwatch_expectations", "option_market_statistics"}
        for entry in plan["datasets"]:
            dataset = entry["dataset"]
            item = fact(dataset, security_id="US:MARKET" if dataset in shared else SID)
            if dataset == "relationships":
                item.update(source_type="sec", source_id="sec-submissions", source_family="sec")
            with self.subTest(dataset=dataset):
                coverage = self.coverage([item], [{"capabilities": [{
                    "dataset": dataset, "evidence_ids": [item["evidence_id"]],
                }]}])
                selected = [row for row in coverage["dataset_observations"] if row["dataset"] == dataset]
                self.assertEqual(coverage["status"], "CLOSED")
                self.assertTrue(any(row["delivered_evidence_count"] == 1 for row in selected))
                self.assertTrue(all(row["source_domain"] == DATASET_DOMAIN[dataset] for row in selected))

    def test_capture_gate_delivery_and_unknown_mapping_are_separate(self):
        batches = [{"capabilities": [
            {"dataset": "business_segments", "evidence_ids": ["captured-only"]},
            {"dataset": "unrecognized_feed", "evidence_ids": ["unknown-capture"]},
        ]}]
        coverage = self.coverage([fact("unrecognized_feed")], batches)
        self.assertEqual(coverage["status"], "UNMAPPED")
        self.assertEqual(coverage["unmapped_datasets"], ["unrecognized_feed"])
        unknown = next(row for row in coverage["dataset_observations"] if row["dataset"] == "unrecognized_feed")
        self.assertEqual(unknown["target_capability"], "UNMAPPED")
        self.assertEqual(unknown["source_domain"], "UNMAPPED")
        self.assertEqual(unknown["delivered_evidence_count"], 0)
        captured = next(row for row in coverage["dataset_observations"] if row["dataset"] == "business_segments")
        self.assertEqual(captured["capture_evidence_count"], 1)
        self.assertEqual(captured["gate_eligible_evidence_count"], 0)
        self.assertEqual(captured["actual_research_use_status"], "NOT_EVALUATED_AT_PREPARATION")

    def test_shared_task_company_context_is_not_reported_as_undelivered(self):
        item = fact("financial_history", semantic_field="us-gaap.OperatingIncomeLoss",
                    source_type="sec", source_id="sec-companyfacts", source_family="sec")
        coverage = self.coverage([item])
        shared = [row for row in coverage["dataset_observations"]
                  if row["dataset"] == "financial_history"
                  and row["target_capability"] in {"MACRO_CONTEXT", "MARKET_STATE"}]
        self.assertEqual(len(shared), 2)
        self.assertTrue(all(row["delivered_evidence_ids"] == [item["evidence_id"]] for row in shared))
        self.assertTrue(all(row["source_domain"] == "COMPANY" for row in shared))

    def test_wrong_security_and_skeptic_do_not_gain_forward_access(self):
        foreign = fact("business_segments", security_id="US:COMMON_STOCK:MSFT")
        for capability in ("FUNDAMENTAL_EVENT", "INDUSTRY_COMPARISON", "INDEPENDENT_SKEPTIC"):
            self.assertEqual(_facts_for_capability([foreign], capability=capability,
                             security_ids=[SID], benchmark_id=None), [])
        self.assertNotIn("runtime_skeptic", {binding[0] for binding in CAPABILITY_BINDINGS.values()})
        for capability in CAPABILITY_BINDINGS:
            self.assertEqual(capability_tools(capability),
                             ["fixture_evidence.query", "fixture_math.calculate"]
                             if capability in {"FUNDAMENTAL_EVENT", "OWNERSHIP_DISCLOSURE"}
                             else ["fixture_evidence.query"])
        with self.assertRaisesRegex(ValueError, "UNMAPPED"):
            capability_tools("INDEPENDENT_SKEPTIC")

    def audit_fixture(self, run, *, unsigned=False):
        write_json(run / "evidence/gate.json", {
            "run_id": "run-routing", "bundle_hash": "gate",
            "allowed_evidence": [fact("business_segments"), fact("mystery", "ev-unknown")],
        })
        routing = self.coverage([fact("business_segments")])
        write_json(run / "audit/provider-coverage.json", {"capability_routing": routing})
        for cap, inv, refs in (("FUNDAMENTAL_EVENT", "fund", ["ev-one"]),
                               ("INDUSTRY_COMPARISON", "industry", [])):
            write_json(run / f"research/reports/{inv}/dimension-report.json", {
                "report_id": inv, "invocation_id": inv, "capability": cap,
                "status": "COMPLETE", "claims": [{"evidence_refs": refs}],
            })
        event = {"event_type": "mcp_tool_result", "run_id": "run-routing",
                 "invocation_id": "fund", "tool": "fixture_evidence.query", "evidence_ids": ["ev-one"]}
        if not unsigned:
            event["event_hash"] = canonical_hash(event)
        path = run / "events/mcp/events.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(event) + "\n")
        return path, event

    def test_actual_queries_and_references_are_per_consumer_not_global(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            self.audit_fixture(run)
            audit = build_research_consumption_audit(run)
            dimensions = {row["capability"]: row for row in audit["dimension_rows"]}
            self.assertEqual(dimensions["FUNDAMENTAL_EVENT"]["queried_count"], 1)
            self.assertEqual(dimensions["FUNDAMENTAL_EVENT"]["direct_or_indirect_reference_count"], 1)
            self.assertEqual(dimensions["INDUSTRY_COMPARISON"]["queried_count"], 0)
            self.assertEqual(dimensions["INDUSTRY_COMPARISON"]["direct_or_indirect_reference_count"], 0)
            company = next(row for row in audit["rows"] if row["dataset"] == "business_segments")
            self.assertEqual(company["domain"], "COMPANY")
            self.assertEqual(len(company["routing_observations"]), 2)
            self.assertEqual(audit["unmapped_datasets"], ["mystery"])

    def test_unsigned_history_is_readable_but_not_query_proof_and_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            path, event = self.audit_fixture(run, unsigned=True)
            audit = build_research_consumption_audit(run)
            self.assertEqual(audit["event_integrity"][str(run.resolve())], "UNVERIFIED_LEGACY_EVENTS")
            self.assertEqual(next(row for row in audit["rows"] if row["dataset"] == "business_segments")["queried_by_invocation"], {})
            event["event_hash"] = "0" * 64
            path.write_text(json.dumps(event) + "\n")
            with self.assertRaisesRegex(ValueError, "EVENT_HASH_MISMATCH"):
                build_research_consumption_audit(run)
            event["run_id"] = "other-run"
            event["event_hash"] = canonical_hash({k: v for k, v in event.items() if k != "event_hash"})
            path.write_text(json.dumps(event) + "\n")
            with self.assertRaisesRegex(ValueError, "EVENT_RUN_MISMATCH"):
                build_research_consumption_audit(run)

    def test_dataset_identity_cannot_be_changed_by_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            self.audit_fixture(run)
            write_json(run / "audit/provider-coverage.json", {"providers": [{"provider": "moomoo_sg",
                "dataset_observations": [{"dataset": "macro_history", "evidence_ids": ["ev-one"]}]}]})
            with self.assertRaisesRegex(ValueError, "DATASET_BINDING_MISMATCH"):
                build_research_consumption_audit(run)

    def test_actual_prepare_and_query_producer_reach_scoped_consumer_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _ = stage_fixtures.MultidimensionalStageTests().prepare(Path(directory), count=1)
            gate = json.loads((run / "evidence/gate.json").read_text())
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            before = build_research_consumption_audit(run)
            before_dimensions = {row["capability"]: row for row in before["dimension_rows"]}
            self.assertEqual(before["catalog_status"], "HASH_VERIFIED_ALLOWED_CATALOG")
            self.assertGreater(before_dimensions["FUNDAMENTAL_EVENT"]["catalog_allowed_count"], 0)
            self.assertEqual(before_dimensions["FUNDAMENTAL_EVENT"]["queried_count"], 0)
            evidence_id = task["allowed_evidence_ids"][0]
            tools = GateScopedFixtureTools(gate, run_id=task["run_id"], agent=task["agent"],
                invocation_id=task["invocation_id"], allowed_tools=capability_tools(task["capability"]),
                allowed_evidence_ids=task["allowed_evidence_ids"])
            tools.query(run_id=task["run_id"], agent=task["agent"],
                        invocation_id=task["invocation_id"], evidence_ids=[evidence_id])
            path = run / "events/mcp/events.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("\n".join(json.dumps(event) for event in tools.events) + "\n")
            after = build_research_consumption_audit(run)
            dimensions = {row["capability"]: row for row in after["dimension_rows"]}
            self.assertEqual(dimensions["FUNDAMENTAL_EVENT"]["queried_count"], 1)
            self.assertEqual(dimensions["FUNDAMENTAL_EVENT"]["direct_or_indirect_reference_count"], 0)
            self.assertEqual(dimensions["INDUSTRY_COMPARISON"]["queried_count"], 0)
            self.assertEqual(dimensions["MACRO_CONTEXT"]["queried_count"], 0)
            index["tasks"][0]["allowed_evidence_ids"].append("missing")
            write_json(index_path, index)
            with self.assertRaisesRegex(ValueError, "CATALOG_BINDING_INVALID"):
                build_research_consumption_audit(run)
