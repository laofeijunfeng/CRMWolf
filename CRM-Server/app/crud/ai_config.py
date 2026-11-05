"""AI 配置 CRUD"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ai_config import AIConfig
from app.schemas.ai_config import AIConfigCreate, StructuredOutputMode


class AIConfigCRUD:
    def get_config(self, db: Session, team_id: int) -> Optional[AIConfig]:
        return db.query(AIConfig).filter(AIConfig.team_id == team_id).first()

    def create_config(self, db: Session, obj_in: AIConfigCreate, updated_by: Optional[int] = None, team_id: int = 1) -> AIConfig:
        if not obj_in.api_key:
            raise ValueError("首次配置必须提供 API Key")
        db_obj = AIConfig(
            team_id=team_id,
            api_host=obj_in.api_host,
            api_key_encrypted=AIConfig.encrypt_api_key(obj_in.api_key),
            model_name=obj_in.model_name,
            temperature=0.1,
            max_tokens=1024,
            structured_output_mode=obj_in.structured_output_mode,
            assistant_verified_fingerprint=None,
            assistant_verified_at=None,
            updated_by=updated_by,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_config(self, db: Session, db_obj: AIConfig, obj_in: AIConfigCreate, updated_by: Optional[int] = None) -> AIConfig:
        db_obj.api_host = obj_in.api_host
        if obj_in.api_key:
            db_obj.api_key_encrypted = AIConfig.encrypt_api_key(obj_in.api_key)
        db_obj.model_name = obj_in.model_name
        db_obj.structured_output_mode = obj_in.structured_output_mode
        db_obj.assistant_verified_fingerprint = None
        db_obj.assistant_verified_at = None
        db_obj.updated_by = updated_by
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_decrypted_api_key(self, db: Session, team_id: int) -> Optional[str]:
        config = self.get_config(db, team_id)
        if config:
            return AIConfig.decrypt_api_key(config.api_key_encrypted)
        return None

    def save_or_update(self, db: Session, obj_in: AIConfigCreate, updated_by: Optional[int] = None, team_id: int = 1) -> AIConfig:
        existing = self.get_config(db, team_id)
        if existing:
            return self.update_config(db, existing, obj_in, updated_by)
        return self.create_config(db, obj_in, updated_by, team_id)

    def mark_assistant_verified(
        self,
        db: Session,
        *,
        team_id: int,
        expected_fingerprint: str,
        tested_fingerprint: str,
        output_mode: StructuredOutputMode,
        verified_at: datetime,
    ) -> bool:
        """Atomically certify only the config snapshot that was actually tested."""
        config = db.query(AIConfig).filter(AIConfig.team_id == team_id).populate_existing().first()
        if config is None:
            return False
        api_key = AIConfig.decrypt_api_key(config.api_key_encrypted)
        current_mode = config.structured_output_mode or "json_object"
        current = AIConfig.capability_fingerprint(config.api_host, api_key, config.model_name, current_mode)
        tested = AIConfig.capability_fingerprint(config.api_host, api_key, config.model_name, output_mode)
        if current != expected_fingerprint or tested != tested_fingerprint:
            db.rollback()
            return False
        changed = db.query(AIConfig).filter(
            AIConfig.id == config.id,
            AIConfig.team_id == team_id,
            AIConfig.api_host == config.api_host,
            AIConfig.api_key_encrypted == config.api_key_encrypted,
            AIConfig.model_name == config.model_name,
            AIConfig.structured_output_mode == current_mode,
        ).update({
            AIConfig.structured_output_mode: output_mode,
            AIConfig.assistant_verified_fingerprint: tested_fingerprint,
            AIConfig.assistant_verified_at: verified_at,
        }, synchronize_session=False)
        db.commit()
        db.expire_all()
        return changed == 1

    def mark_assistant_unverified(self, db: Session, *, team_id: int) -> None:
        db.query(AIConfig).filter(AIConfig.team_id == team_id).update({
            AIConfig.assistant_verified_fingerprint: None,
            AIConfig.assistant_verified_at: None,
        }, synchronize_session=False)
        db.commit()
        db.expire_all()


ai_config_crud = AIConfigCRUD()
