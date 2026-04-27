"""
创建 AI Skill 配置相关表的迁移脚本
"""
from app.core.database import engine, Base
from app.models.ai_skill import AISkill, AISkillAction, AICRUDMapping, AIEnumMapping


def create_ai_skill_tables():
    """创建 AI Skill 配置相关表"""
    print("开始创建 AI Skill 配置表...")

    # 创建表
    Base.metadata.create_all(
        bind=engine,
        tables=[
            AISkill.__table__,
            AISkillAction.__table__,
            AICRUDMapping.__table__,
            AIEnumMapping.__table__
        ]
    )

    print("AI Skill 配置表创建成功！")
    print("表名：crm_ai_skills, crm_ai_skill_actions, crm_ai_crud_mappings, crm_ai_enum_mappings")


if __name__ == "__main__":
    create_ai_skill_tables()