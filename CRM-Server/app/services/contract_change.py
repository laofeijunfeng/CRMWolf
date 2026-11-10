"""Contract change requests: submit through the contract approval flow, apply on final approval."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.approval_phase import ApprovalPhase
from app.constants.business_types import BusinessType
from app.crud.contract_change import PENDING_GUARD, contract_change_crud
from app.models.contract import Contract, ContractStatus
from app.models.contract_change import ContractChangeRequest
from app.services.approval_transaction_manager import approval_transaction_manager
from app.services.contract import ContractPricingService
from app.services.file_storage import FileStorageError, file_storage_service

CONTRACT_AMOUNT_KEY = "contract_amount"
PENDING_CHANGE_MESSAGE = "已有一条变更在审批中，审批结束前不能再次发起"
_CENT = Decimal("0.01")


class ContractChangeError(ValueError):
    """Business rule violation; message is safe to show to the user."""


class ContractNotFoundError(LookupError):
    """Contract is missing, deleted or belongs to another team."""


@dataclass(frozen=True)
class ContractChangeAttachment:
    filename: str
    content: bytes
    content_type: Optional[str]


@dataclass(frozen=True)
class ContractFinancialSnapshot:
    paid_amount: Decimal
    invoiced_amount: Decimal
    planned_amount: Decimal

    @property
    def floor_amount(self) -> Decimal:
        return max(self.paid_amount, self.invoiced_amount, self.planned_amount)

    def violation(self, amount: Decimal) -> Optional[str]:
        """Name the highest financial fact the amount would fall below."""
        floors = (
            (self.planned_amount, "回款计划金额合计"),
            (self.invoiced_amount, "已开票金额"),
            (self.paid_amount, "已回款金额"),
        )
        violated = [(value, label) for value, label in floors if amount < value]
        if not violated:
            return None
        value, label = max(violated, key=lambda item: item[0])
        return f"变更后合同金额不能低于{label} ¥{value:,.2f}"


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def amount_change_values(change: ContractChangeRequest) -> tuple[Decimal, Decimal]:
    """Return (old, new) contract amount recorded by the change."""
    for item in change.change_items_json or []:
        if item.get("key") == CONTRACT_AMOUNT_KEY:
            return Decimal(item["old_value"]), Decimal(item["new_value"])
    raise ContractChangeError("合同变更缺少合同金额变更项")


class ContractChangeService:
    def get_pending(self, db: Session, team_id: int, contract_id: int) -> Optional[ContractChangeRequest]:
        return contract_change_crud.get_pending(db, team_id, contract_id)

    def list_history(self, db: Session, team_id: int, contract_id: int) -> list[ContractChangeRequest]:
        return contract_change_crud.list_by_contract(db, team_id, contract_id)

    def get_financial_snapshot(self, db: Session, team_id: int, contract_id: int) -> ContractFinancialSnapshot:
        return ContractFinancialSnapshot(
            paid_amount=_money(contract_change_crud.approved_payment_total(db, team_id, contract_id)),
            invoiced_amount=_money(contract_change_crud.issued_invoice_total(db, team_id, contract_id)),
            planned_amount=_money(contract_change_crud.planned_payment_total(db, team_id, contract_id)),
        )

    def can_request(self, contract: Contract, actor_id: str) -> bool:
        return self._ineligibility(contract, actor_id) is None

    def create_request(
        self,
        db: Session,
        *,
        team_id: int,
        contract_id: int,
        actor_id: str,
        actor_name: str,
        new_amount: Decimal,
        reason: str,
        attachment: Optional[ContractChangeAttachment] = None,
    ) -> ContractChangeRequest:
        contract = contract_change_crud.get_active_contract(db, contract_id, team_id)
        if contract is None:
            raise ContractNotFoundError("合同不存在")
        reason = reason.strip()
        if not reason:
            raise ContractChangeError("请填写变更原因")
        new_amount = _money(new_amount)

        attachment_path: Optional[str] = None
        if attachment is not None:
            try:
                attachment_path = file_storage_service.save_contract_change_file(
                    team_id=team_id,
                    contract_id=contract_id,
                    filename=attachment.filename,
                    content=attachment.content,
                )
            except FileStorageError as error:
                raise ContractChangeError(str(error)) from error

        # The manager reads the flow-matching amount after the create func runs,
        # so it reflects the amount observed under the contract row lock.
        match_kwargs: dict = {"amount": max(contract.total_amount, new_amount), "license_type": contract.license_type}

        def create_change() -> ContractChangeRequest:
            locked = contract_change_crud.lock_active_contract(db, contract_id, team_id)
            if locked is None:
                raise ContractChangeError("合同不存在")
            ineligible = self._ineligibility(locked, actor_id)
            if ineligible:
                raise ContractChangeError(ineligible)
            old_amount = _money(locked.total_amount)
            if new_amount <= 0:
                raise ContractChangeError("合同金额必须大于 0")
            if new_amount == old_amount:
                raise ContractChangeError("变更后合同金额与当前金额相同")
            violation = self.get_financial_snapshot(db, team_id, contract_id).violation(new_amount)
            if violation:
                raise ContractChangeError(violation)
            if contract_change_crud.get_pending(db, team_id, contract_id) is not None:
                raise ContractChangeError(PENDING_CHANGE_MESSAGE)

            change = ContractChangeRequest(
                team_id=team_id,
                contract_id=contract_id,
                creator_id=actor_id,
                change_items_json=[{
                    "key": CONTRACT_AMOUNT_KEY,
                    "old_value": f"{old_amount:.2f}",
                    "new_value": f"{new_amount:.2f}",
                }],
                reason=reason,
                approval_phase=ApprovalPhase.DRAFT.value,
                pending_guard=PENDING_GUARD,
                attachment_path=attachment_path,
                attachment_name=attachment.filename if attachment else None,
                attachment_size=len(attachment.content) if attachment else None,
                attachment_mime_type=attachment.content_type if attachment else None,
            )
            db.add(change)
            try:
                db.flush()
            except IntegrityError as error:
                raise ContractChangeError(PENDING_CHANGE_MESSAGE) from error
            match_kwargs["amount"] = max(old_amount, new_amount)
            return change

        change, _approval, error = approval_transaction_manager.create_with_approval(
            db,
            BusinessType.CONTRACT_CHANGE,
            create_change,
            match_kwargs,
            submitter_id=actor_id,
            submitter_name=actor_name,
            team_id=team_id,
            rollback_on_no_flow=True,
        )
        if change is None:
            if attachment_path:
                file_storage_service.delete_file(attachment_path)
            raise ContractChangeError(error or "合同变更提交失败")
        return change

    def apply_approved_change(self, db: Session, change: ContractChangeRequest) -> None:
        """Apply the final approval to the contract; caller owns the transaction."""
        contract = contract_change_crud.lock_active_contract(db, change.contract_id, change.team_id)
        if contract is None:
            raise ValueError("合同不存在，无法应用合同变更")
        _old_amount, new_amount = amount_change_values(change)
        violation = self.get_financial_snapshot(db, change.team_id, change.contract_id).violation(new_amount)
        if violation:
            raise ValueError(violation)
        contract.total_amount = new_amount
        contract.standard_unit_price = ContractPricingService.calculate_standard_unit_price(
            new_amount,
            contract.user_count,
            contract.license_type,
            subscription_years=contract.subscription_years,
        )
        change.pending_guard = None

    def release_pending(self, change: ContractChangeRequest) -> None:
        change.pending_guard = None

    @staticmethod
    def _ineligibility(contract: Contract, actor_id: str) -> Optional[str]:
        if str(contract.creator_id) != str(actor_id):
            return "只有合同创建人可以申请变更合同"
        if contract.approval_phase != ApprovalPhase.APPROVED.value:
            return "只有审批通过的合同可以申请变更"
        if contract.status == ContractStatus.TERMINATED:
            return "已终止的合同不能申请变更"
        return None


contract_change_service = ContractChangeService()
