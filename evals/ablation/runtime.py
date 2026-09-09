"""Ablation comparison derived only from real Runtime and Eval artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.runtime_eval import verify_runtime_eval_job
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.trace_validation import trace_integrity_report


PROFILES = ("cio-only", "analyst-cio", "full-council")


class RuntimeAblationError(ValueError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeAblationError(f"ABLATION_ARTIFACT_INVALID:{path}") from exc
    if not isinstance(value, Mapping):
        raise RuntimeAblationError(f"ABLATION_ARTIFACT_NOT_OBJECT:{path}")
    return dict(value)


def _gate_context_hash(gate: Mapping[str, Any]) -> str:
    return canonical_hash({key: value for key, value in gate.items() if key not in {"run_id", "bundle_hash"}})


def _variant(repository_root: Path, profile: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(entry.get("run_dir"), str) or not isinstance(entry.get("eval_result"), str):
        raise RuntimeAblationError("STATIC_VARIANT_SCORE_FORBIDDEN")
    run_dir = Path(entry["run_dir"]).resolve()
    trace = _read(run_dir / "decision_trace.json")
    trace_integrity_report(trace, run_dir=run_dir)
    manifest = _read(run_dir / "run_manifest.json")
    if manifest.get("run_mode") != "EVAL_ABLATION" or manifest.get("ablation_profile") != profile:
        raise RuntimeAblationError(f"ABLATION_PROFILE_MISMATCH:{profile}")
    evaluation_path = Path(entry["eval_result"]).resolve()
    evaluation = _read(evaluation_path)
    if evaluation.get("schema_version") != "runtime-eval-job/1.0.0" or evaluation.get("run_id") != trace["run_id"]:
        raise RuntimeAblationError(f"ABLATION_EVAL_INVALID:{profile}")
    try:
        verified_evaluation = verify_runtime_eval_job(
            repository_root,
            eval_result_path=evaluation_path,
        )
    except ValueError as exc:
        raise RuntimeAblationError(f"ABLATION_EVAL_VERIFICATION_FAILED:{profile}") from exc
    if verified_evaluation.get("eval_hash") != evaluation.get("eval_hash"):
        raise RuntimeAblationError(f"ABLATION_EVAL_HASH_MISMATCH:{profile}")
    fixture = _read(run_dir / "audit" / "fixture_snapshot.json")
    gate = _read(run_dir / "evidence" / "gate.json")
    version_lock = trace.get("runtime", {}).get("version_lock", {})
    semantic = evaluation["semantic_rubric"]
    applicable = [item["grade"] for item in semantic.values() if item["status"] != "NOT_APPLICABLE"]
    quality = sum(applicable) / (3 * len(applicable)) if applicable else None
    saved_telemetry = trace.get("codex_execution", {}).get("telemetry", {}) if isinstance(trace.get("codex_execution"), Mapping) else {}
    measured = saved_telemetry if manifest.get("authenticity_required") is not False else entry
    missing_telemetry = any(measured.get(field) is None for field in ("input_tokens", "output_tokens", "latency_ms"))
    hard_gate_failures = [name for name, item in evaluation["hard_gates"].items() if item["status"] != "PASS"]
    return {
        "profile": profile,
        "run_id": trace["run_id"],
        "run_dir": str(run_dir),
        "eval_result": str(evaluation_path),
        "trace_hash": canonical_hash(trace),
        "eval_hash": evaluation["eval_hash"],
        "eval_artifact_hash": file_hash(evaluation_path),
        "comparison_lock": {
            "portfolio_hash": canonical_hash(fixture["portfolio"]),
            "gate_context_hash": _gate_context_hash(gate),
            "version_lock_hash": canonical_hash(version_lock),
            "model": trace.get("runtime", {}).get("model"),
            "risk_policy": version_lock.get("risk_policy"),
            "rubric_hash": evaluation["source_hashes"].get("rubric"),
            "case_id": entry.get("case_id"),
        },
        "metrics": {
            "semantic_quality": quality,
            "evidence_grounding": semantic.get("analyst_thesis_grounding", {}).get("grade"),
            "counter_evidence": semantic.get("skeptic_counter_evidence", {}).get("grade"),
            "no_trade_quality": semantic.get("no_trade_reasoning", {}).get("grade"),
            "conflict_handling": semantic.get("cio_conflict_handling", {}).get("grade"),
            "risk_violations": int("risk_bypass" in hard_gate_failures),
            "schema_failures": int("schema_and_artifacts" in hard_gate_failures),
            "input_tokens": measured.get("input_tokens") if not missing_telemetry else None,
            "output_tokens": measured.get("output_tokens") if not missing_telemetry else None,
            "latency_ms": measured.get("latency_ms") if not missing_telemetry else None,
            "telemetry_status": "MISSING_TELEMETRY" if missing_telemetry else "AVAILABLE",
        },
    }


def _conclusion(records: Sequence[Mapping[str, Any]], *, threshold: float) -> tuple[str, list[str]]:
    quality = {record["profile"]: record["metrics"]["semantic_quality"] for record in records}
    if all(value is None for value in quality.values()):
        safe_stop = all(
            int(record["metrics"]["risk_violations"]) == 0
            and int(record["metrics"]["schema_failures"]) == 0
            for record in records
        )
        if safe_stop:
            return "NO_MEASURABLE_GAIN", ["NO_SEMANTIC_DIMENSIONS_APPLICABLE"]
        return "NOT_COMPARABLE", ["ABLATION_NOT_COMPARABLE"]
    if any(value is None for value in quality.values()):
        return "NOT_COMPARABLE", ["ABLATION_NOT_COMPARABLE"]
    baseline = max(float(quality["cio-only"]), float(quality["analyst-cio"]))
    gain = float(quality["full-council"]) - baseline
    if gain >= threshold:
        return "MEASURABLE_GAIN", []
    if gain < 0:
        return "NEGATIVE_GAIN", []
    return "NO_MEASURABLE_GAIN", ["NO_MEASURABLE_GAIN"]


def _compare_case(
    repository_root: Path,
    *,
    case_id: str,
    variants: Mapping[str, Mapping[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    if set(variants) != set(PROFILES):
        raise RuntimeAblationError(f"ABLATION_PROFILE_SET_INVALID:{case_id}")
    records = [_variant(repository_root, profile, variants[profile]) for profile in PROFILES]
    if any(record["comparison_lock"]["case_id"] != case_id for record in records):
        raise RuntimeAblationError(f"ABLATION_CASE_ID_MISMATCH:{case_id}")
    locks = [record["comparison_lock"] for record in records]
    comparable = all(lock == locks[0] for lock in locks[1:])
    if comparable:
        conclusion, reason_codes = _conclusion(records, threshold=threshold)
    else:
        conclusion, reason_codes = "NOT_COMPARABLE", ["ABLATION_NOT_COMPARABLE"]
    return {
        "case_id": case_id,
        "profiles": records,
        "comparability": {"status": "PASS" if comparable else "FAIL", "lock": locks[0] if comparable else None},
        "conclusion": conclusion,
        "reason_codes": reason_codes,
    }


def _mean(values: Sequence[Any]) -> float | None:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return sum(numeric) / len(numeric) if numeric else None


def _aggregate_profile(cases: Sequence[Mapping[str, Any]], profile: str) -> dict[str, Any]:
    records = [
        next(record for record in case["profiles"] if record["profile"] == profile)
        for case in cases
    ]
    telemetry_available = all(record["metrics"]["telemetry_status"] == "AVAILABLE" for record in records)
    metrics = {
        "semantic_quality": _mean([record["metrics"]["semantic_quality"] for record in records]),
        "evidence_grounding": _mean([record["metrics"]["evidence_grounding"] for record in records]),
        "counter_evidence": _mean([record["metrics"]["counter_evidence"] for record in records]),
        "no_trade_quality": _mean([record["metrics"]["no_trade_quality"] for record in records]),
        "conflict_handling": _mean([record["metrics"]["conflict_handling"] for record in records]),
        "risk_violations": sum(int(record["metrics"]["risk_violations"]) for record in records),
        "schema_failures": sum(int(record["metrics"]["schema_failures"]) for record in records),
        "input_tokens": sum(int(record["metrics"]["input_tokens"]) for record in records) if telemetry_available else None,
        "output_tokens": sum(int(record["metrics"]["output_tokens"]) for record in records) if telemetry_available else None,
        "latency_ms": sum(int(record["metrics"]["latency_ms"]) for record in records) if telemetry_available else None,
        "telemetry_status": "AVAILABLE" if telemetry_available else "MISSING_TELEMETRY",
    }
    aggregate = {
        "profile": profile,
        "run_ids": [record["run_id"] for record in records],
        "trace_hashes": [record["trace_hash"] for record in records],
        "eval_hashes": [record["eval_hash"] for record in records],
        "metrics": metrics,
    }
    if len(records) == 1:
        aggregate.update(
            run_id=records[0]["run_id"],
            trace_hash=records[0]["trace_hash"],
            eval_hash=records[0]["eval_hash"],
        )
    return aggregate


def compare_runtime_ablation_set(
    repository_root: Path,
    *,
    ablation_id: str,
    cases: Mapping[str, Mapping[str, Mapping[str, Any]]],
    output_dir: Path,
) -> dict[str, Any]:
    """Compare a declared set of case-matched A/B/C runs and aggregate honestly."""

    if output_dir.exists():
        raise RuntimeAblationError("ABLATION_OUTPUT_EXISTS")
    profile_contract = _read(repository_root / "evals" / "ablation" / "profiles-v1.json")
    expected_cases = profile_contract["representative_cases"]
    if list(cases) != expected_cases:
        raise RuntimeAblationError("ABLATION_REPRESENTATIVE_CASE_SET_INVALID")
    threshold = float(profile_contract["quality_gain_threshold"])
    case_results = [
        _compare_case(
            repository_root,
            case_id=case_id,
            variants=cases[case_id],
            threshold=threshold,
        )
        for case_id in expected_cases
    ]
    aggregate_profiles = [_aggregate_profile(case_results, profile) for profile in PROFILES]
    comparable = all(
        case["comparability"]["status"] == "PASS" and case["conclusion"] != "NOT_COMPARABLE"
        for case in case_results
    )
    if comparable:
        conclusion, reason_codes = _conclusion(aggregate_profiles, threshold=threshold)
    else:
        conclusion = "NOT_COMPARABLE"
        reason_codes = [
            f"ABLATION_CASE_NOT_COMPARABLE:{case['case_id']}"
            for case in case_results
            if case["comparability"]["status"] != "PASS" or case["conclusion"] == "NOT_COMPARABLE"
        ]
    body: dict[str, Any] = {
        "schema_version": "ablation-report/1.0.0",
        "ablation_id": ablation_id,
        "cases": case_results,
        "profiles": aggregate_profiles,
        "comparability": {"status": "PASS" if comparable else "FAIL", "case_count": len(case_results)},
        "metrics": {record["profile"]: record["metrics"] for record in aggregate_profiles},
        "configuration": {
            "profiles_hash": canonical_hash(profile_contract),
            "representative_cases": expected_cases,
        },
        "conclusion": conclusion,
        "reason_codes": reason_codes,
    }
    body["report_hash"] = canonical_hash(body)
    schema = _read(repository_root / "product" / "schemas" / "runtime" / "ablation-report.schema.json")
    validate_schema_instance(body, schema)
    output_dir.mkdir(parents=True)
    (output_dir / "result.json").write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Multi-Agent Ablation 报告",
        "",
        f"- Ablation ID：`{ablation_id}`",
        f"- 代表案例：`{len(case_results)}`",
        f"- 聚合结论：`{conclusion}`",
        "",
        "## 逐案例",
        "",
    ]
    for case in case_results:
        lines.append(f"### {case['case_id']}")
        lines.append("")
        lines.append(f"- 可比性：`{case['comparability']['status']}`；结论：`{case['conclusion']}`")
        for record in case["profiles"]:
            lines.append(
                f"- {record['profile']}: run_id={record['run_id']}, trace={record['trace_hash']}, "
                f"eval={record['eval_hash']}, quality={record['metrics']['semantic_quality']}, "
                f"tokens={record['metrics']['input_tokens']}+{record['metrics']['output_tokens']}, "
                f"latency_ms={record['metrics']['latency_ms']}, telemetry={record['metrics']['telemetry_status']}"
            )
        lines.append("")
    lines.extend(["## 聚合 Profile", ""])
    for record in aggregate_profiles:
        lines.append(
            f"- {record['profile']}: quality={record['metrics']['semantic_quality']}, "
            f"tokens={record['metrics']['input_tokens']}+{record['metrics']['output_tokens']}, "
            f"latency_ms={record['metrics']['latency_ms']}, telemetry={record['metrics']['telemetry_status']}"
        )
    lines.extend(["", "## Reason Codes", ""])
    lines.extend([f"- `{code}`" for code in reason_codes] or ["- 无"])
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return body


def compare_runtime_variants(
    repository_root: Path,
    *,
    ablation_id: str,
    variants: Mapping[str, Mapping[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    if set(variants) != set(PROFILES):
        raise RuntimeAblationError("ABLATION_PROFILE_SET_INVALID")
    case_ids = {str(entry.get("case_id")) for entry in variants.values()}
    if len(case_ids) != 1:
        raise RuntimeAblationError("ABLATION_CASE_ID_MISMATCH")
    case_id = case_ids.pop()
    profile_contract = _read(repository_root / "evals" / "ablation" / "profiles-v1.json")
    case = _compare_case(
        repository_root,
        case_id=case_id,
        variants=variants,
        threshold=float(profile_contract["quality_gain_threshold"]),
    )
    records = case["profiles"]
    body: dict[str, Any] = {
        "schema_version": "ablation-report/1.0.0",
        "ablation_id": ablation_id,
        "cases": [case],
        "profiles": records,
        "comparability": case["comparability"],
        "metrics": {record["profile"]: record["metrics"] for record in records},
        "configuration": {
            "profiles_hash": canonical_hash(profile_contract),
            "representative_cases": [case_id],
        },
        "conclusion": case["conclusion"],
        "reason_codes": case["reason_codes"],
    }
    body["report_hash"] = canonical_hash(body)
    schema = _read(repository_root / "product" / "schemas" / "runtime" / "ablation-report.schema.json")
    validate_schema_instance(body, schema)
    output_dir.mkdir(parents=True)
    (output_dir / "result.json").write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Multi-Agent Ablation 报告", "", f"- Ablation ID：`{ablation_id}`", f"- 结论：`{body['conclusion']}`", ""]
    for record in records:
        lines.append(
            f"- {record['profile']}: run_id={record['run_id']}, trace={record['trace_hash']}, "
            f"eval={record['eval_hash']}, quality={record['metrics']['semantic_quality']}, "
            f"tokens={record['metrics']['input_tokens']}+{record['metrics']['output_tokens']}, "
            f"latency_ms={record['metrics']['latency_ms']}, telemetry={record['metrics']['telemetry_status']}"
        )
    lines.extend(["", "## Reason Codes", ""])
    lines.extend([f"- `{code}`" for code in body["reason_codes"]] or ["- 无"])
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return body


def verify_runtime_ablation_result(repository_root: Path, result_path: Path) -> dict[str, Any]:
    """Recompute an ablation report from the bound run and Eval artifacts."""

    saved = _read(result_path.resolve())
    body = dict(saved)
    if body.pop("report_hash", None) != canonical_hash(body):
        raise RuntimeAblationError("ABLATION_REPORT_HASH_INVALID")
    contract = _read(repository_root / "evals" / "ablation" / "profiles-v1.json")
    threshold = float(contract["quality_gain_threshold"])
    rebuilt_cases = []
    for saved_case in saved.get("cases", []):
        variants = {
            record["profile"]: {
                "run_dir": record["run_dir"],
                "eval_result": record["eval_result"],
                "case_id": saved_case["case_id"],
                "input_tokens": record.get("metrics", {}).get("input_tokens"),
                "output_tokens": record.get("metrics", {}).get("output_tokens"),
                "latency_ms": record.get("metrics", {}).get("latency_ms"),
            }
            for record in saved_case.get("profiles", [])
        }
        rebuilt_cases.append(
            _compare_case(
                repository_root,
                case_id=saved_case["case_id"],
                variants=variants,
                threshold=threshold,
            )
        )
    if not rebuilt_cases:
        raise RuntimeAblationError("ABLATION_CASES_MISSING")
    aggregate_profiles = (
        [_aggregate_profile(rebuilt_cases, profile) for profile in PROFILES]
        if len(rebuilt_cases) > 1
        else rebuilt_cases[0]["profiles"]
    )
    comparable = all(
        case["comparability"]["status"] == "PASS" and case["conclusion"] != "NOT_COMPARABLE"
        for case in rebuilt_cases
    )
    if len(rebuilt_cases) == 1:
        conclusion = rebuilt_cases[0]["conclusion"]
        reason_codes = rebuilt_cases[0]["reason_codes"]
        comparability = rebuilt_cases[0]["comparability"]
    elif comparable:
        conclusion, reason_codes = _conclusion(aggregate_profiles, threshold=threshold)
        comparability = {"status": "PASS", "case_count": len(rebuilt_cases)}
    else:
        conclusion = "NOT_COMPARABLE"
        reason_codes = [
            f"ABLATION_CASE_NOT_COMPARABLE:{case['case_id']}"
            for case in rebuilt_cases
            if case["comparability"]["status"] != "PASS" or case["conclusion"] == "NOT_COMPARABLE"
        ]
        comparability = {"status": "FAIL", "case_count": len(rebuilt_cases)}
    rebuilt: dict[str, Any] = {
        "schema_version": "ablation-report/1.0.0",
        "ablation_id": saved["ablation_id"],
        "cases": rebuilt_cases,
        "profiles": aggregate_profiles,
        "comparability": comparability,
        "metrics": {record["profile"]: record["metrics"] for record in aggregate_profiles},
        "configuration": {
            "profiles_hash": canonical_hash(contract),
            "representative_cases": [case["case_id"] for case in rebuilt_cases],
        },
        "conclusion": conclusion,
        "reason_codes": reason_codes,
    }
    rebuilt["report_hash"] = canonical_hash(rebuilt)
    if rebuilt != saved:
        raise RuntimeAblationError("ABLATION_REPORT_RECOMPUTE_MISMATCH")
    return rebuilt
