"""Offline Draft 2020-12 validation for repository-owned JSON contracts.

The public entry point preserves the project's failure-code vocabulary while a
standards implementation evaluates the schema. Unknown keywords and remote
references fail before any instance is accepted.
"""

from __future__ import annotations

import json
import math
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable
from referencing.jsonschema import DRAFT202012


class SchemaValidationError(ValueError):
    pass


_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_ANNOTATIONS = {
    "$schema", "$id", "$anchor", "$dynamicAnchor", "$vocabulary", "$comment",
    "$defs", "title", "description", "default", "examples", "readOnly",
    "writeOnly", "deprecated", "contentEncoding", "contentMediaType",
    "contentSchema", "x-generated-from", "x-evidence-id-constraint",
    "x-eval-ablation",
}
_KEYWORDS = frozenset(Draft202012Validator.VALIDATORS) | _ANNOTATIONS | {"then", "else"}
_SCHEMA_MAPS = {"$defs", "properties", "patternProperties", "dependentSchemas"}
_SCHEMA_ARRAYS = {"allOf", "anyOf", "oneOf", "prefixItems"}
_SCHEMA_VALUES = {
    "additionalProperties", "contains", "else", "if", "items", "not",
    "propertyNames", "then", "unevaluatedItems", "unevaluatedProperties",
}
_ERROR_CODES = {
    "additionalProperties": "SCHEMA_EXTRA_PROPERTY",
    "anyOf": "SCHEMA_ANY_OF_INVALID",
    "const": "SCHEMA_CONST_INVALID",
    "enum": "SCHEMA_ENUM_INVALID",
    "maxItems": "SCHEMA_MAX_ITEMS",
    "maxLength": "SCHEMA_MAX_LENGTH",
    "maximum": "SCHEMA_MAXIMUM",
    "minItems": "SCHEMA_MIN_ITEMS",
    "minLength": "SCHEMA_MIN_LENGTH",
    "minimum": "SCHEMA_MINIMUM",
    "not": "SCHEMA_NOT_INVALID",
    "oneOf": "SCHEMA_ONE_OF_INVALID",
    "pattern": "SCHEMA_PATTERN_INVALID",
    "required": "SCHEMA_REQUIRED_MISSING",
    "type": "SCHEMA_TYPE_INVALID",
    "uniqueItems": "SCHEMA_UNIQUE_ITEMS",
}


def _check_schema_tree(schema: Any, *, location: str = "$", seen: set[int] | None = None) -> None:
    if isinstance(schema, bool):
        return
    if not isinstance(schema, Mapping):
        raise SchemaValidationError(f"SCHEMA_DEFINITION_INVALID:{location}")
    if seen is None:
        seen = set()
    if id(schema) in seen:
        raise SchemaValidationError(f"SCHEMA_DEFINITION_CYCLIC:{location}")
    seen.add(id(schema))
    try:
        dialect = schema.get("$schema")
        if dialect is not None and dialect != _DIALECT:
            raise SchemaValidationError(f"SCHEMA_DIALECT_UNSUPPORTED:{location}:{dialect}")
        for keyword, value in schema.items():
            if keyword not in _KEYWORDS:
                raise SchemaValidationError(f"SCHEMA_KEYWORD_UNSUPPORTED:{location}:{keyword}")
            if keyword in {"$ref", "$dynamicRef"}:
                if not isinstance(value, str) or not _approved_reference(value):
                    raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{location}:{value}")
            if keyword in _SCHEMA_MAPS:
                if not isinstance(value, Mapping):
                    raise SchemaValidationError(f"SCHEMA_KEYWORD_INVALID:{location}:{keyword}")
                for name, child in value.items():
                    _check_schema_tree(child, location=f"{location}.{keyword}.{name}", seen=seen)
            elif keyword in _SCHEMA_ARRAYS:
                if not isinstance(value, list):
                    raise SchemaValidationError(f"SCHEMA_KEYWORD_INVALID:{location}:{keyword}")
                for index, child in enumerate(value):
                    _check_schema_tree(child, location=f"{location}.{keyword}[{index}]", seen=seen)
            elif keyword in _SCHEMA_VALUES:
                _check_schema_tree(value, location=f"{location}.{keyword}", seen=seen)
    finally:
        seen.remove(id(schema))


def _approved_reference(reference: str) -> bool:
    if reference.startswith("#/") or reference == "#":
        return True
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
        return False
    return ".." not in Path(parsed.path).parts and Path(parsed.path).name.endswith(".schema.json")


