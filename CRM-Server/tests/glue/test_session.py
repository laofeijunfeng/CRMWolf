"""Session Manager 单元测试

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 6.3
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import redis.asyncio as redis

from app.glue.core.session import (
    SessionManager,
    GlueSession,
    PendingAction,
    RecentEntities,
    HistoryEntry,
)
from app.glue.config import SessionMode


class TestSessionManager:
    """SessionManager 测试"""

    @pytest.fixture
    def redis_client(self):
        """Redis client fixture"""
        mock_redis = AsyncMock(spec=redis.Redis)
        return mock_redis

    @pytest.fixture
    def session_manager(self, redis_client):
        """SessionManager fixture"""
        return SessionManager(redis_client)

    @pytest.mark.asyncio
    async def test_load_new_session(self, session_manager, redis_client):
        """测试加载新 session（不存在）"""
        redis_client.get = AsyncMock(return_value=None)

        session = await session_manager.load("tenant_001", 123)

        assert session.tenant_id == "tenant_001"
        assert session.crm_user_id == 123
        assert session.mode == SessionMode.IDLE
        assert session.pending is None

    @pytest.mark.asyncio
    async def test_load_existing_session(self, session_manager, redis_client):
        """测试加载已存在的 session"""
        mock_data = """
        {
            "v": 1,
            "tenant_id": "tenant_001",
            "crm_user_id": 123,
            "mode": "preview",
            "updated_at": 1719220000,
            "pending": null,
            "recent_entities": {
                "customer_id": 101,
                "opportunity_id": 456
            },
            "history_last_n": []
        }
        """
        redis_client.get = AsyncMock(return_value=mock_data)
        redis_client.expire = AsyncMock()

        session = await session_manager.load("tenant_001", 123)

        assert session.tenant_id == "tenant_001"
        assert session.crm_user_id == 123
        assert session.mode == "preview"
        assert session.recent_entities.customer_id == 101

    @pytest.mark.asyncio
    async def test_save_session(self, session_manager, redis_client):
        """测试保存 session"""
        session = GlueSession(
            tenant_id="tenant_001",
            crm_user_id=123,
            mode=SessionMode.IDLE,
        )

        redis_client.set = AsyncMock()

        result = await session_manager.save(session)

        assert result is True
        redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_session(self, session_manager, redis_client):
        """测试清空 session"""
        redis_client.delete = AsyncMock()

        result = await session_manager.clear("tenant_001", 123)

        assert result is True
        redis_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_pending(self, session_manager, redis_client):
        """测试设置 pending action"""
        session = GlueSession(
            tenant_id="tenant_001",
            crm_user_id=123,
            mode=SessionMode.IDLE,
        )
        pending = PendingAction(
            action_id="act_xxx",
            intent="update_amount",
            slots={"opportunity_id": 456, "amount": 350000},
            preview_snapshot={},
        )

        redis_client.set = AsyncMock()

        result = await session_manager.set_pending(session, pending)

        assert result is True
        assert session.mode == SessionMode.PREVIEW
        assert session.pending is not None
        assert session.pending.expires_at is not None

    @pytest.mark.asyncio
    async def test_add_history(self, session_manager, redis_client):
        """测试添加对话历史"""
        session = GlueSession(
            tenant_id="tenant_001",
            crm_user_id=123,
            mode=SessionMode.IDLE,
            history_last_n=[],
        )

        redis_client.set = AsyncMock()

        result = await session_manager.add_history(session, "user", "测试消息")

        assert result is True
        assert len(session.history_last_n) == 1
        assert session.history_last_n[0].role == "user"
        assert session.history_last_n[0].text == "测试消息"


class TestPendingAction:
    """PendingAction 测试"""

    def test_pending_not_expired(self):
        """测试 pending 未过期"""
        pending = PendingAction(
            action_id="act_xxx",
            intent="update_amount",
            slots={},
            preview_snapshot={},
            expires_at=9999999999,  # 未来时间
        )

        assert not pending.is_expired()

    def test_pending_expired(self):
        """测试 pending 已过期"""
        pending = PendingAction(
            action_id="act_xxx",
            intent="update_amount",
            slots={},
            preview_snapshot={},
            expires_at=1000000000,  # 过去时间
        )

        assert pending.is_expired()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])