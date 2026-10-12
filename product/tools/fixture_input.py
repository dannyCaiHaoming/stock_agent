"""版本化合成fixture的原生输入；不伪造Handoff、不开放真实账户建议。"""
from __future__ import annotations
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from product.runtime.evidence_gate import load_fixture, run_evidence_gate, validate_fixture
from product.runtime.hashing import canonical_hash, file_hash

ROOT = Path(__file__).resolve().parents[2]
INPUT_KIND = "FIXTURE_COUNCIL"
FILES = frozenset({"normal-research.json", "insufficient-evidence.json", "evidence-conflict.json",
                   "future-or-stale.json", "risk-veto.json", "invalid-portfolio.json"})
CAPABILITIES = frozenset({"FIXTURE_COMPANY_RESEARCH", "INDEPENDENT_FIRST_PASS", "FIXTURE_COUNCIL_DECISION"})


def _source(relative):
    path = ROOT / relative
    if (str(Path(relative).parent) != "evals/fixtures/codex-native" or Path(relative).name not in FILES
            or any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()):
        raise ValueError("NATIVE_FIXTURE_SOURCE_NOT_APPROVED")
    return path


def prepare_fixture_request(fixture_path: Path, *, research_question: str):
    path = Path(fixture_path).absolute()
    if not path.is_relative_to(ROOT) or not isinstance(research_question, str) or not research_question.strip():
        raise ValueError("NATIVE_FIXTURE_SOURCE_OR_QUESTION_INVALID")
    relative = str(path.relative_to(ROOT))
    path = _source(relative)
    stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source = {"source_id": "native-fixture:"+relative, "as_of": stamp, "retrieved_at": stamp}
    try:
        fixture = load_fixture(path)
    except ValueError:
        return {**source, "status": "BLOCKED_INPUT", "terminal_state": "SAFE_NO_TRADE", "action": "NO_TRADE",
                "reason_code": "INPUT_INVALID", "model_calls": 0, "advisory_only": True, "risk_status": "NOT_RUN"}
    run_id = "native-fixture-" + str(uuid4())
    gate = run_evidence_gate(fixture, run_id=run_id).artifact
    if not gate["allowed_evidence_ids"]:
        return {**source, "status": "PRE_AGENT_SAFE_TERMINATION", "terminal_state": "SAFE_NO_TRADE", "action": "NO_TRADE",
                "reason_code": "STALE_DATA", "gate": gate, "model_calls": 0, "advisory_only": True, "risk_status": "NOT_RUN"}
    value = {"schema_version": "native-fixture-input/1.0.0", "input_kind": INPUT_KIND,
             "request_id": run_id, "research_question": research_question.strip(), "resolved_cutoff": fixture["decision_cutoff"],
             "source_ref": relative, "source_hash": file_hash(path), "source_text": path.read_text(encoding="utf-8"),
             "fixture": copy.deepcopy(fixture), **source}
    value["request_hash"] = canonical_hash(value)
    validate_fixture_request(value)
    return {"input": value, "gate": gate, "model_calls": 0, "status": "PREPARED_NOT_RESEARCHED"}


def validate_fixture_request(value, *, require_source=True):
    if (value.get("schema_version") != "native-fixture-input/1.0.0" or value.get("input_kind") != INPUT_KIND
            or value.get("request_hash") != canonical_hash({k: v for k, v in value.items() if k != "request_hash"})):
        raise ValueError("NATIVE_FIXTURE_INPUT_HASH_INVALID")
    source_text = value.get("source_text")
    if (not isinstance(source_text, str) or hashlib.sha256(source_text.encode("utf-8")).hexdigest() != value["source_hash"]
            or json.loads(source_text) != value["fixture"]
            or str(Path(value["source_ref"]).parent) != "evals/fixtures/codex-native" or Path(value["source_ref"]).name not in FILES):
        raise ValueError("NATIVE_FIXTURE_SOURCE_DRIFT")
    validate_fixture(value["fixture"])
    if require_source:
        path = _source(value["source_ref"])
        if file_hash(path) != value["source_hash"] or load_fixture(path) != value["fixture"]:
            raise ValueError("NATIVE_FIXTURE_SOURCE_DRIFT")
    if (value["resolved_cutoff"] != value["fixture"]["decision_cutoff"]
            or not isinstance(value.get("research_question"), str) or not value["research_question"].strip()
            or any(f["source_type"] != "fixture" for f in value["fixture"]["evidence"])):
        raise ValueError("NATIVE_FIXTURE_SOURCE_DRIFT")


def fixture_subjects(value):
    validate_fixture_request(value)
    return [{"security_id": p["security_id"], "display_symbol": p["security_id"], "display_name": p["security_id"],
             "market": "FIXTURE", "asset_type": "COMMON_STOCK", "identity_status": "FIXTURE_ONLY"}
            for p in value["fixture"]["portfolio"]["positions"]]
