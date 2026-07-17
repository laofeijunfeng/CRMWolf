from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List, Tuple
from app.models.user import User, UserStatus
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash


class UserCRUD:
    def get_by_id(self, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def get_by_feishu_open_id(self, db: Session, feishu_open_id: str) -> Optional[User]:
        """已废弃，保留兼容"""
        return db.query(User).filter(User.feishu_open_id == feishu_open_id).first()

    def get_by_mobile(self, db: Session, mobile: str) -> Optional[User]:
        return db.query(User).filter(User.mobile == mobile).first()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[UserStatus] = None,
        region: Optional[str] = None
    ) -> Tuple[List[User], int]:
        query = db.query(User)

        if status:
            query = query.filter(User.status == status)
        if region:
            query = query.filter(User.region == region)

        total = query.count()
        users = query.offset(skip).limit(limit).all()
        return users, total

    def count(self, db: Session) -> int:
        """获取用户总数"""
        return db.query(User).count()

    def create(self, db: Session, obj_in: UserCreate) -> User:
        db_obj = User(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_from_email(
        self,
        db: Session,
        email: str,
        name: str,
        password: Optional[str] = None,
        mobile: Optional[str] = None,
        region: Optional[str] = None
    ) -> User:
        """通过邮箱创建用户"""
        user_data = {
            "email": email,
            "name": name,
            "mobile": mobile,
            "region": region,
            "status": UserStatus.ACTIVE
        }
        if password:
            user_data["password_hash"] = get_password_hash(password)

        db_obj = User(**user_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def set_password(self, db: Session, db_obj: User, password: str) -> User:
        """设置用户密码"""
        db_obj.password_hash = get_password_hash(password)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: User, obj_in: UserUpdate) -> User:
        update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, user_id: int) -> Optional[User]:
        obj = db.query(User).filter(User.id == user_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj


user_crud = UserCRUD()
