"""Task D2 / E1+E3：合同审批回归专项测试（P0）。

锁定 A5 重构（crud/approval.py 解耦合同 → 通用 match_flow_generic）的
"E1 合同回归契约"——business_type='CONTRACT' 分支的匹配结果必须与改造前
legacy `match_flow(contract)` 逐字一致。

三场景 + 端到端全覆盖：
- 场景1 金额边界：金额恰好等于 min_amount / max_amount 的合同匹配到对应 flow
- 场景2 license_type 匹配：license_type 不匹配的 flow 被排除
- 场景3 多 flow 评分排序：多个候选 flow 时按 calculate_flow_precision_score 选最优
- 端到端：合同提交 → approve 末节点 → status=SIGNED；
         reject → DRAFT；cancel → DRAFT，全链路状态切换不变

E1 核心断言：每个场景下 `match_flow_generic(db, BusinessType.CONTRACT, team_id,
contract.total_amount, contract.license_type)` 返回的 flow 与直接调 legacy
`match_flow(db, contract, team_id)` 返回的 flow 完全一致（同 id、同 error）。

fixture 仿 A5/A6/B2：内存 SQLite + StaticPool（跨线程共享同一连接），
只建本测试所需表（Contract / ApprovalFlow / ApprovalNode / Approval /
ApprovalRecord），FK 指向的 customers 等表不建（SQLite 不强制 FK）。
"""
import pytest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import BigInteger
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# SQLite 把 BigInteger 编译为 INTEGER，确保 BigInteger 主键在 SQLite 上能自增
# （SQLite 仅对 INTEGER PRIMARY KEY 启用 rowid 自增；BIGINT 不具备此行为）。
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
from app.crud.approval import approval_crud, approval_flow_crud


# ---------- DB fixtures ----------------------------------------------------

