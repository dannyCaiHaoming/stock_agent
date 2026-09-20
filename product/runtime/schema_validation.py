"""Small strict validator for repository-owned assurance JSON Schemas.

The project intentionally has no third-party runtime dependencies.  This module
implements only the Draft 2020-12 keywords used by the assurance schemas.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


class SchemaValidationError(ValueError):
    pass


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaValidationError(f"SCHEMA_KEYWORD_UNSUPPORTED:type={expected}")


def _resolve_local_ref(reference: str, root_schema: Mapping[str, Any]) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{reference}")
    current: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise SchemaValidationError(f"SCHEMA_REF_UNKNOWN:{reference}")
        current = current[part]
    if not isinstance(current, Mapping):
        raise SchemaValidationError(f"SCHEMA_REF_INVALID:{reference}")
    return current


def validate_schema_instance(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str = "$",
    _root_schema: Mapping[str, Any] | None = None,
) -> None:
    root_schema = schema if _root_schema is None else _root_schema
    reference = schema.get("$ref")
    if isinstance(reference, str):
        validate_schema_instance(
            value,
            _resolve_local_ref(reference, root_schema),
            path=path,
            _root_schema=root_schema,
        )
        return
    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        for branch in one_of:
            if not isinstance(branch, Mapping):
                raise SchemaValidationError("SCHEMA_KEYWORD_INVALID:oneOf")
            try:
                validate_schema_instance(
                    value, branch, path=path, _root_schema=root_schema
                )
            except SchemaValidationError:
                continue
            matches += 1
        if matches != 1:
            raise SchemaValidationError(f"SCHEMA_ONE_OF_INVALID:{path}:matches={matches}")
        return
    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        for branch in any_of:
            if not isinstance(branch, Mapping):
                raise SchemaValidationError("SCHEMA_KEYWORD_INVALID:anyOf")
            try:
                validate_schema_instance(
                    value, branch, path=path, _root_schema=root_schema
                )
            except SchemaValidationError:
                continue
            return
        raise SchemaValidationError(f"SCHEMA_ANY_OF_INVALID:{path}:matches=0")
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(_type_matches(value, item) for item in expected_type):
            raise SchemaValidationError(f"SCHEMA_TYPE_INVALID:{path}")
    elif isinstance(expected_type, str) and not _type_matches(value, expected_type):
        raise SchemaValidationError(f"SCHEMA_TYPE_INVALID:{path}")
    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"SCHEMA_CONST_INVALID:{path}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"SCHEMA_ENUM_INVALID:{path}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            raise SchemaValidationError(f"SCHEMA_MIN_LENGTH:{path}")
        if "pattern" in schema and re.fullmatch(str(schema["pattern"]), value) is None:
            raise SchemaValidationError(f"SCHEMA_PATTERN_INVALID:{path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"SCHEMA_MINIMUM:{path}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"SCHEMA_MAXIMUM:{path}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < int(schema["minItems"]):
            raise SchemaValidationError(f"SCHEMA_MIN_ITEMS:{path}")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise SchemaValidationError(f"SCHEMA_MAX_ITEMS:{path}")
        if schema.get("uniqueItems") and len({repr(item) for item in value}) != len(value):
            raise SchemaValidationError(f"SCHEMA_UNIQUE_ITEMS:{path}")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                validate_schema_instance(
                    item,
                    item_schema,
                    path=f"{path}[{index}]",
                    _root_schema=root_schema,
                )
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise SchemaValidationError(f"SCHEMA_REQUIRED_MISSING:{path}:{','.join(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise SchemaValidationError(f"SCHEMA_EXTRA_PROPERTY:{path}:{','.join(extra)}")
        for key, item in value.items():
            child = properties.get(key) if isinstance(properties, Mapping) else None
            if isinstance(child, Mapping):
                validate_schema_instance(
                    item,
                    child,
                    path=f"{path}.{key}",
                    _root_schema=root_schema,
                )
