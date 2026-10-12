"""Boundary contract validation and canonical hashing for Tiger data."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import validate_schema_instance


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPOSITORY_ROOT / "product" / "schemas" / "broker"
SCHEMAS = {
    "tiger-account-snapshot/1.0.0": "tiger-account-snapshot.schema.json",
    "broker-sync-manifest/1.0.0": "broker-sync-manifest.schema.json",
    "trade-history-analysis/1.0.0": "trade-history-analysis.schema.json",
}


class TigerContractError(ValueError):
    """Stable boundary contract validation error."""


def content_hash(value: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(value))
    payload.pop("content_hash", None)
    return canonical_hash(payload)


def finalize_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(value))
    payload["content_hash"] = content_hash(payload)
    validate_contract(payload)
    return payload


def validate_contract(value: Mapping[str, Any]) -> None:
    version = value.get("schema_version")
    filename = SCHEMAS.get(str(version))
    if filename is None:
        raise TigerContractError("TIGER_CONTRACT_SCHEMA_UNSUPPORTED")
    schema = json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
    validate_schema_instance(value, schema)
    if value.get("content_hash") != content_hash(value):
        raise TigerContractError("TIGER_CONTRACT_HASH_MISMATCH")

