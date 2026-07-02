"""审批业务单据适配器层单元测试（Task A4）。

覆盖：
- get_adapter 注册表对 CONTRACT/PAYMENT/INVOICE 三个 business_type 命中
- 未知 business_type raise ValueError
- ContractAdapter.on_submit 把 DRAFT 切到 PENDING_REVIEW
"""
import pytest
from unittest.mock import Mock

from app.services.approval_adapter import get_adapter
from app.constants.business_types import BusinessType
from app.models.contract import Contract, ContractStatus
from app.models.invoice import InvoiceApplication
from app.models.payment import PaymentRecord


@pytest.fixture
def db_session():
    """最小 Mock 会话；on_* 仅改实体属性，不真正访问 DB。"""
    return Mock()


@pytest.fixture
def seed_contract_draft():
    """提供一个内存中的 DRAFT 合同（不持久化）。"""
    contract = Contract()
    contract.id = 1
    contract.team_id = 1
    contract.status = ContractStatus.DRAFT
    contract.creator_id = "ou_test"
    contract.total_amount = 10000
    contract.license_type = "SUBSCRIPTION"
    contract.contract_name = "测试合同"
    return contract


def test_get_contract_adapter():
    a = get_adapter(BusinessType.CONTRACT)
    assert a is not None


def test_get_payment_adapter():
    assert get_adapter(BusinessType.PAYMENT) is not None


def test_get_invoice_adapter():
    assert get_adapter(BusinessType.INVOICE) is not None


def test_invalid_business_type_raises():
    with pytest.raises(ValueError):
        get_adapter("UNKNOWN")


def test_contract_adapter_on_submit(db_session, seed_contract_draft):
    a = get_adapter(BusinessType.CONTRACT)
    a.on_submit(db_session, seed_contract_draft)
    assert seed_contract_draft.status == ContractStatus.PENDING_REVIEW


def test_on_methods_are_none_safe(db_session):
    """E4 守卫：entity=None 时所有 on_* 不抛异常。"""
    for bt in (BusinessType.CONTRACT, BusinessType.PAYMENT, BusinessType.INVOICE):
        a = get_adapter(bt)
        a.on_submit(db_session, None)
        a.on_approved(db_session, None)
        a.on_rejected(db_session, None)
        a.on_cancelled(db_session, None)


# --- 字段引用正确性（Task A4 fix）----------------------------------------

def test_contract_get_name_returns_contract_name(seed_contract_draft):
    """get_name 必须读 Contract.contract_name（非不存在的 name 列）。"""
    a = get_adapter(BusinessType.CONTRACT)
    assert a.get_name(seed_contract_draft) == "测试合同"


def test_contract_get_name_fallback_when_blank():
    """contract_name 为空时 fallback 到 合同#{id}。"""
    contract = Contract()
    contract.id = 42
    contract.contract_name = None
    a = get_adapter(BusinessType.CONTRACT)
    assert a.get_name(contract) == "合同#42"


def test_contract_get_submitter_name_is_none(seed_contract_draft):
    """Contract 无 creator_name 列，第二元必须为 None（不靠 getattr 幻觉）。"""
    a = get_adapter(BusinessType.CONTRACT)
    submitter_id, submitter_name = a.get_submitter(seed_contract_draft)
    assert submitter_id == "ou_test"
    assert submitter_name is None


def test_invoice_get_submitter_uses_applicant_id_no_name():
    """InvoiceApplication 只有 applicant_id，无 applicant_name 列。"""
    inv = InvoiceApplication()
    inv.id = 7
    inv.applicant_id = "ou_applicant"
    a = get_adapter(BusinessType.INVOICE)
    submitter_id, submitter_name = a.get_submitter(inv)
    assert submitter_id == "ou_applicant"
    assert submitter_name is None


def test_payment_get_submitter_keeps_creator_name():
    """PaymentRecord 有 creator_name 列，保留 getattr（非 None）。"""
    pay = PaymentRecord()
    pay.id = 9
    pay.creator_id = "ou_creator"
    pay.creator_name = "张三"
    a = get_adapter(BusinessType.PAYMENT)
    submitter_id, submitter_name = a.get_submitter(pay)
    assert submitter_id == "ou_creator"
    assert submitter_name == "张三"
