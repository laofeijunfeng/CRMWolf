import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.board_primitives import (
    AmountString,
    BoardAmountMetric,
    BoardCountMetric,
    BoardMetric,
    BoardOwner,
    BoardPercentageMetric,
    BoardTone,
    Count,
    DateString,
    EntityId,
    MonthString,
    Percentage,
    StrictBoardModel,
    validate_preview_counts,
)


class _Probe(StrictBoardModel):
    count: Count
    entity_id: EntityId
    amount: AmountString | None = None
    percentage: Percentage | None = None
    day: DateString | None = None
    month: MonthString | None = None
    tone: BoardTone | None = None
    enabled: bool | None = None


def test_strict_primitives_reject_coercion_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": True, "entity_id": 1})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 1.5, "entity_id": 1})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": "1", "entity_id": 1})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": -1, "entity_id": 1})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 0})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "extra": True})


def test_amounts_dates_and_percentages_keep_transport_constraints() -> None:
    probe = _Probe.model_validate(
        {
            "count": 0,
            "entity_id": 7,
            "amount": "-1.01",
            "percentage": 0.0,
            "day": "2026-09-30",
            "month": "2026-09",
            "tone": "warning",
            "enabled": False,
        }
    )

    assert probe.amount == "-1.01"
    assert probe.percentage == 0.0
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "amount": "1"})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "amount": "1.2"})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "amount": 1.0})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "percentage": float("nan")})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "percentage": 100.1})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "day": "2026-02-31"})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "month": "2026-13"})
    with pytest.raises(ValidationError):
        _Probe.model_validate({"count": 0, "entity_id": 1, "tone": "critical"})


def test_metric_union_requires_matching_secondary_fields() -> None:
    metric = TypeAdapter(BoardMetric).validate_python(
        {
            "key": "amount",
            "label": "金额",
            "value_type": "amount",
            "value": "12.50",
            "secondary_label": "同比",
            "secondary_value": "-1.00",
        }
    )

    assert isinstance(metric, BoardAmountMetric)
    assert metric.secondary_value == "-1.00"
    with pytest.raises(ValidationError, match="secondary value and label"):
        BoardCountMetric.model_validate(
            {"key": "count", "label": "数量", "value_type": "count", "value": 1, "secondary_value": 2}
        )
    with pytest.raises(ValidationError, match="secondary value and label"):
        BoardPercentageMetric.model_validate(
            {
                "key": "ratio",
                "label": "占比",
                "value_type": "percentage",
                "value": 10.0,
                "secondary_label": "上月",
            }
        )
    with pytest.raises(ValidationError):
        BoardCountMetric.model_validate(
            {"key": "count", "label": "数量", "value_type": "count", "value": True}
        )


def test_owner_and_null_metrics_are_strict() -> None:
    owner = BoardOwner.model_validate({"id": "u-1", "name": "Ada"})

    assert owner.avatar_url is None
    with pytest.raises(ValidationError):
        BoardOwner.model_validate({"id": 1, "name": "Ada"})
    count = BoardCountMetric.model_validate(
        {"key": "count", "label": "数量", "value_type": "count", "value": None}
    )
    assert count.secondary_value is None
    assert count.secondary_label is None


@pytest.mark.parametrize(
    ("count", "shown", "has_more", "remaining"),
    [
        (0, 0, False, 0),
        (5, 5, False, 0),
        (6, 5, True, 1),
    ],
)
def test_preview_counts_accept_consistent_windows(
    count: int,
    shown: int,
    has_more: bool,
    remaining: int,
) -> None:
    validate_preview_counts(count=count, shown=shown, has_more=has_more, remaining=remaining)


@pytest.mark.parametrize(
    ("count", "shown", "has_more", "remaining"),
    [
        (-1, 0, False, 0),
        (6, 6, True, 0),
        (6, 5, False, 1),
        (6, 5, True, 2),
    ],
)
def test_preview_counts_reject_inconsistent_windows(
    count: int,
    shown: int,
    has_more: bool,
    remaining: int,
) -> None:
    with pytest.raises(ValueError, match="inconsistent board preview counts"):
        validate_preview_counts(count=count, shown=shown, has_more=has_more, remaining=remaining)
