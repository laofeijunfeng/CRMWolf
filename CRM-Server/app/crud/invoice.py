from datetime import date, datetime, time
from typing import List, Optional, Tuple

from sqlalchemy import and_, exists, not_, or_
from sqlalchemy.orm import Session

from app.constants.business_types import BusinessType
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.invoice import (
    InvoiceApplication,
    InvoiceApplicationStatus,
    InvoiceRedOffset,
    InvoiceRedOffsetSourceType,
    InvoiceReissueApplication,
    InvoiceReissueApplicationStatus,
    InvoiceTitle,
)
from app.models.payment import PaymentPlan
from app.schemas.invoice import (
    InvoiceApplicationCreate,
    InvoiceApplicationUpdate,
    InvoiceReissueApplicationCreate,
    InvoiceReissueApplicationUpdate,
    InvoiceTitleCreate,
    InvoiceTitleUpdate,
)
from app.services.business_number_generator import BusinessNumberGenerator
from app.utils.approval_delete_guard import assert_deletable_approval_resource
from app.utils.time import business_now


def _split_csv(value: Optional[str]) -> List[str]:
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


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
    
    def delete(self, db: Session, title_id: int, team_id: Optional[int] = None) -> bool:
        title = self.get_by_id(db, title_id, team_id)
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
        payment_plan_id: Optional[int] = None,
        status: Optional[str] = None,
        status_exclude: Optional[str] = None,
        invoice_type: Optional[str] = None,
        invoice_type_exclude: Optional[str] = None,
        invoice_effective_status: Optional[str] = None,
        applicant_id: Optional[str] = None,
        current_user_id: Optional[str] = None,
        keyword: Optional[str] = None,
        created_time_start: Optional[date] = None,
        created_time_end: Optional[date] = None,
        order_by: Optional[str] = None,
        order_dir: Optional[str] = None
    ) -> Tuple[List[InvoiceApplication], int]:
        query = db.query(InvoiceApplication).filter(InvoiceApplication.team_id == team_id)
        
        if customer_id:
            query = query.filter(InvoiceApplication.customer_id == customer_id)
        
        if contract_id:
            query = query.filter(InvoiceApplication.contract_id == contract_id)

        if payment_plan_id:
            query = query.filter(InvoiceApplication.payment_plan_id == payment_plan_id)
        
        if status:
            query = query.filter(InvoiceApplication.status.in_(_split_csv(status)))
        if status_exclude:
            query = query.filter(InvoiceApplication.status.notin_(_split_csv(status_exclude)))

        if invoice_type:
            query = query.filter(InvoiceApplication.invoice_type.in_(_split_csv(invoice_type)))
        if invoice_type_exclude:
            query = query.filter(InvoiceApplication.invoice_type.notin_(_split_csv(invoice_type_exclude)))

        invoice_effective_status_values = _split_csv(invoice_effective_status)
        if invoice_effective_status_values:
            completed_reissue_exists = exists().where(
                and_(
                    InvoiceReissueApplication.team_id == team_id,
                    InvoiceReissueApplication.original_invoice_application_id == InvoiceApplication.id,
                    InvoiceReissueApplication.status == InvoiceReissueApplicationStatus.COMPLETED,
                    InvoiceReissueApplication.new_invoice_file_path.isnot(None),
                    InvoiceReissueApplication.new_invoice_file_path != "",
                )
            )
            red_offset_exists = exists().where(
                and_(
                    InvoiceRedOffset.team_id == team_id,
                    InvoiceRedOffset.invoice_application_id == InvoiceApplication.id,
                )
            )
            pending_reissue_exists = exists().where(
                and_(
                    InvoiceReissueApplication.team_id == team_id,
                    InvoiceReissueApplication.original_invoice_application_id == InvoiceApplication.id,
                    InvoiceReissueApplication.status.in_([
                        InvoiceReissueApplicationStatus.DRAFT,
                        InvoiceReissueApplicationStatus.PENDING_REVIEW,
                        InvoiceReissueApplicationStatus.APPROVED,
                    ]),
                )
            )
            status_predicates = []
            if "REISSUED" in invoice_effective_status_values:
                status_predicates.append(completed_reissue_exists)
            if "RED_OFFSET" in invoice_effective_status_values:
                status_predicates.append(and_(red_offset_exists, not_(completed_reissue_exists)))
            if "REISSUE_PENDING" in invoice_effective_status_values:
                status_predicates.append(and_(not_(red_offset_exists), not_(completed_reissue_exists), pending_reissue_exists))
            if "ACTIVE" in invoice_effective_status_values:
                status_predicates.append(and_(not_(red_offset_exists), not_(completed_reissue_exists), not_(pending_reissue_exists)))
            if status_predicates:
                query = query.filter(or_(*status_predicates))
        
        if applicant_id:
            query = query.filter(InvoiceApplication.applicant_id == applicant_id)
        
        if current_user_id:
            query = query.filter(InvoiceApplication.applicant_id == current_user_id)

        if created_time_start:
            query = query.filter(InvoiceApplication.created_time >= datetime.combine(created_time_start, time.min))

        if created_time_end:
            query = query.filter(InvoiceApplication.created_time <= datetime.combine(created_time_end, time.max))

        if keyword and keyword.strip():
            like_keyword = f"%{keyword.strip()}%"
            query = (
                query
                .join(Customer, InvoiceApplication.customer_id == Customer.id)
                .join(Contract, InvoiceApplication.contract_id == Contract.id)
                .filter(
                    or_(
                        InvoiceApplication.application_number.ilike(like_keyword),
                        InvoiceApplication.invoice_title_text.ilike(like_keyword),
                        InvoiceApplication.invoice_taxpayer_id.ilike(like_keyword),
                        InvoiceApplication.invoice_number.ilike(like_keyword),
                        Customer.account_name.ilike(like_keyword),
                        Contract.contract_name.ilike(like_keyword),
                    )
                )
            )
        
        total = query.count()

        allowed_sort_fields = {
            "application_number": InvoiceApplication.application_number,
            "invoice_type": InvoiceApplication.invoice_type,
            "invoice_amount": InvoiceApplication.invoice_amount,
            "invoice_title_text": InvoiceApplication.invoice_title_text,
            "status": InvoiceApplication.status,
            "created_time": InvoiceApplication.created_time,
            "issued_time": InvoiceApplication.issued_time,
        }
        order_column = allowed_sort_fields.get(order_by or "")
        if order_column is not None and order_dir and order_dir.lower() == "asc":
            query = query.order_by(order_column.asc())
        elif order_column is not None:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(InvoiceApplication.created_time.desc())

        applications = query.offset(skip).limit(limit).all()
        
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
            deal_journey_id=payment_plan.deal_journey_id or contract.deal_journey_id,
            invoice_title_id=obj_in.invoice_title_id,
            invoice_amount=obj_in.invoice_amount,
            invoice_type=obj_in.invoice_type,
            payment_record_id=obj_in.payment_record_id,
            status=InvoiceApplicationStatus.DRAFT,
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
        from app.models.deal_journey import DealJourneyEventType, DealJourneySourceType
        from app.services.deal_journey_service import deal_journey_service
        deal_journey_service.record_event(
            db,
            deal_journey_id=db_obj.deal_journey_id,
            team_id=team_id,
            customer_id=db_obj.customer_id,
            event_type=DealJourneyEventType.INVOICE_APPLIED,
            source_type=DealJourneySourceType.INVOICE_APPLICATION,
            source_id=db_obj.id,
            event_time=db_obj.created_time,
            actor_id=applicant_id,
            summary=f"申请开票：{db_obj.invoice_amount}",
        )
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
        invoice_file_path: Optional[str] = None,
        invoice_number: Optional[str] = None,
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
            invoice_file_path: 发票文件相对路径（审批通过后的开票业务附件）
            invoice_number: 发票号码
        """
        from app.constants.business_types import BusinessType
        from app.crud.approval import approval_crud
        from app.models.approval import ApprovalStatus

        application = self.get_by_id(db, application_id, team_id)
        if not application:
            return None

        approval = approval_crud.get_by_entity(
            db, BusinessType.INVOICE, application_id, team_id,
        )
        if not approval or approval.status != ApprovalStatus.APPROVED:
            raise ValueError("发票未通过审批，不可开票")

        if application.status != InvoiceApplicationStatus.APPROVED:
            raise ValueError(f"发票申请状态为 {application.status}，不可开票")

        if invoice_file_path is not None:
            application.invoice_file_path = invoice_file_path
        if invoice_number is not None:
            application.invoice_number = invoice_number
        application.status = InvoiceApplicationStatus.ISSUED
        application.issued_time = business_now()
        db.commit()
        db.refresh(application)
        from app.models.deal_journey import DealJourneyEventType, DealJourneySourceType
        from app.services.deal_journey_service import deal_journey_service
        deal_journey_service.record_event(
            db,
            deal_journey_id=application.deal_journey_id,
            team_id=application.team_id,
            customer_id=application.customer_id,
            event_type=DealJourneyEventType.INVOICE_ISSUED,
            source_type=DealJourneySourceType.INVOICE_APPLICATION,
            source_id=application.id,
            event_time=application.issued_time,
            summary=f"完成开票：{application.invoice_amount}",
            metadata={"invoice_number": application.invoice_number},
        )
        db.commit()
        db.refresh(application)
        return application

    def delete(self, db: Session, application_id: int, team_id: int) -> bool:
        application = self.get_by_id(db, application_id, team_id)
        if not application:
            return False

        assert_deletable_approval_resource(
            db,
            resource=application,
            business_type=BusinessType.INVOICE,
            business_id=application_id,
            team_id=team_id,
            resource_name="发票申请",
            locked_business_statuses=(
                InvoiceApplicationStatus.PENDING_REVIEW,
                InvoiceApplicationStatus.APPROVED,
                InvoiceApplicationStatus.ISSUED,
            ),
        )

        if application.status not in [InvoiceApplicationStatus.DRAFT, InvoiceApplicationStatus.REJECTED]:
            raise ValueError("只有草稿或已拒绝状态的发票申请可以删除")

        db.delete(application)
        db.commit()
        return True
    
    def _generate_application_number(self, db: Session) -> str:
        return BusinessNumberGenerator.generate('INV', db)
    
    def get_payment_plan_invoice_summary(self, db: Session, payment_plan_id: int, team_id: Optional[int] = None) -> dict:
        applications = self.get_by_payment_plan(db, payment_plan_id, team_id)
        
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


class InvoiceReissueApplicationCRUD:
    ACTIVE_STATUSES = (
        InvoiceReissueApplicationStatus.DRAFT,
        InvoiceReissueApplicationStatus.PENDING_REVIEW,
        InvoiceReissueApplicationStatus.APPROVED,
    )

    def get_by_id(self, db: Session, reissue_id: int, team_id: Optional[int] = None) -> Optional[InvoiceReissueApplication]:
        query = db.query(InvoiceReissueApplication).filter(InvoiceReissueApplication.id == reissue_id)
        if team_id is not None:
            query = query.filter(InvoiceReissueApplication.team_id == team_id)
        return query.first()

    def get_by_original_invoice(
        self,
        db: Session,
        original_invoice_application_id: int,
        team_id: Optional[int] = None,
    ) -> List[InvoiceReissueApplication]:
        query = db.query(InvoiceReissueApplication).filter(
            InvoiceReissueApplication.original_invoice_application_id == original_invoice_application_id
        )
        if team_id is not None:
            query = query.filter(InvoiceReissueApplication.team_id == team_id)
        return query.order_by(InvoiceReissueApplication.created_time.asc(), InvoiceReissueApplication.id.asc()).all()

    def get_active_by_original_invoice(
        self,
        db: Session,
        original_invoice_application_id: int,
        team_id: Optional[int] = None,
    ) -> Optional[InvoiceReissueApplication]:
        query = db.query(InvoiceReissueApplication).filter(
            InvoiceReissueApplication.original_invoice_application_id == original_invoice_application_id,
            InvoiceReissueApplication.status.in_(self.ACTIVE_STATUSES),
        )
        if team_id is not None:
            query = query.filter(InvoiceReissueApplication.team_id == team_id)
        return query.first()

    def create(
        self,
        db: Session,
        original_invoice: InvoiceApplication,
        obj_in: InvoiceReissueApplicationCreate,
        applicant_id: str,
        team_id: int,
    ) -> InvoiceReissueApplication:
        if original_invoice.team_id != team_id:
            raise ValueError("原发票申请不存在")
        if original_invoice.status != InvoiceApplicationStatus.ISSUED:
            raise ValueError("只有已开票的发票申请可以申请重开")
        if invoice_red_offset_crud.get_by_invoice(db, original_invoice.id, team_id):
            raise ValueError("该发票已冲红，不可申请重开")
        if self.get_active_by_original_invoice(db, original_invoice.id, team_id):
            raise ValueError("该发票已有未完成的重开申请")

        application_number = self._generate_application_number(db)
        db_obj = InvoiceReissueApplication(
            application_number=application_number,
            team_id=team_id,
            original_invoice_application_id=original_invoice.id,
            applicant_id=applicant_id,
            status=InvoiceReissueApplicationStatus.DRAFT,
            **obj_in.model_dump(),
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        db_obj: InvoiceReissueApplication,
        obj_in: InvoiceReissueApplicationUpdate,
    ) -> InvoiceReissueApplication:
        if db_obj.status not in [InvoiceReissueApplicationStatus.DRAFT, InvoiceReissueApplicationStatus.REJECTED]:
            raise ValueError("只有草稿或已拒绝状态的重开申请可以编辑")

        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.commit()
        db.refresh(db_obj)
        return db_obj

    def complete(
        self,
        db: Session,
        reissue_id: int,
        team_id: int,
        *,
        red_invoice_file_path: str,
        red_invoice_number: Optional[str],
        new_invoice_file_path: str,
        new_invoice_number: Optional[str],
    ) -> Optional[InvoiceReissueApplication]:
        from app.constants.business_types import BusinessType
        from app.crud.approval import approval_crud
        from app.models.approval import ApprovalStatus

        reissue = self.get_by_id(db, reissue_id, team_id)
        if not reissue:
            return None

        approval = approval_crud.get_by_entity(db, BusinessType.INVOICE_REISSUE, reissue_id, team_id)
        if not approval or approval.status != ApprovalStatus.APPROVED:
            raise ValueError("重开申请未通过审批，不可完成重开")

        if reissue.status != InvoiceReissueApplicationStatus.APPROVED:
            raise ValueError(f"重开申请状态为 {reissue.status}，不可完成重开")

        now = business_now()
        reissue.red_invoice_file_path = red_invoice_file_path
        reissue.red_invoice_number = red_invoice_number
        reissue.red_issued_time = now
        reissue.new_invoice_file_path = new_invoice_file_path
        reissue.new_invoice_number = new_invoice_number
        reissue.new_issued_time = now
        reissue.completed_time = now
        reissue.status = InvoiceReissueApplicationStatus.COMPLETED

        invoice_red_offset_crud.create_from_reissue(
            db,
            reissue,
            red_invoice_file_path=red_invoice_file_path,
            red_invoice_number=red_invoice_number,
            red_offset_time=now,
        )
        db.commit()
        db.refresh(reissue)
        return reissue

    def _generate_application_number(self, db: Session) -> str:
        return BusinessNumberGenerator.generate("INVR", db)


class InvoiceRedOffsetCRUD:
    def get_by_id(self, db: Session, red_offset_id: int, team_id: Optional[int] = None) -> Optional[InvoiceRedOffset]:
        query = db.query(InvoiceRedOffset).filter(InvoiceRedOffset.id == red_offset_id)
        if team_id is not None:
            query = query.filter(InvoiceRedOffset.team_id == team_id)
        return query.first()

    def get_by_invoice(
        self,
        db: Session,
        invoice_application_id: int,
        team_id: Optional[int] = None,
    ) -> List[InvoiceRedOffset]:
        query = db.query(InvoiceRedOffset).filter(
            InvoiceRedOffset.invoice_application_id == invoice_application_id
        )
        if team_id is not None:
            query = query.filter(InvoiceRedOffset.team_id == team_id)
        return query.order_by(InvoiceRedOffset.red_offset_time.asc(), InvoiceRedOffset.id.asc()).all()

    def get_by_reissue(
        self,
        db: Session,
        reissue_application_id: int,
        team_id: Optional[int] = None,
    ) -> Optional[InvoiceRedOffset]:
        query = db.query(InvoiceRedOffset).filter(
            InvoiceRedOffset.reissue_application_id == reissue_application_id
        )
        if team_id is not None:
            query = query.filter(InvoiceRedOffset.team_id == team_id)
        return query.first()

    def create_from_reissue(
        self,
        db: Session,
        reissue: InvoiceReissueApplication,
        *,
        red_invoice_file_path: str,
        red_invoice_number: Optional[str],
        red_offset_time: datetime,
    ) -> InvoiceRedOffset:
        existing = self.get_by_reissue(db, reissue.id, reissue.team_id)
        if existing:
            existing.red_invoice_file_path = red_invoice_file_path
            existing.red_invoice_number = red_invoice_number
            existing.reason = reissue.reason
            existing.created_by = reissue.applicant_id
            existing.red_offset_time = red_offset_time
            return existing

        red_offset = InvoiceRedOffset(
            team_id=reissue.team_id,
            invoice_application_id=reissue.original_invoice_application_id,
            source_type=InvoiceRedOffsetSourceType.REISSUE,
            reissue_application_id=reissue.id,
            red_invoice_file_path=red_invoice_file_path,
            red_invoice_number=red_invoice_number,
            reason=reissue.reason,
            created_by=reissue.applicant_id,
            red_offset_time=red_offset_time,
        )
        db.add(red_offset)
        return red_offset

    def assert_can_create_manual(
        self,
        db: Session,
        invoice_application: InvoiceApplication,
        *,
        team_id: int,
    ) -> None:
        if invoice_application.team_id != team_id:
            raise ValueError("发票申请不存在")
        if invoice_application.status != InvoiceApplicationStatus.ISSUED:
            raise ValueError("只有已开票的发票可以冲红")
        if self.get_by_invoice(db, invoice_application.id, team_id):
            raise ValueError("该发票已冲红")
        if invoice_reissue_application_crud.get_active_by_original_invoice(db, invoice_application.id, team_id):
            raise ValueError("该发票已有未完成的重开申请，不能单独冲红")

        completed_reissue = db.query(InvoiceReissueApplication).filter(
            InvoiceReissueApplication.team_id == team_id,
            InvoiceReissueApplication.original_invoice_application_id == invoice_application.id,
            InvoiceReissueApplication.status == InvoiceReissueApplicationStatus.COMPLETED,
            InvoiceReissueApplication.new_invoice_file_path.isnot(None),
            InvoiceReissueApplication.new_invoice_file_path != "",
        ).first()
        if completed_reissue:
            raise ValueError("该发票已重开，不能单独冲红")

    def create_manual(
        self,
        db: Session,
        invoice_application: InvoiceApplication,
        *,
        red_invoice_file_path: str,
        red_invoice_number: Optional[str],
        reason: Optional[str],
        created_by: str,
        team_id: int,
    ) -> InvoiceRedOffset:
        self.assert_can_create_manual(db, invoice_application, team_id=team_id)

        now = business_now()
        red_offset = InvoiceRedOffset(
            team_id=team_id,
            invoice_application_id=invoice_application.id,
            source_type=InvoiceRedOffsetSourceType.MANUAL,
            reissue_application_id=None,
            red_invoice_file_path=red_invoice_file_path,
            red_invoice_number=red_invoice_number,
            reason=reason,
            created_by=created_by,
            red_offset_time=now,
        )
        db.add(red_offset)
        db.commit()
        db.refresh(red_offset)
        return red_offset


invoice_title_crud = InvoiceTitleCRUD()
invoice_application_crud = InvoiceApplicationCRUD()
invoice_reissue_application_crud = InvoiceReissueApplicationCRUD()
invoice_red_offset_crud = InvoiceRedOffsetCRUD()
