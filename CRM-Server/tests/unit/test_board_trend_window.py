from datetime import date, datetime, timezone

import pytest

from app.core.list_query.engine import parse_date_value
from app.core.list_query.types import FilterCondition
from app.services.board_trend_window import (
    BoardTrendWindow,
    extract_board_date_bounds,
    month_key,
    resolve_board_trend_window,
)


def test_supported_date_bounds_use_inclusive_day_bounds() -> None:
    filters = [
        FilterCondition(field="created_time", op="after", value="2026-07-18"),
        FilterCondition(field="created_time", op="before", value="2026-08-09"),
    ]
    assert extract_board_date_bounds(filters, "created_time") == (
        date(2026, 7, 18),
        date(2026, 8, 9),
    )


@pytest.mark.parametrize("op", ["is_empty", "is_not_empty"])
def test_empty_date_operators_do_not_create_trend_bounds(op: str) -> None:
    assert extract_board_date_bounds(
        [FilterCondition(field="created_time", op=op)],
        "created_time",
    ) == (None, None)


def test_window_examples_are_exact() -> None:
    today = date(2026, 10, 12)
    assert resolve_board_trend_window(today=today, start_bound=None, end_bound=None).months == (
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
    )
    assert resolve_board_trend_window(
        today=today,
        start_bound=date(2026, 7, 18),
        end_bound=None,
    ).months == ("2026-07", "2026-08", "2026-09")
    assert resolve_board_trend_window(
        today=today,
        start_bound=None,
        end_bound=date(2026, 8, 9),
    ).months == ("2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08")


def test_empty_or_invalid_value_rules() -> None:
    assert resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 10, 1),
        end_bound=None,
    ).months == ()
    assert resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 8, 1),
        end_bound=date(2026, 7, 31),
    ).months == ()


def test_unbounded_window_closes_at_latest_complete_month() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=None,
        end_bound=None,
    )

    assert window.event_start == date(2026, 4, 1)
    assert window.event_end == date(2026, 9, 30)
    assert window.empty is False


def test_start_only_window_keeps_start_and_caps_end() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 7, 18),
        end_bound=None,
    )

    assert window.event_start == date(2026, 7, 18)
    assert window.event_end == date(2026, 9, 30)


def test_end_only_window_uses_six_complete_months() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=None,
        end_bound=date(2026, 8, 9),
    )

    assert window.event_start == date(2026, 3, 1)
    assert window.event_end == date(2026, 8, 9)


def test_two_sided_window_keeps_explicit_end_past_latest_complete_month() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 5, 17),
        end_bound=date(2026, 7, 9),
    )

    assert window.months == ("2026-05", "2026-06", "2026-07")
    assert window.event_start == date(2026, 5, 17)
    assert window.event_end == date(2026, 7, 9)


def test_future_end_only_window_is_capped_at_latest_complete_month() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=None,
        end_bound=date(2026, 12, 10),
    )

    assert window.months == (
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
    )
    assert window.event_start == date(2026, 4, 1)
    assert window.event_end == date(2026, 9, 30)


def test_empty_windows_have_no_event_interval() -> None:
    future = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 10, 1),
        end_bound=None,
    )
    reversed_bounds = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 8, 1),
        end_bound=date(2026, 7, 31),
    )

    assert future == BoardTrendWindow(None, None, ())
    assert reversed_bounds == BoardTrendWindow(None, None, ())
    assert future.empty is True


def test_two_sided_window_allows_future_end_when_start_is_complete() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 8, 1),
        end_bound=date(2026, 12, 10),
    )

    assert window.event_start == date(2026, 8, 1)
    assert window.event_end == date(2026, 12, 10)
    assert window.months == ("2026-08", "2026-09", "2026-10", "2026-11", "2026-12")


def test_equal_bounds_are_a_single_closed_day() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 10, 12),
        start_bound=date(2026, 6, 15),
        end_bound=date(2026, 6, 15),
    )

    assert window.event_start == date(2026, 6, 15)
    assert window.event_end == date(2026, 6, 15)
    assert window.months == ("2026-06",)


