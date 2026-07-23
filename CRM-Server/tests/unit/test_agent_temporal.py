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
