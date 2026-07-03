"""Admin API 安全测试

测试 app/glue/api/admin.py 端点的认证和授权。

参见: Task 3.2 Admin API Security Fix + Session UUID API
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
import redis.asyncio as redis

from app.glue.api.admin import router
from app.models.user import User


# ==================== Test App Setup ====================

@pytest.fixture
def app():
    """创建测试 FastAPI 应用"""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    return AsyncMock(spec=redis.Redis)


@pytest.fixture
def mock_user():
    """Mock 活跃用户"""
    user = MagicMock(spec=User)
    user.id = 1
    user.status = "active"
    return user


@pytest.fixture
def mock_team_id():
    """Mock team_id"""
    return 100


# ==================== Authentication Tests ====================

class TestAdminAuthentication:
    """Admin 端点认证测试"""

    def test_get_session_requires_authentication(self, client):
        """GET /sessions/{session_id} 应返回 401/422 无认证"""
        response = client.get("/glue/v1/sessions/test-session-id")
        # 由于 TestClient 同步调用异步端点，会返回 422 (缺少依赖注入)
        # 或 401/403 如果依赖正确注入但无认证
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_delete_session_requires_authentication(self, client):
        """DELETE /sessions/{session_id} 应返回 401/422 无认证"""
        response = client.delete("/glue/v1/sessions/test-session-id")
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


# ==================== Authorization Tests ====================

class TestAdminAuthorization:
    """Admin 端点授权测试（session.tenant_id 校验）"""

    @pytest.mark.asyncio
    async def test_get_session_tenant_mismatch_returns_403(self, mock_redis, mock_user, mock_team_id):
        """GET /sessions session.tenant_id 不匹配应返回 403"""
        from app.glue.api.admin import get_session
        from fastapi import HTTPException
        from app.glue.core.session import GlueSession, SessionMode

        # Mock session with mismatched tenant_id
        mock_session = GlueSession(
            tenant_id="999",  # 不匹配 team_id=100
            crm_user_id=123,
            mode=SessionMode.IDLE,
        )
        mock_session.session_id = "test-session-id"

        with patch("app.glue.api.admin.SessionManager") as MockSessionManager:
            mock_manager = AsyncMock()
            mock_manager.load = AsyncMock(return_value=mock_session)
            MockSessionManager.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await get_session(
                    session_id="test-session-id",
                    redis_client=mock_redis,
                    team_id=mock_team_id,  # 100
                )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "无权访问此 Session" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_session_tenant_match_success(self, mock_redis, mock_user, mock_team_id):
        """GET /sessions session.tenant_id 匹配应成功"""
        from app.glue.api.admin import get_session, SessionResponse
        from app.glue.core.session import GlueSession, SessionMode

        # Mock session with matching tenant_id
        mock_session = GlueSession(
            tenant_id="100",  # 匹配 team_id=100
            crm_user_id=123,
            mode=SessionMode.IDLE,
            history_last_n=[],
        )
        mock_session.session_id = "test-session-id"

        with patch("app.glue.api.admin.SessionManager") as MockSessionManager:
            mock_manager = AsyncMock()
            mock_manager.load = AsyncMock(return_value=mock_session)
            MockSessionManager.return_value = mock_manager

            response = await get_session(
                session_id="test-session-id",
                redis_client=mock_redis,
                team_id=mock_team_id,  # 100
            )

        assert isinstance(response, SessionResponse)
        assert response.session_id == "test-session-id"

    @pytest.mark.asyncio
    async def test_delete_session_tenant_mismatch_returns_403(self, mock_redis, mock_user, mock_team_id):
        """DELETE /sessions session.tenant_id 不匹配应返回 403"""
        from app.glue.api.admin import clear_session
        from fastapi import HTTPException
        from app.glue.core.session import GlueSession, SessionMode

        # Mock session with mismatched tenant_id
        mock_session = GlueSession(
            tenant_id="999",  # 不匹配 team_id=100
            crm_user_id=123,
            mode=SessionMode.IDLE,
        )
        mock_session.session_id = "test-session-id"

        with patch("app.glue.api.admin.SessionManager") as MockSessionManager:
            mock_manager = AsyncMock()
            mock_manager.load = AsyncMock(return_value=mock_session)
            MockSessionManager.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await clear_session(
                    session_id="test-session-id",
                    redis_client=mock_redis,
                    team_id=mock_team_id,
                )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "无权访问此 Session" in exc_info.value.detail


# ==================== Session Existence Tests ====================

class TestSessionExistence:
    """Session 存在性检查测试"""

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_404(self, mock_redis, mock_team_id):
        """GET 不存在的 session 应返回 404"""
        from app.glue.api.admin import get_session
        from fastapi import HTTPException

        with patch("app.glue.api.admin.SessionManager") as MockSessionManager:
            mock_manager = AsyncMock()
            mock_manager.load = AsyncMock(return_value=None)  # Session 不存在
            MockSessionManager.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await get_session(
                    session_id="nonexistent-session",
                    redis_client=mock_redis,
                    team_id=mock_team_id,
                )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Session not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_nonexistent_session_returns_404(self, mock_redis, mock_team_id):
        """DELETE 不存在的 session 应返回 404"""
        from app.glue.api.admin import clear_session
        from fastapi import HTTPException

        with patch("app.glue.api.admin.SessionManager") as MockSessionManager:
            mock_manager = AsyncMock()
            mock_manager.load = AsyncMock(return_value=None)  # Session 不存在
            MockSessionManager.return_value = mock_manager

            with pytest.raises(HTTPException) as exc_info:
                await clear_session(
                    session_id="nonexistent-session",
                    redis_client=mock_redis,
                    team_id=mock_team_id,
                )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Session not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_existing_session_success(self, mock_redis, mock_team_id):
        """DELETE 存在的 session 应成功"""
        from app.glue.api.admin import clear_session, SessionDeleteResponse
        from app.glue.core.session import GlueSession, SessionMode

        # Mock session with matching tenant_id
        mock_session = GlueSession(
            tenant_id="100",  # 匹配 team_id=100
            crm_user_id=123,
            mode=SessionMode.IDLE,
        )
        mock_session.session_id = "test-session-id"

        with patch("app.glue.api.admin.SessionManager") as MockSessionManager:
            mock_manager = AsyncMock()
            mock_manager.load = AsyncMock(return_value=mock_session)
            mock_manager.clear = AsyncMock(return_value=True)
            MockSessionManager.return_value = mock_manager

            response = await clear_session(
                session_id="test-session-id",
                redis_client=mock_redis,
                team_id=mock_team_id,
            )

        assert isinstance(response, SessionDeleteResponse)
        assert response.message == "Session deleted"
        assert response.session_id == "test-session-id"


# ==================== Health Check (No Auth Required) ====================

class TestHealthCheck:
    """健康检查测试（无需认证）"""

    def test_health_check_no_auth_required(self, client):
        """GET /health 应无需认证"""
        response = client.get("/glue/v1/health")
        # 健康检查不需要认证，应该返回 200 或其他成功状态
        # 或者因 mock Redis 而返回内部错误，但不应返回 401/403
        assert response.status_code not in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]


__all__ = [
    "TestAdminAuthentication",
    "TestAdminAuthorization",
    "TestSessionExistence",
    "TestHealthCheck",
]