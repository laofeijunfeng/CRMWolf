"""DialogueEngine 单元测试。"""

import pytest

from app.glue.core.dialogue import DialogueEngine, DialogueAction, DialogueResult
from app.glue.core.session import GlueSession, PendingAction
from app.glue.config import SessionMode


class TestDialogueEngine:
    """DialogueEngine 测试"""

    @pytest.fixture
    def engine(self):
        """DialogueEngine fixture"""
        return DialogueEngine()

    @pytest.fixture
    def idle_session(self):
        """IDLE Session fixture"""
        return GlueSession(
            tenant_id="tenant_001",
            crm_user_id=123,
            mode=SessionMode.IDLE,
        )

    @pytest.fixture
    def preview_session(self):
        """PREVIEW Session fixture"""
        return GlueSession(
            tenant_id="tenant_001",
            crm_user_id=123,
            mode=SessionMode.PREVIEW,
            pending=PendingAction(
                action_id="act_xxx",
                intent="update_amount",
                slots={"opportunity_id": 456, "amount": 350000},
                preview_snapshot={},
                expires_at=9999999999,
            ),
        )

    @pytest.mark.asyncio
    async def test_handle_idle(self, engine, idle_session):
        """测试 IDLE 状态处理"""
        result = await engine.dispatch(idle_session, "给#456加跟进")

        assert result.action == DialogueAction.PARSE_INTENT
        assert result.success

    @pytest.mark.asyncio
    async def test_handle_preview_confirm(self, engine, preview_session):
        """测试 PREVIEW 状态处理（确认）"""
        result = await engine.dispatch(preview_session, "确认")

        assert result.action == DialogueAction.EXECUTE_ACTION
        assert result.next_mode == SessionMode.EXECUTING

    @pytest.mark.asyncio
    async def test_handle_preview_cancel(self, engine, preview_session):
        """测试 PREVIEW 状态处理（取消）"""
        result = await engine.dispatch(preview_session, "取消")

        assert result.action == DialogueAction.CANCEL_ACTION
        assert result.next_mode == SessionMode.IDLE

    @pytest.mark.asyncio
    async def test_handle_preview_correction(self, engine, preview_session):
        """测试 PREVIEW 状态处理（修正）"""
        result = await engine.dispatch(preview_session, "金额改成38万")

        assert result.action == DialogueAction.CORRECT_ACTION
        assert result.next_mode == SessionMode.PREVIEW

    def test_is_cancel(self, engine):
        """测试取消检测"""
        assert engine._is_cancel("取消")
        assert engine._is_cancel("算了")
        assert engine._is_cancel("不用了")
        assert not engine._is_cancel("确认")

    def test_is_confirm(self, engine):
        """测试确认检测"""
        assert engine._is_confirm("确认")
        assert engine._is_confirm("确定")
        assert engine._is_confirm("好的")
        assert not engine._is_confirm("取消")

    def test_is_correction(self, engine):
        """测试修正检测"""
        assert engine._is_correction("不对")
        assert engine._is_correction("错了")
        assert engine._is_correction("改成")
        assert not engine._is_correction("确认")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
