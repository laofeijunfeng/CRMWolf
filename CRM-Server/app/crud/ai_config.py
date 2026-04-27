"""
AI 配置 CRUD
"""
from sqlalchemy.orm import Session
from typing import Optional
from app.models.ai_config import AIConfig
from app.schemas.ai_config import AIConfigCreate


class AIConfigCRUD:
    """AI 配置 CRUD 操作"""

    def get_config(self, db: Session) -> Optional[AIConfig]:
        """获取 AI 配置（ID 固定为 1）"""
        return db.query(AIConfig).filter(AIConfig.id == 1).first()

    def create_config(self, db: Session, obj_in: AIConfigCreate, updated_by: Optional[int] = None) -> AIConfig:
        """创建 AI 配置"""
        encrypted_key = AIConfig.encrypt_api_key(obj_in.api_key)

        db_obj = AIConfig(
            id=1,
            api_host=obj_in.api_host,
            api_key_encrypted=encrypted_key,
            model_name=obj_in.model_name,
            temperature=0.1,
            max_tokens=1024,
            updated_by=updated_by
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_config(self, db: Session, db_obj: AIConfig, obj_in: AIConfigCreate, updated_by: Optional[int] = None) -> AIConfig:
        """更新 AI 配置"""
        encrypted_key = AIConfig.encrypt_api_key(obj_in.api_key)

        db_obj.api_host = obj_in.api_host
        db_obj.api_key_encrypted = encrypted_key
        db_obj.model_name = obj_in.model_name
        db_obj.updated_by = updated_by
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_decrypted_api_key(self, db: Session) -> Optional[str]:
        """获取解密后的 API Key"""
        config = self.get_config(db)
        if config:
            return AIConfig.decrypt_api_key(config.api_key_encrypted)
        return None

    def save_or_update(self, db: Session, obj_in: AIConfigCreate, updated_by: Optional[int] = None) -> AIConfig:
        """保存或更新配置（如果存在则更新，不存在则创建）"""
        existing = self.get_config(db)
        if existing:
            return self.update_config(db, existing, obj_in, updated_by)
        return self.create_config(db, obj_in, updated_by)


ai_config_crud = AIConfigCRUD()