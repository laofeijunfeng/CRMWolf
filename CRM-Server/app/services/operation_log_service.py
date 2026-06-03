"""
操作记录服务助手

该模块提供便捷的方法供业务模块记录操作日志。
使用示例：

    from app.services.operation_log_service import operation_log_service
    from app.constants.operation_log_events import EventTypes, ResourceTypes, EventActions
    
    # 记录线索创建
    operation_log_service.log(
        db=db,
        event_type=EventTypes.LEAD_CREATED,
        event_action=EventActions.CREATE,
        resource_type=ResourceTypes.LEAD,
        resource_id=lead.id,
        operator_id=str(user.id),
        operator_name=user.name,
        content={
            "leadName": lead.lead_name,
            "source": lead.source.value,
            "city": lead.city
        }
    )
"""

from sqlalchemy.orm import Session
from typing import Optional, Dict, Any, List
from app.schemas.operation_log import OperationLogCreate
from app.crud.operation_log import operation_log_crud


class OperationLogService:
    """操作记录服务"""
    
    def log(
        self,
        db: Session,
        event_type: str,
        event_action: str,
        resource_type: str,
        resource_id: int,
        operator_id: str,
        content: Dict[str, Any],
        operator_name: Optional[str] = None,
        secondary_resource_type: Optional[str] = None,
        secondary_resource_id: Optional[int] = None,
        remark: Optional[str] = None,
        team_id: Optional[int] = None
    ) -> Optional[object]:
        """
        记录操作日志

        参数:
            db: 数据库会话
            event_type: 事件类型
            event_action: 事件动作
            resource_type: 资源类型
            resource_id: 资源ID
            operator_id: 操作人ID
            content: 事件内容
            operator_name: 操作人姓名
            secondary_resource_type: 次资源类型
            secondary_resource_id: 次资源ID
            remark: 备注
        """
        try:
            log_data = OperationLogCreate(
                event_type=event_type,
                event_action=event_action,
                primary_resource_type=resource_type,
                primary_resource_id=resource_id,
                secondary_resource_type=secondary_resource_type,
                secondary_resource_id=secondary_resource_id,
                operator_id=operator_id,
                operator_name=operator_name,
                content=content,
                remark=remark
            )

            return operation_log_crud.create(db, log_data, team_id=team_id)
        except Exception as e:
            print(f"记录操作日志失败: {str(e)}")
            return None
    
    def log_lead_created(
        self,
        db: Session,
        lead_id: int,
        lead_name: str,
        source: str,
        city: str,
        operator_id: str,
        operator_name: Optional[str] = None
    ):
        """记录线索创建"""
        return self.log(
            db=db,
            event_type="LEAD_CREATED",
            event_action="CREATE",
            resource_type="LEAD",
            resource_id=lead_id,
            operator_id=operator_id,
            operator_name=operator_name,
            content={
                "leadName": lead_name,
                "source": source,
                "city": city
            }
        )
    
    def log_lead_converted(
        self,
        db: Session,
        lead_id: int,
        lead_name: str,
        customer_id: int,
        customer_name: str,
        operator_id: str,
        operator_name: Optional[str] = None,
        team_id: Optional[int] = None
    ):
        """记录线索转化"""
        return self.log(
            db=db,
            event_type="LEAD_CONVERTED",
            event_action="CONVERT",
            resource_type="LEAD",
            resource_id=lead_id,
            secondary_resource_type="CUSTOMER",
            secondary_resource_id=customer_id,
            operator_id=operator_id,
            operator_name=operator_name,
            team_id=team_id,
            content={
                "originalLeadName": lead_name,
                "newCustomerName": customer_name,
                "newCustomerId": customer_id
            }
        )
    
    def log_customer_follow_up(
        self,
        db: Session,
        customer_id: int,
        follow_up_content: str,
        method: str,
        operator_id: str,
        operator_name: Optional[str] = None,
        next_follow_time: Optional[str] = None,
        next_action: Optional[str] = None,
        team_id: Optional[int] = None,
        follow_up_id: Optional[int] = None
    ):
        """记录客户跟进"""
        content_data = {
            "content": follow_up_content,
            "method": method
        }
        if next_follow_time:
            content_data["next_follow_up_date"] = next_follow_time
        if next_action:
            content_data["next_action"] = next_action
        if follow_up_id:
            content_data["follow_up_id"] = follow_up_id

        return self.log(
            db=db,
            event_type="MANUAL_FOLLOW_UP",
            event_action="CREATE",
            resource_type="CUSTOMER",
            resource_id=customer_id,
            operator_id=operator_id,
            operator_name=operator_name,
            content=content_data,
            team_id=team_id
        )

    def log_lead_follow_up(
        self,
        db: Session,
        lead_id: int,
        follow_up_content: str,
        method: str,
        operator_id: str,
        operator_name: Optional[str] = None,
        next_follow_time: Optional[str] = None,
        next_action: Optional[str] = None,
        team_id: Optional[int] = None,
        follow_up_id: Optional[int] = None
    ):
        """记录线索跟进"""
        content_data = {
            "content": follow_up_content,
            "method": method
        }
        if next_follow_time:
            content_data["next_follow_up_date"] = next_follow_time
        if next_action:
            content_data["next_action"] = next_action
        if follow_up_id:
            content_data["follow_up_id"] = follow_up_id

        return self.log(
            db=db,
            event_type="MANUAL_FOLLOW_UP",
            event_action="CREATE",
            resource_type="LEAD",
            resource_id=lead_id,
            operator_id=operator_id,
            operator_name=operator_name,
            content=content_data,
            team_id=team_id
        )
    
    def log_opportunity_created(
        self,
        db: Session,
        opportunity_id: int,
        opportunity_name: str,
        expected_amount: float,
        stage: str,
        operator_id: str,
        operator_name: Optional[str] = None
    ):
        """记录商机创建"""
        return self.log(
            db=db,
            event_type="OPPORTUNITY_CREATED",
            event_action="CREATE",
            resource_type="OPPORTUNITY",
            resource_id=opportunity_id,
            operator_id=operator_id,
            operator_name=operator_name,
            content={
                "opportunityName": opportunity_name,
                "expectedAmount": expected_amount,
                "stage": stage
            }
        )
    
    def log_contract_created(
        self,
        db: Session,
        contract_id: int,
        contract_name: str,
        amount: float,
        operator_id: str,
        operator_name: Optional[str] = None
    ):
        """记录合同创建"""
        return self.log(
            db=db,
            event_type="CONTRACT_CREATED",
            event_action="CREATE",
            resource_type="CONTRACT",
            resource_id=contract_id,
            operator_id=operator_id,
            operator_name=operator_name,
            content={
                "contractName": contract_name,
                "amount": float(amount)
            }
        )
    
    def log_contract_status_changed(
        self,
        db: Session,
        contract_id: int,
        previous_status: str,
        current_status: str,
        operator_id: str,
        operator_name: Optional[str] = None
    ):
        """记录合同状态变更"""
        return self.log(
            db=db,
            event_type="CONTRACT_STATUS_CHANGED",
            event_action="UPDATE",
            resource_type="CONTRACT",
            resource_id=contract_id,
            operator_id=operator_id,
            operator_name=operator_name,
            content={
                "previousStatus": previous_status,
                "currentStatus": current_status
            }
        )


operation_log_service = OperationLogService()
