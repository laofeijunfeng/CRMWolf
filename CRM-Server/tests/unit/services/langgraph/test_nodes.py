"""
Tests for LangGraph Nodes

Tests for RouterNode, IntentDetectorNode, EntityResolverNode,
PreviewNode, ExecuteNode, WorkflowNode.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

from app.services.langgraph.state import AgentState, create_initial_state
from app.services.langgraph.nodes.router import (
    router_node,
    match_workflow,
    route_after_router,
)
from app.services.langgraph.nodes.intent import (
    intent_detector_node,
    route_after_intent,
)


class TestRouterNode:
    """Tests for RouterNode."""

    def test_router_routes_to_react_by_default(self) -> None:
        """Test that router routes to ReAct when no workflow match."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="随便聊聊",
        )

        config = {"configurable": {}}

        result = router_node(state, config)

        assert result["workflow_id"] is None
        assert result["round_num"] == 0

    def test_router_routes_to_workflow_on_keyword_match(self) -> None:
        """Test that router routes to workflow on keyword match."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="确认采购",
        )

        # Add entity context (customer)
        state["entity_context"] = {
            "entity_type": "Customer",
            "entity_id": 101,
            "entity_name": "张三科技",
        }

        config = {"configurable": {}}

        result = router_node(state, config)

        # Should match customer_win_flow
        assert result.get("workflow_id") == "customer_win_flow"
        assert result["workflow_step_index"] == 0

    def test_route_after_router_returns_workflow(self) -> None:
        """Test route_after_router returns 'workflow' when workflow_id set."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="Test",
        )
        state["workflow_id"] = "customer_win_flow"

        route = route_after_router(state)

        assert route == "workflow"

    def test_route_after_router_returns_react(self) -> None:
        """Test route_after_router returns 'react' when no workflow_id."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="Test",
        )

        route = route_after_router(state)

        assert route == "react"


class TestIntentDetectorNode:
    """Tests for IntentDetectorNode."""

    @pytest.mark.asyncio
    async def test_intent_detector_returns_intent_result(self) -> None:
        """Test that intent detector returns intent_result."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="创建客户张三",
        )

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = """
        {
            "action": "create_customer",
            "entity_type": "Customer",
            "confidence": 0.9,
            "params": {"account_name": "张三"},
            "needs_entity_resolution": false
        }
        """

        config = {"configurable": {"db": Mock()}}

        # Patch LLM call
        with patch("app.services.langgraph.nodes.intent.ChatAnthropic") as mock_llm:
            mock_chain = MagicMock()
            mock_chain.invoke = MagicMock(return_value=mock_response)

            with patch("app.services.langgraph.nodes.intent.ChatPromptTemplate") as mock_prompt:
                mock_prompt.from_messages = MagicMock()
                mock_prompt_instance = MagicMock()
                mock_prompt_instance.__or__ = MagicMock(return_value=mock_chain)
                mock_prompt.from_messages.return_value = mock_prompt_instance

                result = intent_detector_node(state, config)

        # Should have intent_result
        assert "intent_result" in result

    def test_route_after_intent_returns_entity_resolver(self) -> None:
        """Test route_after_intent returns 'entity_resolver' when needed."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进张三",
        )
        state["intent_result"] = {
            "action": "create_follow_up",
            "needs_entity_resolution": True,
        }

        route = route_after_intent(state)

        assert route == "entity_resolver"

    def test_route_after_intent_returns_preview(self) -> None:
        """Test route_after_intent returns 'preview' when ready."""
        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进",
        )
        state["intent_result"] = {
            "action": "create_follow_up",
            "needs_entity_resolution": False,
            "needs_slot_collection": False,
        }

        route = route_after_intent(state)

        assert route == "preview"


class TestEntityResolverNode:
    """Tests for EntityResolverNode."""

    def test_entity_resolver_returns_entity_result(self) -> None:
        """Test that entity resolver returns entity_result."""
        from app.services.langgraph.nodes.entity import entity_resolver_node

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进张三",
        )
        state["intent_result"] = {
            "entity_type": "Customer",
            "entity_hint": "张三",
        }

        # Mock database
        mock_db = Mock()
        mock_customer = Mock()
        mock_customer.id = 101
        mock_customer.account_name = "张三科技"

        mock_db.query = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer

        config = {"configurable": {"db": mock_db}}

        # Mock EntityResolver
        with patch("app.services.langgraph.nodes.entity.EntityResolver") as mock_resolver:
            mock_resolver_instance = MagicMock()
            mock_resolver_instance.resolve = MagicMock(
                return_value=Mock(
                    entity_id=101,
                    entity_type="Customer",
                    entity_name="张三科技",
                    confidence=0.85,
                    matched_by="search",
                    error=None,
                    candidates=None,
                )
            )
            mock_resolver.return_value = mock_resolver_instance

            result = entity_resolver_node(state, config)

        # Should have entity_result
        assert "entity_result" in result


class TestPreviewNode:
    """Tests for PreviewNode."""

    def test_preview_node_returns_preview_result(self) -> None:
        """Test that preview node returns preview_result."""
        from app.services.langgraph.nodes.preview import preview_node

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进客户",
        )
        state["intent_result"] = {
            "action": "create_follow_up",
            "params": {"content": "电话跟进"},
        }
        state["entity_result"] = {
            "entity_id": 101,
            "entity_type": "Customer",
        }

        mock_db = Mock()

        config = {"configurable": {"db": mock_db}}

        # Mock ActionEntry
        with patch("app.services.langgraph.nodes.preview.ActionEntry") as mock_entry:
            mock_entry_instance = MagicMock()
            mock_result = Mock()
            mock_result.action_id = "action-123"
            mock_result.status = "preview"
            mock_result.plan = Mock()
            mock_result.plan.model_dump = MagicMock(return_value={"description": "创建跟进"})
            mock_result.requires_confirmation = False
            mock_result.confidence = 0.9

            mock_entry_instance.create_follow_up = MagicMock(return_value=mock_result)
            mock_entry.return_value = mock_entry_instance

            result = preview_node(state, config)

        # Should have preview_result
        assert "preview_result" in result


class TestExecuteNode:
    """Tests for ExecuteNode."""

    def test_execute_node_returns_exec_result(self) -> None:
        """Test that execute node returns exec_result."""
        from app.services.langgraph.nodes.execute import execute_node

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进",
        )
        state["intent_result"] = {
            "action": "create_follow_up",
            "params": {"content": "电话跟进"},
        }
        state["preview_result"] = {
            "action_id": "action-123",
            "status": "preview",
        }
        state["entity_result"] = {
            "entity_id": 101,
            "entity_type": "Customer",
        }

        mock_db = Mock()

        config = {"configurable": {"db": mock_db}}

        # Mock ActionEntry
        with patch("app.services.langgraph.nodes.execute.ActionEntry") as mock_entry:
            mock_entry_instance = MagicMock()
            mock_result = Mock()
            mock_result.status = "completed"
            mock_result.data = {"follow_up_id": 501}
            mock_result.error = None

            mock_entry_instance.create_follow_up = MagicMock(return_value=mock_result)
            mock_entry.return_value = mock_entry_instance

            result = execute_node(state, config)

        # Should have exec_result
        assert "exec_result" in result
        assert result["exec_result"]["status"] == "completed"


class TestWorkflowNode:
    """Tests for WorkflowNode."""

    def test_workflow_node_executes_steps(self) -> None:
        """Test that workflow node executes steps."""
        from app.services.langgraph.nodes.workflow import workflow_node

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="确认采购",
        )
        state["workflow_id"] = "customer_win_flow"
        state["workflow_step_index"] = 0
        state["entity_context"] = {
            "entity_type": "Customer",
            "entity_id": 101,
            "entity_name": "张三科技",
        }

        mock_db = Mock()

        config = {"configurable": {"db": mock_db}}

        # Mock handler execution
        with patch("app.services.langgraph.nodes.workflow._execute_step") as mock_execute:
            mock_execute.return_value = {
                "success": True,
                "data": {"follow_up_id": 501},
            }

            result = workflow_node(state, config)

        # Should increment step index
        assert result["workflow_step_index"] == 1


class TestAskUserNode:
    """Tests for AskUserNode."""

    def test_ask_user_node_sets_waiting_state(self) -> None:
        """Test that ask_user node sets waiting_for_user."""
        from app.services.langgraph.nodes.ask_user import ask_user_node

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="跟进客户",
        )
        state["pending_question"] = "请提供跟进内容"
        state["pending_missing_fields"] = ["content"]

        config = {"configurable": {"db": Mock()}}

        # Mock interrupt (returns immediately in test)
        with patch("app.services.langgraph.nodes.ask_user.interrupt") as mock_interrupt:
            mock_interrupt.return_value = "电话跟进客户，讨论合作意向"

            result = ask_user_node(state, config)

        # Should clear waiting state after resume
        assert result["waiting_for_user"] == False
        assert result["pending_question"] == None


class TestConfirmNode:
    """Tests for ConfirmNode."""

    def test_confirm_node_handles_confirmation(self) -> None:
        """Test that confirm node handles user confirmation."""
        from app.services.langgraph.nodes.confirm import confirm_node

        state = create_initial_state(
            session_id="test-123",
            user_id=1,
            team_id=1,
            user_message="Test",
        )
        state["preview_result"] = {
            "action_id": "action-123",
            "plan": {
                "description": "创建跟进记录",
                "changes": [{"field": "content", "to_value": "电话跟进"}],
            },
            "requires_confirmation": True,
        }

        config = {"configurable": {}}

        # Mock interrupt
        with patch("app.services.langgraph.nodes.confirm.interrupt") as mock_interrupt:
            mock_interrupt.return_value = "确认执行"

            result = confirm_node(state, config)

        # Should set confirmed
        assert result["confirmed"] == True