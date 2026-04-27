from sqlalchemy.orm import Session
from typing import List, Tuple, Optional
from app.models.customer_follow_up import CustomerFollowUp
from app.models.lead import LeadFollowUp
from app.schemas.customer_follow_up import CustomerFollowUpCreate, CustomerFollowUpUpdate


class CustomerFollowUpCRUD:
    def get_by_id(self, db: Session, follow_up_id: int) -> CustomerFollowUp:
        return db.query(CustomerFollowUp).filter(CustomerFollowUp.id == follow_up_id).first()

    def get_by_customer_id(
        self,
        db: Session,
        customer_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[CustomerFollowUp], int]:
        query = db.query(CustomerFollowUp).filter(
            CustomerFollowUp.customer_id == customer_id
        )
        
        total = query.count()
        follow_ups = query.order_by(
            CustomerFollowUp.created_time.desc()
        ).offset(skip).limit(limit).all()
        
        return follow_ups, total

    def get_by_original_lead_id(
        self,
        db: Session,
        lead_id: int
    ) -> List[CustomerFollowUp]:
        return db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead_id
        ).all()

    def create(
        self,
        db: Session,
        obj_in: CustomerFollowUpCreate,
        customer_id: int,
        creator_id: str,
        operator_name: Optional[str] = None,
        original_lead_id: Optional[int] = None
    ) -> CustomerFollowUp:
        from app.services.operation_log_service import operation_log_service
        
        follow_up_data = obj_in.model_dump()
        follow_up_data['customer_id'] = customer_id
        follow_up_data['creator_id'] = creator_id
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
            next_follow_time=db_obj.next_follow_time.strftime("%Y-%m-%d") if db_obj.next_follow_time else None
        )
        
        return db_obj

    def migrate_from_lead(
        self,
        db: Session,
        lead_id: int,
        new_customer_id: int
    ) -> List[CustomerFollowUp]:
        lead_follow_ups = db.query(LeadFollowUp).filter(
            LeadFollowUp.lead_id == lead_id
        ).all()
        
        migrated_follow_ups = []
        for lead_follow_up in lead_follow_ups:
            new_follow_up = CustomerFollowUp(
                customer_id=new_customer_id,
                original_lead_id=lead_id,
                content=lead_follow_up.content,
                method=lead_follow_up.method,
                next_follow_time=lead_follow_up.next_follow_time,
                creator_id=lead_follow_up.creator_id,
                created_time=lead_follow_up.created_time
            )
            db.add(new_follow_up)
            migrated_follow_ups.append(new_follow_up)
        
        db.commit()
        return migrated_follow_ups

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

    def delete(self, db: Session, db_obj: CustomerFollowUp) -> CustomerFollowUp:
        db.delete(db_obj)
        db.commit()
        return db_obj


customer_follow_up_crud = CustomerFollowUpCRUD()
