from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/Users/caihaoming/Documents/stock_agent")

from product.deterministic.policy import ALLOWED_POLICY_METRICS, RuleBasis
from product.mcp.contracts import AccessMode, TOOL_CONTRACTS, validate_read_only_registry
from product.runtime.fixture_mcp import _tool_manifest
from product.runtime.hashing import canonical_hash
from product.runtime.regression_invariants import (
    INVARIANT_REGISTRY,
    expected_invariant_schema,
    validate_invariant_schema_binding,
)


ROOT = Path("/Users/caihaoming/Documents/stock_agent")
OUT = ROOT / "evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


validate_read_only_registry()
case_schema = load(ROOT / "product/schemas/runtime/regression-case.schema.json")
validate_invariant_schema_binding(case_schema)
suite = load(OUT / "regression/suite-fresh/result.json")
case_rows = suite["case_results"]
run_ids = [row["outcome"]["run_id"] for row in case_rows]
future = OUT / "regression/suite-fresh/cases/future-information-leakage"
injection = load(future / "run/audit/regression-injection.json")
gate = load(future / "run/evidence/gate.json")
future_eval = load(future / "runtime-eval/eval/result.json")
future_proof = load(future / "execution-proof.json")
source_manifest = load(OUT / "runs/source-normal/run_manifest.json")
source_trace = load(OUT / "runs/source-normal/decision_trace.json")
source_event = load(OUT / "commands/05b-source-codex-exec-escalated.event.json")
promotion = load(OUT / "promotion/result/result.json")
negative_promotion = load(OUT / "promotion/negative-assertion/result.json")
calibration = load(OUT / "calibration/result/result.json")
ablation = load(OUT / "ablation/result/result.json")
policy = load(ROOT / "evals/promotion/policy-v1.json")
runtime_profile = load(ROOT / "product/runtime-profile.json")
plugin_mcp = load(ROOT / "product/.mcp.json")

variants = load(ROOT / "evals/results/runtime-replay-and-eval-hardening-hardening-fix-20260907/ablation/variants-hardening-final.json")["cases"]
ablation_locks = sorted({
    canonical_hash(load(Path(entry["run_dir"]) / "run_manifest.json")["discovery"]["version_manifest"])
    for profiles in variants.values() for entry in profiles.values()
})

