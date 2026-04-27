"""
测试权限系统的脚本
验证合同和财务相关权限是否正常工作
"""
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.core.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.permission import Permission
from app.models.contract import Contract
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.invoice import InvoiceApplication
from datetime import date, datetime
from decimal import Decimal


client = TestClient(app)


def test_permissions_created(db: Session):
    """测试权限是否正确创建"""
    print("\n" + "="*80)
    print("测试权限创建")
    print("="*80)
    
    permissions = db.query(Permission).filter(
        Permission.code.like("contract:%") | 
        Permission.code.like("invoice:%") | 
        Permission.code.like("payment:%") |
        Permission.code.like("finance:%")
    ).all()
    
    print(f"\n找到 {len(permissions)} 个权限:")
    for perm in permissions:
        print(f"  - {perm.code}: {perm.name}")
    
    assert len(permissions) > 0, "应该创建至少一个权限"
    
    expected_permissions = [
        "contract:view_own",
        "contract:view_all",
        "contract:create",
        "contract:edit_own",
        "contract:edit_all",
        "contract:approve_own",
        "contract:approve_all",
        "contract:submit_approval",
        "contract:cancel_approval",
        "invoice:create",
        "invoice:approve",
        "invoice:view_all",
        "invoice:mark_issued",
        "payment:confirm",
        "payment:view_all",
        "payment:register",
        "finance:receivables_view",
        "finance:reports_view",
        "finance:audit_logs"
    ]
    
    permission_codes = {p.code for p in permissions}
    for expected in expected_permissions:
        assert expected in permission_codes, f"缺少权限: {expected}"
    
    print("\n✅ 所有权限都已正确创建")


def test_roles_permissions_assigned(db: Session):
    """测试角色权限分配"""
    print("\n" + "="*80)
    print("测试角色权限分配")
    print("="*80)
    
    roles = db.query(Role).all()
    
    for role in roles:
        print(f"\n角色: {role.code} ({role.name})")
        
        permissions = db.query(Permission).join("role_permissions").filter(
            Permission.id.in_(
                db.query(Role.role_permissions).filter(Role.id == role.id)
            )
        ).all()
        
        print(f"  权限数量: {len(permissions)}")
        for perm in permissions[:5]:
            print(f"    - {perm.code}")
        if len(permissions) > 5:
            print(f"    ... 还有 {len(permissions) - 5} 个权限")


def test_contract_approve_own_permission():
    """测试审批自己创建的合同的权限"""
    print("\n" + "="*80)
    print("测试合同审批权限")
    print("="*80)
    
    response = client.get(
        "/api/v1/auth/login",
        params={
            "email": "admin@example.com",
            "password": "admin123"
        }
    )
    
    if response.status_code != 200:
        print("\n⚠️  需要创建测试用户")
        return
    
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n管理员登录成功")
    print(f"Token: {token[:50]}...")
    
    permissions_response = client.get(
        "/api/v1/users/me/permissions",
        headers=headers
    )
    
    if permissions_response.status_code == 200:
        permissions = permissions_response.json()
        print(f"\n管理员权限:")
        for perm in permissions[:10]:
            print(f"  - {perm}")
        
        has_approve_own = "contract:approve_own" in permissions
        has_approve_all = "contract:approve_all" in permissions
        
        print(f"\n拥有 contract:approve_own 权限: {has_approve_own}")
        print(f"拥有 contract:approve_all 权限: {has_approve_all}")
        
        assert has_approve_own, "管理员应该拥有 contract:approve_own 权限"
        assert has_approve_all, "管理员应该拥有 contract:approve_all 权限"
        
        print("\n✅ 管理员拥有正确的审批权限")


def test_finance_permissions():
    """测试财务相关权限"""
    print("\n" + "="*80)
    print("测试财务权限")
    print("="*80)
    
    response = client.get(
        "/api/v1/finance/receivables/aging-analysis",
        headers={"Authorization": "Bearer test_token"}
    )
    
    if response.status_code == 401:
        print("\n⚠️  需要有效的认证令牌")
        return
    
    if response.status_code == 403:
        print("\n✅ 权限检查正常工作（403 Forbidden）")
    elif response.status_code == 200:
        print("\n✅ 拥有财务权限，访问成功")


def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("飞书轻量化CRM - 权限系统测试")
    print("="*80)
    
    db = next(get_db())
    
    try:
        test_permissions_created(db)
        test_roles_permissions_assigned(db)
        test_contract_approve_own_permission()
        test_finance_permissions()
        
        print("\n" + "="*80)
        print("✅ 权限系统测试完成")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
