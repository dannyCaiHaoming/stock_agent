"""CIO 短引用实际工具接缝；合成上游/执行事件，不证明真实模型加载。"""
from __future__ import annotations

import copy
import io
import json
import unittest
from unittest.mock import patch

from product.runtime.cio_handoff import build_cio_reference_map, cio_model_view, cio_model_schema
from product.runtime.fixture_mcp import serve_stdio
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.multidimensional_references import translate_references, validate_reference_map
from product.runtime.predecision_cio_stage import (
    _native_output_schema, build_predecision_cio_prompt, launch_predecision_cio_run,
    predecision_cio_reference_map, validate_predecision_cio_run,
    REFERENCE_LOCKED_RESOURCES,
)
from product.runtime.schema_validation import validate_schema_instance
from tests import test_predecision_cio_stage as fixtures


class CioReferenceHandoffTests(unittest.TestCase):
    def prepare(self):
        helper = fixtures.PredecisionCioPreparationTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper._prepare()
        root = helper.target
        invocation = json.loads((root / "invocations/runtime_cio.json").read_text())
        catalog = json.loads((root / "report-catalog.json").read_text())["reports"]
        return helper, invocation, catalog, predecision_cio_reference_map(fixtures.REPO, root)

    def call(self, root, invocation, name, **arguments):
        request = {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": {
            "run_id": invocation["run_id"], "agent": "runtime_cio",
            "invocation_id": invocation["invocation_id"], **arguments,
        }}}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
            serve_stdio(stateless=True, default_run_dir=root, event_log=root / "events/mcp/events.jsonl")
        return json.loads(output.getvalue())

    def test_actual_stdio_delivers_aliases_and_keeps_canonical_receipts(self):
        helper, invocation, catalog, mapping = self.prepare()
        root = helper.target
        before = {item["artifact_ref"]: file_hash(root / "source-inputs" / item["artifact_ref"])
                  for item in catalog}
        result = self.call(root, invocation, "read_reports", report_ids=list(mapping["reports"]))
        self.assertNotIn("error", result, result)
        value = result["result"]["structuredContent"]
        canonical = {"reports": [{"report_id": report_id, "report": json.loads(
            (root / "source-inputs" / next(item["artifact_ref"] for item in catalog
                                          if item["report_id"] == report_id)).read_text())}
            for report_id in mapping["reports"].values()]}
        projected = {"reports": value["reports"]}
        self.assertEqual(projected, cio_model_view(canonical, mapping))
        self.assertEqual(translate_references(projected, mapping), canonical)
        self.assertEqual(value["result_hash"], canonical_hash(projected))
        self.assertEqual(value["canonical_result_hash"], canonical_hash(canonical))
        self.assertEqual(value["reference_map_hash"], mapping["map_hash"])
        events = [json.loads(line) for line in (root / "events/mcp/events.jsonl").read_text().splitlines()]
        self.assertEqual(events[0]["report_ids"], list(mapping["reports"].values()))
        self.assertEqual(events[1]["canonical_event_hash"], events[0]["event_hash"])
        self.assertEqual(events[1]["output_hash"], canonical_hash(value))
        self.assertEqual(before, {item["artifact_ref"]: file_hash(root / "source-inputs" / item["artifact_ref"])
                                  for item in catalog})
        query = self.call(root, invocation, "query", evidence_ids=list(mapping["evidence"]))
        self.assertNotIn("error", query, query)
        facts = query["result"]["structuredContent"]["evidence"]
        self.assertEqual([f["evidence_id"] for f in facts], list(mapping["evidence"]))
        original = json.loads((root / "evidence/gate.json").read_text())["allowed_evidence"]
        self.assertEqual(translate_references({"evidence": facts}, mapping)["evidence"],
                         [next(f for f in original if f["evidence_id"] == eid)
                          for eid in mapping["evidence"].values()])

    def test_foreign_decorated_raw_and_wrong_type_report_refs_fail_without_delivery(self):
        helper, invocation, catalog, mapping = self.prepare()
        ref = next(iter(mapping["reports"]))
        for bad in (catalog[0]["report_id"], ref + "|source=sec", ref + "|as_of=2026-09-20",
                    ref.replace("p.", "e.", 1), "p.foreign-run.1", "unknown", 42):
            with self.subTest(ref=bad):
                response = self.call(helper.target, invocation, "read_reports", report_ids=[bad])
                self.assertIn("error", response, response)
        log = helper.target / "events/mcp/events.jsonl"
        self.assertFalse(any(json.loads(line).get("tool") == "research_reports.read"
                             for line in log.read_text().splitlines()))

    def test_report_enum_retains_original_role_subset(self):
        _, _, catalog, mapping = self.prepare()
        selected = catalog[-1]["report_id"]
        schema = {"type": "object", "properties": {
            "report_id": {"type": "string", "enum": [selected]},
            "report_ids": {"type": "array", "items": {"type": "string", "enum": [selected]}},
        }, "required": ["report_id", "report_ids"], "additionalProperties": False}
        model = cio_model_schema(schema, mapping)
        alias = next(ref for ref, report_id in mapping["reports"].items() if report_id == selected)
        validate_schema_instance({"report_id": alias, "report_ids": [alias]}, model)
        for bad in (selected, next(ref for ref in mapping["reports"] if ref != alias)):
            with self.subTest(ref=bad), self.assertRaises(ValueError):
                validate_schema_instance({"report_id": bad, "report_ids": [bad]}, model)

    def test_map_is_exact_bound_to_run_catalog_and_gate_not_a_resigned_summary(self):
        helper, invocation, catalog, mapping = self.prepare()
        for change in ({"run_id": "other-run"}, {"allowed_evidence_ids": ["ev-outside"]},
                       {"reference_transport_version": "unknown/9"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_cio_reference_map(helper.target, {**invocation, **change}, catalog)
        changed_catalog = copy.deepcopy(catalog)
        changed_catalog[0]["file_hash"] = "0" * 64
        other = build_cio_reference_map(helper.target, invocation, changed_catalog)
        self.assertNotEqual(mapping["map_hash"], other["map_hash"])
        with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
            translate_references({"report_ids": list(mapping["reports"])}, other)
        forged = copy.deepcopy(mapping)
        forged["reports"][next(iter(forged["reports"]))] = "forged-report"
        forged["map_hash"] = canonical_hash({k: v for k, v in forged.items() if k != "map_hash"})
        with self.assertRaisesRegex(ValueError, "REFERENCE_MAP_INVALID"):
            validate_reference_map(forged)
        # 已冻结目录有修改时，实际工具不会仅凭重新计算的映射放行。
        (helper.target / "source-inputs" / catalog[0]["artifact_ref"]).write_text("{}")
        response = self.call(helper.target, invocation, "read_reports", report_ids=list(mapping["reports"]))
        self.assertIn("CIO_FROZEN_INPUT_DRIFT", response["error"]["message"])

    def test_explicit_projection_preserves_values_prose_and_legacy_map(self):
        helper, invocation, catalog, mapping = self.prepare()
        sample = {"report_id": catalog[0]["report_id"], "evidence_refs": ["ev-1"],
                  "text": "不是增长；原引用 ev-1 只作为文字，保留冲突。",
                  "value": {"report_id": catalog[0]["report_id"], "evidence_id": "ev-1"},
                  "metadata": {"evidence_refs": ["ev-1"]}}
        projected = cio_model_view(sample, mapping)
        self.assertEqual(projected["value"], sample["value"])
        self.assertEqual(projected["metadata"], sample["metadata"])
        self.assertEqual(projected["text"], sample["text"])
        self.assertEqual(translate_references(projected, mapping), sample)
        self.assertIsNone(build_cio_reference_map(helper.target,
                         {k: v for k, v in invocation.items() if k != "reference_transport_version"}, catalog))
        self.assertEqual(cio_model_view(sample, None), sample)

    def test_actual_prompt_and_schema_share_refs_without_request_hashes(self):
        helper, _, catalog, mapping = self.prepare()
        prompt = build_predecision_cio_prompt(fixtures.REPO, helper.target)
        context = json.loads(prompt.split("<validated_research_context>\n", 1)[1].split("\n</validated_research_context>", 1)[0])
        self.assertEqual(context["allowed_evidence_ids"], list(mapping["evidence"]))
        self.assertFalse(any(key.endswith("_hash") for key in context["request"]))
        request = json.loads((helper.target / "predecision-cio-request.json").read_text())
        schema = _native_output_schema(fixtures.REPO, request, catalog, run_dir=helper.target)
        self.assertEqual(set(schema["properties"]["report_selections"]["items"]["enum"]), set(mapping["reports"]))
        self.assertEqual(set(item["report_id"] for item in context["report_catalog"]), set(mapping["reports"]))

    def test_legacy_prepared_packet_is_readable_but_execution_is_retired(self):
        helper, _, _, _ = self.prepare()
        root = helper.target
        for ref, hash_field in (("run_manifest.json", "manifest_hash"),
                                ("invocations/runtime_cio.json", "invocation_hash")):
            record = json.loads((root / ref).read_text())
            del record["reference_transport_version"]
            if ref == "run_manifest.json":
                for resource in REFERENCE_LOCKED_RESOURCES:
                    del record["resource_locks"][resource]
            record[hash_field] = canonical_hash({k: v for k, v in record.items() if k != hash_field})
            (root / ref).write_text(json.dumps(record))
        before = {str(path.relative_to(root)): file_hash(path) for path in root.rglob("*") if path.is_file()}
        validate_predecision_cio_run(fixtures.REPO, root)
        self.assertIsNone(predecision_cio_reference_map(fixtures.REPO, root))
        self.assertIn('"report_id": "company:US:COMMON_STOCK:MRVL"', build_predecision_cio_prompt(fixtures.REPO, root))
        with patch.dict("os.environ", {"STOCK_AGENT_PRODUCT_HOST_LAUNCH": "1"}), patch(
            "subprocess.run") as process:
            with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                launch_predecision_cio_run(fixtures.REPO, run_dir=root)
            process.assert_not_called()
        self.assertEqual(before, {str(path.relative_to(root)): file_hash(path) for path in root.rglob("*") if path.is_file()})
