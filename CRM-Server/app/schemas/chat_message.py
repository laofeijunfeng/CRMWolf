"""
聊天消息 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional


class ChatMessageRequest(BaseModel):
    """聊天消息请求（通用接口）"""
    channel_user_id: str = Field(..., description="渠道用户标识（飞书open_id/钉钉userId等）")
    channel_type: str = Field(default="feishu", description="渠道类型：feishu/dingtalk/wechat/slack")
    msg_type: str = Field(default="text", description="消息类型（固定为text）")
    content: str = Field(..., min_length=1, max_length=1000, description="文本内容")
    timestamp: int = Field(..., description="时间戳")


class ChatReplyData(BaseModel):
    """聊天回复数据"""
    reply_text: str = Field(..., description="纯文本回复内容")


class ChatMessageResponse(BaseModel):
    """聊天消息响应"""
    code: int = Field(default=0, description="响应码（0=成功）")
    message: str = Field(default="success", description="提示信息")
    data: Optional[ChatReplyData] = Field(None, description="回复数据")