"""Deterministic run-package lifecycle; contains no LLM orchestration."""

from __future__ import annotations

import json
import platform
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.deterministic.metrics import calculate_portfolio_metrics

from .decision_contract import load_decision_contract, render_cio_action_prompt
from .discovery import discover_product_resources
from .evidence_gate import FixtureValidationError, load_fixture, run_evidence_gate
from .execution_proof import ExecutionProofError, verify_specialist_execution_proof
from .format_repair import (
    build_format_repair_request,
    is_format_only_error,
    verify_format_repair,
)
from .hashing import canonical_hash, file_hash
from .invocation import (
    OUTPUT_SCHEMAS,
    build_cio_ablation_output_schema,
    build_live_cio_output_schema,
    build_specialist_output_schema,
    build_specialist_task_prompt,
    build_specialist_inputs,
    create_invocation_manifest,
    validate_skeptic_first_pass_input,
    verify_invocation_manifest,
)
from .risk_runtime import build_risk_snapshot, check_cio_draft
from .replay_capsule import build_replay_capsule, capsule_reference
from .runtime_profiles import validate_runtime_mode
from .terminal_contract import (
    FailureStage,
    RISK_LINEAGE_VERSION,
    RUN_ERROR_VERSION,
    TRACE_VERSION,
    normalize_failure_stage,
)
from .validation import (
    ArtifactValidationError,
    collect_evidence_refs,
    validate_cio_draft,
    validate_company_report,
    validate_skeptic_report,
    validate_evidence_closure,
)


RUN_PACKAGE_VERSION = "native-run-package/2.1.0"


class TerminalState(StrEnum):
    COMPLETED = "COMPLETED"
    SAFE_NO_TRADE = "SAFE_NO_TRADE"
    FAILED_VALIDATION = "FAILED_VALIDATION"


