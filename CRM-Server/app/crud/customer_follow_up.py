from datetime import datetime
from sqlalchemy.orm import Session
from typing import List, Tuple, Optional
from app.models.customer_follow_up import CustomerFollowUp
from app.models.lead import LeadFollowUp
from app.schemas.customer_follow_up import CustomerFollowUpCreate, CustomerFollowUpUpdate


class CustomerFollowUpCRUD:
    def get_by_id(self, db: Session, follow_up_id: int, team_id: Optional[int] = None) -> CustomerFollowUp:
        query = db.query(CustomerFollowUp).filter(CustomerFollowUp.id == follow_up_id)
        if team_id is not None:
            query = query.filter(CustomerFollowUp.team_id == team_id)
        return query.first()

    def get_by_customer_id(
        self,
        db: Session,
        customer_id: int,
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[CustomerFollowUp], int]:
        query = db.query(CustomerFollowUp).filter(
            CustomerFollowUp.customer_id == customer_id
        )

        if team_id is not None:
            query = query.filter(CustomerFollowUp.team_id == team_id)

        total = query.count()
        follow_ups = query.order_by(
            CustomerFollowUp.created_time.desc()
        ).offset(skip).limit(limit).all()

        return follow_ups, total

    def get_by_original_lead_id(
        self,
        db: Session,
        lead_id: int,
        team_id: Optional[int] = None
    ) -> List[CustomerFollowUp]:
        query = db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead_id
        )
        if team_id is not None:
            query = query.filter(LeadFollowUp.team_id == team_id)
        return query.all()

    def create(
        self,
        db: Session,
        obj_in: CustomerFollowUpCreate,
        customer_id: int,
        creator_id: str,
        team_id: int,
        operator_name: Optional[str] = None,
        original_lead_id: Optional[int] = None
    ) -> CustomerFollowUp:
        from app.services.operation_log_service import operation_log_service

        follow_up_data = obj_in.model_dump()
        follow_up_data['customer_id'] = customer_id
        follow_up_data['creator_id'] = creator_id
        follow_up_data['team_id'] = team_id
        if original_lead_id:
            follow_up_data['original_lead_id'] = original_lead_id

        db_obj = CustomerFollowUp(**follow_up_data)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        
        operation_log_service.log_customer_follow_up(
            db=db,
            customer_id=customer_id,
            follow_up_content=db_obj.content,
            method=db_obj.method,
            operator_id=creator_id,
            operator_name=operator_name,
            next_follow_time=db_obj.next_follow_time.strftime("%Y-%m-%d") if db_obj.next_follow_time else None,
            next_action=db_obj.next_action,
            team_id=team_id,
            follow_up_id=db_obj.id
        )
        
        return db_obj

    def migrate_from_lead(
        self,
        db: Session,
        lead_id: int,
        new_customer_id: int,
        team_id: int
    ) -> List[CustomerFollowUp]:
        lead_follow_ups = db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead_id
        ).all()

        migrated_follow_ups = []
        for lead_follow_up in lead_follow_ups:
            new_follow_up = CustomerFollowUp(
                customer_id=new_customer_id,
                team_id=team_id,
                original_lead_id=lead_id,
                content=lead_follow_up.content,
                method=lead_follow_up.method.value if hasattr(lead_follow_up.method, 'value') else lead_follow_up.method,
                next_follow_time=lead_follow_up.next_follow_time,
                next_action=lead_follow_up.next_action,
                creator_id=lead_follow_up.creator_id,
                created_time=lead_follow_up.created_time
            )
            db.add(new_follow_up)
            migrated_follow_ups.append(new_follow_up)

        db.commit()
        return migrated_follow_ups

    def update(
        self,
        db: Session,
        db_obj: CustomerFollowUp,
        obj_in: CustomerFollowUpUpdate
    ) -> CustomerFollowUp:
        """更新跟进记录"""
        update_data = obj_in.model_dump(exclude_unset=True)

        if update_data:
            for field, value in update_data.items():
                setattr(db_obj, field, value)

            db.commit()
            db.refresh(db_obj)

        return db_obj

    def update_next_time(
        self,
        db: Session,
        db_obj: CustomerFollowUp,
        next_follow_time
    ) -> CustomerFollowUp:
        db_obj.next_follow_time = next_follow_time
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update_effectiveness_status(
        self,
        db: Session,
        follow_up_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> Optional[CustomerFollowUp]:
        follow_up = self.get_by_id(db, follow_up_id)
        if not follow_up:
            return None

        follow_up.effectiveness_status = status
        follow_up.effectiveness_error_message = error_message
        if status in {"PENDING", "GENERATING"}:
            follow_up.effectiveness_score = None
            follow_up.effectiveness_is_valid = None
            follow_up.effectiveness_reason = None
            follow_up.effectiveness_detail_json = None
            follow_up.effectiveness_evaluated_time = None
        elif status == "FAILED":
            follow_up.effectiveness_evaluated_time = datetime.now()

        db.commit()
        db.refresh(follow_up)
        return follow_up

    def update_effectiveness_result(
        self,
        db: Session,
        follow_up_id: int,
        score: int,
        is_valid: bool,
        reason: str,
        detail_json: Optional[str] = None
    ) -> Optional[CustomerFollowUp]:
        follow_up = self.get_by_id(db, follow_up_id)
        if not follow_up:
            return None

        follow_up.effectiveness_score = score
        follow_up.effectiveness_is_valid = is_valid
        follow_up.effectiveness_reason = reason
        follow_up.effectiveness_detail_json = detail_json
        follow_up.effectiveness_status = "COMPLETED"
        follow_up.effectiveness_evaluated_time = datetime.now()
        follow_up.effectiveness_error_message = None

        db.commit()
        db.refresh(follow_up)
        return follow_up

    def delete(self, db: Session, db_obj: CustomerFollowUp) -> CustomerFollowUp:
        db.delete(db_obj)
        db.commit()
        return db_obj


customer_follow_up_crud = CustomerFollowUpCRUD()
