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

    def assign_to_user(self, db: Session, user_id: int, role_id: int) -> UserRole:
        user_role = UserRole(user_id=user_id, role_id=role_id)
        db.add(user_role)
        db.commit()
        db.refresh(user_role)
        return user_role

    def remove_from_user(self, db: Session, user_id: int, role_id: int) -> bool:
        user_role = db.query(UserRole).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id
        ).first()
        
        if user_role:
            db.delete(user_role)
            db.commit()
            return True
        return False

    def get_user_roles(self, db: Session, user_id: int) -> List[Role]:
        return db.query(Role).join(UserRole, Role.id == UserRole.role_id).filter(UserRole.user_id == user_id).all()
    
    def get_role_users(self, db: Session, role_id: int) -> List:
        from app.models.user import User
        return db.query(User).join(UserRole, User.id == UserRole.user_id).filter(UserRole.role_id == role_id).all()

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
        # 需要删除的权限
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


role_crud = RoleCRUD()
