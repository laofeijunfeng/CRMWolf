"""企微渠道适配器

userid 解析 +企微回调验签 +企微消息发送。

参见: CRM-Docs/requirements/AI-GLUE-REQUIREMENTS.md 十一、渠道适配器 11.2
参见: CRM-Docs/plans/AI-GLUE-IMPLEMENTATION-PLAN.md Phase 5.3
"""

from typing import Optional
import hashlib
import httpx

from app.glue.channels.base import ChannelSender


class WecomChannelSender(ChannelSender):
    """企微渠道适配器"""

    channel = "wecom"

    # TODO: 从配置获取企微 corp_id 和 secret
    CORP_ID = ""
    SECRET = ""

    async def send(self, reply_token: str, text: str) -> bool:
        """发送企微消息

        Args:
            reply_token:企微 userid 或自定义 token
            text: 回复文本

        Returns:
            bool: 发送是否成功
        """
        # TODO: 实现企微消息发送 API 调用
        # 企微 API: https://developer.work.weixin.qq.com/document/path/90236

        try:
            # 简化示例：直接返回成功
            return True

        except Exception:
            return False

    async def resolve_user(self, channel_user_id: str) -> Optional[int]:
        """解析企微 userid → CRM 用户 ID

        Args:
            channel_user_id:企微 userid

        Returns:
            Optional[int]: CRM 用户 ID 或 None
        """
        # TODO: 查询 UserMapping 表
        return None

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """验证企微签名

       企微签名算法: SHA256(corpid + token + body)

        Args:
            body: 请求体
            signature:企微签名

        Returns:
            bool: 签名是否有效
        """
        # TODO: 实现企微签名验证
        #企微签名验证文档: https://developer.work.weixin.qq.com/document/path/90306

        # 简化示例：暂不验证
        return True


__all__ = ["WecomChannelSender"]