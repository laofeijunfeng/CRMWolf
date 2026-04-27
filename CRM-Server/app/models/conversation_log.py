"""
会话日志模型
"""
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from app.core.database import Base


class ConversationLog(Base):
    """会话日志模型"""
    __tablename__ = "crm_conversation_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, comment="CRM用户ID")
    channel_user_id = Column(String(100), index=True, comment="渠道用户标识（飞书open_id/钉钉userId等）")
    channel_type = Column(String(20), default="feishu", comment="渠道类型：feishu/dingtalk/wechat/slack")
    request_text = Column(String(1000), comment="用户请求文本")
    ai_skill = Column(String(50), comment="AI匹配的Skill名称")
    ai_action = Column(String(50), comment="AI匹配的Action名称")
    ai_params = Column(JSON, comment="AI解析的参数")
    ai_reply_text = Column(String(500), comment="AI返回的追问/提示文本")
    execution_result = Column(String(1000), comment="Skill执行结果")
    status = Column(String(20), default="PENDING", comment="状态：PENDING/SUCCESS/FAILED/PARAM_MISSING")
    error_message = Column(String(500), comment="错误信息")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    def __repr__(self):
        return f"<ConversationLog(id={self.id}, channel_user_id={self.channel_user_id}, status={self.status})>"