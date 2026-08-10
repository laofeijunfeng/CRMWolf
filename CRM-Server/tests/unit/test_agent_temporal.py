"""CRM AI Agent temporal resolver tests."""
from datetime import datetime

from app.services.agent.schemas import AgentTemporalExpression
from app.services.agent.temporal import AgentTemporalResolver


def test_agent_temporal_resolver_resolves_next_weekday_from_system_date():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="下周三",
        kind="RELATIVE_WEEKDAY",
        direction="next",
        weekday=3,
        confidence=0.95,
    )

    result = resolver.resolve_follow_up_time(
        expression,
        base_datetime=datetime(2026, 7, 23, 10, 0, 0),
    )

    assert result == "2026-07-29T09:00:00"


def test_agent_temporal_resolver_rejects_low_confidence_time():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="过几天",
        kind="RELATIVE_DAY",
        direction="future",
        amount=3,
        confidence=0.4,
    )

    assert resolver.resolve_follow_up_time(expression, base_datetime=datetime(2026, 7, 23, 10, 0, 0)) is None


def test_agent_temporal_resolver_resolves_relative_week():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="2 周后",
        kind="RELATIVE_WEEK",
        direction="future",
        amount=2,
        unit="week",
        confidence=0.95,
    )

    result = resolver.resolve_follow_up_time(
        expression,
        base_datetime=datetime(2026, 8, 10, 0, 45, 25),
    )

    assert result == "2026-08-24T09:00:00"


def test_agent_temporal_resolver_resolves_relative_month():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="2 个月后",
        kind="RELATIVE_MONTH",
        direction="future",
        amount=2,
        unit="month",
        confidence=0.95,
    )

    result = resolver.resolve_follow_up_time(
        expression,
        base_datetime=datetime(2026, 8, 10, 0, 45, 25),
    )

    assert result == "2026-10-10T09:00:00"


def test_agent_temporal_resolver_clamps_relative_month_to_last_valid_day():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="1 个月后",
        kind="RELATIVE_MONTH",
        direction="future",
        amount=1,
        unit="month",
        confidence=0.95,
    )

    result = resolver.resolve_date(
        expression,
        base_datetime=datetime(2026, 1, 31, 10, 0, 0),
    )

    assert result == "2026-02-28"


def test_agent_temporal_resolver_resolves_relative_year():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="1 年后",
        kind="RELATIVE_YEAR",
        direction="future",
        amount=1,
        unit="year",
        confidence=0.95,
    )

    result = resolver.resolve_follow_up_time(
        expression,
        base_datetime=datetime(2026, 8, 10, 0, 45, 25),
    )

    assert result == "2027-08-10T09:00:00"


def test_agent_temporal_resolver_rejects_relative_day_with_month_unit():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="2 个月后",
        kind="RELATIVE_DAY",
        direction="future",
        amount=2,
        unit="month",
        confidence=0.95,
    )

    result = resolver.resolve_follow_up_time(
        expression,
        base_datetime=datetime(2026, 8, 10, 0, 45, 25),
    )

    assert result is None


def test_agent_temporal_resolver_resolves_month_end_without_year():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="9 月底",
        kind="MONTH_END",
        month=9,
        confidence=0.95,
    )

    result = resolver.resolve_date(expression, base_datetime=datetime(2026, 7, 24, 10, 0, 0))

    assert result == "2026-09-30"


def test_agent_temporal_resolver_resolves_month_day_without_year():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="9 月 30 号",
        kind="MONTH_DAY",
        month=9,
        day=30,
        confidence=0.95,
    )

    result = resolver.resolve_date(expression, base_datetime=datetime(2026, 7, 24, 10, 0, 0))

    assert result == "2026-09-30"


def test_agent_temporal_resolver_rolls_month_day_to_next_year_when_needed():
    resolver = AgentTemporalResolver()
    expression = AgentTemporalExpression(
        raw_text="1 月 10 号",
        kind="MONTH_DAY",
        month=1,
        day=10,
        confidence=0.95,
    )

    result = resolver.resolve_date(expression, base_datetime=datetime(2026, 7, 24, 10, 0, 0))

    assert result == "2027-01-10"
