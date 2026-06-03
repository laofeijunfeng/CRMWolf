"""PreviewRenderer 单元测试

参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 6.3
"""

import pytest

from app.glue.core.renderer import PreviewRenderer


class TestPreviewRenderer:
    """PreviewRenderer 测试"""

    @pytest.fixture
    def renderer(self):
        """PreviewRenderer fixture"""
        return PreviewRenderer()

    def test_render_update_amount(self, renderer):
        """测试渲染 update_amount 预览"""
        plan = {
            "action_type": "update_amount",
            "description": "更新商机金额",
            "changes": [
                {"field": "amount", "to_value": 350000, "from_value": 300000}
            ],
        }
        entity_info = {
            "name": "CRM项目升级",
            "id": 456,
            "type": "Opportunity",
        }

        text = renderer.render(plan, entity_info)

        assert "⏱ 预览：更新商机金额" in text
        assert "商机：CRM项目升级（#456）" in text
        assert "金额" in text
        assert "30万" in text or "300,000" in text
        assert "35万" in text or "350,000" in text

    def test_render_receipt(self, renderer):
        """测试渲染执行回执"""
        result = {"opportunity_id": 456, "amount": 350000}
        text = renderer.render_receipt("update_amount", result)

        assert "✅" in text
        assert "已完成" in text

    def test_render_error_permission_denied(self, renderer):
        """测试渲染权限拒绝错误"""
        text = renderer.render_error("AI_PERMISSION_DENIED", "")

        assert "❌" in text
        assert "没有权限" in text

    def test_format_amount_large(self, renderer):
        """测试金额格式化（大金额）"""
        text = renderer._format_amount(350000)
        assert "35万" in text or "350,000" in text

    def test_format_amount_small(self, renderer):
        """测试金额格式化（小金额）"""
        text = renderer._format_amount(5000)
        assert "5,000" in text or "5000" in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])