"""Team-scoped persistence queries for contract change requests."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.models.contract import Contract
from app.models.contract_change import ContractChangeRequest
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus
from app.models.payment import PaymentPlan, PaymentRecord

PENDING_GUARD = "pending"


class ContractChangeCRUD:
    def get_by_id(self, db: Session, change_id: int, team_id: int) -> Optional[ContractChangeRequest]:
        return db.query(ContractChangeRequest).filter(
            ContractChangeRequest.id == change_id,
            ContractChangeRequest.team_id == team_id,
            ContractChangeRequest.deleted_at.is_(None),
        ).first()

    def get_by_ids(self, db: Session, change_ids: list[int], team_id: int) -> list[ContractChangeRequest]:
        if not change_ids:
            return []
        return db.query(ContractChangeRequest).filter(
            ContractChangeRequest.id.in_(change_ids),
            ContractChangeRequest.team_id == team_id,
            ContractChangeRequest.deleted_at.is_(None),
        ).all()

    def get_pending(self, db: Session, team_id: int, contract_id: int) -> Optional[ContractChangeRequest]:
        return db.query(ContractChangeRequest).filter(
            ContractChangeRequest.team_id == team_id,
            ContractChangeRequest.contract_id == contract_id,
            ContractChangeRequest.pending_guard == PENDING_GUARD,
            ContractChangeRequest.deleted_at.is_(None),
        ).first()

    def list_by_contract(self, db: Session, team_id: int, contract_id: int) -> list[ContractChangeRequest]:
        return db.query(ContractChangeRequest).filter(
            ContractChangeRequest.team_id == team_id,
            ContractChangeRequest.contract_id == contract_id,
            ContractChangeRequest.deleted_at.is_(None),
        ).order_by(ContractChangeRequest.created_time.desc(), ContractChangeRequest.id.desc()).all()

    def get_active_contract(self, db: Session, contract_id: int, team_id: int) -> Optional[Contract]:
        return db.query(Contract).filter(
            Contract.id == contract_id,
            Contract.team_id == team_id,
            Contract.deleted_at.is_(None),
        ).first()

    def lock_active_contract(self, db: Session, contract_id: int, team_id: int) -> Optional[Contract]:
        return db.query(Contract).filter(
            Contract.id == contract_id,
            Contract.team_id == team_id,
            Contract.deleted_at.is_(None),
        ).populate_existing().with_for_update().first()

    def approved_payment_total(self, db: Session, team_id: int, contract_id: int) -> Decimal:
        total = db.query(func.coalesce(func.sum(PaymentRecord.actual_amount), 0)).join(
            PaymentPlan, PaymentPlan.id == PaymentRecord.payment_plan_id,
        ).filter(
            PaymentPlan.contract_id == contract_id,
            PaymentPlan.team_id == team_id,
            PaymentRecord.team_id == team_id,
            PaymentRecord.approval_phase == ApprovalPhase.APPROVED.value,
        ).scalar()
        return Decimal(str(total))

    def issued_invoice_total(self, db: Session, team_id: int, contract_id: int) -> Decimal:
        total = db.query(func.coalesce(func.sum(InvoiceApplication.invoice_amount), 0)).filter(
            InvoiceApplication.contract_id == contract_id,
            InvoiceApplication.team_id == team_id,
            InvoiceApplication.status == InvoiceApplicationStatus.ISSUED,
        ).scalar()
        return Decimal(str(total))

    def planned_payment_total(self, db: Session, team_id: int, contract_id: int) -> Decimal:
        total = db.query(func.coalesce(func.sum(PaymentPlan.planned_amount), 0)).filter(
            PaymentPlan.contract_id == contract_id,
            PaymentPlan.team_id == team_id,
        ).scalar()
        return Decimal(str(total))


contract_change_crud = ContractChangeCRUD()
