"""显式补丁、完整业务重验与保留维护绑定；不模拟正常Hook或签发运行权限。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import tests.test_multidimensional_stage as fixtures
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.runtime.local_revision import VERSION, _apply, located_paths, bind, resolve, verify_binding
from product.runtime.schema_validation import schema_issue_locations


class LocalRevisionTests(unittest.TestCase):
    """直接验证仍供显式维护使用的绑定API；合成身份不是作者/宿主证明。"""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = fixtures.MultidimensionalStageTests()
        self.run, _ = self.fixture.prepare(Path(self.temp.name), count=1)
        tasks = json.loads((self.run / "research/dispatch-index.json").read_text())["tasks"]
        self.task = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
        self.draft = self.fixture.dimension_draft(self.task)
        self.draft["observation_conditions"] = [{"condition_id": "bad-condition", "description": "待验证披露。",
                                                 "claim_refs": ["missing-claim"], "evidence_refs": []}]
        with self.assertRaisesRegex(ValueError, "DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING"):
            self.fixture.read_dimension_draft(self.run, self.task, self.draft)
        self.payload = {"hook_event_name": "SubagentStop", "session_id": "synthetic-parent",
                        "agent_id": "synthetic-child", "agent_type": self.task["agent"],
                        "model": "synthetic-maintenance-model", "last_assistant_message": json.dumps(self.draft)}
        self.identity = {"identity_binding": {"status": "BOUND"}, "trusted_task_binding": {
            key: self.task[key] for key in ("run_id", "invocation_id", "agent", "task_id", "task_name")}}
        self.base = self.run / "explicit-revision-base.json"
        self.base.write_text(self.payload["last_assistant_message"] + "\n")
        # 调用方显式提供诊断/身份，只验证维护边界，不恢复首Stop自动授权或额度调度。
        self.repair = bind(self.run, self.payload, self.identity, {
            "raw_path": self.base.name,
            "raw_output_hash": canonical_hash({"assistant_message": self.payload["last_assistant_message"]}),
        }, {"validation_error": "DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING"},
            [{"path": "/observation_conditions/0"}])
        self.assertEqual(self.repair["repair_contract"], VERSION)
        self.assertEqual(self.repair["allowed_paths"], ["/observation_conditions/0"])
        self.first = {**copy.deepcopy(self.identity), "repair_request": self.repair}
        self.first["event_hash"] = legacy_envelope_hash(self.first, hash_field="event_hash")

    def patch(self, changes=None):
        return {"base_draft_ref": self.repair["base_draft_ref"], "changes": changes or [
            {"op": "remove", "path": "/observation_conditions/0"}]}

    def resolve_patch(self, candidate, **identity_overrides):
        record = copy.deepcopy(self.identity)
        resolved = resolve(self.run, {**self.payload, **identity_overrides,
                                     "last_assistant_message": json.dumps(candidate)}, record, self.first)
        return json.loads(resolved["last_assistant_message"]), record

    def test_explicit_patch_persists_business_report_without_rewriting_base(self):
        original = self.base.read_bytes()
        corrected, record = self.resolve_patch(self.patch())
        report, output = self.fixture.save_dimension_fixture(self.run, self.task, corrected)
        self.assertEqual(report["observation_conditions"], [])
        self.assertEqual(report["data_gaps"], self.draft["data_gaps"])
        self.assertEqual(record["local_revision"]["base_hash"], canonical_hash(self.draft))
        self.assertEqual(json.loads(Path(output["json"]).read_text()), report)
        self.assertEqual(self.base.read_bytes(), original)
        self.assertFalse((self.run / "invocation/subagent-events.jsonl").exists())

    def test_unrelated_change_rejected_without_publish(self):
        with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_OUT_OF_SCOPE:/data_gaps"):
            self.resolve_patch(self.patch([{"op": "replace", "path": "/data_gaps", "value": []}]))
        self.assertFalse((self.run / "research/reports").exists())

    def test_complete_second_draft_cannot_bypass_allowed_paths(self):
        with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_OUT_OF_SCOPE:/data_gaps/0"):
            self.resolve_patch({**self.draft, "observation_conditions": [], "data_gaps": []})

    def test_retained_full_object_transport_is_bound_to_exact_base(self):
        corrected, record = self.resolve_patch({**self.draft, "observation_conditions": []})
        self.assertEqual(corrected, {**self.draft, "observation_conditions": []})
        self.assertEqual(record["local_revision"]["transport"], "FULL_OBJECT_COMPATIBILITY")
        self.fixture.read_dimension_draft(self.run, self.task, corrected)

    def test_full_validator_rejects_dangling_reference_in_allowed_change(self):
        corrected, _ = self.resolve_patch(self.patch([{"op": "replace", "path": "/observation_conditions/0/claim_refs",
                                                      "value": ["another-missing-claim"]}]))
        with self.assertRaisesRegex(ValueError, "DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING"):
            self.fixture.read_dimension_draft(self.run, self.task, corrected)
        self.assertFalse((self.run / "research/reports").exists())

    def test_identity_mismatch_rejects_without_modifying_binding_or_base(self):
        before = {str(path): path.read_bytes() for path in self.run.rglob("*") if path.is_file()}
        for field in ("model", "agent_id", "session_id", "agent_type"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "LOCAL_REVISION_BINDING_DRIFT"):
                self.resolve_patch(self.patch(), **{field: "foreign"})
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.run.rglob("*") if path.is_file()})
        corrected, _ = self.resolve_patch(self.patch())
        self.fixture.read_dimension_draft(self.run, self.task, corrected)

    def test_wrong_base_reference_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_BASE_REFERENCE_INVALID"):
            self.resolve_patch({**self.patch(), "base_draft_ref": "b.other-task"})

    def test_resigned_constraint_tampering_rejected_without_write(self):
        path = self.run / self.repair["binding_path"]
        original = path.read_bytes()
        value = json.loads(original)
        value["allowed_paths"].append("/data_gaps")
        value["content_hash"] = legacy_envelope_hash(value, hash_field="content_hash")
        path.write_text(json.dumps(value))
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_BINDING_DRIFT"):
            self.resolve_patch(self.patch())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})
        path.write_bytes(original)
        corrected, _ = self.resolve_patch(self.patch())
        self.fixture.read_dimension_draft(self.run, self.task, corrected)

    def test_original_draft_and_event_tampering_rejected(self):
        original = self.base.read_bytes()
        self.base.write_text(json.dumps({**self.draft, "data_gaps": []}))
        with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_BASE_DRIFT"):
            self.resolve_patch(self.patch())
        self.base.write_bytes(original)
        self.first["repair_request"] = {**self.repair, "allowed_paths": ["/data_gaps"]}
        with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_EVENT_DRIFT"):
            verify_binding(self.run, self.payload, self.identity, self.first)


class LocalRevisionMechanicsTests(unittest.TestCase):
    def test_calculation_locator_opens_only_that_original_selection_object(self):
        paths = located_paths([{"path": "$.calculation_selections[1].calculation_ref"},
                               {"path": "/calculation_selections/3/claim_ids/0"}])
        self.assertEqual(paths, ["/calculation_selections/1", "/calculation_selections/3"])
        base = {"calculation_selections": [{"calculation_ref": str(i)} for i in range(4)]}
        result = _apply(base, [{"op": "remove", "path": paths[0]},
                               {"op": "replace", "path": paths[1] + "/calculation_ref", "value": "author"}], paths)
        self.assertEqual(result["calculation_selections"],
                         [{"calculation_ref": "0"}, {"calculation_ref": "2"}, {"calculation_ref": "author"}])
        for path in ("/calculation_selections", "/calculation_selections/0/calculation_ref", "/run_id"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                _apply(base, [{"op": "replace", "path": path, "value": []}], paths)

    def test_schema_locations_are_leaf_fields_not_unrestricted_root(self):
        schema = {"type": "object", "properties": {"summary": {"type": "string"}},
                  "required": ["summary"], "additionalProperties": False}
        self.assertEqual(located_paths(schema_issue_locations({"extra": 1}, schema)), ["/extra", "/summary"])

    def test_schema_diagnostic_limit_counts_unique_fields_not_repeated_required_errors(self):
        from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance
        schema = {'type': 'object', 'properties': {f'field_{i}': {'type': 'string'} for i in range(32)},
                  'required': [f'field_{i}' for i in range(32)], 'additionalProperties': False}
        findings = schema_issue_locations({}, schema)
        self.assertEqual(len(findings), 32)
        self.assertEqual(len({f['path'] for f in findings}), 32)
        with self.assertRaisesRegex(SchemaValidationError, 'SCHEMA_REQUIRED_MISSING'):
            validate_schema_instance({}, schema)
        too_many = {**schema, 'properties': {**schema['properties'], 'field_32': {'type': 'string'}},
                    'required': [*schema['required'], 'field_32']}
        with self.assertRaisesRegex(SchemaValidationError, 'SCHEMA_DIAGNOSTICS_TOO_MANY'):
            schema_issue_locations({}, too_many)
        multiple_constraints = {'type': 'object', 'properties': {'choice': {'type': 'string', 'enum': ['x']}}}
        results = schema_issue_locations({'choice': 1}, multiple_constraints)
        self.assertEqual(len(results), 2)
        self.assertEqual({r['path'] for r in results}, {'/choice'})
        self.assertEqual(len({r['code'] for r in results}), 2)

    def test_paths_do_not_parse_error_prose_or_allow_technical_identity(self):
        self.assertEqual(located_paths([{"path": "claims[0].evidence_refs[1]"},
                                       {"path": "run_id"}, {"path": "error: claims[1]"}]), ["/claims/0"])

    def test_patch_preserves_nonselected_claim_exactly_and_does_not_guess_ids(self):
        base = {"claims": [{"evidence_refs": ["e.invalid"]}, {"statement": "不能证明改善。", "value": True}],
                "source": {"unit": "USD", "as_of": "2026-01-01"}}
        original = copy.deepcopy(base)
        fixed = _apply(base, [{"op": "replace", "path": "/claims/0/evidence_refs", "value": ["e.also-invalid"]}], ["/claims/0"])
        self.assertEqual(fixed["claims"][0]["evidence_refs"], ["e.also-invalid"])
        self.assertEqual(fixed["claims"][1], base["claims"][1])
        self.assertEqual(fixed["source"], base["source"])
        self.assertEqual(base, original)

    def test_array_deletions_apply_after_edits_using_original_indices(self):
        base = {"claims": [{"statement": "A"}, {"statement": "B"}, {"statement": "C"}]}
        result = _apply(base, [{"op": "remove", "path": "/claims/0"},
                               {"op": "replace", "path": "/claims/1/statement", "value": "B corrected"}],
                        ["/claims/0", "/claims/1"])
        self.assertEqual(result, {"claims": [{"statement": "B corrected"}, {"statement": "C"}]})
        result = _apply(base, [{"op": "remove", "path": "/claims/0"}, {"op": "remove", "path": "/claims/2"}],
                        ["/claims/0", "/claims/2"])
        self.assertEqual(result, {"claims": [{"statement": "B"}]})

    def test_root_overlap_array_shift_and_metadata_are_forbidden(self):
        base = {"claims": [{"statement": "A"}, {"statement": "B"}]}
        cases = [
            [{"op": "replace", "path": "/", "value": {}}],
            [{"op": "replace", "path": "/run_id", "value": "another"}],
            [{"op": "replace", "path": "/claims/0", "value": {}},
             {"op": "replace", "path": "/claims/0/statement", "value": "C"}],
            [{"op": "remove", "path": "/claims/0"}, {"op": "replace", "path": "/claims/0/statement", "value": "C"}],
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _apply(base, changes, ["/claims/0", "/claims/1"])
