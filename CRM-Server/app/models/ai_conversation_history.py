"""
AI 对话历史模型

用于持久化存储用户的 AI 助手对话记录
"""
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, JSON, Index, Text
from sqlalchemy.sql import func
from app.core.database import Base


class AIConversationHistory(Base):
    """AI 对话历史模型"""
    __tablename__ = "crm_ai_conversation_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    team_id = Column(BigInteger, nullable=False, index=True, comment="团队ID")
    user_id = Column(Integer, nullable=False, index=True, comment="用户ID")
    title = Column(String(200), nullable=False, comment="对话标题（自动提取）")
    summary = Column(Text, comment="对话摘要")
    action_type = Column(String(50), comment="操作类型：create_customer, win_opportunity 等")
    entity_type = Column(String(20), comment="实体类型：customer, opportunity, lead, contract")
    entity_id = Column(BigInteger, comment="实体ID")
    messages = Column(JSON, nullable=False, default=list, comment="对话消息列表")
    status = Column(String(20), default="active", comment="状态：active, archived, deleted")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index('idx_ai_conversation_team_user', 'team_id', 'user_id'),
        Index('idx_ai_conversation_created_at', 'created_at'),
        {'comment': 'AI 对话历史表'}
    )

    def __repr__(self):
        return f"<AIConversationHistory(id={self.id}, title={self.title}, team_id={self.team_id})>"