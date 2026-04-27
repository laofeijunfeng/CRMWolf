"""
更新 lead_convert action 配置，支持名称查找

运行方式：
  python scripts/update_lead_convert_config.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud


def main():
    """更新 lead_convert action 配置"""
    db = SessionLocal()

    try:
        # 查找 LeadSkill
        skill = ai_skill_crud.get_by_name(db, "LeadSkill")
        if not skill:
            print("✗ LeadSkill 不存在")
            return

        # 查找 convert action
        action = ai_skill_action_crud.get_by_skill_and_action(db, skill.id, "convert")

        if not action:
            print("✗ lead_convert action 不存在，需要先创建")
            # 创建 convert action
            action_data = {
                "skill_id": skill.id,
                "action_name": "convert",
                "display_name": "线索转化",
                "description": "将线索转化为客户",
                "handler_type": "StatusChangeHandler",
                "handler_config": {
                    "crud_mapping": "lead",
                    "status_field": "status",
                    "target_status": "CONVERTED",
                    "name_lookup_field": "lead_name",
                    "name_field": "lead_name",
                    "exclude_status": ["CONVERTED", "INVALID"],
                    "result_template": "线索转化成功\n线索：{lead_name}\n已转化为客户"
                },
                "required_params": ["lead_name"],
                "optional_params": [],
                "permission_code": "lead:convert",
                "sort_order": 5,
                "is_active": 1
            }
            action = ai_skill_action_crud.create(db, action_data)
            print(f"✓ 创建 lead_convert action")
        else:
            # 更新 handler_config
            new_handler_config = {
                "crud_mapping": "lead",
                "status_field": "status",
                "target_status": "CONVERTED",
                "name_lookup_field": "lead_name",
                "name_field": "lead_name",
                "exclude_status": ["CONVERTED", "INVALID"],
                "result_template": "线索转化成功\n线索：{lead_name}\n已转化为客户"
            }

            # 更新 required_params
            new_required_params = ["lead_name"]

            action.handler_config = new_handler_config
            action.required_params = new_required_params
            db.commit()
            db.refresh(action)
            print(f"✓ 更新 lead_convert action 配置")

        print("\n当前配置：")
        print(f"  handler_type: {action.handler_type}")
        print(f"  handler_config: {action.handler_config}")
        print(f"  required_params: {action.required_params}")

    except Exception as e:
        print(f"✗ 更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()