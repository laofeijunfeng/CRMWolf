from sqlalchemy.orm import Session
from typing import Optional, List
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.schemas.permission import PermissionCreate, PermissionUpdate


class PermissionCRUD:
    def get_by_id(self, db: Session, permission_id: int) -> Optional[Permission]:
        return db.query(Permission).filter(Permission.id == permission_id).first()

    def get_by_code(self, db: Session, code: str) -> Optional[Permission]:
        return db.query(Permission).filter(Permission.code == code).first()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        resource: Optional[str] = None,
        action: Optional[str] = None
    ) -> List[Permission]:
        query = db.query(Permission)
        
        if resource:
            query = query.filter(Permission.resource == resource)
        if action:
            query = query.filter(Permission.action == action)
        
        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: PermissionCreate) -> Permission:
        db_obj = Permission(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: Permission, obj_in: PermissionUpdate) -> Permission:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, permission_id: int) -> Permission:
        obj = db.query(Permission).filter(Permission.id == permission_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def assign_to_role(self, db: Session, role_id: int, permission_id: int) -> RolePermission:
        role_permission = RolePermission(role_id=role_id, permission_id=permission_id)
        db.add(role_permission)
        db.commit()
        db.refresh(role_permission)
        return role_permission

    def remove_from_role(self, db: Session, role_id: int, permission_id: int) -> bool:
        role_permission = db.query(RolePermission).filter(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id
        ).first()
        
        if role_permission:
            db.delete(role_permission)
            db.commit()
            return True
        return False

    def get_role_permissions(self, db: Session, role_id: int) -> List[Permission]:
        return db.query(Permission).join(RolePermission, Permission.id == RolePermission.permission_id).filter(
            RolePermission.role_id == role_id
        ).all()

    def get_user_permissions(self, db: Session, user_id: int) -> List[Permission]:
        from app.models.user_role import UserRole
        
        return db.query(Permission).join(RolePermission, Permission.id == RolePermission.permission_id).join(UserRole, RolePermission.role_id == UserRole.role_id).filter(
            UserRole.user_id == user_id
        ).all()


permission_crud = PermissionCRUD()
