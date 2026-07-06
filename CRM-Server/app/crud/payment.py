from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text
from sqlalchemy.orm import joinedload
from typing import Optional, List, Tuple
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.models.payment import PaymentPlan, PaymentRecord, PaymentPlanStatus, PaymentConfirmationStatus
from app.models.contract import Contract, ContractStatus, PaymentStatus
from app.schemas.payment import (
    PaymentPlanCreate, PaymentPlanUpdate, PaymentPlanBatchCreate,
    PaymentRecordCreate, PaymentRecordUpdate
)


class PaymentPlanCRUD:
    def get_by_id(self, db: Session, plan_id: int, team_id: Optional[int] = None) -> Optional[PaymentPlan]:
        query = db.query(PaymentPlan).filter(PaymentPlan.id == plan_id)
        if team_id is not None:
            query = query.filter(PaymentPlan.team_id == team_id)
        return query.first()

    def get_by_contract_id(self, db: Session, contract_id: int, team_id: Optional[int] = None, status: Optional[str] = None) -> List[PaymentPlan]:
        query = db.query(PaymentPlan).filter(PaymentPlan.contract_id == contract_id)

        if team_id is not None:
            query = query.filter(PaymentPlan.team_id == team_id)

        if status:
            query = query.filter(PaymentPlan.status == status)

        return query.order_by(PaymentPlan.due_date.asc()).all()

    def get_multi(self, db: Session, team_id: int, skip: int = 0, limit: int = 100, status: Optional[str] = None) -> Tuple[List[PaymentPlan], int]:
        query = db.query(PaymentPlan).filter(PaymentPlan.team_id == team_id)

        if status:
            query = query.filter(PaymentPlan.status == status)

        total = query.count()
        plans = query.order_by(PaymentPlan.due_date.asc()).offset(skip).limit(limit).all()

        return plans, total

    def list_plans(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        owner_id: Optional[str] = None,
        due_date_start: Optional[date] = None,
        due_date_end: Optional[date] = None,
        current_user_id: Optional[str] = None
    ) -> Tuple[List[PaymentPlan], int]:
        from app.models.contract import Contract
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity

        plans_query = db.query(PaymentPlan).join(Contract, PaymentPlan.contract_id == Contract.id)
        plans_query = plans_query.filter(PaymentPlan.team_id == team_id)
        
        if status:
            plans_query = plans_query.filter(PaymentPlan.status == status)
        
        if due_date_start:
            plans_query = plans_query.filter(PaymentPlan.due_date >= due_date_start)
        
        if due_date_end:
            plans_query = plans_query.filter(PaymentPlan.due_date <= due_date_end)
        
        if owner_id:
            plans_query = plans_query.filter(Contract.creator_id == owner_id)
        
        if current_user_id:
            plans_query = plans_query.filter(Contract.creator_id == current_user_id)
        
        total = plans_query.count()
        
        plans = plans_query.order_by(PaymentPlan.due_date.asc()).offset(skip).limit(limit).all()
        
        for plan in plans:
            contract = db.query(Contract).filter(Contract.id == plan.contract_id).first()
            if contract:
                plan.contract = contract
                if contract.customer_id:
                    customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
                    if customer:
                        contract.customer = customer
                if contract.opportunity_id:
                    opportunity = db.query(Opportunity).filter(Opportunity.id == contract.opportunity_id).first()
                    if opportunity:
                        contract.opportunity = opportunity
        
        return plans, total
    
    def create(self, db: Session, contract_id: int, obj_in: PaymentPlanCreate, team_id: int) -> PaymentPlan:
        db_plan = PaymentPlan(
            contract_id=contract_id,
            team_id=team_id,
            **obj_in.model_dump()
        )
        db.add(db_plan)
        db.commit()
        db.refresh(db_plan)
        return db_plan

    def batch_create(self, db: Session, contract_id: int, plans_data: List[PaymentPlanCreate], creator_id: str, team_id: int) -> List[PaymentPlan]:
        from app.crud.user import user_crud
        from app.crud.customer import customer_crud
        from app.models.payment import PaymentPlan
        from app.services.operation_log_service import operation_log_service
        from app.schemas.payment import PaymentPlanResponse  # 导入 Pydantic schema

        total_planned = sum(p.planned_amount for p in plans_data)

        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            raise ValueError("合同不存在")

        if total_planned > float(contract.total_amount):
            raise ValueError(f"回款计划总额({total_planned})不能超过合同总额({contract.total_amount})")

        plans = []
        for plan_data in plans_data:
            db_plan = PaymentPlan(
                contract_id=contract_id,
                team_id=team_id,
                **plan_data.model_dump()
            )
            db.add(db_plan)
            plans.append(db_plan)

        db.commit()

        # 刷新对象并确保所有字段加载（避免延迟加载）
        for plan in plans:
            db.refresh(plan)
            # 显式加载关系字段（如有）
            # db.expunge(plan)  # 将对象从 Session分离，但保持属性可访问

        # 转换为 Pydantic schema（避免 detached 对象问题）
        plan_responses = [PaymentPlanResponse.model_validate(plan) for plan in plans]
        
        operator = user_crud.get_by_id(db, int(creator_id))
        operator_name = operator.name if operator else None

        customer = customer_crud.get_by_id(db, contract.customer_id)

        operation_log_service.log(
            db=db,
            event_type="PAYMENT_PLAN_CREATED",
            event_action="CREATE",
            resource_type="CUSTOMER",
            resource_id=contract.customer_id,
            secondary_resource_type="CONTRACT",
            secondary_resource_id=contract_id,
            operator_id=creator_id,
            operator_name=operator_name,
            content={
                "contractNumber": contract.contract_number,
                "contractName": contract.contract_name,
                "planCount": len(plans),
                "totalPlannedAmount": float(total_planned),
                "customerId": contract.customer_id,
                "customerName": customer.account_name if customer else None
            }
        )

        return plan_responses  # 返回 Pydantic schema 列表，而非 ORM 对象

    def update(self, db: Session, db_obj: PaymentPlan, obj_in: PaymentPlanUpdate) -> PaymentPlan:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, plan_id: int, team_id: int) -> bool:
        plan = self.get_by_id(db, plan_id, team_id)  # 使用 team_id 进行团队隔离验证
        if not plan:
            return False

        if plan.payment_records:
            raise ValueError("存在关联的回款记录，无法删除")

        db.delete(plan)
        db.commit()
        return True
    
    def update_status(self, db: Session, plan: PaymentPlan) -> PaymentPlan:
        from app.models.payment import PaymentRecord
        
        # 从数据库重新查询回款记录，确保获取最新数据
        payment_records = db.query(PaymentRecord).filter(
            PaymentRecord.payment_plan_id == plan.id
        ).all()
        
        total_paid = sum(float(r.actual_amount) for r in payment_records)
        planned = float(plan.planned_amount)
        
        if total_paid >= planned:
            plan.status = PaymentPlanStatus.COMPLETED
        elif total_paid > 0:
            plan.status = PaymentPlanStatus.PARTIAL
        elif plan.due_date < date.today():
            plan.status = PaymentPlanStatus.OVERDUE
        else:
            plan.status = PaymentPlanStatus.PENDING
        
        db.commit()
        db.refresh(plan)
        return plan
    
    def get_upcoming_payments(self, db: Session, team_id: int, days: int = 7) -> List[PaymentPlan]:
        from app.models.contract import Contract
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity

        target_date = date.today() + timedelta(days=days)

        plans = db.query(PaymentPlan).filter(
            and_(
                PaymentPlan.team_id == team_id,
                PaymentPlan.status == PaymentPlanStatus.PENDING,
                PaymentPlan.due_date <= target_date,
                PaymentPlan.due_date >= date.today()
            )
        ).order_by(PaymentPlan.due_date.asc()).all()
        
        for plan in plans:
            contract = db.query(Contract).filter(Contract.id == plan.contract_id).first()
            if contract:
                plan.contract = contract
                if contract.customer_id:
                    customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
                    if customer:
                        contract.customer = customer
                if contract.opportunity_id:
                    opportunity = db.query(Opportunity).filter(Opportunity.id == contract.opportunity_id).first()
                    if opportunity:
                        contract.opportunity = opportunity
        
        return plans
    
    def get_overdue_payments(self, db: Session, team_id: int) -> List[PaymentPlan]:
        from app.models.contract import Contract
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity

        plans = db.query(PaymentPlan).filter(
            and_(
                PaymentPlan.team_id == team_id,
                PaymentPlan.due_date < date.today(),
                PaymentPlan.status != PaymentPlanStatus.COMPLETED
            )
        ).order_by(PaymentPlan.due_date.asc()).all()
        
        for plan in plans:
            contract = db.query(Contract).filter(Contract.id == plan.contract_id).first()
            if contract:
                plan.contract = contract
                if contract.customer_id:
                    customer = db.query(Customer).filter(Customer.id == contract.customer_id).first()
                    if customer:
                        contract.customer = customer
                if contract.opportunity_id:
                    opportunity = db.query(Opportunity).filter(Opportunity.id == contract.opportunity_id).first()
                    if opportunity:
                        contract.opportunity = opportunity
        
        return plans


