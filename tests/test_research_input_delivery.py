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

from product.runtime.codex_hook_recorder import handle_hook_event
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
from tests import test_multidimensional_stage as dimension_helpers
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
                root, task, view, _, _ = helper.prepare(Path(directory), kind)
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
                    environment = helper.targeted_environment(root, task)
                    parent = "dependency-parent"
                    # 基本面已经由依赖 fixture 实际保存，其原始 Start 仍可重建相同视图。
                    if task["capability"] == "FUNDAMENTAL_EVENT":
                        full = dimensions.build_multidimensional_dispatch_packet(REPO, root, task["task_name"])
                        view = json.loads(dimensions.serialize_multidimensional_model_context(full))
                    else:
                        self.assertEqual(handle_hook_event(helper.dispatch_payload(task, parent=parent),
                                                          environ=environment)[0]["decision"], "ALLOW")
                        event, response = handle_hook_event(helper.start_payload(task, parent=parent, child=task["task_name"] + ":child"),
                                                            environ=environment)
                        self.assertEqual(event["context_binding"]["status"], "DELIVERED", event)
                        full = dimensions.build_multidimensional_dispatch_packet(REPO, root, task["task_name"])
                        view = json.loads(response["hookSpecificOutput"]["additionalContext"])
                        self.assertEqual(event["delivery_diagnostics"]["model_context_bytes"], len(encoded(view)))
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
                        stopped, _ = handle_hook_event(helper.stop_payload(
                            task, helper.dimension_draft(task), parent=parent, child=task["task_name"] + ":child"),
                            environ=environment)
                        self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
                    self.retain("dimension-" + task["capability"].lower(), root, full, view,
                                tool_output=result, tool_events=tools.events)
            self.assertEqual(capabilities, set(dimensions.EIGHT_DIMENSION_INPUTS))




if __name__ == "__main__":
    unittest.main()
