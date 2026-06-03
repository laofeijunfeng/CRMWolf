"""
迁移 Skill Action 配置，添加名称查找支持

解决的问题：
- 用户提供实体名称（如商机名称）时，系统仍然要求 ID
- 赢单、详情查询、创建合同等操作无法通过名称查找实体

运行方式：
  python scripts/migrate_skill_name_lookup.py          # 执行迁移
  python scripts/migrate_skill_name_lookup.py --verify # 验证迁移结果
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud
from sqlalchemy.orm.attributes import flag_modified


# ============================================================================
# 需要更新的 Action 配置
# ============================================================================
ACTION_UPDATES = [
    # 1. OpportunitySkill.win - 赢单操作，支持商机名称查找
    {
        "skill_name": "OpportunitySkill",
        "action_name": "win",
        "handler_config_updates": {
            "name_lookup_field": "opportunity_name",
            "name_field": "opportunity_name"
        },
        "required_params_updates": ["opportunity_name", "actual_amount", "actual_closing_date"],
        "optional_params_updates": ["opportunity_id"]
    },

    # 2. OpportunitySkill.detail - 商机详情查询，支持名称查找
    {
        "skill_name": "OpportunitySkill",
        "action_name": "detail",
        "handler_config_updates": {
            "name_lookup_field": "opportunity_name",
            "name_field": "opportunity_name"
        },
        "required_params_updates": ["opportunity_name"],
        "optional_params_updates": ["opportunity_id"]
    },

    # 3. LeadSkill.detail - 线索详情查询，支持名称查找
    {
        "skill_name": "LeadSkill",
        "action_name": "detail",
        "handler_config_updates": {
            "name_lookup_field": "lead_name",
            "name_field": "lead_name"
        },
        "required_params_updates": ["lead_name"],
        "optional_params_updates": ["lead_id"]
    },

    # 4. CustomerSkill.detail - 客户详情查询，支持名称查找
    {
        "skill_name": "CustomerSkill",
        "action_name": "detail",
        "handler_config_updates": {
            "name_lookup_field": "customer_name",
            "name_field": "account_name"
        },
        "required_params_updates": ["customer_name"],
        "optional_params_updates": ["customer_id"]
    },

    # 5. ContractSkill.detail - 合同详情查询，支持名称查找
    {
        "skill_name": "ContractSkill",
        "action_name": "detail",
        "handler_config_updates": {
            "name_lookup_field": "contract_name",
            "name_field": "contract_name"
        },
        "required_params_updates": ["contract_name"],
        "optional_params_updates": ["contract_id"]
    },

    # 6. ContractSkill.create - 创建合同，支持通过商机名称查找
    {
        "skill_name": "ContractSkill",
        "action_name": "create",
        "handler_config_updates": {
            "parent_lookup": {
                "parent_crud_mapping": "opportunity",
                "parent_lookup_field": "opportunity_name",
                "parent_name_field": "opportunity_name",
                "parent_result_field": "opportunity_id",
                "parent_required_status": "WON",
                "exclude_status": ["LOST"]
            }
        },
        "required_params_updates": ["opportunity_name", "contract_name", "signing_contact_id"],
        "optional_params_updates": ["opportunity_id"]
    },

    # 7. PaymentSkill.summary - 回款汇总，支持合同名称查找
    {
        "skill_name": "PaymentSkill",
        "action_name": "summary",
        "handler_config_updates": {
            "name_lookup_field": "contract_name",
            "name_field": "contract_name",
            "parent_crud_mapping": "contract"
        },
        "required_params_updates": ["contract_name"],
        "optional_params_updates": ["contract_id"]
    },
]


def migrate_name_lookup(db):
    """迁移名称查找配置"""
    print("\n=== 开始迁移名称查找配置 ===")

    migrated_count = 0
    for update in ACTION_UPDATES:
        skill_name = update["skill_name"]
        action_name = update["action_name"]

        skill = ai_skill_crud.get_by_name(db, skill_name)
        if not skill:
            print(f"  ✗ Skill {skill_name} 不存在，跳过")
            continue

        action = ai_skill_action_crud.get_by_skill_and_action(db, skill.id, action_name)
        if not action:
            print(f"  ✗ Action {skill_name}.{action_name} 不存在，跳过")
            continue

        # 更新 handler_config
        handler_config = action.handler_config or {}
        handler_config_updates = update.get("handler_config_updates", {})
        for key, value in handler_config_updates.items():
            handler_config[key] = value

        # 更新 required_params
        required_params_updates = update.get("required_params_updates")
        if required_params_updates:
            action.required_params = required_params_updates

        # 更新 optional_params
        optional_params_updates = update.get("optional_params_updates")
        if optional_params_updates:
            action.optional_params = optional_params_updates

        # 保存更新 - 使用 flag_modified 确保 SQLAlchemy 检测到 JSON 字段变更
        action.handler_config = handler_config
        flag_modified(action, "handler_config")
        db.commit()

        migrated_count += 1
        print(f"  ✓ 更新 Action: {skill_name}.{action_name}")
        if handler_config_updates:
            print(f"    handler_config 添加: {list(handler_config_updates.keys())}")
        if required_params_updates:
            print(f"    required_params: {required_params_updates}")

    print(f"\n=== 迁移完成: {migrated_count}/{len(ACTION_UPDATES)} ===")
    return migrated_count


def verify_migration(db):
    """验证迁移结果"""
    print("\n=== 验证迁移结果 ===")

    for update in ACTION_UPDATES:
        skill_name = update["skill_name"]
        action_name = update["action_name"]

        skill = ai_skill_crud.get_by_name(db, skill_name)
        if not skill:
            print(f"  ✗ {skill_name}.{action_name}: Skill 不存在")
            continue

        action = ai_skill_action_crud.get_by_skill_and_action(db, skill.id, action_name)
        if not action:
            print(f"  ✗ {skill_name}.{action_name}: Action 不存在")
            continue

        handler_config = action.handler_config or {}
        handler_config_updates = update.get("handler_config_updates", {})

        errors = []
        for key in handler_config_updates.keys():
            if key not in handler_config:
                errors.append(f"缺少配置: {key}")

        if errors:
            print(f"  ✗ {skill_name}.{action_name}: {', '.join(errors)}")
        else:
            # 检查 name_lookup_field 是否正确设置
            name_lookup = handler_config.get("name_lookup_field")
            if name_lookup:
                print(f"  ✓ {skill_name}.{action_name}: 支持名称查找 ({name_lookup})")
            elif handler_config.get("parent_lookup"):
                parent_lookup = handler_config.get("parent_lookup")
                parent_lookup_field = parent_lookup.get("parent_lookup_field")
                print(f"  ✓ {skill_name}.{action_name}: 支持父实体名称查找 ({parent_lookup_field})")
            else:
                print(f"  ⚠ {skill_name}.{action_name}: 未配置名称查找")


def main():
    """执行迁移"""
    import argparse

    parser = argparse.ArgumentParser(description="迁移 Skill 名称查找配置")
    parser.add_argument("--verify", action="store_true", help="仅验证迁移结果")
    args = parser.parse_args()

    db = SessionLocal()

    try:
        if args.verify:
            verify_migration(db)
        else:
            print("=" * 50)
            print("CRMWolf Skill 名称查找配置迁移")
            print("=" * 50)
            migrate_name_lookup(db)
            verify_migration(db)

    except Exception as e:
        print(f"\n✗ 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()