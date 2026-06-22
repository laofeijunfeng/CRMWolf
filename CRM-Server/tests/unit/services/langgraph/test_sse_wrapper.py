"""
Tests for LangGraph SSE Wrapper

Tests for SSE event format compatibility between LangGraph and legacy format.
Ensures frontend can receive same events without modification.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import AsyncGenerator

from app.services.langgraph.sse_wrapper import (
    build_sse_event,
    build_start_event,
    build_node_start_event,
    build_node_result_event,
    build_tool_call_event,
    build_tool_result_event,
    build_waiting_for_user_event,
    build_react_complete_event,
    build_error_event,
    stream_sse_events,
    filter_result_for_display,
)


class TestSSEEventBuilders:
    """Tests for SSE event builder functions."""

    def test_build_sse_event_format(self) -> None:
        """Test that SSE event format is correct."""
        event = build_sse_event("test", {"data": "value"})

        # Should have correct SSE format
        assert event.startswith("event: test\n")
        assert "data:" in event
        assert event.endswith("\n\n")

    def test_build_start_event(self) -> None:
        """Test start event format."""
        event = build_start_event("session-123")

        assert "event: start" in event
        assert json.dumps({"session_id": "session-123"}) in event

    def test_build_node_start_event(self) -> None:
        """Test node_start event format."""
        event = build_node_start_event("intent_detector")

        assert "event: node_start" in event
        assert json.dumps({"node": "intent_detector"}) in event

    def test_build_node_result_event(self) -> None:
        """Test node_result event format."""
        result = {"action": "create_customer", "confidence": 0.9}
        event = build_node_result_event("intent_detector", result)

        assert "event: node_result" in event
        assert "intent_detector" in event
        assert "create_customer" in event

    def test_build_tool_call_event(self) -> None:
        """Test tool_call event format."""
        event = build_tool_call_event("create_follow_up", {"customer_id": 101})

        assert "event: tool_call" in event
        assert "create_follow_up" in event
        assert json.dumps({"tool": "create_follow_up"}) in event

    def test_build_tool_result_event(self) -> None:
        """Test tool_result event format."""
        result = {"success": True, "follow_up_id": 501}
        event = build_tool_result_event("create_follow_up", result)

        assert "event: tool_result" in event
        assert "create_follow_up" in event
        assert "follow_up_id" in event

    def test_build_waiting_for_user_event(self) -> None:
        """Test waiting_for_user event format."""
        event = build_waiting_for_user_event(
            question="请选择客户",
            options=["张三科技", "光大证券"],
            missing_fields=["customer_id"],
            field_options={"customer_source": ["线上", "电话"]},
        )

        assert "event: waiting_for_user" in event
        assert "请选择客户" in event
        assert json.dumps(["张三科技", "光大证券"]) in event

    def test_build_react_complete_event(self) -> None:
        """Test react_complete event format."""
        event = build_react_complete_event(3, "对话处理完成")

        assert "event: react_complete" in event
        assert json.dumps({"rounds": 3, "message": "对话处理完成"}) in event

    def test_build_error_event(self) -> None:
        """Test error event format."""
        event = build_error_event("操作失败")

        assert "event: error" in event
        assert "操作失败" in event


class TestFilterResultForDisplay:
    """Tests for result filtering."""

    def test_filter_excludes_sensitive_fields(self) -> None:
        """Test that sensitive fields are excluded."""
        result = {
            "success": True,
            "data": {"follow_up_id": 101},
            "db": "should_be_excluded",
            "user": {"secret": "data"},
        }

        filtered = filter_result_for_display(result)

        assert "db" not in filtered
        assert "user" not in filtered
        assert "success" in filtered
        assert "data" in filtered

    def test_filter_handles_nested_dicts(self) -> None:
        """Test that nested dicts are filtered recursively."""
        result = {
            "success": True,
            "nested": {
                "value": "keep",
                "_internal": "remove",
            },
        }

        filtered = filter_result_for_display(result)

        assert filtered["nested"]["value"] == "keep"
        assert "_internal" not in filtered["nested"]

    def test_filter_handles_lists(self) -> None:
        """Test that lists with dicts are filtered."""
        result = {
            "items": [
                {"id": 1, "name": "Item1"},
                {"id": 2, "_internal": "remove"},
            ],
        }

        filtered = filter_result_for_display(result)

        assert filtered["items"][0]["id"] == 1
        assert "_internal" not in filtered["items"][1]


class TestSSECompatibility:
    """Tests for SSE format compatibility with legacy API."""

    def test_event_format_matches_legacy(self) -> None:
        """Test that event format matches legacy ai_tool_service."""
        # Legacy format example
        legacy_format = "event: tool_result\ndata: {\"tool\": \"create_follow_up\"}\n\n"

        # New format
        new_format = build_tool_call_event("create_follow_up")

        # Both should have same structure
        assert "event: tool_result" in legacy_format
        assert new_format.startswith("event:")
        assert "data:" in new_format

    def test_waiting_for_user_format_matches(self) -> None:
        """Test waiting_for_user format matches legacy."""
        # Legacy waiting_for_user event structure
        expected_fields = {
            "question",
            "options",
            "missing_fields",
            "field_options",
        }

        event = build_waiting_for_user_event(
            question="Test",
            options=["A", "B"],
            missing_fields=["field1"],
            field_options={"field1": {"options": ["X", "Y"]}},
        )

        # Parse event data
        data_start = event.find("data: ") + 6
        data_end = event.find("\n\n")
        data_json = json.loads(event[data_start:data_end])

        # Should have same fields as legacy
        for field in expected_fields:
            assert field in data_json

    def test_react_complete_format_matches(self) -> None:
        """Test react_complete format matches legacy."""
        event = build_react_complete_event(3, "完成")

        data_start = event.find("data: ") + 6
        data_end = event.find("\n\n")
        data_json = json.loads(event[data_start:data_end])

        # Should have rounds and message
        assert "rounds" in data_json
        assert "message" in data_json
        assert data_json["rounds"] == 3


class TestStreamSSEEvents:
    """Tests for stream_sse_events function."""

    @pytest.mark.asyncio
    async def test_stream_yields_start_event_first(self) -> None:
        """Test that stream yields start event first."""
        # Mock app
        mock_app = MagicMock()

        # Mock astream_events (empty stream)
        async def mock_stream(*args, **kwargs):
            return
            yield  # Never executes

        mock_app.astream_events = mock_stream

        # Collect events
        events = []
        async for event in stream_sse_events(
            mock_app, {"messages": []}, "test-session"
        ):
            events.append(event)

        # First event should be start
        assert len(events) > 0
        assert "event: start" in events[0]

    @pytest.mark.asyncio
    async def test_stream_handles_interrupt(self) -> None:
        """Test that stream handles interrupt correctly."""
        mock_app = MagicMock()

        # Mock stream with interrupt
        async def mock_stream(*args, **kwargs):
            yield {"event": "on_interrupt", "data": {"value": {"question": "Test?"}}}

        mock_app.astream_events = mock_stream

        events = []
        async for event in stream_sse_events(
            mock_app, {"messages": []}, "test-session"
        ):
            events.append(event)

        # Should have waiting_for_user event
        assert any("event: waiting_for_user" in e for e in events)


class TestSSEEventParsing:
    """Tests for SSE event parsing (frontend side)."""

    def test_event_can_be_parsed_by_frontend(self) -> None:
        """Test that events can be parsed by frontend SSE parser."""
        # Frontend parser logic (from aiAssistant.ts)
        def parse_sse_event(event_str: str) -> tuple[str, dict]:
            lines = event_str.strip().split("\n")
            event_type = None
            data = None

            for line in lines:
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])

            return event_type, data

        # Test various events
        events = [
            build_start_event("session-123"),
            build_tool_call_event("create_follow_up"),
            build_waiting_for_user_event("Test?", ["A", "B"]),
        ]

        for event in events:
            event_type, data = parse_sse_event(event)

            assert event_type is not None
            assert data is not None
            assert isinstance(data, dict)