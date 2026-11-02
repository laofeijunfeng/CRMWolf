"""Payment composition is optional, complete, and tied to the payment amount."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.payment import PaymentRecordCreate, PaymentRecordUpdate
from app.schemas.payment_composition import (
    composition_payload,
    composition_sum_message,
    format_payment_yuan,
)
from app.services.approval_adapter import _payment_composition_card_fields


def _create(**overrides):
    payload = {
        "actual_amount": 150000,
        "payment_date": "2026-11-02",
        "commission_member_id": "7",
    }
    payload.update(overrides)
    return PaymentRecordCreate(**payload)


def test_missing_composition_stays_one_payment():
    record = _create()
    assert record.composition is None


def test_composition_must_equal_payment_amount():
    with pytest.raises(ValidationError) as exc:
        _create(composition={
            "renewal": {"headcount": 100, "amount": "100000.00"},
            "expansion": {"headcount": 50, "amount": "40000.00"},
        })
    assert "比这笔回款少 ¥10,000.00" in str(exc.value)


def test_composition_accepts_zero_segment_when_sum_matches():
    record = _create(composition={
        "renewal": {"headcount": 100, "amount": "150000.00"},
        "expansion": {"headcount": 0, "amount": "0.00"},
    })
    assert record.composition is not None
    assert record.composition.expansion.headcount == 0
    assert record.composition.expansion.amount == Decimal("0.00")


def test_partial_composition_is_rejected():
    with pytest.raises(ValidationError):
        _create(composition={"renewal": {"headcount": 100, "amount": "100000.00"}})


def test_fractional_headcount_is_rejected():
    with pytest.raises(ValidationError):
        _create(composition={
            "renewal": {"headcount": 1.5, "amount": "100000.00"},
            "expansion": {"headcount": 50, "amount": "50000.00"},
        })


def test_amount_with_more_than_two_decimals_is_rejected():
    with pytest.raises(ValidationError):
        _create(composition={
            "renewal": {"headcount": 100, "amount": "100000.005"},
            "expansion": {"headcount": 50, "amount": "49999.995"},
        })


def test_update_checks_composition_against_the_submitted_amount():
    with pytest.raises(ValidationError) as exc:
        PaymentRecordUpdate(
            actual_amount=160000,
            composition={
                "renewal": {"headcount": 100, "amount": "100000.00"},
                "expansion": {"headcount": 50, "amount": "50000.00"},
            },
        )
    assert "少 ¥10,000.00" in str(exc.value)


def test_update_can_clear_composition():
    record = PaymentRecordUpdate(composition=None)
    assert record.composition is None
    assert "composition" in record.model_fields_set


def test_empty_record_has_no_public_composition():
    class Record:
        renewal_headcount = None
        renewal_amount = None
        expansion_headcount = None
        expansion_amount = None

    assert composition_payload(Record()) is None
    assert _payment_composition_card_fields(Record()) is None


def test_complete_record_exposes_both_segments():
    class Record:
        renewal_headcount = 100
        renewal_amount = Decimal("100000.00")
        expansion_headcount = 50
        expansion_amount = Decimal("50000.00")

    assert composition_payload(Record()) == {
        "renewal": {"headcount": 100, "amount": 100000.0},
        "expansion": {"headcount": 50, "amount": 50000.0},
    }
    assert _payment_composition_card_fields(Record()) == {
        "续购人数": "100人",
        "续购金额": "¥100,000.00",
        "增购人数": "50人",
        "增购金额": "¥50,000.00",
    }


def test_sum_message_uses_the_approved_sentence():
    message = composition_sum_message(Decimal("100000.00"), Decimal("150000.00"))
    expected = (
        f"两段合计 {format_payment_yuan(Decimal('100000.00'))}"
        f"，比这笔回款少 {format_payment_yuan(Decimal('50000.00'))}。"  # noqa: RUF001
    )
    assert message == expected
