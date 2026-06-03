"""IntentDetector 单元测试

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 6.3
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.glue.core.intent import IntentDetector, IntentResult
from app.glue.core.session import GlueSession, RecentEntities


class TestIntentDetector:
    """IntentDetector 测试"""

    @pytest.fixture
    def detector(self):
        """IntentDetector fixture"""
        return IntentDetector()

    @pytest.fixture
    def session_with_entities(self):
        """Session with recent entities"""
        return GlueSession(
            tenant_id="tenant_001",
            crm_user_id=123,
            recent_entities=RecentEntities(
                customer_id=101,
                opportunity_id=456,
            ),
        )

    @pytest.mark.asyncio
    async def test_detect_intent(self, detector):
        """测试意图检测"""
        # TODO: 实现 mock httpx 调用
        pass

    @pytest.mark.asyncio
    async def test_merge_with_session(self, detector, session_with_entities):
        """测试 Session 补全"""
        entities = {"text": "跟进一下这个客户"}
        slots = detector._merge_with_session(entities, session_with_entities)

        # 应补全 customer_id
        assert slots.get("customer_id") == 101

    def test_check_missing_fields_create_follow_up(self, detector):
        """测试缺失字段检查（create_follow_up）"""
        slots = {"customer_id": 101}  # 缺少 content
        missing = detector._check_missing_fields("create_follow_up", slots)

        assert "content" in missing

    def test_check_missing_fields_all_filled(self, detector):
        """测试缺失字段检查（所有字段已填充）"""
        slots = {"customer_id": 101, "content": "跟进内容"}
        missing = detector._check_missing_fields("create_follow_up", slots)

        assert len(missing) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])