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
