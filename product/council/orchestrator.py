"""Test-only reference state machine for deterministic contract coverage.

This module is retained to exercise risk and output boundaries with fake callbacks.
It is not a product runtime entrypoint and must never be used to claim Codex Skill,
Subagent, or LLM participation.  The Codex-native entrypoint lives in the
``portfolio-council`` Skill; Python remains limited to deterministic tools,
validation, risk, replay, and persistence.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence

from .output import force_no_trade, validate_final_plan


REFERENCE_ONLY = True


class RuntimeAgent(Protocol):
    def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class RiskEngine(Protocol):
    def preflight(self, portfolio: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def final_check(
        self, portfolio: Mapping[str, Any], draft: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


Synthesis = Callable[
    [Mapping[str, Any], Sequence[Mapping[str, Any]], Mapping[str, Any]], Mapping[str, Any]
]
Revision = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]


def _preflight_no_trade_reason(preflight: Mapping[str, Any]) -> str:
    """Map objective risk/data vetoes to the public advisory reason taxonomy."""

    vetoes = {str(code) for code in preflight.get("veto_codes", ())}
    if "STALE_PRICE" in vetoes:
        return "STALE_DATA"
    if "POLICY_VERSION_MISMATCH" in vetoes:
        return "MANDATE_VIOLATION"
    if vetoes & {"LIQUIDITY_LIMIT", "MISSING_LIQUIDITY_DATA"}:
        return "LIQUIDITY_LIMIT"
    if "INVALID_INPUT" in vetoes:
        return "INPUT_INVALID"
    return "RISK_VETO"


@dataclass(frozen=True)
class CouncilRunResult:
    final_plan: Mapping[str, Any]
    reports: tuple[Mapping[str, Any], ...]
    preflight: Mapping[str, Any]
    draft_versions: tuple[Mapping[str, Any], ...]
    risk_reports: tuple[Mapping[str, Any], ...]
    trace_events: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


class CouncilOrchestrator:
    """Execute a bounded council run with isolated first-pass research."""

    def __init__(self, agents: Mapping[str, RuntimeAgent], max_workers: int = 4):
        self._agents = dict(agents)
        self._max_workers = max(1, max_workers)

    def _validate_capabilities(self, requested: Sequence[str]) -> tuple[str, ...]:
        capabilities = tuple(dict.fromkeys(requested))
        unknown = sorted(set(capabilities) - set(self._agents))
        if unknown:
            raise ValueError(f"unregistered capabilities: {unknown}")
        if not capabilities:
            raise ValueError("the CIO must request at least one capability")
        return capabilities

    def _research_request(
        self,
        capability: str,
        portfolio: Mapping[str, Any],
        evidence_refs: Sequence[str],
        decision_cutoff: str,
        preflight: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "capability": capability,
            "portfolio": deepcopy(dict(portfolio)),
            "evidence_refs": list(evidence_refs),
            "decision_cutoff": decision_cutoff,
            "risk_preflight": deepcopy(dict(preflight)),
            "isolation": "first-pass-no-peer-conclusions",
        }

    def run(
        self,
        *,
        portfolio: Mapping[str, Any],
        requested_capabilities: Sequence[str],
        evidence_refs: Sequence[str],
        cio_synthesize: Synthesis,
        risk_engine: RiskEngine,
        cio_revise: Revision | None = None,
        decision_cutoff: str | None = None,
    ) -> CouncilRunResult:
        capabilities = self._validate_capabilities(requested_capabilities)
        cutoff = decision_cutoff or datetime.now(timezone.utc).isoformat()
        preflight = dict(risk_engine.preflight(portfolio))
        events: list[dict[str, Any]] = [
            {"stage": "preflight", "capabilities": list(capabilities), "decision_cutoff": cutoff}
        ]

        if preflight.get("status") == "REJECTED":
            stopped_draft = {
                "schema_version": "1.0.0",
                "decisions": [
                    {"security_id": item.get("security_id", "PORTFOLIO")}
                    for item in portfolio.get("positions", ())
                    if isinstance(item, Mapping)
                ],
            }
            final = validate_final_plan(
                force_no_trade(
                    stopped_draft,
                    preflight,
                    reason=_preflight_no_trade_reason(preflight),
                )
            )
            events.append({"stage": "preflight_stop", "status": "REJECTED"})
            events.append({"stage": "finalized", "advisory_only": True})
            return CouncilRunResult(
                final_plan=final,
                reports=(),
                preflight=preflight,
                draft_versions=(),
                risk_reports=(preflight,),
                trace_events=tuple(events),
            )

        def invoke(capability: str) -> Mapping[str, Any]:
            request = self._research_request(
                capability, portfolio, evidence_refs, cutoff, preflight
            )
            report = dict(self._agents[capability](request))
            report.setdefault("capability", capability)
            return report

        with ThreadPoolExecutor(max_workers=min(self._max_workers, len(capabilities))) as pool:
            reports = tuple(pool.map(invoke, capabilities))
        events.append({"stage": "research_complete", "report_count": len(reports)})

        draft = dict(cio_synthesize(portfolio, reports, preflight))
        drafts = [deepcopy(draft)]
        risks = [dict(risk_engine.final_check(portfolio, draft))]
        events.append({"stage": "risk_check", "status": risks[-1].get("status"), "attempt": 1})

        if risks[-1].get("status") == "REVISE_REQUIRED" and cio_revise is not None:
            draft = dict(cio_revise(draft, risks[-1]))
            drafts.append(deepcopy(draft))
            risks.append(dict(risk_engine.final_check(portfolio, draft)))
            events.append({"stage": "risk_check", "status": risks[-1].get("status"), "attempt": 2})

        final_risk = risks[-1]
        if final_risk.get("status") != "APPROVED":
            final = force_no_trade(draft, final_risk)
        else:
            final = deepcopy(draft)
            final["advisory_only"] = True
            final["risk_report"] = deepcopy(final_risk)
        final = validate_final_plan(final)
        events.append({"stage": "finalized", "advisory_only": True})
        return CouncilRunResult(
            final_plan=final,
            reports=reports,
            preflight=preflight,
            draft_versions=tuple(drafts),
            risk_reports=tuple(risks),
            trace_events=tuple(events),
        )
