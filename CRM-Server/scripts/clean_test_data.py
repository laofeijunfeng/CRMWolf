"""
清理数据库测试数据，保留系统配置数据

保留的系统配置数据：
- 用户表 (crm_users)
- 角色表 (crm_roles)
- 权限表 (crm_permissions)
- 用户角色关联表 (crm_user_roles)
- 角色权限关联表 (crm_role_permissions)
- 销售阶段表 (crm_opportunity_stages)

清理的业务数据：
- 线索表 (crm_leads)
- 线索跟进记录表 (crm_lead_follow_ups)
- 客户表 (crm_customers)
- 联系人表 (crm_contacts)
- 客户跟进记录表 (crm_customer_follow_ups)
- 商机表 (crm_opportunities)
"""
from app.core.database import SessionLocal
from sqlalchemy import text


def clean_test_data():
    db = SessionLocal()
    try:
        print("=" * 60)
        print("开始清理测试数据...")
        print("=" * 60)
        
        tables_to_clean = [
            ("crm_customer_follow_ups", "客户跟进记录"),
            ("crm_lead_follow_ups", "线索跟进记录"),
            ("crm_opportunities", "商机"),
            ("crm_contacts", "联系人"),
            ("crm_customers", "客户"),
            ("crm_leads", "线索"),
        ]
        
        total_deleted = 0
        
        for table_name, table_desc in tables_to_clean:
            try:
                result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar()
                if result > 0:
                    print(f"\n清理 {table_desc} ({table_name})...")
                    db.execute(text(f"DELETE FROM {table_name}"))
                    deleted = result
                    total_deleted += deleted
                    print(f"  ✓ 已删除 {deleted} 条记录")
                else:
                    print(f"\n{table_desc} ({table_name}) - 无数据，跳过")
            except Exception as e:
                print(f"  ✗ 清理 {table_desc} 失败: {e}")
        
        db.commit()
        
        print("\n" + "=" * 60)
        print(f"清理完成！共删除 {total_deleted} 条测试数据")
        print("=" * 60)
        
        print("\n保留的系统配置数据：")
        print("  - 用户表 (crm_users)")
        print("  - 角色表 (crm_roles)")
        print("  - 权限表 (crm_permissions)")
        print("  - 用户角色关联表 (crm_user_roles)")
        print("  - 角色权限关联表 (crm_role_permissions)")
        print("  - 销售阶段表 (crm_opportunity_stages)")
        
    except Exception as e:
        print(f"\n清理失败: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("\n⚠️  警告：此操作将删除所有业务测试数据！")
    print("   系统配置数据（用户、角色、权限、销售阶段）将被保留。\n")
    
    confirm = input("确认继续？(输入 'yes' 确认): ")
    if confirm.lower() == 'yes':
        clean_test_data()
    else:
        print("操作已取消")
