from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import tests.test_multidimensional_stage as fixtures
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.runtime.local_revision import VERSION, _apply, located_paths
from product.runtime.schema_validation import schema_issue_locations


class LocalRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = fixtures.MultidimensionalStageTests()
        self.run, _ = self.fixture.prepare(Path(self.temp.name), count=1)
        tasks = json.loads((self.run / "research/dispatch-index.json").read_text())["tasks"]
        self.task = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
        self.env = self.fixture.targeted_environment(self.run, self.task)
        self.env["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"] = "1"
        self.parent, self.child = "local-parent", "local-child"
        handle_hook_event(self.fixture.dispatch_payload(self.task, parent=self.parent), environ=self.env)
        handle_hook_event(self.fixture.start_payload(self.task, parent=self.parent, child=self.child), environ=self.env)
        self.draft = self.fixture.dimension_draft(self.task)
        self.draft["observation_conditions"] = [{"condition_id": "bad-condition", "description": "待验证披露。",
                                                 "claim_refs": ["missing-claim"], "evidence_refs": []}]

    def stop(self, draft, **overrides):
        payload = self.fixture.stop_payload(self.task, draft, parent=self.parent, child=self.child)
        return handle_hook_event({**payload, **overrides}, environ=self.env)

    def first(self):
        record, response = self.stop(self.draft)
        self.assertEqual(record["output_capture"]["repair_state"], "REPAIR_REQUESTED", record)
        repair = json.loads(response["reason"])
        self.assertEqual(repair["repair_contract"], VERSION)
        self.assertEqual(repair["allowed_paths"], ["/observation_conditions/0"])
        self.assertNotIn("original_draft", repair)
        self.assertNotIn("binding_hash", repair)
        self.assertNotIn("binding_path", repair)
        return record, {**repair, "binding_path": record["repair_request"]["binding_path"]}

    @staticmethod
    def patch(repair, changes=None):
        return {"base_draft_ref": repair["base_draft_ref"], "changes": changes or [
            {"op": "remove", "path": "/observation_conditions/0"}]}

    def test_native_patch_saves_report_and_both_originals_without_rewriting_base(self):
        first, repair = self.first()
        path = self.run / first["output_capture"]["raw_path"]
        original = path.read_bytes()
        second, response = self.stop(self.patch(repair))
        self.assertEqual(second["output_capture"]["status"], "SAVED", second)
        self.assertEqual(response, {})
        self.assertEqual(path.read_bytes(), original)
        self.assertNotEqual(first["output_capture"]["raw_path"], second["output_capture"]["raw_path"])
        report = json.loads((self.run / second["output_capture"]["path"]).read_text())
        self.assertEqual(report["observation_conditions"], [])
        self.assertEqual(report["data_gaps"], self.draft["data_gaps"])
        self.assertEqual(second["local_revision"]["base_hash"], canonical_hash(self.draft))

    def test_unrelated_change_rejected_without_publish(self):
        _, repair = self.first()
        second, response = self.stop(self.patch(repair, [{"op": "replace", "path": "/data_gaps", "value": []}]))
        self.assertEqual(second["output_capture"]["failure_code"], "LOCAL_REVISION_OUT_OF_SCOPE:/data_gaps")
        self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
        self.assertEqual(response, {})
        raw = json.loads((self.run / second["output_capture"]["raw_path"]).read_text())
        self.assertEqual(raw["changes"][0]["path"], "/data_gaps")

    def test_complete_second_draft_cannot_bypass_allowed_paths(self):
        self.first()
        second, _ = self.stop({**self.draft, "observation_conditions": [], "data_gaps": []})
        self.assertEqual(second["output_capture"]["failure_code"], "LOCAL_REVISION_OUT_OF_SCOPE:/data_gaps/0")

    def test_complete_object_compatibility_is_still_bound_to_exact_base(self):
        self.first()
        second, _ = self.stop({**self.draft, "observation_conditions": []})
        self.assertEqual(second["output_capture"]["status"], "SAVED", second)
        self.assertEqual(second["local_revision"]["transport"], "FULL_OBJECT_COMPATIBILITY")

    def test_full_validator_rejects_dangling_reference_in_allowed_change(self):
        _, repair = self.first()
        second, _ = self.stop(self.patch(repair, [{"op": "replace", "path": "/observation_conditions/0/claim_refs",
                                                 "value": ["another-missing-claim"]}]))
        self.assertEqual(second["output_capture"]["failure_code"], "DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING")
        self.assertIn("local_revision", second)
        self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
        third, _ = self.stop(self.patch(repair))
        self.assertEqual(third["output_capture"]["failure_code"], "LOCAL_REVISION_LIMIT_EXHAUSTED")
        self.assertNotIn("raw_path", third["output_capture"])

    def test_wrong_model_does_not_consume_original_agent_attempt(self):
        _, repair = self.first()
        bad, _ = self.stop(self.patch(repair), model="untrusted-model")
        self.assertEqual(bad["identity_binding"]["status"], "FAILED")
        self.assertNotIn("raw_path", bad["output_capture"])
        good, _ = self.stop(self.patch(repair))
        self.assertEqual(good["output_capture"]["attempt"], 2)
        self.assertEqual(good["output_capture"]["status"], "SAVED", good)

    def test_wrong_base_reference_fails_closed(self):
        _, repair = self.first()
        patch = self.patch(repair)
        patch["base_draft_ref"] = "b.other-task"
        record, _ = self.stop(patch)
        self.assertEqual(record["output_capture"]["failure_code"], "LOCAL_REVISION_BASE_REFERENCE_INVALID")

    def test_base_and_constraint_tampering_rejected(self):
        _, repair = self.first()
        path = self.run / repair["binding_path"]
        original = path.read_bytes()
        value = json.loads(path.read_text())
        value["allowed_paths"].append("/data_gaps")
        value["content_hash"] = legacy_envelope_hash(value, hash_field="content_hash")
        path.write_text(json.dumps(value))
        before = {str(p): p.read_bytes() for p in (self.run / "research/raw-drafts").glob("*")}
        record, _ = self.stop(self.patch(repair))
        self.assertEqual(record["output_capture"]["failure_code"], "LOCAL_REVISION_BINDING_DRIFT")
        self.assertFalse(record["local_revision_authorized"])
        self.assertEqual({str(p): p.read_bytes() for p in (self.run / "research/raw-drafts").glob("*")}, before)
        path.write_bytes(original)
        accepted, _ = self.stop(self.patch(repair))
        self.assertEqual(accepted["output_capture"]["attempt"], 2)
        self.assertEqual(accepted["output_capture"]["status"], "SAVED")

    def test_original_draft_tampering_rejected(self):
        record, repair = self.first()
        path = self.run / record["output_capture"]["raw_path"]
        path.write_text(json.dumps({**self.draft, "data_gaps": []}))
        failed, _ = self.stop(self.patch(repair))
        self.assertEqual(failed["output_capture"]["failure_code"], "LOCAL_REVISION_BASE_DRIFT")


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
