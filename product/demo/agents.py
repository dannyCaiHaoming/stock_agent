"""三个相互独立的确定性 Demo Agent Adapter。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash

from .contracts import (
    RESPONSE_VERSION,
    DemoValidationError,
    validate_agent_request,
    validate_agent_response,
)
from .ports import DeterministicMathPort, EvidenceQueryPort


def _skill_execution(
    topology: Mapping[str, Any], *, run_id: str, invocation_id: str, agent: str
) -> list[dict[str, str]]:
    return [
        {
            "skill_name": item["name"],
            "version": item["version"],
            "invocation_hash": canonical_hash(
                {
                    "run_id": run_id,
                    "invocation_id": invocation_id,
                    "agent": agent,
                    "skill": item["name"],
                    "binding_only": True,
                    "reasoning_executed": False,
                }
            ),
        }
        for item in topology["agents"][agent]["skills"]
    ]


def _response(request: Mapping[str, Any], output: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": RESPONSE_VERSION,
        "run_id": request["run_id"],
        "invocation_id": request["invocation_id"],
        "agent_name": request["recipient"],
        "status": output["status"],
        "input_refs": deepcopy(request["input_refs"]),
        "output": dict(output),
        "producer_type": "deterministic_demo",
        "llm_used": False,
        "skill_reasoning_executed": False,
    }
    validate_agent_response(value, request=request)
    return value


class CompanyAnalystDemoAdapter:
    """封装 fixture 中的 Analyst 示例，不选择组合动作。"""

    agent_name = "runtime_company_analyst"

    def respond(
        self,
        request: Mapping[str, Any],
        *,
        evidence: EvidenceQueryPort,
        math: DeterministicMathPort,
        topology: Mapping[str, Any],
    ) -> dict[str, Any]:
        checked = validate_agent_request(request)
        if checked["recipient"] != self.agent_name:
            raise DemoValidationError("ANALYST_REQUEST_IDENTITY_INVALID")
        sample = deepcopy(checked["demo_payload"])
        evidence_ids = sample.pop("evidence_refs", None)
        calculation = sample.pop("calculation", None)
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise DemoValidationError("ANALYST_EVIDENCE_REFS_REQUIRED")
        evidence.query(evidence_ids=evidence_ids)
        artifact_refs: list[str] = []
        if calculation is not None:
            if not isinstance(calculation, Mapping):
                raise DemoValidationError("ANALYST_CALCULATION_INVALID")
            result = math.calculate(
                calculation_id=str(calculation.get("calculation_id", "")),
                operation=str(calculation.get("operation", "")),
                evidence_ids=calculation.get("evidence_ids", []),
            )
            artifact_refs.append(
                f"demo://calculations/{result['calculation_id']}#{result['calculation_hash']}"
            )
        output = {
            "schema_version": "agent-research-report/2.0.0",
            "run_id": checked["run_id"],
            "invocation_id": checked["invocation_id"],
            "status": sample["status"],
            "agent": self.agent_name,
            "scope": sample["scope"],
            "claims": sample["claims"],
            "assumptions": sample["assumptions"],
            "counter_evidence_refs": sample["counter_evidence_refs"],
            "uncertainties": sample["uncertainties"],
            "data_gaps": sample["data_gaps"],
            "invalidation_conditions": sample["invalidation_conditions"],
            "confidence": sample["confidence"],
            "confidence_rationale": sample["confidence_rationale"],
            "skill_execution": _skill_execution(
                topology,
                run_id=checked["run_id"],
                invocation_id=checked["invocation_id"],
                agent=self.agent_name,
            ),
            "artifact_refs": artifact_refs,
        }
        return _response(checked, output)


class IndependentSkepticDemoAdapter:
    """封装独立首轮反证示例，不接收 Analyst 输出。"""

    agent_name = "runtime_skeptic"

    def respond(
        self,
        request: Mapping[str, Any],
        *,
        evidence: EvidenceQueryPort,
        topology: Mapping[str, Any],
    ) -> dict[str, Any]:
        checked = validate_agent_request(request)
        if checked["recipient"] != self.agent_name:
            raise DemoValidationError("SKEPTIC_REQUEST_IDENTITY_INVALID")
        if checked["upstream_responses"]:
            raise DemoValidationError("SPECIALIST_CONTEXT_ISOLATION_VIOLATION")
        sample = deepcopy(checked["demo_payload"])
        evidence_ids = sample.pop("evidence_refs", None)
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise DemoValidationError("SKEPTIC_EVIDENCE_REFS_REQUIRED")
        evidence.query(evidence_ids=evidence_ids)
        output = {
            "schema_version": "counter-thesis-report/2.0.0",
            "run_id": checked["run_id"],
            "invocation_id": checked["invocation_id"],
            "status": sample["status"],
            "agent": self.agent_name,
            "mode": "INDEPENDENT_FIRST_PASS",
            "scope": sample["scope"],
            "challenges": sample["challenges"],
            "evidence_refs": evidence_ids,
            "counter_evidence_refs": sample["counter_evidence_refs"],
            "uncertainties": sample["uncertainties"],
            "data_gaps": sample["data_gaps"],
            "invalidation_conditions": sample["invalidation_conditions"],
            "confidence": sample["confidence"],
            "confidence_rationale": sample["confidence_rationale"],
            "skill_execution": _skill_execution(
                topology,
                run_id=checked["run_id"],
                invocation_id=checked["invocation_id"],
                agent=self.agent_name,
            ),
            "artifact_refs": [],
        }
        return _response(checked, output)


class CioDemoAdapter:
    """验证 CIO 输入输出接缝；不代表 Codex 当前主线程已担任 CIO。"""

    agent_name = "runtime_cio"

    def respond(
        self,
        request: Mapping[str, Any],
        *,
        evidence: EvidenceQueryPort,
        topology: Mapping[str, Any],
    ) -> dict[str, Any]:
        checked = validate_agent_request(request)
        if checked["recipient"] != self.agent_name:
            raise DemoValidationError("CIO_REQUEST_IDENTITY_INVALID")
        upstream = checked["upstream_responses"]
        identities = [item.get("agent_name") for item in upstream if isinstance(item, Mapping)]
        if set(identities) != {"runtime_company_analyst", "runtime_skeptic"} or len(identities) != 2:
            raise DemoValidationError("CIO_SPECIALIST_IDENTITIES_INVALID")
        if any(item.get("run_id") != checked["run_id"] for item in upstream):
            raise DemoValidationError("CROSS_RUN_OUTPUT")
        if len({item.get("producer_type") for item in upstream}) != 1:
            raise DemoValidationError("SPECIALIST_PRODUCER_MISMATCH")
        sample = deepcopy(checked["demo_payload"])
        evidence_ids = sample.get("evidence_refs")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise DemoValidationError("CIO_EVIDENCE_REFS_REQUIRED")
        evidence.query(evidence_ids=evidence_ids)
        output = {
            "schema_version": "cio-decision-draft/2.1.0",
            "run_id": checked["run_id"],
            "invocation_id": checked["invocation_id"],
            "status": sample["status"],
            "agent": self.agent_name,
            "consumed_reports": [
                {
                    "agent": item["agent_name"],
                    "output_hash": canonical_hash(item["output"]),
                }
                for item in sorted(upstream, key=lambda item: item["agent_name"])
            ],
            "action": sample["action"],
            "security_id": sample["security_id"],
            "current_weight": sample["current_weight"],
            "target_weight_range": sample["target_weight_range"],
            "maximum_notional": sample["maximum_notional"],
            "time_horizon": sample["time_horizon"],
            "thesis": sample["thesis"],
            "counter_thesis": sample["counter_thesis"],
            "consensus": sample["consensus"],
            "conflicts": sample["conflicts"],
            "unresolved_questions": sample["unresolved_questions"],
            "invalidation_conditions": sample["invalidation_conditions"],
            "confidence": sample["confidence"],
            "confidence_rationale": sample["confidence_rationale"],
            "evidence_refs": evidence_ids,
            "no_trade_reason": sample["no_trade_reason"],
            "no_trade_explanation": sample["no_trade_explanation"],
            "reevaluation_conditions": sample["reevaluation_conditions"],
            "skill_execution": _skill_execution(
                topology,
                run_id=checked["run_id"],
                invocation_id=checked["invocation_id"],
                agent=self.agent_name,
            ),
            "advisory_only": True,
        }
        return _response(checked, output)
