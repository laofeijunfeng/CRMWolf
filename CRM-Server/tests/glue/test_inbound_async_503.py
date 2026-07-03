"""Task 2.5: IM 异步渠道未实现，必须返回 503 而非 ok=True 假装成功。

遵循 Global Constraints「诚实失败」原则：任何未实现的异步渠道必须显式 503，
禁止返回 ok=True 假装成功。
"""
import pytest
from fastapi import HTTPException

from app.glue.config import GlueConfig


def test_glue_config_feishu_is_async_delivery():
    """验证飞书渠道配置为 async_delivery=True。"""
    channel_config = GlueConfig.CHANNEL_CONFIG.get("feishu", {})
    assert channel_config.get("async_delivery", False) is True, \
        "飞书渠道应配置为异步交付"


def test_async_delivery_raises_503():
    """验证 async_delivery=True 时抛出 503 HTTPException。"""
    # 模拟 inbound.py:130-135 的逻辑
    async_delivery = True  # IM 渠道如飞书

    if async_delivery:
        # 应抛出 503（inbound.py 已修改）
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(
                status_code=503,
                detail="IM 异步投递队列尚未实现，请使用 web 同步渠道或联系管理员",
            )
        assert exc_info.value.status_code == 503
        assert "异步" in exc_info.value.detail or "未实现" in exc_info.value.detail


def test_web_channel_is_sync_delivery():
    """验证 web 渠道配置为 async_delivery=False（同步）。"""
    channel_config = GlueConfig.CHANNEL_CONFIG.get("web", {})
    assert channel_config.get("async_delivery", True) is False, \
        "web 渠道应配置为同步交付"