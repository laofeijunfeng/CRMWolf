"""
权限码规范化迁移脚本

将所有权限码统一为三层格式：{resource}:{action}:{scope}
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal

# ============================================================================
# 需要删除的冗余权限（这些权限会被合并到其他权限）
# ============================================================================
DELETE_PERMISSIONS = [
    "customer:delete",       # 合并到 customer:delete:own
    "customer:update",       # 合并到 customer:edit:own
    "opportunity:delete",    # 合并到 opportunity:delete:own
    "opportunity:update",    # 合并到 opportunity:edit:own
    "opportunity:stage",     # 合并到 opportunity:stage:view
    "finance:view_receivables",  # 合并到 finance:receivables:view
]

# ============================================================================
# 权限更新表：需要更新的权限及其新值
# ============================================================================
PERMISSION_UPDATE = {
    # 格式: 旧权限码 -> (新权限码, 新名称, resource, action, scope)
    # scope 为 None 表示无范围限制

    # ========== 线索管理 (lead) ==========
    "lead:create": ("lead:create", "创建线索", "lead", "create", None),
    "lead:view_own": ("lead:view:own", "查看自己的线索", "lead", "view", "own"),
    "lead:view_all": ("lead:view:all", "查看所有线索", "lead", "view", "all"),
    "lead:edit_own": ("lead:edit:own", "编辑自己的线索", "lead", "edit", "own"),
    "lead:edit_all": ("lead:edit:all", "编辑所有线索", "lead", "edit", "all"),
    "lead:delete_own": ("lead:delete:own", "删除自己的线索", "lead", "delete", "own"),
    "lead:assign": ("lead:assign", "分配线索", "lead", "assign", None),
    "lead:claim": ("lead:claim", "领取线索", "lead", "claim", None),
    "lead:convert": ("lead:convert", "转化线索", "lead", "convert", None),
    "lead:return_to_pool": ("lead:return", "退回线索到公海", "lead", "return", None),
    "lead:import": ("lead:import", "导入线索", "lead", "import", None),
    "lead:follow_up:create": ("lead:follow_up:create", "创建线索跟进", "lead", "follow_up_create", None),
    "lead:list": ("lead:api:list", "API 线索列表", "lead", "api_list", None),
    "lead:read": ("lead:api:read", "API 线索详情", "lead", "api_read", None),

    # ========== 客户管理 (customer) ==========
    "customer:create": ("customer:create", "创建客户", "customer", "create", None),
    "customer:view:own": ("customer:view:own", "查看自己的客户", "customer", "view", "own"),
    "customer:view:all": ("customer:view:all", "查看所有客户", "customer", "view", "all"),
    "customer:edit_own": ("customer:edit:own", "编辑自己的客户", "customer", "edit", "own"),
    "customer:edit_all": ("customer:edit:all", "编辑所有客户", "customer", "edit", "all"),
    "customer:delete_own": ("customer:delete:own", "删除自己的客户", "customer", "delete", "own"),
    "customer:assign": ("customer:assign", "分配客户", "customer", "assign", None),
    "customer:claim": ("customer:claim", "领取客户", "customer", "claim", None),
    "customer:return_to_pool": ("customer:return", "退回客户到公海", "customer", "return", None),
    "customer:contact:create": ("customer:contact:create", "创建客户联系人", "customer", "contact_create", None),
    "customer:contact:edit": ("customer:contact:edit", "编辑客户联系人", "customer", "contact_edit", None),
    "customer:contact:delete": ("customer:contact:delete", "删除客户联系人", "customer", "contact_delete", None),
    "customer:follow_up:create": ("customer:follow_up:create", "创建客户跟进", "customer", "follow_up_create", None),
    "customer:follow_up:edit": ("customer:follow_up:edit", "编辑客户跟进", "customer", "follow_up_edit", None),
    "customer:follow_up:delete": ("customer:follow_up:delete", "删除客户跟进", "customer", "follow_up_delete", None),
    "customer:list": ("customer:api:list", "API 客户列表", "customer", "api_list", None),
    "customer:read": ("customer:api:read", "API 客户详情", "customer", "api_read", None),

    # ========== 商机管理 (opportunity) ==========
    "opportunity:create": ("opportunity:create", "创建商机", "opportunity", "create", None),
    "opportunity:view:own": ("opportunity:view:own", "查看自己的商机", "opportunity", "view", "own"),
    "opportunity:view:all": ("opportunity:view:all", "查看所有商机", "opportunity", "view", "all"),
    "opportunity:edit_own": ("opportunity:edit:own", "编辑自己的商机", "opportunity", "edit", "own"),
    "opportunity:edit_all": ("opportunity:edit:all", "编辑所有商机", "opportunity", "edit", "all"),
    "opportunity:delete_own": ("opportunity:delete:own", "删除自己的商机", "opportunity", "delete", "own"),
    "opportunity:assign": ("opportunity:assign", "分配商机", "opportunity", "assign", None),
    "opportunity:win": ("opportunity:win", "标记商机赢单", "opportunity", "win", None),
    "opportunity:lose": ("opportunity:lose", "标记商机输单", "opportunity", "lose", None),
    "opportunity:stage:create": ("opportunity:stage:create", "创建商机阶段", "opportunity", "stage_create", None),
    "opportunity:stage:update": ("opportunity:stage:edit", "编辑商机阶段", "opportunity", "stage_edit", None),
    "opportunity:stage:delete": ("opportunity:stage:delete", "删除商机阶段", "opportunity", "stage_delete", None),
    "opportunity:stage:manage": ("opportunity:stage:manage", "管理商机阶段", "opportunity", "stage_manage", None),
    "opportunity:analytics:view": ("opportunity:analytics:view", "查看商机分析", "opportunity", "analytics_view", None),
    "opportunity:list": ("opportunity:api:list", "API 商机列表", "opportunity", "api_list", None),
    "opportunity:read": ("opportunity:api:read", "API 商机详情", "opportunity", "api_read", None),

    # ========== 合同管理 (contract) ==========
    "contract:create": ("contract:create", "创建合同", "contract", "create", None),
    "contract:view_own": ("contract:view:own", "查看自己的合同", "contract", "view", "own"),
    "contract:view_all": ("contract:view:all", "查看所有合同", "contract", "view", "all"),
    "contract:edit_own": ("contract:edit:own", "编辑自己的合同", "contract", "edit", "own"),
    "contract:edit_all": ("contract:edit:all", "编辑所有合同", "contract", "edit", "all"),
    "contract:delete_own": ("contract:delete:own", "删除自己的合同", "contract", "delete", "own"),
    "contract:approve_own": ("contract:approve:own", "审批自己创建的合同", "contract", "approve", "own"),
    "contract:approve_all": ("contract:approve:all", "审批所有合同", "contract", "approve", "all"),
    "contract:submit_approval": ("contract:submit", "提交合同审批", "contract", "submit", None),
    "contract:cancel_approval": ("contract:cancel", "撤回合同审批", "contract", "cancel", None),
    "contract:list": ("contract:api:list", "API 合同列表", "contract", "api_list", None),
    "contract:read": ("contract:api:read", "API 合同详情", "contract", "api_read", None),

    # ========== 回款管理 (payment) ==========
    "payment:plan:create": ("payment:plan:create", "创建回款计划", "payment", "plan_create", None),
    "payment:plan:edit": ("payment:plan:edit", "编辑回款计划", "payment", "plan_edit", None),
    "payment:plan:delete": ("payment:plan:delete", "删除回款计划", "payment", "plan_delete", None),
    "payment:plan:view_own": ("payment:plan:view:own", "查看自己的回款计划", "payment", "plan_view", "own"),
    "payment:plan:view_all": ("payment:plan:view:all", "查看所有回款计划", "payment", "plan_view", "all"),
    "payment:view_own": ("payment:view:own", "查看自己的回款", "payment", "view", "own"),
    "payment:view_all": ("payment:view:all", "查看所有回款", "payment", "view", "all"),
    "payment:register": ("payment:register", "登记回款", "payment", "register", None),
    "payment:confirm": ("payment:confirm", "确认回款入账", "payment", "confirm", None),
    "payment:create": ("payment:api:create", "API 创建回款", "payment", "api_create", None),
    "payment:list": ("payment:api:list", "API 回款列表", "payment", "api_list", None),
    "payment:read": ("payment:api:read", "API 回款详情", "payment", "api_read", None),

    # ========== 发票管理 (invoice) ==========
    "invoice:create": ("invoice:create", "创建发票申请", "invoice", "create", None),
    "invoice:view_own": ("invoice:view:own", "查看自己的发票", "invoice", "view", "own"),
    "invoice:view_all": ("invoice:view:all", "查看所有发票", "invoice", "view", "all"),
    "invoice:approve": ("invoice:approve", "审批发票申请", "invoice", "approve", None),
    "invoice:mark_issued": ("invoice:issue", "标记发票已开票", "invoice", "issue", None),
    "invoice:list": ("invoice:api:list", "API 发票列表", "invoice", "api_list", None),
    "invoice:read": ("invoice:api:read", "API 发票详情", "invoice", "api_read", None),

    # ========== 财务管理 (finance) ==========
    "finance:receivables_view": ("finance:receivables:view", "查看应收账款", "finance", "receivables_view", None),
    "finance:reports_view": ("finance:reports:view", "查看财务报表", "finance", "reports_view", None),
    "finance:audit_logs": ("finance:audit:view", "查看财务审计日志", "finance", "audit_view", None),

    # ========== 系统管理 ==========
    "user:manage": ("user:manage", "管理用户", "user", "manage", None),
    "role:manage": ("role:manage", "管理角色", "role", "manage", None),
    "permission:manage": ("permission:manage", "管理权限", "permission", "manage", None),
    "system:config": ("system:config", "系统配置", "system", "config", None),
    "ai:manage": ("ai:manage", "AI 配置管理", "ai", "manage", None),
    "ai:read": ("ai:view", "AI 配置查看", "ai", "view", None),
    "apikey:manage": ("apikey:manage", "管理 API Key", "apikey", "manage", None),
    "approval:flow:create": ("approval:flow:create", "创建审批流程", "approval", "flow_create", None),
    "approval:flow:update": ("approval:flow:edit", "编辑审批流程", "approval", "flow_edit", None),
    "statistics:view": ("statistics:view", "查看统计数据", "statistics", "view", None),
    "report:view": ("report:view:own", "查看报表", "report", "view", "own"),
    "report:view:team": ("report:view:team", "查看团队报表", "report", "view", "team"),

    # ========== 采购管理 (procurement) ==========
    "procurement_method:view": ("procurement_method:view", "查看采购方式", "procurement_method", "view", None),
    "procurement_method:create": ("procurement_method:create", "创建采购方式", "procurement_method", "create", None),
    "procurement_method:update": ("procurement_method:edit", "编辑采购方式", "procurement_method", "edit", None),
    "procurement_method:delete": ("procurement_method:delete", "删除采购方式", "procurement_method", "delete", None),
    "procurement_stage:view": ("procurement_stage:view", "查看阶段模板", "procurement_stage", "view", None),
    "procurement_stage:create": ("procurement_stage:create", "创建阶段模板", "procurement_stage", "create", None),
    "procurement_stage:update": ("procurement_stage:edit", "编辑阶段模板", "procurement_stage", "edit", None),
    "procurement_stage:delete": ("procurement_stage:delete", "删除阶段模板", "procurement_stage", "delete", None),
    "procurement:admin:assess": ("procurement:admin:assess", "采购管理-影响评估", "procurement", "admin_assess", None),
    "procurement:admin:migrate": ("procurement:admin:migrate", "采购管理-批量迁移", "procurement", "admin_migrate", None),
    "procurement:admin:rollback": ("procurement:admin:rollback", "采购管理-版本回滚", "procurement", "admin_rollback", None),
}

# ============================================================================
# Action 权限码更新表
# ============================================================================
ACTION_PERMISSION_UPDATE = {
    "query_stage": "opportunity:view:own",
    "advance_stage": "opportunity:edit:own",
    "set_procurement_method": "opportunity:edit:own",
    "rollback_stage": "opportunity:edit:own",
    "query_stage_history": "opportunity:view:own",
}


def step1_delete_redundant_permissions(db):
    """步骤 1: 删除冗余权限"""
    print("\n=== 步骤 1: 删除冗余权限 ===\n")

    deleted_count = 0

    for old_code in DELETE_PERMISSIONS:
        # 查找该权限
        result = db.execute(text("SELECT id FROM permissions WHERE code = :code"), {"code": old_code})
        perm = result.fetchone()

        if not perm:
            print(f"  ⚠️  权限不存在: {old_code}")
            continue

        perm_id = perm[0]

        # 查找对应的目标权限（合并后的权限）
        target_code = None
        if old_code == "customer:delete":
            target_code = "customer:delete:own"
        elif old_code == "customer:update":
            target_code = "customer:edit:own"
        elif old_code == "opportunity:delete":
            target_code = "opportunity:delete:own"
        elif old_code == "opportunity:update":
            target_code = "opportunity:edit:own"
        elif old_code == "opportunity:stage":
            target_code = "opportunity:stage:view"
        elif old_code == "finance:view_receivables":
            target_code = "finance:receivables:view"

        if target_code:
            # 查找目标权限
            result = db.execute(text("SELECT id FROM permissions WHERE code = :code"), {"code": target_code})
            target_perm = result.fetchone()

            if target_perm:
                target_id = target_perm[0]
                # 将旧权限的角色关联迁移到目标权限（避免重复）
                db.execute(text("""
                    INSERT IGNORE INTO role_permissions (role_id, permission_id, created_at)
                    SELECT role_id, :target_id, NOW()
                    FROM role_permissions
                    WHERE permission_id = :old_id
                """), {"target_id": target_id, "old_id": perm_id})
                print(f"  ✓ 迁移角色关联: {old_code} -> {target_code}")

        # 删除旧权限的角色关联
        db.execute(text("DELETE FROM role_permissions WHERE permission_id = :id"), {"id": perm_id})

        # 删除旧权限
        db.execute(text("DELETE FROM permissions WHERE id = :id"), {"id": perm_id})
        print(f"  ✓ 删除权限: {old_code}")
        deleted_count += 1

    print(f"\n删除完成: {deleted_count} 个冗余权限")
    return deleted_count


def step2_update_permissions(db):
    """步骤 2: 更新权限码"""
    print("\n=== 步骤 2: 更新权限码 ===\n")

    updated_count = 0

    for old_code, (new_code, new_name, resource, action, scope) in PERMISSION_UPDATE.items():
        # 检查权限是否存在
        result = db.execute(text("SELECT id, name FROM permissions WHERE code = :code"), {"code": old_code})
        perm = result.fetchone()

        if not perm:
            print(f"  ⚠️  权限不存在: {old_code}")
            continue

        perm_id = perm[0]
        old_name = perm[1]

        # 检查新权限码是否已存在
        if old_code != new_code:
            result = db.execute(text("SELECT id FROM permissions WHERE code = :code"), {"code": new_code})
            if result.fetchone():
                print(f"  ⚠️  新权限码已存在: {new_code}，跳过")
                continue

        # 更新权限
        db.execute(text("""
            UPDATE permissions
            SET code = :new_code, name = :new_name, resource = :resource, action = :action, scope = :scope
            WHERE id = :id
        """), {
            "id": perm_id,
            "new_code": new_code,
            "new_name": new_name,
            "resource": resource,
            "action": action,
            "scope": scope
        })

        if old_code != new_code:
            print(f"  ✓ {old_code} -> {new_code}")
        else:
            print(f"  ✓ 更新 {old_code} 字段")
        updated_count += 1

    print(f"\n更新完成: {updated_count} 个权限")
    return updated_count


def step3_update_actions(db):
    """步骤 3: 更新 Action 权限码"""
    print("\n=== 步骤 3: 更新 Action 权限码 ===\n")

    updated_count = 0

    for action_name, new_perm in ACTION_PERMISSION_UPDATE.items():
        result = db.execute(text("""
            UPDATE crm_ai_skill_actions
            SET permission_code = :new_perm
            WHERE action_name = :action_name
        """), {"new_perm": new_perm, "action_name": action_name})

        if result.rowcount > 0:
            print(f"  ✓ {action_name}: {new_perm}")
            updated_count += result.rowcount

    print(f"\nAction 更新完成: {updated_count} 个")
    return updated_count


def step4_verify(db):
    """步骤 4: 验证迁移结果"""
    print("\n=== 步骤 4: 验证迁移结果 ===\n")

    # 检查权限码格式
    result = db.execute(text("SELECT code FROM permissions ORDER BY code"))
    codes = [row[0] for row in result]

    two_layer = []
    three_layer = []

    for code in codes:
        parts = code.split(':')
        if len(parts) == 2:
            two_layer.append(code)
        elif len(parts) == 3:
            three_layer.append(code)

    print(f"权限码统计:")
    print(f"  两层格式: {len(two_layer)} 个")
    print(f"  三层格式: {len(three_layer)} 个")
    print(f"  总计: {len(codes)} 个")

    # 检查 Action 权限码
    result = db.execute(text("""
        SELECT action_name, permission_code
        FROM crm_ai_skill_actions
        ORDER BY action_name
    """))

    print("\nAction 权限码:")
    for row in result:
        print(f"  {row[0]}: {row[1]}")

    # 检查角色权限数量
    result = db.execute(text("""
        SELECT r.code, COUNT(rp.permission_id) as perm_count
        FROM roles r
        LEFT JOIN role_permissions rp ON r.id = rp.role_id
        GROUP BY r.id, r.code
        ORDER BY r.code
    """))

    print("\n角色权限数量:")
    for row in result:
        print(f"  {row[0]}: {row[1]} 个权限")

    return len(codes)


def step5_clear_cache():
    """步骤 5: 清除权限缓存"""
    print("\n=== 步骤 5: 清除权限缓存 ===\n")

    try:
        from app.core.redis import get_redis_client
        redis_client = get_redis_client()
        pattern = "user_permissions:*"
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
            print(f"  ✓ 已清除 {len(keys)} 个用户权限缓存")
        else:
            print("  ✓ 无权限缓存需要清除")
        return True
    except Exception as e:
        print(f"  ⚠️  清除缓存失败: {str(e)}")
        return False


def main():
    """执行迁移"""
    print("=" * 60)
    print("权限码规范化迁移")
    print("=" * 60)

    db = SessionLocal()

    try:
        # 步骤 1: 删除冗余权限
        step1_delete_redundant_permissions(db)

        # 步骤 2: 更新权限码
        step2_update_permissions(db)

        # 步骤 3: 更新 Action 权限码
        step3_update_actions(db)

        # 提交事务
        db.commit()

        # 步骤 4: 验证迁移结果
        step4_verify(db)

        # 步骤 5: 清除缓存
        step5_clear_cache()

        print("\n" + "=" * 60)
        print("✅ 权限码规范化迁移完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()