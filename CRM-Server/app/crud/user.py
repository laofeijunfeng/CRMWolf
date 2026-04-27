from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, List
from app.models.user import User, UserStatus
from app.schemas.user import UserCreate, UserUpdate, FeishuUserInfo


class UserCRUD:
    def get_by_id(self, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    def get_by_feishu_open_id(self, db: Session, feishu_open_id: str) -> Optional[User]:
        return db.query(User).filter(User.feishu_open_id == feishu_open_id).first()

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    def get_by_mobile(self, db: Session, mobile: str) -> Optional[User]:
        return db.query(User).filter(User.mobile == mobile).first()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[UserStatus] = None,
        region: Optional[str] = None
    ) -> List[User]:
        query = db.query(User)
        
        if status:
            query = query.filter(User.status == status)
        if region:
            query = query.filter(User.region == region)
        
        return query.offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: UserCreate) -> User:
        db_obj = User(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_from_feishu(self, db: Session, feishu_info: FeishuUserInfo, region: Optional[str] = None) -> User:
        user_data = {
            "feishu_open_id": feishu_info.open_id,
            "feishu_union_id": feishu_info.union_id,
            "feishu_user_id": feishu_info.user_id,
            "name": feishu_info.name,
            "en_name": feishu_info.en_name,
            "email": feishu_info.email,
            "mobile": feishu_info.mobile,
            "avatar_url": feishu_info.avatar_url,
            "employee_no": feishu_info.employee_no,
            "tenant_key": feishu_info.tenant_key,
            "region": region
        }
        
        db_obj = User(**user_data)
        db.add(db_obj)
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

    def update_from_feishu(self, db: Session, db_obj: User, feishu_info: FeishuUserInfo) -> User:
        if feishu_info.name:
            db_obj.name = feishu_info.name
        if feishu_info.en_name:
            db_obj.en_name = feishu_info.en_name
        if feishu_info.email:
            db_obj.email = feishu_info.email
        if feishu_info.mobile:
            db_obj.mobile = feishu_info.mobile
        if feishu_info.avatar_url:
            db_obj.avatar_url = feishu_info.avatar_url
        if feishu_info.employee_no:
            db_obj.employee_no = feishu_info.employee_no
        if feishu_info.tenant_key:
            db_obj.tenant_key = feishu_info.tenant_key
        
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, user_id: int) -> User:
        obj = db.query(User).filter(User.id == user_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def get_or_create_from_feishu(
        self,
        db: Session,
        feishu_info: FeishuUserInfo,
        region: Optional[str] = None
    ) -> User:
        user = self.get_by_feishu_open_id(db, feishu_info.open_id)
        
        if user:
            return self.update_from_feishu(db, user, feishu_info)
        else:
            return self.create_from_feishu(db, feishu_info, region)


user_crud = UserCRUD()
