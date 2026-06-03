"""ActionPlanner 单元测试

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 6.3
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.glue.core.planner import ActionPlanner, ActionPlanResult


class TestActionPlanner:
    """ActionPlanner 测试"""

    @pytest.fixture
    def planner(self):
        """ActionPlanner fixture"""
        return ActionPlanner()

    def test_intent_action_map(self, planner):
        """测试 Intent → Action 映射"""
        assert planner.INTENT_ACTION_MAP["create_follow_up"] == "/ai/actions/create-follow-up"
        assert planner.INTENT_ACTION_MAP["win_opportunity"] == "/ai/actions/win-opportunity"

    @pytest.mark.asyncio
    async def test_plan_create_follow_up(self, planner):
        """测试规划 create_follow_up"""
        # TODO: 实现 mock httpx 调用
        pass

    def test_build_request_create_follow_up(self, planner):
        """测试请求参数组装（create_follow_up）"""
        slots = {"customer_id": 101, "content": "跟进内容"}
        request = planner._build_request("create_follow_up", slots)

        assert request["preview"] is True
        assert request["customer_id"] == 101
        assert request["content"] == "跟进内容"

    def test_build_request_update_amount(self, planner):
        """测试请求参数组装（update_amount）"""
        slots = {"opportunity_id": 456, "amount": 350000}
        request = planner._build_request("update_amount", slots)

        assert request["preview"] is True
        assert request["opportunity_id"] == 456
        assert request["amount"] == 350000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])