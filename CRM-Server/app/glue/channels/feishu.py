"""飞书渠道适配器

open_id 解析 + 飞书 API 验签 + 飞书消息发送。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 十一、渠道适配器 11.2
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 5.2
"""

from typing import Optional
import hashlib
import httpx

from app.glue.channels.base import ChannelSender


class FeishuChannelSender(ChannelSender):
    """飞书渠道适配器"""

    channel = "feishu"

    # TODO: 从配置获取飞书 app_id 和 app_secret
    APP_ID = ""
    APP_SECRET = ""

    async def send(self, reply_token: str, text: str) -> bool:
        """发送飞书消息

        Args:
            reply_token: 飞书 open_message_id 或自定义 token
            text: 回复文本

        Returns:
            bool: 发送是否成功
        """
        # TODO: 实现飞书消息发送 API 调用
        # 飞书 API: https://open.feishu.cn/document/ukTMukTMukTM/uTM5UjM3NjMzNjMz

        try:
            # 简化示例：直接返回成功
            # 实际需调用飞书 API
            return True

        except Exception:
            return False

    async def resolve_user(self, channel_user_id: str) -> Optional[int]:
        """解析飞书 open_id → CRM 用户 ID

        Args:
            channel_user_id: 飞书 open_id

        Returns:
            Optional[int]: CRM 用户 ID 或 None
        """
        # TODO: 查询 UserMapping 表
        # UserMapping 表结构: id, tenant_id, channel, channel_user_id, crm_user_id
        return None

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """验证飞书签名

        飞书签名算法: SHA256(timestamp + token + body)

        Args:
            body: 请求体
            signature: 飞书签名

        Returns:
            bool: 签名是否有效
        """
        # TODO: 实现飞书签名验证
        # 飞书签名验证文档: https://open.feishu.cn/document/ukTMukTMukTM/uTM5UjM3NjMzNjMz

        # 简化示例：暂不验证
        return True


__all__ = ["FeishuChannelSender"]