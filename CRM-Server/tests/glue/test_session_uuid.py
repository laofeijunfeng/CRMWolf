"""Session UUID 寻址测试

Task 3.2: 统一 Session API 为 uuid 寻址

参见: .claude/sdd/task-3.2-brief.md
"""

import pytest
from unittest.mock import AsyncMock
import redis.asyncio as redis
import json

from app.glue.core.session import SessionManager, GlueSession


class TestSessionUUIDAddressing:
    """Session UUID 寻址测试"""

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
    async def test_session_key_format(self, session_manager):
        """测试 session key 格式为 ai:glue:session:{session_id}"""
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        key = session_manager._session_key(session_id)
        assert key == "ai:glue:session:550e8400-e29b-41d4-a716-446655440000"

    @pytest.mark.asyncio
    async def test_glue_session_has_session_id_field(self):
        """测试 GlueSession 包含 session_id 字段"""
        session = GlueSession(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_id="tenant_001",
            crm_user_id=123,
        )
        assert hasattr(session, "session_id")
        assert session.session_id == "550e8400-e29b-41d4-a716-446655440000"

    @pytest.mark.asyncio
    async def test_glue_session_auto_generates_session_id(self):
        """测试 GlueSession 自动生成 session_id"""
        session = GlueSession(
            tenant_id="tenant_001",
            crm_user_id=123,
        )
        assert session.session_id != ""
        assert len(session.session_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_create_returns_uuid(self, session_manager, redis_client):
        """测试 create() 返回 UUID 格式的 session_id"""
        redis_client.set = AsyncMock()

        session_id = await session_manager.create(tenant_id="tenant_001", crm_user_id=123)

        assert session_id is not None
        assert len(session_id) == 36  # UUID format: 8-4-4-4-12
        redis_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_by_session_id(self, session_manager, redis_client):
        """测试通过 session_id 加载 session"""
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        mock_data = json.dumps({
            "v": 1,
            "session_id": session_id,
            "tenant_id": "tenant_001",
            "crm_user_id": 123,
            "mode": "idle",
            "updated_at": 1719220000,
            "pending": None,
            "pending_queue": [],
            "recent_entities": None,
            "history_last_n": [],
            "entity_resolution_context": None,
            "ambiguity_context": None,
        })

        redis_client.get = AsyncMock(return_value=mock_data)
        redis_client.expire = AsyncMock()

        loaded = await session_manager.load(session_id)

        assert loaded is not None
        assert loaded.session_id == session_id
        assert loaded.tenant_id == "tenant_001"
        assert loaded.crm_user_id == 123
        redis_client.get.assert_called_once()
        redis_client.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self, session_manager, redis_client):
        """测试加载不存在的 session 返回 None"""
        redis_client.get = AsyncMock(return_value=None)

        loaded = await session_manager.load("nonexistent-session-id")

        assert loaded is None

    @pytest.mark.asyncio
    async def test_save_by_session_id(self, session_manager, redis_client):
        """测试通过 session_id 保存 session"""
        session = GlueSession(
            session_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_id="tenant_001",
            crm_user_id=123,
        )
        redis_client.set = AsyncMock()

        result = await session_manager.save(session)

        assert result is True
        redis_client.set.assert_called_once()
        # Verify the key format
        call_args = redis_client.set.call_args
        key = call_args[0][0]
        assert key == "ai:glue:session:550e8400-e29b-41d4-a716-446655440000"

    @pytest.mark.asyncio
    async def test_clear_by_session_id(self, session_manager, redis_client):
        """测试通过 session_id 删除 session"""
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        redis_client.delete = AsyncMock()

        result = await session_manager.clear(session_id)

        assert result is True
        redis_client.delete.assert_called_once_with("ai:glue:session:550e8400-e29b-41d4-a716-446655440000")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])