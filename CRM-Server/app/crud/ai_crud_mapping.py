"""
AI CRUD Mapping CRUD
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from app.models.ai_skill import AICRUDMapping


class AICRUDMappingCRUD:
    """CRUD 映射 CRUD"""

    def get_by_id(self, db: Session, mapping_id: int) -> Optional[AICRUDMapping]:
        return db.query(AICRUDMapping).filter(AICRUDMapping.id == mapping_id).first()

    def get_by_name(self, db: Session, mapping_name: str) -> Optional[AICRUDMapping]:
        return db.query(AICRUDMapping).filter(AICRUDMapping.mapping_name == mapping_name).first()

    def get_all(self, db: Session) -> List[AICRUDMapping]:
        return db.query(AICRUDMapping).all()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[AICRUDMapping], int]:
        query = db.query(AICRUDMapping)
        total = query.count()
        mappings = query.offset(skip).limit(limit).all()
        return mappings, total

    def create(self, db: Session, mapping_data: dict) -> AICRUDMapping:
        db_obj = AICRUDMapping(**mapping_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, mapping_id: int, update_data: dict) -> Optional[AICRUDMapping]:
        mapping = db.query(AICRUDMapping).filter(AICRUDMapping.id == mapping_id).first()
        if mapping:
            for field, value in update_data.items():
                setattr(mapping, field, value)
            db.commit()
            db.refresh(mapping)
        return mapping

    def delete(self, db: Session, mapping_id: int) -> Optional[AICRUDMapping]:
        mapping = db.query(AICRUDMapping).filter(AICRUDMapping.id == mapping_id).first()
        if mapping:
            db.delete(mapping)
            db.commit()
        return mapping


ai_crud_mapping_crud = AICRUDMappingCRUD()