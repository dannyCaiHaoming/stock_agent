"""Build a complete append-only Decision Trace from a Council result."""

from __future__ import annotations

from typing import Sequence

from product.trace import DecisionTrace, DecisionTraceSnapshot, TraceStage, VersionLock

from .orchestrator import CouncilRunResult


def build_council_trace(
    *,
    run_id: str,
    trace_id: str,
    decision_cutoff: str,
    versions: VersionLock,
    result: CouncilRunResult,
    evidence_refs: Sequence[str],
) -> DecisionTraceSnapshot:
    """Record the causal artifact chain without re-running any LLM reasoning."""

    if not result.reports or not result.draft_versions:
        raise ValueError("a complete research trace requires reports and a CIO draft")
    trace = DecisionTrace(run_id, trace_id, decision_cutoff, versions)
    occurred_at = decision_cutoff

    def append(stage: TraceStage, suffix: str, inputs: Sequence[str], payload: dict) -> str:
        artifact_id = f"{run_id}-{suffix}"
        trace.append(
            event_id=f"{run_id}-event-{suffix}",
            stage=stage,
            occurred_at=occurred_at,
            producer_id=("risk-engine" if stage is TraceStage.RISK_REPORT else "portfolio-council"),
            artifact_id=artifact_id,
            input_artifact_ids=inputs,
            payload=payload,
        )
        return artifact_id

    input_id = append(TraceStage.INPUT, "input", (), {"advisory_only": True})
    plan_id = append(
        TraceStage.RESEARCH_PLAN,
        "research-plan",
        (input_id,),
        {"preflight_status": result.preflight.get("status")},
    )
    delegation_id = append(
        TraceStage.DELEGATION,
        "delegation",
        (plan_id,),
        {"capabilities": [report.get("capability") for report in result.reports]},
    )
    tool_id = append(TraceStage.TOOL_CALL, "tool-call", (delegation_id,), {"read_only": True})
    evidence_id = append(
        TraceStage.EVIDENCE,
        "evidence",
        (tool_id,),
        {"evidence_refs": list(evidence_refs)},
    )
    report_ids = tuple(
        append(
            TraceStage.AGENT_REPORT,
            f"agent-report-{index}",
            (delegation_id, evidence_id),
            {"capability": report.get("capability")},
        )
        for index, report in enumerate(result.reports, start=1)
    )
    draft_id = append(
        TraceStage.CIO_DRAFT,
        "cio-draft-1",
        report_ids,
        {"decision_count": len(result.draft_versions[0].get("decisions", ()))},
    )
    risk_id = append(
        TraceStage.RISK_REPORT,
        "risk-report-1",
        (draft_id,),
        {"status": result.risk_reports[0].get("status")},
    )
    final_input = risk_id
    if len(result.draft_versions) == 2:
        revision_id = append(
            TraceStage.CIO_REVISION,
            "cio-revision-1",
            (draft_id, risk_id),
            {"revision_count": 1},
        )
        final_input = append(
            TraceStage.RISK_REPORT,
            "risk-report-2",
            (revision_id,),
            {"status": result.risk_reports[1].get("status")},
        )
    append(
        TraceStage.FINAL_OUTPUT,
        "final-output",
        (final_input,),
        {"advisory_only": result.final_plan.get("advisory_only")},
    )
    return trace.snapshot(require_complete=True)
