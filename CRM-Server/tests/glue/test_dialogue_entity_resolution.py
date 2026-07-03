"""Task 2.1 (B1): 实体消解主用例不再 TypeError。

dialogue.py _handle_resolving_entity 调 resolve(text, entity_type_hint=..., keyword=...)
与 EntityResolver.resolve(text, entity_type, session) 签名错配，
导致 RESOLVING_ENTITY 分支必 TypeError → 500。修复后应对齐签名。
"""
from unittest.mock import MagicMock, AsyncMock

import pytest

from app.glue.core.dialogue import DialogueEngine, DialogueAction
from app.glue.core.session import GlueSession, PendingAction
from app.glue.config import SessionMode
from app.glue.core.types import EntityResolveResult


@pytest.fixture
def engine():
    """DialogueEngine with mock db（组件 __init__ 只存 db，不即时使用）。"""
    return DialogueEngine(db=MagicMock(), tenant_id=1, user_id=2)


@pytest.fixture
def resolving_session():
    """RESOLVING_ENTITY 模式 session，带实体消解上下文。"""
    return GlueSession(
        tenant_id="1",
        crm_user_id=2,
        mode=SessionMode.RESOLVING_ENTITY,
        entity_resolution_context={"entity_type": "Customer", "keyword": "张三"},
        pending=PendingAction(
            action_id="act_test",
            intent_type="follow_up_customer",
            slots={},
            preview_snapshot={},
            expires_at=9999999999,
        ),
    )


@pytest.mark.asyncio
async def test_resolving_entity_does_not_typeerror(engine, resolving_session, monkeypatch):
    """B1: resolve() 签名错配已修，RESOLVING_ENTITY 分支不再 TypeError 进 ERROR。"""
    # 让 entity_resolver.resolve 返回消解成功结果（模拟唯一命中）
    async def fake_resolve(text, entity_type, session):
        return EntityResolveResult(
            entity_id=1,
            entity_type=entity_type,
            confidence=0.9,
        )
    monkeypatch.setattr(engine.entity_resolver, "resolve", fake_resolve)

    result = await engine.dispatch(resolving_session, "跟进张三")

    # 不再因 TypeError 进 ERROR；消解成功应推进到下一阶段（PREVIEW/COLLECTING）
    assert result.action != DialogueAction.ERROR, f"实体消解不应 ERROR：{result.message}"