class PaymentRecordCRUD:
    def get_by_id(self, db: Session, record_id: int, team_id: Optional[int] = None) -> Optional[PaymentRecord]:
        query = db.query(PaymentRecord).filter(PaymentRecord.id == record_id)
        if team_id is not None:
            query = query.filter(PaymentRecord.team_id == team_id)
        return query.first()

    def get_by_plan_id(self, db: Session, plan_id: int, team_id: Optional[int] = None) -> List[PaymentRecord]:
        query = db.query(PaymentRecord).filter(
            PaymentRecord.payment_plan_id == plan_id
        )
        if team_id is not None:
            query = query.filter(PaymentRecord.team_id == team_id)
        return query.order_by(PaymentRecord.payment_date.desc()).all()

    def list_records(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        contract_id: Optional[int] = None,
        payment_plan_id: Optional[int] = None,
        payment_date_start: Optional[date] = None,
        payment_date_end: Optional[date] = None,
        min_amount: Optional[float] = None,
        creator_id: Optional[str] = None,
        current_user_id: Optional[str] = None,
        approval_status: Optional[str] = None
    ) -> Tuple[List[PaymentRecord], int]:
        from app.models.contract import Contract
        from app.models.customer import Customer
        from app.models.opportunity import Opportunity
        from app.models.approval import Approval, ApprovalStatus
        from app.constants.business_types import BusinessType

        records_query = db.query(PaymentRecord).join(
            PaymentPlan, PaymentRecord.payment_plan_id == PaymentPlan.id
        ).join(
            Contract, PaymentPlan.contract_id == Contract.id
        )
        records_query = records_query.filter(PaymentRecord.team_id == team_id)

        # Task 1.4: approval_status filtering
        if approval_status == 'pending_submit':
            # 待提交审批：无approval_id，confirmation_status='PENDING'
            records_query = records_query.filter(
                PaymentRecord.approval_id.is_(None),
                PaymentRecord.confirmation_status == PaymentConfirmationStatus.PENDING
            )
        elif approval_status == 'pending_approval':
            # 审批中：有approval_id，approval.status='PENDING'
            records_query = records_query.join(
                Approval, PaymentRecord.approval_id == Approval.id
            ).filter(
                PaymentRecord.approval_id.isnot(None),
                Approval.status == ApprovalStatus.PENDING
            )
        elif approval_status == 'approved':
            # 已通过：confirmation_status='CONFIRMED'
            records_query = records_query.filter(
                PaymentRecord.confirmation_status == PaymentConfirmationStatus.CONFIRMED
            )
        elif approval_status == 'rejected':
            # 已驳回：approval.status='REJECTED'
            records_query = records_query.join(
                Approval, PaymentRecord.approval_id == Approval.id
            ).filter(
                Approval.status == ApprovalStatus.REJECTED
            )
        
        if contract_id:
            records_query = records_query.filter(PaymentPlan.contract_id == contract_id)
        
        if payment_plan_id:
            records_query = records_query.filter(PaymentRecord.payment_plan_id == payment_plan_id)
        
        if payment_date_start:
            records_query = records_query.filter(PaymentRecord.payment_date >= payment_date_start)
        
        if payment_date_end:
            records_query = records_query.filter(PaymentRecord.payment_date <= payment_date_end)
        
        if min_amount:
            records_query = records_query.filter(PaymentRecord.actual_amount >= min_amount)
        
        if creator_id:
            records_query = records_query.filter(PaymentRecord.creator_id == creator_id)
        
        if current_user_id:
            records_query = records_query.filter(Contract.creator_id == current_user_id)
        
        total = records_query.count()
        records = records_query.order_by(PaymentRecord.payment_date.desc()).offset(skip).limit(limit).all()

        for record in records:
            payment_plan = record.payment_plan if hasattr(record, 'payment_plan') else None
            if not payment_plan:
                payment_plan = db.query(PaymentPlan).filter(PaymentPlan.id == record.payment_plan_id).first()
                if payment_plan:
                    record.payment_plan = payment_plan

            if payment_plan:
                contract = payment_plan.contract if hasattr(payment_plan, 'contract') else None
                if not contract:
                    contract = db.query(Contract).filter(Contract.id == payment_plan.contract_id).first()
                    if contract:
                        payment_plan.contract = contract

                # Note: Customer and Opportunity are optional - may not be loaded in test fixtures
                # The API layer will handle enrichment if needed

        return records, total
    
    def create(self, db: Session, plan_id: int, obj_in: PaymentRecordCreate, creator_id: str, creator_name: str, team_id: int) -> PaymentRecord:
        from app.crud.user import user_crud
        from app.crud.customer import customer_crud
        from app.services.operation_log_service import operation_log_service

        plan = db.query(PaymentPlan).filter(PaymentPlan.id == plan_id).first()
        if not plan:
            raise ValueError("回款计划不存在")

        total_paid = sum(float(r.actual_amount) for r in plan.payment_records)
        planned = float(plan.planned_amount)

        if total_paid + obj_in.actual_amount > planned:
            raise ValueError(f"回款金额超出计划，计划金额: {planned}，已回款: {total_paid}，本次: {obj_in.actual_amount}")

        db_record = PaymentRecord(
            payment_plan_id=plan_id,
            team_id=team_id,
            **obj_in.model_dump(),
            creator_id=creator_id,
            creator_name=creator_name
        )
        db.add(db_record)
        db.flush()
        
        from app.crud.payment import payment_plan_crud
        payment_plan_crud.update_status(db, plan)
        self._update_contract_payment_status(db, plan.contract_id)
        
        db.commit()
        db.refresh(db_record)

        # 填充关联对象，避免 DetachedInstanceError
        db_record.payment_plan = plan
        if plan.contract:
            db_record.payment_plan.contract = plan.contract
        # 重新获取 contract 以确保所有属性可用
        contract = db.query(Contract).filter(Contract.id == plan.contract_id).first()
        if contract:
            db_record.payment_plan.contract = contract

            operator = user_crud.get_by_id(db, int(creator_id))
            operator_name_display = operator.name if operator else creator_name

            customer = customer_crud.get_by_id(db, contract.customer_id)

            operation_log_service.log(
                db=db,
                event_type="PAYMENT_RECEIVED",
                event_action="CREATE",
                resource_type="CUSTOMER",
                resource_id=contract.customer_id,
                secondary_resource_type="CONTRACT",
                secondary_resource_id=contract.id,
                operator_id=creator_id,
                operator_name=operator_name_display,
                content={
                    "contractNumber": contract.contract_number,
                    "contractName": contract.contract_name,
                    "actualAmount": float(db_record.actual_amount),
                    "paymentDate": db_record.payment_date.isoformat() if db_record.payment_date else None,
                    "customerId": contract.customer_id,
                    "customerName": customer.account_name if customer else None
                }
            )

        # 自动提交审批
        self._auto_submit_approval(db, db_record, creator_id, creator_name)

        return db_record
    
    def update(self, db: Session, db_obj: PaymentRecord, obj_in: PaymentRecordUpdate) -> PaymentRecord:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        
        from app.crud.payment import payment_plan_crud
        plan = db.query(PaymentPlan).filter(PaymentPlan.id == db_obj.payment_plan_id).first()
        if plan:
            payment_plan_crud.update_status(db, plan)
            self._update_contract_payment_status(db, plan.contract_id)
        
        db.refresh(db_obj)
        return db_obj
    
    def delete(self, db: Session, record_id: int, team_id: int) -> bool:
        record = self.get_by_id(db, record_id, team_id)  # 使用 team_id 进行团队隔离验证
        if not record:
            return False

        plan_id = record.payment_plan_id
        db.delete(record)
        db.flush()

        from app.crud.payment import payment_plan_crud
        plan = db.query(PaymentPlan).filter(PaymentPlan.id == plan_id).first()
        if plan:
            payment_plan_crud.update_status(db, plan)
            self._update_contract_payment_status(db, plan.contract_id)

        db.commit()
        return True
    
    def confirm_payment(
        self,
        db: Session,
        record_id: int,
        confirmer_id: str,
        confirmer_name: str,
        action: str,
        notes: Optional[str] = None,
        invoice_application_ids: Optional[List[int]] = None
    ) -> Optional[PaymentRecord]:
        from app.models.payment import PaymentConfirmationStatus
        from app.models.invoice import InvoiceApplication
        
        record = self.get_by_id(db, record_id)
        if not record:
            return None
        
        if record.confirmation_status != PaymentConfirmationStatus.PENDING:
            raise ValueError("只能确认待确认状态的回款记录")
        
        if action == "confirm":
            record.confirmation_status = PaymentConfirmationStatus.CONFIRMED
        elif action == "dispute":
            record.confirmation_status = PaymentConfirmationStatus.DISPUTED
        else:
            raise ValueError("无效的确认操作")
        
        record.confirmed_by = confirmer_id
        record.confirmed_by_name = confirmer_name
        record.confirmed_time = datetime.now()
        record.confirmation_notes = notes
        
        if invoice_application_ids:
            invoice_applications = db.query(InvoiceApplication).filter(
                InvoiceApplication.id.in_(invoice_application_ids)
            ).all()
            
            for inv_app in invoice_applications:
                if inv_app.payment_record_id is not None:
                    raise ValueError(f"发票申请 {inv_app.application_number} 已经关联了回款记录")
            
            for inv_app in invoice_applications:
                inv_app.payment_record_id = record_id
        
        db.commit()
        db.refresh(record)
        return record
    
    def _update_contract_payment_status(self, db: Session, contract_id: int):
        from app.models.contract import Contract
        from app.models.payment import PaymentPlanStatus
        
        contract = db.query(Contract).filter(Contract.id == contract_id).first()
        if not contract:
            return
        
        plans = db.query(PaymentPlan).filter(PaymentPlan.contract_id == contract_id).all()
        
        if not plans:
            contract.payment_status = PaymentStatus.UNPAID
            contract.total_paid_amount = 0
        else:
            total_paid = sum(float(r.actual_amount) for p in plans for r in p.payment_records)
            contract.total_paid_amount = total_paid
            
            total_planned = sum(float(p.planned_amount) for p in plans)
            
            has_overdue = any(p.status == PaymentPlanStatus.OVERDUE for p in plans)
            all_completed = all(p.status == PaymentPlanStatus.COMPLETED for p in plans)
            
            if has_overdue:
                contract.payment_status = PaymentStatus.OVERDUE
            elif total_paid >= total_planned:
                contract.payment_status = PaymentStatus.COMPLETED
            elif total_paid > 0:
                contract.payment_status = PaymentStatus.PARTIAL
            else:
                contract.payment_status = PaymentStatus.UNPAID
        
        db.commit()

    def _auto_submit_approval(self, db: Session, record: PaymentRecord, creator_id: str, creator_name: str):
        """
        登记回款后自动提交审批（Task: 登记回款自动提交审批）

        流程：
        1. 调用 match_flow_generic 匹配 PAYMENT 审批流程
        2. 若未匹配 -> 免审批直通（返回，不报错）
        3. 若匹配 -> create_approval_generic 创建审批实例
        """
        from app.crud.approval import approval_crud, approval_flow_crud
        from app.models.approval import BusinessType

        # 匹配 PAYMENT 审批流程（金额=回款金额）
        flow, error_msg = approval_flow_crud.match_flow_generic(
            db,
            business_type=BusinessType.PAYMENT,
            team_id=record.team_id,
            amount=record.actual_amount,
            license_type=None
        )

        # 未匹配 = 免审批直通（决策1）
        if flow is None:
            return

        # 创建审批实例
        approval_crud.create_approval_generic(
            db,
            business_type=BusinessType.PAYMENT,
            business_id=record.id,
            team_id=record.team_id,
            flow=flow,
            submitter_id=creator_id,
            submitter_name=creator_name
        )


def query_pending_approval_me(db: Session, team_id: int, user_roles: List[str]) -> int:
    """
    Task 1.4: 查询待我审批的回款记录数量

    Args:
        db: 数据库会话
        team_id: 团队ID
        user_roles: 当前用户的角色代码列表

    Returns:
        待我审批的数量
    """
    from app.models.approval import Approval, ApprovalNode, ApprovalStatus
    from app.constants.business_types import BusinessType

    if not user_roles:
        return 0

    # 查询当前审批节点角色属于当前用户角色集的审批记录
    pending_approval_me_count = db.query(Approval).join(
        ApprovalNode, Approval.current_node_id == ApprovalNode.id
    ).join(
        PaymentRecord, Approval.business_id == PaymentRecord.id
    ).join(
        PaymentPlan, PaymentRecord.payment_plan_id == PaymentPlan.id
    ).filter(
        Approval.business_type == BusinessType.PAYMENT,
        Approval.team_id == team_id,
        Approval.status == ApprovalStatus.PENDING,
        PaymentPlan.team_id == team_id,
        ApprovalNode.approve_role.in_(user_roles)
    ).count()

    return pending_approval_me_count


payment_plan_crud = PaymentPlanCRUD()
payment_record_crud = PaymentRecordCRUD()