def test_year_boundary_keeps_every_month_including_january() -> None:
    window = resolve_board_trend_window(
        today=date(2026, 2, 3),
        start_bound=None,
        end_bound=None,
    )

    assert window.months == (
        "2025-08",
        "2025-09",
        "2025-10",
        "2025-11",
        "2025-12",
        "2026-01",
    )
    assert window.event_start == date(2025, 8, 1)
    assert window.event_end == date(2026, 1, 31)


def test_invalid_window_invariants_are_rejected() -> None:
    with pytest.raises(ValueError, match="empty trend window"):
        BoardTrendWindow(date(2026, 4, 1), None, ())
    with pytest.raises(ValueError, match="closed event bounds"):
        BoardTrendWindow(None, date(2026, 9, 30), ("2026-09",))
    with pytest.raises(ValueError, match="reversed trend event interval"):
        BoardTrendWindow(date(2026, 9, 1), date(2026, 8, 1), ("2026-08",))


def test_extract_intersects_repeated_supported_bounds_for_one_field() -> None:
    filters = [
        FilterCondition(field="signed_date", op="after", value="2026-05-01"),
        FilterCondition(field="signed_date", op="eq", value="2026-05-17"),
        FilterCondition(field="signed_date", op="before", value="2026-07-09"),
        FilterCondition(field="signed_date", op="before", value="2026-08-01"),
        FilterCondition(field="other_date", op="after", value="2026-01-01"),
        FilterCondition(field="signed_date", op="is_empty"),
    ]

    assert extract_board_date_bounds(filters, "signed_date") == (
        date(2026, 5, 17),
        date(2026, 5, 17),
    )


def test_extract_between_uses_both_bounds_and_ignores_other_fields() -> None:
    filters = [
        FilterCondition(field="signed_date", op="between", value=["2026-07-20", "2026-05-01"]),
        FilterCondition(field="other_date", op="between", value=["2026-01-01", "2026-01-31"]),
        FilterCondition(field="signed_date", op="between", value=["bad", "2026-06-01"]),
    ]

    assert extract_board_date_bounds(filters, "signed_date") == (
        date(2026, 5, 1),
        date(2026, 7, 20),
    )


def test_extract_ignores_other_fields_invalid_values_and_missing_filters() -> None:
    filters = [
        FilterCondition(field="created_time", op="after", value="not-a-date"),
        FilterCondition(field="created_time", op="before", value=""),
        FilterCondition(field="paid_at", op="eq", value="2026-06-01"),
    ]

    assert extract_board_date_bounds(None, "created_time") == (None, None)
    assert extract_board_date_bounds(filters, "created_time") == (None, None)


def test_extract_uses_existing_parser_business_date() -> None:
    filters = [
        FilterCondition(field="occurred_at", op="after", value="2026-07-18T23:30:00+08:00"),
        FilterCondition(field="occurred_at", op="before", value=datetime(2026, 8, 9, 18, 0)),
    ]

    assert extract_board_date_bounds(filters, "occurred_at") == (
        date(2026, 7, 18),
        date(2026, 8, 9),
    )


def test_parse_date_value_preserves_existing_timezone_semantics() -> None:
    aware = datetime(2026, 7, 18, 23, 30, tzinfo=timezone.utc)

    assert parse_date_value(None) is None
    assert parse_date_value("") is None
    assert parse_date_value("not-a-date") is None
    assert parse_date_value(date(2026, 7, 18)) == datetime(2026, 7, 18)
    assert parse_date_value("2026-07-18") == datetime(2026, 7, 18)
    assert parse_date_value(aware) == aware
    assert parse_date_value("2026-07-18T23:30:00Z") == datetime(2026, 7, 18, 23, 30)
    assert parse_date_value("2026-07-18T23:30:00+08:00") == datetime(2026, 7, 18, 23, 30)


def test_month_key_uses_calendar_month() -> None:
    assert month_key(date(2026, 4, 30)) == "2026-04"