class RunPackageError(ValueError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise RunPackageError(f"artifact must be an object: {path}")
    return dict(value)


def _write_json(path: Path, value: Mapping[str, Any], *, replace: bool = False) -> None:
    if path.exists() and not replace:
        raise RunPackageError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    if path.exists():
        raise RunPackageError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _protected_files(repository_root: Path) -> list[Path]:
    roots = (
        repository_root / "product" / ".codex-plugin",
        repository_root / "product" / ".codex" / "agents",
        repository_root / "product" / "skills",
        repository_root / "product" / "schemas",
        repository_root / "product" / "contracts",
        repository_root / "product" / "deterministic",
        repository_root / "product" / "runtime",
    )
    files = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    files.extend(
        [
            repository_root / "product" / "AGENTS.md",
            repository_root / "product" / "version-manifest.json",
        ]
    )
    return sorted(set(path.resolve() for path in files))


def integrity_snapshot(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    files = {
        str(path.relative_to(root)): file_hash(path) for path in _protected_files(root)
    }
    return {"files": files, "snapshot_hash": canonical_hash(files)}


def verify_integrity(repository_root: Path, expected: Mapping[str, Any]) -> None:
    actual = integrity_snapshot(repository_root)
    if actual != expected:
        raise RunPackageError("PROTECTED_RUNTIME_INTEGRITY_CHANGED")


def _base_trace(run_id: str, run_manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": TRACE_VERSION,
        "run_id": run_id,
        "terminal_state": None,
        "failed_stage": None,
        "runtime": {
            "model": run_manifest["model"],
            "codex_runtime": run_manifest["codex_runtime"],
            "candidate_version": run_manifest["candidate_version"],
            "discovery_hash": run_manifest["discovery"]["discovery_hash"],
            "version_lock": run_manifest["discovery"]["version_manifest"],
            "runtime_profile": run_manifest["runtime_profile"],
            "replay_capsule": run_manifest.get("replay_capsule"),
            "trigger_reason": run_manifest.get("trigger_reason", "product_council"),
        },
        "agents": [],
        "events": [],
        "risk_lineage": [],
        "artifacts": {},
        "codex_execution": None,
        "mcp_events": [],
        "evidence_lineage": None,
    }


def _record_artifact(trace: dict[str, Any], run_dir: Path, path: Path) -> None:
    trace["artifacts"][str(path.relative_to(run_dir))] = file_hash(path)


def _record_all_artifacts(trace: dict[str, Any], run_dir: Path) -> None:
    # Rebuild the closure from the current run tree.  A retried stage may have
    # removed or renamed a transient artifact that was recorded by an earlier
    # failed terminalization; retaining that stale entry makes the final trace
    # impossible to verify even though the published package is self-consistent.
    trace["artifacts"] = {}
    for path in sorted(run_dir.rglob("*")):
        relative = path.relative_to(run_dir)
        # Invocation evidence and Codex's live SQLite/log state are control-plane
        # records.  They can still change while the deterministic finalizer is
        # hashing the business run package, so they must not enter that closure.
        operational = bool(relative.parts) and relative.parts[0] in {
            ".codex-runtime",
            "invocation",
        }
        if path.is_file() and path.name != "decision_trace.json" and not operational:
            _record_artifact(trace, run_dir, path)


def _enrich_trace_from_run(trace: dict[str, Any], run_dir: Path) -> None:
    gate_path = run_dir / "evidence" / "gate.json"
    if gate_path.is_file():
        gate = _read_json(gate_path)
        trace["evidence_lineage"] = {
            "decision_cutoff": gate["decision_cutoff"],
            "allowed_evidence_ids": gate["allowed_evidence_ids"],
            "excluded_evidence_ids": gate["excluded_evidence_ids"],
            "bundle_hash": gate["bundle_hash"],
            "freshness_policy_version": gate["freshness_policy_version"],
            "conflict_policy_version": gate["conflict_policy_version"],
        }
    agents_by_name = {
        str(item.get("name")): item
        for item in trace.get("agents", [])
        if isinstance(item, dict)
    }
    for agent_name, entry in agents_by_name.items():
        manifest_path = run_dir / "invocations" / f"{agent_name}.json"
        if not manifest_path.is_file():
            continue
        manifest = _read_json(manifest_path)
        entry.update(
            {
                "agent_sha256": manifest["agent"]["sha256"],
                "model": manifest["model"],
                "codex_runtime": manifest["codex_runtime"],
                "input_hash": manifest["input_hash"],
                "task_prompt_hash": manifest["task_prompt_hash"],
                "instruction_bundle_hash": manifest["instruction_bundle_hash"],
                "evidence_ids": manifest["evidence_ids"],
                "skills": manifest["skills"],
                "tool_permissions": manifest["tool_permissions"],
                "decision_contract": manifest["decision_contract"],
                "output_schema": manifest["output_schema"],
                "output_schema_hash": manifest["output_schema_hash"],
            }
        )
        output_root = "cio" if agent_name == "runtime_cio" else "agents"
        output_path = run_dir / output_root / f"{agent_name}.json"
        if output_path.is_file():
            entry["output_hash"] = canonical_hash(_read_json(output_path))
            entry["status"] = "COMPLETED"
    proof_path = run_dir / "events" / "codex" / "specialist-execution-proof.json"
    if proof_path.is_file():
        proof = _read_json(proof_path)
        trace["codex_execution"] = {
            "schema_version": proof["schema_version"],
            "proof_hash": proof["proof_hash"],
            "parent": proof["parent"],
            "dispatches": proof["dispatches"],
            "children": proof["children"],
            "parallel_dispatch_proven": proof["parallel_dispatch_proven"],
            "independent_sessions_proven": proof["independent_sessions_proven"],
            "specialist_topology": proof.get("specialist_topology", []),
            "portfolio_council_skill_bound": proof.get("portfolio_council_skill_bound"),
            "telemetry": proof.get("telemetry"),
        }
    mcp_path = run_dir / "events" / "mcp" / "events.jsonl"
    if mcp_path.is_file():
        trace["mcp_events"] = [
            json.loads(line)
            for line in mcp_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _render_report(decision: Mapping[str, Any]) -> str:
    item = decision["decisions"][0]
    risk = decision["risk_report"]
    lines = [
        "# Portfolio Council 研究建议",
        "",
        f"- Run ID: `{decision['run_id']}`",
        f"- 终态: `{decision['terminal_state']}`",
        f"- 动作: `{item['action']}`",
        f"- 仅供建议: `{str(decision['advisory_only']).lower()}`",
        f"- Risk 状态: `{risk['status']}`",
        "",
        "## Thesis",
        "",
        item.get("thesis") or "本次未形成可发布的投资 Thesis。",
        "",
        "## Counter Thesis",
        "",
        item.get("counter_thesis") or "本次未形成可发布的 Counter Thesis。",
        "",
        "## Evidence IDs",
        "",
    ]
    refs = item.get("evidence_refs", [])
    lines.extend([f"- `{ref}`" for ref in refs] or ["- 无"])
    lines.extend(["", "## 失效与重评条件", ""])
    conditions = item.get("invalidation_conditions", []) + item.get(
        "reevaluation_conditions", []
    )
    lines.extend([f"- {condition}" for condition in conditions] or ["- 无"])
    if item.get("no_trade_reason"):
        lines.extend(
            [
                "",
                "## NO_TRADE",
                "",
                f"- 原因码: `{item['no_trade_reason']}`",
                f"- 说明: {item['no_trade_explanation']}",
            ]
        )
    return "\n".join(lines) + "\n"


def _safe_no_trade_decision(
    *, run_id: str, reason: str, explanation: str, reevaluation: Sequence[str]
) -> dict[str, Any]:
    return {
        "schema_version": "final-decision/2.0.0",
        "run_id": run_id,
        "terminal_state": TerminalState.SAFE_NO_TRADE.value,
        "advisory_only": True,
        "decisions": [
            {
                "action": "NO_TRADE",
                "security_id": None,
                "thesis": "",
                "counter_thesis": "",
                "evidence_refs": [],
                "invalidation_conditions": [],
                "no_trade_reason": reason,
                "no_trade_explanation": explanation,
                "reevaluation_conditions": list(reevaluation),
            }
        ],
        "risk_report": {
            "status": "NOT_RUN",
            "reason": "PRE_AGENT_SAFE_TERMINATION",
            "policy_version": "risk/reference/1.0.0",
        },
    }


def _publish_terminal(
    run_dir: Path,
    *,
    decision: Mapping[str, Any],
    trace: dict[str, Any],
) -> None:
    decision_path = run_dir / "decision.json"
    report_path = run_dir / "report.md"
    trace_path = run_dir / "decision_trace.json"
    manifest_path = run_dir / "run_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    report_text = _render_report(decision)
    if manifest.get("source_mode") == "live":
        from .live_report import render_live_report
        from .live_context import load_live_run_context
        portfolio, snapshot, gate, calendar = load_live_run_context(run_dir, manifest)
        reports = {name: _read_json(run_dir / f"agents/{name}.json")
                   for name in ("runtime_company_analyst", "runtime_skeptic")
                   if (run_dir / f"agents/{name}.json").is_file()}
        report_text = render_live_report(dict(decision), gate=gate, reports=reports, holding_horizon=portfolio["holding_horizon"],
            portfolio=portfolio, snapshot=snapshot, calendar=calendar)
    _write_json(decision_path, decision)
    report_path.write_text(report_text, encoding="utf-8")
    trace["terminal_state"] = decision["terminal_state"]
    trace["failed_stage"] = None
    _enrich_trace_from_run(trace, run_dir)
    _record_all_artifacts(trace, run_dir)
    _write_json(trace_path, trace, replace=True)


def fail_run(
    run_dir: Path,
    *,
    run_id: str,
    code: str,
    message: str,
    failed_stage: FailureStage | str,
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if (run_dir / "decision.json").exists() or (run_dir / "report.md").exists():
        raise RunPackageError("FAILED_VALIDATION cannot coexist with final advice")
    stage = normalize_failure_stage(failed_stage)
    error = {
        "schema_version": RUN_ERROR_VERSION,
        "run_id": run_id,
        "terminal_state": TerminalState.FAILED_VALIDATION.value,
        "failed_stage": stage,
        "code": code,
        "message": message,
    }
    _write_json(run_dir / "run_error.json", error)
    current_trace = trace or {
        "schema_version": TRACE_VERSION,
        "run_id": run_id,
        "terminal_state": None,
        "failed_stage": None,
        "runtime": {},
        "agents": [],
        "events": [],
        "risk_lineage": [],
        "artifacts": {},
        "codex_execution": None,
        "mcp_events": [],
        "evidence_lineage": None,
    }
    current_trace["terminal_state"] = TerminalState.FAILED_VALIDATION.value
    current_trace["failed_stage"] = stage
    current_trace["events"].append(
        {"stage": "VALIDATION_FAILED", "failed_stage": stage, "code": code}
    )
    _enrich_trace_from_run(current_trace, run_dir)
    _record_all_artifacts(current_trace, run_dir)
    _write_json(run_dir / "decision_trace.json", current_trace, replace=True)
    return error


def prepare_run(
    repository_root: Path,
    *,
    fixture_path: Path,
    run_dir: Path,
    run_id: str,
    model: str,
    research_question: str,
    authenticity_required: bool = True,
    run_mode: str = "PRODUCT_COUNCIL",
    ablation_profile: str | None = None,
    trigger_reason: str = "product_council",
) -> dict[str, Any]:
    root = repository_root.resolve()
    try:
        topology = validate_runtime_mode(
            run_mode=run_mode, ablation_profile=ablation_profile
        )
    except ValueError as exc:
        raise RunPackageError(str(exc)) from exc
    fixture_root = (root / "evals" / "fixtures" / "codex-native").resolve()
    fixture_path = fixture_path.resolve()
    regression_injection_root = (run_dir.resolve().parent / "injection").resolve()
    regression_injected_fixture = (
        authenticity_required is False
        and trigger_reason == "regression_deterministic_injection"
        and fixture_path.is_relative_to(regression_injection_root)
        and fixture_path.name == "injected-fixture.json"
    )
    if not fixture_path.is_relative_to(fixture_root) and not regression_injected_fixture:
        raise RunPackageError("fixture must come from the versioned codex-native fixture root")
    if run_dir.exists():
        raise RunPackageError("run directory must be new")
    run_dir.mkdir(parents=True)

    try:
        discovery = discover_product_resources(root)
        if model != discovery.version_manifest["model"]:
            raise RunPackageError("explicit model differs from candidate manifest")
    except (OSError, ValueError) as exc:
        return fail_run(
            run_dir,
            run_id=run_id,
            code="PREFLIGHT_VALIDATION_FAILED",
            message=str(exc),
            failed_stage=FailureStage.PREFLIGHT,
        )

    try:
        fixture = load_fixture(fixture_path)
    except FixtureValidationError as exc:
        if not str(exc).startswith("portfolio "):
            return fail_run(
                run_dir,
                run_id=run_id,
                code="PREFLIGHT_VALIDATION_FAILED",
                message=str(exc),
                failed_stage=FailureStage.PREFLIGHT,
            )
        try:
            fixture = _read_json(fixture_path)
        except (OSError, ValueError) as read_error:
            return fail_run(
                run_dir,
                run_id=run_id,
                code="PREFLIGHT_VALIDATION_FAILED",
                message=str(read_error),
                failed_stage=FailureStage.PREFLIGHT,
            )
        integrity = integrity_snapshot(root)
        run_manifest = {
            "schema_version": RUN_PACKAGE_VERSION,
            "run_id": run_id,
            "candidate_version": discovery.version_manifest["candidate_version"],
            "codex_runtime": discovery.version_manifest["codex_runtime"],
            "model": model,
            "runtime_profile": discovery.version_manifest["runtime_profile"],
            "fixture": str(fixture_path),
            "fixture_id": fixture.get("fixture_id", "invalid-portfolio"),
            "decision_cutoff": fixture.get("decision_cutoff"),
            "research_question": research_question,
            "output_dir": str(run_dir.resolve()),
            "authenticity_required": authenticity_required,
            "run_mode": run_mode,
            "ablation_profile": ablation_profile,
            "trigger_reason": trigger_reason,
            "discovery": discovery.to_dict(),
            "integrity_before": integrity,
        }
        _write_json(run_dir / "run_manifest.json", run_manifest)
        trace = _base_trace(run_id, run_manifest)
        trace["events"].append(
            {
                "stage": "PRE_AGENT_SAFE_TERMINATION",
                "reason": "INPUT_INVALID",
                "detail": str(exc),
                "agent_calls": 0,
            }
        )
        decision = _safe_no_trade_decision(
            run_id=run_id,
            reason="INPUT_INVALID",
            explanation="Portfolio fixture 未通过确定性输入契约。",
            reevaluation=["修正持仓、现金或证券标识后重新运行。"],
        )
        _publish_terminal(run_dir, decision=decision, trace=trace)
        return {"run_id": run_id, "next_state": TerminalState.SAFE_NO_TRADE.value}
    except (OSError, ValueError) as exc:
        return fail_run(
            run_dir,
            run_id=run_id,
            code="PREFLIGHT_VALIDATION_FAILED",
            message=str(exc),
            failed_stage=FailureStage.PREFLIGHT,
        )

    integrity = integrity_snapshot(root)
    run_manifest = {
        "schema_version": RUN_PACKAGE_VERSION,
        "run_id": run_id,
        "candidate_version": discovery.version_manifest["candidate_version"],
        "codex_runtime": discovery.version_manifest["codex_runtime"],
        "model": model,
        "runtime_profile": discovery.version_manifest["runtime_profile"],
        "fixture": str(fixture_path),
        "fixture_id": fixture["fixture_id"],
        "decision_cutoff": fixture["decision_cutoff"],
        "research_question": research_question,
        "output_dir": str(run_dir.resolve()),
        "authenticity_required": authenticity_required,
        "run_mode": run_mode,
        "ablation_profile": ablation_profile,
        "trigger_reason": trigger_reason,
        "discovery": discovery.to_dict(),
        "integrity_before": integrity,
    }
    _write_json(run_dir / "run_manifest.json", run_manifest)
    _write_json(run_dir / "audit" / "fixture_snapshot.json", fixture)
    try:
        gate = run_evidence_gate(fixture, run_id=run_id).artifact
    except (OSError, ValueError, FixtureValidationError) as exc:
        return fail_run(
            run_dir,
            run_id=run_id,
            code="EVIDENCE_GATE_FAILED",
            message=str(exc),
            failed_stage=FailureStage.EVIDENCE_GATE,
        )
    _write_json(run_dir / "evidence" / "gate.json", gate)
    try:
        capsule = build_replay_capsule(
            root,
            run_dir=run_dir,
            run_id=run_id,
            locked_context={
                "candidate_version": run_manifest["candidate_version"],
                "model": model,
                "codex_runtime": run_manifest["codex_runtime"],
                "python_runtime": f"python/{platform.python_version()}",
                "runtime_profile": run_manifest["runtime_profile"],
                "run_mode": run_mode,
                "ablation_profile": ablation_profile,
                "trigger_reason": trigger_reason,
                "research_question": research_question,
                "decision_cutoff": fixture["decision_cutoff"],
                "fixture_hash": file_hash(run_dir / "audit" / "fixture_snapshot.json"),
                "gate_hash": file_hash(run_dir / "evidence" / "gate.json"),
                "version_manifest_hash": canonical_hash(discovery.version_manifest),
                "product_integrity_hash": integrity["snapshot_hash"],
            },
        )
    except (OSError, ValueError) as exc:
        return fail_run(
            run_dir,
            run_id=run_id,
            code="REPLAY_CAPSULE_BUILD_FAILED",
            message=str(exc),
            failed_stage=FailureStage.PREFLIGHT,
        )
    run_manifest["replay_capsule"] = capsule_reference(
        capsule, capsule_dir=run_dir / "replay_capsule"
    )
    run_manifest["execution_replay_supported"] = True
    _write_json(run_dir / "run_manifest.json", run_manifest, replace=True)
    trace = _base_trace(run_id, run_manifest)
    trace["events"].extend(
        [
            {"stage": "DISCOVERY_PREFLIGHT", "status": "PASSED"},
            {
                "stage": "EVIDENCE_GATE",
                "status": "PASSED",
                "allowed_evidence_ids": gate["allowed_evidence_ids"],
                "excluded_evidence_ids": gate["excluded_evidence_ids"],
                "bundle_hash": gate["bundle_hash"],
            },
        ]
    )
    for path in (run_dir / "run_manifest.json", run_dir / "evidence" / "gate.json"):
        _record_artifact(trace, run_dir, path)

    if not gate["allowed_evidence_ids"]:
        decision = _safe_no_trade_decision(
            run_id=run_id,
            reason="STALE_DATA",
            explanation="Point-in-time Evidence Gate 后没有可供研究使用的事实。",
            reevaluation=["提供不晚于 decision_cutoff 且满足 freshness policy 的证据。"],
        )
        trace["events"].append(
            {"stage": "PRE_AGENT_SAFE_TERMINATION", "agent_calls": 0}
        )
        _publish_terminal(run_dir, decision=decision, trace=trace)
        return {"run_id": run_id, "next_state": TerminalState.SAFE_NO_TRADE.value}

    inputs = build_specialist_inputs(
        run_id=run_id,
        fixture=fixture,
        allowed_evidence_ids=gate["allowed_evidence_ids"],
        research_question=research_question,
    )
    return _prepare_specialist_invocations(root, run_dir=run_dir, run_id=run_id,
        model=model, gate=gate, inputs=inputs, trace=trace, topology=topology)


def _prepare_specialist_invocations(root: Path, *, run_dir: Path, run_id: str,
                                    model: str, gate: Mapping[str, Any],
                                    inputs: Mapping[str, Any], trace: dict[str, Any],
                                    topology: Sequence[str]) -> dict[str, Any]:
    """共用确定性准备步骤；实际 Agent 委派仍由 Codex Skill 执行。"""
    specialists = tuple(agent for agent in topology if agent != "runtime_cio")
    if "runtime_skeptic" in specialists:
        validate_skeptic_first_pass_input(inputs["runtime_skeptic"])
    specialist_schema_paths: dict[str, Path] = {}
    for agent_name in specialists:
        schema_path = run_dir / "schemas" / Path(
            OUTPUT_SCHEMAS[agent_name]
        ).name
        _write_json(
            schema_path,
            build_specialist_output_schema(
                root,
                agent_name=agent_name,
                allowed_evidence_ids=gate["allowed_evidence_ids"],
            ),
        )
        specialist_schema_paths[agent_name] = schema_path
    for agent_name in specialists:
        agent_input = inputs[agent_name]
        input_path = run_dir / "inputs" / f"{agent_name}.json"
        _write_json(input_path, agent_input)
        task_prompt = build_specialist_task_prompt(
            agent_name=agent_name,
            allowed_evidence_ids=gate["allowed_evidence_ids"],
            source_mode=str(agent_input.get("source_mode", "fixture")),
        )
        _write_text(run_dir / "prompts" / f"{agent_name}.txt", task_prompt)
        manifest = create_invocation_manifest(
            root,
            run_id=run_id,
            agent_name=agent_name,
            agent_input=agent_input,
            task_prompt=task_prompt,
            model=model,
            evidence_ids=gate["allowed_evidence_ids"],
            output_schema_path=specialist_schema_paths[agent_name],
        )
        _write_json(run_dir / "invocations" / f"{agent_name}.json", manifest)
        trace["agents"].append(
            {
                "name": agent_name,
                "version": manifest["agent"]["version"],
                "invocation_id": manifest["invocation_id"],
                "manifest_hash": manifest["manifest_hash"],
                "status": "PREPARED",
            }
        )
    trace["events"].append(
        {
            "stage": "SPECIALIST_INVOCATIONS_PREPARED",
            "agents": list(specialists),
        }
    )
    _write_json(run_dir / "decision_trace.json", trace, replace=True)
    if not specialists:
        return prepare_cio(root, run_dir=run_dir, model=model)
    return {"run_id": run_id, "next_state": "DISPATCH_REQUIRED"}


def prepare_live_run(repository_root: Path, *, portfolio_path: Path, snapshot_path: Path,
                     cache_root: Path, calendar, run_dir: Path, run_id: str, model: str,
                     focus_security_id: str | None = None, authenticity_required: bool = True) -> dict[str, Any]:
    """复用运行包生命周期准备 live；此函数不采集数据、不委派模型。"""
    from product.mcp.live.contracts import external_path, validate_contract
    from product.mcp.live.market import load_locked_calendar
    from product.runtime.live_context import validate_raw_records, live_artifact_hashes, live_resource_hashes, source_topology_lock
    from product.runtime.live_input import load_live_portfolio, build_live_specialist_inputs
    from product.runtime.evidence_gate import run_live_evidence_gate
    import re

    if not isinstance(run_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}", run_id) is None:
        raise RunPackageError("LIVE_RUN_ID_INVALID")
    root = repository_root.resolve()
    run_dir = external_path(run_dir)
    portfolio_path, snapshot_path, cache_root = [external_path(p) for p in (portfolio_path, snapshot_path, cache_root)]
    if run_dir.exists():
        raise RunPackageError("run directory must be new")
    run_dir.mkdir(parents=True, mode=0o700)
    trace = None
    try:
        discovery = discover_product_resources(root, source_profile="live-us-equity")
        if model != discovery.version_manifest["model"]:
            raise RunPackageError("explicit model differs from candidate manifest")
        portfolio = load_live_portfolio(portfolio_path)
        snapshot = _read_json(snapshot_path)
        validate_contract("snapshot", snapshot)
        if authenticity_required and snapshot["schema_version"] != "live-snapshot/4.0.0":
            raise RunPackageError("LIVE_CURRENT_SNAPSHOT_REQUIRED")
        if snapshot["schema_version"] in ("live-snapshot/3.0.0", "live-snapshot/4.0.0") and (
                {s["security_id"] for s in snapshot["source_selections"]} != {p["security_id"] for p in portfolio["positions"]}):
            raise RunPackageError("LIVE_ROUTING_PORTFOLIO_COVERAGE_MISMATCH")
        if snapshot["portfolio_hash"] != canonical_hash(portfolio):
            raise RunPackageError("LIVE_SNAPSHOT_PORTFOLIO_MISMATCH")
        focus = focus_security_id if focus_security_id is not None else portfolio["focus_security_id"]
        if focus not in {p["security_id"] for p in portfolio["positions"]}:
            raise RunPackageError("LIVE_FOCUS_UNKNOWN")
        def read_cached(digest):
            path = cache_root / "objects" / digest
            if path.is_symlink() or not path.resolve().is_relative_to(cache_root):
                raise RunPackageError("LIVE_CACHE_PATH_ESCAPE")
            return path.read_bytes()
        objects = validate_raw_records(snapshot, read_cached)
        if authenticity_required and snapshot.get("identity") is not None:
            from product.mcp.live.security_metadata import METADATA_VERSION, EASTMONEY_METADATA_VERSION
            versions = (METADATA_VERSION, EASTMONEY_METADATA_VERSION) if snapshot["schema_version"] in ("live-snapshot/3.0.0", "live-snapshot/4.0.0") else (METADATA_VERSION,)
            if any(item.get("metadata_version") not in versions for item in snapshot["identity"]["security_metadata"]):
                raise RunPackageError("LIVE_REAL_IDENTITY_PROOF_REQUIRED")
        calendar_record = calendar.lock_record()
        calendar = load_locked_calendar(calendar_record)
        gate = run_live_evidence_gate(snapshot, run_id=run_id, calendar=calendar).artifact
        for path, value in (("audit/live/portfolio.json", portfolio), ("audit/live/snapshot.json", snapshot),
                            ("audit/live/calendar.json", calendar_record), ("evidence/gate.json", gate)):
            _write_json(run_dir / path, value)
        for digest, raw in objects.items():
            path = run_dir / "audit/live/objects" / digest
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("xb") as stream:
                stream.write(raw)
        manifest = {
            "schema_version": "native-run-package/3.0.0", "source_mode": "live", "run_id": run_id,
            "specialist_context_delivery": "subagent-start-context/2.0.0",
            "specialist_output_delivery": "native-research-draft/1.0.0",
            "candidate_version": discovery.version_manifest["candidate_version"],
            "codex_runtime": discovery.version_manifest["codex_runtime"], "model": model,
            "runtime_profile": discovery.version_manifest["runtime_profile"],
            "decision_cutoff": snapshot["decision_cutoff"], "research_question": portfolio["research_question"],
            "focus_security_id": focus, "output_dir": str(run_dir), "authenticity_required": authenticity_required,
            "run_mode": "PRODUCT_COUNCIL", "ablation_profile": None, "trigger_reason": "live_advisory",
            "discovery": discovery.to_dict(), "integrity_before": integrity_snapshot(root),
            "source_context": {"snapshot_hash": snapshot["snapshot_hash"], "artifact_hashes": live_artifact_hashes(run_dir),
                               "resource_hashes": live_resource_hashes(root),
                               "topology_lock": source_topology_lock(snapshot)},
            "execution_replay_supported": False,
            "execution_replay_scope": "Live execution replay is outside this Change; no historical lock is modified."
        }
        _write_json(run_dir / "run_manifest.json", manifest)
        trace = _base_trace(run_id, manifest)
        trace["runtime"]["source_context"] = manifest["source_context"]
        trace["runtime"]["specialist_context_delivery"] = manifest["specialist_context_delivery"]
        trace["events"].extend([{"stage": "DISCOVERY_PREFLIGHT", "status": "PASSED", "source_mode": "live"},
                               {"stage": "EVIDENCE_GATE", "status": "PASSED", "bundle_hash": gate["bundle_hash"]}])
        _write_json(run_dir / "decision_trace.json", trace)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return fail_run(run_dir, run_id=run_id, code="LIVE_PREPARE_VALIDATION_FAILED", message=str(exc),
                        failed_stage=FailureStage.PREFLIGHT, trace=trace)
    try:
        inputs = build_live_specialist_inputs(portfolio, snapshot, gate, calendar=calendar, focus_security_id=focus)
    except ValueError as exc:
        # 仅明确的缺价/身份缺失可前置安全终止；损坏、漂移等校验错误仍失败。
        if not str(exc).startswith(("LIVE_PRICE_MISSING:", "LIVE_IDENTITY_SNAPSHOT_MISSING")):
            return fail_run(run_dir, run_id=run_id, code="LIVE_INPUT_BINDING_FAILED", message=str(exc),
                            failed_stage=FailureStage.EVIDENCE_GATE, trace=trace)
        decision = _safe_no_trade_decision(run_id=run_id, reason="INPUT_INVALID", explanation=str(exc),
            reevaluation=["补齐合格行情与证券身份后重新冻结资料；本次不构成研究质量通过。"])
        decision["decisions"][0].update(target_weight_range=None, maximum_notional=None)
        trace["events"].append({"stage": "PRE_AGENT_SAFE_TERMINATION", "agent_calls": 0, "reason": str(exc)})
        _publish_terminal(run_dir, decision=decision, trace=trace)
        return {"run_id": run_id, "next_state": TerminalState.SAFE_NO_TRADE.value}
    # 共用 fixture 已验证的 Schema、Prompt、Invocation 准备步骤。
    try:
        return _prepare_specialist_invocations(root, run_dir=run_dir, run_id=run_id, model=model,
            gate=gate, inputs=inputs, trace=trace, topology=validate_runtime_mode(run_mode="PRODUCT_COUNCIL", ablation_profile=None))
    except (OSError, ValueError) as exc:
        return fail_run(run_dir, run_id=run_id, code="LIVE_INVOCATION_PREPARE_FAILED", message=str(exc),
                        failed_stage=FailureStage.PREFLIGHT, trace=trace)


def prepare_cio(
    repository_root: Path,
    *,
    run_dir: Path,
    model: str,
) -> dict[str, Any]:
    root = repository_root.resolve()
    run_manifest = _read_json(run_dir / "run_manifest.json")
    run_id = run_manifest["run_id"]
    gate = _read_json(run_dir / "evidence" / "gate.json")
    reports: dict[str, dict[str, Any]] = {}
    refs: set[str] = set()
    validators = {
        "runtime_company_analyst": validate_company_report,
        "runtime_skeptic": validate_skeptic_report,
    }
    trace = _read_json(run_dir / "decision_trace.json")
    topology = validate_runtime_mode(
        run_mode=str(run_manifest.get("run_mode", "PRODUCT_COUNCIL")),
        ablation_profile=run_manifest.get("ablation_profile"),
    )
    specialists = tuple(agent for agent in topology if agent != "runtime_cio")
    try:
        for agent_name in specialists:
            validator = validators[agent_name]
            agent_input = _read_json(run_dir / "inputs" / f"{agent_name}.json")
            manifest = _read_json(run_dir / "invocations" / f"{agent_name}.json")
            verify_invocation_manifest(root, manifest, agent_input=agent_input)
            report_path = run_dir / "agents" / f"{agent_name}.json"
            report = _read_json(report_path)
            repair_request_path = run_dir / "repairs" / f"{agent_name}-request-1.json"
            if repair_request_path.is_file():
                repair_request = _read_json(repair_request_path)
                repaired_path = run_dir / str(
                    repair_request.get("repaired_output_relative_path", "")
                )
                if not repaired_path.is_file():
                    return {
                        "run_id": run_id,
                        "next_state": "ONE_SPECIALIST_FORMAT_REPAIR_REQUIRED",
                        "agent": agent_name,
                        "repair_request": str(repair_request_path),
                        "repaired_output": str(repaired_path),
                    }
                repaired = _read_json(repaired_path)
                verify_format_repair(
                    report,
                    repaired,
                    repair_request,
                    run_id=run_id,
                    agent_name=agent_name,
                    allowed_evidence_ids=manifest["evidence_ids"],
                )
                refs.update(validator(repaired, run_id=run_id, manifest=manifest))
                original_path = run_dir / "repairs" / f"{agent_name}-attempt-1.json"
                _write_json(original_path, report)
                _write_json(report_path, repaired, replace=True)
                acceptance = {
                    "schema_version": "specialist-format-repair-acceptance/2.0.0",
                    "run_id": run_id,
                    "agent": agent_name,
                    "repair_number": 1,
                    "request_hash": repair_request["request_hash"],
                    "original_report_hash": canonical_hash(report),
                    "repaired_report_hash": canonical_hash(repaired),
                    "evidence_refs": sorted(collect_evidence_refs(repaired)),
                    "status": "ACCEPTED",
                }
                _write_json(
                    run_dir / "repairs" / f"{agent_name}-acceptance.json",
                    acceptance,
                )
                trace["events"].append(
                    {
                        "stage": "SPECIALIST_FORMAT_REPAIR_ACCEPTED",
                        "agent": agent_name,
                        "repair_number": 1,
                        "request_hash": repair_request["request_hash"],
                    }
                )
                report = repaired
            else:
                try:
                    refs.update(validator(report, run_id=run_id, manifest=manifest))
                except ArtifactValidationError as exc:
                    if not is_format_only_error(exc):
                        raise
                    repair_request = build_format_repair_request(
                        report,
                        run_id=run_id,
                        agent_name=agent_name,
                        validation_error=exc,
                    )
                    _write_json(repair_request_path, repair_request)
                    trace["events"].append(
                        {
                            "stage": "SPECIALIST_FORMAT_REPAIR_REQUIRED",
                            "agent": agent_name,
                            "repair_number": 1,
                            "request_hash": repair_request["request_hash"],
                            "original_evidence_refs": repair_request[
                                "original_evidence_refs"
                            ],
                        }
                    )
                    _write_json(
                        run_dir / "decision_trace.json", trace, replace=True
                    )
                    return {
                        "run_id": run_id,
                        "next_state": "ONE_SPECIALIST_FORMAT_REPAIR_REQUIRED",
                        "agent": agent_name,
                        "repair_request": str(repair_request_path),
                        "repaired_output": str(
                            run_dir
                            / repair_request["repaired_output_relative_path"]
                        ),
                    }
            if run_manifest.get("source_mode") == "live" and run_manifest.get("authenticity_required", True):
                from .invocation import verify_specialist_start_binding
                verify_specialist_start_binding(root, run_dir, agent_name, report=report)
            reports[agent_name] = report
    except (OSError, ValueError, ArtifactValidationError, ImportError) as exc:
        trace["events"].append(
            {
                "stage": "SPECIALIST_FORMAT_REPAIR_REJECTED"
                if (run_dir / "repairs").is_dir()
                else "SPECIALIST_REPORT_REJECTED",
                "error": str(exc),
            }
        )
        return fail_run(
            run_dir,
            run_id=run_id,
            code="RUNTIME_DEPENDENCY_MISSING" if isinstance(exc, ImportError) else "SPECIALIST_REPORT_VALIDATION_FAILED",
            message=str(exc),
            failed_stage=FailureStage.SPECIALIST_VALIDATION,
            trace=trace,
        )

    live = run_manifest.get("source_mode") == "live"
    if live:
        try:
            from .live_context import load_live_run_context
            from .risk_runtime import build_live_risk_snapshot
            portfolio, evidence_snapshot, gate, calendar = load_live_run_context(run_dir, run_manifest)
            snapshot, valuation = build_live_risk_snapshot(portfolio, evidence_snapshot, gate, run_id=run_id, calendar=calendar)
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            return fail_run(
                run_dir, run_id=run_id,
                code="RUNTIME_DEPENDENCY_MISSING" if isinstance(exc, ImportError) else "LIVE_CIO_CONTEXT_INVALID",
                message=str(exc), failed_stage=FailureStage.CIO_SYNTHESIS, trace=trace,
            )
    else:
        fixture = _read_json(run_dir / "audit" / "fixture_snapshot.json")
        snapshot = build_risk_snapshot(fixture, run_id=run_id)
    metrics = calculate_portfolio_metrics(snapshot)
    if not specialists:
        refs.update(gate["allowed_evidence_ids"])
    cio_input = {
        "run_id": run_id,
        "agent": "runtime_cio",
        "decision_cutoff": run_manifest["decision_cutoff"],
        "research_question": run_manifest["research_question"],
        "validated_reports": reports,
        "validated_report_hashes": {
            agent_name: canonical_hash(report)
            for agent_name, report in reports.items()
        },
        "evidence_references": sorted(refs),
        "mechanical_conflicts": gate["conflicts"],
        "portfolio_metrics": json.loads(json.dumps(metrics, default=str)),
        "allowed_evidence_ids": sorted(refs),
        "evidence_access": "fixture_evidence.query",
    }
    if live:
        from product.mcp.live.identity import verify_frozen_identity
        identity = verify_frozen_identity(portfolio, evidence_snapshot["identity"], cutoff=evidence_snapshot["decision_cutoff"])
        cio_input.update(source_mode="live", evidence_access="live_evidence.query",
            security_id=run_manifest["focus_security_id"], holding_horizon=portfolio["holding_horizon"],
            portfolio_hash=canonical_hash(portfolio), snapshot_hash=evidence_snapshot["snapshot_hash"],
            gate_hash=gate["bundle_hash"], valuation_hash=valuation["valuation_hash"], identity_hash=identity["identity_hash"],
            valuation=valuation, mandate=portfolio["mandate"], data_gaps=evidence_snapshot["gaps"])
    _write_json(run_dir / "inputs" / "runtime_cio.json", cio_input)
    contract_prompt = render_cio_action_prompt(load_decision_contract(root / "product"))
    task_prompt = (
        f"按 {run_manifest.get('run_mode', 'PRODUCT_COUNCIL')} / {run_manifest.get('ablation_profile')} 拓扑，"
        f"综合 {len(reports)} 份已验证结构化报告与 Gate-scoped Evidence，输出 CIODecisionDraft 2.1.0 JSON；"
        "consumed_reports 必须逐字复制输入中的 validated_report_hashes，"
        "不得自行计算文件字节哈希。\n"
        f"{contract_prompt}"
    )
    if live:
        task_prompt += ("\n这是 live-us-equity 持仓研究，只允许 HOLD/TRIM/EXIT/NO_TRADE，security_id 必须为输入指定目标。"
                        "用中文说明持仓与期限、事实到假设到影响、独立反证及冲突取舍、可观察的失效条件和置信度依据。"
                        "不得把数据不足写成研究通过，不得补写无 Evidence 的事实；只使用 mcp__live_runtime__query。"
                        "当前估值基于完整组合，不能假定其他子运行建议已经成交。")
    _write_text(run_dir / "prompts" / "runtime_cio.txt", task_prompt)
    cio_schema_path: Path | None = None
    expected_report_agents: Sequence[str] | None = None
    if live:
        cio_schema_path = run_dir / "schemas" / "cio-decision-draft.schema.json"
        _write_json(cio_schema_path, build_live_cio_output_schema(root))
    elif run_manifest.get("run_mode") == "EVAL_ABLATION":
        cio_schema_path = run_dir / "schemas" / "cio-decision-draft.schema.json"
        _write_json(
            cio_schema_path,
            build_cio_ablation_output_schema(
                root, expected_report_agents=specialists
            ),
        )
        expected_report_agents = specialists
    manifest = create_invocation_manifest(
        root,
        run_id=run_id,
        agent_name="runtime_cio",
        agent_input=cio_input,
        task_prompt=task_prompt,
        model=model,
        evidence_ids=sorted(refs),
        output_schema_path=cio_schema_path,
        expected_report_agents=expected_report_agents,
    )
    _write_json(run_dir / "invocations" / "runtime_cio.json", manifest)
    trace["agents"].append(
        {
            "name": "runtime_cio",
            "version": manifest["agent"]["version"],
            "invocation_id": manifest["invocation_id"],
            "manifest_hash": manifest["manifest_hash"],
            "status": "PREPARED",
        }
    )
    trace["events"].append(
        {
            "stage": "SPECIALIST_REPORTS_VALIDATED",
            "reports": sorted(reports),
            "evidence_ids": sorted(refs),
        }
    )
    _write_json(run_dir / "decision_trace.json", trace, replace=True)
    return {"run_id": run_id, "next_state": "CIO_SYNTHESIS_REQUIRED"}


def finalize_cio(
    repository_root: Path,
    *,
    run_dir: Path,
    revision: bool = False,
) -> dict[str, Any]:
    root = repository_root.resolve()
    run_manifest = _read_json(run_dir / "run_manifest.json")
    run_id = run_manifest["run_id"]
    live = run_manifest.get("source_mode") == "live"
    if live:
        from .live_context import load_live_run_context
        from .risk_runtime import check_live_cio_draft
        portfolio, evidence_snapshot, live_gate, calendar = load_live_run_context(run_dir, run_manifest)
    else:
        fixture = _read_json(run_dir / "audit" / "fixture_snapshot.json")
    cio_input = _read_json(run_dir / "inputs" / "runtime_cio.json")
    manifest = _read_json(run_dir / "invocations" / "runtime_cio.json")
    draft_name = "runtime_cio_revision.json" if revision else "runtime_cio.json"
    draft_path = run_dir / "cio" / draft_name
    trace = _read_json(run_dir / "decision_trace.json")
    topology = validate_runtime_mode(
        run_mode=str(run_manifest.get("run_mode", "PRODUCT_COUNCIL")),
        ablation_profile=run_manifest.get("ablation_profile"),
    )
    specialists = tuple(agent for agent in topology if agent != "runtime_cio")
    if run_manifest.get("authenticity_required") is not False:
        try:
            proof = _read_json(
                run_dir / "events" / "codex" / "specialist-execution-proof.json"
            )
            specialist_manifests = {
                agent_name: _read_json(
                    run_dir / "invocations" / f"{agent_name}.json"
                )
                for agent_name in specialists
            }
            specialist_reports = {
                agent_name: _read_json(run_dir / "agents" / f"{agent_name}.json")
                for agent_name in specialists
            }
            mcp_event_path = run_dir / "events" / "mcp" / "events.jsonl"
            mcp_events = [
                json.loads(line)
                for line in mcp_event_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            verify_specialist_execution_proof(
                proof,
                invocation_manifests=specialist_manifests,
                reports=specialist_reports,
                mcp_events=mcp_events,
            )
        except (OSError, ValueError, ExecutionProofError, json.JSONDecodeError) as exc:
            return fail_run(
                run_dir,
                run_id=run_id,
                code="NATIVE_EXECUTION_PROOF_FAILED",
                message=str(exc),
                failed_stage=FailureStage.EXECUTION_PROOF,
                trace=trace,
            )
    try:
        verify_invocation_manifest(root, manifest, agent_input=cio_input)
        draft = _read_json(draft_path)
        report_hashes = {
            agent_name: canonical_hash(
                _read_json(run_dir / "agents" / f"{agent_name}.json")
            )
            for agent_name in specialists
        }
        validate_cio_draft(
            draft,
            run_id=run_id,
            manifest=manifest,
            report_hashes=report_hashes,
            expected_report_agents=specialists,
        )
        if revision:
            original = _read_json(run_dir / "cio" / "runtime_cio.json")
            original_refs = set(original["evidence_refs"])
            if not set(draft["evidence_refs"]) <= original_refs:
                raise ArtifactValidationError("REVISION_EXPANDED_EVIDENCE_SET")
    except (OSError, ValueError, ArtifactValidationError, json.JSONDecodeError) as exc:
        return fail_run(
            run_dir,
            run_id=run_id,
            code="CIO_VALIDATION_FAILED",
            message=str(exc),
            failed_stage=FailureStage.CIO_VALIDATION,
            trace=trace,
        )

    risk_entry = {
        "schema_version": RISK_LINEAGE_VERSION,
        "run_id": run_id,
        "attempt": len(trace["risk_lineage"]) + 1,
        "status": "STARTED",
        "policy_version": run_manifest["discovery"]["version_manifest"]["risk_policy"],
        "input_hash": canonical_hash(draft),
        "result_hash": None,
        "result": None,
        "error": None,
    }
    trace["risk_lineage"].append(risk_entry)
    trace["events"].append(
        {
            "stage": "RISK_ENGINE_STARTED",
            "attempt": risk_entry["attempt"],
            "input_hash": risk_entry["input_hash"],
            "policy_version": risk_entry["policy_version"],
        }
    )
    _write_json(run_dir / "decision_trace.json", trace, replace=True)
    try:
        risk = (check_live_cio_draft(portfolio, evidence_snapshot, live_gate, draft, run_id=run_id,
                                   calendar=calendar, focus_security_id=run_manifest["focus_security_id"])
                if live else check_cio_draft(fixture, draft, run_id=run_id))
    except (OSError, ValueError, ArithmeticError, KeyError, TypeError) as exc:
        risk_entry["status"] = "FAILED"
        risk_entry["error"] = str(exc)
        _write_json(run_dir / "decision_trace.json", trace, replace=True)
        return fail_run(
            run_dir,
            run_id=run_id,
            code="RISK_ENGINE_FAILED",
            message=str(exc),
            failed_stage=FailureStage.RISK_ENGINE,
            trace=trace,
        )
    risk_entry["status"] = "COMPLETED"
    risk_entry["result_hash"] = canonical_hash(risk)
    risk_entry["result"] = risk

    risk_path = run_dir / "risk" / ("check-2.json" if revision else "check-1.json")
    _write_json(risk_path, risk)
    status = risk["check"]["status"]
    if status == "REVISE_REQUIRED" and not revision:
        request = {
            "schema_version": "risk-revision-request/2.0.0",
            "run_id": run_id,
            "revision_number": 1,
            "maximum_revisions": 1,
            "feasible_bounds": risk["check"]["feasible_bounds"],
            "violations": risk["check"]["violations"],
            "original_evidence_refs": draft["evidence_refs"],
        }
        _write_json(run_dir / "risk" / "revision-request.json", request)
        trace["events"].append({"stage": "RISK_REVISION_REQUIRED", "revision": 1})
        _write_json(run_dir / "decision_trace.json", trace, replace=True)
        return {"run_id": run_id, "next_state": "ONE_CIO_REVISION_REQUIRED"}

    if status == "APPROVED":
        terminal = (
            TerminalState.SAFE_NO_TRADE
            if draft["action"] == "NO_TRADE"
            else TerminalState.COMPLETED
        )
        item = {
            "action": draft["action"],
            "security_id": draft["security_id"],
            "current_weight": draft["current_weight"],
            "target_weight_range": draft["target_weight_range"],
            "maximum_notional": draft["maximum_notional"],
            "time_horizon": draft["time_horizon"],
            "thesis": draft["thesis"],
            "counter_thesis": draft["counter_thesis"],
            "evidence_refs": draft["evidence_refs"],
            "invalidation_conditions": draft["invalidation_conditions"],
            "unresolved_questions": draft["unresolved_questions"],
            "confidence": draft["confidence"],
            "confidence_rationale": draft["confidence_rationale"],
            "no_trade_reason": draft["no_trade_reason"],
            "no_trade_explanation": draft["no_trade_explanation"],
            "reevaluation_conditions": draft["reevaluation_conditions"],
        }
    else:
        terminal = TerminalState.SAFE_NO_TRADE
        # 已持久化的 Risk 结果及 Trace 引用不可变；第二次仍需修订时由终态契约否决。
        item = {
            "action": "NO_TRADE",
            "security_id": draft.get("security_id"),
            "thesis": draft.get("thesis", ""),
            "counter_thesis": draft.get("counter_thesis", ""),
            "evidence_refs": draft.get("evidence_refs", []),
            "invalidation_conditions": draft.get("invalidation_conditions", []),
            "no_trade_reason": "RISK_VETO",
            "no_trade_explanation": "deterministic Risk Engine 否决了 CIO 草案。",
            "reevaluation_conditions": ["仅在满足 Risk Engine 可行边界后重新评估。"],
        }
    decision = {
        "schema_version": "final-decision/2.0.0",
        "run_id": run_id,
        "terminal_state": terminal.value,
        "advisory_only": True,
        "decisions": [item],
        "risk_report": {
            "status": status,
            "policy_version": risk["policy_version"],
            "original_action": risk["original_action"],
            "final_action": risk["final_action"] if status == "APPROVED" else "NO_TRADE",
            "violations": risk["check"]["violations"],
            "feasible_bounds": risk["check"]["feasible_bounds"],
            "veto_reason": risk["veto_reason"] if status == "APPROVED" else "RISK_VETO",
        },
    }
    if live:
        item.setdefault("target_weight_range", None)
        item.setdefault("maximum_notional", None)
    try:
        gate = _read_json(run_dir / "evidence" / "gate.json")
        validate_evidence_closure(
            decision, allowed_evidence_ids=gate["allowed_evidence_ids"]
        )
        validate_evidence_closure(
            risk, allowed_evidence_ids=gate["allowed_evidence_ids"]
        )
        verify_integrity(root, run_manifest["integrity_before"])
    except (RunPackageError, ArtifactValidationError, OSError, ValueError) as exc:
        return fail_run(
            run_dir,
            run_id=run_id,
            code="RUNTIME_INTEGRITY_FAILED",
            message=str(exc),
            failed_stage=FailureStage.PUBLICATION_VALIDATION,
            trace=trace,
        )
    trace["events"].append(
        {
            "stage": "TERMINAL_DECISION_VALIDATED",
            "terminal_state": terminal.value,
            "risk_status": status,
        }
    )
    _publish_terminal(run_dir, decision=decision, trace=trace)
    return {"run_id": run_id, "next_state": terminal.value}
