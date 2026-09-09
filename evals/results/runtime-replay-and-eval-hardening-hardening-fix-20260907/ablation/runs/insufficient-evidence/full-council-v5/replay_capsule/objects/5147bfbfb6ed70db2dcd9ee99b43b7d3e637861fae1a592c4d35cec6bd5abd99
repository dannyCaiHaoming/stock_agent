"""Portfolio input, normalized snapshot, mandate, and security contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from .base import (
    ArtifactContract,
    ArtifactEnvelope,
    ContractValidationError,
    JsonContract,
    require_finite_number,
    require_fraction,
    require_identifier,
    require_iso_datetime,
    require_lineage_member,
    require_non_empty_sequence,
    require_text,
    require_unique,
)


class IdentifierResolution(str, Enum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class SecurityIdentifier(JsonContract):
    schema_name: ClassVar[str] = "security-identifier"

    scheme: str
    value: str
    market: str
    resolution: IdentifierResolution
    canonical_id: str | None = None
    candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.resolution, IdentifierResolution):
            raise ContractValidationError("resolution must be an IdentifierResolution value")
        require_text(self.scheme, "security identifier scheme")
        require_text(self.value, "security identifier value")
        require_text(self.market, "security identifier market")
        if self.canonical_id is not None:
            require_identifier(self.canonical_id, "canonical_id")
        for index, candidate in enumerate(self.candidates):
            require_identifier(candidate, f"candidates[{index}]")
        require_unique(self.candidates, "security identifier candidates")

        if self.resolution is IdentifierResolution.RESOLVED:
            if self.canonical_id is None or self.candidates:
                raise ContractValidationError(
                    "a resolved security identifier requires canonical_id and no candidates"
                )
        elif self.resolution is IdentifierResolution.UNKNOWN:
            if self.canonical_id is not None or self.candidates:
                raise ContractValidationError(
                    "an unknown security identifier cannot contain a canonical_id or candidates"
                )
        elif self.resolution is IdentifierResolution.AMBIGUOUS:
            if self.canonical_id is not None or len(self.candidates) < 2:
                raise ContractValidationError(
                    "an ambiguous security identifier requires at least two candidates and no canonical_id"
                )


@dataclass(frozen=True, slots=True)
class PortfolioPositionInput(JsonContract):
    schema_name: ClassVar[str] = "portfolio-position-input"

    security: SecurityIdentifier
    quantity: int | float
    cost_basis: int | float | None = None

    def __post_init__(self) -> None:
        require_finite_number(self.quantity, "position quantity")
        if self.quantity <= 0:
            raise ContractValidationError("position quantity must be positive for the long-only MVP")
        if self.cost_basis is not None:
            require_finite_number(self.cost_basis, "cost_basis")
            if self.cost_basis < 0:
                raise ContractValidationError("cost_basis must not be negative")


@dataclass(frozen=True, slots=True)
class Mandate(ArtifactContract):
    schema_name: ClassVar[str] = "mandate"

    envelope: ArtifactEnvelope
    mandate_id: str
    mandate_version: str
    base_currency: str
    allowed_markets: tuple[str, ...]
    benchmark_id: str
    long_only: bool = True
    leverage_allowed: bool = False
    derivatives_allowed: bool = False
    shorting_allowed: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.mandate_id, "mandate_id")
        require_text(self.mandate_version, "mandate_version")
        require_text(self.base_currency, "base_currency")
        require_non_empty_sequence(self.allowed_markets, "allowed_markets")
        for index, market in enumerate(self.allowed_markets):
            require_text(market, f"allowed_markets[{index}]")
        require_unique(self.allowed_markets, "allowed_markets")
        require_identifier(self.benchmark_id, "benchmark_id")
        if not self.long_only or self.leverage_allowed or self.derivatives_allowed or self.shorting_allowed:
            raise ContractValidationError(
                "the initial product mandate must be long-only, unlevered, without derivatives or shorting"
            )


@dataclass(frozen=True, slots=True)
class PortfolioInput(ArtifactContract):
    schema_name: ClassVar[str] = "portfolio-input"

    envelope: ArtifactEnvelope
    positions: tuple[PortfolioPositionInput, ...]
    cash: int | float
    base_currency: str
    benchmark_id: str
    mandate_artifact_id: str

    def __post_init__(self) -> None:
        require_finite_number(self.cash, "cash")
        if self.cash < 0:
            raise ContractValidationError("cash must not be negative for the unlevered MVP")
        require_text(self.base_currency, "base_currency")
        require_identifier(self.benchmark_id, "benchmark_id")
        require_lineage_member(self.envelope, self.mandate_artifact_id, "mandate_artifact_id")

        canonical_ids: list[str] = []
        for position in self.positions:
            if position.security.resolution is not IdentifierResolution.RESOLVED:
                raise ContractValidationError(
                    f"security {position.security.value} is {position.security.resolution.value}; input must not guess"
                )
            assert position.security.canonical_id is not None
            canonical_ids.append(position.security.canonical_id)
        require_unique(canonical_ids, "portfolio canonical security IDs")


@dataclass(frozen=True, slots=True)
class SnapshotPosition(JsonContract):
    schema_name: ClassVar[str] = "snapshot-position"

    security_id: str
    quantity: int | float
    price: int | float
    market_value: int | float
    weight: int | float
    price_as_of: str

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        for field_name, value in (
            ("quantity", self.quantity),
            ("price", self.price),
            ("market_value", self.market_value),
        ):
            require_finite_number(value, field_name)
            if value < 0:
                raise ContractValidationError(f"{field_name} must not be negative")
        require_fraction(self.weight, "weight")
        require_iso_datetime(self.price_as_of, "price_as_of")


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot(ArtifactContract):
    schema_name: ClassVar[str] = "portfolio-snapshot"

    envelope: ArtifactEnvelope
    source_portfolio_artifact_id: str
    mandate_artifact_id: str
    as_of: str
    positions: tuple[SnapshotPosition, ...]
    cash: int | float
    total_value: int | float
    base_currency: str
    benchmark_id: str

    def __post_init__(self) -> None:
        require_lineage_member(
            self.envelope, self.source_portfolio_artifact_id, "source_portfolio_artifact_id"
        )
        require_lineage_member(self.envelope, self.mandate_artifact_id, "mandate_artifact_id")
        require_iso_datetime(self.as_of, "portfolio snapshot as_of")
        require_finite_number(self.cash, "cash")
        require_finite_number(self.total_value, "total_value")
        if self.cash < 0 or self.total_value < 0:
            raise ContractValidationError("cash and total_value must not be negative")
        require_text(self.base_currency, "base_currency")
        require_identifier(self.benchmark_id, "benchmark_id")
        require_unique([position.security_id for position in self.positions], "snapshot security IDs")
