"""Task 3.5 测试：/v1/agent/chat 代理到 Glue SSE。

验证：
- 端点函数内部使用 Glue DialogueEngine + GlueSSEStreamer
- SSE 事件兼容（start/result/complete/error）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.api.agent_assistant import (
    AgentAssistantRequest,
    chat_with_agent,
    get_session_state,
    delete_session,
)


@pytest.mark.asyncio
async def test_agent_chat_uses_glue_components():
    """Task 3.5: chat_with_agent 内部调用 Glue SSE Streamer"""
    # Mock dependencies
    mock_user = MagicMock(id=1, username="test_user")
    mock_team_id = 1

    # Mock Glue components
    with patch("app.api.agent_assistant.get_redis_client") as mock_redis:
        with patch("app.api.agent_assistant.SessionManager") as mock_session_mgr_class:
            with patch("app.api.agent_assistant.DialogueEngine") as mock_engine_class:
                with patch("app.api.agent_assistant.GlueSSEStreamer") as mock_streamer_class:
                    # Setup mocks
                    redis_client = MagicMock()
                    mock_redis.return_value = redis_client

                    # Mock SessionManager
                    session_mgr = MagicMock()
                    session_mgr.load = AsyncMock(return_value=None)  # 新 session
                    session_mgr.save = AsyncMock()
                    mock_session_mgr_class.return_value = session_mgr

                    # Mock GlueSSEStreamer - yield SSE events
                    streamer = MagicMock()
                    async def fake_stream(*args, **kwargs):
                        yield "event: start\ndata: {\"session_id\":\"test-sid\"}\n\n"
                        yield "event: result\ndata: {\"event\":\"result\",\"success\":true,\"message\":\"OK\",\"content\":\"OK\",\"answer\":\"OK\",\"rounds\":1,\"is_partial\":false}\n\n"
                        yield "event: complete\ndata: {\"answer\":\"OK\",\"rounds\":1,\"is_partial\":false}\n\n"
                    streamer.stream = fake_stream
                    mock_streamer_class.return_value = streamer

                    # Mock DialogueEngine
                    engine = MagicMock()
                    mock_engine_class.return_value = engine

                    # Call the function
                    request = AgentAssistantRequest(content="创建商机金额1000万")
                    response = await chat_with_agent(
                        request,
                        team_id=mock_team_id,
                        current_user=mock_user,
                    )

                    # Verify response is StreamingResponse
                    assert response.media_type == "text/event-stream"

                    # Verify Glue components were called
                    mock_streamer_class.assert_called_once()
                    mock_engine_class.assert_called_once_with(
                        redis_client=redis_client,
                        team_id=mock_team_id,
                        user_id=mock_user.id,
                    )

                    # Consume the stream to verify events
                    events = []
                    async for chunk in response.body_iterator:
                        events.append(chunk)

                    assert len(events) >= 3
                    assert "event: start" in events[0]
                    assert "event: result" in events[1]
                    assert "event: complete" in events[2]


@pytest.mark.asyncio
async def test_agent_chat_creates_new_session_if_not_found():
    """Task 3.5: 无 session_id 时自动创建新 GlueSession"""
    mock_user = MagicMock(id=1)
    mock_team_id = 1

    with patch("app.api.agent_assistant.get_redis_client") as mock_redis:
        with patch("app.api.agent_assistant.SessionManager") as mock_session_mgr_class:
            with patch("app.api.agent_assistant.DialogueEngine") as mock_engine_class:
                with patch("app.api.agent_assistant.GlueSSEStreamer") as mock_streamer_class:
                    redis_client = MagicMock()
                    mock_redis.return_value = redis_client

                    # Mock SessionManager.load returns None (new session)
                    session_mgr = MagicMock()
                    session_mgr.load = AsyncMock(return_value=None)
                    session_mgr.save = AsyncMock()
                    mock_session_mgr_class.return_value = session_mgr

                    # Mock streamer - 完整的 stream（包含 complete）
                    streamer = MagicMock()
                    async def complete_stream(*args, **kwargs):
                        yield "event: start\ndata: {}\n\n"
                        yield "event: complete\ndata: {}\n\n"  # 必须有 complete 才会 save
                    streamer.stream = complete_stream
                    mock_streamer_class.return_value = streamer

                    mock_engine_class.return_value = MagicMock()

                    # Call without session_id
                    request = AgentAssistantRequest(content="test")
                    response = await chat_with_agent(
                        request,
                        team_id=mock_team_id,
                        current_user=mock_user,
                    )

                    # 手动消费整个 stream（触发 save）
                    chunks = []
                    async for chunk in response.body_iterator:
                        chunks.append(chunk)

                    # Verify stream was consumed
                    assert len(chunks) >= 2

                    # Verify SessionManager.save was called after stream completed
                    session_mgr.save.assert_called_once()


@pytest.mark.asyncio
async def test_get_session_proxies_to_glue_session_manager():
    """Task 3.5: /v1/agent/session/{id} GET 代理到 Glue SessionManager"""
    mock_user = MagicMock(id=1)
    mock_team_id = 1
    session_id = "test-session-uuid"

    with patch("app.api.agent_assistant.get_redis_client") as mock_redis:
        with patch("app.api.agent_assistant.SessionManager") as mock_session_mgr_class:
            redis_client = MagicMock()
            mock_redis.return_value = redis_client

            # Mock GlueSession
            from app.glue.core.session import GlueSession
            mock_session = GlueSession(
                session_id=session_id,
                tenant_id=str(mock_team_id),
                crm_user_id=mock_user.id,
                history_last_n=[],
                pending=None,
            )

            session_mgr = MagicMock()
            session_mgr.load = AsyncMock(return_value=mock_session)
            mock_session_mgr_class.return_value = session_mgr

            # Call get_session_state
            response = await get_session_state(
                session_id,
                team_id=mock_team_id,
                current_user=mock_user,
            )

            # Verify SessionManager.load was called
            session_mgr.load.assert_called_once_with(session_id)

            # Verify response format
            assert response["session_id"] == session_id
            assert response["messages"] == []


@pytest.mark.asyncio
async def test_get_session_403_if_wrong_team():
    """Task 3.5: Session GET 校验归属（非当前 team → 403）"""
    mock_user = MagicMock(id=1)
    mock_team_id = 1
    session_id = "test-session-uuid"

    with patch("app.api.agent_assistant.get_redis_client") as mock_redis:
        with patch("app.api.agent_assistant.SessionManager") as mock_session_mgr_class:
            redis_client = MagicMock()
            mock_redis.return_value = redis_client

            # Mock GlueSession with different team_id
            from app.glue.core.session import GlueSession
            mock_session = GlueSession(
                session_id=session_id,
                tenant_id="999",  # Different team!
                crm_user_id=mock_user.id,
                history_last_n=[],
                pending=None,
            )

            session_mgr = MagicMock()
            session_mgr.load = AsyncMock(return_value=mock_session)
            mock_session_mgr_class.return_value = session_mgr

            # Call should raise 403
            with pytest.raises(HTTPException) as exc:
                await get_session_state(
                    session_id,
                    team_id=mock_team_id,
                    current_user=mock_user,
                )

            assert exc.value.status_code == 403
            assert "different team" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_delete_session_proxies_to_glue():
    """Task 3.5: Session DELETE 代理到 Glue SessionManager"""
    mock_user = MagicMock(id=1)
    mock_team_id = 1
    session_id = "test-session-uuid"

    with patch("app.api.agent_assistant.get_redis_client") as mock_redis:
        with patch("app.api.agent_assistant.SessionManager") as mock_session_mgr_class:
            redis_client = MagicMock()
            mock_redis.return_value = redis_client

            # Mock GlueSession
            from app.glue.core.session import GlueSession
            mock_session = GlueSession(
                session_id=session_id,
                tenant_id=str(mock_team_id),
                crm_user_id=mock_user.id,
                history_last_n=[],
                pending=None,
            )

            session_mgr = MagicMock()
            session_mgr.load = AsyncMock(return_value=mock_session)
            session_mgr.clear = AsyncMock()
            mock_session_mgr_class.return_value = session_mgr

            # Call delete_session
            response = await delete_session(
                session_id,
                team_id=mock_team_id,
                current_user=mock_user,
            )

            # Verify SessionManager.clear was called
            session_mgr.clear.assert_called_once_with(session_id)

            # Verify response
            assert response["message"] == "Session deleted"
            assert response["session_id"] == session_id