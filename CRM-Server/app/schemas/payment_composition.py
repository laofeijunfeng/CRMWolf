"""Renewal and expansion amounts recorded on one payment."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, field_validator


def parse_payment_money(value: object) -> Decimal:
    """Accept a non-negative amount with at most two decimal places."""
    if isinstance(value, bool) or value is None:
        raise ValueError("金额需大于等于 0，且只精确到分")  # noqa: RUF001
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("金额需大于等于 0，且只精确到分") from exc  # noqa: RUF001
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2 or amount < 0:
        raise ValueError("金额需大于等于 0，且只精确到分")  # noqa: RUF001
    return amount.quantize(Decimal("0.01"))


def format_payment_yuan(amount: Decimal) -> str:
    return f"¥{amount:,.2f}"


def composition_sum_message(total: Decimal, actual: Decimal) -> str | None:
    """Return the approved shortfall sentence, or None when the cents match."""
    total_cents = total.quantize(Decimal("0.01"))
    actual_cents = actual.quantize(Decimal("0.01"))
    if total_cents == actual_cents:
        return None
    delta = (actual_cents - total_cents).copy_abs()
    direction = "少" if total_cents < actual_cents else "多"
    return f"两段合计 {format_payment_yuan(total_cents)}，比这笔回款{direction} {format_payment_yuan(delta)}。"  # noqa: RUF001


class PaymentCompositionSegment(BaseModel):
    headcount: int = Field(..., ge=0, description="人数大于等于 0 的整数")
    amount: Decimal = Field(..., ge=0, description="金额大于等于 0，精确到分")  # noqa: RUF001

    @field_validator("headcount", mode="before")
    @classmethod
    def headcount_is_whole_number(cls, value: object) -> object:
        if isinstance(value, bool | float):
            raise ValueError("人数需为大于等于 0 的整数")
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped.isdigit():
                raise ValueError("人数需为大于等于 0 的整数")
            return int(stripped)
        return value

    @field_validator("amount", mode="before")
    @classmethod
    def amount_is_cents(cls, value: object) -> Decimal:
        return parse_payment_money(value)


class PaymentComposition(BaseModel):
    renewal: PaymentCompositionSegment
    expansion: PaymentCompositionSegment

    def total_amount(self) -> Decimal:
        return (self.renewal.amount + self.expansion.amount).quantize(Decimal("0.01"))

    def matches(self, actual_amount: object) -> None:
        message = composition_sum_message(self.total_amount(), parse_payment_money(actual_amount))
        if message is not None:
            raise ValueError(message)

    def column_values(self) -> dict[str, int | Decimal]:
        return {
            "renewal_headcount": self.renewal.headcount,
            "renewal_amount": self.renewal.amount,
            "expansion_headcount": self.expansion.headcount,
            "expansion_amount": self.expansion.amount,
        }


EMPTY_COMPOSITION_COLUMNS: dict[str, None] = {
    "renewal_headcount": None,
    "renewal_amount": None,
    "expansion_headcount": None,
    "expansion_amount": None,
}


def composition_payload(record: object) -> dict[str, dict[str, int | float]] | None:
    """Return the public composition object, or None when this payment has none."""
    renewal_headcount = getattr(record, "renewal_headcount", None)
    renewal_amount = getattr(record, "renewal_amount", None)
    expansion_headcount = getattr(record, "expansion_headcount", None)
    expansion_amount = getattr(record, "expansion_amount", None)
    if (
        renewal_headcount is None
        or renewal_amount is None
        or expansion_headcount is None
        or expansion_amount is None
    ):
        return None
    return {
        "renewal": {
            "headcount": int(renewal_headcount),
            "amount": float(renewal_amount),
        },
        "expansion": {
            "headcount": int(expansion_headcount),
            "amount": float(expansion_amount),
        },
    }


def assert_record_composition_matches(record: object) -> None:
    renewal_headcount = getattr(record, "renewal_headcount", None)
    renewal_amount = getattr(record, "renewal_amount", None)
    expansion_headcount = getattr(record, "expansion_headcount", None)
    expansion_amount = getattr(record, "expansion_amount", None)
    values = (renewal_headcount, renewal_amount, expansion_headcount, expansion_amount)
    if all(value is None for value in values):
        return
    if (
        renewal_headcount is None
        or renewal_amount is None
        or expansion_headcount is None
        or expansion_amount is None
    ):
        raise ValueError("请填完续购和增购的人数和金额。")
    composition = PaymentComposition(
        renewal=PaymentCompositionSegment(headcount=int(renewal_headcount), amount=renewal_amount),
        expansion=PaymentCompositionSegment(headcount=int(expansion_headcount), amount=expansion_amount),
    )
    composition.matches(getattr(record, "actual_amount", None))
