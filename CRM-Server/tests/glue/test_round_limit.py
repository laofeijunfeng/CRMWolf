"""Task 3.4: Glue 轮次管理（MAX_ROUNDS + 超限降级）。

验证多意图场景下轮次计数，防止无限循环。
"""
from unittest.mock import MagicMock, AsyncMock
import pytest
import redis.asyncio as redis

from app.glue.core.dialogue import DialogueEngine, DialogueAction
from app.glue.core.session import GlueSession, PendingAction, SessionManager
from app.glue.config import SessionMode
from app.glue.core.executor import ExecutionResult


@pytest.fixture
def engine():
    """DialogueEngine with mock db."""
    return DialogueEngine(db=MagicMock(), tenant_id=1, user_id=2)


@pytest.fixture
def executing_session_with_queue():
    """EXECUTING mode session with multi-intent queue."""
    return GlueSession(
        tenant_id="1",
        crm_user_id=2,
        mode=SessionMode.EXECUTING,
        pending=PendingAction(
            action_id="action-1",
            intent_type="create_follow_up",
            slots={"customer_id": 1, "content": "跟进1"},
            missing_slots=[],
            preview_snapshot={},
        ),
        pending_queue=[
            PendingAction(
                action_id="action-1",
                intent_type="create_follow_up",
                slots={"customer_id": 1, "content": "跟进1"},
                missing_slots=[],
                preview_snapshot={},
            ),
            PendingAction(
                action_id="action-2",
                intent_type="create_follow_up",
                slots={"customer_id": 2, "content": "跟进2"},
                missing_slots=[],
                preview_snapshot={},
            ),
            PendingAction(
                action_id="action-3",
                intent_type="create_follow_up",
                slots={"customer_id": 3, "content": "跟进3"},
                missing_slots=[],
                preview_snapshot={},
            ),
        ],
        round_count=0,
    )


@pytest.fixture
def redis_client():
    """Redis client fixture."""
    mock_redis = AsyncMock(spec=redis.Redis)
    return mock_redis


@pytest.fixture
def session_manager(redis_client):
    """SessionManager fixture."""
    return SessionManager(redis_client)


@pytest.mark.asyncio
async def test_round_count_increments_on_multi_intent_execution(engine, executing_session_with_queue, monkeypatch):
    """Task 3.4: 轮次计数应在多意图执行时递增。"""
    call_count = {"count": 0}

    async def fake_execute(pending, action_id):
        call_count["count"] += 1
        return ExecutionResult(
            success=True,
            message=f"执行成功 {call_count['count']}",
            action_id=action_id,
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    # 第一次执行后，round_count 应递增
    result = await engine.dispatch(executing_session_with_queue, "确认")

    assert result.success, f"执行应成功: {result.message}"
    assert executing_session_with_queue.round_count >= 1, "round_count 应递增"


@pytest.mark.asyncio
async def test_multi_intent_exceeds_max_rounds_marks_partial(engine, executing_session_with_queue, monkeypatch):
    """Task 3.4: 超过 MAX_ROUNDS 时 is_partial=True，不再继续执行。"""
    # 设置 MAX_ROUNDS = 2（小于队列长度 3）
    engine.MAX_ROUNDS = 2

    execute_calls = []

    async def fake_execute(pending, action_id):
        execute_calls.append(action_id)
        return ExecutionResult(
            success=True,
            message=f"执行成功: {action_id}",
            action_id=action_id,
        )

    monkeypatch.setattr(engine.action_executor, "execute", fake_execute)

    # 第一次执行（round_count: 0 -> 1）
    result1 = await engine.dispatch(executing_session_with_queue, "确认")
    assert result1.success, f"第一次执行应成功: {result1.message}"

    # 第二次执行（round_count: 1 -> 2）- 达到 MAX_ROUNDS
    result2 = await engine.dispatch(executing_session_with_queue, "确认")
    assert result2.success, f"第二次执行应成功: {result2.message}"

    # 第三次执行 - 应被阻止，返回 is_partial=True
    result3 = await engine.dispatch(executing_session_with_queue, "确认")

    # 验证 is_partial 标记
    assert result3.data is not None, "result.data 应存在"
    assert result3.data.get("is_partial") is True, "超过 MAX_ROUNDS 应返回 is_partial=True"

    # 验证只执行了 2 次（MAX_ROUNDS 限制）
    assert len(execute_calls) == 2, f"应只执行 {engine.MAX_ROUNDS} 次，实际执行 {len(execute_calls)} 次"


@pytest.mark.asyncio
async def test_max_rounds_default_is_10(engine):
    """Task 3.4: MAX_ROUNDS 默认值应为 10（对齐 ReAct）。"""
    assert engine.MAX_ROUNDS == 10, "MAX_ROUNDS 默认值应为 10"


@pytest.mark.asyncio
async def test_round_count_resets_on_new_session(engine, monkeypatch):
    """Task 3.4: 新 session 的 round_count 应为 0。"""
    new_session = GlueSession(
        tenant_id="1",
        crm_user_id=2,
        mode=SessionMode.IDLE,
    )

    assert new_session.round_count == 0, "新 session 的 round_count 应为 0"


@pytest.mark.asyncio
async def test_round_count_serialization(session_manager, redis_client):
    """Task 3.4: round_count 应正确序列化和反序列化。"""
    session = GlueSession(
        tenant_id="tenant_001",
        crm_user_id=123,
        mode=SessionMode.EXECUTING,
        round_count=5,
    )

    # 序列化
    serialized = session_manager._serialize(session)
    assert "round_count" in serialized, "序列化数据应包含 round_count"
    assert '"round_count": 5' in serialized, "round_count 值应为 5"

    # 反序列化
    redis_client.get = AsyncMock(return_value=serialized)
    redis_client.expire = AsyncMock()

    loaded = await session_manager.load(session.session_id)

    assert loaded.round_count == 5, f"反序列化后 round_count 应为 5，实际 {loaded.round_count}"


@pytest.mark.asyncio
async def test_round_count_defaults_to_zero_on_deserialize_old_data(session_manager, redis_client):
    """Task 3.4: 旧数据（无 round_count）反序列化时应默认为 0。"""
    # 旧格式数据（不含 round_count）
    old_data = """
    {
        "v": 1,
        "session_id": "test-session-123",
        "tenant_id": "tenant_001",
        "crm_user_id": 123,
        "mode": "idle",
        "updated_at": 1719220000,
        "pending": null,
        "pending_queue": [],
        "recent_entities": null,
        "history_last_n": [],
        "entity_resolution_context": null,
        "ambiguity_context": null
    }
    """

    redis_client.get = AsyncMock(return_value=old_data)
    redis_client.expire = AsyncMock()

    loaded = await session_manager.load("test-session-123")

    assert loaded.round_count == 0, "旧数据反序列化后 round_count 应默认为 0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])