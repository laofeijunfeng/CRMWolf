from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import Optional, List, Tuple
from datetime import date

from app.models.invoice import InvoiceTitle, InvoiceApplication, InvoiceApplicationStatus, InvoiceType
from app.models.payment import PaymentPlan, PaymentRecord
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.schemas.invoice import (
    InvoiceTitleCreate, InvoiceTitleUpdate,
    InvoiceApplicationCreate, InvoiceApplicationUpdate
)


class InvoiceTitleCRUD:
    def get_by_id(self, db: Session, title_id: int, team_id: Optional[int] = None) -> Optional[InvoiceTitle]:
        query = db.query(InvoiceTitle).filter(InvoiceTitle.id == title_id)
        if team_id is not None:
            query = query.filter(InvoiceTitle.team_id == team_id)
        return query.first()

    def get_by_customer_id(self, db: Session, customer_id: int, team_id: Optional[int] = None) -> List[InvoiceTitle]:
        query = db.query(InvoiceTitle).filter(
            InvoiceTitle.customer_id == customer_id
        )
        if team_id is not None:
            query = query.filter(InvoiceTitle.team_id == team_id)
        return query.order_by(InvoiceTitle.is_default.desc(), InvoiceTitle.created_time.desc()).all()

    def get_default_title(self, db: Session, customer_id: int, team_id: Optional[int] = None) -> Optional[InvoiceTitle]:
        query = db.query(InvoiceTitle).filter(
            and_(
                InvoiceTitle.customer_id == customer_id,
                InvoiceTitle.is_default == True
            )
        )
        if team_id is not None:
            query = query.filter(InvoiceTitle.team_id == team_id)
        return query.first()

    def get_by_taxpayer_id(self, db: Session, customer_id: int, taxpayer_id: str, team_id: Optional[int] = None) -> Optional[InvoiceTitle]:
        query = db.query(InvoiceTitle).filter(
            and_(
                InvoiceTitle.customer_id == customer_id,
                InvoiceTitle.taxpayer_id == taxpayer_id
            )
        )
        if team_id is not None:
            query = query.filter(InvoiceTitle.team_id == team_id)
        return query.first()

    def create(self, db: Session, customer_id: int, obj_in: InvoiceTitleCreate, team_id: int) -> InvoiceTitle:
        db_obj = InvoiceTitle(
            customer_id=customer_id,
            team_id=team_id,
            **obj_in.model_dump()
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, db_obj: InvoiceTitle, obj_in: InvoiceTitleUpdate) -> InvoiceTitle:
        update_data = obj_in.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def set_default(self, db: Session, customer_id: int, title_id: int) -> Optional[InvoiceTitle]:
        db.query(InvoiceTitle).filter(
            and_(
                InvoiceTitle.customer_id == customer_id,
                InvoiceTitle.is_default == True
            )
        ).update({"is_default": False})
        
        title = self.get_by_id(db, title_id)
        if title and title.customer_id == customer_id:
            title.is_default = True
            db.commit()
            db.refresh(title)
            return title
        return None
    
    def delete(self, db: Session, title_id: int) -> bool:
        title = self.get_by_id(db, title_id)
        if not title:
            return False
        
        db.delete(title)
        db.commit()
        return True


