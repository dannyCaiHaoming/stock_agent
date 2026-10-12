"""共享资料准备的语义结构，不包含宿主启动或执行状态。"""
from typing import Any
from product.runtime.schema_validation import validate_schema_definition

DISCOVERY_KINDS = {"RESEARCH_REPORT_DISCOVERY", "MACRO_RESEARCH_DISCOVERY", "MARKET_RESEARCH_DISCOVERY"}
MATERIAL_ROLES = {
    "RESEARCH_REPORT_DISCOVERY": "runtime_company_analyst",
    "MACRO_RESEARCH_DISCOVERY": "runtime_market_catalyst",
    "MARKET_RESEARCH_DISCOVERY": "runtime_market_catalyst",
    "PEER_SELECTION": "runtime_market_catalyst",
}

def _output_schema(*, run_id: str, invocation_id: str, agent: str, kind: str) -> dict[str, Any]:
    selection = {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "document_id", "rationale"],
        "properties": {
            "candidate_id": {"type": "string", "minLength": 1},
            "document_id": {"type": ["string", "null"], "minLength": 1},
            "rationale": {"type": "string", "minLength": 1},
        },
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "research-material-preparation-draft/1.0.0",
        "type": "object", "additionalProperties": False,
        "required": [
            "run_id", "invocation_id", "agent", "preparation_kind", "security_id",
            "status", "summary", "queries", "selections", "gaps", "artifact_refs",
        ],
        "properties": {
            "run_id": {"type": "string", "const": run_id},
            "invocation_id": {"type": "string", "const": invocation_id},
            "agent": {"type": "string", "const": agent},
            "preparation_kind": {"type": "string", "const": kind},
            "security_id": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": ["READY", "SOURCE_LIMITED", "BLOCKED_CONFIGURATION"]},
            "summary": {"type": "string", "minLength": 1},
            "queries": {
                "type": "array", "maxItems": 3,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["query", "purpose"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 240},
                        "purpose": {"type": "string", "minLength": 1},
                    },
                },
            },
            "selections": {"type": "array", "maxItems": 5 if kind in DISCOVERY_KINDS else 3, "items": selection},
            "gaps": {
                "type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["reason_code", "description", "impact"],
                    "properties": {
                        "reason_code": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "impact": {"type": "string", "minLength": 1},
                    },
                },
            },
            "artifact_refs": {"type": "array", "uniqueItems": True, "items": {"type": "string", "minLength": 1}},
        },
    }
    validate_schema_definition(schema)
    return schema

def material_schema(kind):
    schema = _output_schema(run_id="business", invocation_id="business", agent=MATERIAL_ROLES[kind], kind=kind)
    removed = {"run_id", "invocation_id", "agent", "security_id", "preparation_kind", "artifact_refs", "queries"}
    schema["$id"] = "native-material-semantic/1.0.0"
    schema["required"] = [key for key in schema["required"] if key not in removed] + ["query_intents"]
    query = schema["properties"]["queries"]
    for key in removed:
        schema["properties"].pop(key)
    schema["properties"]["query_intents"] = query
    if kind == "PEER_SELECTION":
        query["maxItems"] = 0
    validate_schema_definition(schema)
    return schema
