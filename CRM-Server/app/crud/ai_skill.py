"""
AI Skill CRUD
"""
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from app.models.ai_skill import AISkill, AISkillAction, AIActionParam


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


class AIActionParamCRUD:
    """Action 参数定义 CRUD"""

    def get_by_id(self, db: Session, param_id: int) -> Optional[AIActionParam]:
        return db.query(AIActionParam).filter(AIActionParam.id == param_id).first()

    def get_by_action_and_param(
        self,
        db: Session,
        action_id: int,
        param_name: str
    ) -> Optional[AIActionParam]:
        return db.query(AIActionParam).filter(
            AIActionParam.action_id == action_id,
            AIActionParam.param_name == param_name
        ).first()

    def get_by_action_id(self, db: Session, action_id: int) -> List[AIActionParam]:
        """获取某 Action 的所有参数定义"""
        return db.query(AIActionParam).filter(
            AIActionParam.action_id == action_id
        ).order_by(AIActionParam.sort_order).all()

    def get_required_params(self, db: Session, action_id: int) -> List[AIActionParam]:
        """获取某 Action 的必填参数"""
        return db.query(AIActionParam).filter(
            AIActionParam.action_id == action_id,
            AIActionParam.required == 1
        ).order_by(AIActionParam.sort_order).all()

    def get_all(self, db: Session) -> List[AIActionParam]:
        return db.query(AIActionParam).order_by(AIActionParam.action_id, AIActionParam.sort_order).all()

    def create(self, db: Session, param_data: dict) -> AIActionParam:
        db_obj = AIActionParam(**param_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def create_batch(self, db: Session, params_data: List[dict]) -> List[AIActionParam]:
        """批量创建参数定义"""
        db_objs = [AIActionParam(**data) for data in params_data]
        db.add_all(db_objs)
        db.commit()
        return db_objs

    def update(self, db: Session, param_id: int, update_data: dict) -> Optional[AIActionParam]:
        param = db.query(AIActionParam).filter(AIActionParam.id == param_id).first()
        if param:
            for field, value in update_data.items():
                setattr(param, field, value)
            db.commit()
            db.refresh(param)
        return param

    def delete(self, db: Session, param_id: int) -> Optional[AIActionParam]:
        param = db.query(AIActionParam).filter(AIActionParam.id == param_id).first()
        if param:
            db.delete(param)
            db.commit()
        return param

    def delete_by_action_id(self, db: Session, action_id: int) -> int:
        """删除某 Action 的所有参数定义"""
        count = db.query(AIActionParam).filter(AIActionParam.action_id == action_id).count()
        db.query(AIActionParam).filter(AIActionParam.action_id == action_id).delete()
        db.commit()
        return count


ai_action_param_crud = AIActionParamCRUD()