"""当前入口输入保真与字节证据；合成事件，零 LLM、零外部网络。

显式设置 STOCK_AGENT_HANDOFF_EVIDENCE_DIR 可保留原件供复核；默认普通测试会清理临时目录。
原件只属于本地测试证据，不是产品运行包、Replay 证明或候选版本锁。
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.multidimensional_references import translate_references
from product.runtime import common_stock_stage as stocks
from product.runtime import research_materials_stage as materials
from product.runtime import multidimensional_stage as dimensions
from product.runtime import independent_skeptic_stage as skeptic
from product.runtime import common_stock_eval as grading
from product.runtime.fixture_mcp import StatelessFixtureTools
from product.runtime.invocation import build_specialist_dispatch_message, build_specialist_start_context
from tests import test_material_semantic_handoff as material_helpers
from tests import test_common_stock_semantic_handoff as stock_helpers
from tests import test_multidimensional_stage as dimension_helpers
from tests import test_skeptic_semantic_handoff as skeptic_helpers
from tests import test_council_eval_local_revision as eval_helpers
from tests import test_cio_local_revision as cio_helpers
from tests import test_runtime_eval_local_revision as runtime_eval_helpers
from tests.test_common_stock_research_contracts import gate_for as base_gate

REPO = Path(__file__).resolve().parents[1]
SOURCE_LIMITS = {
    "original_amount": "100", "unit": "USD million", "period": "2026-Q2",
    "subject": "合并持续经营主体", "footnote": "不含已终止业务，不能外推全年",
    "negative_statement": "收入增长并不证明现金流改善",
    "conflicts": [{"source_id": "另一披露", "definition": "净额而非总额"}],
    "source_limitations": "管理层说明，不是独立研报预测",
    "metadata": {"request_hash": "来源正文中的字段，不是运行锁"},
}


def rich_gate(handoff, run_id=None):
    gate = base_gate(handoff, run_id)
    for fact in gate["allowed_evidence"]:
        if fact["semantic_field"] == "revenue":
            fact["value"] = copy.deepcopy(SOURCE_LIMITS)
    gate["bundle_hash"] = canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
    return gate


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class ResearchInputDeliveryTests(unittest.TestCase):
    def retain(self, entry, root, full, model, *, tool_output=None, tool_events=None, scope="SAME_FROZEN_PACKET"):
        target = os.environ.get("STOCK_AGENT_HANDOFF_EVIDENCE_DIR")
        if not target:
            return
        directory = Path(target).resolve() / entry
        directory.mkdir(parents=True, exist_ok=False)
        # 保留原始路径文本，复制后的包不宣称可直接 execution replay。
        shutil.copytree(root, directory / "snapshot")
        for name, value in (("full-input.json", full), ("model-input.json", model),
                            ("tool-output.json", tool_output), ("tool-events.json", tool_events)):
            (directory / name).write_bytes(encoded(value))
        manifest = {
            "entry": entry, "validation_level": "DETERMINISTIC_SYNTHETIC_SEAM",
            "model_execution": "NOT_RUN", "comparison_scope": scope,
            "original_root": str(root), "copied_package_is_execution_replay": False,
            "full_input_bytes": len(encoded(full)), "model_input_bytes": len(encoded(model)),
            "byte_delta": len(encoded(model)) - len(encoded(full)),
            "token_usage": None, "total_cost": None, "historical_model_baseline": "NOT_OBSERVED",
            "artifacts": {str(path.relative_to(directory)): file_hash(path)
                          for path in sorted(directory.rglob("*")) if path.is_file()},
        }
        (directory / "measurement.json").write_bytes(encoded(manifest))

    def assert_facts(self, root, original_ids, delivered, mapping=None):
        gate = json.loads((root / "evidence/gate.json").read_text())
        original = {fact["evidence_id"]: fact for fact in gate["allowed_evidence"]}
        restored = translate_references(delivered, mapping) if mapping else delivered
        self.assertEqual(restored["evidence"], [original[key] for key in original_ids])
        # 逐字段相等包括原值、期间、单位、来源和限制，而非只检查 ID 个数。
        self.assertEqual(set(original_ids), {fact["evidence_id"] for fact in restored["evidence"]})

    def test_material_kinds_keep_research_fields_without_duplicate_task_identity(self):
        for kind in sorted(materials.DISCOVERY_KINDS | {"PEER_SELECTION"}):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory, patch(
                "tests.test_research_materials_stage.gate_for", rich_gate):
                helper = material_helpers.MaterialSemanticHandoffTests()
                root, task, view = helper.prepare(Path(directory), kind)
                full = materials.build_research_materials_dispatch_packet(REPO, root, task["task_name"])
                before = copy.deepcopy(full)
                removed = {"task_hash", "agent", "run_id", "invocation_id", "task_id", "task_name"}
                self.assertEqual(view["task"], {key: value for key, value in full["task"].items() if key not in removed})
                for key in ("evidence_catalog", "peer_candidate_group", "identity", "tool_context", "output_schema"):
                    self.assertEqual(view[key], full[key])
                full["task"]["source_limitations"] = {"task_hash": "原文中的同名字段", "footnote": "不代表预测"}
                updated = json.loads(materials.serialize_research_materials_dispatch_context(full))
                self.assertEqual(updated["task"]["source_limitations"], full["task"]["source_limitations"])
                self.retain("materials-" + kind.lower(), root, before, view)

    def test_stock_actual_query_restores_complete_facts_and_preserves_request_semantics(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "tests.test_common_stock_semantic_handoff.fixtures.gate_for", rich_gate):
            helper = stock_helpers.CommonStockSemanticHandoffTests()
            root, task, request, view = helper.prepare(directory)
            full = helper.frozen_packet(root, task)
            original = copy.deepcopy(full)
            result = helper.call(root, request, "query", evidence_ids=view["allowed_evidence_ids"])
            mapping = full["reference_map"]
            self.assert_facts(root, [mapping["evidence"][ref] for ref in view["allowed_evidence_ids"]], result, mapping)
            removed = {"agent_binding", "skill_bindings", "council_request_hash", "evidence_bundle_hash",
                       "handoff_hash", "portfolio_hash", "request_hash"}
            translated = translate_references(full, mapping, to_model=True)
            self.assertEqual(view["holding_research_request"], {
                key: value for key, value in translated["holding_research_request"].items() if key not in removed})
            full["holding_research_request"]["user_context"]["source_limitations"] = {
                "request_hash": "来源正文里的字段", "footnote": "并非利润预测", "conflicts": ["定义不一致"]}
            # 变化后的冻结输入建立自己的映射，而非放宽原映射漂移验证。
            from product.runtime.multidimensional_references import build_reference_map
            base = {key: value for key, value in full.items() if key not in {"reference_map", "context_budget"}}
            full["reference_map"] = build_reference_map(base, mapping["binding"]["gate_hash"], mapping["binding"]["run_dir"])
            projected = stocks.common_stock_model_packet(full)
            self.assertEqual(projected["holding_research_request"]["user_context"], full["holding_research_request"]["user_context"])
            self.retain("common-stock", root, original, view, tool_output=result)

    def test_all_eight_capabilities_deliver_authorized_catalog_and_exact_tool_facts(self):
        helper = dimension_helpers.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory, patch("tests.test_multidimensional_stage.gate_for", rich_gate):
            root, _ = helper.prepare(Path(directory), count=1)
            index = json.loads((root / "research/dispatch-index.json").read_text())
            helper.save_fundamental_dependency(root, index)
            capabilities = set()
            for task in index["tasks"]:
                capabilities.add(task["capability"])
                with self.subTest(capability=task["capability"]):
                    full = dimensions.build_multidimensional_dispatch_packet(REPO, root, task["task_name"])
                    view = json.loads(dimensions.serialize_multidimensional_model_context(full))
                    mapping = full["reference_map"]
                    catalog = view["evidence_catalog"]
                    restored = translate_references(view, mapping)
                    # 紧凑目录是表格，不是对象中的引用字段；按明确列定位还原。
                    id_column = catalog["columns"].index("evidence_id")
                    for row in restored["evidence_catalog"]["rows"]:
                        row[id_column] = mapping["evidence"][row[id_column]]
                    expected = [[item.get(key) for key in catalog["columns"]] for item in full["evidence_catalog"]]
                    self.assertEqual(restored["evidence_catalog"]["rows"], expected)
                    for key in ("dependency_reports", "portfolio_context", "research_input_topology"):
                        if key in full:
                            # 研究报告中的 research_reference 是额外定位符，其余完整正文逐项保留。
                            actual = copy.deepcopy(restored[key])
                            if key == "dependency_reports":
                                for report in actual:
                                    for claim in report["claims"]:
                                        claim.pop("research_reference", None)
                            self.assertEqual(actual, full[key])
                    tools = StatelessFixtureTools(default_run_dir=root)
                    aliases = list(mapping["evidence"])
                    result = None
                    if aliases:
                        args = {key: task[key] for key in ("run_id", "agent", "invocation_id")}
                        result = tools.query(**args, evidence_ids=aliases)
                        self.assert_facts(root, [mapping["evidence"][ref] for ref in aliases], result, mapping)
                        with self.assertRaises(ValueError):
                            tools.query(**args, evidence_ids=[aliases[0] + "|source=other"])
                    if task["capability"] != "FUNDAMENTAL_EVENT":
                        helper.save_dimension_fixture(root, task, helper.dimension_draft(task))
                    self.assertFalse((root / "invocation/subagent-events.jsonl").exists())
                    self.retain("dimension-" + task["capability"].lower(), root, full, view,
                                tool_output=result, tool_events=tools.events)
            self.assertEqual(capabilities, set(dimensions.EIGHT_DIMENSION_INPUTS))

    def test_skeptic_and_fixture_specialists_keep_facts_and_independent_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = skeptic_helpers.SkepticSemanticHandoffTests()
            root, task, view = helper.prepare(directory)
            full = skeptic.build_skeptic_dispatch_packet(REPO, root, task["task_name"])
            result = helper.query(root, task, view["allowed_evidence_ids"])["result"]["structuredContent"]
            self.assert_facts(root, task["allowed_evidence_ids"], result, full["reference_map"])
            self.assertNotIn("forward_reports", view["agent_input"])
            self.retain("independent-skeptic", root, full, view, tool_output=result)
        from product.runtime.run_package import prepare_run
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "fixture"
            prepared = prepare_run(REPO, fixture_path=REPO / "evals/fixtures/codex-native/normal-research.json",
                run_dir=root, run_id="delivery-fixture", model="gpt-6-luna",
                research_question="合成输入无损交付", authenticity_required=False)
            self.assertTrue((root / "run_manifest.json").is_file(), prepared)
            for agent in ("runtime_company_analyst", "runtime_skeptic"):
                full = json.loads(build_specialist_dispatch_message(REPO, root, agent))
                view = json.loads(build_specialist_start_context(REPO, root, agent)[0])
                self.assertEqual(view["frozen_input"]["agent_input"], full["agent_input"])
                self.assertNotIn("validated_reports", full["agent_input"])
                self.assertNotIn("invocation", view["frozen_input"])
                self.retain("fixture-" + agent, root, full, view)
            self.assertFalse((root / "invocation").exists())

    def test_cio_and_eval_views_retain_complete_semantic_inputs(self):
        cio = cio_helpers.CioLocalRevisionTests()
        self.addCleanup(cio.doCleanups)
        for prepare in (cio.fixture, cio.predecision):
            root, _, _, _ = prepare()
            self.assertFalse((root / "invocation/cio-stop-events.jsonl").exists())
            if prepare == cio.fixture:
                full = json.loads((root / "inputs/runtime_cio.json").read_text())
                view = json.loads((root / "inputs/runtime_cio.model.json").read_text())
                self.assertEqual(view["mechanical_conflicts"], full["mechanical_conflicts"])
                self.assertEqual(view["portfolio_metrics"], full["portfolio_metrics"])
                scope = "FROZEN_JSON_REPRESENTATION_NOT_PROOF_OF_MODEL_READ"
            else:
                prompt = (root / "invocation/prompt.txt").read_text()
                view = json.loads(prompt.split("<validated_research_context>\n", 1)[1].split("\n</validated_research_context>", 1)[0])
                full = {**view, "request": json.loads((root / "predecision-cio-request.json").read_text())}
                scope = "EMBEDDED_CONTEXT_REQUEST_WRAPPER_ONLY"
            self.retain("cio-" + prepare.__name__, root, full, view, scope=scope)
        evaluator = eval_helpers.CouncilEvalLocalRevisionTests()
        evaluator.setUp()
        self.addCleanup(evaluator.doCleanups)
        root, _, _ = evaluator.evaluator()
        full = grading.build_common_stock_eval_packet(root)
        view = grading.common_stock_eval_model_packet(full)
        for key in ("report", "report_markdown", "rubric", "allowed_evidence", "hard_gates"):
            if key in full["input_manifest"]:
                self.assertEqual(view["input"][key], full["input_manifest"][key])
        self.retain("common-stock-eval", root, full, view)
        evaluator = runtime_eval_helpers.RuntimeEvalLocalRevisionTests()
        evaluator.setUp()
        self.addCleanup(evaluator.doCleanups)
        root, parent, child, _ = evaluator.job(invalid=False)
        self.assertEqual(evaluator.collect(root, parent, child)["local_revision"]["status"], "FIRST_DRAFT")
        full = json.loads((root / "grader-input.json").read_text())
        view = json.loads((root / "grader-model-input.json").read_text())
        from product.runtime.runtime_eval import runtime_eval_model_input
        self.assertEqual(view, runtime_eval_model_input(full))
        self.retain("runtime-eval", root, full, view, scope="CHILD_VERIFIED_GRADER_INPUT_FILE_READ_ONLY")


if __name__ == "__main__":
    unittest.main()