class InvoiceApplicationCRUD:
    def get_by_id(self, db: Session, application_id: int, team_id: Optional[int] = None) -> Optional[InvoiceApplication]:
        query = db.query(InvoiceApplication).filter(InvoiceApplication.id == application_id)
        if team_id is not None:
            query = query.filter(InvoiceApplication.team_id == team_id)
        return query.first()

    def get_by_application_number(self, db: Session, application_number: str, team_id: Optional[int] = None) -> Optional[InvoiceApplication]:
        query = db.query(InvoiceApplication).filter(
            InvoiceApplication.application_number == application_number
        )
        if team_id is not None:
            query = query.filter(InvoiceApplication.team_id == team_id)
        return query.first()

    def get_by_payment_plan(self, db: Session, payment_plan_id: int, team_id: Optional[int] = None) -> List[InvoiceApplication]:
        query = db.query(InvoiceApplication).filter(
            InvoiceApplication.payment_plan_id == payment_plan_id
        )
        if team_id is not None:
            query = query.filter(InvoiceApplication.team_id == team_id)
        return query.order_by(InvoiceApplication.created_time.desc()).all()

    def get_by_contract(self, db: Session, contract_id: int, team_id: Optional[int] = None) -> List[InvoiceApplication]:
        query = db.query(InvoiceApplication).filter(
            InvoiceApplication.contract_id == contract_id
        )
        if team_id is not None:
            query = query.filter(InvoiceApplication.team_id == team_id)
        return query.order_by(InvoiceApplication.created_time.desc()).all()

    def get_by_customer(self, db: Session, customer_id: int, team_id: Optional[int] = None) -> List[InvoiceApplication]:
        query = db.query(InvoiceApplication).filter(
            InvoiceApplication.customer_id == customer_id
        )
        if team_id is not None:
            query = query.filter(InvoiceApplication.team_id == team_id)
        return query.order_by(InvoiceApplication.created_time.desc()).all()

    def list_applications(
        self,
        db: Session,
        team_id: int,
        skip: int = 0,
        limit: int = 100,
        customer_id: Optional[int] = None,
        contract_id: Optional[int] = None,
        status: Optional[str] = None,
        applicant_id: Optional[str] = None,
        current_user_id: Optional[str] = None
    ) -> Tuple[List[InvoiceApplication], int]:
        from app.models.user import User

        query = db.query(InvoiceApplication).filter(InvoiceApplication.team_id == team_id)
        
        if customer_id:
            query = query.filter(InvoiceApplication.customer_id == customer_id)
        
        if contract_id:
            query = query.filter(InvoiceApplication.contract_id == contract_id)
        
        if status:
            query = query.filter(InvoiceApplication.status == status)
        
        if applicant_id:
            query = query.filter(InvoiceApplication.applicant_id == applicant_id)
        
        if current_user_id:
            query = query.join(Customer, InvoiceApplication.customer_id == Customer.id).filter(
                Customer.owner_id == current_user_id
            )
        
        total = query.count()
        applications = query.order_by(InvoiceApplication.created_time.desc()).offset(skip).limit(limit).all()
        
        return applications, total
    
    def create(
        self,
        db: Session,
        obj_in: InvoiceApplicationCreate,
        applicant_id: str,
        team_id: int
    ) -> InvoiceApplication:
        payment_plan = db.query(PaymentPlan).filter(PaymentPlan.id == obj_in.payment_plan_id).first()
        if not payment_plan:
            raise ValueError("回款计划不存在")
        
        contract = db.query(Contract).filter(Contract.id == payment_plan.contract_id).first()
        if not contract:
            raise ValueError("关联合同不存在")
        
        invoice_title = db.query(InvoiceTitle).filter(InvoiceTitle.id == obj_in.invoice_title_id).first()
        if not invoice_title:
            raise ValueError("开票抬头不存在")
        
        if invoice_title.customer_id != contract.customer_id:
            raise ValueError("开票抬头不属于该客户")
        
        application_number = self._generate_application_number(db)
        
        db_obj = InvoiceApplication(
            application_number=application_number,
            customer_id=contract.customer_id,
            contract_id=contract.id,
            opportunity_id=contract.opportunity_id,
            team_id=team_id,
            applicant_id=applicant_id,
            payment_plan_id=obj_in.payment_plan_id,
            invoice_title_id=obj_in.invoice_title_id,
            invoice_amount=obj_in.invoice_amount,
            invoice_type=obj_in.invoice_type,
            payment_record_id=obj_in.payment_record_id,
            status=InvoiceApplicationStatus.PENDING_REVIEW,
            invoice_title_type=invoice_title.title_type,
            invoice_title_text=invoice_title.title,
            invoice_taxpayer_id=invoice_title.taxpayer_id,
            invoice_bank_name=invoice_title.bank_name,
            invoice_bank_account=invoice_title.bank_account,
            invoice_address=invoice_title.address,
            invoice_phone=invoice_title.phone
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(self, db: Session, db_obj: InvoiceApplication, obj_in: InvoiceApplicationUpdate) -> InvoiceApplication:
        if db_obj.status not in [InvoiceApplicationStatus.DRAFT, InvoiceApplicationStatus.REJECTED]:
            raise ValueError("只有草稿或已拒绝状态的发票申请可以编辑")
        
        update_data = obj_in.model_dump(exclude_unset=True)
        
        if 'invoice_title_id' in update_data:
            invoice_title = db.query(InvoiceTitle).filter(InvoiceTitle.id == update_data['invoice_title_id']).first()
            if not invoice_title:
                raise ValueError("开票抬头不存在")
            
            if invoice_title.customer_id != db_obj.customer_id:
                raise ValueError("开票抬头不属于该客户")
            
            db_obj.invoice_title_type = invoice_title.title_type
            db_obj.invoice_title_text = invoice_title.title
            db_obj.invoice_taxpayer_id = invoice_title.taxpayer_id
            db_obj.invoice_bank_name = invoice_title.bank_name
            db_obj.invoice_bank_account = invoice_title.bank_account
            db_obj.invoice_address = invoice_title.address
            db_obj.invoice_phone = invoice_title.phone
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def mark_issued(
        self,
        db: Session,
        application_id: int,
        team_id: Optional[int] = None,
    ) -> Optional[InvoiceApplication]:
        """将已通过通用审批引擎审批的发票申请标记为已开票。

        B2 改判定源：原 `application.status == APPROVED` 直接判定改为查
        `approval_crud.get_by_entity(INVOICE, application_id, team_id).status == APPROVED`。
        原因：发票审批已迁通用引擎（A6 submit_generic_approval / approve_generic_approval），
        状态机由适配器 on_approved 回写——本方法不再读 InvoiceApplication.status，
        改为以 Approval.status 为权威源，避免单据表与审批表不一致时误开票。

        Args:
            db: 数据库会话
            application_id: 发票申请 ID
            team_id: 团队 ID（团队隔离；从端点注入，避免误跨团队开票）
        """
        from app.crud.approval import approval_crud
        from app.constants.business_types import BusinessType
        from app.models.approval import ApprovalStatus

        application = self.get_by_id(db, application_id, team_id)
        if not application:
            return None

        approval = approval_crud.get_by_entity(
            db, BusinessType.INVOICE, application_id, team_id,
        )
        if not approval or approval.status != ApprovalStatus.APPROVED:
            raise ValueError("发票未通过审批，不可开票")

        application.status = InvoiceApplicationStatus.ISSUED
        db.commit()
        db.refresh(application)
        return application

    def delete(self, db: Session, application_id: int) -> bool:
        application = self.get_by_id(db, application_id)
        if not application:
            return False
        
        if application.status not in [InvoiceApplicationStatus.DRAFT, InvoiceApplicationStatus.REJECTED]:
            raise ValueError("只有草稿或已拒绝状态的发票申请可以删除")
        
        db.delete(application)
        db.commit()
        return True
    
    def _generate_application_number(self, db: Session) -> str:
        today = date.today()
        date_str = today.strftime("%Y%m%d")
        
        count = db.query(InvoiceApplication).filter(
            InvoiceApplication.application_number.like(f"INV-{date_str}-%")
        ).count()
        
        sequence = count + 1
        return f"INV-{date_str}-{sequence:04d}"
    
    def get_payment_plan_invoice_summary(self, db: Session, payment_plan_id: int) -> dict:
        applications = self.get_by_payment_plan(db, payment_plan_id)
        
        payment_plan = db.query(PaymentPlan).filter(PaymentPlan.id == payment_plan_id).first()
        if not payment_plan:
            return None
        
        total_invoiced = sum(float(app.invoice_amount) for app in applications)
        
        return {
            "payment_plan_id": payment_plan_id,
            "stage_name": payment_plan.stage_name,
            "planned_amount": float(payment_plan.planned_amount),
            "total_invoiced_amount": total_invoiced,
            "invoice_count": len(applications),
            "invoices": applications
        }


invoice_title_crud = InvoiceTitleCRUD()
invoice_application_crud = InvoiceApplicationCRUD()
