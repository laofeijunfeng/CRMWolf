"""
角色权限初始化服务

在应用启动时自动检查并初始化角色权限，确保部署后系统可用
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.core.logging import get_logger
from app.constants.permissions import ALL_PERMISSIONS, ROLES_DATA, ROLE_PERMISSIONS_MAPPING

logger = get_logger(__name__)


def ensure_permissions_exist(db: Session) -> dict:
    """确保所有权限存在，返回权限字典 {code: permission}"""
    permissions = {}
    for perm_data in ALL_PERMISSIONS:
        # 先按 code 查找（更可靠）
        perm = db.query(Permission).filter(Permission.code == perm_data["code"]).first()
        if not perm:
            # 按 code 查不到才创建，避免名称冲突
            try:
                perm = Permission(**perm_data)
                db.add(perm)
                db.commit()
                db.refresh(perm)
                logger.info(f"创建权限: {perm.code} - {perm.name}")
            except Exception as e:
                # 如果创建失败（名称冲突），跳过
                db.rollback()
                logger.warning(f"权限 {perm_data['code']} 创建失败，跳过: {e}")
                continue
        permissions[perm.code] = perm
    return permissions


def ensure_roles_exist(db: Session) -> dict:
    """确保角色存在并更新名称，返回角色字典 {code: role}"""
    roles = {}
    for role_data in ROLES_DATA:
        role = db.query(Role).filter(Role.code == role_data["code"]).first()
        if not role:
            role = Role(**role_data)
            db.add(role)
            db.commit()
            db.refresh(role)
            logger.info(f"创建角色: {role.code} - {role.name}")
        else:
            # 更新已存在角色的名称和描述
            if role.name != role_data["name"] or role.description != role_data["description"]:
                role.name = role_data["name"]
                role.description = role_data["description"]
                db.commit()
                logger.info(f"更新角色: {role.code} - {role.name}")
        roles[role.code] = role
    return roles


def ensure_role_permissions(db: Session, roles: dict, permissions: dict) -> None:
    """确保角色权限关联存在"""
    all_perm_codes = set(permissions.keys())

    for role_code, perm_config in ROLE_PERMISSIONS_MAPPING.items():
        role = roles.get(role_code)
        if not role:
            continue

        # 获取当前角色已有的权限
        existing_perms = db.query(RolePermission.permission_id).filter(
            RolePermission.role_id == role.id
        ).all()
        existing_perm_ids = {p[0] for p in existing_perms}

        # 确定需要分配的权限
        if perm_config == "all":
            # TEAM_ADMIN 获得所有权限
            target_perm_codes = all_perm_codes
        else:
            target_perm_codes = set(perm_config)

        # 添加缺失的权限
        added_count = 0
        for perm_code in target_perm_codes:
            perm = permissions.get(perm_code)
            if perm and perm.id not in existing_perm_ids:
                rp = RolePermission(role_id=role.id, permission_id=perm.id)
                db.add(rp)
                added_count += 1
                logger.info(f"为角色 {role_code} 分配权限: {perm_code}")

        if added_count > 0:
            db.commit()
            logger.info(f"角色 {role_code} 新增 {added_count} 个权限")


def init_roles_permissions():
    """初始化角色和权限（幂等操作）"""
    db = SessionLocal()
    try:
        logger.info("开始初始化角色权限...")

        # 确保所有权限存在
        permissions = ensure_permissions_exist(db)
        logger.info(f"权限总数: {len(permissions)}")

        # 确保角色存在
        roles = ensure_roles_exist(db)
        logger.info(f"角色总数: {len(roles)}")

        # 确保角色权限关联存在
        ensure_role_permissions(db, roles, permissions)

        # 验证结果
        for role_code in ROLES_DATA:
            role = roles.get(role_code["code"])
            if role:
                rp_count = db.query(RolePermission).filter(
                    RolePermission.role_id == role.id
                ).count()
                logger.info(f"角色 {role.code}: {rp_count} 个权限")

        logger.info("角色权限初始化完成")

    except Exception as e:
        logger.error(f"角色权限初始化失败: {e}")
        db.rollback()
    finally:
        db.close()