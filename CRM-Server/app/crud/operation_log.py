from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List, Tuple, Dict, Any
import uuid
from datetime import datetime, timedelta

from app.models.operation_log import OperationLog
from app.schemas.operation_log import OperationLogCreate


class OperationLogCRUD:
    def create(self, db: Session, obj_in: OperationLogCreate, team_id: Optional[int] = None) -> OperationLog:
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
            team_id=team_id,
            operated_at=datetime.now(),
            content=obj_in.content,
            remark=obj_in.remark
        )

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_by_event_id(self, db: Session, event_id: str, team_id: Optional[int] = None) -> Optional[OperationLog]:
        query = db.query(OperationLog).filter(OperationLog.event_id == event_id)
        if team_id is not None:
            query = query.filter(OperationLog.team_id == team_id)
        return query.first()

    def get_by_resource(
        self,
        db: Session,
        primary_resource_type: str,
        primary_resource_id: int,
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        event_types: Optional[List[str]] = None
    ) -> Tuple[List[OperationLog], int]:
        query = db.query(OperationLog).filter(
            OperationLog.primary_resource_type == primary_resource_type,
            OperationLog.primary_resource_id == primary_resource_id
        )

        if team_id is not None:
            query = query.filter(OperationLog.team_id == team_id)

        if event_types:
            query = query.filter(OperationLog.event_type.in_(event_types))

        total = query.count()
        logs = query.order_by(OperationLog.operated_at.desc()).offset(skip).limit(limit).all()

        return logs, total

    def get_by_operator(
        self,
        db: Session,
        operator_id: str,
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[OperationLog], int]:
        query = db.query(OperationLog).filter(OperationLog.operator_id == operator_id)

        if team_id is not None:
            query = query.filter(OperationLog.team_id == team_id)

        total = query.count()
        logs = query.order_by(OperationLog.operated_at.desc()).offset(skip).limit(limit).all()

        return logs, total

    def get_by_event_types(
        self,
        db: Session,
        event_types: List[str],
        team_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[List[OperationLog], int]:
        query = db.query(OperationLog).filter(OperationLog.event_type.in_(event_types))

        if team_id is not None:
            query = query.filter(OperationLog.team_id == team_id)

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

    def get_multi(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        event_type: Optional[str] = None,
        operator_id: Optional[str] = None
    ) -> Tuple[List[OperationLog], int]:
        """获取团队的操作日志列表"""
        query = db.query(OperationLog).filter(OperationLog.team_id == team_id)

        if event_type:
            query = query.filter(OperationLog.event_type == event_type)

        if operator_id:
            query = query.filter(OperationLog.operator_id == operator_id)

        total = query.count()
        logs = query.order_by(OperationLog.operated_at.desc()).offset(skip).limit(limit).all()

        return logs, total

    # ==================== 撤销支持方法（新增） ====================

    def get_by_id(self, db: Session, operation_id: int) -> Optional[OperationLog]:
        """根据ID获取操作日志"""
        return db.query(OperationLog).filter(OperationLog.id == operation_id).first()

    def update(self, db: Session, operation_id: int, update_data: Dict[str, Any]) -> Optional[OperationLog]:
        """更新操作日志"""
        log = self.get_by_id(db, operation_id)
        if not log:
            return None

        for key, value in update_data.items():
            if hasattr(log, key):
                setattr(log, key, value)

        db.commit()
        db.refresh(log)
        return log

    def get_by_workflow_session(
        self,
        db: Session,
        session_id: str
    ) -> List[OperationLog]:
        """根据 Workflow Session ID 获取操作日志（按时间正序）"""
        return db.query(OperationLog).filter(
            OperationLog.workflow_session_id == session_id
        ).order_by(OperationLog.operated_at.asc()).all()

    def log_with_undo(
        self,
        db: Session,
        event_type: str,
        event_action: str,
        primary_resource_type: str,
        primary_resource_id: int,
        operator_id: str,
        operator_name: str = None,
        team_id: int = None,
        undoable: bool = True,
        undo_ttl: int = 10,
        workflow_session_id: str = None,
        step_id: str = None,
        before_snapshot: Dict = None,
        after_snapshot: Dict = None,
        content: Dict = None,
        parent_operation_id: int = None
    ) -> OperationLog:
        """
        创建带撤销配置的操作日志

        Args:
            db: 数据库会话
            event_type: 事件类型
            event_action: 事件动作
            primary_resource_type: 主资源类型
            primary_resource_id: 主资源ID
            operator_id: 操作人ID
            operator_name: 操作人姓名
            team_id: 团队ID
            undoable: 是否可撤销
            undo_ttl: 撤销窗口（秒）
            workflow_session_id: Workflow Session ID
            step_id: Workflow 步骤ID
            before_snapshot: 操作前快照
            after_snapshot: 操作后快照
            content: 事件内容
            parent_operation_id: 父操作ID

        Returns:
            创建的操作日志
        """
        event_id = f"evt_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        db_obj = OperationLog(
            event_id=event_id,
            event_type=event_type,
            event_action=event_action,
            primary_resource_type=primary_resource_type,
            primary_resource_id=primary_resource_id,
            operator_id=operator_id,
            operator_name=operator_name,
            team_id=team_id,
            operated_at=datetime.now(),
            content=content or {},
            undoable=undoable,
            undo_ttl=undo_ttl,
            undo_deadline=datetime.now() + timedelta(seconds=undo_ttl) if undoable else None,
            workflow_session_id=workflow_session_id,
            step_id=step_id,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            parent_operation_id=parent_operation_id
        )

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def get_recent_undoable(
        self,
        db: Session,
        operator_id: str,
        within_seconds: int = 60
    ) -> Optional[OperationLog]:
        """获取用户最近的可撤销操作"""
        cutoff_time = datetime.now() - timedelta(seconds=within_seconds)

        return db.query(OperationLog).filter(
            OperationLog.operator_id == operator_id,
            OperationLog.undoable == True,
            OperationLog.undone == False,
            OperationLog.undo_deadline > datetime.now(),
            OperationLog.operated_at >= cutoff_time
        ).order_by(OperationLog.operated_at.desc()).first()


operation_log_crud = OperationLogCRUD()
