from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List, Tuple
import uuid
from datetime import datetime

from app.models.operation_log import OperationLog
from app.schemas.operation_log import OperationLogCreate


class OperationLogCRUD:
    def create(self, db: Session, obj_in: OperationLogCreate) -> OperationLog:
        event_id = f"evt_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        db_obj = OperationLog(
            event_id=event_id,
            event_type=obj_in.event_type,
            event_action=obj_in.event_action,
            primary_resource_type=obj_in.primary_resource_type,
            primary_resource_id=obj_in.primary_resource_id,
            secondary_resource_type=obj_in.secondary_resource_type,
            secondary_resource_id=obj_in.secondary_resource_id,
            operator_id=obj_in.operator_id,
            operator_name=obj_in.operator_name,
            operated_at=datetime.now(),
            content=obj_in.content,
            remark=obj_in.remark
        )
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_event_id(self, db: Session, event_id: str) -> Optional[OperationLog]:
        return db.query(OperationLog).filter(OperationLog.event_id == event_id).first()

    def get_by_resource(
        self,
        db: Session,
        primary_resource_type: str,
        primary_resource_id: int,
        skip: int = 0,
        limit: int = 20,
        event_types: Optional[List[str]] = None
    ) -> Tuple[List[OperationLog], int]:
        query = db.query(OperationLog).filter(
            OperationLog.primary_resource_type == primary_resource_type,
            OperationLog.primary_resource_id == primary_resource_id
        )
        
        if event_types:
            query = query.filter(OperationLog.event_type.in_(event_types))
        
        total = query.count()
        logs = query.order_by(OperationLog.operated_at.desc()).offset(skip).limit(limit).all()
        
        return logs, total

    def get_by_operator(
        self,
        db: Session,
        operator_id: str,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[OperationLog], int]:
        query = db.query(OperationLog).filter(OperationLog.operator_id == operator_id)
        
        total = query.count()
        logs = query.order_by(OperationLog.operated_at.desc()).offset(skip).limit(limit).all()
        
        return logs, total

    def get_by_event_types(
        self,
        db: Session,
        event_types: List[str],
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[OperationLog], int]:
        query = db.query(OperationLog).filter(OperationLog.event_type.in_(event_types))
        
        total = query.count()
        logs = query.order_by(OperationLog.operated_at.desc()).offset(skip).limit(limit).all()
        
        return logs, total

    def migrate_lead_logs_to_customer(
        self,
        db: Session,
        lead_id: int,
        customer_id: int
    ):
        """
        将线索的操作记录迁移到客户
        
        当线索转化为客户时，将所有与该线索相关的操作记录（包括跟进记录）
        更新为指向新客户，这样在客户详情中可以看到完整的操作历史
        """
        logs = db.query(OperationLog).filter(
            and_(
                OperationLog.primary_resource_type == "LEAD",
                OperationLog.primary_resource_id == lead_id
            )
        ).all()
        
        for log in logs:
            log.primary_resource_type = "CUSTOMER"
            log.primary_resource_id = customer_id
            if log.secondary_resource_type == "LEAD":
                log.secondary_resource_type = "CUSTOMER"
                if log.secondary_resource_id == lead_id:
                    log.secondary_resource_id = customer_id
        
        db.commit()
        
        return len(logs)


operation_log_crud = OperationLogCRUD()
