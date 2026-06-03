from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.role_permission import RolePermission
from app.models.permission import Permission
from app.schemas.role import RoleCreate, RoleUpdate


class RoleCRUD:
    def get_by_id(self, db: Session, role_id: int) -> Optional[Role]:
        return db.query(Role).filter(Role.id == role_id).first()

    def get_by_code(self, db: Session, code: str) -> Optional[Role]:
        return db.query(Role).filter(Role.code == code).first()

    def get_by_name(self, db: Session, name: str) -> Optional[Role]:
        return db.query(Role).filter(Role.name == name).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> List[Role]:
        return db.query(Role).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: RoleCreate) -> Role:
        db_obj = Role(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: Role, obj_in: RoleUpdate) -> Role:
        update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, role_id: int) -> Role:
        obj = db.query(Role).filter(Role.id == role_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def assign_to_user(self, db: Session, user_id: int, role_id: int, team_id: int) -> UserRole:
        """
        为用户在指定团队分配角色

        Args:
            user_id: 用户ID
            role_id: 角色ID
            team_id: 团队ID
        """
        user_role = UserRole(user_id=user_id, role_id=role_id, team_id=team_id)
        db.add(user_role)
        db.commit()
        db.refresh(user_role)
        return user_role

    def remove_from_user(self, db: Session, user_id: int, role_id: int, team_id: int) -> bool:
        """
        移除用户在指定团队的角色

        Args:
            user_id: 用户ID
            role_id: 角色ID
            team_id: 团队ID
        """
        user_role = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            UserRole.team_id == team_id
        ).first()

        if user_role:
            db.delete(user_role)
            db.commit()
            return True
        return False

    def get_user_roles(self, db: Session, user_id: int, team_id: Optional[int] = None) -> List[Role]:
        """
        获取用户的角色列表

        Args:
            user_id: 用户ID
            team_id: 团队ID（可选，不传则返回用户在所有团队的角色）
        """
        query = db.query(Role).join(UserRole, Role.id == UserRole.role_id).filter(UserRole.user_id == user_id)
        if team_id is not None:
            query = query.filter(UserRole.team_id == team_id)
        return query.all()

    def get_user_roles_by_team(self, db: Session, user_id: int, team_id: int) -> List[Role]:
        """
        获取用户在指定团队的角色列表

        Args:
            user_id: 用户ID
            team_id: 团队ID
        """
        return db.query(Role).join(UserRole, Role.id == UserRole.role_id).filter(
            UserRole.user_id == user_id,
            UserRole.team_id == team_id
        ).all()

    def get_role_users(self, db: Session, role_id: int, team_id: Optional[int] = None) -> List:
        """
        获取拥有指定角色的用户列表

        Args:
            role_id: 角色ID
            team_id: 团队ID（可选）
        """
        from app.models.user import User
        query = db.query(User).join(UserRole, User.id == UserRole.user_id).filter(UserRole.role_id == role_id)
        if team_id is not None:
            query = query.filter(UserRole.team_id == team_id)
        return query.all()

    def update_permissions(self, db: Session, role_id: int, permission_ids: List[int]) -> List[Permission]:
        """批量更新角色权限"""
        # 获取当前角色的权限 ID 列表
        current_permissions = db.query(RolePermission.permission_id).filter(
            RolePermission.role_id == role_id
        ).all()
        current_ids = set(p[0] for p in current_permissions)
        new_ids = set(permission_ids)

        # 需要添加的权限
        to_add = new_ids - current_ids
        # 要要删除的权限
        to_remove = current_ids - new_ids

        # 删除权限
        if to_remove:
            db.query(RolePermission).filter(
                RolePermission.role_id == role_id,
                RolePermission.permission_id.in_(to_remove)
            ).delete(synchronize_session=False)

        # 添加权限
        for permission_id in to_add:
            role_permission = RolePermission(role_id=role_id, permission_id=permission_id)
            db.add(role_permission)

        db.commit()

        # 返回更新后的权限列表
        return db.query(Permission).join(
            RolePermission, Permission.id == RolePermission.permission_id
        ).filter(RolePermission.role_id == role_id).all()

    def remove_all_user_roles_in_team(self, db: Session, user_id: int, team_id: int) -> int:
        """
        删除用户在某团队的所有角色

        Args:
            user_id: 用户ID
            team_id: 团队ID

        Returns:
            int: 删除的记录数
        """
        count = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.team_id == team_id
        ).delete(synchronize_session=False)
        db.commit()

        # 清除权限缓存
        from app.services.permission_service import permission_service
        permission_service.clear_user_permissions_cache(user_id, team_id)

        return count

    def assign_roles_to_user(self, db: Session, user_id: int, role_ids: List[int], team_id: int) -> List[UserRole]:
        """
        为用户批量分配角色（替换模式：先清除再分配）

        Args:
            user_id: 用户ID
            role_ids: 角色ID列表
            team_id: 团队ID

        Returns:
            List[UserRole]: 新创建的用户角色关联列表
        """
        # 先删除用户在该团队的现有角色
        self.remove_all_user_roles_in_team(db, user_id, team_id)

        # 再分配新角色
        user_roles = []
        for role_id in role_ids:
            user_role = UserRole(user_id=user_id, role_id=role_id, team_id=team_id)
            db.add(user_role)
            user_roles.append(user_role)

        db.commit()

        # 清除权限缓存（已在 remove_all_user_roles_in_team 中调用，这里再次确保）
        from app.services.permission_service import permission_service
        permission_service.clear_user_permissions_cache(user_id, team_id)

        return user_roles


role_crud = RoleCRUD()