@pytest.fixture(scope="function")
def db_session():
    """内存 SQLite + StaticPool（跨线程共享同一连接），仅建本测试所需表。"""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    tables = [
        Contract.__table__,
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


# ---------- helpers --------------------------------------------------------

TEAM_ID = 1


def _make_flow(
    db, *, flow_code, flow_name, min_amount=None, max_amount=None,
    license_type=None, business_type=BusinessType.CONTRACT, is_active=1,
    team_id=TEAM_ID,
):
    """建一条 ApprovalFlow（无节点），返回 flow。"""
    flow = ApprovalFlow(
        team_id=team_id,
        flow_name=flow_name,
        flow_code=flow_code,
        business_type=business_type,
        min_amount=min_amount,
        max_amount=max_amount,
        license_type=license_type,
        is_active=is_active,
    )
    db.add(flow)
    db.commit()
    db.refresh(flow)
    return flow


def _make_flow_with_node(db, *, flow_code, flow_name, min_amount=None,
                         max_amount=None, license_type=None, node_code="N1",
                         approve_role="SALES_DIRECTOR", team_id=TEAM_ID):
    """建一条 ApprovalFlow + 1 个节点（node_order=1），返回 (flow, node)。"""
    flow = ApprovalFlow(
        team_id=team_id,
        flow_name=flow_name,
        flow_code=flow_code,
        business_type=BusinessType.CONTRACT,
        min_amount=min_amount,
        max_amount=max_amount,
        license_type=license_type,
        is_active=1,
    )
    db.add(flow)
    db.flush()
    node = ApprovalNode(
        team_id=team_id,
        flow_id=flow.id,
        node_name=f"{flow_name}-节点1",
        node_code=node_code,
        node_order=1,
        approve_role=approve_role,
        is_required=1,
    )
    db.add(node)
    db.commit()
    db.refresh(flow)
    db.refresh(node)
    return flow, node


def _make_contract(db, *, total_amount, license_type="SUBSCRIPTION",
                   contract_number="CON-REG-001", team_id=TEAM_ID,
                   status=ContractStatus.DRAFT):
    """建一条合同（DRAFT 默认），返回 contract。"""
    contract = Contract(
        team_id=team_id,
        contract_number=contract_number,
        contract_name=f"回归测试合同-{contract_number}",
        customer_id=1,
        opportunity_id=1,
        signing_contact_id=1,
        user_count=10,
        total_amount=total_amount,
        license_type=license_type,
        subscription_years=1,
        standard_unit_price=10000,
        status=status,
        owner_id="u1",
        creator_id="u1",
    )
    db.add(contract)
    db.commit()
    db.refresh(contract)
    return contract


def _assert_e1_equivalence(db, contract, team_id=TEAM_ID):
    """E1 核心断言：match_flow_generic(CONTRACT) 与 legacy match_flow(contract)
    返回结果逐字一致（同 flow id、同 error）。

    legacy match_flow 是 thin wrapper，直接委托 match_flow_generic(CONTRACT,
    team_id, contract.total_amount, contract.license_type)，故二者必然一致；
    本断言把"E1 契约"固化为可执行回归——任何破坏委托关系或参数顺序的改动
    都会被此断言捕获。
    """
    legacy_flow, legacy_err = approval_flow_crud.match_flow(db, contract, team_id=team_id)
    g_flow, g_err = approval_flow_crud.match_flow_generic(
        db, BusinessType.CONTRACT, team_id,
        contract.total_amount, contract.license_type,
    )
    # flow 一致：同为 None 或同 id
    if legacy_flow is None:
        assert g_flow is None, (
            f"E1 破裂：legacy match_flow 返 None 但 generic 返 flow id={g_flow.id}"
        )
    else:
        assert g_flow is not None, (
            "E1 破裂：legacy match_flow 返 flow id="
            f"{legacy_flow.id} 但 generic 返 None"
        )
        assert g_flow.id == legacy_flow.id, (
            f"E1 破裂：legacy 选 flow id={legacy_flow.id}，generic 选 flow id={g_flow.id}"
        )
    # error 一致：逐字
    assert g_err == legacy_err, (
        f"E1 破裂：legacy err={legacy_err!r}，generic err={g_err!r}"
    )
    return legacy_flow, legacy_err


# ---------- 场景1：金额边界 ------------------------------------------------

def test_scenario1_amount_boundary_min(db_session):
    """金额恰好等于 min_amount 的合同匹配到对应 flow（边界含端点）。"""
    flow = _make_flow(
        db_session, flow_code="BOUNDARY_MIN", flow_name="边界-下限",
        min_amount=100000, max_amount=500000, license_type=None,
    )
    contract = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-BND-MIN",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    assert err is None
    assert matched is not None and matched.id == flow.id


def test_scenario1_amount_boundary_max(db_session):
    """金额恰好等于 max_amount 的合同匹配到对应 flow（边界含端点）。"""
    flow = _make_flow(
        db_session, flow_code="BOUNDARY_MAX", flow_name="边界-上限",
        min_amount=100000, max_amount=500000, license_type=None,
    )
    contract = _make_contract(
        db_session, total_amount=500000, license_type="SUBSCRIPTION",
        contract_number="CON-BND-MAX",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    assert err is None
    assert matched is not None and matched.id == flow.id


def test_scenario1_amount_below_min_unmatched(db_session):
    """金额 < min_amount 不匹配（沿用 CONTRACT 报错语义）。"""
    _make_flow(
        db_session, flow_code="BELOW_MIN", flow_name="低于下限",
        min_amount=100000, max_amount=500000, license_type=None,
    )
    contract = _make_contract(
        db_session, total_amount=99999, license_type="SUBSCRIPTION",
        contract_number="CON-BND-BELOW",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    assert matched is None
    assert err == "未找到匹配的审批流程，请联系管理员配置"


def test_scenario1_amount_above_max_unmatched(db_session):
    """金额 > max_amount 不匹配（沿用 CONTRACT 报错语义）。"""
    _make_flow(
        db_session, flow_code="ABOVE_MAX", flow_name="高于上限",
        min_amount=100000, max_amount=500000, license_type=None,
    )
    contract = _make_contract(
        db_session, total_amount=500001, license_type="SUBSCRIPTION",
        contract_number="CON-BND-ABOVE",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    assert matched is None
    assert err == "未找到匹配的审批流程，请联系管理员配置"


# ---------- 场景2：license_type 匹配 ---------------------------------------

def test_scenario2_license_type_matched(db_session):
    """license_type 匹配的 flow 被选中。"""
    flow = _make_flow(
        db_session, flow_code="LIC_MATCH", flow_name="授权-订阅",
        min_amount=None, max_amount=None, license_type="SUBSCRIPTION",
    )
    contract = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-LIC-MATCH",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    assert err is None
    assert matched is not None and matched.id == flow.id


def test_scenario2_license_type_excluded(db_session):
    """license_type 不匹配的 flow 被排除（合同走 SUBSCRIPTION，flow 限 PERPETUAL）。"""
    _make_flow(
        db_session, flow_code="LIC_PERP", flow_name="授权-买断",
        min_amount=None, max_amount=None, license_type="PERPETUAL",
    )
    contract = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-LIC-EXCL",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    # 唯一 flow 被排除 → 未匹配，沿用 CONTRACT 报错语义
    assert matched is None
    assert err == "未找到匹配的审批流程，请联系管理员配置"


def test_scenario2_license_type_none_flow_accepts_any(db_session):
    """flow.license_type=None 表示不限制，任何 license_type 的合同都匹配。"""
    flow = _make_flow(
        db_session, flow_code="LIC_ANY", flow_name="授权-不限",
        min_amount=None, max_amount=None, license_type=None,
    )
    contract_perp = _make_contract(
        db_session, total_amount=100000, license_type="PERPETUAL",
        contract_number="CON-LIC-ANY-P",
    )
    matched_p, err_p = _assert_e1_equivalence(db_session, contract_perp)
    assert err_p is None
    assert matched_p is not None and matched_p.id == flow.id

    contract_sub = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-LIC-ANY-S",
    )
    matched_s, err_s = _assert_e1_equivalence(db_session, contract_sub)
    assert err_s is None
    assert matched_s is not None and matched_s.id == flow.id


# ---------- 场景3：多 flow 评分排序 ----------------------------------------

def test_scenario3_multi_flow_score_ranking_narrow_wins(db_session):
    """多候选 flow 时按 calculate_flow_precision_score 选最优。

    构造：
    - WIDE_FLOW：min=1, max=1000000, license_type=None
      评分：min+max 都有 → 50；范围宽度 999999 远大于金额 100000 的 50%，
      无范围加分；有金额条件 +10；无 license_type 匹配 +0 → 60 分
    - NARROW_FLOW：min=99000, max=101000, license_type='SUBSCRIPTION'
      评分：min+max 都有 → 50；范围宽度 2000 < 金额 100000 的 10%（10000）→ +10；
      有金额条件 +10；license_type 匹配 +20 → 90 分

    合同 amount=100000, license_type='SUBSCRIPTION'：两 flow 都在范围内，
    NARROW_FLOW（90 分）应胜出。E1 要求 legacy 与 generic 选同一条。
    """
    wide = _make_flow(
        db_session, flow_code="WIDE", flow_name="宽范围-无授权",
        min_amount=1, max_amount=1000000, license_type=None,
    )
    narrow = _make_flow(
        db_session, flow_code="NARROW", flow_name="窄范围-订阅",
        min_amount=99000, max_amount=101000, license_type="SUBSCRIPTION",
    )
    contract = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-MULTI-SCORE",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    assert err is None
    assert matched is not None, "多 flow 评分排序应命中而非 None"
    assert matched.id == narrow.id, (
        f"应选高评分 NARROW_FLOW(id={narrow.id})，实选 id={matched.id}（wide id={wide.id}）"
    )


def test_scenario3_multi_flow_score_via_calculate_flow_precision_score(db_session):
    """直接验证 calculate_flow_precision_score 评分与排序选择一致。

    构造同上场景，但直接调 calculate_flow_precision_score 取分，
    断言 NARROW_FLOW 分 > WIDE_FLOW 分，且 match_flow 选高分 flow。
    """
    from app.crud.approval import calculate_flow_precision_score

    wide = _make_flow(
        db_session, flow_code="WIDE2", flow_name="宽范围2-无授权",
        min_amount=1, max_amount=1000000, license_type=None,
    )
    narrow = _make_flow(
        db_session, flow_code="NARROW2", flow_name="窄范围2-订阅",
        min_amount=99000, max_amount=101000, license_type="SUBSCRIPTION",
    )
    amount = 100000
    license_type = "SUBSCRIPTION"
    wide_score = calculate_flow_precision_score(wide, amount, license_type)
    narrow_score = calculate_flow_precision_score(narrow, amount, license_type)
    assert wide_score == 60, f"WIDE_FLOW 评分应为 60，实得 {wide_score}"
    assert narrow_score == 90, f"NARROW_FLOW 评分应为 90，实得 {narrow_score}"
    assert narrow_score > wide_score

    contract = _make_contract(
        db_session, total_amount=amount, license_type=license_type,
        contract_number="CON-MULTI-SCORE2",
    )
    matched, err = _assert_e1_equivalence(db_session, contract)
    assert err is None
    assert matched.id == narrow.id


# ---------- 端到端：全链路状态切换 -----------------------------------------

def test_e2e_submit_approve_final_node_signed(db_session):
    """合同提交 → approve 末节点 → status=SIGNED；approval=APPROVED。

    全链路状态切换不变（A5 适配器层 + A4 ContractAdapter.on_approved）。
    """
    flow, _node = _make_flow_with_node(
        db_session, flow_code="E2E_OK", flow_name="端到端-通过",
        min_amount=1, max_amount=1000000, license_type=None,
    )
    contract = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-E2E-OK",
    )
    # 提交：create_approval → adapter.on_submit 切 PENDING_REVIEW
    ap = approval_crud.create_approval(
        db_session, contract, flow, submitter_id="u1", submitter_name="eddie",
    )
    assert ap.status == ApprovalStatus.PENDING
    assert ap.business_type == BusinessType.CONTRACT
    assert ap.business_id == contract.id
    assert ap.contract_id == contract.id  # CONTRACT 分支兼容旧字段
    db_session.refresh(contract)
    assert contract.status == ContractStatus.PENDING_REVIEW

    # 末节点 APPROVE：无 next_node → APPROVED + on_approved → SIGNED
    from app.schemas.approval import ApprovalActionRequest
    req = ApprovalActionRequest(
        action=ApprovalAction.APPROVE, comment="同意", updated_time=ap.updated_time,
    )
    approval_crud.approve(
        db_session, ap, req, approver_id="reviewer", approver_name="审核人",
    )
    db_session.refresh(contract)
    db_session.refresh(ap)
    assert contract.status == ContractStatus.SIGNED
    assert ap.status == ApprovalStatus.APPROVED


def test_e2e_submit_reject_back_to_draft(db_session):
    """合同提交 → reject → status=DRAFT；approval=REJECTED。"""
    flow, _node = _make_flow_with_node(
        db_session, flow_code="E2E_REJ", flow_name="端到端-驳回",
        min_amount=1, max_amount=1000000, license_type=None,
    )
    contract = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-E2E-REJ",
    )
    ap = approval_crud.create_approval(
        db_session, contract, flow, submitter_id="u1", submitter_name="eddie",
    )
    db_session.refresh(contract)
    assert contract.status == ContractStatus.PENDING_REVIEW

    from app.schemas.approval import ApprovalActionRequest
    req = ApprovalActionRequest(
        action=ApprovalAction.REJECT, comment="驳回", updated_time=ap.updated_time,
    )
    approval_crud.approve(
        db_session, ap, req, approver_id="reviewer", approver_name="审核人",
    )
    db_session.refresh(contract)
    db_session.refresh(ap)
    assert contract.status == ContractStatus.DRAFT
    assert ap.status == ApprovalStatus.REJECTED


def test_e2e_submit_cancel_back_to_draft(db_session):
    """合同提交 → cancel → status=DRAFT；approval=CANCELLED。"""
    flow, _node = _make_flow_with_node(
        db_session, flow_code="E2E_CAN", flow_name="端到端-撤回",
        min_amount=1, max_amount=1000000, license_type=None,
    )
    contract = _make_contract(
        db_session, total_amount=100000, license_type="SUBSCRIPTION",
        contract_number="CON-E2E-CAN",
    )
    ap = approval_crud.create_approval(
        db_session, contract, flow, submitter_id="u1", submitter_name="eddie",
    )
    db_session.refresh(contract)
    assert contract.status == ContractStatus.PENDING_REVIEW

    approval_crud.cancel(db_session, ap, user_id="u1")
    db_session.refresh(contract)
    db_session.refresh(ap)
    assert contract.status == ContractStatus.DRAFT
    assert ap.status == ApprovalStatus.CANCELLED
