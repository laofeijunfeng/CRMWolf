"""
初始化 AI Action 参数定义数据

为关键 Action（如创建线索、创建商机）添加参数定义，用于动态表单渲染

运行方式：
  python scripts/seed_action_params.py          # 执行初始化
  python scripts/seed_action_params.py --verify # 验证数据完整性
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.crud.ai_skill import ai_skill_crud, ai_skill_action_crud, ai_action_param_crud
from app.models.ai_skill import AIActionParam


# ============================================================================
# Action 参数定义数据
# ============================================================================
ACTION_PARAMS_DATA = {
    # LeadSkill.create 参数定义
    "LeadSkill.create": [
        {
            "param_name": "lead_name",
            "label": "线索名称",
            "param_type": "text",
            "required": 1,
            "placeholder": "请输入线索名称，如：某某公司采购意向",
            "sort_order": 1
        },
        {
            "param_name": "source",
            "label": "来源",
            "param_type": "select",
            "required": 1,
            "placeholder": "请选择线索来源",
            "options": [
                {"value": "ONLINE_REGISTER", "label": "线上注册"},
                {"value": "MARKETING_ACTIVITY", "label": "市场活动"},
                {"value": "REFERRAL", "label": "客户推荐"},
                {"value": "COLD_CALL", "label": "电话营销"},
                {"value": "WEBSITE_INQUIRY", "label": "网站咨询"},
                {"value": "EXHIBITION", "label": "展会"},
                {"value": "OTHER", "label": "其他"}
            ],
            "sort_order": 2
        },
        {
            "param_name": "city",
            "label": "城市",
            "param_type": "text",
            "required": 1,
            "placeholder": "请输入城市名称，如：北京、上海",
            "sort_order": 3
        },
        {
            "param_name": "contact_name",
            "label": "联系人姓名",
            "param_type": "text",
            "required": 1,
            "placeholder": "请输入联系人姓名",
            "sort_order": 4
        },
        {
            "param_name": "contact_phone",
            "label": "联系电话",
            "param_type": "text",
            "required": 1,
            "placeholder": "请输入联系电话",
            "sort_order": 5
        },
        {
            "param_name": "company_scale",
            "label": "团队规模",
            "param_type": "select",
            "required": 0,
            "placeholder": "请选择团队规模",
            "options": [
                {"value": "SCALE_1_50", "label": "1-50人"},
                {"value": "SCALE_51_200", "label": "51-200人"},
                {"value": "SCALE_201_500", "label": "201-500人"},
                {"value": "SCALE_501_1000", "label": "501-1000人"},
                {"value": "SCALE_1000_PLUS", "label": "1000人以上"}
            ],
            "sort_order": 6
        }
    ],

    # OpportunitySkill.create 参数定义
    "OpportunitySkill.create": [
        {
            "param_name": "customer_name",
            "label": "客户名称",
            "param_type": "text",
            "required": 1,
            "placeholder": "请输入客户名称",
            "sort_order": 1
        },
        {
            "param_name": "total_amount",
            "label": "商机金额",
            "param_type": "number",
            "required": 1,
            "placeholder": "请输入商机金额（元）",
            "sort_order": 2
        },
        {
            "param_name": "user_count",
            "label": "用户数量",
            "param_type": "number",
            "required": 1,
            "placeholder": "请输入预计用户数量",
            "sort_order": 3
        },
        {
            "param_name": "expected_closing_date",
            "label": "预计成交日期",
            "param_type": "date",
            "required": 1,
            "placeholder": "请选择预计成交日期",
            "sort_order": 4
        },
        {
            "param_name": "purchase_type",
            "label": "采购类型",
            "param_type": "select",
            "required": 0,
            "placeholder": "请选择采购类型",
            "options": [
                {"value": "NEW", "label": "新购"},
                {"value": "RENEWAL", "label": "续购"},
                {"value": "EXPANSION", "label": "增购"}
            ],
            "default_value": "NEW",
            "sort_order": 5
        },
        {
            "param_name": "license_type",
            "label": "授权模式",
            "param_type": "select",
            "required": 0,
            "placeholder": "请选择授权模式",
            "options": [
                {"value": "SUBSCRIPTION", "label": "订阅"},
                {"value": "PERPETUAL", "label": "买断"}
            ],
            "default_value": "SUBSCRIPTION",
            "sort_order": 6
        }
    ],

    # LeadSkill.follow_up 参数定义
    "LeadSkill.follow_up": [
        {
            "param_name": "lead_name",
            "label": "线索名称",
            "param_type": "text",
            "required": 1,
            "placeholder": "请输入线索名称",
            "sort_order": 1
        },
        {
            "param_name": "content",
            "label": "跟进内容",
            "param_type": "textarea",
            "required": 1,
            "placeholder": "请输入跟进内容",
            "sort_order": 2
        },
        {
            "param_name": "method",
            "label": "跟进方式",
            "param_type": "select",
            "required": 1,
            "placeholder": "请选择跟进方式",
            "options": [
                {"value": "PHONE", "label": "电话"},
                {"value": "WECHAT", "label": "微信"},
                {"value": "VISIT", "label": "拜访"},
                {"value": "EMAIL", "label": "邮件"},
                {"value": "OTHER", "label": "其他"}
            ],
            "sort_order": 3
        },
        {
            "param_name": "next_follow_time",
            "label": "下次跟进时间",
            "param_type": "date",
            "required": 0,
            "placeholder": "请选择下次跟进时间",
            "sort_order": 4
        }
    ],

    # CustomerSkill.follow_up 参数定义
    "CustomerSkill.follow_up": [
        {
            "param_name": "customer_name",
            "label": "客户名称",
            "param_type": "text",
            "required": 1,
            "placeholder": "请输入客户名称",
            "sort_order": 1
        },
        {
            "param_name": "content",
            "label": "跟进内容",
            "param_type": "textarea",
            "required": 1,
            "placeholder": "请输入跟进内容",
            "sort_order": 2
        },
        {
            "param_name": "method",
            "label": "跟进方式",
            "param_type": "select",
            "required": 1,
            "placeholder": "请选择跟进方式",
            "options": [
                {"value": "PHONE", "label": "电话"},
                {"value": "WECHAT", "label": "微信"},
                {"value": "VISIT", "label": "拜访"},
                {"value": "EMAIL", "label": "邮件"},
                {"value": "OTHER", "label": "其他"}
            ],
            "sort_order": 3
        },
        {
            "param_name": "next_follow_time",
            "label": "下次跟进时间",
            "param_type": "date",
            "required": 0,
            "placeholder": "请选择下次跟进时间",
            "sort_order": 4
        }
    ]
}


def seed_action_params(db):
    """初始化 Action 参数定义数据"""
    print("\n=== 开始初始化 Action 参数定义数据 ===")

    total_count = 0

    for skill_action_key, params_data in ACTION_PARAMS_DATA.items():
        skill_name, action_name = skill_action_key.split(".", 1)

        # 获取 Skill
        skill = ai_skill_crud.get_by_name(db, skill_name)
        if not skill:
            print(f"  ✗ Skill {skill_name} 不存在，跳过")
            continue

        # 获取 Action
        action = ai_skill_action_crud.get_by_skill_and_action(db, skill.id, action_name)
        if not action:
            print(f"  ✗ Action {skill_name}.{action_name} 不存在，跳过")
            continue

        # 删除已有的参数定义（重新初始化）
        ai_action_param_crud.delete_by_action_id(db, action.id)

        # 批量创建参数定义
        for param_data in params_data:
            param_create_data = {
                "action_id": action.id,
                **param_data
            }
            ai_action_param_crud.create(db, param_create_data)
            total_count += 1

        print(f"  ✓ 创建 {skill_name}.{action_name} 参数定义: {len(params_data)} 个")

    print(f"=== Action 参数定义初始化完成: {total_count} 个 ===")
    return total_count


def verify_params(db):
    """验证参数定义数据"""
    print("\n=== 开始验证参数定义数据 ===")

    errors = []

    for skill_action_key, params_data in ACTION_PARAMS_DATA.items():
        skill_name, action_name = skill_action_key.split(".", 1)

        skill = ai_skill_crud.get_by_name(db, skill_name)
        if not skill:
            errors.append(f"Skill {skill_name} 不存在")
            continue

        action = ai_skill_action_crud.get_by_skill_and_action(db, skill.id, action_name)
        if not action:
            errors.append(f"Action {skill_name}.{action_name} 不存在")
            continue

        params = ai_action_param_crud.get_by_action_id(db, action.id)
        if len(params) != len(params_data):
            errors.append(
                f"{skill_name}.{action_name} 参数数量不匹配: "
                f"期望 {len(params_data)}, 实际 {len(params)}"
            )
        else:
            print(f"  ✓ {skill_name}.{action_name}: {len(params)} 个参数")

    if errors:
        print("\n=== 验证失败 ===")
        for error in errors:
            print(f"  ✗ {error}")
        return False
    else:
        print("\n=== 验证成功 ===")
        return True


def main():
    """执行初始化"""
    import argparse

    parser = argparse.ArgumentParser(description="初始化 Action 参数定义数据")
    parser.add_argument("--verify", action="store_true", help="仅验证数据完整性")
    args = parser.parse_args()

    db = SessionLocal()

    try:
        if args.verify:
            success = verify_params(db)
            sys.exit(0 if success else 1)
        else:
            print("=" * 50)
            print("CRMWolf Action 参数定义初始化脚本")
            print("=" * 50)

            # 执行初始化
            param_count = seed_action_params(db)

            # 验证
            print("\n" + "=" * 50)
            verify_params(db)

            print("\n" + "=" * 50)
            print(f"初始化完成: {param_count} 个参数定义")
            print("=" * 50)

    except Exception as e:
        print(f"\n✗ 初始化失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()