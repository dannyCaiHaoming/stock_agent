"""Council decision, deterministic risk, and advisory output contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar, Mapping

from .base import (
    ArtifactContract,
    ArtifactEnvelope,
    ContractValidationError,
    JsonContract,
    require_finite_number,
    require_fraction,
    require_identifier,
    require_lineage_member,
    require_non_empty_sequence,
    require_text,
    require_unique,
)


class DecisionAction(str, Enum):
    BUY = "BUY"
    ADD = "ADD"
    HOLD = "HOLD"
    TRIM = "TRIM"
    EXIT = "EXIT"
    NO_TRADE = "NO_TRADE"


class RiskStatus(str, Enum):
    APPROVED = "APPROVED"
    REVISE_REQUIRED = "REVISE_REQUIRED"
    REJECTED = "REJECTED"


class NoTradeReason(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    STALE_DATA = "STALE_DATA"
    MATERIAL_SOURCE_CONFLICT = "MATERIAL_SOURCE_CONFLICT"
    UNRESOLVED_THESIS_CONFLICT = "UNRESOLVED_THESIS_CONFLICT"
    LOW_CONVICTION = "LOW_CONVICTION"
    INPUT_INVALID = "INPUT_INVALID"
    MANDATE_VIOLATION = "MANDATE_VIOLATION"
    LIQUIDITY_LIMIT = "LIQUIDITY_LIMIT"
    RISK_VETO = "RISK_VETO"


@dataclass(frozen=True, slots=True)
class TargetWeightRange(JsonContract):
    schema_name: ClassVar[str] = "target-weight-range"

    minimum: int | float
    maximum: int | float

    def __post_init__(self) -> None:
        require_fraction(self.minimum, "target weight minimum")
        require_fraction(self.maximum, "target weight maximum")
        if self.minimum > self.maximum:
            raise ContractValidationError("target weight minimum must not exceed maximum")


def _validate_ids(values: tuple[str, ...], field_name: str, *, required: bool = False) -> None:
    if required:
        require_non_empty_sequence(values, field_name)
    for index, value in enumerate(values):
        require_identifier(value, f"{field_name}[{index}]")
    require_unique(values, field_name)


def _validate_texts(values: tuple[str, ...], field_name: str, *, required: bool = False) -> None:
    if required:
        require_non_empty_sequence(values, field_name)
    for index, value in enumerate(values):
        require_text(value, f"{field_name}[{index}]")


@dataclass(frozen=True, slots=True)
class CouncilDraftDecision(ArtifactContract):
    schema_name: ClassVar[str] = "council-draft-decision"

    envelope: ArtifactEnvelope
    action: DecisionAction
    security_id: str | None
    current_weight: int | float | None
    target_weight_range: TargetWeightRange | None
    maximum_notional: int | float | None
    time_horizon: str
    thesis_claim_ids: tuple[str, ...]
    counter_thesis_claim_ids: tuple[str, ...]
    evidence_fact_ids: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    unresolved_uncertainties: tuple[str, ...]
    confidence: int | float
    no_trade_reason: NoTradeReason | None = None
    no_trade_explanation: str | None = None
    reevaluation_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.action, DecisionAction):
            raise ContractValidationError("action must be a DecisionAction value")
        if self.no_trade_reason is not None and not isinstance(self.no_trade_reason, NoTradeReason):
            raise ContractValidationError("no_trade_reason must be a NoTradeReason value")
        if self.security_id is not None:
            require_identifier(self.security_id, "security_id")
        if self.current_weight is not None:
            require_fraction(self.current_weight, "current_weight")
        if self.maximum_notional is not None:
            require_finite_number(self.maximum_notional, "maximum_notional")
            if self.maximum_notional < 0:
                raise ContractValidationError("maximum_notional must not be negative")
        require_text(self.time_horizon, "time_horizon")
        _validate_ids(self.thesis_claim_ids, "thesis_claim_ids")
        _validate_ids(self.counter_thesis_claim_ids, "counter_thesis_claim_ids")
        _validate_ids(self.evidence_fact_ids, "evidence_fact_ids")
        _validate_texts(self.invalidation_conditions, "invalidation_conditions")
        _validate_texts(self.unresolved_uncertainties, "unresolved_uncertainties")
        _validate_texts(self.reevaluation_conditions, "reevaluation_conditions")
        require_fraction(self.confidence, "confidence")

        if self.action is DecisionAction.NO_TRADE:
            if self.no_trade_reason is None or not self.no_trade_explanation:
                raise ContractValidationError("NO_TRADE requires a reason code and explanation")
            require_text(self.no_trade_explanation, "no_trade_explanation")
            if self.target_weight_range is not None or self.maximum_notional is not None:
                raise ContractValidationError("NO_TRADE must not carry a proposed target or notional")
            require_non_empty_sequence(self.reevaluation_conditions, "reevaluation_conditions")
        else:
            if self.security_id is None or self.current_weight is None or self.target_weight_range is None:
                raise ContractValidationError(
                    "a proposed action requires security_id, current_weight, and target_weight_range"
                )
            if self.action in (DecisionAction.BUY, DecisionAction.ADD) and self.maximum_notional is None:
                raise ContractValidationError("BUY and ADD require maximum_notional")
            if self.no_trade_reason is not None or self.no_trade_explanation is not None:
                raise ContractValidationError("non-NO_TRADE actions must not carry NO_TRADE fields")
            _validate_ids(self.thesis_claim_ids, "thesis_claim_ids", required=True)
            _validate_ids(self.evidence_fact_ids, "evidence_fact_ids", required=True)
            _validate_texts(self.invalidation_conditions, "invalidation_conditions", required=True)


@dataclass(frozen=True, slots=True)
class RiskViolation(JsonContract):
    schema_name: ClassVar[str] = "risk-violation"

    policy_clause: str
    reason_code: str
    calculation: str
    observed_value: int | float | str
    limit_value: int | float | str

    def __post_init__(self) -> None:
        require_text(self.policy_clause, "policy_clause")
        require_identifier(self.reason_code, "risk reason_code")
        require_text(self.calculation, "risk calculation")


@dataclass(frozen=True, slots=True)
class FeasibleBound(JsonContract):
    schema_name: ClassVar[str] = "feasible-bound"

    field_name: str
    minimum: int | float | None = None
    maximum: int | float | None = None

    def __post_init__(self) -> None:
        require_text(self.field_name, "feasible bound field_name")
        if self.minimum is None and self.maximum is None:
            raise ContractValidationError("a feasible bound requires minimum or maximum")
        if self.minimum is not None:
            require_finite_number(self.minimum, "feasible bound minimum")
        if self.maximum is not None:
            require_finite_number(self.maximum, "feasible bound maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ContractValidationError("feasible bound minimum must not exceed maximum")


@dataclass(frozen=True, slots=True)
class RiskCheckReport(ArtifactContract):
    schema_name: ClassVar[str] = "risk-check-report"

    envelope: ArtifactEnvelope
    status: RiskStatus
    policy_version: str
    draft_artifact_id: str
    pre_trade_metrics: Mapping[str, int | float]
    post_trade_metrics: Mapping[str, int | float]
    violations: tuple[RiskViolation, ...] = ()
    feasible_bounds: tuple[FeasibleBound, ...] = ()
    veto_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, RiskStatus):
            raise ContractValidationError("status must be a RiskStatus value")
        require_text(self.policy_version, "policy_version")
        require_lineage_member(self.envelope, self.draft_artifact_id, "draft_artifact_id")
        for field_name, metrics in (
            ("pre_trade_metrics", self.pre_trade_metrics),
            ("post_trade_metrics", self.post_trade_metrics),
        ):
            for key, value in metrics.items():
                require_text(key, f"{field_name} key")
                require_finite_number(value, f"{field_name}.{key}")
        for index, code in enumerate(self.veto_codes):
            require_identifier(code, f"veto_codes[{index}]")
        require_unique(self.veto_codes, "veto_codes")
        if self.status is RiskStatus.APPROVED and (self.violations or self.veto_codes):
            raise ContractValidationError("APPROVED risk reports cannot contain violations or veto codes")
        if self.status is RiskStatus.REVISE_REQUIRED and not self.feasible_bounds:
            raise ContractValidationError("REVISE_REQUIRED risk reports require feasible bounds")
        if self.status is RiskStatus.REJECTED and (not self.violations or not self.veto_codes):
            raise ContractValidationError("REJECTED risk reports require violations and veto codes")


@dataclass(frozen=True, slots=True)
class AdvisoryPlanItem(JsonContract):
    schema_name: ClassVar[str] = "advisory-plan-item"

    action: DecisionAction
    security_id: str | None
    current_weight: int | float | None
    target_weight_range: TargetWeightRange | None
    maximum_notional: int | float | None
    time_horizon: str
    thesis_claim_ids: tuple[str, ...]
    counter_thesis_claim_ids: tuple[str, ...]
    evidence_fact_ids: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    unresolved_uncertainties: tuple[str, ...] = ()
    no_trade_reason: NoTradeReason | None = None
    no_trade_explanation: str | None = None
    reevaluation_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.action, DecisionAction):
            raise ContractValidationError("action must be a DecisionAction value")
        if self.no_trade_reason is not None and not isinstance(self.no_trade_reason, NoTradeReason):
            raise ContractValidationError("no_trade_reason must be a NoTradeReason value")
        if self.security_id is not None:
            require_identifier(self.security_id, "security_id")
        if self.current_weight is not None:
            require_fraction(self.current_weight, "current_weight")
        if self.maximum_notional is not None:
            require_finite_number(self.maximum_notional, "maximum_notional")
            if self.maximum_notional < 0:
                raise ContractValidationError("maximum_notional must not be negative")
        require_text(self.time_horizon, "time_horizon")
        _validate_ids(self.thesis_claim_ids, "thesis_claim_ids")
        _validate_ids(self.counter_thesis_claim_ids, "counter_thesis_claim_ids")
        _validate_ids(self.evidence_fact_ids, "evidence_fact_ids")
        _validate_texts(self.invalidation_conditions, "invalidation_conditions")
        _validate_texts(self.unresolved_uncertainties, "unresolved_uncertainties")
        _validate_texts(self.reevaluation_conditions, "reevaluation_conditions")
        if self.action is DecisionAction.NO_TRADE:
            if self.no_trade_reason is None or not self.no_trade_explanation:
                raise ContractValidationError("NO_TRADE requires reason and explanation")
            if self.target_weight_range is not None or self.maximum_notional is not None:
                raise ContractValidationError("NO_TRADE must not contain target execution parameters")
            require_non_empty_sequence(self.reevaluation_conditions, "reevaluation_conditions")
        else:
            if self.security_id is None or self.current_weight is None or self.target_weight_range is None:
                raise ContractValidationError("an advisory action requires security and weight context")
            if self.action in (DecisionAction.BUY, DecisionAction.ADD) and self.maximum_notional is None:
                raise ContractValidationError("BUY and ADD require maximum_notional")
            _validate_ids(self.thesis_claim_ids, "thesis_claim_ids", required=True)
            _validate_ids(self.evidence_fact_ids, "evidence_fact_ids", required=True)
            _validate_texts(self.invalidation_conditions, "invalidation_conditions", required=True)
            if self.no_trade_reason is not None or self.no_trade_explanation is not None:
                raise ContractValidationError("non-NO_TRADE actions must not carry NO_TRADE fields")


@dataclass(frozen=True, slots=True)
class FinalDecisionPlan(ArtifactContract):
    schema_name: ClassVar[str] = "final-decision-plan"

    envelope: ArtifactEnvelope
    draft_artifact_id: str
    risk_report_artifact_id: str
    risk_status: RiskStatus
    items: tuple[AdvisoryPlanItem, ...]
    advisory_only: bool = field(default=True)

    def __post_init__(self) -> None:
        if not isinstance(self.risk_status, RiskStatus):
            raise ContractValidationError("risk_status must be a RiskStatus value")
        require_lineage_member(self.envelope, self.draft_artifact_id, "draft_artifact_id")
        require_lineage_member(self.envelope, self.risk_report_artifact_id, "risk_report_artifact_id")
        require_non_empty_sequence(self.items, "final decision items")
        if self.advisory_only is not True:
            raise ContractValidationError("FinalDecisionPlan must set advisory_only to true")
        if self.risk_status is not RiskStatus.APPROVED:
            if any(item.action is not DecisionAction.NO_TRADE for item in self.items):
                raise ContractValidationError(
                    "a non-approved risk result cannot produce an actionable advisory item"
                )
