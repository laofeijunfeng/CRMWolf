"""CorrectionResolver 单元测试。"""

import pytest

from app.glue.core.corrector import CorrectionResolver, CorrectionResult
from app.glue.core.session import PendingAction


class TestCorrectionResolver:
    """CorrectionResolver 测试"""

    @pytest.fixture
    def resolver(self):
        """CorrectionResolver fixture"""
        return CorrectionResolver()

    @pytest.fixture
    def pending_action(self):
        """PendingAction fixture"""
        return PendingAction(
            action_id="act_xxx",
            intent="update_amount",
            slots={"opportunity_id": 456, "amount": 300000},
            preview_snapshot={},
        )

    def test_is_correction_true(self, resolver):
        """测试修正意图检测（True）"""
        assert resolver._is_correction("金额不对，是38万")
        assert resolver._is_correction("改成35万")
        assert resolver._is_correction("应该是40万")

    def test_is_correction_false(self, resolver):
        """测试修正意图检测（False）"""
        assert not resolver._is_correction("确认")
        assert not resolver._is_correction("取消")
        assert not resolver._is_correction("好的")

    def test_resolve_amount_correction(self, resolver, pending_action):
        """测试金额修正"""
        result = resolver.resolve("金额改成38万", pending_action)

        assert result.success
        assert result.corrected_field == "amount"
        assert result.updated_slots["amount"] == 380000

    def test_resolve_no_correction_keyword(self, resolver, pending_action):
        """测试无修正关键词"""
        result = resolver.resolve("金额是38万", pending_action)

        # 无修正关键词，应返回失败
        assert not result.success

    def test_extract_amount_with_unit(self, resolver):
        """测试提取金额（带单位）"""
        import re
        match = re.search(r"(\d+\.?\d*)\s*(万|w|元|k)?", "金额改成38万")
        value = resolver._extract_value("amount", match)

        assert value == 380000

    def test_extract_amount_without_unit(self, resolver):
        """测试提取金额（无单位）"""
        import re
        match = re.search(r"(\d+\.?\d*)\s*(万|w|元|k)?", "改成380000")
        value = resolver._extract_value("amount", match)

        assert value == 380000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