def _local_registry() -> Registry:
    schema_root = Path(__file__).resolve().parents[1] / "schemas"

    def retrieve(uri: str) -> Resource:
        if not _approved_reference(uri):
            raise NoSuchResource(ref=uri)
        filename = Path(urlsplit(uri).path).name
        candidates = list(schema_root.rglob(filename)) if filename else []
        if len(candidates) != 1:
            raise NoSuchResource(ref=uri)
        try:
            schema = json.loads(candidates[0].read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise NoSuchResource(ref=uri) from exc
        _check_schema_tree(schema, location=filename)
        return Resource.from_contents(schema, default_specification=DRAFT202012)

    return Registry(retrieve=retrieve)


def _check_local_pointer(root: Mapping[str, Any] | bool, reference: str, location: str) -> None:
    if reference == "#":
        return
    target: Any = root
    for token in reference[2:].split("/"):
        if re.search(r"~(?![01])", token):
            raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{location}:{reference}")
        part = token.replace("~1", "/").replace("~0", "~")
        if isinstance(target, Mapping) and part in target:
            target = target[part]
        elif isinstance(target, list) and part.isdecimal() and int(part) < len(target):
            target = target[int(part)]
        else:
            raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{location}:{reference}")
    if not isinstance(target, (Mapping, bool)):
        raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{location}:{reference}")


def _check_reference_targets(
    schema: Mapping[str, Any] | bool,
    *,
    root: Mapping[str, Any] | bool,
    registry: Registry,
    visited_files: set[str],
    location: str = "$",
) -> None:
    if isinstance(schema, bool):
        return
    for keyword, value in schema.items():
        if keyword in {"$ref", "$dynamicRef"}:
            if value.startswith("#"):
                _check_local_pointer(root, value, location)
            else:
                filename = Path(urlsplit(value).path).name
                try:
                    registry.resolver().lookup(value)
                except (NoSuchResource, Unresolvable, ValueError) as exc:
                    raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{location}:{value}") from exc
                if filename not in visited_files:
                    visited_files.add(filename)
                    try:
                        external_root = registry.resolver().lookup(filename).contents
                    except (NoSuchResource, Unresolvable, ValueError) as exc:
                        raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{location}:{value}") from exc
                    _check_schema_tree(external_root, location=filename)
                    _check_reference_targets(
                        external_root, root=external_root, registry=registry,
                        visited_files=visited_files, location=filename,
                    )
        elif keyword in _SCHEMA_MAPS:
            for name, child in value.items():
                _check_reference_targets(
                    child, root=root, registry=registry, visited_files=visited_files,
                    location=f"{location}.{keyword}.{name}",
                )
        elif keyword in _SCHEMA_ARRAYS:
            for index, child in enumerate(value):
                _check_reference_targets(
                    child, root=root, registry=registry, visited_files=visited_files,
                    location=f"{location}.{keyword}[{index}]",
                )
        elif keyword in _SCHEMA_VALUES:
            _check_reference_targets(
                value, root=root, registry=registry, visited_files=visited_files,
                location=f"{location}.{keyword}",
            )


def _reject_nonfinite(value: Any, *, path: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise SchemaValidationError(f"SCHEMA_NONFINITE_NUMBER:{path}")
    if isinstance(value, Decimal) and not value.is_finite():
        raise SchemaValidationError(f"SCHEMA_NONFINITE_NUMBER:{path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, path=f"{path}[{index}]")


def _error_path(error: ValidationError, root: str) -> str:
    location = root
    for part in error.absolute_path:
        location += f"[{part}]" if isinstance(part, int) else f".{part}"
    return location


def _failure(error: ValidationError, *, path: str) -> SchemaValidationError:
    code = _ERROR_CODES.get(str(error.validator), "SCHEMA_CONSTRAINT_INVALID")
    location = _error_path(error, path)
    if error.validator == "enum" and isinstance(error.validator_value, list):
        choices = error.validator_value
        if all(isinstance(choice, str) and "," not in choice for choice in choices):
            return SchemaValidationError(f"{code}:{location}:allowed={','.join(choices)}")
    if error.validator == "required" and isinstance(error.instance, Mapping):
        missing = [name for name in error.validator_value if name not in error.instance]
        return SchemaValidationError(f"{code}:{location}:{','.join(missing)}")
    if (error.validator == "additionalProperties" and error.validator_value is False
            and isinstance(error.instance, Mapping)):
        properties = error.schema.get("properties", {})
        patterns = error.schema.get("patternProperties", {})
        if isinstance(properties, Mapping) and isinstance(patterns, Mapping):
            extra = sorted(
                name for name in error.instance
                if name not in properties and not any(re.search(pattern, name) for pattern in patterns)
            )
            return SchemaValidationError(f"{code}:{location}:{','.join(extra)}")
    return SchemaValidationError(f"{code}:{location}")


def _schema_registry(resources: Mapping[str, Mapping[str, Any] | bool] | None) -> Registry:
    # None 是当前仓库；显式集合（包括空集合）只允许冻结依赖，绝不回退。
    if resources is None:
        return _local_registry()
    registry = Registry()
    for name, resource in resources.items():
        if not _approved_reference(name) or "#" in name:
            raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:$:{name}")
        _check_schema_tree(resource, location=name)
        try:
            Draft202012Validator.check_schema(resource)
        except SchemaError as exc:
            raise SchemaValidationError(f"SCHEMA_DEFINITION_INVALID:{name}:{exc.message}") from exc
        registry = registry.with_resource(
            name, Resource.from_contents(resource, default_specification=DRAFT202012)
        )
    return registry


def validate_schema_definition(
    schema: Mapping[str, Any] | bool,
    *, schema_resources: Mapping[str, Mapping[str, Any] | bool] | None = None,
) -> None:
    """Fail before model dispatch when a current local contract is unsupported."""

    _check_schema_tree(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SchemaValidationError(f"SCHEMA_DEFINITION_INVALID:$:{exc.message}") from exc
    _check_reference_targets(schema, root=schema, registry=_schema_registry(schema_resources), visited_files=set())


def validate_schema_instance(
    value: Any,
    schema: Mapping[str, Any] | bool,
    *,
    path: str = "$",
    _root_schema: Mapping[str, Any] | None = None,
    schema_resources: Mapping[str, Mapping[str, Any] | bool] | None = None,
) -> None:
    """Validate every supported constraint without remote schema retrieval."""

    root = schema if _root_schema is None else _root_schema
    validate_schema_definition(root, schema_resources=schema_resources)
    _reject_nonfinite(value, path=path)
    try:
        validator = Draft202012Validator(
            schema, registry=_schema_registry(schema_resources), format_checker=FormatChecker()
        )
        errors = list(validator.iter_errors(value))
    except (NoSuchResource, Unresolvable, ValueError) as exc:
        raise SchemaValidationError(f"SCHEMA_REF_UNSUPPORTED:{path}:{exc}") from exc
    if errors:
        errors.sort(key=lambda item: (
            tuple(str(part) for part in item.absolute_path),
            0 if item.validator == "required" else 1,
            str(item.validator),
        ))
        raise _failure(errors[0], path=path)


def schema_issue_locations(value: Any, schema: Mapping[str, Any] | bool) -> list[dict[str, str]]:
    """共享离线校验器给出有界字段位置；不从自然语言报错猜修订范围。"""
    from product.tools.revision import pointer

    validate_schema_definition(schema)
    _reject_nonfinite(value, path="$")
    validator = Draft202012Validator(schema, registry=_local_registry(), format_checker=FormatChecker())
    result = []
    seen = set()
    field_paths = set()
    for error in validator.iter_errors(value):
        parts = list(error.absolute_path)
        fields = None
        if error.validator == "required" and isinstance(error.instance, Mapping):
            fields = [key for key in error.validator_value if key not in error.instance]
        elif error.validator == "additionalProperties" and error.validator_value is False and isinstance(error.instance, Mapping):
            fields = [key for key in error.instance if key not in error.schema.get("properties", {})
                      and not any(re.search(p, key) for p in error.schema.get("patternProperties", {}))]
        locations = [parts + [key] for key in fields] if fields is not None else [parts]
        for location in locations:
            if not location:
                continue
            path = pointer(location)
            code = _ERROR_CODES.get(str(error.validator), "SCHEMA_CONSTRAINT_INVALID")
            if (code, path) in seen:
                continue
            seen.add((code, path))
            field_paths.add(path)
            # required errors repeat the same object for each missing property.
            # Bound editable fields, not repeated messages about those fields.
            if len(field_paths) > 32:
                raise SchemaValidationError("SCHEMA_DIAGNOSTICS_TOO_MANY")
            result.append({"code": code, "path": path})
    return result
