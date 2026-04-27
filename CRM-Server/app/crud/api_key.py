from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from app.models.api_key import ApiKey, ApiKeyStatus
from app.schemas.api_key import ApiKeyCreate, ApiKeyUpdate


class ApiKeyCRUD:
    def get_by_id(self, db: Session, api_key_id: int) -> Optional[ApiKey]:
        return db.query(ApiKey).filter(ApiKey.id == api_key_id).first()

    def get_by_key_id(self, db: Session, key_id: str) -> Optional[ApiKey]:
        """根据对外展示的 Key ID 查询"""
        return db.query(ApiKey).filter(ApiKey.key_id == key_id).first()

    def get_by_api_key_hash(self, db: Session, api_key_hash: str) -> Optional[ApiKey]:
        """根据 API Key 哈希值查询（用于认证）"""
        return db.query(ApiKey).filter(ApiKey.api_key_hash == api_key_hash).first()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[ApiKeyStatus] = None
    ) -> List[ApiKey]:
        query = db.query(ApiKey)
        if status:
            query = query.filter(ApiKey.status == status)
        return query.order_by(ApiKey.created_at.desc()).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: ApiKeyCreate, created_by: Optional[int] = None) -> ApiKey:
        """创建 ApiKey，返回 db_obj，原始 key 需在 API 层单独返回"""
        key_id = ApiKey.generate_key_id()
        raw_api_key = ApiKey.generate_api_key()
        api_key_hash = ApiKey.hash_api_key(raw_api_key)

        db_obj = ApiKey(
            key_id=key_id,
            api_key_hash=api_key_hash,
            app_name=obj_in.app_name,
            description=obj_in.description,
            permissions=obj_in.permissions,
            ip_whitelist=obj_in.ip_whitelist,
            rate_limit_tps=obj_in.rate_limit_tps,
            status=ApiKeyStatus.ACTIVE,
            expires_at=obj_in.expires_at,
            created_by=created_by
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)

        # 将原始 key 临时存储在对象上（仅用于返回给调用方）
        db_obj._raw_api_key = raw_api_key
        return db_obj

    def update(self, db: Session, db_obj: ApiKey, obj_in: ApiKeyUpdate) -> ApiKey:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_status(self, db: Session, api_key_id: int, status: ApiKeyStatus) -> Optional[ApiKey]:
        db_obj = self.get_by_id(db, api_key_id)
        if db_obj:
            db_obj.status = status
            db.commit()
            db.refresh(db_obj)
        return db_obj

    def update_last_used(self, db: Session, api_key_id: int) -> Optional[ApiKey]:
        """更新最后使用时间"""
        db_obj = self.get_by_id(db, api_key_id)
        if db_obj:
            db_obj.last_used_at = datetime.utcnow()
            db.commit()
        return db_obj

    def delete(self, db: Session, api_key_id: int) -> Optional[ApiKey]:
        obj = db.query(ApiKey).filter(ApiKey.id == api_key_id).first()
        if obj:
            db.delete(obj)
            db.commit()
        return obj

    def is_valid(self, db: Session, api_key_hash: str, client_ip: Optional[str] = None) -> tuple[bool, Optional[ApiKey], str]:
        """
        校验 API Key 是否有效

        返回：(是否有效, ApiKey对象, 错误消息)
        """
        db_obj = self.get_by_api_key_hash(db, api_key_hash)

        if not db_obj:
            return False, None, "API Key 不存在"

        if db_obj.status != ApiKeyStatus.ACTIVE:
            return False, db_obj, f"API Key 状态为 {db_obj.status.value}，不可使用"

        if db_obj.expires_at and datetime.utcnow() > db_obj.expires_at:
            return False, db_obj, "API Key 已过期"

        if db_obj.ip_whitelist and len(db_obj.ip_whitelist) > 0:
            if client_ip and client_ip not in db_obj.ip_whitelist:
                return False, db_obj, f"IP {client_ip} 不在白名单中"

        return True, db_obj, ""

    def has_permission(self, db_obj: ApiKey, permission_code: str) -> bool:
        """检查 ApiKey 是否有特定权限"""
        if not db_obj.permissions:
            return False
        return permission_code in db_obj.permissions


api_key_crud = ApiKeyCRUD()