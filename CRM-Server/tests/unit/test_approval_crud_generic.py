"""Task A5：crud/approval.py 解耦合同——通用审批 CRUD 单元测试。

覆盖：
- get_by_entity：单据无审批时返回 None
- create_approval_generic：写 business_type/business_id 列、INVOICE 不写 contract_id
- 旧 create_approval(db, contract, ...) legacy wrapper：CONTRACT 分支 contract_id=business_id 兼容
- match_flow_generic：四类业务未匹配审批流程时都返回配置错误
- match_flow 旧 wrapper 委托 generic CONTRACT 分支（E1 合同回归契约）
- approve/cancel 经适配器回写状态 + E4 None 守卫（单据已删仅终结审批）
"""
import pytest
from datetime import datetime, date

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker

# SQLite 把 BigInteger 编译为 INTEGER，确保 BigInteger 主键在 SQLite 上能自增
# （SQLite 仅对 INTEGER PRIMARY KEY 启用 rowid 自增；BIGINT不具备此行为）。
# 仅作用于 sqlite 方言，不影响 MySQL 真实引擎。
@compiles(BigInteger, "sqlite")
def _bigint_to_sqlite_int(element, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


from app.core.database import Base
from app.constants.business_types import BusinessType
from app.models.approval import (
    Approval, ApprovalRecord, ApprovalFlow, ApprovalNode,
    ApprovalStatus, ApprovalAction,
)
from app.models.contract import Contract, ContractStatus
from app.models.invoice import InvoiceApplication, InvoiceApplicationStatus, InvoiceType
from app.crud.approval import approval_crud, approval_flow_crud


@pytest.fixture(scope="function")
def db_session():
    """内存 SQLite，仅创建本测试需要的表（避免触发全模型级联建表）。"""
    engine = create_engine("sqlite:///:memory:")
    # 显式列表：只建本测试用到的表；FK 指向的表（customers 等）不建，SQLite 不强制 FK
    tables = [
        Contract.__table__,
        InvoiceApplication.__table__,
        ApprovalFlow.__table__,
        ApprovalNode.__table__,
        Approval.__table__,
        ApprovalRecord.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ---------- 种子 fixtures --------------------------------------------------

@pytest.fixture
def seed_flow_with_one_node(db_session):
    """创建一条 CONTRACT 类型审批流程 + 1 个节点。返回 (flow, node)。"""
    flow = ApprovalFlow(
        team_id=1,
        flow_name="小额合同审批",
        flow_code="SMALL_CONTRACT",
        business_type=BusinessType.CONTRACT,
        min_amount=0,
        max_amount=200000,
        is_active=1,
    )
    db_session.add(flow)
    db_session.flush()
    node = ApprovalNode(
        team_id=1,
        flow_id=flow.id,
        node_name="销售总监审批",
        node_code="SALES_DIRECTOR",
        node_order=1,
        approve_role="SALES_DIRECTOR",
        is_required=1,
    )
    db_session.add(node)
    db_session.commit()
    return flow, node


@pytest.fixture
def seed_invoice_flow_with_one_node(db_session):
    """创建一条 INVOICE 类型审批流程 + 1 个节点。返回 (flow, node)。"""
    flow = ApprovalFlow(
        team_id=1,
        flow_name="发票审批",
        flow_code="INVOICE_FLOW",
        business_type=BusinessType.INVOICE,
        is_active=1,
    )
    db_session.add(flow)
    db_session.flush()
    node = ApprovalNode(
        team_id=1,
        flow_id=flow.id,
        node_name="财务审批",
        node_code="FINANCE",
        node_order=1,
        approve_role="FINANCE",
        is_required=1,
    )
    db_session.add(node)
    db_session.commit()
    return flow, node


@pytest.fixture
def seed_contract_draft(db_session):
    """创建一条 DRAFT 合同。"""
    contract = Contract(
        team_id=1,
        contract_number="CON-2026-001",
        contract_name="测试合同",
        customer_id=1,
        opportunity_id=1,
        signing_contact_id=1,
        user_count=10,
        total_amount=100000,
        license_type="SUBSCRIPTION",
        subscription_years=1,
        standard_unit_price=10000,
        status=ContractStatus.DRAFT,
        owner_id="u1",
        creator_id="u1",
    )
    db_session.add(contract)
    db_session.commit()
    return contract


@pytest.fixture
def seed_invoice_draft(db_session):
    """创建一条 DRAFT 发票申请。"""
    inv = InvoiceApplication(
        team_id=1,
        application_number="INV-2026-001",
        customer_id=1,
        contract_id=1,
        opportunity_id=1,
        payment_plan_id=1,
        invoice_amount=5000,
        invoice_type=InvoiceType.VAT_NORMAL,
        status=InvoiceApplicationStatus.DRAFT,
        applicant_id="u1",
        invoice_title_type="COMPANY",
        invoice_title_text="测试公司",
        invoice_taxpayer_id="91110000XXXXXXX",
    )
    db_session.add(inv)
    db_session.commit()
    return inv


# ---------- brief Step 1 三测 ----------------------------------------------

def test_get_by_entity_returns_none_when_absent(db_session):
    a = approval_crud.get_by_entity(db_session, BusinessType.INVOICE, 999999, team_id=1)
    assert a is None


def test_get_by_entity_returns_latest_approval_by_id_after_resubmit(
    db_session, seed_contract_draft, seed_flow_with_one_node
):
    """撤回后重新提交时，即使 created_time 同秒，也必须取新审批实例。"""
    flow, _ = seed_flow_with_one_node

    first = approval_crud.create_approval(
        db_session, seed_contract_draft, flow, "u1", "eddie"
    )
    approval_crud.cancel(db_session, first, "u1")

    second = approval_crud.create_approval(
        db_session, seed_contract_draft, flow, "u1", "eddie"
    )

    same_time = datetime(2026, 7, 16, 16, 17, 44)
    first.created_time = same_time
    second.created_time = same_time
    db_session.commit()

    latest = approval_crud.get_by_entity(
        db_session, BusinessType.CONTRACT, seed_contract_draft.id, team_id=1
    )

    assert latest.id == second.id
    assert latest.status == ApprovalStatus.PENDING


def test_create_approval_generic_writes_business_columns(
    db_session, seed_invoice_flow_with_one_node, seed_invoice_draft
):
    flow, _ = seed_invoice_flow_with_one_node
    ap = approval_crud.create_approval_generic(
        db_session, BusinessType.INVOICE, seed_invoice_draft.id,
        team_id=seed_invoice_draft.team_id, flow=flow,
        submitter_id="u1", submitter_name="eddie",
    )
    assert ap.business_type == BusinessType.INVOICE
    assert ap.business_id == seed_invoice_draft.id
    assert ap.contract_id is None  # INVOICE 不写 contract_id
    assert ap.status == ApprovalStatus.PENDING
    # on_submit 经适配器切状态
    db_session.refresh(seed_invoice_draft)
    assert seed_invoice_draft.status == InvoiceApplicationStatus.PENDING_REVIEW


def test_contract_create_legacy_still_works(
    db_session, seed_contract_draft, seed_flow_with_one_node
):
    flow, _ = seed_flow_with_one_node
    ap = approval_crud.create_approval(
        db_session, seed_contract_draft, flow, "u1", "eddie"
    )
    assert ap.business_type == BusinessType.CONTRACT
    assert ap.business_id == seed_contract_draft.id
    assert ap.contract_id == seed_contract_draft.id  # 兼容旧字段
    assert ap.status == ApprovalStatus.PENDING
    # on_submit 经 ContractAdapter 切 PENDING_REVIEW（与原 contract.status = PENDING_REVIEW 一致）
    db_session.refresh(seed_contract_draft)
    assert seed_contract_draft.status == ContractStatus.PENDING_REVIEW


# ---------- 决策1：match_flow_generic 未匹配分支 ----------------------------

def test_match_flow_generic_contract_unmatched_returns_error(db_session):
    """CONTRACT 未匹配审批流程时返回配置错误。"""
    flow, err = approval_flow_crud.match_flow_generic(
        db_session, BusinessType.CONTRACT, team_id=1, amount=999999999, license_type="SUBSCRIPTION"
    )
    assert flow is None
    assert err == "未找到匹配的合同审批流程，请联系管理员创建或完善审批流程"


def test_match_flow_generic_contract_empty_amount_returns_specific_error(db_session):
    """CONTRACT 金额为空时沿用原特定错误信息（E1 逐字一致）。"""
    flow, err = approval_flow_crud.match_flow_generic(
        db_session, BusinessType.CONTRACT, team_id=1, amount=0, license_type="SUBSCRIPTION"
    )
    assert flow is None
    assert err == "合同金额为空，无法匹配审批流程，请补充金额或让管理员创建默认流程"


def test_match_flow_generic_payment_unmatched_returns_error(db_session):
    """PAYMENT 未匹配审批流程时返回配置错误。"""
    flow, err = approval_flow_crud.match_flow_generic(
        db_session, BusinessType.PAYMENT, team_id=1, amount=5000, license_type=None
    )
    assert flow is None
    assert err == "未找到匹配的回款审批流程，请联系管理员创建或完善审批流程"


def test_match_flow_generic_invoice_unmatched_returns_error(db_session):
    """INVOICE 未匹配审批流程时返回配置错误。"""
    flow, err = approval_flow_crud.match_flow_generic(
        db_session, BusinessType.INVOICE, team_id=1, amount=5000, license_type=None
    )
    assert flow is None
    assert err == "未找到匹配的发票审批流程，请联系管理员创建或完善审批流程"


def test_match_flow_generic_license_unmatched_returns_error(db_session):
    """LICENSE 未匹配审批流程时返回配置错误。"""
    flow, err = approval_flow_crud.match_flow_generic(
        db_session, BusinessType.LICENSE, team_id=1, amount=None, license_type=None
    )
    assert flow is None
    assert err == "未找到匹配的License审批流程，请联系管理员创建或完善审批流程"


# ---------- E1 合同回归契约：match_flow 旧 wrapper 委托 generic CONTRACT ----

def test_match_flow_legacy_delegates_generic_contract(
    db_session, seed_contract_draft, seed_flow_with_one_node
):
    """match_flow(contract) 应命中 seed_flow（与 match_flow_generic(CONTRACT) 一致）。"""
    flow, err = approval_flow_crud.match_flow(db_session, seed_contract_draft, team_id=1)
    assert flow is not None
    assert flow.id == seed_flow_with_one_node[0].id
    assert err is None
    # 等价于 generic CONTRACT 分支
    g_flow, g_err = approval_flow_crud.match_flow_generic(
        db_session, BusinessType.CONTRACT, 1,
        seed_contract_draft.total_amount, seed_contract_draft.license_type,
    )
    assert g_flow is not None and g_flow.id == flow.id
    assert g_err is None


# ---------- approve/cancel 经适配器 + E4 None 守卫 --------------------------

def test_approve_final_node_writes_contract_signed_via_adapter(
    db_session, seed_contract_draft, seed_flow_with_one_node
):
    """末节点 APPROVE 经 ContractAdapter.on_approved → status=SIGNED（等价原 contract.status=SIGNED）。"""
    flow, _ = seed_flow_with_one_node
    ap = approval_crud.create_approval(
        db_session, seed_contract_draft, flow, "u1", "eddie"
    )
    # 构造 action_request
    from app.schemas.approval import ApprovalActionRequest
    from app.models.approval import ApprovalAction as AA
    req = ApprovalActionRequest(action=AA.APPROVE, comment="同意", updated_time=ap.updated_time)
    approval_crud.approve(db_session, ap, req, approver_id="reviewer", approver_name="审核人")
    db_session.refresh(seed_contract_draft)
    assert seed_contract_draft.status == ContractStatus.SIGNED
    db_session.refresh(ap)
    assert ap.status == ApprovalStatus.APPROVED


def test_approve_reject_writes_contract_draft_via_adapter(
    db_session, seed_contract_draft, seed_flow_with_one_node
):
    """REJECT 经 ContractAdapter.on_rejected → status=DRAFT（等价原 contract.status=DRAFT）。"""
    flow, _ = seed_flow_with_one_node
    ap = approval_crud.create_approval(
        db_session, seed_contract_draft, flow, "u1", "eddie"
    )
    from app.schemas.approval import ApprovalActionRequest
    from app.models.approval import ApprovalAction as AA
    req = ApprovalActionRequest(action=AA.REJECT, comment="驳回", updated_time=ap.updated_time)
    approval_crud.approve(db_session, ap, req, approver_id="reviewer", approver_name="审核人")
    db_session.refresh(seed_contract_draft)
    assert seed_contract_draft.status == ContractStatus.DRAFT
    db_session.refresh(ap)
    assert ap.status == ApprovalStatus.REJECTED


def test_cancel_writes_contract_draft_via_adapter(
    db_session, seed_contract_draft, seed_flow_with_one_node
):
    """cancel 经 ContractAdapter.on_cancelled → status=DRAFT（等价原 contract.status=DRAFT）。"""
    flow, _ = seed_flow_with_one_node
    ap = approval_crud.create_approval(
        db_session, seed_contract_draft, flow, "u1", "eddie"
    )
    approval_crud.cancel(db_session, ap, user_id="u1")
    db_session.refresh(seed_contract_draft)
    assert seed_contract_draft.status == ContractStatus.DRAFT
    db_session.refresh(ap)
    assert ap.status == ApprovalStatus.CANCELLED


def test_approve_entity_deleted_skips_on_status_write(
    db_session, seed_contract_draft, seed_flow_with_one_node
):
    """E4 守卫：单据已删（get_entity 返 None）时仅终结审批，不回写单据状态、不抛异常。"""
    flow, _ = seed_flow_with_one_node
    ap = approval_crud.create_approval(
        db_session, seed_contract_draft, flow, "u1", "eddie"
    )
    # 模拟单据已删：把 business_id 指向不存在的 ID，使 adapter.get_entity 返 None
    ap.business_id = 999999
    db_session.commit()
    from app.schemas.approval import ApprovalActionRequest
    from app.models.approval import ApprovalAction as AA
    req = ApprovalActionRequest(action=AA.APPROVE, comment="同意", updated_time=ap.updated_time)
    approval_crud.approve(db_session, ap, req, approver_id="reviewer", approver_name="审核人")
    db_session.refresh(ap)
    # 审批仍终结
    assert ap.status == ApprovalStatus.APPROVED
    # 原合同状态不变（未回写）
    db_session.refresh(seed_contract_draft)
    assert seed_contract_draft.status == ContractStatus.PENDING_REVIEW
