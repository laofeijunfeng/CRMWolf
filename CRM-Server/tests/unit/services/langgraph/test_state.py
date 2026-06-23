"""
Tests for LangGraph State Module

Tests for AgentState, UserExecCtx, and state helper functions.
"""

import pytest
from datetime import datetime

from app.services.langgraph.state import (
    AgentState,
    UserExecCtx,
    create_initial_state,
    update_state_with_entity,
)


class TestAgentState:
    """Tests for AgentState TypedDict."""

    def test_agent_state_required_fields(self) -> None:
        """Test that AgentState has all required fields."""
        state = AgentState(
            messages=[{"role": "user", "content": "Hello"}],
            session_id="test-session",
            user_id=1,
            team_id=1,
            entity_context=None,
            round_num=0,
            execution_history=[],
            recent_entities={},
            intent_result=None,
            entity_result=None,
            preview_result=None,
            exec_result=None,
            waiting_for_user=False,
            pending_question=None,
            pending_options=None,
            pending_missing_fields=None,
            pending_field_options=None,
            workflow_id=None,
            workflow_step_index=0,
            rollback_points=[],
            error=None,
            workflow_terminated=False,
            termination_reason=None,
        )

        assert state["session_id"] == "test-session"
        assert state["user_id"] == 1
        assert state["team_id"] == 1
        assert state["messages"] == [{"role": "user", "content": "Hello"}]
        assert state["round_num"] == 0

    def test_agent_state_with_entity_context(self) -> None:
        """Test AgentState with entity context."""
        entity_context = {
            "entity_type": "Customer",
            "entity_id": 101,
            "entity_name": "张三科技",
        }

        state = AgentState(
            messages=[{"role": "user", "content": "跟进张三客户"}],
            session_id="test-session",
            user_id=1,
            team_id=1,
            entity_context=entity_context,
            round_num=0,
            execution_history=[],
            recent_entities={"customer_id": 101},
            workflow_step_index=0,
            rollback_points=[],
            waiting_for_user=False,
            workflow_terminated=False,
        )

        assert state["entity_context"]["entity_type"] == "Customer"
        assert state["recent_entities"]["customer_id"] == 101


class TestUserExecCtx:
    """Tests for UserExecCtx."""

    def test_user_exec_ctx_creation(self) -> None:
        """Test UserExecCtx creation."""
        ctx = UserExecCtx(
            user_id=1,
            tenant_id=1,
            source="ai_assistant",
            is_ai=True,
        )

        assert ctx.user_id == 1
        assert ctx.tenant_id == 1
        assert ctx.source == "ai_assistant"
        assert ctx.is_ai == True

    def test_user_exec_ctx_defaults(self) -> None:
        """Test UserExecCtx default values."""
        ctx = UserExecCtx(
            user_id=1,
            tenant_id=1,
        )

        assert ctx.roles == []
        assert ctx.is_ai == False
        assert ctx.source == "web"


class TestCreateInitialState:
    """Tests for create_initial_state helper."""

    def test_create_initial_state_basic(self) -> None:
        """Test basic initial state creation."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="Hello",
        )

        assert state["session_id"] == "test-123"
        assert state["user_id"] == 1
        assert state["team_id"] == 1
        assert state["messages"][0]["content"] == "Hello"
        assert state["round_num"] == 0
        assert state["workflow_step_index"] == 0
        assert state["waiting_for_user"] == False

    def test_create_initial_state_with_entity_context(self) -> None:
        """Test initial state with entity context."""
        entity_context = {
            "entity_type": "Customer",
            "entity_id": 101,
            "entity_name": "张三科技",
        }

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进客户",
            entity_context=entity_context,
        )

        assert state["entity_context"]["entity_type"] == "Customer"
        assert state["entity_context"]["entity_id"] == 101

    def test_create_initial_state_all_defaults(self) -> None:
        """Test that all default fields are set correctly."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="Test",
        )

        # Check all defaults
        assert state["entity_context"] == None
        assert state["execution_history"] == []
        assert state["recent_entities"] == {}
        assert state["intent_result"] == None
        assert state["entity_result"] == None
        assert state["preview_result"] == None
        assert state["exec_result"] == None
        assert state["pending_question"] == None
        assert state["pending_options"] == None
        assert state["pending_missing_fields"] == None
        assert state["pending_field_options"] == None
        assert state["workflow_id"] == None
        assert state["rollback_points"] == []
        assert state["error"] == None
        assert state["workflow_terminated"] == False
        assert state["termination_reason"] == None


class TestUpdateStateWithEntity:
    """Tests for update_state_with_entity helper."""

    def test_update_state_with_entity_basic(self) -> None:
        """Test basic entity state update."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进客户",
        )

        updated = update_state_with_entity(
            state,
            entity_type="Customer",
            entity_id=101,
            entity_name="张三科技",
        )

        assert updated["entity_context"]["entity_type"] == "Customer"
        assert updated["entity_context"]["entity_id"] == 101
        assert updated["entity_context"]["entity_name"] == "张三科技"
        assert updated["recent_entities"]["customer_id"] == 101

    def test_update_state_preserves_other_fields(self) -> None:
        """Test that other fields are preserved during update."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进客户",
        )

        # Add some execution history
        state["execution_history"] = [{"action": "test"}]

        updated = update_state_with_entity(
            state,
            entity_type="Opportunity",
            entity_id=205,
            entity_name="CRM项目",
        )

        # Check preserved fields
        assert updated["session_id"] == "test-123"
        assert updated["execution_history"] == [{"action": "test"}]

        # Check updated fields
        assert updated["recent_entities"]["opportunity_id"] == 205


class TestStateSerialization:
    """Tests for state JSON serialization."""

    def test_state_is_json_serializable(self) -> None:
        """Test that state can be serialized to JSON."""
        import json

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="Hello",
        )

        # Should not raise
        json_str = json.dumps(state, ensure_ascii=False)
        assert json_str is not None

        # Should deserialize correctly
        parsed = json.loads(json_str)
        assert parsed["session_id"] == "test-123"

    def test_state_with_nested_dicts_serializable(self) -> None:
        """Test state with nested dicts is serializable."""
        import json

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进客户",
            entity_context={
                "entity_type": "Customer",
                "entity_id": 101,
                "entity_name": "张三",
            },
        )

        # Should not raise
        json_str = json.dumps(state, ensure_ascii=False)
        parsed = json.loads(json_str)

        assert parsed["entity_context"]["entity_name"] == "张三"