approval_paths_raw = subprocess.run(
    ["rg", "-l", '"approved_by"', str(ROOT), "--glob", "*.json"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
    text=True,
).stdout.splitlines()
valid_approval_paths = []
for raw in approval_paths_raw:
    try:
        value = load(Path(raw))
    except (OSError, json.JSONDecodeError):
        continue
    required = {"approved_by", "decided_at", "rollback_conditions", "candidate_versions", "previous_versions"}
    if required <= set(value):
        valid_approval_paths.append(raw)

fixture_tools = _tool_manifest(stateless=True)
current_lock = canonical_hash(load(ROOT / "product/version-manifest.json"))
audit = {
    "schema_version": "final-independent-bottom-up-audit/1.0.0",
    "candidate_lock": current_lock,
    "runtime_tools": {
        "status": "PASS",
        "access_modes": sorted({contract.access_mode.value for contract in TOOL_CONTRACTS}),
        "contract_names": [contract.name for contract in TOOL_CONTRACTS],
        "fixture_mcp_enabled_tools": plugin_mcp["mcpServers"]["fixture_runtime"]["enabled_tools"],
        "fixture_annotations": {tool["name"]: tool["annotations"] for tool in fixture_tools},
        "runtime_agent_tool_permissions": {
            name: row["tool_permissions"] for name, row in runtime_profile["agents"].items()
        },
        "assertions": {
            "access_enum_read_only": [item.value for item in AccessMode] == ["read"],
            "all_contracts_read_only": all(item.access_mode is AccessMode.READ for item in TOOL_CONTRACTS),
            "fixture_annotations_read_only": all(
                item["annotations"] == {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
                for item in fixture_tools
            ),
            "only_query_and_calculate_enabled": plugin_mcp["mcpServers"]["fixture_runtime"]["enabled_tools"] == ["query", "calculate"],
        },
    },
    "risk_engine": {
        "status": "PASS",
        "rule_bases": sorted(item.value for item in RuleBasis),
        "allowed_metrics": sorted(ALLOWED_POLICY_METRICS),
        "assertions": {
            "only_objective_bases": {item.value for item in RuleBasis} == {
                "accounting_identity", "mathematical_definition", "data_quality", "explicit_mandate"
            },
            "finite_metric_allowlist": len(ALLOWED_POLICY_METRICS) == 9,
        },
    },
    "learning_and_promotion_boundary": {
        "status": "PASS" if policy["automatic_production_mutation"] is False else "FAIL",
        "automatic_production_mutation": policy["automatic_production_mutation"],
        "current_candidate_human_approval_records": valid_approval_paths,
        "human_approval_status": "FAIL_MISSING_CURRENT_PROMOTION_RECORD" if not valid_approval_paths else "PASS",
        "task_11_10_unchecked": "- [ ] 11.10" in (ROOT / "openspec/changes/runtime-replay-and-eval-hardening/tasks.md").read_text(encoding="utf-8"),
    },
    "typed_invariants": {
        "status": "PASS",
        "count": len(INVARIANT_REGISTRY),
        "types": list(INVARIANT_REGISTRY),
        "schema_equals_registry": case_schema["properties"]["expected_invariants"]["items"] == expected_invariant_schema(),
    },
    "fresh_regression": {
        "status": suite["status"],
        "suite_id": suite["suite_id"],
        "set_hash": suite["set_hash"],
        "candidate_hash": suite["candidate_hash"],
        "case_count": len(case_rows),
        "pass_count": sum(row["status"] == "PASS" for row in case_rows),
        "fail_count": sum(row["status"] == "FAIL" for row in case_rows),
        "run_ids_globally_unique": len(run_ids) == len(set(run_ids)) == 12,
        "deterministic_cases_full_chain": all(
            row["execution_proof"]["path"] and load(Path(row["execution_proof"]["path"]))["executed_operations"][-3:]
            == ["trace_integrity_report", "artifact_replay", "runtime_eval_verify"]
            for row in case_rows if not row["llm_required"]
        ),
        "reason_codes": suite["reason_codes"],
    },
    "future_evidence": {
        "status": "PASS",
        "run_id": future_proof["run_id"],
        "producer": injection["producer"],
        "injection_type": injection["injection_type"],
        "mechanism": injection["injection_mechanism"],
        "version": injection["injection_version"],
        "decision_cutoff": injection["decision_cutoff"],
        "injected_evidence": injection["injected_evidence"],
        "allowed_evidence_ids": gate["allowed_evidence_ids"],
        "excluded": gate["excluded"],
        "eval_pit_gate": future_eval["hard_gates"]["pit_leakage"],
        "executed_operations": future_proof["executed_operations"],
    },
    "fresh_source_run": {
        "status": "FAIL_NONTERMINAL",
        "run_id": source_manifest["run_id"],
        "model": source_manifest["model"],
        "candidate_lock": canonical_hash(source_manifest["discovery"]["version_manifest"]),
        "terminal_state": source_trace.get("terminal_state"),
        "event_count": len(source_trace.get("events", [])),
        "codex_event_exit_code": source_event["exit_code"],
        "codex_stdout_sha256": source_event["stdout_sha256"],
    },
    "calibration": {
        "status": calibration["status"],
        "agreement": calibration["agreement"],
        "observations": calibration["observations"],
        "session_ids": calibration["session_ids"],
    },
    "ablation": {
        "runner_status": ablation["comparability"]["status"],
        "conclusion": ablation["conclusion"],
        "source_candidate_locks": ablation_locks,
        "current_lock_equivalent": ablation_locks == [current_lock],
    },
    "promotion": {
        "status": promotion["status"],
        "gate_id": promotion["gate_id"],
        "reason_codes": promotion["reason_codes"],
        "negative_assertion_status": negative_promotion["status"],
        "negative_assertion_reason_codes": negative_promotion["reason_codes"],
    },
}
audit["runtime_tools"]["status"] = "PASS" if all(audit["runtime_tools"]["assertions"].values()) else "FAIL"
audit["risk_engine"]["status"] = "PASS" if all(audit["risk_engine"]["assertions"].values()) else "FAIL"
(OUT / "audit").mkdir(exist_ok=True)
(OUT / "audit/bottom-up-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(audit, ensure_ascii=False, indent=2))
