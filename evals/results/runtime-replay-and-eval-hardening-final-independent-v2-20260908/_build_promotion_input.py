from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path("/Users/caihaoming/Documents/stock_agent")
OUT = ROOT / "evals/results/runtime-replay-and-eval-hardening-final-independent-v2-20260908"
OLD = ROOT / "evals/results/runtime-replay-and-eval-hardening-final-independent-20260908"


def ref(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


payload = {
    "schema_version": "promotion-input/1.0.0",
    "gate_id": "rrh-final-independent-v2-gate-20260908",
    "candidate_version": "0.3.0-candidate.1",
    "baseline_version": "0.2.1-candidate.1",
    "candidate_changes_default_topology": False,
    "artifacts": {
        "candidate_manifest": ref(ROOT / "product/version-manifest.json"),
        "baseline_manifest": ref(ROOT / "evals/results/runtime-replay-and-eval-hardening-acceptance-20260907/promotion/baseline-version-manifest.json"),
        "model_policy": ref(ROOT / "product/model-routing.json"),
        "deterministic_tests": ref(OUT / "test-evidence/full-suite/result.json"),
        "semantic_calibration": ref(OUT / "calibration/result/result.json"),
        "regression": ref(OUT / "regression/suite-fresh/result.json"),
        "execution_replay": ref(OLD / "replay/execution-replay-refinalized/result.json"),
        "runtime_evals": [
            ref(OLD / "runtime-evals/execution-source-risk-veto/eval/result.json"),
            ref(OLD / "runtime-evals/execution-replay-risk-veto/eval/result.json"),
        ],
        "grader_proofs": [
            ref(OLD / "runtime-evals/execution-source-risk-veto/grader-execution-proof.json"),
            ref(OLD / "runtime-evals/execution-replay-risk-veto/grader-execution-proof.json"),
        ],
        "baseline_runtime_evals": [],
        "ablation": ref(OUT / "ablation/result/result.json"),
        "baseline_ablation": None,
        "trace_integrity": [
            ref(OLD / "traces/execution-source-risk-veto.json"),
            ref(OLD / "traces/execution-replay-risk-veto.json"),
        ],
    },
}
(OUT / "promotion/input.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(OUT / "promotion/input.json")
