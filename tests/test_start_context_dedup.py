"""启动 Schema 无损去重；纯合成输入，不调用模型或数据来源。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.schema_validation import validate_schema_instance, SchemaValidationError
from product.runtime.invocation import (
    build_specialist_output_schema, compact_specialist_schema,
    build_specialist_start_context, START_CONTEXT_VERSION, LEGACY_START_CONTEXT_VERSION,
)

ROOT = Path(__file__).resolve().parents[1]


class StartContextDedupTests(unittest.TestCase):
    def setUp(self):
        self.ids = ["ev-sec-" + f"{n:064x}" for n in range(351)]

    def test_equivalent_enum_and_all_other_fields_unchanged(self):
        for agent in ("runtime_company_analyst", "runtime_skeptic"):
            schema = build_specialist_output_schema(ROOT, agent_name=agent, allowed_evidence_ids=self.ids)
            before = copy.deepcopy(schema)
            compact = compact_specialist_schema(schema, self.ids)
            self.assertEqual(schema, before)
            self.assertEqual(compact["$defs"]["start_context_evidence_id"]["enum"], self.ids)
            def expand(value):
                if value == {"$ref": "#/$defs/start_context_evidence_id"}:
                    return compact["$defs"]["start_context_evidence_id"]
                if isinstance(value, dict):
                    return {k: expand(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [expand(v) for v in value]
                return value
            restored = copy.deepcopy(compact)
            del restored["$defs"]["start_context_evidence_id"]
            if "$defs" not in schema:
                del restored["$defs"]
            self.assertEqual(expand(restored), schema)
            resolved = {"type": "array", "items": expand({"$ref": "#/$defs/start_context_evidence_id"})}
            validate_schema_instance(self.ids, resolved)
            for bad in (self.ids[0] + "|source", self.ids[0] + "|as_of=2026", "ev-unknown", 0, None):
                with self.assertRaises(SchemaValidationError):
                    validate_schema_instance([bad], resolved)

    def context(self, packet, version=START_CONTEXT_VERSION, mode="live"):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            (run / "run_manifest.json").write_text(json.dumps({"specialist_context_delivery": version, "source_mode": mode}))
            with patch("product.runtime.live_context.load_live_run_context"), patch(
                "product.runtime.invocation.build_specialist_dispatch_message", return_value=json.dumps(packet)):
                return build_specialist_start_context(ROOT, run, "runtime_company_analyst")

    def packet(self):
        return {"identity": {"run_id": "test"}, "agent_input": {"allowed_evidence_ids": self.ids},
            "invocation": {"model": "test", "manifest_hash": "m", "task_prompt_hash": "p", "output_schema_hash": "s"},
            "task_prompt": "test", "padding": "x" * 70000,
            "output_schema": build_specialist_output_schema(ROOT, agent_name="runtime_skeptic", allowed_evidence_ids=self.ids)}

    def test_oversized_live_context_preserves_input_prompt_and_binding(self):
        packet = self.packet()
        context, binding = self.context(packet)
        value = json.loads(context)
        self.assertLessEqual(len(context.encode()), 128 * 1024)
        self.assertEqual(binding["context_bytes"], len(context.encode()))
        self.assertEqual(value["schema_encoding"]["version"], "start-context-schema-refs/1.0.0")
        for key in ("agent_input", "invocation", "task_prompt", "identity", "padding"):
            self.assertEqual(value["frozen_input"][key], packet[key])

    def test_small_packet_and_legacy_unchanged(self):
        packet = self.packet()
        packet["padding"] = ""
        for version in (START_CONTEXT_VERSION, LEGACY_START_CONTEXT_VERSION):
            context, _ = self.context(packet, version)
            self.assertNotIn("schema_encoding", json.loads(context))
            self.assertEqual(json.loads(context)["frozen_input"], packet)

    def test_still_oversized_or_fixture_or_legacy_fails(self):
        packet = self.packet()
        for version, mode, padding in ((LEGACY_START_CONTEXT_VERSION, "live", 70000),
                                       (START_CONTEXT_VERSION, "fixture", 70000),
                                       (START_CONTEXT_VERSION, "live", 150000)):
            packet["padding"] = "x" * padding
            with self.assertRaisesRegex(ValueError, "START_CONTEXT_TOO_LARGE"):
                self.context(packet, version, mode)

    def test_definition_collision_rejected(self):
        with self.assertRaisesRegex(ValueError, "DEFINITION_COLLISION"):
            compact_specialist_schema({"$defs": {"start_context_evidence_id": {}}}, self.ids)

    def test_remaining_duplicate_invocation_ids_are_losslessly_shared(self):
        packet = self.packet()
        packet["padding"] = "x" * 65000
        packet["invocation"]["evidence_ids"] = self.ids
        context, binding = self.context(packet)
        output = json.loads(context)
        self.assertIn("invocation_encoding", output)
        restored = copy.deepcopy(output["frozen_input"]["invocation"])
        restored["evidence_ids"] = output["frozen_input"]["agent_input"]["allowed_evidence_ids"]
        self.assertEqual(restored, packet["invocation"])
        self.assertEqual(output["frozen_input"]["agent_input"], packet["agent_input"])
        self.assertEqual(binding["invocation_hash"], "m")
        self.assertLessEqual(len(context.encode()), 128 * 1024)
