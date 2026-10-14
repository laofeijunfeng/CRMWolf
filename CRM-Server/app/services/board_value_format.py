from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_QUANTUM = Decimal("0.01")
BOARD_PREVIEW_LIMIT = 5


def money_string(value: Decimal | int | str | None) -> str | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError("amount must be finite")
        return format(amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("invalid fixed-point amount") from error


def finite_percentage(
    numerator: int | Decimal,
    denominator: int | Decimal,
) -> float | None:
    try:
        top, bottom = Decimal(str(numerator)), Decimal(str(denominator))
        if not top.is_finite() or not bottom.is_finite():
            raise ValueError("percentage inputs must be finite")
        if bottom == 0:
            return None
        percentage = top * Decimal("100") / bottom
        if not percentage.is_finite() or not Decimal("0") <= percentage <= Decimal("100"):
            raise ValueError("percentage must be in 0-100")
        return float(percentage)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("invalid percentage") from error
