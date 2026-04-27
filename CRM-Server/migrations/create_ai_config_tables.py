"""
创建 AI 配置和会话日志表的迁移脚本
"""
from app.core.database import engine, Base
from app.models.ai_config import AIConfig
from app.models.conversation_log import ConversationLog


def create_ai_config_tables():
    """创建 AI 配置相关表"""
    print("开始创建 AI 配置表...")

    # 创建表
    Base.metadata.create_all(bind=engine, tables=[AIConfig.__table__, ConversationLog.__table__])

    print("AI 配置表创建成功！")
    print("表名：crm_ai_config, crm_conversation_logs")


if __name__ == "__main__":
    create_ai_config_tables()