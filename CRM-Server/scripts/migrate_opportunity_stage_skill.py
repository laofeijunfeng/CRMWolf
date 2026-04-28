"""
迁移脚本：添加商机阶段管理 Skill

包含以下 Action：
1. query_stage - 查询阶段信息
2. advance_stage - 推进阶段
3. set_procurement_method - 设置采购方式
4. rollback_stage - 回退阶段
5. query_stage_history - 查询阶段历史
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.ai_skill import AISkill, AISkillAction
from datetime import datetime


def migrate_opportunity_stage_skill(db: Session):
    """迁移商机阶段管理 Skill"""

    # 检查是否已存在
    existing_skill = db.query(AISkill).filter(
        AISkill.skill_name == "OpportunityStageSkill"
    ).first()

    if existing_skill:
        print("OpportunityStageSkill 已存在，跳过创建")
        skill_id = existing_skill.id
    else:
        # 创建 Skill
        skill = AISkill(
            skill_name="OpportunityStageSkill",
            display_name="商机阶段管理",
            description="查询商机阶段状态、推进/回退阶段、设置采购方式",
            module_type="opportunity",
            is_active=1,
            sort_order=3,  # 在 OpportunitySkill 之后
            created_time=datetime.now(),
            updated_time=datetime.now()
        )
        db.add(skill)
        db.flush()
        skill_id = skill.id
        print(f"创建 Skill: OpportunityStageSkill (ID: {skill_id})")

    # 创建 Actions
    actions_config = [
        {
            "action_name": "query_stage",
            "display_name": "查询阶段",
            "description": "查询商机当前阶段、可推进阶段列表",
            "handler_type": "StageQueryHandler",
            "handler_config": {
                "crud_mapping": "opportunity",
                "name_lookup_field": "opportunity_name",
                "name_field": "opportunity_name",
                "query_type": "current",
                "customer_lookup": {
                    "customer_crud_mapping": "customer",
                    "customer_lookup_field": "customer_name",
                    "customer_name_field": "account_name"
                }
            },
            "required_params": [],
            "optional_params": ["opportunity_name", "opportunity_id", "customer_name"],
            "permission_code": "opportunity:view_own",
            "sort_order": 1
        },
        {
            "action_name": "advance_stage",
            "display_name": "推进阶段",
            "description": "将商机推进到下一阶段或指定阶段",
            "handler_type": "StageAdvanceHandler",
            "handler_config": {
                "crud_mapping": "opportunity",
                "name_lookup_field": "opportunity_name",
                "name_field": "opportunity_name",
                "stage_lookup_field": "target_stage_name",
                "advance_mode": "forward",
                "default_action": "next",
                "exclude_status": ["WON", "LOST"],
                "support_notes": True,
                "customer_lookup": {
                    "customer_crud_mapping": "customer",
                    "customer_lookup_field": "customer_name",
                    "customer_name_field": "account_name"
                }
            },
            "required_params": [],
            "optional_params": ["opportunity_name", "opportunity_id", "customer_name", "target_stage_name", "notes"],
            "permission_code": "opportunity:edit_own",
            "sort_order": 2
        },
        {
            "action_name": "set_procurement_method",
            "display_name": "设置采购方式",
            "description": "为新商机设置采购方式，自动进入默认起始阶段",
            "handler_type": "SetProcurementMethodHandler",
            "handler_config": {
                "crud_mapping": "opportunity",
                "name_lookup_field": "opportunity_name",
                "name_field": "opportunity_name",
                "method_lookup_field": "procurement_method_name",
                "exclude_status": ["WON", "LOST"],
                "require_no_method": True,
                "customer_lookup": {
                    "customer_crud_mapping": "customer",
                    "customer_lookup_field": "customer_name",
                    "customer_name_field": "account_name"
                }
            },
            "required_params": [],
            "optional_params": ["opportunity_name", "opportunity_id", "customer_name", "procurement_method_name"],
            "permission_code": "opportunity:edit_own",
            "sort_order": 3
        },
        {
            "action_name": "rollback_stage",
            "display_name": "回退阶段",
            "description": "将商机回退到上一阶段或指定阶段",
            "handler_type": "StageAdvanceHandler",
            "handler_config": {
                "crud_mapping": "opportunity",
                "name_lookup_field": "opportunity_name",
                "name_field": "opportunity_name",
                "stage_lookup_field": "target_stage_name",
                "advance_mode": "backward",
                "default_action": "prev",
                "exclude_status": ["WON", "LOST"],
                "support_notes": True,
                "validate_rollback_history": True,
                "customer_lookup": {
                    "customer_crud_mapping": "customer",
                    "customer_lookup_field": "customer_name",
                    "customer_name_field": "account_name"
                }
            },
            "required_params": [],
            "optional_params": ["opportunity_name", "opportunity_id", "customer_name", "target_stage_name", "notes"],
            "permission_code": "opportunity:edit_own",
            "sort_order": 4
        },
        {
            "action_name": "query_stage_history",
            "display_name": "查询阶段历史",
            "description": "查询商机的阶段推进历史记录",
            "handler_type": "StageQueryHandler",
            "handler_config": {
                "crud_mapping": "opportunity",
                "name_lookup_field": "opportunity_name",
                "name_field": "opportunity_name",
                "query_type": "history",
                "customer_lookup": {
                    "customer_crud_mapping": "customer",
                    "customer_lookup_field": "customer_name",
                    "customer_name_field": "account_name"
                }
            },
            "required_params": [],
            "optional_params": ["opportunity_name", "opportunity_id", "customer_name"],
            "permission_code": "opportunity:view_own",
            "sort_order": 5
        }
    ]

    created_count = 0
    for action_config in actions_config:
        # 检查是否已存在
        existing_action = db.query(AISkillAction).filter(
            AISkillAction.skill_id == skill_id,
            AISkillAction.action_name == action_config["action_name"]
        ).first()

        if existing_action:
            print(f"Action {action_config['action_name']} 已存在，跳过创建")
            continue

        action = AISkillAction(
            skill_id=skill_id,
            action_name=action_config["action_name"],
            display_name=action_config["display_name"],
            description=action_config["description"],
            handler_type=action_config["handler_type"],
            handler_config=action_config["handler_config"],
            required_params=action_config["required_params"],
            optional_params=action_config["optional_params"],
            permission_code=action_config["permission_code"],
            result_template=None,
            is_active=1,
            sort_order=action_config["sort_order"],
            created_time=datetime.now(),
            updated_time=datetime.now()
        )
        db.add(action)
        created_count += 1
        print(f"创建 Action: {action_config['action_name']}")

    db.commit()
    print(f"\n迁移完成！创建了 {created_count} 个新 Action")


def main():
    """主函数"""
    db = SessionLocal()
    try:
        migrate_opportunity_stage_skill(db)
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()