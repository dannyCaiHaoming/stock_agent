"""无业务判断的金额数量级换算。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


MONETARY_SCALE_FACTORS = {
    "one": Decimal("1"),
    "thousand": Decimal("1000"),
    "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
    "万": Decimal("10000"),
    "亿": Decimal("100000000"),
}


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid decimal input: {name}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite decimal input: {name}")
    return result


def scale_factor(scale: str) -> Decimal:
    if scale not in MONETARY_SCALE_FACTORS:
        raise ValueError(f"unsupported monetary scale: {scale}")
    return MONETARY_SCALE_FACTORS[scale]


def convert_monetary_value(
    *, value: object, source_scale: str, target_scale: str
) -> str:
    amount = _decimal(value, "value")
    converted = amount * scale_factor(source_scale) / scale_factor(target_scale)
    return format(converted.normalize(), "f")


def require_monetary_equivalence(
    *, source_value: object, source_scale: str,
    reported_value: object, reported_scale: str,
) -> None:
    source = _decimal(source_value, "source_value") * scale_factor(source_scale)
    reported = _decimal(reported_value, "reported_value") * scale_factor(reported_scale)
    if source != reported:
        raise ValueError("reported monetary amount does not match source magnitude")
