"""
创建 AI Action 参数定义表的迁移脚本
"""
from app.core.database import engine, Base
from app.models.ai_skill import AIActionParam


def create_action_params_table():
    """创建 AI Action 参数定义表"""
    print("开始创建 AI Action 参数定义表...")

    # 创建表
    Base.metadata.create_all(
        bind=engine,
        tables=[AIActionParam.__table__]
    )

    print("AI Action 参数定义表创建成功！")
    print("表名：crm_ai_action_params")


if __name__ == "__main__":
    create_action_params_table()