"""
为跟进 Skill 添加 next_action 参数

执行方式：
cd CRM-Server && python3 scripts/add_next_action_to_skill.py
"""

import sys
sys.path.insert(0, '/Users/eddie/Code/CRMWolf/CRM-Server')

from app.core.database import SessionLocal
from app.models.ai_skill import AISkill, AISkillAction


def migrate():
    db = SessionLocal()

    try:
        # 更新 LeadSkill.follow_up
        skill = db.query(AISkill).filter(AISkill.skill_name == 'LeadSkill').first()
        if skill:
            action = db.query(AISkillAction).filter(
                AISkillAction.skill_id == skill.id,
                AISkillAction.action_name == 'follow_up'
            ).first()
            if action:
                current_optional = action.optional_params or []
                if 'next_action' not in current_optional:
                    current_optional.append('next_action')
                    action.optional_params = current_optional
                    print(f"已为 LeadSkill.follow_up 添加 next_action 参数")
                else:
                    print("LeadSkill.follow_up 已包含 next_action 参数")

        # 更新 CustomerSkill.follow_up
        skill2 = db.query(AISkill).filter(AISkill.skill_name == 'CustomerSkill').first()
        if skill2:
            action = db.query(AISkillAction).filter(
                AISkillAction.skill_id == skill2.id,
                AISkillAction.action_name == 'follow_up'
            ).first()
            if action:
                current_optional = action.optional_params or []
                if 'next_action' not in current_optional:
                    current_optional.append('next_action')
                    action.optional_params = current_optional
                    print(f"已为 CustomerSkill.follow_up 添加 next_action 参数")
                else:
                    print("CustomerSkill.follow_up 已包含 next_action 参数")

        db.commit()
        print("迁移完成！")

    except Exception as e:
        db.rollback()
        print(f"迁移失败: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()