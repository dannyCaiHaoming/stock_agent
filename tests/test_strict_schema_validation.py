"""当前写入契约采用标准 Draft 2020-12，未知约束必须 fail-closed。"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from product.runtime.schema_validation import (
    SchemaValidationError,
    validate_schema_definition,
    validate_schema_instance,
)


class StrictSchemaValidationTests(unittest.TestCase):
    def test_explicit_frozen_resources_never_use_current_repository(self):
        schema = {"$ref": "frozen.schema.json#/$defs/value"}
        resources = {"frozen.schema.json": {"$defs": {"value": {"type": "string", "const": "历史值"}}}}
        with patch("product.runtime.schema_validation._local_registry", side_effect=AssertionError("不得读取当前 Schema")):
            validate_schema_instance("历史值", schema, schema_resources=resources)
            with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_CONST_INVALID"):
                validate_schema_instance("当前值", schema, schema_resources=resources)
            for missing in ({}, {"unrelated.schema.json": {"type": "string"}}):
                with self.subTest(resources=missing), self.assertRaisesRegex(SchemaValidationError, "SCHEMA_REF_UNSUPPORTED"):
                    validate_schema_definition(schema, schema_resources=missing)

    def test_frozen_schema_dependencies_are_transitive_and_fail_closed(self):
        schema = {"$ref": "a.schema.json"}
        resources = {"a.schema.json": {"$ref": "b.schema.json"},
                     "b.schema.json": {"type": "integer", "minimum": 1}}
        validate_schema_instance(2, schema, schema_resources=resources)
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_MINIMUM"):
            validate_schema_instance(0, schema, schema_resources=resources)
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_REF_UNSUPPORTED"):
            validate_schema_definition(schema, schema_resources={"a.schema.json": resources["a.schema.json"]})
        for name in ("../escape.schema.json", "/absolute.schema.json", "https://example.com/a.schema.json"):
            with self.subTest(name=name), self.assertRaisesRegex(SchemaValidationError, "SCHEMA_REF_UNSUPPORTED"):
                validate_schema_definition(schema, schema_resources={name: {"type": "integer"}})


    def test_current_research_draft_schemas_fail_during_preparation(self):
        from product.runtime.common_stock_stage import _dynamic_draft_schema as stock_schema
        from product.runtime.multidimensional_stage import _dynamic_draft_schema as dimension_schema
        from product.runtime.research_materials_stage import _output_schema as materials_schema

        repository_root = Path(__file__).resolve().parents[1]
        stock_kwargs = {
            "run_id": "schema-run", "invocation_id": "schema-invocation",
            "allowed_evidence_ids": ["ev-1"],
        }
        dimension_kwargs = {
            **stock_kwargs, "agent": "runtime_market_catalyst",
            "allowed_artifact_refs": [],
        }
        for module, builder, source, arguments in (
            (
                "product.runtime.common_stock_stage", stock_schema,
                "equity-research-report.schema.json", stock_kwargs,
            ),
            (
                "product.runtime.multidimensional_stage", dimension_schema,
                "research-dimension-report-v2.schema.json", dimension_kwargs,
            ),
        ):
            with self.subTest(source=source):
                builder(repository_root, **arguments)
                schema = json.loads(
                    (repository_root / "product/schemas/runtime" / source).read_text(encoding="utf-8")
                )
                schema["unreviewedConstraint"] = True
                with patch(f"{module}._read_object", return_value=schema):
                    with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_KEYWORD_UNSUPPORTED"):
                        builder(repository_root, **arguments)

        materials_schema(
            run_id="schema-run", invocation_id="schema-invocation",
            agent="runtime_company_analyst", kind="RESEARCH_REPORT_DISCOVERY",
        )
        with patch(
            "product.runtime.research_materials_stage.validate_schema_definition",
            side_effect=SchemaValidationError("SCHEMA_DEFINITION_INVALID:preflight"),
        ):
            with self.assertRaisesRegex(SchemaValidationError, "preflight"):
                materials_schema(
                    run_id="schema-run", invocation_id="schema-invocation",
                    agent="runtime_company_analyst", kind="RESEARCH_REPORT_DISCOVERY",
                )


    def test_no_trade_conditional_and_sibling_constraints(self):
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["action", "maximum_notional", "target_weight_range"],
            "properties": {
                "action": {"enum": ["NO_TRADE", "BUY"]},
                "maximum_notional": {"type": ["number", "null"]},
                "target_weight_range": {"type": ["array", "null"]},
            },
            "if": {"properties": {"action": {"const": "NO_TRADE"}}},
            "then": {
                "properties": {
                    "maximum_notional": {"type": "null"},
                    "target_weight_range": {"type": "null"},
                }
            },
            "else": {"properties": {"maximum_notional": {"type": "number"}}},
            "allOf": [{"not": {"required": ["broker_order_id"]}}],
            "additionalProperties": False,
        }
        validate_schema_instance(
            {"action": "NO_TRADE", "maximum_notional": None, "target_weight_range": None},
            schema,
        )
        validate_schema_instance(
            {"action": "BUY", "maximum_notional": 100, "target_weight_range": [0.1, 0.2]},
            schema,
        )
        for mutation in (
            {"maximum_notional": 0},
            {"target_weight_range": [0, 0]},
            {"broker_order_id": "must-not-exist"},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(SchemaValidationError):
                value = {"action": "NO_TRADE", "maximum_notional": None, "target_weight_range": None}
                value.update(mutation)
                validate_schema_instance(value, schema)
        with self.assertRaises(SchemaValidationError):
            validate_schema_instance(
                {"action": "BUY", "maximum_notional": None, "target_weight_range": None},
                schema,
            )

    def test_local_ref_does_not_skip_sibling_or_nested_constraint(self):
        schema = {
            "$defs": {"id": {"type": "string", "minLength": 2}},
            "$ref": "#/$defs/id",
            "maxLength": 3,
        }
        validate_schema_instance("abc", schema)
        for value in ("a", "abcd"):
            with self.subTest(value=value), self.assertRaises(SchemaValidationError):
                validate_schema_instance(value, schema)
        external = {"$ref": "agent-research-report.schema.json#/$defs/skill"}
        validate_schema_instance(
            {"skill_name": "x", "version": "1", "invocation_hash": "a" * 64},
            external,
        )
        with self.assertRaises(SchemaValidationError):
            validate_schema_instance(
                {"skill_name": "x", "version": "1", "invocation_hash": "bad"},
                external,
            )

    def test_missing_local_references_fail_at_definition_preflight(self):
        for reference in ("#/$defs/missing", "missing.schema.json#/$defs/id", "#/$defs/a~2b"):
            with self.subTest(reference=reference):
                schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": reference}
                with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_REF_UNSUPPORTED"):
                    validate_schema_definition(schema)
        validate_schema_definition({
            "$defs": {"a/b~c": {"type": "string"}},
            "properties": {"name": {"$ref": "#/$defs/a~1b~0c"}},
        })
        validate_schema_definition({
            "properties": {
                "skill": {"$ref": "agent-research-report.schema.json#/$defs/skill"},
            },
        })

    def test_external_subschema_resolves_references_from_its_file_root(self):
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012

        root = {"$ref": "fixture.schema.json#/$defs/selected"}
        external = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": {
                "base": {"type": "string"},
                "selected": {"$ref": "#/$defs/base"},
            },
        }
        registry = Registry().with_resource(
            "fixture.schema.json",
            Resource.from_contents(external, default_specification=DRAFT202012),
        )
        with patch("product.runtime.schema_validation._local_registry", return_value=registry):
            validate_schema_definition(root)

        external["$defs"]["selected"]["$ref"] = "#/$defs/missing"
        broken_registry = Registry().with_resource(
            "fixture.schema.json",
            Resource.from_contents(external, default_specification=DRAFT202012),
        )
        with patch("product.runtime.schema_validation._local_registry", return_value=broken_registry):
            with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_REF_UNSUPPORTED"):
                validate_schema_definition(root)

    def test_unknown_keyword_dialect_and_remote_ref_fail_before_validation(self):
        for schema, code in (
            ({"type": "object", "minumum": 5}, "SCHEMA_KEYWORD_UNSUPPORTED"),
            ({"$schema": "https://json-schema.org/draft-07/schema#", "type": "object"},
             "SCHEMA_DIALECT_UNSUPPORTED"),
            ({"$ref": "https://example.com/remote.schema.json"}, "SCHEMA_REF_UNSUPPORTED"),
        ):
            with self.subTest(schema=schema), self.assertRaisesRegex(SchemaValidationError, code):
                validate_schema_instance({}, schema)
        validate_schema_instance({}, {"type": "object", "description": "annotation"})

    def test_run_scoped_annotations_are_explicitly_allowed(self):
        for annotation in ("x-generated-from", "x-evidence-id-constraint", "x-eval-ablation"):
            with self.subTest(annotation=annotation):
                validate_schema_definition({"type": "object", annotation: {"source": "local"}})
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_KEYWORD_UNSUPPORTED"):
            validate_schema_definition({"type": "object", "x-unreviewed-extension": {}})

    def test_bool_is_not_integer_and_nonfinite_is_not_json(self):
        for value in (True, False):
            with self.subTest(value=value), self.assertRaisesRegex(SchemaValidationError, "SCHEMA_TYPE_INVALID"):
                validate_schema_instance(value, {"type": "integer"})
        for value in (
            float("nan"), float("inf"), float("-inf"),
            Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"),
        ):
            with self.subTest(value=value), self.assertRaisesRegex(SchemaValidationError, "SCHEMA_NONFINITE_NUMBER"):
                validate_schema_instance({"v": value}, {"type": "object"})

    def test_additional_property_diagnostic_respects_pattern_properties(self):
        schema = {
            "type": "object",
            "properties": {"known": {"type": "string"}},
            "patternProperties": {"^custom_": {"type": "string"}},
            "additionalProperties": False,
        }
        validate_schema_instance({"known": "yes", "custom_note": "allowed"}, schema)
        with self.assertRaisesRegex(SchemaValidationError, r"SCHEMA_EXTRA_PROPERTY:\$:other$"):
            validate_schema_instance({"custom_note": "allowed", "other": "invalid"}, schema)


if __name__ == "__main__":
    unittest.main()
