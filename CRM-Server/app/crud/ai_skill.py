"""
AI Skill CRUD
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from app.models.ai_skill import AISkill, AISkillAction


class AISkillCRUD:
    """Skill CRUD"""

    def get_by_id(self, db: Session, skill_id: int) -> Optional[AISkill]:
        return db.query(AISkill).filter(AISkill.id == skill_id).first()

    def get_by_name(self, db: Session, skill_name: str) -> Optional[AISkill]:
        return db.query(AISkill).filter(AISkill.skill_name == skill_name).first()

    def get_all_active(self, db: Session) -> List[AISkill]:
        return db.query(AISkill).filter(
            AISkill.is_active == 1
        ).order_by(AISkill.sort_order).all()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        module_type: Optional[str] = None,
        is_active: Optional[int] = None
    ) -> Tuple[List[AISkill], int]:
        query = db.query(AISkill)

        if module_type:
            query = query.filter(AISkill.module_type == module_type)
        if is_active is not None:
            query = query.filter(AISkill.is_active == is_active)

        total = query.count()
        skills = query.order_by(AISkill.sort_order).offset(skip).limit(limit).all()
        return skills, total

    def create(self, db: Session, skill_data: dict) -> AISkill:
        db_obj = AISkill(**skill_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, skill_id: int, update_data: dict) -> Optional[AISkill]:
        skill = db.query(AISkill).filter(AISkill.id == skill_id).first()
        if skill:
            for field, value in update_data.items():
                setattr(skill, field, value)
            db.commit()
            db.refresh(skill)
        return skill

    def delete(self, db: Session, skill_id: int) -> Optional[AISkill]:
        skill = db.query(AISkill).filter(AISkill.id == skill_id).first()
        if skill:
            db.delete(skill)
            db.commit()
        return skill


class AISkillActionCRUD:
    """Skill Action CRUD"""

    def get_by_id(self, db: Session, action_id: int) -> Optional[AISkillAction]:
        return db.query(AISkillAction).filter(AISkillAction.id == action_id).first()

    def get_by_skill_and_action(
        self,
        db: Session,
        skill_id: int,
        action_name: str
    ) -> Optional[AISkillAction]:
        return db.query(AISkillAction).filter(
            AISkillAction.skill_id == skill_id,
            AISkillAction.action_name == action_name,
            AISkillAction.is_active == 1
        ).first()

    def get_by_skill_id(self, db: Session, skill_id: int) -> List[AISkillAction]:
        return db.query(AISkillAction).filter(
            AISkillAction.skill_id == skill_id,
            AISkillAction.is_active == 1
        ).order_by(AISkillAction.sort_order).all()

    def get_all_active(self, db: Session) -> List[AISkillAction]:
        return db.query(AISkillAction).filter(
            AISkillAction.is_active == 1
        ).order_by(AISkillAction.skill_id, AISkillAction.sort_order).all()

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        skill_id: Optional[int] = None,
        handler_type: Optional[str] = None,
        is_active: Optional[int] = None
    ) -> Tuple[List[AISkillAction], int]:
        query = db.query(AISkillAction)

        if skill_id:
            query = query.filter(AISkillAction.skill_id == skill_id)
        if handler_type:
            query = query.filter(AISkillAction.handler_type == handler_type)
        if is_active is not None:
            query = query.filter(AISkillAction.is_active == is_active)

        total = query.count()
        actions = query.order_by(AISkillAction.sort_order).offset(skip).limit(limit).all()
        return actions, total

    def create(self, db: Session, action_data: dict) -> AISkillAction:
        db_obj = AISkillAction(**action_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, action_id: int, update_data: dict) -> Optional[AISkillAction]:
        action = db.query(AISkillAction).filter(AISkillAction.id == action_id).first()
        if action:
            for field, value in update_data.items():
                setattr(action, field, value)
            db.commit()
            db.refresh(action)
        return action

    def delete(self, db: Session, action_id: int) -> Optional[AISkillAction]:
        action = db.query(AISkillAction).filter(AISkillAction.id == action_id).first()
        if action:
            db.delete(action)
            db.commit()
        return action

    def delete_by_skill_id(self, db: Session, skill_id: int) -> int:
        """删除某 Skill 的所有 Action"""
        count = db.query(AISkillAction).filter(AISkillAction.skill_id == skill_id).count()
        db.query(AISkillAction).filter(AISkillAction.skill_id == skill_id).delete()
        db.commit()
        return count


ai_skill_crud = AISkillCRUD()
ai_skill_action_crud = AISkillActionCRUD()