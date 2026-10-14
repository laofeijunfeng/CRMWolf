from decimal import Decimal

import pytest

from app.services.board_value_format import BOARD_PREVIEW_LIMIT, finite_percentage, money_string


def test_empty_or_invalid_value_rules() -> None:
    assert money_string(Decimal("0")) == "0.00"
    assert money_string(Decimal("-1.005")) == "-1.01"
    assert finite_percentage(1, 0) is None
    with pytest.raises(ValueError):
        finite_percentage(2, 1)


def test_money_string_quantizes_only_the_transport_value() -> None:
    assert money_string(None) is None
    assert money_string(0) == "0.00"
    assert money_string("1.2") == "1.20"
    assert money_string(Decimal("1.225")) == "1.23"
    assert money_string(Decimal("-0.004")) == "-0.00"
    assert money_string(Decimal("-1.235")) == "-1.24"
    assert BOARD_PREVIEW_LIMIT == 5


@pytest.mark.parametrize("value", ["", "abc", "NaN", "Infinity", "-Infinity", object()])
def test_money_string_rejects_invalid_or_nonfinite_values(value: object) -> None:
    with pytest.raises(ValueError, match="invalid fixed-point amount"):
        money_string(value)  # type: ignore[arg-type]


def test_finite_percentage_uses_decimal_ratio_without_clamping() -> None:
    assert finite_percentage(0, 4) == 0.0
    assert finite_percentage(1, 4) == 25.0
    assert finite_percentage(Decimal("1"), Decimal("3")) == pytest.approx(100 / 3)
    assert finite_percentage(Decimal("100"), Decimal("100")) == 100.0
    assert finite_percentage(Decimal("0"), Decimal("0")) is None


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [
        (-1, 2),
        (3, 2),
        (Decimal("NaN"), 1),
        (1, Decimal("Infinity")),
        ("bad", 1),
    ],
)
def test_finite_percentage_rejects_out_of_range_or_nonfinite_inputs(
    numerator: object,
    denominator: object,
) -> None:
    with pytest.raises(ValueError, match="invalid percentage"):
        finite_percentage(numerator, denominator)  # type: ignore[arg-type]
