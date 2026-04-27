from app.core.database import SessionLocal
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission

db = SessionLocal()
try:
    director = db.query(Role).filter(Role.code == 'SALES_DIRECTOR').first()
    if director:
        print(f'销售总监角色: {director.name} (ID: {director.id})')
        
        role_perms = db.query(Permission).join(
            RolePermission, 
            RolePermission.permission_id == Permission.id
        ).filter(RolePermission.role_id == director.id).all()
        
        print(f'\n当前配置的权限数量: {len(role_perms)}')
        
        approve_perms = [p for p in role_perms if 'approve' in p.code.lower()]
        print(f'\n审批相关权限 ({len(approve_perms)} 个):')
        for perm in approve_perms:
            print(f'  - {perm.code}: {perm.name}')
        
        print(f'\n所有合同相关权限:')
        contract_perms = [p for p in role_perms if p.code.startswith('contract:')]
        for perm in contract_perms:
            print(f'  - {perm.code}: {perm.name}')
    else:
        print('未找到销售总监角色')
        
finally:
    db.close()
