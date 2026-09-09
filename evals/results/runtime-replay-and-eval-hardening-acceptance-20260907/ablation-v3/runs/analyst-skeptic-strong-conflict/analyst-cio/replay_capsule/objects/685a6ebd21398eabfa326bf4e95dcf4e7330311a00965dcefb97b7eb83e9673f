"""Long-only portfolio normalization and accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from product.mcp.provenance import parse_timestamp


ZERO = Decimal("0")
ONE = Decimal("1")


def decimal_value(value: object, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PortfolioValidationError("INVALID_NUMBER", f"invalid {field_name}") from exc
    if not result.is_finite():
        raise PortfolioValidationError("INVALID_NUMBER", f"non-finite {field_name}")
    return result


class PortfolioValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SecurityRecord:
    security_id: str
    identifiers: tuple[str, ...]
    industry: str
    market: str = "FIXTURE"
    security_type: str = "COMMON_STOCK"


@dataclass(frozen=True, slots=True)
class PriceObservation:
    security_id: str
    price: Decimal
    as_of: str
    source_id: str
    currency: str
    average_daily_value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NormalizedPosition:
    security_id: str
    quantity: Decimal
    price: Decimal
    price_as_of: str
    price_source_id: str
    market_value: Decimal
    weight: Decimal
    industry: str
    average_daily_value: Decimal | None


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    snapshot_id: str
    as_of: str
    base_currency: str
    benchmark: str | None
    mandate_version: str
    cash: Decimal
    total_value: Decimal
    positions: tuple[NormalizedPosition, ...]

    @property
    def cash_weight(self) -> Decimal:
        return self.cash / self.total_value

    def position(self, security_id: str) -> NormalizedPosition | None:
        return next(
            (position for position in self.positions if position.security_id == security_id),
            None,
        )


def build_security_index(
    securities: Sequence[SecurityRecord],
) -> dict[str, tuple[SecurityRecord, ...]]:
    index: dict[str, list[SecurityRecord]] = {}
    for security in securities:
        aliases = {security.security_id, *security.identifiers}
        for alias in aliases:
            index.setdefault(alias.casefold(), []).append(security)
    return {alias: tuple(matches) for alias, matches in index.items()}


def resolve_security(
    identifier: str, index: Mapping[str, tuple[SecurityRecord, ...]]
) -> SecurityRecord:
    matches = index.get(identifier.casefold(), ())
    if not matches:
        raise PortfolioValidationError(
            "UNKNOWN_SECURITY", f"security identifier is not mapped: {identifier}"
        )
    unique = {match.security_id: match for match in matches}
    if len(unique) != 1:
        raise PortfolioValidationError(
            "AMBIGUOUS_SECURITY", f"security identifier is ambiguous: {identifier}"
        )
    return next(iter(unique.values()))


def normalize_portfolio(
    portfolio_input: Mapping[str, object],
    *,
    securities: Sequence[SecurityRecord],
    prices: Mapping[str, PriceObservation],
    cutoff: str,
    max_price_age: timedelta,
    conservation_tolerance: Decimal = Decimal("0.01"),
) -> PortfolioSnapshot:
    """Resolve identifiers, reject ambiguity, and prove amount conservation."""

    if "cash" not in portfolio_input or portfolio_input["cash"] is None:
        raise PortfolioValidationError("MISSING_CASH", "cash is required")
    cash = decimal_value(portfolio_input["cash"], "cash")
    if cash < ZERO:
        raise PortfolioValidationError("NEGATIVE_CASH", "cash cannot be negative")

    cutoff_time = parse_timestamp(cutoff)
    security_index = build_security_index(securities)
    raw_positions = portfolio_input.get("positions")
    if not isinstance(raw_positions, Sequence) or isinstance(raw_positions, (str, bytes)):
        raise PortfolioValidationError("INVALID_POSITIONS", "positions must be a sequence")

    resolved: list[tuple[SecurityRecord, Decimal, PriceObservation, Decimal]] = []
    seen: set[str] = set()
    for raw_position in raw_positions:
        if not isinstance(raw_position, Mapping):
            raise PortfolioValidationError("INVALID_POSITION", "position must be an object")
        identifier = str(raw_position.get("identifier") or "")
        security = resolve_security(identifier, security_index)
        if security.security_id in seen:
            raise PortfolioValidationError(
                "DUPLICATE_POSITION",
                f"duplicate resolved holding: {security.security_id}",
            )
        seen.add(security.security_id)
        quantity = decimal_value(raw_position.get("quantity"), "quantity")
        if quantity <= ZERO:
            raise PortfolioValidationError(
                "LONG_ONLY_VIOLATION", "position quantity must be positive"
            )
        price = prices.get(security.security_id)
        if price is None:
            raise PortfolioValidationError(
                "MISSING_PRICE", f"price is missing: {security.security_id}"
            )
        if price.price <= ZERO:
            raise PortfolioValidationError(
                "INVALID_PRICE", f"price must be positive: {security.security_id}"
            )
        price_time = parse_timestamp(price.as_of)
        if price_time > cutoff_time:
            raise PortfolioValidationError(
                "FUTURE_PRICE", f"price is later than cutoff: {security.security_id}"
            )
        if cutoff_time - price_time > max_price_age:
            raise PortfolioValidationError(
                "STALE_PRICE", f"price is stale: {security.security_id}"
            )
        market_value = quantity * price.price
        resolved.append((security, quantity, price, market_value))

    total_value = cash + sum((item[3] for item in resolved), ZERO)
    if total_value <= ZERO:
        raise PortfolioValidationError(
            "NON_POSITIVE_PORTFOLIO", "portfolio total must be positive"
        )
    declared_total = portfolio_input.get("declared_total_value")
    if declared_total is not None:
        declared = decimal_value(declared_total, "declared_total_value")
        if abs(declared - total_value) > conservation_tolerance:
            raise PortfolioValidationError(
                "AMOUNT_CONSERVATION_FAILED",
                f"declared total {declared} does not equal accounted total {total_value}",
            )

    positions = tuple(
        NormalizedPosition(
            security_id=security.security_id,
            quantity=quantity,
            price=price.price,
            price_as_of=price.as_of,
            price_source_id=price.source_id,
            market_value=market_value,
            weight=market_value / total_value,
            industry=security.industry,
            average_daily_value=price.average_daily_value,
        )
        for security, quantity, price, market_value in sorted(
            resolved, key=lambda item: item[0].security_id
        )
    )
    accounted = cash + sum((position.market_value for position in positions), ZERO)
    if abs(accounted - total_value) > conservation_tolerance:
        raise PortfolioValidationError(
            "AMOUNT_CONSERVATION_FAILED", "normalized amounts do not conserve value"
        )

    snapshot_id = str(portfolio_input.get("snapshot_id") or "portfolio-snapshot")
    return PortfolioSnapshot(
        snapshot_id=snapshot_id,
        as_of=cutoff,
        base_currency=str(portfolio_input.get("base_currency") or "USD"),
        benchmark=(
            str(portfolio_input["benchmark"])
            if portfolio_input.get("benchmark") is not None
            else None
        ),
        mandate_version=str(portfolio_input.get("mandate_version") or "mandate/1.0.0"),
        cash=cash,
        total_value=total_value,
        positions=positions,
    )
