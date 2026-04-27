"""
AI Enum Mapping CRUD
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from app.models.ai_skill import AIEnumMapping


class AIEnumMappingCRUD:
    """Enum 映射 CRUD"""

    def get_by_id(self, db: Session, enum_id: int) -> Optional[AIEnumMapping]:
        return db.query(AIEnumMapping).filter(AIEnumMapping.id == enum_id).first()

    def get_by_name(self, db: Session, enum_name: str) -> Optional[AIEnumMapping]:
        return db.query(AIEnumMapping).filter(AIEnumMapping.enum_name == enum_name).first()

    def get_all(self, db: Session) -> List[AIEnumMapping]:
        return db.query(AIEnumMapping).all()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[AIEnumMapping], int]:
        query = db.query(AIEnumMapping)
        total = query.count()
        enums = query.offset(skip).limit(limit).all()
        return enums, total

    def create(self, db: Session, enum_data: dict) -> AIEnumMapping:
        db_obj = AIEnumMapping(**enum_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, enum_id: int, update_data: dict) -> Optional[AIEnumMapping]:
        enum = db.query(AIEnumMapping).filter(AIEnumMapping.id == enum_id).first()
        if enum:
            for field, value in update_data.items():
                setattr(enum, field, value)
            db.commit()
            db.refresh(enum)
        return enum

    def delete(self, db: Session, enum_id: int) -> Optional[AIEnumMapping]:
        enum = db.query(AIEnumMapping).filter(AIEnumMapping.id == enum_id).first()
        if enum:
            db.delete(enum)
            db.commit()
        return enum


ai_enum_mapping_crud = AIEnumMappingCRUD()